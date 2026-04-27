#!/usr/bin/env bash
# Usage: bash scripts/seed.sh
# Seeds donna.db with provider bootstrap + test clients.
# Can run standalone after nuke — does not require server to be up.

set -e
echo "Seeding Donna DB..."

CONDA_BASE="$(conda info --base 2>/dev/null)"
DONNA_PYTHON="${CONDA_BASE}/envs/donna/bin/python3"
if [ ! -x "$DONNA_PYTHON" ]; then
    echo "ERROR: conda env 'donna' not found at $DONNA_PYTHON"
    exit 1
fi

"$DONNA_PYTHON" - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from db.database import SessionLocal
from db.migrations import init_db
from store.provider_store import ProviderStore
from store.client_store import ClientStore
from store.session_store import SessionStore
from store.bootstrap import bootstrap_provider
from datetime import datetime, timedelta

init_db()  # create tables if they don't exist yet

db = SessionLocal()
provider_store = ProviderStore(db)
client_store = ClientStore(db)
session_store = SessionStore(db)

bootstrap_provider(db)  # creates provider from .env if missing
provider = provider_store.get_first()
if not provider:
    print("ERROR: Could not bootstrap provider. Check .env has ADMIN_PHONE and ADMIN_NAME.")
    sys.exit(1)
print(f"Provider: {provider.name} ({provider.phone_number})")

# Active recurring client — Sarah
# Mock client: python -m mock_client --phone +15550001111 --name "Sarah Chen"
sarah = client_store.get_by_phone("+15550001111")
if not sarah:
    sarah = client_store.create({
        "provider_id": provider.id,
        "name": "Sarah Chen",
        "phone_number": "+15550001111",
        "status": "active",
        "membership_type": "recurring",
        "sessions_per_week": 3,
        "preferred_days": ["mon", "wed", "fri"],
        "preferred_time": "morning",
        "address": "123 Main St, Boston MA",
        "notes": "Prefers 8am. Has a golden retriever named Biscuit.",
    })
    print(f"Created Sarah: {sarah.id}")

# Book Sarah Mon/Wed/Fri 8am this week
today = datetime.utcnow().date()
for days_ahead in [0, 2, 4]:
    slot = datetime.combine(today + timedelta(days=days_ahead),
                            datetime.strptime("08:00", "%H:%M").time())
    existing = session_store.get_conflict(provider.id, slot, 60, provider.buffer_mins)
    if not existing:
        session_store.create({
            "provider_id": provider.id,
            "client_id": sarah.id,
            "scheduled_at": slot,
            "duration_mins": 60,
            "status": "scheduled",
            "is_recurring": True,
            "recurrence_type": "permanent",
            "location": sarah.address,
        })

# Warm prospect — Marcus (+15550002222)
if not client_store.get_by_phone("+15550002222"):
    client_store.create({
        "provider_id": provider.id,
        "name": "Marcus Johnson",
        "phone_number": "+15550002222",
        "status": "prospect",
        "notes": "Met at gym. Interested in 2x/week. Budget conscious.",
    })
    print("Created Marcus")

# Cold prospect — James (+15550000111)
if not client_store.get_by_phone("+15550000111"):
    client_store.create({
        "provider_id": provider.id,
        "name": "James",
        "phone_number": "+15550000111",
        "status": "prospect",
        "notes": "Wants to schedule a session. Reached out via referral.",
    })
    print("Created James")

print("Seed complete. Sarah: 3 sessions this week. Marcus + James: prospects.")
db.close()
PYEOF
