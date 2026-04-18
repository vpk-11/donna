import logging
from fastapi import WebSocket
from rich.console import Console
from messaging.base import MessagingClient
from config import settings

logger = logging.getLogger(__name__)
console = Console()


class WebSocketConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, phone: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[phone] = websocket
        logger.info(f"Connected: {phone}")

    def disconnect(self, phone: str) -> None:
        self._connections.pop(phone, None)
        logger.info(f"Disconnected: {phone}")

    def is_connected(self, phone: str) -> bool:
        return phone in self._connections

    async def send(self, phone: str, message: str) -> None:
        ws = self._connections.get(phone)
        if ws:
            await ws.send_text(message)


class WebSocketMessagingClient(MessagingClient):
    def __init__(self, manager: WebSocketConnectionManager, db_factory):
        self._manager = manager
        self._db_factory = db_factory

    async def send_to_admin(self, message: str) -> None:
        await self.send_to_phone(settings.admin_phone, message)

    async def send_to_phone(self, phone: str, message: str) -> None:
        formatted = f"[DONNA] {message}"
        if self._manager.is_connected(phone):
            await self._manager.send(phone, formatted)
            console.print(f"[cyan][DONNA -> {phone}][/cyan] {message}")
        else:
            logger.warning(f"Phone {phone} not connected — queuing message")
            db = self._db_factory()
            try:
                from store.conversation_store import ConversationStore
                conv_store = ConversationStore(db)
                state = conv_store.get_by_phone(phone)
                if state:
                    ctx = dict(state.context or {})
                    pending = list(ctx.get("pending_messages", []))
                    pending.append(formatted)
                    ctx["pending_messages"] = pending
                    conv_store.update(phone, {"context": ctx})
            finally:
                db.close()

        db = self._db_factory()
        try:
            from store.conversation_store import ConversationStore
            conv_store = ConversationStore(db)
            conv_store.update_last_donna_message(phone, message)
        finally:
            db.close()

    async def deliver_pending(self, phone: str) -> None:
        db = self._db_factory()
        try:
            from store.conversation_store import ConversationStore
            conv_store = ConversationStore(db)
            state = conv_store.get_by_phone(phone)
            if not state:
                return
            ctx = dict(state.context or {})
            pending = ctx.pop("pending_messages", [])
            if pending:
                conv_store.update(phone, {"context": ctx})
                for msg in pending:
                    await self._manager.send(phone, msg)
                    console.print(f"[cyan][DONNA -> {phone} (queued)][/cyan] {msg}")
        finally:
            db.close()
