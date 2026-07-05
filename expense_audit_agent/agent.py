"""
Root orchestrator for the Expense Audit & Compliance Agent fleet.

Demonstrates: multi-agent orchestration (Day 1/2) via ADK's SequentialAgent,
composing four independently-defined sub-agents (each in its own
sub_agents/ folder, each individually testable) into one governed pipeline.

Pipeline shape:
    IntakeAgent -> PolicyCheckAgent -> FraudRiskAgent -> ApprovalAgent

Each stage writes its output to session state (via output_key) and reads
the prior stage's output from there -- this keeps stages loosely coupled:
PolicyCheckAgent doesn't need to know HOW IntakeAgent extracted fields,
only that intake_result exists in state.

The guardrail input scan (prepare_receipt_for_intake) and output check
(postprocess_decision) are NOT agents -- they're plain Python, run by the
orchestrator itself outside the LLM call graph, so they can't be
prompt-injected into skipping themselves.
"""

from __future__ import annotations
import json
import uuid

from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from expense_audit_agent.sub_agents.intake.agent import (
    intake_agent,
    prepare_receipt_for_intake,
)
from expense_audit_agent.sub_agents.policy_check.agent import policy_check_agent
from expense_audit_agent.sub_agents.fraud_risk.agent import fraud_risk_agent
from expense_audit_agent.sub_agents.approval.agent import (
    approval_agent,
    postprocess_decision,
)

root_agent = SequentialAgent(
    name="ExpenseAuditOrchestrator",
    description=(
        "Audits an expense claim end-to-end: extracts structured fields "
        "from a receipt, checks it against policy and precedent, scores "
        "fraud risk via MCP tools, and produces an approve/reject/escalate "
        "decision with mandatory human-in-the-loop paths for ambiguous or "
        "suspicious cases."
    ),
    sub_agents=[intake_agent, policy_check_agent, fraud_risk_agent, approval_agent],
)


async def audit_expense_claim(claim_id: str, submitter: str, raw_receipt_text: str) -> dict:
    """End-to-end entry point used by the eval harness and any external
    caller (e.g. a Slack bot, a web form). Wraps the guardrail pre/post
    steps around a run of root_agent.

    This is the function you actually call to run the pipeline -- not
    root_agent directly -- because the guardrail boundary has to wrap
    every call, not be something a caller can forget to apply.
    """
    guardrail_prep = prepare_receipt_for_intake(raw_receipt_text)

    runner = InMemoryRunner(agent=root_agent, app_name="expense_audit")
    session = await runner.session_service.create_session(
        app_name="expense_audit", user_id=submitter, session_id=str(uuid.uuid4())
    )

    user_message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    f"claim_id: {claim_id}\n"
                    f"submitter: {submitter}\n"
                    f"injection_prescan_suspected: {guardrail_prep['injection_suspected']}\n"
                    f"injection_prescan_evidence: {guardrail_prep['injection_evidence']}\n\n"
                    f"{guardrail_prep['wrapped_text']}"
                )
            )
        ],
    )

    final_state = {}
    try:
        async for event in runner.run_async(
            user_id=submitter, session_id=session.id, new_message=user_message
        ):
            if event.is_final_response():
                final_state = (
                    await runner.session_service.get_session(
                        app_name="expense_audit", user_id=submitter, session_id=session.id
                    )
                ).state
    except Exception as exc:
        # Fail SAFE, not open: any pipeline error (model confusion, tool
        # crash, malformed output) defaults to human escalation rather
        # than silently dropping the claim or, worse, treating an error
        # as an implicit approval. A crash is never treated as "fine."
        return {
            "claim_id": claim_id,
            "intake_result": {},
            "policy_check_result": {},
            "fraud_risk_result": {},
            "approval_result": {
                "status": "escalated",
                "decision_reason": f"Pipeline error, escalated for manual review: {exc}",
            },
            "guardrail_prescan": guardrail_prep,
        }

    def _safe_parse_json(raw) -> dict:
        """Agent text output is stored as a raw string in session state.
        Parse it defensively -- strip markdown fences if the model added
        them despite instructions, and fall back to a dict wrapping the
        raw text so downstream code never crashes on a plain string."""
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        text = str(raw).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw_text": str(raw)}

    intake_result = _safe_parse_json(final_state.get("intake_result"))
    approval_result = _safe_parse_json(final_state.get("approval_result"))

    output_check = postprocess_decision(
        decision_reason=approval_result.get("decision_reason", ""),
        amount_usd=intake_result.get("amount_usd") or intake_result.get("amount"),
    )
    
    if output_check["override_status"]:
        approval_result["status"] = output_check["override_status"]
        approval_result["decision_reason"] = output_check["override_reason"]

    return {
        "claim_id": claim_id,
        "intake_result": intake_result,
        "policy_check_result": _safe_parse_json(final_state.get("policy_check_result")),
        "fraud_risk_result": _safe_parse_json(final_state.get("fraud_risk_result")),
        "approval_result": approval_result,
        "guardrail_prescan": guardrail_prep,
    }