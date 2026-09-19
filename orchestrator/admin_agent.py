import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from db.redis_client import get_redis
from donna_mcp.guard import acting_as
from donna_mcp.tools.clients import create_client, update_client
from donna_mcp.tools.scheduling import (
    book_session, cancel_session, reschedule_session, check_slot_conflict, get_sessions_for_date,
)
from intelligence.prompts import ADMIN_AGENT_SYSTEM
from orchestrator.channels import STATE_AGENT_REGISTRY
from orchestrator.llm_agent import run_agent
from store.client_store import ClientStore
from store.conversation_store import ConversationStore
from store.session_store import SessionStore
from utils.time_utils import calendar_hint, parse_date, parse_datetime

logger = logging.getLogger(__name__)

_NONE = {"type": "object", "properties": {}}
_DT = {
    "date": {"type": "string", "description": "Date, e.g. 2026-09-22 or 'Monday'"},
    "time": {"type": "string", "description": "Time, e.g. '10:00' or '10am'"},
}
_NAME = {"client_name": {"type": "string"}}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props)}


class AdminAgent:
    """The provider's own LLM agent. Runs admin commands with the admin's authority."""

    def __init__(self, provider, messaging_client, orchestrator, business_config: dict):
        self.provider = provider
        self._messaging_client = messaging_client
        self._orchestrator = orchestrator
        self._business_config = business_config

    async def handle_message(self, text: str, db: Session) -> None:
        with acting_as("admin"):
            await self._handle(text, db)

    async def _handle(self, text: str, db: Session) -> None:
        conv_store = ConversationStore(db)
        phone = self.provider.phone_number
        state = conv_store.get_or_create(phone, "admin")

        # Live handoff: the admin talks to a client through Donna
        if state.handoff_active and state.handoff_target_phone:
            await self._handoff_relay(text, state, db, conv_store)
            return

        # Pending yes/no on a dynamic handoff offer
        if state.context.get("pending_dynamic_handoff"):
            await self._pending_handoff_answer(text, state, db, conv_store)
            return

        history = conv_store.get_history(phone)
        if history and history[-1] == {"role": "user", "content": text}:
            history = history[:-1]
        pending = state.context.get("pending_booking")
        response = await run_agent(
            system=ADMIN_AGENT_SYSTEM.format(
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                today=date.today().strftime("%A %Y-%m-%d"),
                calendar=calendar_hint(),
                pending=(f"Booking awaiting your confirmation: {json.dumps(pending)}" if pending else "None"),
            ),
            history=history,
            user_text=text,
            tools=self._tools(db, conv_store),
        )
        if response:
            await self._messaging_client.send_to_admin(response)

    # --- handoff flow (unchanged behavior) ---

    async def _handoff_relay(self, text, state, db, conv_store) -> None:
        phone = self.provider.phone_number
        if text.lower().strip() in ("done", "donna take over", "donna, take over"):
            target = state.handoff_target_phone
            conv_store.update(phone, {"handoff_active": False, "handoff_target_phone": None})
            conv_store.update(target, {"handoff_active": False})
            try:
                r = get_redis()
                raw = r.hget(STATE_AGENT_REGISTRY, target)
                if raw:
                    data = json.loads(raw)
                    data["handoff_active"] = False
                    r.hset(STATE_AGENT_REGISTRY, target, json.dumps(data))
            except Exception as e:
                logger.warning(f"admin.handoff_close redis failed: {e}")
            await self._messaging_client.send_to_admin("Got it - I'm back in control.")
            await self._summarize_handoff(target, db, conv_store)
        else:
            await self._messaging_client.send_to_phone(
                state.handoff_target_phone, f"[{self.provider.name}] {text}"
            )

    async def _pending_handoff_answer(self, text, state, db, conv_store) -> None:
        lower = text.lower().strip()
        target_name = state.context.get("handoff_target_name", "the client")
        target_phone = state.context.get("handoff_target_phone")
        if lower in {"yes", "yeah", "yep", "sure", "jump in", "i will jump in", "do it"}:
            from orchestrator.handoff import start_handoff_from_admin
            await start_handoff_from_admin(self.provider, target_phone, self._messaging_client, db, conv_store)
        elif lower in {"no", "nope", "handle it", "donna handle it", "you handle it"}:
            conv_store.clear_context(self.provider.phone_number)
            await self._messaging_client.send_to_admin("Got it, I'll keep handling it.")
        else:
            await self._messaging_client.send_to_admin(
                f"Just to confirm - do you want to jump into the conversation with {target_name}? (yes / no)"
            )

    async def _summarize_handoff(self, target_phone, db, conv_store) -> None:
        from intelligence.llm_client import call_llm
        client = ClientStore(db).get_by_phone(target_phone)
        name = client.name if client else target_phone
        history = conv_store.get_history(target_phone)
        if not history:
            return
        text = "\n".join(
            f"{'You' if t['role'] == 'donna' else name}: {t['content']}" for t in history[-20:]
        )
        summary = await call_llm(messages=[
            {"role": "system", "content": "You are Donna, the admin's assistant. Be direct and brief."},
            {"role": "user", "content": (
                f"{self.provider.name} just finished a live conversation with their client {name}:\n{text}\n\n"
                "Summarize in 2-3 sentences what was discussed and what the client wants, then list any clear "
                "action items. If booking was discussed, ask whether to go ahead and book it."
            )},
        ])
        await self._messaging_client.send_to_admin(summary)

    # --- tools ---

    def _tools(self, db: Session, conv_store: ConversationStore) -> dict:
        client_store = ClientStore(db)
        session_store = SessionStore(db)
        provider = self.provider
        duration = self._business_config.get("session_duration_mins", 60)

        def find(name: str):
            return client_store.get_by_name(name, provider.id)

        def schedule(days: int = 7):
            out = []
            for i in range(days):
                res = get_sessions_for_date((date.today() + timedelta(days=i)).isoformat())
                for s in res.get("sessions", []):
                    c = client_store.get(s["client_id"])
                    out.append({"client": c.name if c else "Unknown", "when": s["scheduled_at"], "session_id": s["id"]})
            return sorted(out, key=lambda s: s["when"]) or "No sessions scheduled."

        def client_info(client_name: str):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            state = conv_store.get_by_phone(c.phone_number)
            agent = self._orchestrator._agents.get(c.phone_number)
            return {
                "name": c.name, "status": c.status, "notes": c.notes,
                "last_message_to_them": state.last_donna_message if state else None,
                "recent_conversation": agent.recent_history(3) if agent else [],
                "upcoming": [s.scheduled_at.strftime("%a %b %d %I:%M %p") + f" (id {s.id})"
                             for s in session_store.get_upcoming_for_client(c.id)[:3]],
            }

        async def add_note(client_name: str, notes: str):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            merged = f"{c.notes}\n{notes}".strip() if c.notes else notes
            return await asyncio.to_thread(update_client, client_id=c.id, notes=merged)

        async def add_client(client_name: str, phone_number: str, greeting: str, notes: str = ""):
            if client_store.get_by_phone(phone_number):
                return {"error": "already in the system"}
            result = await asyncio.to_thread(
                create_client, name=client_name, phone_number=phone_number, status="prospect", notes=notes or None,
            )
            if "error" not in result:
                conv_store.get_or_create(phone_number, "client")
                await self._messaging_client.send_to_phone(phone_number, greeting)
            return result

        async def message_client(client_name: str, message: str, date: str = "", time: str = ""):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            await self._messaging_client.send_to_phone(c.phone_number, message)
            if date and time:
                slot = parse_datetime(date, time)
                conv_store.get_or_create(c.phone_number, "client")
                conv_store.update_context(c.phone_number, {
                    "pending_booking": {"slot": slot.isoformat(), "client_id": c.id, "alternatives": []},
                })
            return {"sent": True}

        async def book_for_client(client_name: str, date: str, time: str):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            slot = parse_datetime(date, time)
            conflict = await asyncio.to_thread(
                check_slot_conflict, requested_at=slot.isoformat(), duration_mins=duration, requesting_client_id=c.id,
            )
            if conflict.get("status") not in (None, "FREE"):
                return {"booked": False, **conflict,
                        "hint": "if SWAP_POSSIBLE you may use swap_via_orchestrator after the admin agrees"}
            return await asyncio.to_thread(
                book_session, client_id=c.id, scheduled_at=slot.isoformat(), duration_mins=duration,
            )

        async def confirm_pending_booking():
            pending = (conv_store.get_by_phone(provider.phone_number).context or {}).get("pending_booking")
            if not pending:
                return {"error": "nothing pending"}
            result = await asyncio.to_thread(
                book_session, client_id=pending["client_id"], scheduled_at=pending["slot"], duration_mins=duration,
            )
            conv_store.clear_context(provider.phone_number)
            if "error" not in result:
                c = client_store.get(pending["client_id"])
                if c:
                    await self._messaging_client.send_to_phone(
                        c.phone_number,
                        f"You're booked for {datetime.fromisoformat(pending['slot']).strftime('%A %b %d at %I:%M %p')}.",
                    )
            return result

        def decline_pending():
            conv_store.clear_context(provider.phone_number)
            return {"ok": True}

        async def cancel_client_session(client_name: str):
            c = find(client_name)
            up = session_store.get_upcoming_for_client(c.id) if c else []
            if not up:
                return {"error": "no upcoming session found"}
            return await asyncio.to_thread(cancel_session, session_id=up[0].id)

        async def reschedule_client_session(client_name: str, date: str, time: str):
            c = find(client_name)
            up = session_store.get_upcoming_for_client(c.id) if c else []
            if not up:
                return {"error": "no upcoming session found"}
            return await asyncio.to_thread(
                reschedule_session, session_id=up[0].id, new_time=parse_datetime(date, time).isoformat(),
            )

        async def cancel_day(date: str, message_to_clients: str):
            res = get_sessions_for_date(parse_date(date).isoformat())
            cancelled = 0
            for s in res.get("sessions", []):
                out = await asyncio.to_thread(cancel_session, session_id=s["id"])
                c = client_store.get(s["client_id"])
                if "error" not in out and c:
                    cancelled += 1
                    await self._messaging_client.send_to_phone(c.phone_number, message_to_clients)
            return {"cancelled": cancelled}

        async def start_handoff(client_name: str):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            from orchestrator.handoff import start_handoff_from_admin
            await start_handoff_from_admin(provider, c.phone_number, self._messaging_client, db, conv_store)
            return {"ok": True}

        async def swap(client_name: str, date: str, time: str):
            c = find(client_name)
            if not c:
                return {"error": f"No client named {client_name}"}
            slot = parse_datetime(date, time)
            return {"result": await self._orchestrator.route_request(
                provider.phone_number,
                f"Client {c.name} (id {c.id}) needs the {slot.isoformat()} slot freed. "
                f"Find who holds it and ask that client's agent to move.",
                db,
            )}

        return {
            "get_schedule": ("Upcoming sessions for the next N days.",
                             {"type": "object", "properties": {"days": {"type": "integer"}}}, schedule),
            "get_client": ("Status, notes, upcoming sessions and recent conversation of a client.", _obj(_NAME), client_info),
            "add_client_note": ("Append a note to a client.", _obj({**_NAME, "notes": {"type": "string"}}), add_note),
            "add_new_client": ("Add a new prospect and send them a warm greeting you write, introducing yourself as Donna.",
                               _obj({**_NAME, "phone_number": {"type": "string"}, "greeting": {"type": "string"}}), add_client),
            "message_client": ("Send a message you write to a client. Pass date and time if it offers a slot.",
                               {"type": "object", "properties": {**_NAME, "message": {"type": "string"}, **_DT},
                                "required": ["client_name", "message"]}, message_client),
            "book_session_for_client": ("Book a client's session.", _obj({**_NAME, **_DT}), book_for_client),
            "confirm_pending_booking": ("Book the request awaiting the admin's confirmation.", _NONE, confirm_pending_booking),
            "decline_pending": ("Discard whatever is awaiting confirmation.", _NONE, decline_pending),
            "cancel_client_session": ("Cancel a client's next session.", _obj(_NAME), cancel_client_session),
            "reschedule_client_session": ("Move a client's next session.", _obj({**_NAME, **_DT}), reschedule_client_session),
            "cancel_day": ("Cancel every session on a date and notify those clients with the message you write.",
                           _obj({"date": _DT["date"], "message_to_clients": {"type": "string"}}), cancel_day),
            "start_handoff": ("Connect the admin live with a client.", _obj(_NAME), start_handoff),
            "swap_via_orchestrator": ("Get a slot freed that another client holds, via the orchestrator.",
                                      _obj({**_NAME, **_DT}), swap),
        }
