import asyncio
import pytest
from models.schemas import IntentResult
from intelligence.judge import evaluate
from intelligence.context_manager import (
    summarize_conversation,
    should_summarize,
    trim_history,
    HISTORY_TAIL_AFTER_SUMMARY,
)


def test_low_confidence_escalates():
    result = asyncio.run(evaluate(
        intent_result=IntentResult(intent="BOOK_REQUEST", entities={}, confidence=0.4),
        role="client",
        turn_count=1,
        context={},
        client_status="active",
        is_new_client=False,
    ))
    assert result.decision == "escalate_to_admin"
    assert "confidence" in result.reason.lower() or "threshold" in result.reason.lower()


def test_human_request_always_escalates():
    result = asyncio.run(evaluate(
        intent_result=IntentResult(intent="HUMAN_REQUEST", entities={}, confidence=0.95),
        role="client",
        turn_count=2,
        context={},
    ))
    assert result.decision == "escalate_to_admin"


def test_new_client_booking_escalates():
    result = asyncio.run(evaluate(
        intent_result=IntentResult(intent="BOOK_REQUEST", entities={}, confidence=0.9),
        role="client",
        turn_count=1,
        context={},
        client_status="prospect",
        is_new_client=True,
    ))
    assert result.decision == "escalate_to_admin"
    assert "new client" in result.reason.lower()


def test_cancel_request_notifies_admin():
    result = asyncio.run(evaluate(
        intent_result=IntentResult(intent="CANCEL_REQUEST", entities={}, confidence=0.9),
        role="client",
        turn_count=1,
        context={},
        client_status="active",
    ))
    assert result.decision == "notify_admin"


def test_context_manager_summarizes():
    from unittest.mock import AsyncMock, patch

    history = [
        {"role": "user", "content": "Can I book Tuesday at 10am?"},
        {"role": "donna", "content": "Tuesday at 10am works! Just to confirm — shall I put that in?"},
        {"role": "user", "content": "Yes please"},
        {"role": "donna", "content": "Done! Your session is booked for Tuesday at 10am."},
    ]
    assert not should_summarize(history)

    fake_summary = "Sarah asked to book Tuesday at 10am. Donna confirmed and booked the session. No open items."
    with patch("intelligence.context_manager.call_llm", new=AsyncMock(return_value=fake_summary)):
        summary = asyncio.run(summarize_conversation(history, "Sarah", "Coach K"))
    assert isinstance(summary, str)
    assert len(summary) > 20


def test_history_trimming():
    history = [{"role": "user", "content": f"message {i}"} for i in range(25)]
    trimmed = trim_history(history, "Client booked Tuesday at 10am.")

    assert len(trimmed) == 1 + HISTORY_TAIL_AFTER_SUMMARY
    assert trimmed[0]["role"] == "system"
    assert "summary" in trimmed[0]["content"].lower()
    assert trimmed[-1]["content"] == "message 24"
