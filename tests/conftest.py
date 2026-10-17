import pytest
from db.database import SessionLocal
from db.migrations import init_db
from db.redis_client import get_redis
from donna_mcp.guard import acting_as
from donna_mcp.tools.admin import bootstrap_provider_tool
from models.orm import Base
from db.database import engine


@pytest.fixture(scope="function", autouse=True)
def reset_state():
    """Wipe and recreate DB + flush Redis before every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        with acting_as("system"):
            bootstrap_provider_tool()
    finally:
        db.close()

    try:
        r = get_redis()
        r.flushdb()
    except Exception:
        pass

    yield


@pytest.fixture(scope="function", autouse=True)
def default_caller():
    """Tests invoke MCP tools directly as the admin unless they set another caller."""
    with acting_as("admin"):
        yield


@pytest.fixture(autouse=True)
def verifier_off(monkeypatch):
    """The claim verifier makes an LLM call; tests that want it turn it on explicitly."""
    from config import settings
    monkeypatch.setattr(settings, "claim_verifier", False)
