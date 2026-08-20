import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.orm import Client, Provider
from models.schemas import IntentResult
from db.redis_client import get_redis
from orchestrator.channels import (
    STATE_AGENT_REGISTRY, STATE_SESSION, STATE_LAST_DONNA, STATE_TIMEOUT,
)
from intelligence.intent_parser import parse_intent
from intelligence.judge import evaluate as judge_evaluate
from intelligence.judge_rules import NEW_CLIENT_STATUSES
from intelligence.response_generator import generate_response
from intelligence.context_manager import (
    summarize_conversation, trim_history,
    should_summarize, build_context_from_summary,
)
from firewall.input_guard import scan_input
from firewall.output_guard import scan_output
from donna_mcp.tools.scheduling import (
    book_session, cancel_session, reschedule_session,
    get_free_slots, get_upcoming_sessions, check_slot_conflict,
)
from donna_mcp.tools.clients import create_client, update_client
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from store.session_store import SessionStore
from utils.profile import build_client_profile

logger = logging.getLogger(__name__)

_AFFIRMATIVES = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "sounds good", "perfect",
    "great", "confirmed", "confirm", "do it", "go ahead", "yup", "definitely"
}
_NEGATIVES = {
    "no", "nope", "cancel", "never mind", "nevermind", "don't", "dont",
    "no thanks", "not anymore", "skip it"
}
HANDOFF_TRIGGERS = [
    "frustrated", "not happy", "speak to someone", "talk to a person",
    "real person", "talk to kaushik", "speak to kaushik", "human",
    "can i speak to", "can i talk to",
]


