# Graph Report - donna  (2026-06-09)

## Corpus Check
- 41 files · ~9,365 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 234 nodes · 656 edges · 25 communities (17 shown, 8 thin omitted)
- Extraction: 74% EXTRACTED · 26% INFERRED · 0% AMBIGUOUS · INFERRED: 168 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `55794723`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_ORM and Scheduling Core|ORM and Scheduling Core]]
- [[_COMMUNITY_Admin Intent Dispatch|Admin Intent Dispatch]]
- [[_COMMUNITY_Inbound Routing and DB|Inbound Routing and DB]]
- [[_COMMUNITY_Handoff State Machine|Handoff State Machine]]
- [[_COMMUNITY_Messaging Abstraction Layer|Messaging Abstraction Layer]]
- [[_COMMUNITY_Config and LLM Pipeline|Config and LLM Pipeline]]
- [[_COMMUNITY_Conversation History Store|Conversation History Store]]
- [[_COMMUNITY_New Client Onboarding|New Client Onboarding]]
- [[_COMMUNITY_Mock Terminal Client|Mock Terminal Client]]
- [[_COMMUNITY_Nuke Script|Nuke Script]]
- [[_COMMUNITY_Seed Script|Seed Script]]
- [[_COMMUNITY_DB Session Factory|DB Session Factory]]
- [[_COMMUNITY_FastAPI App Entry|FastAPI App Entry]]
- [[_COMMUNITY_Project README|Project README]]
- [[_COMMUNITY_Python Requirements|Python Requirements]]
- [[_COMMUNITY_DB Wipe Utility|DB Wipe Utility]]

