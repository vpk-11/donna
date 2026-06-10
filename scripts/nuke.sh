#!/usr/bin/env bash
# Usage: bash scripts/nuke.sh
# WARNING: Deletes donna.db and flushes Redis. Irreversible.

read -p "This will wipe all Donna data. Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

rm -f donna.db
echo "Done. Start the server to reinitialize."

redis-cli FLUSHDB
echo "Redis state cleared."
