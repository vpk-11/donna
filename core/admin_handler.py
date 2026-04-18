import logging
from sqlalchemy.orm import Session
from models.orm import Provider
from store.conversation_store import ConversationStore
from store.provider_store import ProviderStore
from store.client_store import ClientStore
from store.session_store import SessionStore
from intelligence.intent_parser import parse_intent
from intelligence.response_generator import generate_response

logger = logging.getLogger(__name__)


async def handle_admin(text: str, provider: Provider, messaging_client, db: Session) -> None:
    conv_store = ConversationStore(db)
    state = conv_store.get_or_create(provider.phone_number, "admin")

    # Check 1: handoff relay active
    if state.handoff_active and state.handoff_target_phone:
        lower = text.lower().strip()
        if lower in ("done", "donna take over", "donna, take over"):
            conv_store.update(provider.phone_number, {
                "handoff_active": False,
                "handoff_target_phone": None,
            })
            target_state = conv_store.get_by_phone(state.handoff_target_phone)
            if target_state:
                conv_store.update(state.handoff_target_phone, {"handoff_active": False})
            await messaging_client.send_to_admin("Got it - I'm back in control.")
        else:
            relay_msg = f"[{provider.name}] {text}"
            await messaging_client.send_to_phone(state.handoff_target_phone, relay_msg)
        return

    # Check 2: pending dynamic handoff yes/no
    if state.context.get("pending_dynamic_handoff"):
        lower = text.lower().strip()
        affirmatives = {"yes", "yeah", "yep", "sure", "jump in", "i will jump in", "do it"}
        negatives = {"no", "nope", "handle it", "donna handle it", "you handle it"}
        target_name = state.context.get("handoff_target_name", "the client")
        target_phone = state.context.get("handoff_target_phone")

        if lower in affirmatives:
            from core.handoff import start_handoff_from_admin
            await start_handoff_from_admin(provider, target_phone, messaging_client, db, conv_store)
        elif lower in negatives:
            conv_store.clear_context(provider.phone_number)
            await messaging_client.send_to_admin("Got it, I'll keep handling it.")
        else:
            await messaging_client.send_to_admin(
                f"Just to confirm - do you want to jump into the conversation with {target_name}? (yes / no)"
            )
        return

    # Check 3: pending clarification for NEW_CLIENT_INTRO
    if state.context.get("pending_clarification") == "NEW_CLIENT_INTRO":
        from core.admin_handler_actions import handle_new_client_intro_clarification
        await handle_new_client_intro_clarification(text, provider, state, messaging_client, db, conv_store)
        return

    # Parse intent normally
    history = conv_store.get_history(provider.phone_number)
    intent_result = await parse_intent(
        message=text,
        role="admin",
        context=state.context,
        last_donna_message=state.last_donna_message or "",
        history=history,
    )

    client_store = ClientStore(db)
    session_store = SessionStore(db)

    intent = intent_result.intent

    if intent == "CHECK_SCHEDULE":
        await _check_schedule(provider, messaging_client, db, session_store, client_store)
    elif intent == "CHECK_CLIENT_STATUS":
        await _check_client_status(intent_result, provider, messaging_client, db, client_store, session_store, conv_store)
    elif intent == "CLIENT_INFO":
        await _update_client_info(intent_result, provider, messaging_client, db, client_store)
    elif intent == "NEW_CLIENT_INTRO":
        from core.admin_handler_actions import handle_new_client_intro
        await handle_new_client_intro(text, intent_result, provider, state, messaging_client, db, conv_store, client_store)
    elif intent == "BOOK_SESSION":
        await _handle_book_session(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store)
    elif intent == "CANCEL_DAY":
        from scheduling.session_manager import cancel_day
        from utils.time_utils import parse_date
        date_str = intent_result.entities.get("date", "today")
        target_date = parse_date(date_str)
        await cancel_day(provider.id, target_date, messaging_client, db, session_store, client_store)
    elif intent == "CANCEL_SESSION":
        await _handle_cancel_session(intent_result, provider, messaging_client, db, client_store, session_store)
    elif intent == "RESCHEDULE_SESSION":
        await _handle_reschedule_session(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store)
    elif intent == "HANDOFF_REQUEST":
        from core.handoff import start_handoff_from_admin
        target_name = intent_result.entities.get("client_name", "")
        target_client = client_store.get_by_name(target_name, provider.id) if target_name else None
        if target_client:
            await start_handoff_from_admin(provider, target_client.phone_number, messaging_client, db, conv_store)
        else:
            await messaging_client.send_to_admin("Who do you want to jump in with? Give me their name.")
    elif intent == "HANDOFF_DELEGATE":
        conv_store.clear_context(provider.phone_number)
        await messaging_client.send_to_admin("Got it - I'll keep handling it.")
    elif intent == "CONFIRM":
        await _handle_admin_confirm(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store)
    elif intent == "DECLINE":
        conv_store.clear_context(provider.phone_number)
        await messaging_client.send_to_admin("Understood, no problem.")
    else:
        response = await generate_response(
            situation=f"Admin sent an unclear message: '{text}'. Ask for clarification.",
            recipient=provider.name,
            provider_name=provider.name,
            business_type=provider.business_type,
        )
        await messaging_client.send_to_admin(response)


