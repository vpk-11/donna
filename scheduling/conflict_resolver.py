from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from models.orm import Provider
from store.session_store import SessionStore
from store.client_store import ClientStore


@dataclass
class ConflictResult:
    status: str  # "FREE" | "ALTERNATIVES" | "SWAP_POSSIBLE" | "NO_AVAILABILITY"
    slot: Optional[datetime] = None
    slots: Optional[list[datetime]] = None
    blocking_client_id: Optional[int] = None
    blocking_client_name: Optional[str] = None
    blocking_alternatives: Optional[list[datetime]] = None


async def resolve_slot(
    provider_id: int,
    requested_at: datetime,
    duration_mins: int,
    requesting_client_id: int,
    db: Session,
    session_store: SessionStore,
    client_store: Optional[ClientStore],
    provider: Provider,
) -> ConflictResult:
    conflict_session = session_store.get_conflict(
        provider_id, requested_at, duration_mins, provider.buffer_mins
    )
    if not conflict_session:
        return ConflictResult(status="FREE", slot=requested_at)

    alternatives = session_store.get_free_slots(
        provider_id, requested_at.date(), duration_mins, provider
    )
    if alternatives:
        return ConflictResult(status="ALTERNATIVES", slots=alternatives)

    if client_store is None:
        return ConflictResult(status="NO_AVAILABILITY")

    blocking_client = client_store.get(conflict_session.client_id)
    if not blocking_client:
        return ConflictResult(status="NO_AVAILABILITY")

    blocking_alternatives = session_store.get_free_slots(
        provider_id, requested_at.date(), duration_mins, provider,
        exclude_client_id=blocking_client.id
    )
    if blocking_alternatives:
        return ConflictResult(
            status="SWAP_POSSIBLE",
            blocking_client_id=blocking_client.id,
            blocking_client_name=blocking_client.name,
            blocking_alternatives=blocking_alternatives,
        )

    return ConflictResult(status="NO_AVAILABILITY")
