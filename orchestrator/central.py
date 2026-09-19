import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.orm import Provider
from db.redis_client import get_redis
from orchestrator.channels import STATE_AGENT_REGISTRY, STATE_SESSION
from orchestrator.admin_agent import AdminAgent
from orchestrator.agent import ClientAgent
from orchestrator.llm_agent import run_agent
from donna_mcp.guard import acting_as
from intelligence.prompts import ORCHESTRATOR_SYSTEM
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from store.session_store import SessionStore

logger = logging.getLogger(__name__)


class CentralOrchestrator:
    """Routes inbound messages to the admin agent or a per-client agent, and relays
    agent-to-agent requests. It never mutates data itself."""

    def __init__(self, messaging_client, business_config: dict):
        self._agents: dict[str, ClientAgent] = {}
        self._provider: Provider | None = None
        self._admin_agent: AdminAgent | None = None
        self._messaging_client = messaging_client
        self._business_config = business_config
        self._open_requests: dict[str, str] = {}  # target agent phone -> requester phone

    async def startup(self, db: Session) -> None:
        self._provider = ProviderStore(db).get_first()
        if not self._provider:
            raise RuntimeError("No provider configured. Run seed.sh first.")
        self._admin_agent = AdminAgent(self._provider, self._messaging_client, self, self._business_config)
        logger.info(f"Orchestrator started for provider: {self._provider.name}")

    async def handle_message(self, phone: str, text: str, db: Session) -> None:
        try:
            with acting_as("orchestrator"):
                await self._handle_message_inner(phone, text, db)
        except Exception as e:
            logger.exception(f"orchestrator.handle_message unhandled error for {phone}: {e}")

    async def _handle_message_inner(self, phone: str, text: str, db: Session) -> None:
        if not self._provider or not self._admin_agent:
            logger.error("Orchestrator not initialized - missing provider")
            return

        conv_store = ConversationStore(db)
        state = conv_store.get_by_phone(phone)
        if state:
            conv_store.append_history(phone, "user", text)

        if phone == self._provider.phone_number:
            await self._admin_agent.handle_message(text, db)
        else:
            if not state:
                conv_store.get_or_create(phone, "client")
                conv_store.append_history(phone, "user", text)
            agent = await self._get_or_spawn_agent(phone, db)
            await agent.handle_message(text, db)

    async def _get_or_spawn_agent(self, phone: str, db: Session) -> ClientAgent:
        if phone in self._agents:
            return self._agents[phone]

        agent = ClientAgent(
            phone=phone,
            client=ClientStore(db).get_by_phone(phone),
            provider=self._provider,
            messaging_client=self._messaging_client,
            business_config=self._business_config,
            orchestrator=self,
        )

        try:
            r = get_redis()
            summary_raw = r.get(STATE_SESSION.format(phone=phone))
            if summary_raw:
                agent.load_summary(summary_raw.decode() if isinstance(summary_raw, bytes) else summary_raw)
        except Exception as e:
            logger.warning(f"Could not load summary for {phone}: {e}")

        try:
            now = datetime.now(timezone.utc).isoformat()
            get_redis().hset(STATE_AGENT_REGISTRY, phone, json.dumps({
                "started_at": now, "last_active": now, "handoff_active": False,
            }))
        except Exception as e:
            logger.warning(f"Could not register agent for {phone}: {e}")

        self._agents[phone] = agent
        logger.info(f"agent.spawned: {phone}")
        return agent

    def retire_agent(self, phone: str) -> None:
        self._agents.pop(phone, None)

    # -------------------------------------------------------------------------
    # Agent-to-agent: requests come here, this agent decides whom to relay to
    # -------------------------------------------------------------------------

    async def request_slot_freed(self, requester_phone: str, client, slot, db: Session) -> str:
        return await self.route_request(
            requester_phone,
            f"Client {client.name} (id {client.id}) needs the {slot.isoformat()} slot freed. "
            f"Find who holds it and ask that client's agent to move.",
            db,
        )

    async def route_request(self, requester_phone: str, request: str, db: Session) -> str:
        """LLM orchestrator step. Finds the slot holder and relays to that client's own agent."""
        session_store = SessionStore(db)
        client_store = ClientStore(db)

        def find_slot_holder(when_iso: str):
            when = datetime.fromisoformat(when_iso)
            conflict = session_store.get_conflict(
                self._provider.id, when, self._business_config.get("session_duration_mins", 60),
                self._provider.buffer_mins,
            )
            if not conflict:
                return {"holder": None}
            alts = session_store.get_free_slots(
                self._provider.id, when.date(), conflict.duration_mins, self._provider,
                exclude_client_id=conflict.client_id,
            )
            return {
                "holder_client_id": conflict.client_id,
                "alternative_slots": [s.isoformat() for s in alts[:3]],
            }

        async def relay(client_id: int, request_text: str):
            target = client_store.get(client_id)
            if not target:
                return {"error": "unknown client"}
            self._open_requests[target.phone_number] = requester_phone
            logger.info(f"relay: orchestrator -> agent({target.phone_number})")
            agent = await self._get_or_spawn_agent(target.phone_number, db)
            outcome = await agent.handle_orchestrator_request(request_text, db)
            logger.info(f"relay: agent({target.phone_number}) -> orchestrator: {outcome}")
            return {"outcome": outcome}

        logger.info(f"relay: agent({requester_phone}) -> orchestrator: {request}")
        with acting_as("orchestrator"):
            return await run_agent(
                system=ORCHESTRATOR_SYSTEM,
                history=[],
                user_text=request,
                tools={
                    "find_slot_holder": (
                        "Who holds the session at this ISO datetime, and their alternative slots.",
                        {"type": "object", "properties": {"when_iso": {"type": "string"}}, "required": ["when_iso"]},
                        find_slot_holder,
                    ),
                    "relay_to_client_agent": (
                        "Send a request to a client's own agent. Never include the requester's name.",
                        {"type": "object", "properties": {
                            "client_id": {"type": "integer"}, "request_text": {"type": "string"}},
                         "required": ["client_id", "request_text"]},
                        relay,
                    ),
                },
            ) or "no outcome"

    async def report_outcome(self, from_phone: str, outcome: str, db: Session) -> str:
        """A client agent finished a relayed request. Forward to the requester's agent, or the admin."""
        requester = self._open_requests.pop(from_phone, None)
        logger.info(f"relay: agent({from_phone}) -> orchestrator: outcome '{outcome}'")
        if requester is None:
            return "no open request"
        if requester == self._provider.phone_number:
            await self._messaging_client.send_to_admin(f"Update on the slot swap: {outcome}")
        else:
            logger.info(f"relay: orchestrator -> agent({requester})")
            agent = await self._get_or_spawn_agent(requester, db)
            await agent.handle_orchestrator_update(outcome, db)
        return "forwarded"
