import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.database import MutationGuardError, SessionLocal
from donna_mcp.guard import CallerNotAllowed, acting_as
from donna_mcp.tools.clients import create_client, update_client
from donna_mcp.tools.scheduling import book_session, reschedule_session
from firewall import input_guard
from orchestrator.agent import ClientAgent
from orchestrator.central import CentralOrchestrator
from store.client_store import ClientStore
from store.provider_store import ProviderStore

PHONE_A = "+15559990001"
PHONE_B = "+15559990002"
ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def clients():
    a = create_client(name="Alice", phone_number=PHONE_A)
    b = create_client(name="Bob", phone_number=PHONE_B)
    return a, b


def _messaging():
    m = MagicMock()
    m.send_to_admin = AsyncMock()
    m.send_to_phone = AsyncMock()
    return m


def _agent(phone, client_dict, messaging=None):
    db = SessionLocal()
    try:
        provider = ProviderStore(db).get_first()
        client = ClientStore(db).get(client_dict["id"])
        db.expunge_all()
    finally:
        db.close()
    return ClientAgent(phone, client, provider, messaging or _messaging(), {})


# --- 1/2: firewall fail modes ---

def _boom(*a, **kw):
    raise RuntimeError("scanner down")


def test_prompt_injection_scanner_error_fails_closed(monkeypatch):
    monkeypatch.setattr(input_guard._injection_scanner, "scan", _boom)
    r = input_guard.scan_input("Can I move my session to Friday?", PHONE_A, is_admin=False)
    assert r.action == "block" and r.threat == "ScannerFailClosed"
    assert r.log_entry["scanner"] == "prompt_injection"


def test_identity_spoof_scanner_error_fails_closed(monkeypatch):
    bad = MagicMock()
    bad.search.side_effect = RuntimeError("regex down")
    monkeypatch.setattr(input_guard, "_identity_spoof_patterns", [bad])
    r = input_guard.scan_input("Can I move my session to Friday?", PHONE_A, is_admin=False)
    assert r.action == "block" and r.threat == "ScannerFailClosed"
    assert r.log_entry["scanner"] == "identity_spoof"


@pytest.mark.parametrize("name", ["_topic_scanner", "_token_scanner"])
def test_low_stakes_scanner_error_fails_open(monkeypatch, name):
    monkeypatch.setattr(getattr(input_guard, name), "scan", _boom)
    r = input_guard.scan_input("Can I move my session to Friday?", PHONE_A, is_admin=False)
    assert r.action == "pass"


# --- 3: context isolation ---

def test_other_clients_context_never_reaches_llm(clients):
    a, b = clients
    agent_a = _agent(PHONE_A, a)
    agent_b = _agent(PHONE_B, b)
    agent_b._history = agent_b._own([{"role": "user", "content": "BOB-SECRET-MARKER"}])
    # simulate a shared/leaked history list
    agent_a._history = agent_a._own([{"role": "user", "content": "hello"}]) + agent_b._history

    prompts = []

    async def fake_llm(messages, tools, **kw):
        prompts.append(" ".join(str(m.get("content")) for m in messages))
        return {"content": "ok", "tool_calls": None}

    db = SessionLocal()
    try:
        with patch("orchestrator.llm_agent.call_llm_tools", fake_llm):
            asyncio.run(agent_a.handle_message("What services do you offer?", db))
    finally:
        db.close()
    assert prompts and all("BOB-SECRET-MARKER" not in p for p in prompts)
    assert any("hello" in p for p in prompts)


# --- 4: mutation gating ---

def test_write_outside_mcp_raises(clients):
    db = SessionLocal()
    try:
        with pytest.raises(MutationGuardError):
            ClientStore(db).update(clients[0]["id"], {"notes": "x"})
    finally:
        db.close()


def test_no_write_code_outside_allowed_dirs():
    allowed = {"donna_mcp", "store", "db", "tests", "core", "scripts", "graphify-out"}
    pattern = re.compile(r"\.(add|commit|flush|merge)\(|\.execute\(")
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in allowed or rel.parts[0].startswith("."):
            continue
        if pattern.search(path.read_text()):
            offenders.append(str(rel))
    assert offenders == [], offenders


def test_write_window_flag_private():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in ("db", "donna_mcp", "tests") or rel.parts[0].startswith("."):
            continue
        assert "_mcp_write_ok" not in path.read_text(), rel


# --- 5/6/7: routing, orchestrator, scoping ---

def test_orchestrator_cannot_mutate(clients):
    with acting_as("orchestrator"):
        with pytest.raises(CallerNotAllowed):
            update_client(client_id=clients[0]["id"], notes="x")
        with pytest.raises(CallerNotAllowed):
            book_session(client_id=clients[0]["id"], scheduled_at="2027-02-01T10:00:00")


def test_agent_scoping(clients):
    a, b = clients
    with acting_as("agent", PHONE_A):
        assert "error" not in update_client(client_id=a["id"], notes="mine")
        with pytest.raises(CallerNotAllowed):
            update_client(client_id=b["id"], notes="not mine")
    booked = book_session(client_id=b["id"], scheduled_at="2027-02-02T10:00:00")
    with acting_as("agent", PHONE_A):
        with pytest.raises(CallerNotAllowed):
            reschedule_session(session_id=booked["id"], new_time="2027-02-02T14:00:00")


def test_swap_routes_through_owning_agent(clients, caplog):
    import json
    from datetime import datetime
    a, b = clients
    when = datetime(2027, 2, 3, 10, 0)
    booked = book_session(client_id=b["id"], scheduled_at=when.isoformat())
    messaging = _messaging()

    def call(name, **args):
        return {"content": "", "tool_calls": [{"id": name, "function": {"name": name, "arguments": json.dumps(args)}}]}

    async def fake_llm(messages, tools, **kw):
        if "orchestrator of a multi-agent" in messages[0]["content"]:
            done = [m["role"] for m in messages].count("tool")
            if done == 0:
                return call("find_slot_holder", when_iso=when.isoformat())
            if done == 1:
                return call("relay_to_client_agent", client_id=b["id"], request_text="Move to 14:00.")
            return {"content": "Asked the holder to move.", "tool_calls": None}
        return {"content": "Something came up on our end, can you shift to 2pm?", "tool_calls": None}

    db = SessionLocal()
    try:
        provider = ProviderStore(db).get_first()
        orch = CentralOrchestrator(messaging, {})
        orch._provider = provider
        with patch("orchestrator.llm_agent.call_llm_tools", fake_llm), caplog.at_level("INFO"):
            with acting_as("agent", PHONE_A):
                result = asyncio.run(orch.route_request(PHONE_A, "Client Alice needs the slot freed.", db))
    finally:
        db.close()
    assert result == "Asked the holder to move."
    messaging.send_to_phone.assert_awaited_with(PHONE_B, "Something came up on our end, can you shift to 2pm?")
    text = caplog.text
    assert text.index("agent(+15559990001) -> orchestrator") < text.index("orchestrator -> agent(+15559990002)")
    assert "agent(+15559990001) -> agent" not in text and "agent(+15559990002) -> agent" not in text
    # the orchestrator never mutated: the session is untouched until B's own agent acts
    assert booked["scheduled_at"].startswith("2027-02-03T10:00")


def test_cold_agent_may_create_only_its_own_client():
    with acting_as("agent", PHONE_A):
        assert "error" not in create_client(name="Newbie", phone_number=PHONE_A, status="cold_lead")
        with pytest.raises(CallerNotAllowed):
            create_client(name="Other", phone_number=PHONE_B)
