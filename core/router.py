from sqlalchemy.orm import Session
from store.provider_store import ProviderStore
from store.client_store import ClientStore


async def route_message(phone: str, text: str, messaging_client, db: Session) -> None:
    from core.admin_handler import handle_admin
    from core.client_handler import handle_client, handle_cold_inbound

    provider_store = ProviderStore(db)
    client_store = ClientStore(db)

    provider = provider_store.get_by_phone(phone)
    if provider:
        await handle_admin(text, provider, messaging_client, db)
        return

    client = client_store.get_by_phone(phone)
    if client:
        await handle_client(text, client, messaging_client, db)
        return

    await handle_cold_inbound(text, phone, messaging_client, db)
