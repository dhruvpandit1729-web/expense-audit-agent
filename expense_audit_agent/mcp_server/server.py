"""
MCP server for the expense audit pipeline.

This is deliberately a SEPARATE process/server speaking the Model Context
Protocol, not an in-process Python function, to demonstrate genuine agent
interoperability (Day 2 concept): FraudRiskAgent talks to this server the
same way it could talk to a third party's MCP server it doesn't control or
even share a codebase with.

Tools exposed:
- convert_to_usd(amount, currency) -> dict
- check_duplicate_receipt(vendor, amount_usd, expense_date) -> dict
    Looks for a prior claim with the same vendor/amount within a few days
    of each other, the classic duplicate-submission fraud pattern.
- log_claim(claim_id, vendor, amount_usd, expense_date) -> dict
    Appends a processed claim to the log, called only after final approval.

Run standalone (for manual testing):
    python -m expense_audit_agent.mcp_server.server
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("expense-audit-tools")

_CLAIMS_LOG = Path(__file__).resolve().parents[2] / "data" / "submitted_claims_log.json"

# Static demo FX table so the capstone runs offline/deterministically.
# Swap for a live FX API call in production.
_FX_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "INR": 0.012,
    "JPY": 0.0064,
    "CAD": 0.73,
}


@mcp.tool()
def convert_to_usd(amount: float, currency: str) -> dict:
    """Convert an expense amount to USD using a fixed reference rate table.

    Args:
        amount: the expense amount in its original currency
        currency: ISO currency code, e.g. "EUR", "INR"

    Returns:
        dict with amount_usd and the rate used, or an error if the
        currency isn't supported.
    """
    code = currency.upper().strip()
    if code not in _FX_TO_USD:
        return {"error": f"Unsupported currency code: {code}"}
    rate = _FX_TO_USD[code]
    return {"amount_usd": round(amount * rate, 2), "rate_used": rate, "currency": code}


@mcp.tool()
def check_duplicate_receipt(vendor: str, amount_usd: float, expense_date: str) -> dict:
    """Check whether a claim with the same vendor and amount was already
    submitted within 5 days of this expense_date -- the standard signature
    of an accidental or fraudulent duplicate submission.

    Args:
        vendor: normalized vendor name
        amount_usd: claim amount already converted to USD
        expense_date: ISO date string, e.g. "2026-06-15"

    Returns:
        dict with is_duplicate (bool) and matched_claim_id if found.
    """
    if not _CLAIMS_LOG.exists():
        return {"is_duplicate": False, "matched_claim_id": None}

    raw_text = _CLAIMS_LOG.read_text().strip()
    if not raw_text:
        return {"is_duplicate": False, "matched_claim_id": None}

    log = json.loads(raw_text)
    target_date = datetime.fromisoformat(expense_date)

    for entry in log:
        if entry["vendor"].lower() != vendor.lower():
            continue
        if abs(entry["amount_usd"] - amount_usd) > 0.01:
            continue
        entry_date = datetime.fromisoformat(entry["expense_date"])
        if abs((entry_date - target_date).days) <= 5:
            return {"is_duplicate": True, "matched_claim_id": entry["claim_id"]}

    return {"is_duplicate": False, "matched_claim_id": None}


@mcp.tool()
def log_claim(claim_id: str, vendor: str, amount_usd: float, expense_date: str) -> dict:
    """Append a processed claim to the shared log so future duplicate
    checks can see it. Call this once a claim clears fraud review.
    """
    _CLAIMS_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing_text = _CLAIMS_LOG.read_text().strip() if _CLAIMS_LOG.exists() else ""
    log = json.loads(existing_text) if existing_text else []
    log.append(
        {
            "claim_id": claim_id,
            "vendor": vendor,
            "amount_usd": amount_usd,
            "expense_date": expense_date,
        }
    )
    _CLAIMS_LOG.write_text(json.dumps(log, indent=2))
    return {"logged": True}


if __name__ == "__main__":
    mcp.run(transport="stdio")