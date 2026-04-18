import logging
from contextlib import asynccontextmanager
from urllib.parse import unquote
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from db.database import SessionLocal
from db.migrations import init_db
from store.bootstrap import bootstrap_provider
from messaging.websocket_client import WebSocketConnectionManager, WebSocketMessagingClient
from core.router import route_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ws_manager = WebSocketConnectionManager()
messaging_client: WebSocketMessagingClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global messaging_client
    init_db()
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
