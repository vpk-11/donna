import logging
from datetime import datetime
from sqlalchemy.orm import Session
from models.orm import Client, Provider
from models.schemas import IntentResult
from store.conversation_store import ConversationStore
from store.session_store import SessionStore
from store.provider_store import ProviderStore
from intelligence.intent_parser import parse_intent
from intelligence.response_generator import generate_response
from utils.profile import build_client_profile

_AFFIRMATIVES = {"yes", "yeah", "yep", "sure", "ok", "okay", "sounds good", "perfect",
                 "great", "confirmed", "confirm", "do it", "go ahead", "yup", "definitely"}
_NEGATIVES = {"no", "nope", "cancel", "never mind", "nevermind", "don't", "dont",
              "no thanks", "not anymore", "skip it"}

logger = logging.getLogger(__name__)

HANDOFF_TRIGGERS = [
    "frustrated", "not happy", "speak to someone", "talk to a person",
    "real person", "talk to kaushik", "speak to kaushik", "human",
    "can i speak to", "can i talk to",
]


async def handle_client(text: str, client: Client, messaging_client, db: Session) -> None:
    conv_store = ConversationStore(db)
    provider_store = ProviderStore(db)
    state = conv_store.get_or_create(client.phone_number, "client")
    provider = provider_store.get(client.provider_id)

    if state.handoff_active:
        relay = f"[{client.name}] {text}"
        await messaging_client.send_to_admin(relay)
        return

    lower = text.lower()
    if any(trigger in lower for trigger in HANDOFF_TRIGGERS):
        from core.handoff import trigger_dynamic_handoff
        await trigger_dynamic_handoff(client, provider, messaging_client, db, conv_store)
        return

    history = conv_store.get_history(client.phone_number)
    client_profile = build_client_profile(client)

    # Shortcut: if we're waiting on a yes/no and client gives a plain affirmative/negative,
    # skip the LLM — it reliably misclassifies "yes" as BOOK_REQUEST when booking history exists.
    _lower = text.lower().strip()
    _has_pending = state.context.get("pending_booking") or state.context.get("pending_reschedule")
    if _has_pending and _lower in _AFFIRMATIVES:
        intent_result = IntentResult(intent="CONFIRM", entities={}, confidence=1.0)
    elif _has_pending and _lower in _NEGATIVES:
        intent_result = IntentResult(intent="DECLINE", entities={}, confidence=1.0)
    else:
        intent_result = await parse_intent(
            message=text,
            role="client",
            context=state.context,
            last_donna_message=state.last_donna_message or "",
            history=history,
        )

    state = conv_store.get_by_phone(client.phone_number)
    turn_count = (state.turn_count or 0) + 1
    conv_store.update(client.phone_number, {"turn_count": turn_count})

    if turn_count >= 5 and intent_result.intent == "UNKNOWN":
        from core.handoff import trigger_dynamic_handoff
        await trigger_dynamic_handoff(client, provider, messaging_client, db, conv_store)
        return

    session_store = SessionStore(db)

    intent = intent_result.intent

    def _gen_kwargs():
        return dict(
            recipient=client.name,
            provider_name=provider.name,
            business_type=provider.business_type,
            history=history,
            client_profile=client_profile,
        )

    if intent == "INQUIRY_SERVICES":
        config = provider.business_config or {}
        services_desc = config.get("services", f"1-on-1 {provider.business_type} sessions")
        response = await generate_response(
            situation=f"Client asked what services are offered. Services: {services_desc}.",
            **_gen_kwargs(),
        )
        await messaging_client.send_to_phone(client.phone_number, response)

    elif intent == "INQUIRY_PRICING":
        config = provider.business_config or {}
        pricing = config.get("pricing", "Please contact us for pricing details.")
        response = await generate_response(
            situation=f"Client asked about pricing. Pricing info: {pricing}.",
            **_gen_kwargs(),
        )
        await messaging_client.send_to_phone(client.phone_number, response)

    elif intent == "INQUIRY_AVAILABILITY":
        upcoming = session_store.get_upcoming_for_client(client.id)
        date_str = intent_result.entities.get("date", "")
        if upcoming and not date_str:
            session_strs = [s.scheduled_at.strftime("%A %b %d at %I:%M %p") for s in upcoming[:3]]
            situation = f"Client asked about their sessions. Their upcoming booked sessions: {', '.join(session_strs)}. Tell them their schedule."
        else:
            from utils.time_utils import parse_date
            target_date = parse_date(date_str or "today")
            slots = session_store.get_free_slots(provider.id, target_date, 60, provider)
            if slots:
                slot_strs = [s.strftime("%I:%M %p") for s in slots[:5]]
                situation = f"Client asked about availability on {target_date.strftime('%A %b %d')}. Available slots: {', '.join(slot_strs)}."
            else:
                situation = f"Client asked about availability on {target_date.strftime('%A %b %d')}. No open slots that day."
        response = await generate_response(situation=situation, **_gen_kwargs())
        await messaging_client.send_to_phone(client.phone_number, response)

    elif intent == "BOOK_REQUEST":
        await _handle_client_book_request(client, intent_result.entities, provider, messaging_client, db, session_store, conv_store, history, client_profile)

    elif intent == "RESCHEDULE_REQUEST":
        await _handle_client_reschedule(client, intent_result, provider, state, messaging_client, db, session_store, conv_store, history, client_profile)

    elif intent == "CANCEL_REQUEST":
        await _handle_client_cancel(client, intent_result, provider, messaging_client, db, session_store, conv_store, history, client_profile)

    elif intent == "CONFIRM":
        state = conv_store.get_by_phone(client.phone_number)
        await _handle_confirm(client, intent_result, state, provider, messaging_client, db, session_store, conv_store, history, client_profile)

    elif intent == "DECLINE":
        state = conv_store.get_by_phone(client.phone_number)
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
        response = await generate_response(situation=situation, **_gen_kwargs())
        await messaging_client.send_to_phone(client.phone_number, response)

    elif intent == "HUMAN_REQUEST":
        from core.handoff import trigger_explicit_handoff_from_client
        await trigger_explicit_handoff_from_client(client, provider, messaging_client, db, conv_store)

    else:
        response = await generate_response(
            situation=f"Client sent an unclear message: '{text}'. Ask one clarifying question.",
            **_gen_kwargs(),
        )
        await messaging_client.send_to_phone(client.phone_number, response)


