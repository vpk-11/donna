# Graph Report - donna  (2026-06-17)

## Corpus Check
- 69 files · ~19,017 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 403 nodes · 1108 edges · 32 communities (27 shown, 5 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 169 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4dc53921`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_ORM and Scheduling Core|ORM and Scheduling Core]]
- [[_COMMUNITY_Admin Intent Dispatch|Admin Intent Dispatch]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Messaging Abstraction Layer|Messaging Abstraction Layer]]
- [[_COMMUNITY_Community 5|Community 5]]
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

## God Nodes (most connected - your core abstractions)
1. `ClientStore` - 42 edges
2. `Session` - 40 edges
3. `ConversationStore` - 37 edges
4. `Provider` - 33 edges
5. `SessionStore` - 33 edges
6. `CentralOrchestrator` - 32 edges
7. `ClientAgent` - 26 edges
8. `ProviderStore` - 26 edges
9. `handle_admin()` - 24 edges
10. `generate_response()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `WebSocket` --uses--> `CentralOrchestrator`  [INFERRED]
  main.py → orchestrator/central.py
- `Provider` --uses--> `ConversationStore`  [INFERRED]
  core/admin_handler.py → store/conversation_store.py
- `Provider` --uses--> `ProviderStore`  [INFERRED]
  core/admin_handler.py → store/provider_store.py
- `Session` --uses--> `ConversationStore`  [INFERRED]
  core/admin_handler.py → store/conversation_store.py
- `Session` --uses--> `ProviderStore`  [INFERRED]
  core/admin_handler.py → store/provider_store.py

## Import Cycles
- 1-file cycle: `store/session_store.py -> store/session_store.py`
- 1-file cycle: `main.py -> main.py`
- 1-file cycle: `utils/time_utils.py -> utils/time_utils.py`
- 1-file cycle: `scheduling/conflict_resolver.py -> scheduling/conflict_resolver.py`
- 2-file cycle: `main.py -> messaging/websocket_client.py -> main.py`

## Hyperedges (group relationships)
- **LLM Inference Pipeline** — intelligence_intent_parser_parse_intent, intelligence_response_generator_generate_response, intelligence_prompts_intent_parser_system, intelligence_prompts_response_generator_system_template, config_settings [INFERRED 0.85]
- **Message Routing and Intent Dispatch** — core_router_route_message, core_admin_handler_handle_admin, core_client_handler_handle_client, intelligence_intent_parser_parse_intent [EXTRACTED 0.95]
- **Handoff State Machine** — core_handoff_trigger_dynamic_handoff, core_handoff_start_handoff_from_admin, core_handoff_trigger_explicit_handoff_from_client, core_admin_handler_handle_admin, core_client_handler_handle_client [INFERRED 0.85]
- **Repository Pattern: Store Classes Wrapping ORM Models** — store_client_store_clientstore, store_provider_store_providerstore, store_session_store_sessionstore, store_conversation_store_conversationstore, models_orm_client, models_orm_provider, models_orm_session, models_orm_conversationstate [INFERRED 0.95]
- **Conflict Resolution Pipeline: resolve_slot + SessionStore + ClientStore** — scheduling_conflict_resolver_resolve_slot, store_session_store_sessionstore_get_conflict, store_session_store_sessionstore_get_free_slots, store_client_store_clientstore_get, scheduling_conflict_resolver_conflictresult [EXTRACTED 1.00]
- **Session Lifecycle: create, cancel, archive, reschedule** — store_session_store_sessionstore_create, store_session_store_sessionstore_cancel, store_session_store_sessionstore_archive, store_session_store_sessionstore_reschedule, models_orm_sessionarchive [INFERRED 0.95]

## Communities (32 total, 5 thin omitted)

### Community 0 - "ORM and Scheduling Core"
Cohesion: 0.10
Nodes (41): Base, Scheduling Conflict Resolution Strategy, Provider, Session, Session, Client, ConversationStore, Provider (+33 more)

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.12
Nodes (34): BaseSettings, Config, Settings, _check_client_status(), _check_schedule(), handle_admin(), _handle_admin_confirm(), _handle_book_session() (+26 more)

### Community 2 - "Community 2"
Cohesion: 0.19
Nodes (13): should_summarize(), summarize_conversation(), trim_history(), evaluate(), _llm_judge(), IntentResult, JudgeResult, test_cancel_request_notifies_admin() (+5 more)

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.08
Nodes (20): ABC, CentralOrchestrator, handle_cold_inbound(), Session, route_message(), FastAPI, warmup_firewall(), get_orchestrator() (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (16): ClientAgent, CentralOrchestrator, ClientStore, ConversationStore, Session, SessionStore, _make_client(), _make_messaging() (+8 more)

### Community 6 - "Conversation History Store"
Cohesion: 0.10
Nodes (25): Any, Base, engine, init_db(), get_async_redis(), get_redis(), ping_redis(), ConversationSummary (+17 more)

### Community 7 - "New Client Onboarding"
Cohesion: 0.15
Nodes (17): Conversation History Ring Buffer, ConversationState, _create_and_greet_client(), handle_new_client_intro(), handle_new_client_intro_clarification(), ClientStore, ConversationStore, Provider (+9 more)

### Community 15 - "FastAPI App Entry"
Cohesion: 0.14
Nodes (20): BaseModel, FirewallResult, scan_input(), scan_output(), FirewallResult, FirewallResult, JudgeResult, MessageEnvelope (+12 more)

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
Cohesion: 0.28
Nodes (8): IntentResult, ClientAgent, Client, ClientStore, ConversationStore, Provider, Session, SessionStore

## Knowledge Gaps
- **26 isolated node(s):** `FirewallResult`, `Client`, `Client`, `Provider`, `Any` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `New Client Onboarding` to `ORM and Scheduling Core`, `Admin Intent Dispatch`, `Messaging Abstraction Layer`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Why does `CentralOrchestrator` connect `Community 5` to `Community 26`, `Messaging Abstraction Layer`, `FastAPI App Entry`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `ClientAgent` connect `Community 26` to `Community 5`, `FastAPI App Entry`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `ClientStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ClientStore` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `Session` (e.g. with `ClientStore` and `ConversationState`) actually correct?**
  _`Session` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ConversationStore` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`ConversationStore` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `Provider` (e.g. with `ClientStore` and `ConversationStore`) actually correct?**
  _`Provider` has 23 INFERRED edges - model-reasoned connections that need verification._