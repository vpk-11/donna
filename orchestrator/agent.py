import asyncio
import logging
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from models.orm import Client, Provider
from db.redis_client import get_redis
from orchestrator.channels import (
    STATE_AGENT_REGISTRY, STATE_SESSION, STATE_LAST_DONNA, STATE_TIMEOUT,
)
from orchestrator.llm_agent import run_agent
from intelligence.judge_rules import NEW_CLIENT_STATUSES
from intelligence.prompts import CLIENT_AGENT_SYSTEM
from intelligence.context_manager import (
    summarize_conversation, trim_history,
    should_summarize, build_context_from_summary,
)
from firewall.input_guard import scan_input
from firewall.output_guard import scan_output
from donna_mcp.tools.scheduling import (
    book_session, cancel_session, reschedule_session, check_slot_conflict,
)
from donna_mcp.tools.clients import create_client
from donna_mcp.tools.conversation import save_conversation_summary
from donna_mcp.guard import acting_as
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from store.session_store import SessionStore
from utils.profile import build_client_profile
from utils.time_utils import calendar_hint, parse_date, parse_datetime

logger = logging.getLogger(__name__)

HANDOFF_TRIGGERS = [
    "frustrated", "not happy", "speak to someone", "talk to a person",
    "real person", "talk to kaushik", "speak to kaushik", "human",
    "can i speak to", "can i talk to",
]

_DATE_TIME = {
    "date": {"type": "string", "description": "Date, e.g. 2026-09-22 or 'Monday'"},
    "time": {"type": "string", "description": "Time, e.g. '10:00' or '10am'"},
}
_NONE = {"type": "object", "properties": {}}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props)}


