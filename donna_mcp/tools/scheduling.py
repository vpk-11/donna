import asyncio
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from fastmcp import FastMCP

from config import load_business_config
from db.database import SessionLocal
from donna_mcp.guard import mutating
from scheduling.conflict_resolver import resolve_slot
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from store.session_store import SessionStore

scheduling_mcp = FastMCP("scheduling")


@contextmanager
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _session_dict(s) -> dict:
    return {
        "id": s.id,
        "provider_id": s.provider_id,
        "client_id": s.client_id,
        "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
        "duration_mins": s.duration_mins,
        "location": s.location,
        "status": s.status,
        "is_recurring": s.is_recurring,
        "recurrence_type": s.recurrence_type,
        "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@scheduling_mcp.tool()
def get_free_slots(date: str, duration_mins: int = 60) -> dict:
    """
    Get available time slots for a given date.
    date: ISO date string, e.g. "2026-06-15".
    Returns list of ISO datetime strings representing open slot start times.
    """
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": f"Invalid date format: {date}. Use YYYY-MM-DD."}
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        slots = SessionStore(db).get_free_slots(
            provider.id, target_date, duration_mins, provider
        )
        return {"slots": [s.isoformat() for s in slots]}


@scheduling_mcp.tool()
def check_slot_conflict(
    requested_at: str,
    duration_mins: int = 60,
    requesting_client_id: int = 0,
) -> dict:
    """
    Check if a time slot is free, and if not, whether alternatives or a swap exist.
    Returns status: FREE | ALTERNATIVES | SWAP_POSSIBLE | NO_AVAILABILITY.
    requested_at: ISO datetime string.
    requesting_client_id: 0 if no specific client (e.g. checking on behalf of new client).
    """
    try:
        requested_dt = datetime.fromisoformat(requested_at)
    except ValueError:
        return {"error": f"Invalid datetime: {requested_at}. Use ISO 8601."}
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        # V3: resolve_slot should be sync
        result = asyncio.run(
            resolve_slot(
                provider_id=provider.id,
                requested_at=requested_dt,
                duration_mins=duration_mins,
                requesting_client_id=requesting_client_id,
                db=db,
                session_store=SessionStore(db),
                client_store=ClientStore(db),
                provider=provider,
            )
        )
        out = {"status": result.status}
        if result.slot:
            out["slot"] = result.slot.isoformat()
        if result.slots:
            out["slots"] = [s.isoformat() for s in result.slots]
        if result.blocking_client_id:
            out["blocking_client_id"] = result.blocking_client_id
            out["blocking_client_name"] = result.blocking_client_name
        if result.blocking_alternatives:
            out["blocking_alternatives"] = [s.isoformat() for s in result.blocking_alternatives]
        return out


@scheduling_mcp.tool()
@mutating("client_id")
def book_session(
    client_id: int,
    scheduled_at: str,
    duration_mins: int = 60,
    location: Optional[str] = None,
    is_recurring: bool = False,
    recurrence_type: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Book a session for a client.
    scheduled_at: ISO datetime string, e.g. "2026-06-15T10:00:00".
    Runs a conflict check first. Returns error if slot is not FREE.
    """
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return {"error": f"Invalid datetime: {scheduled_at}. Use ISO 8601."}

    if scheduled_dt <= datetime.now():
        return {"error": f"Cannot book a session in the past: {scheduled_at}"}

    business_config = load_business_config()

    days_open = business_config.get("days_open")
    if days_open is not None and scheduled_dt.weekday() not in days_open:
        return {"error": f"Closed on {scheduled_dt.strftime('%A')}s."}

    max_per_day = business_config.get("max_sessions_per_client_per_day")
    if max_per_day is not None:
        with _db() as db:
            provider = ProviderStore(db).get_first()
            if not provider:
                return {"error": "No provider configured"}
            existing_today = SessionStore(db).get_sessions_for_date(provider.id, scheduled_dt.date())
        client_count = sum(1 for s in existing_today if s.client_id == client_id)
        if client_count >= max_per_day:
            return {
                "error": f"Client already has {client_count} session(s) booked on "
                         f"{scheduled_dt.date()}, max is {max_per_day} per day."
            }

    conflict_result = check_slot_conflict(
        requested_at=scheduled_at,
        duration_mins=duration_mins,
        requesting_client_id=client_id,
    )
    if "error" in conflict_result:
        return conflict_result
    if conflict_result.get("status") != "FREE":
        return {
            "error": "Slot is not available",
            "conflict": conflict_result,
        }

    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        try:
            session = SessionStore(db).create({
                "provider_id": provider.id,
                "client_id": client_id,
                "scheduled_at": scheduled_dt,
                "duration_mins": duration_mins,
                "location": location,
                "status": "scheduled",
                "is_recurring": is_recurring,
                "recurrence_type": recurrence_type,
                "notes": notes,
            }, buffer_mins=provider.buffer_mins)
        except ValueError as e:
            return {"error": str(e)}
        return _session_dict(session)


@scheduling_mcp.tool()
@mutating("session_id")
def cancel_session(session_id: int) -> dict:
    """
    Cancel a scheduled session by ID.
    Returns the session's status before cancellation.
    """
    with _db() as db:
        store = SessionStore(db)
        session = store.get(session_id)
        if not session:
            return {"error": f"No session with id={session_id}"}

        pre_cancel_status = session.status

        if pre_cancel_status == "cancelled":
            return {"error": f"Session {session_id} is already cancelled"}

        store.cancel(session_id)
        return {
            "ok": True,
            "session_id": session_id,
            "pre_cancel_status": pre_cancel_status,
        }


@scheduling_mcp.tool()
@mutating("session_id")
def reschedule_session(session_id: int, new_time: str) -> dict:
    """
    Reschedule a session to a new time.
    new_time: ISO datetime string, e.g. "2026-06-15T14:00:00".
    Runs a conflict check first. Returns error if slot is not FREE.
    """
    try:
        new_dt = datetime.fromisoformat(new_time)
    except ValueError:
        return {"error": f"Invalid datetime: {new_time}. Use ISO 8601."}

    if new_dt <= datetime.now():
        return {"error": f"Cannot reschedule to a past time: {new_time}"}

    with _db() as db:
        session = SessionStore(db).get(session_id)
        if not session:
            return {"error": f"No session with id={session_id}"}
        client_id = session.client_id
        duration_mins = session.duration_mins

    conflict_result = check_slot_conflict(
        requested_at=new_time,
        duration_mins=duration_mins,
        requesting_client_id=client_id,
    )
    if "error" in conflict_result:
        return conflict_result
    if conflict_result.get("status") != "FREE":
        return {
            "error": "New slot is not available",
            "conflict": conflict_result,
        }

    with _db() as db:
        store = SessionStore(db)
        store.reschedule(session_id, new_dt)
        updated = store.get(session_id)
        return _session_dict(updated)


@scheduling_mcp.tool()
def get_sessions_for_date(date: str) -> dict:
    """
    Get all scheduled sessions on a given date.
    date: ISO date string, e.g. "2026-06-15".
    """
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": f"Invalid date: {date}. Use YYYY-MM-DD."}
    with _db() as db:
        provider = ProviderStore(db).get_first()
        if not provider:
            return {"error": "No provider configured"}
        sessions = SessionStore(db).get_sessions_for_date(provider.id, target_date)
        return {"sessions": [_session_dict(s) for s in sessions]}


@scheduling_mcp.tool()
def get_upcoming_sessions(client_id: int) -> dict:
    """Get the next 5 upcoming scheduled sessions for a client."""
    with _db() as db:
        sessions = SessionStore(db).get_upcoming_for_client(client_id)
        return {"sessions": [_session_dict(s) for s in sessions]}
