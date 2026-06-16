import json
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import unquote
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from db.database import SessionLocal
from db.migrations import init_db
from db.redis_client import ping_redis
from firewall.warmup import warmup_firewall
from store.bootstrap import bootstrap_provider
from messaging.websocket_client import WebSocketConnectionManager, WebSocketMessagingClient
from core.router import route_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ws_manager = WebSocketConnectionManager()
messaging_client: WebSocketMessagingClient | None = None
business_config: dict = {}

_BUSINESS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "business.json")


def get_business_config() -> dict:
    return business_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global messaging_client, business_config
    init_db()

    if not ping_redis():
        raise RuntimeError("Redis is not reachable. Start Redis before Donna.")

    with open(_BUSINESS_CONFIG_PATH) as f:
        business_config = json.load(f)
    logger.info(f"Loaded business config: {business_config.get('business_type')}")

    warmup_firewall()

    db = SessionLocal()
    try:
        bootstrap_provider(db)
    finally:
        db.close()
    messaging_client = WebSocketMessagingClient(ws_manager, SessionLocal)
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
    await messaging_client.deliver_pending(phone)
    try:
        while True:
            text = await websocket.receive_text()
            logger.info(f"Message from {phone}: {text[:80]}")
            db = SessionLocal()
            try:
                await route_message(phone, text, messaging_client, db)
            finally:
                db.close()
    except WebSocketDisconnect:
        ws_manager.disconnect(phone)
