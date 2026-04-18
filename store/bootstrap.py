import json
import logging
from sqlalchemy.orm import Session
from store.provider_store import ProviderStore
from config import settings

logger = logging.getLogger(__name__)


def bootstrap_provider(db: Session) -> None:
    store = ProviderStore(db)
    existing = store.get_by_phone(settings.admin_phone)
    if existing:
        logger.info(f"Provider already exists: {existing.name} ({existing.phone_number})")
        return

    working_hours = json.loads(settings.working_hours)
    provider = store.create({
        "phone_number": settings.admin_phone,
        "name": settings.admin_name,
        "business_type": settings.business_type,
        "location_type": settings.location_type,
        "auto_book": settings.auto_book,
        "buffer_mins": settings.buffer_mins,
        "working_hours": working_hours,
        "business_config": {},
    })
    logger.info(f"Bootstrapped provider: {provider.name} ({provider.phone_number})")
