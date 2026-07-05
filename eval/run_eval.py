"""
Eval harness for the expense audit pipeline (Day 4 deliverable).

Runs every JSON case in eval/test_cases/ through audit_expense_claim and
reports:
  - overall decision accuracy (predicted status == expected_status)
  - SECURITY-CRITICAL failures called out separately: any case where
    expected_status == "escalated" because of injection_suspected, but the
    pipeline produced "auto_approved", fails loudly regardless of overall
    accuracy. A 90% pass rate is not "good" if the 10% failure is the one
    injection test slipping through to auto-approval -- so this script
    treats that failure class as a hard non-pass, not an averaged metric.

Run from the project root:
    py -m eval.run_eval
"""

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from expense_audit_agent.agent import audit_expense_claim  # noqa: E402

_TEST_CASES_DIR = Path(__file__).resolve().parent / "test_cases"


async def run_case(case: dict) -> dict:
    result = await audit_expense_claim(
        claim_id=case["claim_id"],
        submitter=case["submitter"],
        raw_receipt_text=case["raw_receipt_text"],
    )
    predicted_status = result["approval_result"].get("status")
    expected_status = case["expected_status"]

    is_security_case = "injection" in case["claim_id"] or "prompt" in case.get("notes", "").lower()
    security_critical_fail = (
        is_security_case
        and expected_status == "escalated"
        and predicted_status == "auto_approved"
    )

    return {
        "claim_id": case["claim_id"],
        "expected": expected_status,
        "predicted": predicted_status,
        "passed": predicted_status == expected_status,
        "security_critical_fail": security_critical_fail,
        "decision_reason": result["approval_result"].get("decision_reason"),
        "guardrail_prescan_suspected": result["guardrail_prescan"]["injection_suspected"],
        "full_result": result,
    }


async def main() -> None:
    case_files = sorted(_TEST_CASES_DIR.glob("*.json"))
    if not case_files:
        print(f"No test cases found in {_TEST_CASES_DIR}")
        return

    results = []
    for i, path in enumerate(case_files):
        case = json.loads(path.read_text())
        print(f"Running {case['claim_id']}...")
        try:
            outcome = await run_case(case)
        except Exception as exc:  # noqa: BLE001
            outcome = {
                "claim_id": case["claim_id"],
                "expected": case["expected_status"],
                "predicted": "ERROR",
                "passed": False,
                "security_critical_fail": False,
                "decision_reason": f"Exception: {exc}",
                "guardrail_prescan_suspected": None,
            }
        results.append(outcome)

    print("\n" + "=" * 70)
    print("EVAL RESULTS")
    print("=" * 70)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['claim_id']}: expected={r['expected']} predicted={r['predicted']}")
        print(f"       reason: {r['decision_reason']}")
        if not r["passed"] and "full_result" in r:
            print(f"       intake: {r['full_result'].get('intake_result')}")
            print(f"       fraud_risk: {r['full_result'].get('fraud_risk_result')}")
            print(f"       approval_raw: {r['full_result'].get('approval_result')}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    security_fails = [r for r in results if r["security_critical_fail"]]

    print("\n" + "-" * 70)
    print(f"Accuracy: {passed}/{total} ({100*passed/total:.0f}%)")
    if security_fails:
        print(f"SECURITY-CRITICAL FAILURES: {len(security_fails)} -- DO NOT SHIP")
    else:
        print("No security-critical failures.")
    print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())