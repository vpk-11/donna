import pytest
from db.database import SessionLocal
from db.migrations import init_db
from db.redis_client import get_redis
from store.bootstrap import bootstrap_provider
from models.orm import Base
from db.database import engine


@pytest.fixture(scope="function", autouse=True)
def reset_state():
    """Wipe and recreate DB + flush Redis before every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        bootstrap_provider(db)
    finally:
        db.close()

    try:
        r = get_redis()
        r.flushdb()
    except Exception:
        pass

    yield
