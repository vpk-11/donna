import json
import pytest


def test_redis_round_trip():
    from db.redis_client import get_redis
    from orchestrator.channels import CHAN_CLIENT_MSG, make_envelope

    r = get_redis()
    pubsub = r.pubsub()
    channel = CHAN_CLIENT_MSG.format(phone="+15550001111")
    pubsub.subscribe(channel)

    envelope = make_envelope(
        event="client_message",
        phone="+15550001111",
        payload={"text": "hello"},
        source="client",
    )
    r.publish(channel, json.dumps(envelope))

    # consume the subscribe confirmation message first
    pubsub.get_message(timeout=0.5)
    message = pubsub.get_message(timeout=1.0)
    assert message is not None
    data = json.loads(message["data"])
    assert data["event"] == "client_message"
    assert data["phone"] == "+15550001111"
    pubsub.unsubscribe(channel)


def test_db_migration():
    from db.migrations import init_db
    from db.database import SessionLocal
    from models.orm import ConversationSummary

    init_db()
    session = SessionLocal()
    try:
        session.query(ConversationSummary).first()
    finally:
        session.close()


def test_parse_date_raises_on_garbage():
    from utils.time_utils import parse_date

    with pytest.raises(ValueError):
        parse_date("not a date at all")


def test_llm_client_import_chain():
    from intelligence.intent_parser import parse_intent  # noqa
    from intelligence.response_generator import generate  # noqa
    from intelligence.llm_client import call_llm  # noqa
