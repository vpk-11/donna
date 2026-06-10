import logging
from datetime import date
from sqlalchemy.orm import Session
from store.session_store import SessionStore
from store.client_store import ClientStore
from store.provider_store import ProviderStore
from intelligence.response_generator import generate_response

logger = logging.getLogger(__name__)


async def cancel_day(
    provider_id: int,
    target_date: date,
    messaging_client,
    db: Session,
    session_store: SessionStore,
    client_store: ClientStore,
) -> None:
    sessions = session_store.get_sessions_for_date(provider_id, target_date)
    if not sessions:
        await messaging_client.send_to_admin("No sessions scheduled for that day.")
        return

    provider = ProviderStore(db).get_first()
    await messaging_client.send_to_admin(
        f"You have {len(sessions)} session(s) today - cancelling all and notifying clients now."
    )

    for session in sessions:
        pre_status = session_store.cancel(session.id)
        session_store.archive(session.id, reason="provider_emergency", pre_cancel_status=pre_status)
        client = client_store.get(session.client_id)
        if not client:
            continue
        cancel_msg = await generate_response(
            situation=f"Session with {client.name} on {target_date} cancelled by {provider.name} due to a personal emergency. Apologize and say they'll be rescheduled ASAP.",
            recipient=client.name,
            provider_name=provider.name,
            business_type=provider.business_type,
        )
        await messaging_client.send_to_phone(client.phone_number, cancel_msg)

    await messaging_client.send_to_admin(
        f"Done - cancelled {len(sessions)} session(s). All clients notified."
    )
