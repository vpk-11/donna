from datetime import datetime
from sqlalchemy.orm import Session
from models.orm import ConversationState

HISTORY_MAX_TURNS = 10


class ConversationStore:
    def __init__(self, db: Session):
        self.db = db

    def get_by_phone(self, phone_number: str) -> ConversationState | None:
        return (
            self.db.query(ConversationState)
            .filter(ConversationState.phone_number == phone_number)
            .first()
        )

    def get_or_create(self, phone_number: str, role: str) -> ConversationState:
        state = self.get_by_phone(phone_number)
        if not state:
            state = ConversationState(
                phone_number=phone_number,
                role=role,
                context={},
                turn_count=0,
                handoff_active=False,
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)
        return state

    def update(self, phone_number: str, data: dict) -> ConversationState | None:
        state = self.get_by_phone(phone_number)
        if not state:
            return None
        for key, value in data.items():
            setattr(state, key, value)
        state.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(state)
        return state

    def update_context(self, phone_number: str, context_updates: dict) -> None:
        state = self.get_by_phone(phone_number)
        if not state:
            return
        ctx = dict(state.context or {})
        ctx.update(context_updates)
        state.context = ctx
        state.updated_at = datetime.utcnow()
        self.db.commit()

    def clear_context(self, phone_number: str) -> None:
        """Clear pending state but preserve history and protected keys (prefixed _)."""
        state = self.get_by_phone(phone_number)
        if not state:
            return
        protected = {k: v for k, v in (state.context or {}).items() if k.startswith("_")}
        state.context = protected
        state.updated_at = datetime.utcnow()
        self.db.commit()

    def append_history(self, phone_number: str, role: str, content: str) -> None:
        """Append a turn to conversation history. role is 'user' or 'donna'."""
        state = self.get_by_phone(phone_number)
        if not state:
            return
        ctx = dict(state.context or {})
        history = list(ctx.get("_history", []))
        history.append({"role": role, "content": content})
        if len(history) > HISTORY_MAX_TURNS:
            history = history[-HISTORY_MAX_TURNS:]
        ctx["_history"] = history
        state.context = ctx
        state.updated_at = datetime.utcnow()
        self.db.commit()

    def get_history(self, phone_number: str) -> list[dict]:
        state = self.get_by_phone(phone_number)
        if not state:
            return []
        return list((state.context or {}).get("_history", []))

    def update_last_donna_message(self, phone_number: str, message: str) -> None:
        """Called after every Donna send. Updates last_donna_message and appends to history."""
        state = self.get_by_phone(phone_number)
        if not state:
            return
        state.last_donna_message = message
        # Append to history
        ctx = dict(state.context or {})
        history = list(ctx.get("_history", []))
        history.append({"role": "donna", "content": message})
        if len(history) > HISTORY_MAX_TURNS:
            history = history[-HISTORY_MAX_TURNS:]
        ctx["_history"] = history
        state.context = ctx
        state.updated_at = datetime.utcnow()
        self.db.commit()