async def handle_cold_inbound(text: str, phone: str, messaging_client, db: Session) -> None:
    conv_store = ConversationStore(db)
    provider_store = ProviderStore(db)
    provider = provider_store.get_first()
    state = conv_store.get_or_create(phone, "client")

    if state.context.get("awaiting_name"):
        name = text.strip()
        from store.client_store import ClientStore
        client_store = ClientStore(db)
        client = client_store.create({
            "provider_id": provider.id,
            "name": name,
            "phone_number": phone,
            "status": "cold_lead",
        })
        ctx = dict(state.context)
        ctx.pop("awaiting_name", None)
        ctx["client_created"] = True
        intent_after = ctx.pop("intent_after_name", None)
        conv_store.update(phone, {"context": ctx, "client_id": client.id})

        welcome = await generate_response(
            situation=f"New client just gave their name: {name}. Welcome them warmly and ask how you can help.",
            recipient=name,
            provider_name=provider.name,
            business_type=provider.business_type,
        )
        await messaging_client.send_to_phone(phone, welcome)
        return

    if state.turn_count == 0:
        conv_store.update(phone, {"turn_count": 1})
        greeting = await generate_response(
            situation=f"New person texted for the first time. Greet them as {provider.name}'s assistant and ask how you can help.",
            recipient="there",
            provider_name=provider.name,
            business_type=provider.business_type,
        )
        await messaging_client.send_to_phone(phone, greeting)
        return

    intent_result = await parse_intent(
        message=text,
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
        await messaging_client.send_to_phone(phone, response)
        return

    from store.client_store import ClientStore
    dummy_client = type("DummyClient", (), {
        "name": "there",
        "phone_number": phone,
        "provider_id": provider.id if provider else 1,
    })()

    if intent_result.intent == "INQUIRY_SERVICES":
        config = provider.business_config or {} if provider else {}
        services_desc = config.get("services", f"1-on-1 {provider.business_type} sessions") if provider else "sessions"
        response = await generate_response(
            situation=f"Prospect asked what services are offered. Services: {services_desc}.",
            recipient="there",
            provider_name=provider.name if provider else "us",
            business_type=provider.business_type if provider else "business",
        )
    elif intent_result.intent == "INQUIRY_PRICING":
        config = provider.business_config or {} if provider else {}
        pricing = config.get("pricing", "Contact us for pricing details.")
        response = await generate_response(
            situation=f"Prospect asked about pricing. Info: {pricing}.",
            recipient="there",
            provider_name=provider.name if provider else "us",
            business_type=provider.business_type if provider else "business",
        )
    else:
        response = await generate_response(
            situation=f"Unknown cold inbound message: '{text}'. Respond helpfully and warmly.",
            recipient="there",
            provider_name=provider.name if provider else "us",
            business_type=provider.business_type if provider else "business",
        )

    await messaging_client.send_to_phone(phone, response)


async def _handle_client_book_request(client, entities, provider, messaging_client, db, session_store, conv_store, history=None, client_profile=None):
    from scheduling.conflict_resolver import resolve_slot
    from utils.time_utils import parse_datetime

    def gkw(**extra):
        return dict(recipient=client.name, provider_name=provider.name,
                    business_type=provider.business_type, history=history, client_profile=client_profile, **extra)

    date_str = entities.get("date", "")
    time_str = entities.get("time", "")

    if not date_str or not time_str:
        response = await generate_response(situation="Client wants to book but didn't specify date/time. Ask what date and time works for them.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    try:
        slot = parse_datetime(date_str, time_str)
    except ValueError:
        response = await generate_response(situation="Client gave an unclear time for booking. Ask them to clarify the date and time.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    result = await resolve_slot(
        provider_id=provider.id, requested_at=slot, duration_mins=60,
        requesting_client_id=client.id, db=db, session_store=session_store,
        client_store=None, provider=provider,
    )

    if result.status == "FREE":
        if provider.auto_book:
            try:
                session_store.create({
                    "provider_id": provider.id, "client_id": client.id,
                    "scheduled_at": slot, "duration_mins": 60,
                    "status": "scheduled", "is_recurring": False,
                })
            except ValueError:
                response = await generate_response(situation="That slot just got taken. Apologize and ask what other time works.", **gkw())
                await messaging_client.send_to_phone(client.phone_number, response)
                return
            response = await generate_response(situation=f"Client booked {slot.strftime('%A %b %d at %I:%M %p')}. Confirm the booking.", **gkw())
            await messaging_client.send_to_phone(client.phone_number, response)
            await messaging_client.send_to_admin(f"{client.name} booked {slot.strftime('%A %b %d at %I:%M %p')}. Added to your schedule.")
        else:
            conv_store.update_context(client.phone_number, {"pending_booking": {"slot": slot.isoformat(), "client_id": client.id, "alternatives": []}})
            response = await generate_response(situation=f"{slot.strftime('%A at %I:%M %p')} is available. Ask client to confirm.", **gkw())
            await messaging_client.send_to_phone(client.phone_number, response)
    elif result.status in ("ALTERNATIVES", "SWAP_POSSIBLE"):
        slots = result.slots or result.blocking_alternatives or []
        alt_strs = [s.strftime("%A at %I:%M %p") for s in slots[:3]]
        response = await generate_response(situation=f"{slot.strftime('%A at %I:%M %p')} is not available. Offer these alternatives: {', '.join(alt_strs)}.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
    else:
        response = await generate_response(situation=f"No availability on {slot.strftime('%A %b %d')}. Apologize and ask about other days.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)


async def _handle_client_reschedule(client, intent_result, provider, state, messaging_client, db, session_store, conv_store, history=None, client_profile=None):
    def gkw(**extra):
        return dict(recipient=client.name, provider_name=provider.name,
                    business_type=provider.business_type, history=history, client_profile=client_profile, **extra)

    upcoming = session_store.get_upcoming_for_client(client.id)
    if not upcoming:
        response = await generate_response(situation="Client wants to reschedule but has no upcoming sessions.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    entities = intent_result.entities
    date_str = entities.get("date") or ""
    time_str = entities.get("time") or ""

    # Fill missing date from stored context before deciding whether to ask
    existing_pending = state.context.get("pending_reschedule", {})
    if not date_str and existing_pending.get("target_date"):
        date_str = existing_pending["target_date"]

    if not date_str or not time_str:
        session = upcoming[0]
        pending: dict = {
            "session_id": existing_pending.get("session_id", session.id),
        }
        if date_str:
            from utils.time_utils import parse_date
            pending["target_date"] = parse_date(date_str).isoformat()
        elif existing_pending.get("target_date"):
            pending["target_date"] = existing_pending["target_date"]
        conv_store.update_context(client.phone_number, {"pending_reschedule": pending})
        response = await generate_response(
            situation=f"Client wants to reschedule their session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}. Ask what new time works.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    from utils.time_utils import parse_datetime
    try:
        new_slot = parse_datetime(date_str, time_str)
    except ValueError:
        response = await generate_response(situation="Client gave unclear reschedule time. Ask to clarify.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    session_id = state.context.get("pending_reschedule", {}).get("session_id", upcoming[0].id)
    session_store.reschedule(session_id, new_slot)
    conv_store.clear_context(client.phone_number)
    response = await generate_response(situation=f"You've rescheduled the client's session to {new_slot.strftime('%A %b %d at %I:%M %p')}. Tell them it's all set.", **gkw())
    await messaging_client.send_to_phone(client.phone_number, response)
    await messaging_client.send_to_admin(f"{client.name} rescheduled to {new_slot.strftime('%A %b %d at %I:%M %p')}.")


async def _handle_client_cancel(client, intent_result, provider, messaging_client, db, session_store, conv_store, history=None, client_profile=None):
    def gkw(**extra):
        return dict(recipient=client.name, provider_name=provider.name,
                    business_type=provider.business_type, history=history, client_profile=client_profile, **extra)

    upcoming = session_store.get_upcoming_for_client(client.id)
    if not upcoming:
        response = await generate_response(situation="Client wants to cancel but has no upcoming sessions.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    session = upcoming[0]
    session_store.cancel(session.id)
    session_store.archive(session.id, reason="cancelled_by_client")
    conv_store.clear_context(client.phone_number)
    response = await generate_response(situation=f"Cancelled client's session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}. Confirm cancellation.", **gkw())
    await messaging_client.send_to_phone(client.phone_number, response)
    await messaging_client.send_to_admin(f"{client.name} cancelled their {session.scheduled_at.strftime('%A %b %d at %I:%M %p')} session.")


async def _handle_confirm(client, intent_result, state, provider, messaging_client, db, session_store, conv_store, history=None, client_profile=None):
    def gkw(**extra):
        return dict(recipient=client.name, provider_name=provider.name,
                    business_type=provider.business_type, history=history, client_profile=client_profile, **extra)

    context = state.context

    if context.get("pending_reschedule"):
        reschedule = context["pending_reschedule"]
        session_id = reschedule.get("session_id")
        date_ent = intent_result.entities.get("date", "") or reschedule.get("target_date", "")
        time_ent = intent_result.entities.get("time", "")
        if date_ent or time_ent:
            from utils.time_utils import parse_datetime
            try:
                new_slot = parse_datetime(date_ent, time_ent)
                upcoming = session_store.get_upcoming_for_client(client.id)
                target_id = session_id if session_id else (upcoming[0].id if upcoming else None)
                if target_id:
                    session_store.reschedule(target_id, new_slot)
                conv_store.clear_context(client.phone_number)
                response = await generate_response(situation=f"You've rescheduled the client's session to {new_slot.strftime('%A %b %d at %I:%M %p')}. Tell them it's all set.", **gkw())
                await messaging_client.send_to_phone(client.phone_number, response)
                await messaging_client.send_to_admin(f"{client.name} rescheduled to {new_slot.strftime('%A %b %d at %I:%M %p')}.")
                return
            except ValueError:
                pass
        response = await generate_response(situation="Client confirmed they want to reschedule but didn't say what time. Ask what new time works for them.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        return

    pending = context.get("pending_booking")

    if pending:
        slot = datetime.fromisoformat(pending["slot"])
        try:
            session_store.create({
                "provider_id": provider.id, "client_id": client.id,
                "scheduled_at": slot, "duration_mins": 60,
                "status": "scheduled", "is_recurring": False,
            })
        except ValueError:
            conv_store.clear_context(client.phone_number)
            response = await generate_response(situation="That slot just got taken by someone else. Apologize and offer to find a new time.", **gkw())
            await messaging_client.send_to_phone(client.phone_number, response)
            return
        conv_store.clear_context(client.phone_number)
        response = await generate_response(situation=f"Client confirmed booking for {slot.strftime('%A %b %d at %I:%M %p')}. Confirm and say see you then.", **gkw())
        await messaging_client.send_to_phone(client.phone_number, response)
        await messaging_client.send_to_admin(f"{client.name} confirmed {slot.strftime('%A %b %d at %I:%M %p')}. Added to your schedule.")
        return

    date_ent = intent_result.entities.get("date") or ""
    time_ent = intent_result.entities.get("time") or ""
    if date_ent or time_ent:
        await _handle_client_book_request(client, intent_result.entities, provider, messaging_client, db, session_store, conv_store, history, client_profile)
        return

    # No pending action and no date/time — client confirmed something conversational.
    # Acknowledge warmly and let admin know in case they need to book anything.
    response = await generate_response(
        situation="Client confirmed or said yes in a general sense. You have nothing specific pending. Acknowledge warmly and say you'll be in touch if there's anything to follow up on.",
        **gkw(),
    )
    await messaging_client.send_to_phone(client.phone_number, response)
    await messaging_client.send_to_admin(f"{client.name} confirmed something — check if you need to book a session for them.")
