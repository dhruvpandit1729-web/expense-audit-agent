"""
Agent Skill: Policy Memory.

This is the "Agent Skill" deliverable for the capstone (Day 3 concept):
a self-contained, reusable capability -- rules + memory of past rulings --
that any agent can be equipped with via ADK's tool interface, independent
of which agent or which pipeline uses it.

Why this needs memory at all: company expense policy has edge cases that
aren't fully specified in the written rules (e.g. "is a $40 team lunch for
3 people okay" depends on precedent, not just a per-meal cap). Each ruling
this skill makes is written back to the store, so the SAME ambiguous case
is answered consistently next time instead of re-litigated by the LLM from
scratch -- and a human who overrides a ruling teaches the skill durably.

Storage: a flat JSON file under data/ for the capstone demo. The interface
(get/record) is the contract -- swap the backing store for a real DB or
Vertex AI Search index without touching any agent code.
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional

_STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "policy_memory.json"

# The written, static policy. Treated as ground truth; memory only resolves
# what these rules leave ambiguous.
POLICY_RULES = {
    "MEAL_CAP": {
        "description": "Individual meals capped at $75 USD; team meals capped at $40/person.",
        "severity_if_violated": "violation",
    },
    "RECEIPT_REQUIRED": {
        "description": "Any expense over $25 USD requires an itemized receipt.",
        "severity_if_violated": "violation",
    },
    "ALCOHOL": {
        "description": "Alcohol is reimbursable only as part of a client-facing team meal, max $25/person of the total.",
        "severity_if_violated": "warning",
    },
    "TRAVEL_CLASS": {
        "description": "Air travel under 6 hours must be economy class.",
        "severity_if_violated": "violation",
    },
    "SOFTWARE_PREAPPROVAL": {
        "description": "Software/SaaS purchases over $100 require pre-approval from a manager on file.",
        "severity_if_violated": "violation",
    },
}
CATEGORY_RULE_MAP = {
    "meals": ["MEAL_CAP", "ALCOHOL", "RECEIPT_REQUIRED"],
    "travel": ["TRAVEL_CLASS", "RECEIPT_REQUIRED"],
    "software": ["SOFTWARE_PREAPPROVAL", "RECEIPT_REQUIRED"],
}


def get_applicable_rules(category: str) -> dict:
    """Return ONLY the policy rules relevant to this claim's category.
    This exists because instructing the model to 'ignore irrelevant rules'
    from the full rulebook proved unreliable with a smaller local model --
    it kept misapplying MEAL_CAP to travel claims despite explicit
    instructions to scope by category. Removing the irrelevant rules from
    view entirely is more robust than asking the model to filter them out
    itself. Unknown categories fall back to RECEIPT_REQUIRED only.
    """
    category = category.lower().strip()
    rule_ids = CATEGORY_RULE_MAP.get(category, ["RECEIPT_REQUIRED"])
    return {rid: POLICY_RULES[rid] for rid in rule_ids if rid in POLICY_RULES}


def _load_store() -> dict:
    if not _STORE_PATH.exists():
        return {"rulings": []}
    raw_text = _STORE_PATH.read_text().strip()
    if not raw_text:
        return {"rulings": []}
    return json.loads(raw_text)


def _save_store(store: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(store, indent=2))


def get_policy_rules() -> dict:
    """Return the static, written policy rules. Always called first."""
    return POLICY_RULES


def recall_similar_ruling(category: str, situation_summary: str) -> Optional[dict]:
    """Look up a precedent for an ambiguous case the written rules don't cover.

    Simple keyword overlap for the demo -- swap for embedding similarity
    against a vector store for production without changing the call site.
    """
    store = _load_store()
    situation_words = set(situation_summary.lower().split())
    best, best_score = None, 0
    for ruling in store["rulings"]:
        if ruling["category"] != category:
            continue
        ruling_words = set(ruling["situation_summary"].lower().split())
        overlap = len(situation_words & ruling_words)
        if overlap > best_score:
            best, best_score = ruling, overlap
    return best if best_score >= 2 else None


def record_ruling(
    category: str,
    situation_summary: str,
    ruling: str,
    decided_by: str,
) -> dict:
    """Persist a new ruling so the same ambiguous case resolves consistently
    next time. decided_by is 'agent' or 'human_override'; human overrides
    should be weighted higher when recalled (left as a TODO hook for
    whoever extends this skill -- e.g. prefer human_override rulings on tie).
    """
    store = _load_store()
    entry = {
        "category": category,
        "situation_summary": situation_summary,
        "ruling": ruling,
        "decided_by": decided_by,
        "timestamp": time.time(),
    }
    store["rulings"].append(entry)
    _save_store(store)
    return entry

def check_per_person_cap(total_amount: float, headcount: int, cap_per_person: float) -> dict:
    """Deterministic per-person cap check..."""
    if not headcount or headcount <= 0:
        headcount = 1
    if cap_per_person is None:
        cap_per_person = float("inf")
    per_person = round(total_amount / headcount, 2)
    return {
        "per_person_amount": per_person,
        "cap": cap_per_person,
        "exceeds_cap": per_person > cap_per_person,
    }