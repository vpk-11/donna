# Graph Report - donna  (2026-06-09)

## Corpus Check
- 53 files · ~10,621 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 308 nodes · 784 edges · 33 communities (28 shown, 5 thin omitted)
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 165 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b2ed04f6`
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
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]

## God Nodes (most connected - your core abstractions)
1. `ClientStore` - 42 edges
2. `Session` - 41 edges
3. `ConversationStore` - 37 edges
4. `Provider` - 34 edges
5. `SessionStore` - 34 edges
6. `ProviderStore` - 26 edges
7. `generate_response()` - 25 edges
8. `handle_admin()` - 25 edges
9. `handle_client()` - 20 edges
10. `Client` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Client` --uses--> `IntentResult`  [INFERRED]
  core/client_handler.py → models/schemas.py
- `Client` --uses--> `SessionStore`  [INFERRED]
  core/client_handler.py → store/session_store.py
- `Session` --uses--> `IntentResult`  [INFERRED]
  core/client_handler.py → models/schemas.py
- `Session` --uses--> `ConversationStore`  [INFERRED]
  core/client_handler.py → store/conversation_store.py
- `Session` --uses--> `ProviderStore`  [INFERRED]
  core/client_handler.py → store/provider_store.py

## Import Cycles
- 1-file cycle: `store/session_store.py -> store/session_store.py`
- 1-file cycle: `main.py -> main.py`
- 1-file cycle: `scheduling/conflict_resolver.py -> scheduling/conflict_resolver.py`
- 1-file cycle: `utils/time_utils.py -> utils/time_utils.py`
- 2-file cycle: `main.py -> messaging/websocket_client.py -> main.py`

## Hyperedges (group relationships)
- **LLM Inference Pipeline** — intelligence_intent_parser_parse_intent, intelligence_response_generator_generate_response, intelligence_prompts_intent_parser_system, intelligence_prompts_response_generator_system_template, config_settings [INFERRED 0.85]
- **Message Routing and Intent Dispatch** — core_router_route_message, core_admin_handler_handle_admin, core_client_handler_handle_client, intelligence_intent_parser_parse_intent [EXTRACTED 0.95]
- **Handoff State Machine** — core_handoff_trigger_dynamic_handoff, core_handoff_start_handoff_from_admin, core_handoff_trigger_explicit_handoff_from_client, core_admin_handler_handle_admin, core_client_handler_handle_client [INFERRED 0.85]
- **Repository Pattern: Store Classes Wrapping ORM Models** — store_client_store_clientstore, store_provider_store_providerstore, store_session_store_sessionstore, store_conversation_store_conversationstore, models_orm_client, models_orm_provider, models_orm_session, models_orm_conversationstate [INFERRED 0.95]
- **Conflict Resolution Pipeline: resolve_slot + SessionStore + ClientStore** — scheduling_conflict_resolver_resolve_slot, store_session_store_sessionstore_get_conflict, store_session_store_sessionstore_get_free_slots, store_client_store_clientstore_get, scheduling_conflict_resolver_conflictresult [EXTRACTED 1.00]
- **Session Lifecycle: create, cancel, archive, reschedule** — store_session_store_sessionstore_create, store_session_store_sessionstore_cancel, store_session_store_sessionstore_archive, store_session_store_sessionstore_reschedule, models_orm_sessionarchive [INFERRED 0.95]

## Communities (33 total, 5 thin omitted)

### Community 0 - "ORM and Scheduling Core"
Cohesion: 0.27
Nodes (6): SessionArchive, SessionModel, date, datetime, Session, SessionStore

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.19
Nodes (25): Intent-Driven Dispatch Pattern, Privacy Guard on Swap Messages, _check_client_status(), _check_schedule(), handle_admin(), _handle_admin_confirm(), _handle_book_session(), _handle_cancel_session() (+17 more)

### Community 2 - "Inbound Routing and DB"
Cohesion: 0.23
Nodes (8): cancel_day(), date, Session, SessionStore, bootstrap_provider(), Session, ProviderStore, Provider

### Community 3 - "Handoff State Machine"
Cohesion: 0.14
Nodes (33): Base, Client, Scheduling Conflict Resolution Strategy, Handoff Relay Pattern, Provider, Session, Session, Client (+25 more)

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.11
Nodes (14): ABC, get_async_redis(), get_redis(), ping_redis(), FastAPI, lifespan(), websocket_endpoint(), MessagingClient (+6 more)

### Community 5 - "Config and LLM Pipeline"
Cohesion: 0.12
Nodes (15): Acceptance: 4 Demo Scenes, Admin Handler — Check Order (before intent parsing), Architecture Map, Client Handler — Check Order, Conflict Resolution States, Context Keys (only these, never invent new ones), Donna — Project CLAUDE.md, Graphify (+7 more)

### Community 6 - "Conversation History Store"
Cohesion: 0.18
Nodes (11): Conversation History Ring Buffer, ConversationState, handle_cold_inbound(), Session, route_message(), ConversationState, ConversationStore, Session (+3 more)

### Community 7 - "New Client Onboarding"
Cohesion: 0.40
Nodes (9): _create_and_greet_client(), handle_new_client_intro(), handle_new_client_intro_clarification(), ClientStore, ConversationStore, Provider, Session, looks_like_phone() (+1 more)

### Community 15 - "FastAPI App Entry"
Cohesion: 0.12
Nodes (19): BaseModel, BaseSettings, Config, Settings, Exception, _format_history(), parse_intent(), _parse_json_response() (+11 more)

### Community 20 - "Python Requirements"
Cohesion: 0.20
Nodes (16): book_session(), cancel_session(), check_slot_conflict(), _db(), get_free_slots(), get_sessions_for_date(), get_upcoming_sessions(), Cancel a scheduled session by ID. (+8 more)

### Community 22 - "DB Wipe Utility"
Cohesion: 0.30
Nodes (13): ClientStore, _client_dict(), create_client(), _db(), get_client(), get_client_by_phone(), list_clients(), Update one or more fields on an existing client. Only provided fields are change (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (13): break_between_sessions_mins, business_hours, end, start, business_type, conversation_timeout_mins, days_open, location_type (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.21
Nodes (7): Base, engine, init_db(), ConversationSummary, test_db_migration(), test_parse_date_raises_on_garbage(), test_redis_round_trip()

### Community 27 - "Community 27"
Cohesion: 0.26
Nodes (11): Any, _db(), get_conversation_state(), get_provider(), _provider_dict(), Reset conversation context for a phone number.     Clears pending context keys,, Get the current provider configuration., Update a single provider field.     Updatable fields: name, business_type, locat (+3 more)

## Knowledge Gaps
- **42 isolated node(s):** `business_type`, `location_type`, `travel_time_enabled`, `start`, `end` (+37 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `Conversation History Store` to `Admin Intent Dispatch`, `Handoff State Machine`, `Messaging Abstraction Layer`, `New Client Onboarding`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `SessionStore` connect `ORM and Scheduling Core` to `Admin Intent Dispatch`, `Inbound Routing and DB`, `Handoff State Machine`, `Python Requirements`, `DB Wipe Utility`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `Session` connect `Handoff State Machine` to `ORM and Scheduling Core`, `Inbound Routing and DB`, `Conversation History Store`, `New Client Onboarding`, `DB Wipe Utility`, `Community 26`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `ClientStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ClientStore` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `Session` (e.g. with `Client` and `ClientStore`) actually correct?**
  _`Session` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ConversationStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ConversationStore` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Provider` (e.g. with `Client` and `ClientStore`) actually correct?**
  _`Provider` has 24 INFERRED edges - model-reasoned connections that need verification._