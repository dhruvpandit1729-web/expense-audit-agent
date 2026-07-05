import json
from pathlib import Path

log_path = Path("data/submitted_claims_log.json")
log_path.parent.mkdir(exist_ok=True)
log_path.write_text(json.dumps([
    {"claim_id": "prior-claim-001", "vendor": "Delta Airlines", "amount_usd": 410.00, "expense_date": "2026-06-11"}
], indent=2))
print("Seeded duplicate claim.")