class ClientAgent:
    """One LLM agent per client conversation: its own prompt, history and tool loop."""

    def __init__(
        self,
        phone: str,
        client: Client | None,
        provider: Provider,
        messaging_client,
        business_config: dict,
        orchestrator=None,
    ):
        self.phone = phone
        self.client = client
        self.provider = provider
        self._messaging_client = messaging_client
        self._business_config = business_config
        self._orchestrator = orchestrator
        self._history: list[dict] = []
        self._turn_count = 0
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._last_tool_calls: list[str] = []
        self._ending = False

    def _own(self, entries: list[dict]) -> list[dict]:
        return [{**e, "owner": self.phone} for e in entries]

    def scoped_history(self) -> list[dict]:
        """History that reaches any prompt. Only entries owned by this agent's client."""
        return [e for e in self._history if e.get("owner") == self.phone]

    def load_summary(self, summary: str) -> None:
        self._history = self._own(build_context_from_summary(summary))

    def recent_history(self, n: int) -> list[dict]:
        return self.scoped_history()[-n:]

    async def handle_message(self, text: str, db: Session) -> None:
        try:
            with acting_as("agent", self.phone):
                await self._handle_message_inner(text, db)
        except Exception as e:
            logger.exception(f"agent.handle_message unhandled error for {self.phone}: {e}")
            try:
                await self._send("Something went wrong - want to try again?", ConversationStore(db))
            except Exception:
                pass

    async def _handle_message_inner(self, text: str, db: Session) -> None:
        conv_store = ConversationStore(db)
        client_store = ClientStore(db)

        if self.client is None:
            self.client = client_store.get_by_phone(self.phone)

        state = conv_store.get_or_create(self.phone, "client")

        # --- Input guard (clients only, admin is trusted) ---
        firewall_result = scan_input(message=text, phone=self.phone, is_admin=False)
        if firewall_result.action != "pass":
            await self._send(
                firewall_result.redirect_message or "I didn't quite catch that. Want to try again?",
                conv_store,
            )
            return
        sanitized = firewall_result.sanitized_input or text

        # --- Handoff relay / triggers ---
        if state.handoff_active:
            relay = f"[{self.client.name if self.client else self.phone}] {sanitized}"
            await self._messaging_client.send_to_admin(relay)
            return

        lower = sanitized.lower()
        if self.client and any(t in lower for t in HANDOFF_TRIGGERS):
            from orchestrator.handoff import trigger_dynamic_handoff
            await trigger_dynamic_handoff(
                self.client, self.provider, self._messaging_client, db, conv_store
            )
            return

        self._turn_count += 1
        conv_store.update(self.phone, {"turn_count": self._turn_count})

        # --- The agent decides and acts ---
        self._last_tool_calls = []
        response = await run_agent(
            system=self._system_prompt(state),
            history=self.scoped_history(),
            user_text=sanitized,
            tools=self._tools(db, conv_store),
            calls_made=self._last_tool_calls,
        )
        if not response:
            return

        # --- Output guard ---
        out_result = scan_output(
            response=response,
            phone=self.phone,
            tool_calls_made=self._last_tool_calls,
            exclude_name=self.client.name if self.client else None,
        )
        if out_result.action != "pass":
            await self._send(
                out_result.redirect_message or "Let me double-check on that and get back to you.",
                conv_store,
            )
            return

        # --- Send + update state ---
        await self._send(response, conv_store)
        self._history += self._own([
            {"role": "user", "content": sanitized},
            {"role": "donna", "content": response},
        ])

        if should_summarize(self.scoped_history()) and self.client:
            summary = await summarize_conversation(
                self.scoped_history(),
                client_name=self.client.name,
                provider_name=self.provider.name,
            )
            if summary:
                self._history = self._own(trim_history(self.scoped_history(), summary))
                try:
                    get_redis().set(STATE_SESSION.format(phone=self.phone), summary, ex=7 * 24 * 3600)
                except Exception as e:
                    logger.warning(f"agent.summary_redis_write failed: {e}")

        try:
            timeout_mins = self._business_config.get("conversation_timeout_mins", 5)
            get_redis().set(STATE_TIMEOUT.format(phone=self.phone), "1", ex=timeout_mins * 60)
        except Exception as e:
            logger.warning(f"agent.timeout_key failed: {e}")

        if self._ending:
            await self._finalize_conversation(db, conv_store)

    # -------------------------------------------------------------------------
    # Prompt + tools
    # -------------------------------------------------------------------------

    def _system_prompt(self, state) -> str:
        pending = (state.context or {}).get("pending_orchestrator_request") if state else None
        profile = build_client_profile(self.client) if self.client else "Unknown new contact (not yet a client)"
        config = self.provider.business_config or {}
        return CLIENT_AGENT_SYSTEM.format(
            provider_name=self.provider.name,
            business_type=self.provider.business_type,
            today=date.today().strftime("%A %Y-%m-%d"),
            calendar=calendar_hint(),
            profile=profile,
            services=config.get("services", f"1-on-1 {self.provider.business_type} sessions"),
            pricing=config.get("pricing", "not listed; ask the admin"),
            pending=(
                f"Open request relayed by the orchestrator, awaiting this client's answer: {pending}"
                if pending else "None"
            ),
            cold=(
                "This person is not a client yet. As soon as they tell you their name, you MUST call register_me with it before replying; never say they are registered unless that tool returned success."
                if not self.client else ""
            ),
        )

    def _tools(self, db: Session, conv_store: ConversationStore) -> dict:
        session_store = SessionStore(db)
        duration = self._business_config.get("session_duration_mins", 60)
        config = self.provider.business_config or {}
        tools: dict = {
            "get_services_and_pricing": (
                "Services and pricing this business offers.", _NONE,
                lambda: {"services": config.get("services"), "pricing": config.get("pricing")},
            ),
        }

        if self.client is None:
            async def register_me(name: str):
                result = await asyncio.to_thread(
                    create_client, name=name, phone_number=self.phone, status="cold_lead",
                )
                if "error" not in result:
                    self.client = ClientStore(db).get_by_phone(self.phone)
                    conv_store.update(self.phone, {"client_id": self.client.id})
                return result
            tools["register_me"] = (
                "Register this contact as a new lead. name is the person's own name (never Donna, that is you).",
                _obj({"name": {"type": "string"}}), register_me,
            )
            return tools

        client = self.client

        def my_sessions():
            return [{"session_id": s.id, "when": s.scheduled_at.strftime("%A %Y-%m-%d %H:%M")}
                    for s in session_store.get_upcoming_for_client(client.id)]

        def free_slots(date: str):
            slots = session_store.get_free_slots(self.provider.id, parse_date(date), duration, self.provider)
            return {"slots": [s.strftime("%H:%M") for s in slots[:8]]}

        async def book(date: str, time: str):
            slot = parse_datetime(date, time)
            conflict = await asyncio.to_thread(
                check_slot_conflict, requested_at=slot.isoformat(), duration_mins=duration,
                requesting_client_id=client.id,
            )
            if "error" in conflict:
                return conflict
            if conflict["status"] != "FREE":
                return {
                    "booked": False, "reason": "slot not free",
                    "alternatives": [datetime.fromisoformat(s).strftime("%A %H:%M")
                                     for s in (conflict.get("slots") or [])[:3]],
                    "can_ask_orchestrator_to_free_it": conflict["status"] == "SWAP_POSSIBLE",
                }
            if client.status in NEW_CLIENT_STATUSES or not self.provider.auto_book:
                conv_store.get_or_create(self.provider.phone_number, "admin")
                conv_store.update_context(self.provider.phone_number, {
                    "pending_booking": {"slot": slot.isoformat(), "client_id": client.id, "alternatives": []},
                })
                await self._messaging_client.send_to_admin(
                    f"{client.name} wants {slot.strftime('%A %b %d at %I:%M %p')}. Confirm to book."
                )
                return {"booked": False, "status": "sent to the admin for confirmation"}
            result = await asyncio.to_thread(
                book_session, client_id=client.id, scheduled_at=slot.isoformat(), duration_mins=duration,
            )
            if "error" not in result:
                await self._messaging_client.send_to_admin(
                    f"{client.name} booked {slot.strftime('%A %b %d at %I:%M %p')}. Added to your schedule."
                )
            return result

        async def reschedule(session_id: int, date: str, time: str):
            new_slot = parse_datetime(date, time)
            result = await asyncio.to_thread(
                reschedule_session, session_id=session_id, new_time=new_slot.isoformat(),
            )
            if "error" not in result:
                await self._messaging_client.send_to_admin(
                    f"{client.name} moved a session to {new_slot.strftime('%A %b %d at %I:%M %p')}."
                )
            return result

        async def cancel(session_id: int):
            result = await asyncio.to_thread(cancel_session, session_id=session_id)
            if "error" not in result:
                await self._messaging_client.send_to_admin(f"{client.name} cancelled a session.")
            return result

        async def ask_human():
            from orchestrator.handoff import trigger_explicit_handoff_from_client
            await trigger_explicit_handoff_from_client(
                client, self.provider, self._messaging_client, db, conv_store
            )
            return {"ok": True}

        async def ask_orchestrator(date: str, time: str):
            if self._orchestrator is None:
                return {"error": "no orchestrator"}
            slot = parse_datetime(date, time)
            return {"result": await self._orchestrator.route_request(
                self.phone,
                f"Client {client.name} (id {client.id}) needs the {slot.isoformat()} slot freed. "
                f"Find who holds it and ask that client's agent to move.",
                db,
            )}

        async def report(outcome: str):
            if self._orchestrator is None:
                return {"error": "no orchestrator"}
            return {"result": await self._orchestrator.report_outcome(self.phone, outcome, db)}

        def end():
            self._ending = True
            return {"ok": True}

        def clear_open_request():
            conv_store.update_context(self.phone, {"pending_orchestrator_request": None})
            return {"ok": True}

        tools.update({
            "get_my_upcoming_sessions": ("List this client's upcoming sessions.", _NONE, my_sessions),
            "get_free_slots": ("Open slots on a date.", _obj({"date": _DATE_TIME["date"]}), free_slots),
            "book_session": ("Book a session. Never say it is booked unless this returns booked data.",
                             _obj(_DATE_TIME), book),
            "reschedule_session": ("Move an existing session of this client.",
                                   _obj({"session_id": {"type": "integer"}, **_DATE_TIME}), reschedule),
            "cancel_session": ("Cancel one of this client's sessions.",
                               _obj({"session_id": {"type": "integer"}}), cancel),
            "ask_orchestrator_to_free_slot": (
                "When the wanted slot is held by someone else, ask the orchestrator to arrange it. "
                "You never contact other clients yourself.", _obj(_DATE_TIME), ask_orchestrator),
            "report_to_orchestrator": (
                "After acting on an open relayed request, tell the orchestrator the outcome "
                "(no personal details).", _obj({"outcome": {"type": "string"}}), report),
            "request_human": ("Hand the conversation to the business owner.", _NONE, ask_human),
            "end_conversation": ("Call when the client says goodbye or the request is fully done.", _NONE, end),
            "clear_open_request": ("Mark the orchestrator-relayed request as answered.", _NONE, clear_open_request),
        })
        return tools

    # -------------------------------------------------------------------------
    # Orchestrator-relayed requests (agent-to-agent goes only through the orchestrator)
    # -------------------------------------------------------------------------

    async def handle_orchestrator_request(self, request: str, db: Session) -> str:
        """Another client needs something from this client. This agent asks its own client and acts itself."""
        with acting_as("agent", self.phone):
            conv_store = ConversationStore(db)
            conv_store.get_or_create(self.phone, "client")
            message = await run_agent(
                system=self._system_prompt(conv_store.get_by_phone(self.phone)),
                history=self.scoped_history(),
                user_text=(
                    "Write the text message asking this client to shift their session to one of the alternative "
                    "slots listed in the request, using only those slots, as plain weekday and time. Say 'something came up on our end'. Never mention any other "
                    f"person. Request from the orchestrator: {request}"
                ),
                tools={},
            )
            if not message:
                return "no response from agent"
            conv_store.update_context(self.phone, {"pending_orchestrator_request": request})
            await self._send(message, conv_store)
            return "asked own client; awaiting their answer"

    async def handle_orchestrator_update(self, update: str, db: Session) -> None:
        """The orchestrator reports on a request this agent made. Tell the own client."""
        with acting_as("agent", self.phone):
            conv_store = ConversationStore(db)
            message = await run_agent(
                system=self._system_prompt(conv_store.get_by_phone(self.phone)),
                history=self.scoped_history(),
                user_text=(
                    "Write the text message telling this client the news below, and offer to book the slot "
                    f"if it is now free. Never mention any other person. Update: {update}"
                ),
                tools={},
            )
            if message:
                await self._send(message, conv_store)

    async def _send(self, text: str, conv_store: ConversationStore) -> None:
        await self._messaging_client.send_to_phone(self.phone, text)
        conv_store.update_last_donna_message(self.phone, text)
        try:
            get_redis().set(STATE_LAST_DONNA.format(phone=self.phone), text, ex=24 * 3600)
        except Exception as e:
            logger.warning(f"agent._send redis failed: {e}")

    async def _finalize_conversation(self, db: Session, conv_store: ConversationStore) -> None:
        history = self.scoped_history()
        if history and self.client:
            summary = await summarize_conversation(
                history, client_name=self.client.name, provider_name=self.provider.name,
            )
            if summary:
                try:
                    get_redis().set(STATE_SESSION.format(phone=self.phone), summary, ex=7 * 24 * 3600)
                except Exception as e:
                    logger.warning(f"agent.finalize redis failed: {e}")
                try:
                    save_conversation_summary(self.phone, summary, self._turn_count)
                except Exception as e:
                    logger.warning(f"agent.finalize db_write failed: {e}")

        try:
            r = get_redis()
            r.hdel(STATE_AGENT_REGISTRY, self.phone)
            r.delete(STATE_TIMEOUT.format(phone=self.phone))
        except Exception as e:
            logger.warning(f"agent.finalize registry cleanup failed: {e}")
        logger.info(f"agent.finalized: {self.phone} ({self._turn_count} turns)")
