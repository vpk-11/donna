"""Caller identity and write gating for mutating MCP tools.

Every mutating tool is wrapped with @mutating(scope). The wrapper opens the DB
write window (see db/database.py) and rejects callers that do not own the
target. Callers are set by the code invoking the tools via acting_as().

Scopes:
  client_id / session_id  admin any; agent only its own client
  create_client           admin any; agent only its own phone
  conv                    system/orchestrator/admin any; agent own phone or provider phone
  admin                   admin only
  system                  system only (startup seeding)
"""
import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar

from config import settings
from db.database import SessionLocal, _mcp_write_ok
from models.orm import Client, Session as SessionModel

_caller: ContextVar[tuple[str, str | None] | None] = ContextVar("_caller", default=None)


class CallerNotAllowed(PermissionError):
    pass


@contextmanager
def acting_as(kind: str, phone: str | None = None):
    """kind: system | orchestrator | admin | agent (agent requires the client's phone)."""
    token = _caller.set((kind, phone))
    try:
        yield
    finally:
        _caller.reset(token)


def _client_phone(client_id: int) -> str | None:
    db = SessionLocal()
    try:
        client = db.get(Client, client_id)
        return client.phone_number if client else None
    finally:
        db.close()


def _session_owner_phone(session_id: int) -> str | None:
    db = SessionLocal()
    try:
        session = db.get(SessionModel, session_id)
        return _client_phone(session.client_id) if session else None
    finally:
        db.close()


def _check(scope: str, kind: str, phone: str | None, args: dict) -> bool:
    if scope == "system":
        return kind == "system"
    if kind == "admin":
        return scope != "system"
    if scope == "admin":
        return False
    if scope == "conv":
        if kind in ("system", "orchestrator"):
            return True
        return kind == "agent" and args["phone_number"] in (phone, settings.admin_phone)
    if kind != "agent":
        return False
    if scope == "client_id":
        return _client_phone(args["client_id"]) == phone
    if scope == "session_id":
        return _session_owner_phone(args["session_id"]) == phone
    if scope == "create_client":
        return args["phone_number"] == phone
    raise ValueError(f"unknown scope {scope}")


def mutating(scope: str):
    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            caller = _caller.get()
            if caller is None:
                raise CallerNotAllowed(f"{fn.__name__}: no caller identity set")
            bound = sig.bind(*a, **kw)
            bound.apply_defaults()
            kind, phone = caller
            if not _check(scope, kind, phone, bound.arguments):
                raise CallerNotAllowed(f"{fn.__name__}: {kind}({phone}) may not mutate this target")
            token = _mcp_write_ok.set(True)
            try:
                return fn(*a, **kw)
            finally:
                _mcp_write_ok.reset(token)

        return wrapper

    return deco
