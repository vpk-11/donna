# Donna — Project CLAUDE.md

> Read this before writing any code. See `.claude/DONNA_BRIEF.md` for the full spec.
> Do not touch `.env`. Do not add Co-authored-by lines to commits. Ever.

---

## What It Is

AI business assistant for iMessage (via Linq). Manages both sides of a service
business: provider (admin) and clients. V1 uses WebSocket mock only.

## Session Type

Major feature or rework: load `dev-general` + `dev-backend`.

## Graphify

Knowledge graph at `graphify-out/`. Post-commit hook active.
- Codebase questions: `graphify query "<question>"` first.
- Broad architecture: read `graphify-out/GRAPH_REPORT.md`.
- After out-of-commit edits: `graphify update .`

---

## Stack

- Python 3.12, Anaconda env `donna`
- FastAPI (WebSocket server), SQLAlchemy sync (SQLite), Pydantic v2
- LiteLLM for all LLM calls (async only), rich for terminal output
- DB: `donna.db` — single file, JSON columns for dynamic fields

---

## Hard Constraints

**LLM:** Every LLM call uses `await litellm.acompletion()`. Never sync. No direct
litellm calls outside `intelligence/`. Two calls per turn: intent parser + response
generator.

**DB sessions:** One session per WebSocket message. Open, use, close in finally block.
Never reuse across messages. All DB access goes through `store/` — no raw SQLAlchemy
in handlers.

**`last_donna_message`:** Updated after every single Donna send, no exceptions. Called
inside `websocket_client.py` after every send via `conv_store.update_last_donna_message()`.
Intent parser reads this field — without it, multi-turn conversations break.

**Conversation state:** Read at START of every handler, written at END.

**Date/time parsing:** Only through `utils/time_utils.py`. No duplicate parsing logic.

**Phone detection:** Only through `looks_like_phone()`.

**Config:** `pydantic-settings` reads from shell environment only. `env_file = None`.
Never read or write any `.env` file.

---

## Architecture Map

```
main.py               FastAPI app, WebSocket endpoint, lifespan
config.py             Settings (pydantic-settings, env only)
db/                   engine, SessionLocal, Base, init_db()
models/               ORM tables (orm.py), IntentResult schema (schemas.py)
messaging/            MessagingClient ABC, WebSocketMessagingClient, LinqClient stub
core/                 router.py, admin_handler.py, client_handler.py, handoff.py
intelligence/         intent_parser.py, response_generator.py, prompts.py
scheduling/           conflict_resolver.py, session_manager.py, travel.py
store/                bootstrap.py, provider/client/session/conversation stores
mock/                 terminal WebSocket client
utils/                time_utils.py
scripts/              seed.sh, nuke.sh
```

---

## Message Routing

`route_message()` in `core/router.py`:
1. Admin phone match → `handle_admin()`
2. Known client phone → `handle_client()`
3. Unknown phone → `handle_cold_inbound()`

---

## Admin Handler — Check Order (before intent parsing)

1. `state.handoff_active` + `state.handoff_target_phone` → relay mode
2. `context["pending_dynamic_handoff"]` → yes/no resolution
3. `context["pending_clarification"] == "NEW_CLIENT_INTRO"` → clarification flow
4. Normal intent parsing

---

## Client Handler — Check Order

1. `state.handoff_active` → relay to admin
2. Trigger-word check (frustrated, real person, etc.) → `trigger_dynamic_handoff()`
3. Normal intent parsing + increment `turn_count`
4. `turn_count >= 5` and UNKNOWN → `trigger_dynamic_handoff()`

---

## Conflict Resolution States

`FREE` → `ALTERNATIVES` → `SWAP_POSSIBLE` → `NO_AVAILABILITY`

Defined in `scheduling/conflict_resolver.py` as `ConflictResult` dataclass.

---

## Context Keys (only these, never invent new ones)

```
pending_clarification, partial_name, partial_service,
pending_booking, pending_swap, pending_reschedule,
pending_dynamic_handoff, handoff_target_name, handoff_target_phone,
awaiting_name, intent_after_name, client_created
```

---

## What V1 Does NOT Do

No Linq integration, no real Google Calendar, no payments, no multi-tenant,
no web UI, no SMS/email fallback, no push notifications. Do not stub, mention,
or build any of these.

---

## Running Locally

```bash
conda activate donna
uvicorn main:app --port 8000

# Mock clients (separate terminals)
python -m mock.client --phone +15550000000 --name Kaushik  # admin
python -m mock.client --phone +15550001111 --name Sarah    # client

bash scripts/seed.sh   # seed DB (server must be running first)
bash scripts/nuke.sh   # wipe DB
```

---

## Acceptance: 4 Demo Scenes

All 4 must pass before the build is done. Scenes are in `.claude/DONNA_BRIEF.md`:
Scene 1 (warm prospect onboarding), Scene 2 (conflict + swap), Scene 3 (emergency
cancellation), Scene 4 (cold inbound + dynamic handoff).
