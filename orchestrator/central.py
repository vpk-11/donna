import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from models.orm import Provider
from db.redis_client import get_redis
from orchestrator.channels import STATE_AGENT_REGISTRY, STATE_SESSION
from orchestrator.agent import ClientAgent
from intelligence.intent_parser import parse_intent
from intelligence.response_generator import generate_response
from firewall.input_guard import scan_input
from donna_mcp.tools.scheduling import (
    book_session, cancel_session, reschedule_session,
    get_sessions_for_date, check_slot_conflict,
)
from donna_mcp.tools.clients import create_client, update_client
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from store.session_store import SessionStore
from utils.profile import build_client_profile
from utils.time_utils import looks_like_phone

logger = logging.getLogger(__name__)


class CentralOrchestrator:
    def __init__(self, messaging_client, business_config: dict):
        self._agents: dict[str, ClientAgent] = {}
        self._provider: Provider | None = None
        self._messaging_client = messaging_client
        self._business_config = business_config

    async def startup(self, db: Session) -> None:
        self._provider = ProviderStore(db).get_first()
        if not self._provider:
            raise RuntimeError("No provider configured. Run seed.sh first.")
        logger.info(f"Orchestrator started for provider: {self._provider.name}")

    async def handle_message(self, phone: str, text: str, db: Session) -> None:
        try:
            await self._handle_message_inner(phone, text, db)
        except Exception as e:
            logger.exception(f"orchestrator.handle_message unhandled error for {phone}: {e}")

    async def _handle_message_inner(self, phone: str, text: str, db: Session) -> None:
        if not self._provider:
            logger.error("Orchestrator not initialized - missing provider")
            return

        # Append to history before routing (mirrors V1 route_message)
        conv_store = ConversationStore(db)
        state = conv_store.get_by_phone(phone)
        if state:
            conv_store.append_history(phone, "user", text)

        if phone == self._provider.phone_number:
            await self._handle_admin(text, db)
        else:
            # Create state for cold inbound before history append
            if not state:
                conv_store.get_or_create(phone, "client")
                conv_store.append_history(phone, "user", text)
            agent = await self._get_or_spawn_agent(phone, db)
            await agent.handle_message(text, db)

    async def _get_or_spawn_agent(self, phone: str, db: Session) -> ClientAgent:
        if phone in self._agents:
            return self._agents[phone]

        client = ClientStore(db).get_by_phone(phone)

        agent = ClientAgent(
            phone=phone,
            client=client,
            provider=self._provider,
            messaging_client=self._messaging_client,
            business_config=self._business_config,
        )

        try:
            r = get_redis()
            summary_raw = r.get(STATE_SESSION.format(phone=phone))
            if summary_raw:
                summary = summary_raw.decode() if isinstance(summary_raw, bytes) else summary_raw
                agent.load_summary(summary)
        except Exception as e:
            logger.warning(f"Could not load summary for {phone}: {e}")

        try:
            r = get_redis()
            r.hset(STATE_AGENT_REGISTRY, phone, json.dumps({
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
                "handoff_active": False,
            }))
        except Exception as e:
            logger.warning(f"Could not register agent for {phone}: {e}")

        self._agents[phone] = agent
        logger.info(f"agent.spawned: {phone}")
        return agent

    def retire_agent(self, phone: str) -> None:
        self._agents.pop(phone, None)

    # -------------------------------------------------------------------------
    # Admin handler (migrated from core/admin_handler.py)
    # -------------------------------------------------------------------------

    async def _handle_admin(self, text: str, db: Session) -> None:
        conv_store = ConversationStore(db)
        client_store = ClientStore(db)
        session_store = SessionStore(db)
        state = conv_store.get_or_create(self._provider.phone_number, "admin")

        # Check 1: handoff relay active
        if state.handoff_active and state.handoff_target_phone:
            lower = text.lower().strip()
            if lower in ("done", "donna take over", "donna, take over"):
                target_phone = state.handoff_target_phone
                conv_store.update(self._provider.phone_number, {
                    "handoff_active": False,
                    "handoff_target_phone": None,
                })
                if target_phone:
                    conv_store.update(target_phone, {"handoff_active": False})
                    # Update Redis registry: clear handoff_active for the client
                    try:
                        r = get_redis()
                        existing_raw = r.hget(STATE_AGENT_REGISTRY, target_phone)
                        if existing_raw:
                            data = json.loads(existing_raw)
                            data["handoff_active"] = False
                            r.hset(STATE_AGENT_REGISTRY, target_phone, json.dumps(data))
                    except Exception as e:
                        logger.warning(f"orchestrator.handoff_close redis failed: {e}")
                await self._messaging_client.send_to_admin("Got it - I'm back in control.")
                if target_phone:
                    await self._summarize_handoff(target_phone, db, conv_store, client_store)
            else:
                relay_msg = f"[{self._provider.name}] {text}"
                await self._messaging_client.send_to_phone(state.handoff_target_phone, relay_msg)
            return

        # Check 2: pending dynamic handoff yes/no
        if state.context.get("pending_dynamic_handoff"):
            lower = text.lower().strip()
            affirmatives = {"yes", "yeah", "yep", "sure", "jump in", "i will jump in", "do it"}
            negatives = {"no", "nope", "handle it", "donna handle it", "you handle it"}
            target_name = state.context.get("handoff_target_name", "the client")
            target_phone = state.context.get("handoff_target_phone")

            if lower in affirmatives:
                from orchestrator.handoff import start_handoff_from_admin
                await start_handoff_from_admin(
                    self._provider, target_phone, self._messaging_client, db, conv_store
                )
            elif lower in negatives:
                conv_store.clear_context(self._provider.phone_number)
                await self._messaging_client.send_to_admin("Got it, I'll keep handling it.")
            else:
                await self._messaging_client.send_to_admin(
                    f"Just to confirm - do you want to jump into the conversation with {target_name}? (yes / no)"
                )
            return

        # Check 3: pending clarification for NEW_CLIENT_INTRO
        if state.context.get("pending_clarification") == "NEW_CLIENT_INTRO":
            await self._handle_new_client_intro_clarification(text, state, db, conv_store)
            return

        # Parse intent
        history = conv_store.get_history(self._provider.phone_number)
        intent_result = await parse_intent(
            message=text,
            role="admin",
            context=state.context,
            last_donna_message=state.last_donna_message or "",
            history=history,
        )

        intent = intent_result.intent

        if intent == "CHECK_SCHEDULE":
            await self._check_schedule(db, client_store)
        elif intent == "CHECK_CLIENT_STATUS":
            await self._check_client_status(intent_result, db, client_store, session_store, conv_store)
        elif intent == "CLIENT_INFO":
            await self._update_client_info(intent_result, db, client_store)
        elif intent == "NEW_CLIENT_INTRO":
            await self._handle_new_client_intro(text, intent_result, state, db, conv_store)
        elif intent == "BOOK_SESSION":
            await self._handle_book_session(intent_result, state, db, client_store, conv_store)
        elif intent == "CANCEL_DAY":
            from scheduling.session_manager import cancel_day
            from utils.time_utils import parse_date
            date_str = intent_result.entities.get("date", "today")
            target_date = parse_date(date_str)
            await cancel_day(
                self._provider.id, target_date, self._messaging_client, db, session_store, client_store
            )
        elif intent == "CANCEL_SESSION":
            await self._handle_cancel_session(intent_result, db, client_store, session_store)
        elif intent == "RESCHEDULE_SESSION":
            await self._handle_reschedule_session(intent_result, state, db, client_store, session_store, conv_store)
        elif intent == "PROACTIVE_MESSAGE":
            await self._handle_proactive_message(intent_result, db, client_store, conv_store)
        elif intent == "HANDOFF_REQUEST":
            from orchestrator.handoff import start_handoff_from_admin
            target_name = intent_result.entities.get("client_name", "")
            target_client = client_store.get_by_name(target_name, self._provider.id) if target_name else None
            if target_client:
                await start_handoff_from_admin(
                    self._provider, target_client.phone_number, self._messaging_client, db, conv_store
                )
            else:
                await self._messaging_client.send_to_admin(
                    "Who do you want to jump in with? Give me their name."
                )
        elif intent == "HANDOFF_DELEGATE":
            conv_store.clear_context(self._provider.phone_number)
            await self._messaging_client.send_to_admin("Got it - I'll keep handling it.")
        elif intent == "CONFIRM":
            await self._handle_admin_confirm(intent_result, state, db, client_store, session_store, conv_store)
        elif intent == "DECLINE":
            conv_store.clear_context(self._provider.phone_number)
            await self._messaging_client.send_to_admin("Understood, no problem.")
        else:
            response = await generate_response(
                situation=f"Admin sent an unclear message: '{text}'. Ask for clarification.",
                recipient=self._provider.name,
                provider_name=self._provider.name,
                business_type=self._provider.business_type,
            )
            await self._messaging_client.send_to_admin(response)

    # -------------------------------------------------------------------------
    # Admin intent handlers
    # -------------------------------------------------------------------------

    async def _check_schedule(self, db: Session, client_store: ClientStore) -> None:
        today = datetime.utcnow().date()
        all_sessions = []
        for i in range(7):
            date = today + timedelta(days=i)
            result = await asyncio.to_thread(get_sessions_for_date, date.isoformat())
            if "error" not in result:
                all_sessions.extend(result.get("sessions", []))

        if not all_sessions:
            await self._messaging_client.send_to_admin("No sessions scheduled in the next 7 days.")
            return

        all_sessions.sort(key=lambda s: s["scheduled_at"])
        lines = []
        for s in all_sessions:
            client = client_store.get(s["client_id"])
            name = client.name if client else "Unknown"
            dt = datetime.fromisoformat(s["scheduled_at"])
            lines.append(f"{name} - {dt.strftime('%a %b %d at %I:%M %p')}")

        await self._messaging_client.send_to_admin(f"Upcoming sessions:\n{chr(10).join(lines)}")

    async def _check_client_status(
        self, intent_result, db: Session,
        client_store: ClientStore, session_store: SessionStore, conv_store: ConversationStore,
    ) -> None:
        client_name = intent_result.entities.get("client_name", "")
        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None
        if not client:
            await self._messaging_client.send_to_admin(
                f"I don't see a '{client_name}' in my contacts. New client? Introduce them with their phone number."
            )
            return

        client_state = conv_store.get_by_phone(client.phone_number)
        upcoming = session_store.get_upcoming_for_client(client.id)

        # Supplement with live agent context if available
        live_context = ""
        if client.phone_number in self._agents:
            agent = self._agents[client.phone_number]
            recent = agent.recent_history(3)
            if recent:
                live_context = " Recent live: " + " | ".join(
                    f"{'Donna' if t['role'] == 'donna' else client.name}: {t['content'][:60]}"
                    for t in recent
                )

        last_msg = (client_state.last_donna_message if client_state else None) or "No messages yet"
        upcoming_str = ", ".join(s.scheduled_at.strftime("%a %b %d %I:%M %p") for s in upcoming[:3]) or "None"

        situation = (
            f"Admin asked about client {client.name}. "
            f"Status: {client.status}. "
            f"Last Donna message to them: '{last_msg}'.{live_context} "
            f"Upcoming sessions: {upcoming_str}. "
            f"Notes: {client.notes or 'none'}. "
            f"Summarize for admin."
        )
        response = await generate_response(
            situation=situation,
            recipient=self._provider.name,
            provider_name=self._provider.name,
            business_type=self._provider.business_type,
        )
        await self._messaging_client.send_to_admin(response)

    async def _update_client_info(self, intent_result, db: Session, client_store: ClientStore) -> None:
        client_name = intent_result.entities.get("client_name", "")
        notes = intent_result.entities.get("notes", "")
        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None
        if not client:
            await self._messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
            return
        existing_notes = client.notes or ""
        new_notes = f"{existing_notes}\n{notes}".strip() if existing_notes else notes
        await asyncio.to_thread(update_client, client_id=client.id, notes=new_notes)
        await self._messaging_client.send_to_admin(f"Updated notes for {client.name}.")

    async def _handle_new_client_intro(
        self, text: str, intent_result, state,
        db: Session, conv_store: ConversationStore,
    ) -> None:
        entities = intent_result.entities
        client_name = entities.get("client_name", "").strip()
        phone = entities.get("phone_number", "").strip()
        notes = entities.get("notes", "").strip()

        if not client_name:
            conv_store.update_context(self._provider.phone_number, {"pending_clarification": "NEW_CLIENT_INTRO"})
            await self._messaging_client.send_to_admin("What's the client's name?")
            return

        if not phone:
            conv_store.update_context(self._provider.phone_number, {
                "pending_clarification": "NEW_CLIENT_INTRO",
                "partial_name": client_name,
                "partial_notes": notes,
            })
            await self._messaging_client.send_to_admin(f"Got it - what's {client_name}'s phone number?")
            return

        await self._create_and_greet_client(client_name, phone, notes, db, conv_store)

    async def _handle_new_client_intro_clarification(
        self, text: str, state, db: Session, conv_store: ConversationStore,
    ) -> None:
        ctx = state.context
        partial_name = ctx.get("partial_name", "")
        partial_notes = ctx.get("partial_notes", "")

        if not partial_name:
            if looks_like_phone(text):
                conv_store.update_context(self._provider.phone_number, {
                    "pending_clarification": "NEW_CLIENT_INTRO",
                    "partial_phone": text.strip(),
                })
                await self._messaging_client.send_to_admin("And what's their name?")
            else:
                conv_store.update_context(self._provider.phone_number, {
                    "pending_clarification": "NEW_CLIENT_INTRO",
                    "partial_name": text.strip(),
                })
                await self._messaging_client.send_to_admin(f"Got it - what's {text.strip()}'s phone number?")
            return

        if looks_like_phone(text):
            phone = text.strip()
            conv_store.clear_context(self._provider.phone_number)
            await self._create_and_greet_client(partial_name, phone, partial_notes, db, conv_store)
        else:
            conv_store.update_context(self._provider.phone_number, {"partial_name": text.strip()})
            await self._messaging_client.send_to_admin(f"Got it - what's {text.strip()}'s phone number?")

    async def _create_and_greet_client(
        self, name: str, phone: str, notes: str,
        db: Session, conv_store: ConversationStore,
    ) -> None:
        client_store = ClientStore(db)
        existing = client_store.get_by_phone(phone)
        if existing:
            await self._messaging_client.send_to_admin(f"{existing.name} ({phone}) is already in the system.")
            return

        result = await asyncio.to_thread(
            create_client,
            name=name,
            phone_number=phone,
            status="prospect",
            notes=notes or None,
        )
        if "error" in result:
            await self._messaging_client.send_to_admin(f"Couldn't create client: {result['error']}")
            return

        conv_store.get_or_create(phone, "client")

        greeting = await generate_response(
            situation=f"{self._provider.name} introduced a new prospect named {name} ({notes or 'no extra notes'}). Send a warm greeting introducing yourself as Donna, {self._provider.name}'s assistant, and ask how you can help.",
            recipient=name,
            provider_name=self._provider.name,
            business_type=self._provider.business_type,
        )
        await self._messaging_client.send_to_phone(phone, greeting)
        conv_store.clear_context(self._provider.phone_number)
        await self._messaging_client.send_to_admin(f"Got it - reaching out to {name} now.")

    async def _handle_book_session(
        self, intent_result, state,
        db: Session, client_store: ClientStore, conv_store: ConversationStore,
    ) -> None:
        from utils.time_utils import parse_datetime
        entities = intent_result.entities
        client_name = entities.get("client_name", "")
        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None
        if not client:
            await self._messaging_client.send_to_admin(
                f"Couldn't find a client named '{client_name}'. Try introducing them first."
            )
            return

        date_str = entities.get("date", "")
        time_str = entities.get("time", "")
        if not date_str or not time_str:
            await self._messaging_client.send_to_admin("What date and time should I book?")
            return

        try:
            slot = parse_datetime(date_str, time_str)
        except ValueError:
            await self._messaging_client.send_to_admin("Couldn't parse that time. Try something like 'Monday at 8am'.")
            return

        conflict = await asyncio.to_thread(
            check_slot_conflict,
            requested_at=slot.isoformat(),
            duration_mins=60,
            requesting_client_id=client.id,
        )
        if "error" in conflict:
            await self._messaging_client.send_to_admin("Couldn't check availability. Try again.")
            return

        status = conflict.get("status")

        if status == "FREE":
            result = await asyncio.to_thread(
                book_session,
                client_id=client.id,
                scheduled_at=slot.isoformat(),
                duration_mins=60,
            )
            if "error" in result:
                await self._messaging_client.send_to_admin(f"Can't book that slot - {result['error']}")
                return
            await self._messaging_client.send_to_admin(
                f"Done - {client.name} is booked for {slot.strftime('%A %b %d at %I:%M %p')}."
            )

        elif status == "ALTERNATIVES":
            raw_slots = conflict.get("slots") or []
            alt_strs = [datetime.fromisoformat(s).strftime("%I:%M %p") for s in raw_slots[:3]]
            conv_store.update_context(self._provider.phone_number, {
                "pending_booking": {
                    "client_id": client.id,
                    "slot": slot.isoformat(),
                    "alternatives": raw_slots[:3],
                }
            })
            await self._messaging_client.send_to_admin(
                f"{slot.strftime('%A')} {slot.strftime('%I:%M %p')} is taken. "
                f"I have {', '.join(alt_strs)} free - want to offer {client.name} one of those?"
            )

        elif status == "SWAP_POSSIBLE":
            raw_alts = conflict.get("blocking_alternatives") or []
            alt_strs = [datetime.fromisoformat(s).strftime("%I:%M %p") for s in raw_alts[:3]]
            blocking_name = conflict.get("blocking_client_name", "another client")
            conv_store.update_context(self._provider.phone_number, {
                "pending_swap": {
                    "requesting_client_id": client.id,
                    "blocking_client_id": conflict.get("blocking_client_id"),
                    "requested_slot": slot.isoformat(),
                    "blocking_alternatives": raw_alts[:3],
                }
            })
            await self._messaging_client.send_to_admin(
                f"{slot.strftime('%A')} {slot.strftime('%I:%M %p')} is {blocking_name}'s slot. "
                f"I have {', '.join(alt_strs)} free - want to offer {client.name} one of those?"
            )

        else:
            await self._messaging_client.send_to_admin(
                f"No availability on {slot.strftime('%A %b %d')} at all. Try a different day."
            )

    async def _handle_cancel_session(
        self, intent_result, db: Session,
        client_store: ClientStore, session_store: SessionStore,
    ) -> None:
        from utils.time_utils import parse_date
        entities = intent_result.entities
        client_name = entities.get("client_name", "")
        date_str = entities.get("date", "")
        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None

        if not client:
            await self._messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
            return

        upcoming = session_store.get_upcoming_for_client(client.id)
        if not upcoming:
            await self._messaging_client.send_to_admin(f"{client.name} has no upcoming sessions.")
            return

        session = upcoming[0]
        if date_str:
            target_date = parse_date(date_str)
            for s in upcoming:
                if s.scheduled_at.date() == target_date:
                    session = s
                    break

        result = await asyncio.to_thread(cancel_session, session_id=session.id)
        if "error" in result:
            await self._messaging_client.send_to_admin(f"Couldn't cancel that session: {result['error']}")
            return

        await self._messaging_client.send_to_admin(
            f"Cancelled {client.name}'s session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}."
        )

    async def _handle_reschedule_session(
        self, intent_result, state,
        db: Session, client_store: ClientStore, session_store: SessionStore, conv_store: ConversationStore,
    ) -> None:
        from utils.time_utils import parse_datetime
        entities = intent_result.entities
        client_name = entities.get("client_name", "")
        date_str = entities.get("date", "")
        time_str = entities.get("time", "")
        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None

        if not client:
            await self._messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
            return

        upcoming = session_store.get_upcoming_for_client(client.id)
        if not upcoming:
            await self._messaging_client.send_to_admin(f"{client.name} has no upcoming sessions to reschedule.")
            return

        if not date_str or not time_str:
            conv_store.update_context(self._provider.phone_number, {
                "pending_reschedule": {"session_id": upcoming[0].id}
            })
            await self._messaging_client.send_to_admin(f"What's the new time for {client.name}?")
            return

        try:
            new_slot = parse_datetime(date_str, time_str)
        except ValueError:
            await self._messaging_client.send_to_admin("Couldn't parse that time. Try 'Monday at 10am'.")
            return

        result = await asyncio.to_thread(
            reschedule_session,
            session_id=upcoming[0].id,
            new_time=new_slot.isoformat(),
        )
        if "error" in result:
            await self._messaging_client.send_to_admin(f"Couldn't reschedule: {result['error']}")
            return

        await self._messaging_client.send_to_admin(
            f"Rescheduled {client.name} to {new_slot.strftime('%A %b %d at %I:%M %p')}."
        )

    async def _handle_admin_confirm(
        self, intent_result, state,
        db: Session, client_store: ClientStore, session_store: SessionStore, conv_store: ConversationStore,
    ) -> None:
        context = state.context

        if context.get("pending_swap"):
            swap = context["pending_swap"]
            blocking_client = client_store.get(swap["blocking_client_id"])
            blocking_alts = swap.get("blocking_alternatives", [])
            if blocking_alts and blocking_client:
                new_slot = datetime.fromisoformat(blocking_alts[0])
                old_sessions = session_store.get_upcoming_for_client(blocking_client.id)
                if old_sessions:
                    await asyncio.to_thread(
                        reschedule_session,
                        session_id=old_sessions[0].id,
                        new_time=new_slot.isoformat(),
                    )
                blocking_history = conv_store.get_history(blocking_client.phone_number)
                swap_msg = await generate_response(
                    situation=f"Ask {blocking_client.name} if they can shift their session to {new_slot.strftime('%A at %I:%M %p')} instead. Say something came up on our end. Do not mention any other client's name.",
                    recipient=blocking_client.name,
                    provider_name=self._provider.name,
                    business_type=self._provider.business_type,
                    history=blocking_history,
                    client_profile=build_client_profile(blocking_client),
                )
                await self._messaging_client.send_to_phone(blocking_client.phone_number, swap_msg)
                conv_store.clear_context(self._provider.phone_number)
                await self._messaging_client.send_to_admin(
                    f"Asked {blocking_client.name} to move to {new_slot.strftime('%I:%M %p')}."
                )
            return

        if context.get("pending_booking"):
            booking = context["pending_booking"]
            slot = datetime.fromisoformat(booking["slot"])
            client = client_store.get(booking["client_id"])
            if client:
                result = await asyncio.to_thread(
                    book_session,
                    client_id=client.id,
                    scheduled_at=slot.isoformat(),
                    duration_mins=60,
                )
                conv_store.clear_context(self._provider.phone_number)
                if "error" in result:
                    await self._messaging_client.send_to_admin(f"Can't book that slot - {result['error']}")
                    return
                await self._messaging_client.send_to_admin(
                    f"Done - {client.name} booked for {slot.strftime('%A %b %d at %I:%M %p')}."
                )
            return

        await self._messaging_client.send_to_admin("Got it.")

    async def _handle_proactive_message(
        self, intent_result, db: Session,
        client_store: ClientStore, conv_store: ConversationStore,
    ) -> None:
        entities = intent_result.entities
        client_name = entities.get("client_name") or ""
        message_to_send = entities.get("message_to_send") or ""
        phone = (entities.get("phone_number") or "").strip()

        client = client_store.get_by_name(client_name, self._provider.id) if client_name else None

        if not client:
            if phone:
                existing = client_store.get_by_phone(phone)
                if existing:
                    client = existing
                else:
                    await self._messaging_client.send_to_admin(
                        f"I don't see a '{client_name}' in my contacts. "
                        f"Looks like they might be new - want me to add them at {phone} and reach out? "
                        f"Reply with what I should say, or say 'add {client_name} {phone}' to introduce them first."
                    )
                    return
            else:
                await self._messaging_client.send_to_admin(
                    f"I don't see a '{client_name}' in my contacts. "
                    f"New client? Give me their phone number and I'll add them."
                )
                return

        if not message_to_send:
            await self._messaging_client.send_to_admin(f"What should I tell {client.name}?")
            return

        outbound = await generate_response(
            situation=f"Send this message to {client.name} on behalf of {self._provider.name}: {message_to_send}",
            recipient=client.name,
            provider_name=self._provider.name,
            business_type=self._provider.business_type,
        )
        await self._messaging_client.send_to_phone(client.phone_number, outbound)

        # If message references a slot, set pending_booking for client's next yes
        _date_hint = entities.get("date") or ""
        _time_hint = entities.get("time") or ""
        if _date_hint and _time_hint:
            try:
                from utils.time_utils import parse_datetime
                slot = parse_datetime(_date_hint, _time_hint)
                conv_store.get_or_create(client.phone_number, "client")
                conv_store.update_context(client.phone_number, {
                    "pending_booking": {"slot": slot.isoformat(), "client_id": client.id, "alternatives": []}
                })
            except Exception:
                pass

        await self._messaging_client.send_to_admin(f"Sent to {client.name}.")

    async def _summarize_handoff(
        self, target_phone: str, db: Session,
        conv_store: ConversationStore, client_store: ClientStore,
    ) -> None:
        client = client_store.get_by_phone(target_phone)
        client_name = client.name if client else target_phone
        history = conv_store.get_history(target_phone)

        if not history:
            return

        history_text = "\n".join(
            f"{'You' if t['role'] == 'donna' else client_name}: {t['content']}"
            for t in history[-20:]
        )

        situation = (
            f"You (the AI assistant Donna) just finished relaying a live conversation between "
            f"{self._provider.name} and their client {client_name}. "
            f"Here is the conversation:\n{history_text}\n\n"
            f"Summarize in 2-3 sentences what was discussed and what {client_name} wants. "
            f"Then list any clear action items (e.g. book a session, follow up, send info). "
            f"If booking was discussed, ask {self._provider.name} if they want you to go ahead and book it. "
            f"Be direct and brief."
        )
        summary = await generate_response(
            situation=situation,
            recipient=self._provider.name,
            provider_name=self._provider.name,
            business_type=self._provider.business_type,
        )
        await self._messaging_client.send_to_admin(summary)