async def _check_schedule(provider, messaging_client, db, session_store, client_store):
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    week_end = today + timedelta(days=7)
    from datetime import datetime as dt
    sessions = (
        db.query(__import__("models.orm", fromlist=["Session"]).Session)
        .filter(
            __import__("models.orm", fromlist=["Session"]).Session.provider_id == provider.id,
            __import__("models.orm", fromlist=["Session"]).Session.status == "scheduled",
            __import__("models.orm", fromlist=["Session"]).Session.scheduled_at >= dt.combine(today, dt.min.time()),
            __import__("models.orm", fromlist=["Session"]).Session.scheduled_at <= dt.combine(week_end, dt.max.time()),
        )
        .order_by(__import__("models.orm", fromlist=["Session"]).Session.scheduled_at)
        .all()
    )
    if not sessions:
        await messaging_client.send_to_admin("No sessions scheduled in the next 7 days.")
        return

    lines = []
    for s in sessions:
        client = client_store.get(s.client_id)
        name = client.name if client else "Unknown"
        time_str = s.scheduled_at.strftime("%a %b %d at %I:%M %p")
        lines.append(f"{name} - {time_str}")

    summary = "\n".join(lines)
    await messaging_client.send_to_admin(f"Upcoming sessions:\n{summary}")


async def _check_client_status(intent_result, provider, messaging_client, db, client_store, session_store, conv_store):
    client_name = intent_result.entities.get("client_name", "")
    client = client_store.get_by_name(client_name, provider.id) if client_name else None
    if not client:
        await messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
        return

    client_state = conv_store.get_by_phone(client.phone_number)
    upcoming = session_store.get_upcoming_for_client(client.id)

    last_msg = client_state.last_donna_message if client_state else "No messages yet"
    upcoming_str = ", ".join(s.scheduled_at.strftime("%a %b %d %I:%M %p") for s in upcoming[:3]) or "None"

    situation = (
        f"Admin asked about client {client.name}. "
        f"Status: {client.status}. "
        f"Last Donna message to them: '{last_msg}'. "
        f"Upcoming sessions: {upcoming_str}. "
        f"Notes: {client.notes or 'none'}. "
        f"Summarize for admin."
    )
    response = await generate_response(
        situation=situation,
        recipient=provider.name,
        provider_name=provider.name,
        business_type=provider.business_type,
    )
    await messaging_client.send_to_admin(response)


