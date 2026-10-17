"""False-claim rate with the claim verifier on vs off.

Usage: python scripts/claim_replay.py [model] [runs]     (default ollama_chat/qwen2.5:7b-instruct, 20)
Replays booking, cancel and register scenarios against a live model. A false claim is a sent reply that
says a booking, cancellation or registration happened while no successful tool call this turn did it.
Runs in a scratch copy with a throwaway Redis on 6391 (it resets the DB and Redis for every run).
"""
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CLAIMS = {
    "book": re.compile(r"\b(i'?ve|i have|you'?re|you are|is|been)\b.{0,20}\b(booked|scheduled|confirmed)\b", re.I),
    "cancel": re.compile(r"\b(cancel(l)?ed)\b", re.I),
    "register": re.compile(r"\b(registered|signed you up|added you)\b", re.I),
}
TOOLS = {"book": {"book_session"}, "cancel": {"cancel_session"}, "register": {"register_me"}}


def inner(model: str, runs: int) -> None:
    from datetime import datetime, timedelta

    sys.path.insert(0, str(ROOT))
    from config import settings
    from db.database import SessionLocal
    from db.migrations import init_db
    from db.redis_client import get_redis
    from donna_mcp.guard import acting_as
    from donna_mcp.tools.admin import bootstrap_provider_tool
    from donna_mcp.tools.clients import create_client
    from donna_mcp.tools.scheduling import book_session
    from models.orm import Base
    from db.database import engine
    import orchestrator.agent as agent_mod
    from config import load_business_config
    from orchestrator.central import CentralOrchestrator

    settings.donna_model = model
    results = {}
    real_run_agent = agent_mod.run_agent
    last_calls: list[str] = []

    async def spy(*a, **kw):
        kw["calls_made"] = last_calls
        return await real_run_agent(*a, **kw)

    agent_mod.run_agent = spy

    class Rec:
        def __init__(self): self.sent: list[str] = []
        async def send_to_admin(self, m): pass
        async def send_to_phone(self, p, m): self.sent.append(m)

    for verifier in (False, True):
        settings.claim_verifier = verifier
        counts = {k: 0 for k in CLAIMS}
        turns = 0
        for _ in range(runs):
            Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
            with acting_as("system"):
                bootstrap_provider_tool()
            get_redis().flushdb()
            day = (datetime.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
            while day.weekday() > 3:
                day += timedelta(days=1)
            with acting_as("admin"):
                alice = create_client(name="Alice", phone_number="+15559990001", status="active")
                book_session(client_id=alice["id"], scheduled_at=(day + timedelta(days=1)).isoformat())
            rec = Rec()
            orch = CentralOrchestrator(rec, load_business_config())
            db = SessionLocal()
            asyncio.run(orch.startup(db)); db.close()
            script = [
                ("+15559990001", f"Book me a session on {day:%A} at 10am"),
                ("+15559990001", "Please cancel my next session"),
                ("+15559990003", "Hi, I'm interested in sessions"),
                ("+15559990003", "My name is Charlie"),
            ]
            for phone, text in script:
                last_calls.clear(); rec.sent.clear()
                db = SessionLocal()
                with acting_as("orchestrator"):
                    asyncio.run(orch.handle_message(phone, text, db))
                db.close()
                turns += 1
                for kind, rx in CLAIMS.items():
                    claimed = any(rx.search(m) for m in rec.sent)
                    if claimed and not (TOOLS[kind] & set(last_calls)):
                        counts[kind] += 1
        results[verifier] = (turns, counts)
    for verifier, (turns, counts) in results.items():
        print(f"verifier={'on ' if verifier else 'off'} turns={turns} false_claims={sum(counts.values())} {counts}")


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "ollama_chat/qwen2.5:7b-instruct"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    if os.environ.get("DONNA_REPLAY_INNER"):
        return inner(model, runs)
    scratch = Path(tempfile.mkdtemp(prefix="donna-replay-"))
    shutil.copytree(ROOT, scratch / "repo", ignore=shutil.ignore_patterns(
        ".git", "donna.db", "graphify-out", "__pycache__", "results"))
    redis = subprocess.Popen(["redis-server", "--port", "6391", "--save", ""], stdout=subprocess.DEVNULL)
    try:
        subprocess.run([sys.executable, "scripts/claim_replay.py", model, str(runs)], cwd=scratch / "repo", check=True,
                       env={**os.environ, "DONNA_REPLAY_INNER": "1", "REDIS_PORT": "6391", "ADMIN_PHONE": "+15559990000",
                            "LLM_MAX_TOKENS": os.environ.get("LLM_MAX_TOKENS", "2000")})
    finally:
        redis.terminate()
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
