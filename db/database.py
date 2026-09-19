from contextvars import ContextVar

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./donna.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Write guard: any flush that persists changes raises unless a donna_mcp tool
# handler opened the write window. Private to db/ and donna_mcp/.
_mcp_write_ok: ContextVar[bool] = ContextVar("_mcp_write_ok", default=False)


class MutationGuardError(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _reject_writes_outside_mcp(session, flush_context, instances):
    has_changes = session.new or session.deleted or any(session.is_modified(o) for o in session.dirty)
    if has_changes and not _mcp_write_ok.get():
        raise MutationGuardError("DB write attempted outside the MCP tool layer")