async def _update_client_info(intent_result, provider, messaging_client, db, client_store):
    client_name = intent_result.entities.get("client_name", "")
    notes = intent_result.entities.get("notes", "")
    client = client_store.get_by_name(client_name, provider.id) if client_name else None
    if not client:
        await messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
        return
    existing_notes = client.notes or ""
    new_notes = f"{existing_notes}\n{notes}".strip() if existing_notes else notes
    client_store.update(client.id, {"notes": new_notes})
    await messaging_client.send_to_admin(f"Updated notes for {client.name}.")


async def _handle_book_session(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store):
    from scheduling.conflict_resolver import resolve_slot
    from utils.time_utils import parse_datetime, parse_date
    entities = intent_result.entities
    client_name = entities.get("client_name", "")
    client = client_store.get_by_name(client_name, provider.id) if client_name else None
    if not client:
        await messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'. Try introducing them first.")
        return

    date_str = entities.get("date", "")
    time_str = entities.get("time", "")
    if not date_str or not time_str:
        await messaging_client.send_to_admin("What date and time should I book?")
        return

    try:
        slot = parse_datetime(date_str, time_str)
    except ValueError:
        await messaging_client.send_to_admin(f"Couldn't parse that time. Try something like 'Monday at 8am'.")
        return

    result = await resolve_slot(
        provider_id=provider.id,
        requested_at=slot,
        duration_mins=60,
        requesting_client_id=client.id,
        db=db,
        session_store=session_store,
        client_store=client_store,
        provider=provider,
    )

    if result.status == "FREE":
        try:
            session_store.create({
                "provider_id": provider.id,
                "client_id": client.id,
                "scheduled_at": slot,
                "duration_mins": 60,
                "status": "scheduled",
                "is_recurring": False,
            })
        except ValueError as e:
            await messaging_client.send_to_admin(f"Can't book that slot - {e}")
            return
        await messaging_client.send_to_admin(
            f"Done - {client.name} is booked for {slot.strftime('%A %b %d at %I:%M %p')}."
        )
    elif result.status == "ALTERNATIVES":
        alt_strs = [s.strftime("%I:%M %p") for s in (result.slots or [])[:3]]
        await messaging_client.send_to_admin(
            f"{slot.strftime('%A')} {slot.strftime('%I:%M %p')} is taken. "
            f"I have {', '.join(alt_strs)} free - want to offer {client.name} one of those?"
        )
        conv_store.update_context(provider.phone_number, {
            "pending_booking": {
                "client_id": client.id,
                "slot": slot.isoformat(),
                "alternatives": [s.isoformat() for s in (result.slots or [])[:3]],
            }
        })
    elif result.status == "SWAP_POSSIBLE":
        alt_strs = [s.strftime("%I:%M %p") for s in (result.blocking_alternatives or [])[:3]]
        blocking_name = result.blocking_client_name
        await messaging_client.send_to_admin(
            f"{slot.strftime('%A')} {slot.strftime('%I:%M %p')} is {blocking_name}'s slot. "
            f"I have {', '.join(alt_strs)} free - want to offer {client.name} one of those?"
        )
        conv_store.update_context(provider.phone_number, {
            "pending_swap": {
                "requesting_client_id": client.id,
                "blocking_client_id": result.blocking_client_id,
                "requested_slot": slot.isoformat(),
                "blocking_alternatives": [s.isoformat() for s in (result.blocking_alternatives or [])[:3]],
            }
        })
    else:
        await messaging_client.send_to_admin(
            f"No availability on {slot.strftime('%A %b %d')} at all. Try a different day."
        )


async def _handle_cancel_session(intent_result, provider, messaging_client, db, client_store, session_store):
    from utils.time_utils import parse_date, parse_datetime
    entities = intent_result.entities
    client_name = entities.get("client_name", "")
    date_str = entities.get("date", "")
    client = client_store.get_by_name(client_name, provider.id) if client_name else None

    if not client:
        await messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
        return

    upcoming = session_store.get_upcoming_for_client(client.id)
    if not upcoming:
        await messaging_client.send_to_admin(f"{client.name} has no upcoming sessions.")
        return

    session = upcoming[0]
    if date_str:
        target_date = parse_date(date_str)
        for s in upcoming:
            if s.scheduled_at.date() == target_date:
                session = s
                break

    session_store.cancel(session.id)
    session_store.archive(session.id, reason="cancelled_by_admin")
    await messaging_client.send_to_admin(
        f"Cancelled {client.name}'s session on {session.scheduled_at.strftime('%A %b %d at %I:%M %p')}."
    )


