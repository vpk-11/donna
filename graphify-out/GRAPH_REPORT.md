# Graph Report - donna  (2026-09-20)

## Corpus Check
- 67 files · ~17,100 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 407 nodes · 1199 edges · 29 communities (25 shown, 4 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 70 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ad2e74ac`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Admin Intent Dispatch|Admin Intent Dispatch]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Messaging Abstraction Layer|Messaging Abstraction Layer]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Nuke Script|Nuke Script]]
- [[_COMMUNITY_Seed Script|Seed Script]]
- [[_COMMUNITY_DB Session Factory|DB Session Factory]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Project README|Project README]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 22|Community 22]]

## God Nodes (most connected - your core abstractions)
1. `ConversationStore` - 50 edges
2. `ClientStore` - 48 edges
3. `Session` - 45 edges
4. `SessionStore` - 36 edges
5. `ProviderStore` - 35 edges
6. `CentralOrchestrator` - 33 edges
7. `ClientAgent` - 30 edges
8. `Provider` - 27 edges
9. `book_session()` - 23 edges
10. `Client` - 22 edges

## Surprising Connections (you probably didn't know these)
- `MutationGuardError` --uses--> `Session`  [INFERRED]
  db/database.py → models/orm.py
- `test_db_migration()` --calls--> `init_db()`  [EXTRACTED]
  tests/test_phase1.py → db/migrations.py
- `CallerNotAllowed` --uses--> `Client`  [INFERRED]
  donna_mcp/guard.py → models/orm.py
- `CallerNotAllowed` --uses--> `Session`  [INFERRED]
  donna_mcp/guard.py → models/orm.py
- `WebSocketConnectionManager` --uses--> `ConversationStore`  [INFERRED]
  messaging/websocket_client.py → store/conversation_store.py

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
Cohesion: 0.12
Nodes (23): get_redis(), Exception, build_context_from_summary(), should_summarize(), summarize_conversation(), trim_history(), call_llm(), call_llm_tools() (+15 more)

### Community 1 - "Admin Intent Dispatch"
Cohesion: 0.14
Nodes (12): Scheduling Conflict Resolution Strategy, Client, SessionArchive, ConflictResult, datetime, resolve_slot(), seed.sh Database Seed Script, SessionModel (+4 more)

### Community 2 - "Community 2"
Cohesion: 0.20
Nodes (13): BaseModel, Exception, Fail-closed scanners return a block result; fail-open scanners return None., scan_input(), _scanner_failed(), scan_output(), FirewallResult, MessageEnvelope (+5 more)

### Community 4 - "Messaging Abstraction Layer"
Cohesion: 0.08
Nodes (24): ABC, BaseSettings, Config, load_business_config(), Load config/business.json once, cache in-process. Static file, no     conversati, Settings, get_async_redis(), ping_redis() (+16 more)

### Community 5 - "Community 5"
Cohesion: 0.15
Nodes (20): Conversation History Ring Buffer, ConversationState, ConversationStore, Called after every Donna send. Updates last_donna_message and appends to history, Clear pending state but preserve history and protected keys (prefixed _)., Append a turn to conversation history. role is 'user' or 'donna'., test_record_donna_message_sets_last_message_and_history(), append_conversation_history() (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (20): acting_as(), kind: system | orchestrator | admin | agent (agent requires the client's phone)., Live end-to-end checks against a local Ollama model.  Run: DONNA_LIVE=1 DONNA_MO, Recorder, send(), state(), test_admin_agent_answers_and_acts(), test_book_request_goes_to_admin_then_admin_confirms() (+12 more)

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (20): RuntimeError, _agent(), _boom(), clients(), _messaging(), test_cold_agent_may_create_only_its_own_client(), test_identity_spoof_scanner_error_fails_closed(), test_other_clients_context_never_reaches_llm() (+12 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (29): Base, ConversationSummary, Session, ClientAgent, Another client needs something from this client. This agent asks its own client, The orchestrator reports on a request this agent made. Tell the own client., One LLM agent per client conversation: its own prompt, history and tool loop., History that reaches any prompt. Only entries owned by this agent's client. (+21 more)

### Community 19 - "Project README"
Cohesion: 0.13
Nodes (14): 1. Create the environment, 2. Start Redis, 3. Start an LLM, 4. Set environment variables, 5. Run it, 6. Seed test data, Architecture, Changelog (+6 more)

### Community 20 - "Community 20"
Cohesion: 0.09
Nodes (31): Any, Base, engine, MutationGuardError, _reject_writes_outside_mcp(), init_db(), CallerNotAllowed, _check() (+23 more)

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (44): Decorator for async methods: run the whole method under a caller identity.     k, runs_as(), obj(), JSON schema for an object whose properties are all required., _client_id(), Phase 2 smoke tests. Requires: running Redis, seeded DB (provider + clients with, test_book_session_conflict_returns_error(), test_book_session_happy_path() (+36 more)

## Knowledge Gaps
- **18 isolated node(s):** `Config`, `nuke.sh script`, `seed.sh script`, `Architecture`, `1. Create the environment` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationStore` connect `Community 5` to `Community 0`, `Messaging Abstraction Layer`, `Community 7`, `Community 8`, `Community 15`, `Community 20`, `Community 22`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Why does `ClientStore` connect `Admin Intent Dispatch` to `Community 0`, `Messaging Abstraction Layer`, `Community 6`, `Community 7`, `Community 8`, `Community 15`, `Community 20`, `Community 22`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `Session` connect `Community 15` to `Community 0`, `Admin Intent Dispatch`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 20`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ConversationStore` (e.g. with `WebSocket` and `WebSocketConnectionManager`) actually correct?**
  _`ConversationStore` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ClientStore` (e.g. with `Recorder` and `AdminAgent`) actually correct?**
  _`ClientStore` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Session` (e.g. with `MutationGuardError` and `CallerNotAllowed`) actually correct?**
  _`Session` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `SessionStore` (e.g. with `AdminAgent` and `ClientAgent`) actually correct?**
  _`SessionStore` has 7 INFERRED edges - model-reasoned connections that need verification._