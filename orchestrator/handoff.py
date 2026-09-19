import json
import logging
from sqlalchemy.orm import Session
from models.orm import Client, Provider
from store.conversation_store import ConversationStore
from intelligence.response_generator import generate_response
from db.redis_client import get_redis
from orchestrator.channels import STATE_AGENT_REGISTRY

logger = logging.getLogger(__name__)


def set_agent_handoff_flag(phone: str, active: bool) -> None:
    """Mark handoff_active in the Redis agent registry, if the phone is registered."""
    try:
        r = get_redis()
        existing_raw = r.hget(STATE_AGENT_REGISTRY, phone)
        if existing_raw:
            data = json.loads(existing_raw)
            data["handoff_active"] = active
            r.hset(STATE_AGENT_REGISTRY, phone, json.dumps(data))
    except Exception as e:
        logger.warning(f"handoff.redis_update failed for {phone}: {e}")


async def trigger_dynamic_handoff(
    client: Client,
    provider: Provider,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
) -> None:
    admin_ctx = {
        "pending_dynamic_handoff": True,
        "handoff_target_name": client.name,
        "handoff_target_phone": client.phone_number,
    }
    admin_state = conv_store.get_or_create(provider.phone_number, "admin")
    existing_ctx = dict(admin_state.context or {})
    existing_ctx.update(admin_ctx)
    conv_store.update(provider.phone_number, {"context": existing_ctx})

    await messaging_client.send_to_admin(
        f"Heads up - {client.name} has been going back and forth and seems stuck. "
        f"Want to jump in or should I keep handling it? (yes / no)"
    )

    client_response = await generate_response(
        situation="Client seems stuck and needs more help. Send a warm message saying you're getting them some extra help without mentioning an admin.",
        recipient=client.name,
        provider_name=provider.name,
        business_type=provider.business_type,
    )
    await messaging_client.send_to_phone(client.phone_number, client_response)


async def start_handoff_from_admin(
    provider: Provider,
    target_phone: str,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
) -> None:
    client_state = conv_store.get_by_phone(target_phone)
    client_name = "the client"
    if client_state:
        from store.client_store import ClientStore
        c = ClientStore(db).get_by_phone(target_phone)
        if c:
            client_name = c.name

    conv_store.update(target_phone, {"handoff_active": True})

    admin_state = conv_store.get_by_phone(provider.phone_number)
    admin_ctx = dict(admin_state.context if admin_state else {})
    admin_ctx.pop("pending_dynamic_handoff", None)
    admin_ctx.pop("handoff_target_name", None)
    admin_ctx.pop("handoff_target_phone", None)
    conv_store.update(provider.phone_number, {
        "handoff_active": True,
        "handoff_target_phone": target_phone,
        "context": admin_ctx,
    })

    set_agent_handoff_flag(target_phone, True)

    await messaging_client.send_to_phone(
        target_phone,
        f"Let me loop {provider.name} in directly - give me a moment."
    )
    await messaging_client.send_to_admin(
        f"You're live with {client_name}. Reply normally - I'll relay. "
        f"Text 'done' or 'donna take over' when you're done."
    )


async def trigger_explicit_handoff_from_client(
    client: Client,
    provider: Provider,
    messaging_client,
    db: Session,
    conv_store: ConversationStore,
) -> None:
    conv_store.update(client.phone_number, {"handoff_active": True})

    admin_state = conv_store.get_or_create(provider.phone_number, "admin")
    admin_ctx = dict(admin_state.context or {})
    admin_ctx.pop("pending_dynamic_handoff", None)
    conv_store.update(provider.phone_number, {
        "handoff_active": True,
        "handoff_target_phone": client.phone_number,
        "context": admin_ctx,
    })

    set_agent_handoff_flag(client.phone_number, True)

    await messaging_client.send_to_phone(
        client.phone_number,
        f"Let me loop {provider.name} in - one moment."
    )
    await messaging_client.send_to_admin(
        f"{client.name} wants to speak with you directly. You're live. "
        f"Text 'done' when finished."
    )
