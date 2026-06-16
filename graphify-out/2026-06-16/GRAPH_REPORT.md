# Graph Report - donna  (2026-06-16)

## Corpus Check
- 61 files · ~12,257 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 322 nodes · 838 edges · 34 communities (29 shown, 5 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 167 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2ec2889d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_ORM and Scheduling Core|ORM and Scheduling Core]]
- [[_COMMUNITY_Admin Intent Dispatch|Admin Intent Dispatch]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Messaging Abstraction Layer|Messaging Abstraction Layer]]
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
- [[_COMMUNITY_Community 33|Community 33]]

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
- `check_slot_conflict()` --calls--> `ClientStore`  [INFERRED]
  donna_mcp/tools/scheduling.py → scheduling/session_manager.py
- `FirewallResult` --uses--> `FirewallResult`  [INFERRED]
  firewall/input_guard.py → models/schemas.py
- `FirewallResult` --uses--> `FirewallResult`  [INFERRED]
  firewall/output_guard.py → models/schemas.py
- `Client` --uses--> `IntentResult`  [INFERRED]
  core/client_handler.py → models/schemas.py
- `Session` --uses--> `IntentResult`  [INFERRED]
  core/client_handler.py → models/schemas.py

## Import Cycles
- 1-file cycle: `scheduling/conflict_resolver.py -> scheduling/conflict_resolver.py`
- 1-file cycle: `store/session_store.py -> store/session_store.py`
- 1-file cycle: `main.py -> main.py`
- 1-file cycle: `utils/time_utils.py -> utils/time_utils.py`
- 2-file cycle: `main.py -> messaging/websocket_client.py -> main.py`

## Hyperedges (group relationships)
- **LLM Inference Pipeline** — intelligence_intent_parser_parse_intent, intelligence_response_generator_generate_response, intelligence_prompts_intent_parser_system, intelligence_prompts_response_generator_system_template, config_settings [INFERRED 0.85]
- **Message Routing and Intent Dispatch** — core_router_route_message, core_admin_handler_handle_admin, core_client_handler_handle_client, intelligence_intent_parser_parse_intent [EXTRACTED 0.95]
- **Handoff State Machine** — core_handoff_trigger_dynamic_handoff, core_handoff_start_handoff_from_admin, core_handoff_trigger_explicit_handoff_from_client, core_admin_handler_handle_admin, core_client_handler_handle_client [INFERRED 0.85]
- **Repository Pattern: Store Classes Wrapping ORM Models** — store_client_store_clientstore, store_provider_store_providerstore, store_session_store_sessionstore, store_conversation_store_conversationstore, models_orm_client, models_orm_provider, models_orm_session, models_orm_conversationstate [INFERRED 0.95]
- **Conflict Resolution Pipeline: resolve_slot + SessionStore + ClientStore** — scheduling_conflict_resolver_resolve_slot, store_session_store_sessionstore_get_conflict, store_session_store_sessionstore_get_free_slots, store_client_store_clientstore_get, scheduling_conflict_resolver_conflictresult [EXTRACTED 1.00]
- **Session Lifecycle: create, cancel, archive, reschedule** — store_session_store_sessionstore_create, store_session_store_sessionstore_cancel, store_session_store_sessionstore_archive, store_session_store_sessionstore_reschedule, models_orm_sessionarchive [INFERRED 0.95]

## Communities (34 total, 5 thin omitted)

### Community 0 - "ORM and Scheduling Core"
Cohesion: 0.22
Nodes (10): SessionArchive, cancel_day(), date, Session, SessionModel, SessionStore, date, datetime (+2 more)

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.17
Nodes (27): Intent-Driven Dispatch Pattern, Privacy Guard on Swap Messages, _check_client_status(), _check_schedule(), handle_admin(), _handle_admin_confirm(), _handle_book_session(), _handle_cancel_session() (+19 more)

### Community 2 - "Community 2"
Cohesion: 0.22
Nodes (7): handle_cold_inbound(), Session, route_message(), bootstrap_provider(), Session, ProviderStore, Provider

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.10
Nodes (15): ABC, get_async_redis(), get_redis(), ping_redis(), FastAPI, warmup_firewall(), lifespan(), websocket_endpoint() (+7 more)

### Community 6 - "Conversation History Store"
Cohesion: 0.15
Nodes (17): Conversation History Ring Buffer, ConversationState, _create_and_greet_client(), handle_new_client_intro(), handle_new_client_intro_clarification(), ClientStore, ConversationStore, Provider (+9 more)

### Community 7 - "New Client Onboarding"
Cohesion: 0.14
Nodes (31): Base, Client, Scheduling Conflict Resolution Strategy, Handoff Relay Pattern, Provider, Session, Session, Client (+23 more)

### Community 15 - "FastAPI App Entry"
Cohesion: 0.17
Nodes (15): BaseModel, FirewallResult, scan_input(), FirewallResult, scan_output(), FirewallResult, JudgeResult, MessageEnvelope (+7 more)

### Community 20 - "Python Requirements"
Cohesion: 0.14
Nodes (25): _client_id(), Phase 2 smoke tests. Requires: running Redis, seeded DB (provider + clients with, test_book_session_conflict_returns_error(), test_book_session_happy_path(), test_cancel_session_preserves_pre_cancel_status(), test_get_all_active_agents(), test_reschedule_session_checks_conflict(), get_all_active_agents() (+17 more)

### Community 22 - "DB Wipe Utility"
Cohesion: 0.30
Nodes (13): ClientStore, _client_dict(), create_client(), _db(), get_client(), get_client_by_phone(), list_clients(), Update one or more fields on an existing client. Only provided fields are change (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (13): break_between_sessions_mins, business_hours, end, start, business_type, conversation_timeout_mins, days_open, location_type (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (15): BaseSettings, Config, Settings, Exception, _format_history(), parse_intent(), _parse_json_response(), call_llm() (+7 more)

### Community 27 - "Community 27"
Cohesion: 0.26
Nodes (11): Any, _db(), get_conversation_state(), get_provider(), _provider_dict(), Reset conversation context for a phone number.     Clears pending context keys,, Get the current provider configuration., Update a single provider field.     Updatable fields: name, business_type, locat (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.25
Nodes (6): Base, engine, init_db(), ConversationSummary, test_db_migration(), test_parse_date_raises_on_garbage()

## Knowledge Gaps
- **28 isolated node(s):** `Any`, `WebSocket`, `business_type`, `location_type`, `travel_time_enabled` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `Conversation History Store` to `Admin Intent Dispatch`, `Community 2`, `Messaging Abstraction Layer`, `New Client Onboarding`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Why does `SessionStore` connect `ORM and Scheduling Core` to `Admin Intent Dispatch`, `Community 2`, `New Client Onboarding`, `Python Requirements`, `DB Wipe Utility`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `Session` connect `New Client Onboarding` to `ORM and Scheduling Core`, `Community 33`, `Community 2`, `Conversation History Store`, `DB Wipe Utility`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `ClientStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ClientStore` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `Session` (e.g. with `Client` and `ClientStore`) actually correct?**
  _`Session` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ConversationStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ConversationStore` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Provider` (e.g. with `Client` and `ClientStore`) actually correct?**
  _`Provider` has 24 INFERRED edges - model-reasoned connections that need verification._