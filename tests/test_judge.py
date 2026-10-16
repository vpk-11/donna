import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings
from db.database import SessionLocal
from donna_mcp.tools.clients import create_client
from intelligence import claim_judge
from intelligence.claim_judge import FALLBACK, verify_reply
from orchestrator.agent import ClientAgent
from store.client_store import ClientStore
from store.provider_store import ProviderStore

PHONE = "+15559990001"
SUCCESS = [{"tool": "book_session", "ok": True, "result": {"id": 1}}]
FAILED = [{"tool": "book_session", "ok": False, "result": {"booked": False, "reason": "slot not free"}}]


def _verdict(text):
    return patch.object(claim_judge, "call_llm", AsyncMock(return_value=text))


def run(coro):
    return asyncio.run(coro)


def test_pass_verdict_accepted():
    with _verdict('{"verdict": "pass", "unsupported_claims": []}'):
        assert run(verify_reply("You're booked for Monday 10:00.", SUCCESS))


def test_fail_verdict_rejected():
    with _verdict('{"verdict": "fail", "unsupported_claims": ["booked"]}'):
        assert not run(verify_reply("You're booked for Monday 10:00.", FAILED))


@pytest.mark.parametrize("raw", ["not json", "{}", '{"verdict": "maybe"}', ""])
def test_malformed_output_fails_closed(raw):
    with _verdict(raw):
        assert not run(verify_reply("You're booked.", SUCCESS))


def test_llm_error_fails_closed():
    with patch.object(claim_judge, "call_llm", AsyncMock(side_effect=RuntimeError("down"))):
        assert not run(verify_reply("You're booked.", SUCCESS))


def test_timeout_fails_closed(monkeypatch):
    async def hang(*a, **kw):
        await asyncio.sleep(5)

    monkeypatch.setattr(settings, "judge_timeout_s", 0.05)
    with patch.object(claim_judge, "call_llm", hang):
        assert not run(verify_reply("You're booked.", SUCCESS))


def _agent_turn(reply, trace, verdict):
    """One ClientAgent turn with a canned model reply; returns what was sent to the client."""
    client = create_client(name="Alice", phone_number=PHONE)
    db = SessionLocal()
    try:
        provider = ProviderStore(db).get_first()
        c = ClientStore(db).get(client["id"])
        messaging = MagicMock()
        messaging.send_to_admin = AsyncMock()
        messaging.send_to_phone = AsyncMock()
        agent = ClientAgent(PHONE, c, provider, messaging, {})

        async def fake_run_agent(*a, trace=None, **kw):
            trace.extend(t for t in trace_in)
            return reply

        trace_in = trace
        with patch("orchestrator.agent.run_agent", fake_run_agent), _verdict(json.dumps({"verdict": verdict})):
            run(agent.handle_message("hi", db))
        return [c.args[1] for c in messaging.send_to_phone.await_args_list]
    finally:
        db.close()


def test_failed_claim_is_replaced_by_fallback(monkeypatch):
    monkeypatch.setattr(settings, "claim_verifier", True)
    assert _agent_turn("You're all set for Monday at 10!", FAILED, "fail") == [FALLBACK]


def test_supported_claim_is_sent(monkeypatch):
    monkeypatch.setattr(settings, "claim_verifier", True)
    assert _agent_turn("Monday works, want me to go ahead?", [], "pass") == ["Monday works, want me to go ahead?"]


def test_verifier_error_in_turn_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "claim_verifier", True)
    assert _agent_turn("See you Monday!", SUCCESS, "garbage") == [FALLBACK]


def test_vague_claim_without_tool_calls_is_still_verified(monkeypatch):
    monkeypatch.setattr(settings, "claim_verifier", True)
    assert _agent_turn("You're all set!", [], "fail") == [FALLBACK]


def test_blocked_reply_stays_in_history(monkeypatch):
    from store.conversation_store import ConversationStore
    monkeypatch.setattr(settings, "claim_verifier", True)
    captured = {}
    real = ClientAgent._send_blocked

    async def spy(self, text, user_text, conv_store):
        await real(self, text, user_text, conv_store)
        captured["history"] = self.scoped_history()

    monkeypatch.setattr(ClientAgent, "_send_blocked", spy)
    _agent_turn("Done, sorted!", [], "fail")
    assert [t["content"] for t in captured["history"]] == ["hi", FALLBACK]
