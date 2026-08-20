# Graph Report - donna  (2026-08-20)

## Corpus Check
- 70 files · ~21,277 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 375 nodes · 1307 edges · 29 communities (25 shown, 4 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 59 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `58322d0e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Admin Intent Dispatch|Admin Intent Dispatch]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Messaging Abstraction Layer|Messaging Abstraction Layer]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Nuke Script|Nuke Script]]
- [[_COMMUNITY_Seed Script|Seed Script]]
- [[_COMMUNITY_DB Session Factory|DB Session Factory]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Project README|Project README]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 22|Community 22]]

## God Nodes (most connected - your core abstractions)
1. `ConversationStore` - 67 edges
2. `ClientStore` - 62 edges
3. `Session` - 58 edges
4. `SessionStore` - 46 edges
5. `generate_response()` - 41 edges
6. `Provider` - 38 edges
7. `ProviderStore` - 37 edges
8. `CentralOrchestrator` - 35 edges
9. `ClientAgent` - 31 edges
10. `Client` - 25 edges

## Surprising Connections (you probably didn't know these)
- `ClientAgent` --uses--> `Client`  [INFERRED]
  orchestrator/agent.py → models/orm.py
- `ClientAgent` --uses--> `Provider`  [INFERRED]
  orchestrator/agent.py → models/orm.py
- `ClientAgent` --uses--> `Session`  [INFERRED]
  orchestrator/agent.py → models/orm.py
- `ClientAgent` --uses--> `IntentResult`  [INFERRED]
  orchestrator/agent.py → models/schemas.py
- `ClientAgent` --uses--> `ClientStore`  [INFERRED]
  orchestrator/agent.py → store/client_store.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **LLM Inference Pipeline** — intelligence_intent_parser_parse_intent, intelligence_response_generator_generate_response, intelligence_prompts_intent_parser_system, intelligence_prompts_response_generator_system_template, config_settings [INFERRED 0.85]
- **Message Routing and Intent Dispatch** — core_router_route_message, core_admin_handler_handle_admin, core_client_handler_handle_client, intelligence_intent_parser_parse_intent [EXTRACTED 0.95]
- **Handoff State Machine** — core_handoff_trigger_dynamic_handoff, core_handoff_start_handoff_from_admin, core_handoff_trigger_explicit_handoff_from_client, core_admin_handler_handle_admin, core_client_handler_handle_client [INFERRED 0.85]
- **Repository Pattern: Store Classes Wrapping ORM Models** — store_client_store_clientstore, store_provider_store_providerstore, store_session_store_sessionstore, store_conversation_store_conversationstore, models_orm_client, models_orm_provider, models_orm_session, models_orm_conversationstate [INFERRED 0.95]
- **Conflict Resolution Pipeline: resolve_slot + SessionStore + ClientStore** — scheduling_conflict_resolver_resolve_slot, store_session_store_sessionstore_get_conflict, store_session_store_sessionstore_get_free_slots, store_client_store_clientstore_get, scheduling_conflict_resolver_conflictresult [EXTRACTED 1.00]
- **Session Lifecycle: create, cancel, archive, reschedule** — store_session_store_sessionstore_create, store_session_store_sessionstore_cancel, store_session_store_sessionstore_archive, store_session_store_sessionstore_reschedule, models_orm_sessionarchive [INFERRED 0.95]

## Communities (29 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.32
Nodes (7): Session, CentralOrchestrator, ClientStore, ConversationStore, Session, SessionStore, ClientStore

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.12
Nodes (35): _create_and_greet_client(), handle_new_client_intro(), handle_new_client_intro_clarification(), _check_client_status(), _check_schedule(), handle_admin(), _handle_admin_confirm(), _handle_book_session() (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.10
Nodes (34): BaseModel, BaseSettings, Config, Settings, Exception, scan_input(), scan_output(), build_context_from_summary() (+26 more)

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.09
Nodes (17): ABC, FastAPI, warmup_firewall(), _cli_main(), Donna's CLI entrypoint. One process, one command:      python main.py --admin, _run_admin(), _wait_for_health(), MessagingClient (+9 more)

### Community 5 - "Community 5"
Cohesion: 0.14
Nodes (17): Base, Conversation History Ring Buffer, datetime, IntentResult, ConversationState, ConversationSummary, ClientAgent, ClientStore (+9 more)

### Community 8 - "Community 8"
Cohesion: 0.26
Nodes (13): register_client_names(), _client_dict(), create_client(), _db(), get_client(), get_client_by_phone(), list_clients(), Update one or more fields on an existing client. Only provided fields are change (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.56
Nodes (8): _make_client(), _make_messaging(), _make_provider(), test_client_agent_instantiates(), test_orchestrator_instantiates(), test_orchestrator_routes_admin(), test_orchestrator_spawns_agent_for_client(), test_retire_agent()

### Community 19 - "Project README"
Cohesion: 0.13
Nodes (14): 1. Create the environment, 2. Start Redis, 3. Start an LLM, 4. Set environment variables, 5. Run it, 6. Seed test data, Architecture, Changelog (+6 more)

### Community 20 - "Community 20"
Cohesion: 0.07
Nodes (35): Any, Client, Base, engine, init_db(), get_async_redis(), get_redis(), ping_redis() (+27 more)

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (38): Scheduling Conflict Resolution Strategy, load_business_config(), Load config/business.json once, cache in-process. Static file, no     conversati, SessionArchive, ConflictResult, datetime, resolve_slot(), cancel_day() (+30 more)

## Knowledge Gaps
- **18 isolated node(s):** `Architecture`, `1. Create the environment`, `2. Start Redis`, `3. Start an LLM`, `4. Set environment variables` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `Community 5` to `Community 0`, `Admin Intent Dispatch`, `Community 2`, `Messaging Abstraction Layer`, `Community 20`, `Community 22`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Why does `ClientStore` connect `Community 0` to `Admin Intent Dispatch`, `Community 2`, `Messaging Abstraction Layer`, `Community 5`, `Community 8`, `Community 20`, `Community 22`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `SessionStore` connect `Community 22` to `Community 0`, `Admin Intent Dispatch`, `Community 2`, `Community 5`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `ConversationStore` (e.g. with `WebSocket` and `WebSocketConnectionManager`) actually correct?**
  _`ConversationStore` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `ClientStore` (e.g. with `ClientAgent` and `CentralOrchestrator`) actually correct?**
  _`ClientStore` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Session` (e.g. with `ClientAgent` and `CentralOrchestrator`) actually correct?**
  _`Session` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `SessionStore` (e.g. with `ClientAgent` and `CentralOrchestrator`) actually correct?**
  _`SessionStore` has 7 INFERRED edges - model-reasoned connections that need verification._