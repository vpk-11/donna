import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from contextlib import contextmanager
from typing import Any, Optional

from fastmcp import FastMCP

from db.database import SessionLocal
from store.conversation_store import ConversationStore
from store.provider_store import ProviderStore

admin_mcp = FastMCP("admin")

UPDATABLE_PROVIDER_FIELDS = {
    "name",
    "business_type",
    "location_type",
    "auto_book",
    "buffer_mins",
    "working_hours",
    "business_config",
    "phone_number",
}


@contextmanager
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _provider_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "phone_number": p.phone_number,
        "business_type": p.business_type,
        "location_type": p.location_type,
        "auto_book": p.auto_book,
        "buffer_mins": p.buffer_mins,
        "working_hours": p.working_hours,
        "business_config": p.business_config,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@admin_mcp.tool()
def get_provider() -> dict:
    """Get the current provider configuration."""
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        return _provider_dict(provider)


@admin_mcp.tool()
def update_provider(field: str, value: Any) -> dict:
    """
    Update a single provider field.
    Updatable fields: name, business_type, location_type, auto_book,
    buffer_mins, working_hours, business_config, phone_number.
    working_hours format: {"mon": ["09:00", "17:00"], "tue": ["09:00", "17:00"], ...}.
    """
    if field not in UPDATABLE_PROVIDER_FIELDS:
        return {"error": f"Field '{field}' is not updatable. Valid: {sorted(UPDATABLE_PROVIDER_FIELDS)}"}
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        updated = ProviderStore(db).update(provider.id, {field: value})
        return _provider_dict(updated)


@admin_mcp.tool()
def get_conversation_state(phone_number: str) -> dict:
    """Get current conversation state for a phone number (admin or client)."""
    with _db() as db:
        state = ConversationStore(db).get_or_create(phone_number, role="unknown")
        return {
            "phone_number": state.phone_number,
            "role": state.role,
            "context": state.context,
            "last_donna_message": state.last_donna_message,
            "client_id": state.client_id,
            "session_id": state.session_id,
            "turn_count": state.turn_count,
            "handoff_active": state.handoff_active,
            "handoff_target_phone": state.handoff_target_phone,
            "last_message_at": state.last_message_at.isoformat() if state.last_message_at else None,
        }


@admin_mcp.tool()
def reset_conversation_state(phone_number: str) -> dict:
    """
    Reset conversation context for a phone number.
    Clears pending context keys, handoff state, and turn count.
    Does NOT delete the record -- resets it to a clean state.
    """
    with _db() as db:
        store = ConversationStore(db)
        state = store.get_or_create(phone_number, role="unknown")
        store.clear_context(state.phone_number)
        store.update(state.phone_number, {
            "handoff_active": False,
            "handoff_target_phone": None,
            "turn_count": 0,
        })
        return {"ok": True, "phone_number": phone_number}
