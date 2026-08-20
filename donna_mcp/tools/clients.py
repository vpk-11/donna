from contextlib import contextmanager
from typing import Optional

from fastmcp import FastMCP

from db.database import SessionLocal
from store.client_store import ClientStore
from store.provider_store import ProviderStore

clients_mcp = FastMCP("clients")

VALID_STATUSES = {"active", "inactive", "prospect", "cold_lead"}


@contextmanager
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _client_dict(c) -> dict:
    return {
        "id": c.id,
        "provider_id": c.provider_id,
        "name": c.name,
        "phone_number": c.phone_number,
        "address": c.address,
        "status": c.status,
        "membership_type": c.membership_type,
        "sessions_per_week": c.sessions_per_week,
        "preferred_days": c.preferred_days,
        "preferred_time": c.preferred_time,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@clients_mcp.tool()
def get_client(client_id: int) -> dict:
    """Get a single client by ID."""
    with _db() as db:
        client = ClientStore(db).get(client_id)
        if not client:
            return {"error": f"No client with id={client_id}"}
        return _client_dict(client)


@clients_mcp.tool()
def get_client_by_phone(phone_number: str) -> dict:
    """Get a client by their phone number."""
    with _db() as db:
        client = ClientStore(db).get_by_phone(phone_number)
        if not client:
            return {"error": f"No client with phone={phone_number}"}
        return _client_dict(client)


@clients_mcp.tool()
def list_clients() -> list[dict]:
    """List all clients for the provider."""
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return []
        clients = ClientStore(db).list_by_provider(provider.id)
        return [_client_dict(c) for c in clients]


@clients_mcp.tool()
def create_client(
    name: str,
    phone_number: str,
    status: str = "active",
    address: Optional[str] = None,
    membership_type: Optional[str] = None,
    sessions_per_week: Optional[int] = None,
    preferred_days: Optional[list[str]] = None,
    preferred_time: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Create a new client. status must be one of: active, inactive, prospect, cold_lead.
    preferred_days example: ["mon", "wed", "fri"].
    preferred_time example: "morning" or "09:00".
    """
    if status not in VALID_STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"}
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        existing = ClientStore(db).get_by_phone(phone_number)
        if existing:
            return {"error": f"Client with phone={phone_number} already exists (id={existing.id})"}
        data = {
            "provider_id": provider.id,
            "name": name,
            "phone_number": phone_number,
            "status": status,
            "address": address,
            "membership_type": membership_type,
            "sessions_per_week": sessions_per_week,
            "preferred_days": preferred_days or [],
            "preferred_time": preferred_time,
            "notes": notes,
        }
        client = ClientStore(db).create(data)
        return _client_dict(client)


@clients_mcp.tool()
def update_client(
    client_id: int,
    name: Optional[str] = None,
    phone_number: Optional[str] = None,
    status: Optional[str] = None,
    address: Optional[str] = None,
    membership_type: Optional[str] = None,
    sessions_per_week: Optional[int] = None,
    preferred_days: Optional[list[str]] = None,
    preferred_time: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Update one or more fields on an existing client. Only provided fields are changed."""
    updates = {
        k: v
        for k, v in {
            "name": name,
            "phone_number": phone_number,
            "status": status,
            "address": address,
            "membership_type": membership_type,
            "sessions_per_week": sessions_per_week,
            "preferred_days": preferred_days,
            "preferred_time": preferred_time,
            "notes": notes,
        }.items()
        if v is not None
    }
    if not updates:
        return {"error": "No fields to update"}
    with _db() as db:
        client = ClientStore(db).update(client_id, updates)
        if not client:
            return {"error": f"No client with id={client_id}"}
        return _client_dict(client)
