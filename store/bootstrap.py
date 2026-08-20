import json
import logging
from sqlalchemy.orm import Session
from store.provider_store import ProviderStore
from config import settings

logger = logging.getLogger(__name__)


def bootstrap_provider(db: Session, business_config: dict | None = None) -> None:
    store = ProviderStore(db)
    existing = store.get_by_phone(settings.admin_phone)
    if existing:
        logger.info(f"Provider already exists: {existing.name} ({existing.phone_number})")
        return

    business_config = business_config or {}
    working_hours = json.loads(settings.working_hours)
    provider = store.create({
        "phone_number": settings.admin_phone,
        "name": settings.admin_name,
        "business_type": settings.business_type,
        "location_type": settings.location_type,
        "auto_book": settings.auto_book,
        # config/business.json's break_between_sessions_mins is the source of
        # truth once present; settings.buffer_mins (env var) is only the
        # fallback for a business.json that omits it.
        "buffer_mins": business_config.get("break_between_sessions_mins", settings.buffer_mins),
        "working_hours": working_hours,
        # Real services/pricing come from config/business.json — Kaushik
        # edits real values there. Previously always seeded {}, so Donna
        # could never describe real services/pricing. Only set keys that are
        # actually present and non-empty so downstream .get(key, default)
        # fallbacks (agent.py, central.py, utils/profile.py) still apply for
        # a business.json (or test business_config) that omits them.
        "business_config": {
            k: business_config[k] for k in ("services", "pricing") if business_config.get(k)
        },
    })
    logger.info(f"Bootstrapped provider: {provider.name} ({provider.phone_number})")
