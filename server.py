import logging
from contextlib import asynccontextmanager
from urllib.parse import unquote

# Load .env (if present) into the real process environment before config.py's
# Settings() reads it. Keeps config.py itself reading shell-env-only
# (.claude/CLAUDE.md's rule); .env is just one more way that environment gets
# populated for local dev. Also called by main.py, but this module can be
# run standalone (`uvicorn server:app`), so it loads its own.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from config import load_business_config
from db.database import SessionLocal
from db.migrations import init_db
from db.redis_client import ping_redis
from firewall.warmup import warmup_firewall
from firewall.output_guard import register_client_names
from store.bootstrap import bootstrap_provider
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from messaging.websocket_client import WebSocketConnectionManager, WebSocketMessagingClient
from orchestrator.central import CentralOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ws_manager = WebSocketConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    if not ping_redis():
        raise RuntimeError("Redis is not reachable. Start Redis before Donna.")

    business_config = load_business_config()
    logger.info(f"Loaded business config: {business_config.get('business_type')}")
    if business_config.get("max_concurrent_sessions", 1) != 1:
        logger.warning(
            "max_concurrent_sessions=%s in config/business.json, but the conflict-detection "
            "logic (scheduling/conflict_resolver.py) hard-assumes a single concurrent session "
            "per provider. Values other than 1 are not actually enforced.",
            business_config.get("max_concurrent_sessions"),
        )

    warmup_firewall()

    db = SessionLocal()
    try:
        bootstrap_provider(db, business_config)
        provider = ProviderStore(db).get_first()
        if provider:
            register_client_names([c.name for c in ClientStore(db).list_by_provider(provider.id)])
    finally:
        db.close()
    app.state.messaging_client = WebSocketMessagingClient(ws_manager, SessionLocal)
    app.state.orchestrator = CentralOrchestrator(app.state.messaging_client, business_config)
    db = SessionLocal()
    try:
        await app.state.orchestrator.startup(db)
    finally:
        db.close()
    logger.info("Donna is ready.")
    yield
    logger.info("Donna shutting down.")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{phone_number}")
async def websocket_endpoint(websocket: WebSocket, phone_number: str):
    phone = unquote(phone_number)
    await ws_manager.connect(phone, websocket)
    await websocket.app.state.messaging_client.deliver_pending(phone)
    try:
        while True:
            text = await websocket.receive_text()
            logger.info(f"Message from {phone}: {text[:80]}")
            db = SessionLocal()
            try:
                await websocket.app.state.orchestrator.handle_message(phone, text, db)
            finally:
                db.close()
    except WebSocketDisconnect:
        ws_manager.disconnect(phone)
