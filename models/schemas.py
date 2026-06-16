from typing import Literal
from pydantic import BaseModel


class FirewallResult(BaseModel):
    action: Literal["pass", "redirect", "block"]
    threat: str | None = None
    severity: Literal["low", "medium", "high"] | None = None
    sanitized_input: str | None = None
    redirect_message: str | None = None
    log_entry: dict = {}


class IntentResult(BaseModel):
    intent: str
    entities: dict
    confidence: float  # 0.0 - 1.0


class JudgeResult(BaseModel):
    decision: Literal["autonomous", "notify_admin", "escalate_to_admin"]
    reason: str
    confidence: float


class MessageEnvelope(BaseModel):
    event: str
    phone: str
    payload: dict
    timestamp: str
    source: str
