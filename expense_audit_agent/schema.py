"""
Shared data contracts for the expense audit pipeline.

Every sub-agent reads/writes a subset of this schema via ADK session state
under the key "expense_claim". Keeping one schema everyone agrees on is what
lets four independently-developed agents compose into one reliable pipeline.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    SUBMITTED = "submitted"
    EXTRACTED = "extracted"
    POLICY_CHECKED = "policy_checked"
    RISK_SCORED = "risk_scored"
    AUTO_APPROVED = "auto_approved"
    AUTO_REJECTED = "auto_rejected"
    ESCALATED = "escalated"
    BLOCKED_INJECTION = "blocked_injection"


class PolicyFlag(BaseModel):
    rule_id: str
    description: str
    severity: str = Field(description="info | warning | violation")


class RiskFinding(BaseModel):
    signal: str
    detail: str
    weight: float = Field(description="0.0 (benign) to 1.0 (severe)")


class ExpenseClaim(BaseModel):
    claim_id: str
    submitter: str
    raw_receipt_text: str

    # Filled by IntakeAgent
    vendor: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    amount_usd: Optional[float] = None
    expense_date: Optional[str] = None
    category: Optional[str] = None

    # Filled by PolicyCheckAgent
    policy_flags: list[PolicyFlag] = Field(default_factory=list)

    # Filled by FraudRiskAgent
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    risk_score: Optional[float] = None

    # Filled by ApprovalAgent
    status: ClaimStatus = ClaimStatus.SUBMITTED
    decision_reason: Optional[str] = None

    # Filled by guardrails layer (any stage)
    injection_suspected: bool = False
    injection_evidence: Optional[str] = None