## God Nodes (most connected - your core abstractions)
1. `ClientStore` - 45 edges
2. `Session` - 41 edges
3. `ConversationStore` - 38 edges
4. `Provider` - 34 edges
5. `SessionStore` - 33 edges
6. `ProviderStore` - 29 edges
7. `handle_admin()` - 25 edges
8. `generate_response()` - 25 edges
9. `handle_client()` - 20 edges
10. `Client` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Provider` --uses--> `ConversationStore`  [INFERRED]
  core/admin_handler.py → store/conversation_store.py
- `Provider` --uses--> `ProviderStore`  [INFERRED]
  core/admin_handler.py → store/provider_store.py
- `Provider` --uses--> `SessionStore`  [INFERRED]
  core/admin_handler.py → store/session_store.py
- `Session` --uses--> `ConversationStore`  [INFERRED]
  core/admin_handler.py → store/conversation_store.py
- `Session` --uses--> `ProviderStore`  [INFERRED]
  core/admin_handler.py → store/provider_store.py

## Import Cycles
- 1-file cycle: `store/session_store.py -> store/session_store.py`
- 1-file cycle: `utils/time_utils.py -> utils/time_utils.py`
- 1-file cycle: `main.py -> main.py`
- 1-file cycle: `scheduling/conflict_resolver.py -> scheduling/conflict_resolver.py`
- 2-file cycle: `main.py -> messaging/websocket_client.py -> main.py`

## Hyperedges (group relationships)
- **LLM Inference Pipeline** — intelligence_intent_parser_parse_intent, intelligence_response_generator_generate_response, intelligence_prompts_intent_parser_system, intelligence_prompts_response_generator_system_template, config_settings [INFERRED 0.85]
- **Message Routing and Intent Dispatch** — core_router_route_message, core_admin_handler_handle_admin, core_client_handler_handle_client, intelligence_intent_parser_parse_intent [EXTRACTED 0.95]
- **Handoff State Machine** — core_handoff_trigger_dynamic_handoff, core_handoff_start_handoff_from_admin, core_handoff_trigger_explicit_handoff_from_client, core_admin_handler_handle_admin, core_client_handler_handle_client [INFERRED 0.85]
- **Repository Pattern: Store Classes Wrapping ORM Models** — store_client_store_clientstore, store_provider_store_providerstore, store_session_store_sessionstore, store_conversation_store_conversationstore, models_orm_client, models_orm_provider, models_orm_session, models_orm_conversationstate [INFERRED 0.95]
- **Conflict Resolution Pipeline: resolve_slot + SessionStore + ClientStore** — scheduling_conflict_resolver_resolve_slot, store_session_store_sessionstore_get_conflict, store_session_store_sessionstore_get_free_slots, store_client_store_clientstore_get, scheduling_conflict_resolver_conflictresult [EXTRACTED 1.00]
- **Session Lifecycle: create, cancel, archive, reschedule** — store_session_store_sessionstore_create, store_session_store_sessionstore_cancel, store_session_store_sessionstore_archive, store_session_store_sessionstore_reschedule, models_orm_sessionarchive [INFERRED 0.95]

## Communities (25 total, 8 thin omitted)

### Community 0 - "ORM and Scheduling Core"
Cohesion: 0.23
Nodes (8): Hard Booking Guard Pattern, SQLite Column Arithmetic Bug Fix, SessionArchive, SessionModel, date, datetime, Session, SessionStore

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.10
Nodes (42): BaseModel, BaseSettings, Intent-Driven Dispatch Pattern, Privacy Guard on Swap Messages, Settings, _check_client_status(), _check_schedule(), handle_admin() (+34 more)

### Community 2 - "Inbound Routing and DB"
Cohesion: 0.15
Nodes (11): Config, cancel_day(), ClientStore, date, Session, SessionStore, seed.sh Database Seed Script, bootstrap_provider() (+3 more)

### Community 3 - "Handoff State Machine"
Cohesion: 0.14
Nodes (32): Base, Scheduling Conflict Resolution Strategy, Handoff Relay Pattern, Provider, Session, Client, Client, ConversationStore (+24 more)

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.11
Nodes (13): ABC, Base, engine, init_db(), FastAPI, lifespan(), WebSocket, websocket_endpoint() (+5 more)

### Community 5 - "Config and LLM Pipeline"
Cohesion: 0.12
Nodes (15): Acceptance: 4 Demo Scenes, Admin Handler — Check Order (before intent parsing), Architecture Map, Client Handler — Check Order, Conflict Resolution States, Context Keys (only these, never invent new ones), Donna — Project CLAUDE.md, Graphify (+7 more)

### Community 6 - "Conversation History Store"
Cohesion: 0.17
Nodes (8): Conversation History Ring Buffer, ConversationState, ConversationState, ConversationStore, Session, Clear pending state but preserve history and protected keys (prefixed _)., Append a turn to conversation history. role is 'user' or 'donna'., Called after every Donna send. Updates last_donna_message and appends to history

### Community 7 - "New Client Onboarding"
Cohesion: 0.40
Nodes (9): _create_and_greet_client(), handle_new_client_intro(), handle_new_client_intro_clarification(), ClientStore, ConversationStore, Provider, Session, looks_like_phone() (+1 more)

## Knowledge Gaps
- **31 isolated node(s):** `What It Is`, `Session Type`, `Graphify`, `Stack`, `Hard Constraints` (+26 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `Conversation History Store` to `Admin Intent Dispatch`, `Handoff State Machine`, `Messaging Abstraction Layer`, `New Client Onboarding`?**
  _High betweenness centrality (0.220) - this node is a cross-community bridge._
- **Why does `Session` connect `Handoff State Machine` to `ORM and Scheduling Core`, `Admin Intent Dispatch`, `Inbound Routing and DB`, `Conversation History Store`, `New Client Onboarding`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `ClientStore` connect `Handoff State Machine` to `Admin Intent Dispatch`, `Inbound Routing and DB`, `Conversation History Store`, `New Client Onboarding`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `ClientStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ClientStore` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `Session` (e.g. with `ConversationState` and `ClientStore`) actually correct?**
  _`Session` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `ConversationStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ConversationStore` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Provider` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`Provider` has 24 INFERRED edges - model-reasoned connections that need verification._