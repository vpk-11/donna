import logging
from sqlalchemy.orm import Session
from models.orm import Provider
from store.conversation_store import ConversationStore
from store.client_store import ClientStore
from intelligence.response_generator import generate_response
from utils.time_utils import looks_like_phone

logger = logging.getLogger(__name__)


async def handle_new_client_intro(
    text: str,
    intent_result,
    provider: Provider,
    state,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
    client_store: ClientStore,
) -> None:
    entities = intent_result.entities
    client_name = entities.get("client_name", "").strip()
    phone = entities.get("phone_number", "").strip()
    notes = entities.get("notes", "").strip()

    if not client_name:
        conv_store.update_context(provider.phone_number, {"pending_clarification": "NEW_CLIENT_INTRO"})
        await messaging_client.send_to_admin("What's the client's name?")
        return

    if not phone:
        conv_store.update_context(provider.phone_number, {
            "pending_clarification": "NEW_CLIENT_INTRO",
            "partial_name": client_name,
            "partial_notes": notes,
        })
        await messaging_client.send_to_admin(f"Got it - what's {client_name}'s phone number?")
        return

    await _create_and_greet_client(client_name, phone, notes, provider, messaging_client, db, conv_store, client_store)


async def handle_new_client_intro_clarification(
    text: str,
    provider: Provider,
    state,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
) -> None:
    client_store = ClientStore(db)
    ctx = state.context
    partial_name = ctx.get("partial_name", "")
    partial_notes = ctx.get("partial_notes", "")

    if not partial_name:
        if looks_like_phone(text):
            conv_store.update_context(provider.phone_number, {
                "pending_clarification": "NEW_CLIENT_INTRO",
                "partial_phone": text.strip(),
            })
            await messaging_client.send_to_admin("And what's their name?")
        else:
            conv_store.update_context(provider.phone_number, {
                "pending_clarification": "NEW_CLIENT_INTRO",
                "partial_name": text.strip(),
            })
            await messaging_client.send_to_admin(f"Got it - what's {text.strip()}'s phone number?")
        return

    if looks_like_phone(text):
        phone = text.strip()
        conv_store.clear_context(provider.phone_number)
        await _create_and_greet_client(partial_name, phone, partial_notes, provider, messaging_client, db, conv_store, client_store)
    else:
        conv_store.update_context(provider.phone_number, {"partial_name": text.strip()})
        await messaging_client.send_to_admin(f"Got it - what's {text.strip()}'s phone number?")


async def _create_and_greet_client(
    name: str,
    phone: str,
    notes: str,
    provider: Provider,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
    client_store: ClientStore,
) -> None:
    existing = client_store.get_by_phone(phone)
    if existing:
        await messaging_client.send_to_admin(f"{existing.name} ({phone}) is already in the system.")
        return

    client = client_store.create({
        "provider_id": provider.id,
        "name": name,
        "phone_number": phone,
        "status": "prospect",
        "notes": notes or None,
    })

    conv_store.get_or_create(phone, "client")

    greeting = await generate_response(
        situation=f"{provider.name} introduced a new prospect named {name} ({notes or 'no extra notes'}). Send a warm greeting introducing yourself as Donna, {provider.name}'s assistant, and ask how you can help.",
        recipient=name,
        provider_name=provider.name,
        business_type=provider.business_type,
    )
    await messaging_client.send_to_phone(phone, greeting)
    conv_store.clear_context(provider.phone_number)
    await messaging_client.send_to_admin(f"Got it - reaching out to {name} now.")
