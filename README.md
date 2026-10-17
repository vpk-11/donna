# Donna
<!-- version: v2.4.0 -->
![Version](https://img.shields.io/badge/version-v2.4.0-blue)

Scheduling assistant that runs both sides of a service business over iMessage: the provider (admin) side and the client side. iMessage integration isn't built yet, so a WebSocket mock stands in for it during development. Named after Donna Paulsen from Suits.

**One-line pitch:** Your business, running itself. On iMessage.

Currently scoped to a single-provider, fixed-location, 1:1-session business (the reference scenario is a personal trainer/gym). See [Scope](#scope) for what's deliberately not built yet.

---

## Architecture

One `CentralOrchestrator` routes every inbound message. The provider's phone goes to the `AdminAgent`; every other phone gets its own `ClientAgent`, spawned on first contact and kept isolated from every other client's conversation (separate prompt, separate history, no shared state). Each agent is a tool-calling LLM loop (`orchestrator/llm_agent.py`): the model picks tools, the tools act, and the reply is built from what the tools returned.

```
client message
  -> input firewall (prompt injection, identity spoofing, banned topics, token limit)
  -> ClientAgent tool loop (book, cancel, reschedule, free slots, hand off to the owner)
  -> claim verifier (reply must follow from this turn's tool results)
  -> output firewall (sensitive data, cross-client leak, booking and registration claims)
  -> outbound message
```

- **Writes only happen through MCP tools.** Every database mutation (book, cancel, reschedule, create or update client, conversation state) is a typed tool in `donna_mcp/`. A SQLAlchemy flush guard rejects any write made outside a tool, and each tool checks the caller's identity and scope (`admin`, `agent` for its own client only, `orchestrator`, `system`). Reads go through `store/` directly.
- **Tool-authored confirmations.** When a tool changes state, its own confirmation text is what the client sees. When a tool returns a confirmation, the model's own wording is discarded, so a state change is never described by the model. Replies with no confirmation go through the claim verifier and the output firewall's claim checks, which are a backstop, not a guarantee. A booking that needs admin approval says so, in the tool's words.
- **Agents never talk to each other.** When a client wants a slot another client holds, the request goes to the orchestrator, which finds the holder and relays a neutral request to that client's own agent. Names never cross between clients.
- **The firewall is fail-closed where it matters.** Prompt injection and identity spoofing scanners block the message if the scanner errors or times out. Admin input gets only the token limit and prompt-extraction checks, since the ML injection and exfiltration checks false-positive on owner commands. Admin replies, admin text relayed to a client during a live handoff, handoff summaries and orchestrator relay messages go through the output scan (admin-bound text checks financial secrets only). Fixed template messages are not scanned.
- **State is SQLite-primary.** Conversation context, turn count and handoff state live in SQLite. Redis holds the agent registry, open agent-to-agent requests, conversation summaries and a last-message cache. On restart, agents active within the inactivity timeout are respawned with their summary plus the recent turns stored in SQLite; older context is gone.
- **LLM calls are async-only, one client, bounded.** Everything goes through `intelligence/llm_client.py` with a per-call timeout and bounded retries. Defaults to a local model via Ollama; swappable to any LiteLLM provider with an env var change. Agents need a tool-calling model; `gpt-oss:20b` and `qwen2.5:7b-instruct` both pass the live suite (9/9), `gemma3:4b` has no tool support in Ollama.

---

## Setup

### 1. Create the environment

```bash
conda create -n donna python=3.12 -y
conda activate donna
pip install -r requirements.txt
```

### 2. Start Redis

Required — the server refuses to start without it.

```bash
brew install redis   # if not already installed
redis-server --daemonize yes
```

### 3. Start an LLM

Defaults to a local Ollama model, no API key or cloud dependency required.

```bash
ollama pull qwen2.5:7b-instruct
ollama serve   # if not already running
```

To use a cloud provider instead, set `LLM_MODEL`/`LLM_API_BASE`/`LLM_API_KEY` (see below) to point at it — nothing else changes.

### 4. Set environment variables

Put these in a `.env` file at the repo root (loaded automatically) or export them directly. Required:

```bash
ADMIN_PHONE=+15550000000
ADMIN_NAME="Your Name"
```

Optional (defaults shown):

```bash
LLM_MODEL=ollama_chat/qwen2.5:7b-instruct
LLM_API_BASE=http://localhost:11434
LLM_API_KEY=                       # unused by Ollama, needed for a cloud provider swap
BUSINESS_TYPE=trainer
LOCATION_TYPE=mobile
AUTO_BOOK=false
BUFFER_MINS=15                     # fallback only if config/business.json omits break_between_sessions_mins
WORKING_HOURS={"mon":["09:00","18:00"],"tue":["09:00","18:00"],"wed":["09:00","18:00"],"thu":["09:00","18:00"],"fri":["09:00","18:00"]}
PORT=8000
```

`BUSINESS_TYPE`/`LOCATION_TYPE`/`AUTO_BOOK`/`WORKING_HOURS` describe the provider's identity and set up on first run. `config/business.json` (below) separately controls scheduling policy — session length, buffer between sessions, daily booking limits, and the services/pricing text Donna quotes to clients. Edit `config/business.json` with real values before using this for an actual business; it ships with placeholder text.

### 5. Run it

One command per terminal, everything driven by flags — no separate server-start step.

```bash
# Terminal 1 — starts the server and connects you as the admin, in one process
conda activate donna
python main.py --admin
```

`donna.db` (SQLite) is created automatically on first run, and the provider is bootstrapped from `.env` plus `config/business.json`. Once you see `Connected.`, you're live and can type messages directly.

```bash
# Terminal 2, 3, ... — connect as a client (server must already be running via --admin)
conda activate donna
python main.py --client-name Sarah --client-phone +15550001111
```

Type a message and hit enter to send; replies print inline. `Ctrl+C` disconnects. Running as a client is deliberately lightweight — it doesn't load the server, firewall, or database, so it starts in under a second.

`uvicorn server:app --port 8000` still works if you want the server without an attached admin console.

### 6. Seed test data

```bash
bash scripts/seed.sh
```

Creates:
- **Sarah Chen** (`+15550001111`) — active client, 3 recurring sessions this week (Mon/Wed/Fri, 8am)
- **Marcus Johnson** (`+15550002222`) — warm prospect
- **James** (`+15550000111`) — cold prospect, no name on file yet

Connect as any of them with `python main.py --client-name <name> --client-phone <phone>`, or as a brand-new number to test cold inbound.

---

## Config

- **Provider identity** (`ADMIN_PHONE`, `ADMIN_NAME`, `BUSINESS_TYPE`, `LOCATION_TYPE`, `WORKING_HOURS`, `AUTO_BOOK`) — env vars, set once at bootstrap.
- **Scheduling policy and business content** (`config/business.json`) — session duration, buffer between sessions, max sessions per client per day, which days the business is open, and the services/pricing text Donna uses when a client asks. Static, no conversational onboarding — edit the file directly.

---

## Tests

```bash
pytest -q --ignore=tests/live                 # offline suite, no LLM needed
DONNA_LIVE=1 pytest tests/live -q             # live scenarios against a local Ollama model
python scripts/eval.py ollama_chat/gpt-oss:20b ollama_chat/qwen2.5:7b-instruct   # pass rate and latency per model
python scripts/claim_replay.py [model] [runs] # false-claim rate with the claim verifier on and off
```

The test suite drops all tables and flushes Redis before every test. Run it from a scratch copy of the repo with `REDIS_PORT` pointed at a throwaway Redis, never against your working `donna.db`. `scripts/eval.py` and `scripts/claim_replay.py` do this for you.

---

## Scripts

```bash
bash scripts/seed.sh    # seed test clients and sessions (server must be running first)
bash scripts/nuke.sh    # wipe donna.db and flush Redis — asks for confirmation, irreversible
```

---

## Scope

Deliberately not built:

- No real iMessage/Linq integration — WebSocket mock only.
- No group sessions or cohorts — 1:1 only.
- No travel time between sessions — fixed-location only.
- No Google Calendar sync — SQLite is the source of truth.
- No payments, multi-tenant support, web UI, or push notifications.
- No conversational onboarding — business configuration is a static file, not a setup chat.

---

## Stack

Python 3.12 · FastAPI (WebSocket) · SQLAlchemy (sync, SQLite) · Pydantic v2 · LiteLLM (async) · FastMCP · Redis · LLM Guard

---

## Changelog
- **v2.4.0** (2026-10-17): minor bump
- **v2.3.0** (2026-09-28): minor bump
- **v2.2.3** (2026-09-25): patch bump
- **v2.2.2** (2026-09-25): patch bump
- **v2.2.1** (2026-09-25): patch bump
- **v2.2.0** (2026-09-25): minor bump
- **v2.1.1** (2026-09-24): patch bump
- **v2.1.0** (2026-09-24): minor bump