class ClientAgent:
    def __init__(
        self,
        phone: str,
        client: Client | None,
        provider: Provider,
        messaging_client,
        business_config: dict,
    ):
        self.phone = phone
        self.client = client
        self.provider = provider
        self._messaging_client = messaging_client
        self._business_config = business_config
        self._history: list[dict] = []
        self._turn_count = 0
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._last_tool_calls: list[str] = []

    def load_summary(self, summary: str) -> None:
        self._history = build_context_from_summary(summary)

    async def handle_message(self, text: str, db: Session) -> None:
        try:
            await self._handle_message_inner(text, db)
        except Exception as e:
            logger.exception(f"agent.handle_message unhandled error for {self.phone}: {e}")
            try:
                conv_store = ConversationStore(db)
                await self._send("Something went wrong - want to try again?", conv_store)
            except Exception:
                pass

    async def _handle_message_inner(self, text: str, db: Session) -> None:
        conv_store = ConversationStore(db)
        session_store = SessionStore(db)
        client_store = ClientStore(db)

        if self.client is None:
            self.client = client_store.get_by_phone(self.phone)

        state = conv_store.get_or_create(self.phone, "client")

        # --- Step 1: Input guard (clients only, admin is trusted) ---
        firewall_result = scan_input(message=text, phone=self.phone, is_admin=False)
        if firewall_result.action != "pass":
            await self._send(
                firewall_result.redirect_message or "I didn't quite catch that. Want to try again?",
                conv_store,
            )
            return

        sanitized = firewall_result.sanitized_input or text

        # --- Step 2: Pre-parse checks (preserve V1 logic exactly) ---

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

        _lower_strip = sanitized.lower().strip()
        _has_pending = state.context.get("pending_booking") or state.context.get("pending_reschedule")
        if _has_pending and _lower_strip in _AFFIRMATIVES:
            intent_result = IntentResult(intent="CONFIRM", entities={}, confidence=1.0)
        elif _has_pending and _lower_strip in _NEGATIVES:
            intent_result = IntentResult(intent="DECLINE", entities={}, confidence=1.0)
        else:
            # --- Step 3: Parse intent ---
            intent_result = await parse_intent(
                message=sanitized,
                role="client",
                context=state.context,
                last_donna_message=state.last_donna_message or "",
                history=self._history,
            )

        state = conv_store.get_by_phone(self.phone) or state
        self._turn_count += 1
        conv_store.update(self.phone, {"turn_count": self._turn_count})

        # --- Step 4: Judge ---
        is_new_client = self.client.status in NEW_CLIENT_STATUSES if self.client else True

        judge_result = await judge_evaluate(
            intent_result=intent_result,
            role="client",
            turn_count=self._turn_count,
            context=state.context if state else {},
            client_status=self.client.status if self.client else "unknown",
            is_new_client=is_new_client,
        )

        if self._turn_count >= 5 and intent_result.intent == "UNKNOWN":
            if self.client:
                from orchestrator.handoff import trigger_dynamic_handoff
                await trigger_dynamic_handoff(
                    self.client, self.provider, self._messaging_client, db, conv_store
                )
            return

        if judge_result.decision == "escalate_to_admin":
            if self.client:
                from orchestrator.handoff import trigger_dynamic_handoff
                await trigger_dynamic_handoff(
                    self.client, self.provider, self._messaging_client, db, conv_store
                )
            return

        # --- Step 5: Intent dispatch ---
        self._last_tool_calls = []
        self._current_sanitized = sanitized
        response = await self._dispatch(
            intent_result, state, db, conv_store, session_store, client_store,
        )

        if not response:
            return

        # --- Step 6: Output guard ---
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

        # --- Step 7: Send + update state ---
        await self._send(response, conv_store)
        self._history.append({"role": "user", "content": sanitized})
        self._history.append({"role": "donna", "content": response})

        if should_summarize(self._history) and self.client:
            summary = await summarize_conversation(
                self._history,
                client_name=self.client.name,
                provider_name=self.provider.name,
            )
            if summary:
                self._history = trim_history(self._history, summary)
                try:
                    r = get_redis()
                    r.set(STATE_SESSION.format(phone=self.phone), summary, ex=7 * 24 * 3600)
                except Exception as e:
                    logger.warning(f"agent.summary_redis_write failed: {e}")

        try:
            r = get_redis()
            timeout_mins = self._business_config.get("conversation_timeout_mins", 5)
            r.set(STATE_TIMEOUT.format(phone=self.phone), "1", ex=timeout_mins * 60)
        except Exception as e:
            logger.warning(f"agent.timeout_key failed: {e}")

        # --- Step 8: Conversation end check ---
        state = conv_store.get_by_phone(self.phone)
        await self._check_conversation_end(intent_result, state, db, conv_store)

    async def _send(self, text: str, conv_store: ConversationStore) -> None:
        await self._messaging_client.send_to_phone(self.phone, text)
        conv_store.update_last_donna_message(self.phone, text)
        try:
            r = get_redis()
            r.set(STATE_LAST_DONNA.format(phone=self.phone), text, ex=24 * 3600)
        except Exception as e:
            logger.warning(f"agent._send redis failed: {e}")

    async def _check_conversation_end(
        self,
        intent_result: IntentResult,
        state,
        db: Session,
        conv_store: ConversationStore,
    ) -> None:
        terminal_intents = {"CANCEL_REQUEST", "BOOK_REQUEST", "RESCHEDULE_REQUEST"}
        has_pending = bool(
            state and (
                state.context.get("pending_booking") or
                state.context.get("pending_reschedule")
            )
        ) if state else False

        ends_now = (
            intent_result.intent == "INTENT_GOODBYE" or
            (intent_result.intent in terminal_intents and not has_pending)
        )
        if ends_now:
            await self._finalize_conversation(db, conv_store)

    async def _finalize_conversation(self, db: Session, conv_store: ConversationStore) -> None:
        if self._history and self.client:
            summary = await summarize_conversation(
                self._history,
                client_name=self.client.name,
                provider_name=self.provider.name,
            )
            if summary:
                try:
                    r = get_redis()
                    r.set(STATE_SESSION.format(phone=self.phone), summary, ex=7 * 24 * 3600)
                except Exception as e:
                    logger.warning(f"agent.finalize redis failed: {e}")
                try:
                    from models.orm import ConversationSummary
                    db_summary = ConversationSummary(
                        phone_number=self.phone,
                        summary=summary,
                        turn_count=self._turn_count,
                        session_end=datetime.now(timezone.utc),
                    )
                    db.add(db_summary)
                    db.commit()
                except Exception as e:
                    logger.warning(f"agent.finalize db_write failed: {e}")

        try:
            r = get_redis()
            r.hdel(STATE_AGENT_REGISTRY, self.phone)
            r.delete(STATE_TIMEOUT.format(phone=self.phone))
        except Exception as e:
            logger.warning(f"agent.finalize registry cleanup failed: {e}")
        logger.info(f"agent.finalized: {self.phone} ({self._turn_count} turns)")

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    async def _dispatch(
        self,
        intent_result: IntentResult,
        state,
        db: Session,
        conv_store: ConversationStore,
        session_store: SessionStore,
        client_store: ClientStore,
    ) -> str | None:
        if self.client is None:
            await self._handle_cold_inbound(state, db, conv_store)
            return None

        client = self.client
        history = self._history
        client_profile = build_client_profile(client)
        intent = intent_result.intent

        def gkw(**extra):
            return dict(
                recipient=client.name,
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                history=history,
                client_profile=client_profile,
                **extra,
            )

        if intent == "INQUIRY_SERVICES":
            config = self.provider.business_config or {}
            services_desc = config.get("services", f"1-on-1 {self.provider.business_type} sessions")
            return await generate_response(
                situation=f"Client asked what services are offered. Services: {services_desc}.",
                **gkw(),
            )

        elif intent == "INQUIRY_PRICING":
            config = self.provider.business_config or {}
            pricing = config.get("pricing", "Please contact us for pricing details.")
            return await generate_response(
                situation=f"Client asked about pricing. Pricing info: {pricing}.",
                **gkw(),
            )

        elif intent == "INQUIRY_AVAILABILITY":
            upcoming = session_store.get_upcoming_for_client(client.id)
            date_str = intent_result.entities.get("date", "")
            if upcoming and not date_str:
                session_strs = [s.scheduled_at.strftime("%A %b %d at %I:%M %p") for s in upcoming[:3]]
                situation = f"Client asked about their sessions. Their upcoming booked sessions: {', '.join(session_strs)}. Tell them their schedule."
            else:
                from utils.time_utils import parse_date
                target_date = parse_date(date_str or "today")
                slots = session_store.get_free_slots(self.provider.id, target_date, 60, self.provider)
                if slots:
                    slot_strs = [s.strftime("%I:%M %p") for s in slots[:5]]
                    situation = f"Client asked about availability on {target_date.strftime('%A %b %d')}. Available slots: {', '.join(slot_strs)}."
                else:
                    situation = f"Client asked about availability on {target_date.strftime('%A %b %d')}. No open slots that day."
            return await generate_response(situation=situation, **gkw())

        elif intent == "BOOK_REQUEST":
            return await self._handle_book_request(
                intent_result.entities, state, history, client_profile, conv_store,
            )

        elif intent == "RESCHEDULE_REQUEST":
            return await self._handle_reschedule(
                intent_result, state, history, client_profile, session_store, conv_store,
            )

        elif intent == "CANCEL_REQUEST":
            return await self._handle_cancel(
                intent_result, history, client_profile, session_store, conv_store,
            )

        elif intent == "CONFIRM":
            state = conv_store.get_by_phone(client.phone_number) or state
            return await self._handle_confirm(
                intent_result, state, history, client_profile, session_store, conv_store,
            )

        elif intent == "DECLINE":
            state = conv_store.get_by_phone(client.phone_number) or state
            had_reschedule = bool(state and state.context.get("pending_reschedule"))
            had_booking = bool(state and state.context.get("pending_booking"))
            conv_store.clear_context(client.phone_number)
            if had_reschedule:
                upcoming = session_store.get_upcoming_for_client(client.id)
                slot_str = upcoming[0].scheduled_at.strftime("%A at %I:%M %p") if upcoming else "your current slot"
                situation = f"Client decided not to reschedule - they want to keep {slot_str}. Confirm their session stays as is."
            elif had_booking:
                situation = "Client declined the booking offer. Ask if there's another time that works."
            else:
                situation = "Client declined or said no. Acknowledge briefly and ask if there's anything else they need."
            return await generate_response(situation=situation, **gkw())

        elif intent == "HUMAN_REQUEST":
            from orchestrator.handoff import trigger_explicit_handoff_from_client
            await trigger_explicit_handoff_from_client(
                client, self.provider, self._messaging_client, db, conv_store
            )
            return None

        else:
            return await generate_response(
                situation=f"Client sent an unclear message. Ask one clarifying question.",
                **gkw(),
            )

    # -------------------------------------------------------------------------
    # Cold inbound
    # -------------------------------------------------------------------------

    async def _handle_cold_inbound(
        self,
        state,
        db: Session,
        conv_store: ConversationStore,
    ) -> None:
        phone = self.phone
        provider = self.provider

        if state.context.get("awaiting_name"):
            name = state.context.get("_last_text", "").strip() or "there"
            # We need the raw text here — passed via context by handle_message
            # Actually we need to get it from the last message; use state.context["_pending_name"]
            # The text was stored before dispatch; retrieve it
            name = conv_store.get_by_phone(phone)
            # fallback: use what we have
            name_text = getattr(state, "_dispatch_text", "there")
            # Actually: _handle_cold_inbound is called from _dispatch which has no text param.
            # Store the sanitized text in state before calling _dispatch.
            # We access it via a private attr set on self.
            name_text = getattr(self, "_current_sanitized", "there").strip()

            result = await asyncio.to_thread(
                create_client,
                name=name_text,
                phone_number=phone,
                status="cold_lead",
            )
            if "error" in result:
                logger.error(f"agent.cold_inbound create_client failed: {result['error']}")
                await self._send("Sorry, something went wrong on my end — try again in a moment?", conv_store)
                return

            client_store = ClientStore(db)
            new_client = client_store.get_by_phone(phone)
            ctx = dict(state.context)
            ctx.pop("awaiting_name", None)
            ctx["client_created"] = True
            ctx.pop("intent_after_name", None)
            conv_store.update(phone, {"context": ctx, "client_id": new_client.id})
            self.client = new_client

            welcome = await generate_response(
                situation=f"New client just gave their name: {name_text}. Welcome them warmly and ask how you can help.",
                recipient=name_text,
                provider_name=provider.name,
                business_type=provider.business_type,
            )
            await self._send(welcome, conv_store)
            return

        if (state.turn_count or 0) == 0:
            conv_store.update(phone, {"turn_count": 1})
            greeting = await generate_response(
                situation=f"New person texted for the first time. Greet them as {provider.name}'s assistant and ask how you can help.",
                recipient="there",
                provider_name=provider.name,
                business_type=provider.business_type,
            )
            await self._send(greeting, conv_store)
            return

        intent_result = await parse_intent(
            message=getattr(self, "_current_sanitized", ""),
            role="client",
            context=state.context,
            last_donna_message=state.last_donna_message or "",
        )

        turn_count = (state.turn_count or 0) + 1
        conv_store.update(phone, {"turn_count": turn_count})

        if intent_result.intent == "BOOK_REQUEST":
            conv_store.update_context(phone, {
                "awaiting_name": True,
                "intent_after_name": "BOOK_REQUEST",
            })
            response = await generate_response(
                situation="Cold inbound wants to book but hasn't given their name. Ask for their name first.",
                recipient="there",
                provider_name=provider.name,
                business_type=provider.business_type,
            )
            await self._send(response, conv_store)
            return

        config = provider.business_config or {}
        if intent_result.intent == "INQUIRY_SERVICES":
            services_desc = config.get("services", f"1-on-1 {provider.business_type} sessions")
            situation = f"Prospect asked what services are offered. Services: {services_desc}."
        elif intent_result.intent == "INQUIRY_PRICING":
            pricing = config.get("pricing", "Contact us for pricing details.")
            situation = f"Prospect asked about pricing. Info: {pricing}."
        else:
            situation = f"Unknown cold inbound message. Respond helpfully and warmly."

        response = await generate_response(
            situation=situation,
            recipient="there",
            provider_name=provider.name,
            business_type=provider.business_type,
        )
        await self._send(response, conv_store)

    # -------------------------------------------------------------------------
    # Intent handlers
    # -------------------------------------------------------------------------

    async def _handle_book_request(
        self,
        entities: dict,
        state,
        history: list,
        client_profile: str,
        conv_store: ConversationStore,
    ) -> str:
        from utils.time_utils import parse_datetime
        client = self.client

        def gkw(**extra):
            return dict(
                recipient=client.name,
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                history=history,
                client_profile=client_profile,
                **extra,
            )

        date_str = entities.get("date", "")
        time_str = entities.get("time", "")

        if not date_str or not time_str:
            return await generate_response(
                situation="Client wants to book but didn't specify date/time. Ask what date and time works for them.",
                **gkw(),
            )

        try:
            slot = parse_datetime(date_str, time_str)
        except ValueError:
            return await generate_response(
                situation="Client gave an unclear time for booking. Ask them to clarify the date and time.",
                **gkw(),
            )

        conflict = await asyncio.to_thread(
            check_slot_conflict,
            requested_at=slot.isoformat(),
            duration_mins=60,
            requesting_client_id=client.id,
        )
        if "error" in conflict:
            return await generate_response(
                situation="Could not check availability. Ask client to try a different time.",
                **gkw(),
            )

        status = conflict.get("status")

        if status == "FREE":
            if self.provider.auto_book:
                self._last_tool_calls.append("book_session")
                book_result = await asyncio.to_thread(
                    book_session,
                    client_id=client.id,
                    scheduled_at=slot.isoformat(),
                    duration_mins=60,
                )
                if "error" in book_result:
                    return await generate_response(
                        situation="That slot just got taken. Apologize and ask what other time works.",
                        **gkw(),
                    )
                await self._messaging_client.send_to_admin(
                    f"{client.name} booked {slot.strftime('%A %b %d at %I:%M %p')}. Added to your schedule."
                )
                return await generate_response(
                    situation=f"Client booked {slot.strftime('%A %b %d at %I:%M %p')}. Confirm the booking.",
                    **gkw(),
                )
            else:
                conv_store.update_context(client.phone_number, {
                    "pending_booking": {"slot": slot.isoformat(), "client_id": client.id, "alternatives": []}
                })
                return await generate_response(
                    situation=f"{slot.strftime('%A at %I:%M %p')} is available. Ask client to confirm.",
                    **gkw(),
                )

        elif status in ("ALTERNATIVES", "SWAP_POSSIBLE"):
            raw_slots = conflict.get("slots") or conflict.get("blocking_alternatives") or []
            alt_strs = [datetime.fromisoformat(s).strftime("%A at %I:%M %p") for s in raw_slots[:3]]
            return await generate_response(
                situation=f"{slot.strftime('%A at %I:%M %p')} is not available. Offer these alternatives: {', '.join(alt_strs)}.",
                **gkw(),
            )

        else:
            return await generate_response(
                situation=f"No availability on {slot.strftime('%A %b %d')}. Apologize and ask about other days.",
                **gkw(),
            )

    async def _handle_reschedule(
        self,
        intent_result: IntentResult,
        state,
        history: list,
        client_profile: str,
        session_store: SessionStore,
        conv_store: ConversationStore,
    ) -> str:
        from utils.time_utils import parse_datetime, parse_date
        client = self.client

        def gkw(**extra):
            return dict(
                recipient=client.name,
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                history=history,
                client_profile=client_profile,
                **extra,
            )

        upcoming = session_store.get_upcoming_for_client(client.id)
        if not upcoming:
            return await generate_response(
                situation="Client wants to reschedule but has no upcoming sessions.",
                **gkw(),
            )

        entities = intent_result.entities
        date_str = entities.get("date") or ""
        time_str = entities.get("time") or ""

        existing_pending = state.context.get("pending_reschedule", {})
        if not date_str and existing_pending.get("target_date"):
            date_str = existing_pending["target_date"]

        if not date_str or not time_str:
            session = upcoming[0]
            pending: dict = {"session_id": existing_pending.get("session_id", session.id)}
            if date_str:
                pending["target_date"] = parse_date(date_str).isoformat()
            elif existing_pending.get("target_date"):
                pending["target_date"] = existing_pending["target_date"]
            conv_store.update_context(client.phone_number, {"pending_reschedule": pending})
            return await generate_response(
                situation=f"Client wants to reschedule their session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}. Ask what new time works.",
                **gkw(),
            )

        try:
            new_slot = parse_datetime(date_str, time_str)
        except ValueError:
            return await generate_response(
                situation="Client gave unclear reschedule time. Ask to clarify.",
                **gkw(),
            )

        session_id = state.context.get("pending_reschedule", {}).get("session_id", upcoming[0].id)
        result = await asyncio.to_thread(
            reschedule_session,
            session_id=session_id,
            new_time=new_slot.isoformat(),
        )
        if "error" in result:
            conflict_info = result.get("conflict", {})
            alt_strs = []
            for s in (conflict_info.get("slots") or conflict_info.get("blocking_alternatives") or [])[:3]:
                alt_strs.append(datetime.fromisoformat(s).strftime("%A at %I:%M %p"))
            situation = (
                f"Couldn't reschedule to {new_slot.strftime('%A at %I:%M %p')} - that slot is taken."
                + (f" Offer these alternatives: {', '.join(alt_strs)}." if alt_strs else " Ask what other time works.")
            )
            return await generate_response(situation=situation, **gkw())

        conv_store.clear_context(client.phone_number)
        await self._messaging_client.send_to_admin(
            f"{client.name} rescheduled to {new_slot.strftime('%A %b %d at %I:%M %p')}."
        )
        return await generate_response(
            situation=f"You've rescheduled the client's session to {new_slot.strftime('%A %b %d at %I:%M %p')}. Tell them it's all set.",
            **gkw(),
        )

    async def _handle_cancel(
        self,
        intent_result: IntentResult,
        history: list,
        client_profile: str,
        session_store: SessionStore,
        conv_store: ConversationStore,
    ) -> str:
        client = self.client

        def gkw(**extra):
            return dict(
                recipient=client.name,
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                history=history,
                client_profile=client_profile,
                **extra,
            )

        upcoming = session_store.get_upcoming_for_client(client.id)
        if not upcoming:
            return await generate_response(
                situation="Client wants to cancel but has no upcoming sessions.",
                **gkw(),
            )

        session = upcoming[0]
        result = await asyncio.to_thread(cancel_session, session_id=session.id)
        if "error" in result:
            return await generate_response(
                situation=f"Could not cancel the session. Apologize and suggest they try again.",
                **gkw(),
            )

        conv_store.clear_context(client.phone_number)
        await self._messaging_client.send_to_admin(
            f"{client.name} cancelled their {session.scheduled_at.strftime('%A %b %d at %I:%M %p')} session."
        )
        return await generate_response(
            situation=f"Cancelled client's session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}. Confirm cancellation.",
            **gkw(),
        )

    async def _handle_confirm(
        self,
        intent_result: IntentResult,
        state,
        history: list,
        client_profile: str,
        session_store: SessionStore,
        conv_store: ConversationStore,
    ) -> str | None:
        from utils.time_utils import parse_datetime
        client = self.client
        context = state.context if state else {}

        def gkw(**extra):
            return dict(
                recipient=client.name,
                provider_name=self.provider.name,
                business_type=self.provider.business_type,
                history=history,
                client_profile=client_profile,
                **extra,
            )

        if context.get("pending_reschedule"):
            reschedule = context["pending_reschedule"]
            session_id = reschedule.get("session_id")
            date_ent = intent_result.entities.get("date", "") or reschedule.get("target_date", "")
            time_ent = intent_result.entities.get("time", "")
            if date_ent or time_ent:
                try:
                    new_slot = parse_datetime(date_ent, time_ent)
                    upcoming = session_store.get_upcoming_for_client(client.id)
                    target_id = session_id if session_id else (upcoming[0].id if upcoming else None)
                    if target_id:
                        result = await asyncio.to_thread(
                            reschedule_session,
                            session_id=target_id,
                            new_time=new_slot.isoformat(),
                        )
                        if "error" not in result:
                            conv_store.clear_context(client.phone_number)
                            await self._messaging_client.send_to_admin(
                                f"{client.name} rescheduled to {new_slot.strftime('%A %b %d at %I:%M %p')}."
                            )
                            return await generate_response(
                                situation=f"You've rescheduled the client's session to {new_slot.strftime('%A %b %d at %I:%M %p')}. Tell them it's all set.",
                                **gkw(),
                            )
                except ValueError:
                    pass
            return await generate_response(
                situation="Client confirmed they want to reschedule but didn't say what time. Ask what new time works for them.",
                **gkw(),
            )

        pending = context.get("pending_booking")
        if pending:
            slot = datetime.fromisoformat(pending["slot"])
            self._last_tool_calls.append("book_session")
            result = await asyncio.to_thread(
                book_session,
                client_id=client.id,
                scheduled_at=slot.isoformat(),
                duration_mins=60,
            )
            if "error" in result:
                conv_store.clear_context(client.phone_number)
                return await generate_response(
                    situation="That slot just got taken by someone else. Apologize and offer to find a new time.",
                    **gkw(),
                )
            conv_store.clear_context(client.phone_number)
            await self._messaging_client.send_to_admin(
                f"{client.name} confirmed {slot.strftime('%A %b %d at %I:%M %p')}. Added to your schedule."
            )
            return await generate_response(
                situation=f"Client confirmed booking for {slot.strftime('%A %b %d at %I:%M %p')}. Confirm and say see you then.",
                **gkw(),
            )

        date_ent = intent_result.entities.get("date") or ""
        time_ent = intent_result.entities.get("time") or ""
        if date_ent or time_ent:
            return await self._handle_book_request(
                intent_result.entities, state, history, client_profile, conv_store,
            )

        response = await generate_response(
            situation="Client confirmed or said yes in a general sense. You have nothing specific pending. Acknowledge warmly and say you'll be in touch if there's anything to follow up on.",
            **gkw(),
        )
        await self._messaging_client.send_to_admin(
            f"{client.name} confirmed something - check if you need to book a session for them."
        )
        return response
