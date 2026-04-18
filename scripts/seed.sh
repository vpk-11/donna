#!/usr/bin/env bash
# Usage: bash scripts/seed.sh
# Seeds donna.db with pre-existing clients for testing.
# Run after starting the server at least once (to init the DB).

set -e
echo "Seeding Donna DB..."

conda run -n donna python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from db.database import SessionLocal
from store.provider_store import ProviderStore
from store.client_store import ClientStore
from store.session_store import SessionStore
from datetime import datetime, timedelta

db = SessionLocal()
provider_store = ProviderStore(db)
client_store = ClientStore(db)
session_store = SessionStore(db)

provider = provider_store.get_first()
if not provider:
    print("ERROR: No provider found. Start the server first to bootstrap the provider.")
    sys.exit(1)

# Active recurring client — Sarah
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

# Warm prospect — Marcus
if not client_store.get_by_phone("+15550002222"):
    client_store.create({
        "provider_id": provider.id,
        "name": "Marcus Johnson",
        "phone_number": "+15550002222",
        "status": "prospect",
        "notes": "Met at gym. Interested in 2x/week. Budget conscious.",
    })
    print("Created Marcus")

print("Seed complete. Sarah: 3 sessions this week. Marcus: prospect.")
db.close()
PYEOF