async def _handle_reschedule_session(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store):
    from utils.time_utils import parse_datetime
    entities = intent_result.entities
    client_name = entities.get("client_name", "")
    date_str = entities.get("date", "")
    time_str = entities.get("time", "")
    client = client_store.get_by_name(client_name, provider.id) if client_name else None

    if not client:
        await messaging_client.send_to_admin(f"Couldn't find a client named '{client_name}'.")
        return

    upcoming = session_store.get_upcoming_for_client(client.id)
    if not upcoming:
        await messaging_client.send_to_admin(f"{client.name} has no upcoming sessions to reschedule.")
        return

    if not date_str or not time_str:
        conv_store.update_context(provider.phone_number, {"pending_reschedule": {"session_id": upcoming[0].id}})
        await messaging_client.send_to_admin(f"What's the new time for {client.name}?")
        return

    try:
        new_slot = parse_datetime(date_str, time_str)
    except ValueError:
        await messaging_client.send_to_admin("Couldn't parse that time. Try 'Monday at 10am'.")
        return

    session_store.reschedule(upcoming[0].id, new_slot)
    await messaging_client.send_to_admin(
        f"Rescheduled {client.name} to {new_slot.strftime('%A %b %d at %I:%M %p')}."
    )


async def _handle_admin_confirm(intent_result, provider, state, messaging_client, db, client_store, session_store, conv_store):
    context = state.context

    if context.get("pending_swap"):
        swap = context["pending_swap"]
        blocking_client = client_store.get(swap["blocking_client_id"])
        from datetime import datetime
        blocking_alts = [datetime.fromisoformat(s) for s in swap.get("blocking_alternatives", [])]
        if blocking_alts and blocking_client:
            new_slot = blocking_alts[0]
            old_sessions = session_store.get_upcoming_for_client(blocking_client.id)
            if old_sessions:
                session_store.reschedule(old_sessions[0].id, new_slot)
            # Privacy: do NOT mention the requesting client's name to blocking client
            blocking_history = conv_store.get_history(blocking_client.phone_number)
            from utils.profile import build_client_profile
            swap_msg = await generate_response(
                situation=f"Ask {blocking_client.name} if they can shift their session to {new_slot.strftime('%A at %I:%M %p')} instead. Say something came up on our end. Do not mention any other client's name.",
                recipient=blocking_client.name,
                provider_name=provider.name,
                business_type=provider.business_type,
                history=blocking_history,
                client_profile=build_client_profile(blocking_client),
            )
            await messaging_client.send_to_phone(blocking_client.phone_number, swap_msg)
            conv_store.clear_context(provider.phone_number)
            await messaging_client.send_to_admin(f"Asked {blocking_client.name} to move to {new_slot.strftime('%I:%M %p')}.")
        return

    if context.get("pending_booking"):
        booking = context["pending_booking"]
        from datetime import datetime
        slot = datetime.fromisoformat(booking["slot"])
        client = client_store.get(booking["client_id"])
        if client:
            try:
                session_store.create({
                    "provider_id": provider.id,
                    "client_id": client.id,
                    "scheduled_at": slot,
                    "duration_mins": 60,
                    "status": "scheduled",
                    "is_recurring": False,
                })
            except ValueError as e:
                conv_store.clear_context(provider.phone_number)
                await messaging_client.send_to_admin(f"Can't book that slot - {e}")
                return
            conv_store.clear_context(provider.phone_number)
            await messaging_client.send_to_admin(
                f"Done - {client.name} booked for {slot.strftime('%A %b %d at %I:%M %p')}."
            )
        return

    await messaging_client.send_to_admin("Got it.")
