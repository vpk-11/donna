# Donna

AI-powered business assistant over iMessage (WebSocket mock for V1). Named after Donna Paulsen from Suits.

**One-line pitch:** Your business, running itself. On iMessage.

---

## Setup

### 1. Create the conda environment

```bash
conda create -n donna python=3.12 -y
conda activate donna
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export ADMIN_PHONE=+15550000000
export ADMIN_NAME=Kaushik
export LLM_API_KEY=your_groq_api_key_here
export LLM_MODEL=groq/llama-3.3-70b-versatile  # default
```

Optional:
```bash
export BUSINESS_TYPE=trainer        # trainer | therapist | salon | remote
export LOCATION_TYPE=mobile         # mobile | fixed | remote
export AUTO_BOOK=false
export BUFFER_MINS=15
export WORKING_HOURS='{"mon":["09:00","18:00"],"tue":["09:00","18:00"],"wed":["09:00","18:00"],"thu":["09:00","18:00"],"fri":["09:00","18:00"]}'
```

### 3. Start the server

```bash
conda activate donna
uvicorn main:app --port 8000
```

The DB (`donna.db`) is created automatically on first run. The provider is bootstrapped from env vars.

### 4. Seed test data

```bash
bash scripts/seed.sh
```

Creates Sarah Chen (active recurring client, 3 sessions this week) and Marcus Johnson (warm prospect).

### 5. Connect mock clients

Each terminal tab is one phone:

```bash
# Admin
python -m mock.client --phone +15550000000 --name Kaushik

# Sarah (seeded client)
python -m mock.client --phone +15550001111 --name Sarah

# Greg (new prospect)
python -m mock.client --phone +15550004444 --name Greg

# Cold inbound
python -m mock.client --phone +15550009999 --name Unknown
```

---

## Demo Scenes

### Scene 1: Warm prospect onboarding
```
Admin:  "Greg +15550004444, wants personal training, Mondays"
```

### Scene 2: Conflict resolution + swap
```
Admin:  "Book Greg for Monday 8am"
Admin:  "check if Sarah can move"
Sarah:  "yeah that's fine"
Admin:  "just this week"
```

### Scene 3: Emergency cancellation
```
Admin:  "Cancel everything today, family emergency"
```

### Scene 4: Cold inbound + dynamic handoff
```
# Connect as Unknown (+15550009999), ask 5+ questions
# Donna pings admin asking to jump in
Admin:  "yes"
# Admin is live with the unknown lead
Admin:  "done"  # ends handoff
```

---

## Scripts

```bash
bash scripts/seed.sh    # seed test clients and sessions
bash scripts/nuke.sh    # wipe donna.db and start fresh
```

---

## Architecture

- **Transport:** FastAPI WebSocket (`ws://localhost:8000/ws/{phone}`)
- **DB:** SQLite (`donna.db`), SQLAlchemy sync sessions
- **LLM:** LiteLLM async (`await litellm.acompletion()`)
- **Routing:** phone number determines admin vs client vs cold inbound
- **State:** one `ConversationState` row per phone, `last_donna_message` updated on every send

See `DONNA_BRIEF.md` for full spec.
