"""
Phase 2 smoke tests.
Requires: running Redis, seeded DB (provider + clients with id=4,5).
Run seed setup via: conda run -n donna python tests/test_phase2.py --setup
or just ensure the DB has a provider and at least two clients.
"""
import pytest
from db.migrations import init_db
from db.database import SessionLocal
from store.bootstrap import bootstrap_provider
from store.client_store import ClientStore
from store.provider_store import ProviderStore


CLIENT_1_PHONE = "+15559990001"
CLIENT_2_PHONE = "+15559990002"


@pytest.fixture(scope="function", autouse=True)
def ensure_seed():
    init_db()
    db = SessionLocal()
    try:
        bootstrap_provider(db)
        provider = ProviderStore(db).get_first()
        for phone, name in [(CLIENT_1_PHONE, "Test Client One"), (CLIENT_2_PHONE, "Test Client Two")]:
            if not ClientStore(db).get_by_phone(phone):
                ClientStore(db).create({
                    "provider_id": provider.id,
                    "name": name,
                    "phone_number": phone,
                    "status": "active",
                    "preferred_days": [],
                })
    finally:
        db.close()


def _client_id(phone: str) -> int:
    db = SessionLocal()
    try:
        return ClientStore(db).get_by_phone(phone).id
    finally:
        db.close()


def test_book_session_happy_path():
    from donna_mcp.tools.scheduling import book_session

    result = book_session(
        client_id=_client_id(CLIENT_1_PHONE),
        scheduled_at="2027-01-15T10:00:00",
        duration_mins=60,
    )
    assert "error" not in result, result
    assert result["status"] == "scheduled"
    assert result["client_id"] == _client_id(CLIENT_1_PHONE)


def test_book_session_conflict_returns_error():
    from donna_mcp.tools.scheduling import book_session

    c1 = _client_id(CLIENT_1_PHONE)
    c2 = _client_id(CLIENT_2_PHONE)

    first = book_session(client_id=c1, scheduled_at="2027-01-16T10:00:00", duration_mins=60)
    assert "error" not in first, first

    result = book_session(client_id=c2, scheduled_at="2027-01-16T10:00:00", duration_mins=60)
    assert "error" in result
    assert "conflict" in result
    assert result["conflict"]["status"] != "FREE"


def test_cancel_session_preserves_pre_cancel_status():
    from donna_mcp.tools.scheduling import book_session, cancel_session

    booked = book_session(
        client_id=_client_id(CLIENT_1_PHONE),
        scheduled_at="2027-01-17T10:00:00",
        duration_mins=60,
    )
    assert "error" not in booked, booked

    result = cancel_session(session_id=booked["id"])
    assert result["ok"] is True
    assert result["pre_cancel_status"] == "scheduled"


def test_reschedule_session_checks_conflict():
    from donna_mcp.tools.scheduling import book_session, reschedule_session

    c1 = _client_id(CLIENT_1_PHONE)
    c2 = _client_id(CLIENT_2_PHONE)

    s1 = book_session(client_id=c1, scheduled_at="2027-01-18T10:00:00", duration_mins=60)
    s2 = book_session(client_id=c2, scheduled_at="2027-01-18T12:00:00", duration_mins=60)
    assert "error" not in s1, s1
    assert "error" not in s2, s2

    result = reschedule_session(session_id=s2["id"], new_time="2027-01-18T10:00:00")
    assert "error" in result
    assert "conflict" in result


def test_get_all_active_agents():
    from donna_mcp.tools.admin import get_all_active_agents

    result = get_all_active_agents()
    assert "error" not in result, result
    assert "agents" in result
    assert "count" in result
    assert isinstance(result["count"], int)
