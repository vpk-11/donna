import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from config import settings
from models.orm import Provider
from db.redis_client import get_redis
from orchestrator.channels import STATE_AGENT_REGISTRY, STATE_OPEN_REQUESTS, STATE_SESSION, STATE_TIMEOUT
from orchestrator.admin_agent import AdminAgent
from firewall.input_guard import scan_input
from firewall.output_guard import scan_output
from orchestrator.agent import ClientAgent
from orchestrator.llm_agent import run_agent
from donna_mcp.guard import acting_as, runs_as
from intelligence.prompts import ORCHESTRATOR_SYSTEM
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from store.session_store import SessionStore

logger = logging.getLogger(__name__)

RESTORE_TURNS = 6  # recent stored turns given to a newly spawned agent


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
        self._open_request_at: dict[str, float] = {}  # target agent phone -> epoch seconds it was opened

    async def startup(self, db: Session) -> None:
        self._provider = ProviderStore(db).get_first()
        if not self._provider:
            raise RuntimeError("No provider configured. Run seed.sh first.")
        self._admin_agent = AdminAgent(self._provider, self._messaging_client, self, self._business_config)
        logger.info(f"Orchestrator started for provider: {self._provider.name}")
        await self._restore(db)

    async def _restore(self, db: Session) -> None:
        """Rebuild agents and open requests from Redis after a restart. Conversation state is in SQLite."""
        try:
            r = get_redis()
            registry = r.hgetall(STATE_AGENT_REGISTRY)
            stored = r.hgetall(STATE_OPEN_REQUESTS)
        except Exception as e:
            logger.warning(f"Could not restore agents: {e}")
            return
        restored = 0
        for phone, entry in registry.items():
            if not r.exists(STATE_TIMEOUT.format(phone=phone)):  # inactive past the timeout: drop, respawns on next message
                r.hdel(STATE_AGENT_REGISTRY, phone)
                continue
            await self._get_or_spawn_agent(phone, db)
            r.hset(STATE_AGENT_REGISTRY, phone, entry)  # keep the original started_at/handoff flags
            restored += 1
        self._open_requests, self._open_request_at = {}, {}
        for target, value in stored.items():
            requester, _, opened = value.partition("|")
            try:
                opened_at = float(opened)
            except ValueError:  # no timestamp, or garbage: treat as expired
                opened_at = 0.0
            if target in self._agents and time.time() - opened_at < settings.open_request_ttl_s:
                self._open_requests[target], self._open_request_at[target] = requester, opened_at
            else:  # target not restored, or the request expired
                r.hdel(STATE_OPEN_REQUESTS, target)
        logger.info(f"Restored {restored} agents, {len(self._open_requests)} open requests")

    @runs_as("orchestrator")
    async def handle_message(self, phone: str, text: str, db: Session) -> None:
        try:
            await self._handle_message_inner(phone, text, db)
        except Exception as e:
            logger.exception(f"orchestrator.handle_message unhandled error for {phone}: {e}")

    async def _handle_message_inner(self, phone: str, text: str, db: Session) -> None:
        if not self._provider or not self._admin_agent:
            logger.error("Orchestrator not initialized - missing provider")
            return

        conv_store = ConversationStore(db)
        if phone == self._provider.phone_number:
            if conv_store.get_by_phone(phone):
                conv_store.append_history(phone, "user", text)
            await self._admin_agent.handle_message(text, db)
        else:
            if not conv_store.get_by_phone(phone):
                conv_store.get_or_create(phone, "client")
            agent = await self._get_or_spawn_agent(phone, db)  # before storing: a new agent seeds from history
            conv_store.append_history(phone, "user", text)
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

        await self._seed_recent_turns(agent, db)
        self._agents[phone] = agent
        logger.info(f"agent.spawned: {phone}")
        return agent

    async def _seed_recent_turns(self, agent: ClientAgent, db: Session) -> None:
        """Add the last few stored turns to a new agent, after its summary. Used for every spawn, so a restart
        and a later lazy respawn behave the same. Stored user text is raw (written before the agent's input
        scan), so it is re-scanned and anything that would have been blocked is dropped. A few turns may
        overlap the summary; RESTORE_TURNS keeps that small."""
        turns = ConversationStore(db).get_history(agent.phone)[-RESTORE_TURNS:]
        kept = [t for t in turns
                if t["role"] != "user"
                or (await asyncio.to_thread(scan_input, t["content"], agent.phone, False)).action == "pass"]
        agent._history += agent._own(kept)

    def retire_agent(self, phone: str) -> None:
        self._agents.pop(phone, None)
        self._open_requests.pop(phone, None)  # a finished conversation must not route a later report
        self._open_request_at.pop(phone, None)
        try:
            get_redis().hdel(STATE_OPEN_REQUESTS, phone)
        except Exception as e:
            logger.warning(f"Could not clear open request: {e}")

    # -------------------------------------------------------------------------
    # Agent-to-agent: requests come here, this agent decides whom to relay to
    # -------------------------------------------------------------------------

    async def _bounded(self, coro, fallback: str) -> str:
        """Cap a relay step at relay_timeout_s. Relays only message and ask; no booking is written inside
        them, so cutting one off is safe (the open request, if opened, expires by itself)."""
        try:
            return await asyncio.wait_for(coro, settings.relay_timeout_s)
        except asyncio.TimeoutError:
            logger.error(f"relay timed out after {settings.relay_timeout_s}s")
            return fallback

    async def request_slot_freed(self, requester_phone: str, client, slot, db: Session) -> str:
        return await self._bounded(self._request_slot_freed(requester_phone, client, slot, db),
                                   "still being arranged, no answer yet; tell the client you will update them")

    async def _request_slot_freed(self, requester_phone: str, client, slot, db: Session) -> str:
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
            self._open_request_at[target.phone_number] = time.time()
            try:
                get_redis().hset(STATE_OPEN_REQUESTS, target.phone_number, f"{requester_phone}|{int(time.time())}")
            except Exception as e:
                logger.warning(f"Could not persist open request: {e}")
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
        return await self._bounded(self._report_outcome(from_phone, outcome, db), "forwarding is delayed")

    async def _report_outcome(self, from_phone: str, outcome: str, db: Session) -> str:
        """A client agent finished a relayed request. Forward to the requester's agent, or the admin."""
        requester = self._open_requests.pop(from_phone, None)
        opened_at = self._open_request_at.pop(from_phone, None)
        if requester is not None and opened_at is not None and time.time() - opened_at >= settings.open_request_ttl_s:
            requester = None  # expired: an old request must not capture a later, unrelated report
        try:
            get_redis().hdel(STATE_OPEN_REQUESTS, from_phone)
        except Exception as e:
            logger.warning(f"Could not clear open request: {e}")
        logger.info(f"relay: agent({from_phone}) -> orchestrator: outcome '{outcome}'")
        if requester is None:
            return "no open request"
        if requester == self._provider.phone_number:
            update = f"Update on the slot swap: {outcome}"
            if scan_output(update, self._provider.phone_number, [], is_admin=True).action != "pass":
                update = "Update on the slot swap withheld by the output firewall."
            await self._messaging_client.send_to_admin(update)
        else:
            logger.info(f"relay: orchestrator -> agent({requester})")
            agent = await self._get_or_spawn_agent(requester, db)
            await agent.handle_orchestrator_update(outcome, db)
        return "forwarded"
