from contextlib import contextmanager
from datetime import datetime, timezone

from fastmcp import FastMCP

from db.database import SessionLocal
from donna_mcp.guard import mutating
from models.orm import ConversationSummary
from store.conversation_store import ConversationStore

conversation_mcp = FastMCP("conversation")


@contextmanager
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@conversation_mcp.tool()
@mutating("conv")
def ensure_conversation_state(phone_number: str, role: str) -> dict:
    """Create the conversation state row for a phone number if missing."""
    with _db() as db:
        ConversationStore(db)._get_or_create(phone_number, role)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def update_conversation_state(phone_number: str, data: dict) -> dict:
    """Set fields on a conversation state row."""
    with _db() as db:
        ConversationStore(db)._update(phone_number, data)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def update_conversation_context(phone_number: str, context_updates: dict) -> dict:
    """Merge keys into a conversation's context."""
    with _db() as db:
        ConversationStore(db)._update_context(phone_number, context_updates)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def clear_conversation_context(phone_number: str) -> dict:
    """Clear pending context keys, preserving history and protected (_) keys."""
    with _db() as db:
        ConversationStore(db)._clear_context(phone_number)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def append_conversation_history(phone_number: str, role: str, content: str) -> dict:
    """Append a turn to conversation history. role is 'user' or 'donna'."""
    with _db() as db:
        ConversationStore(db)._append_history(phone_number, role, content)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def record_donna_message(phone_number: str, message: str) -> dict:
    """Record the last message Donna sent and append it to history."""
    with _db() as db:
        ConversationStore(db)._update_last_donna_message(phone_number, message)
        return {"ok": True}


@conversation_mcp.tool()
@mutating("conv")
def save_conversation_summary(phone_number: str, summary: str, turn_count: int) -> dict:
    """Persist an end-of-conversation summary."""
    with _db() as db:
        db.add(ConversationSummary(
            phone_number=phone_number,
            summary=summary,
            turn_count=turn_count,
            session_end=datetime.now(timezone.utc),
        ))
        db.commit()
        return {"ok": True}
