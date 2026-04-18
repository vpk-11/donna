from pydantic import BaseModel


class IntentResult(BaseModel):
    intent: str
    entities: dict
    needs_clarification: bool
    clarification_question: str | None
