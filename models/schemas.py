from typing import Literal
from pydantic import BaseModel


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
