from typing import Literal
from pydantic import BaseModel


class FirewallResult(BaseModel):
    action: Literal["pass", "redirect", "block"]
    threat: str | None = None
    severity: Literal["low", "medium", "high"] | None = None
    sanitized_input: str | None = None
    redirect_message: str | None = None
    log_entry: dict = {}


class MessageEnvelope(BaseModel):
    event: str
    phone: str
    payload: dict
    timestamp: str
    source: str
