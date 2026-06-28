# QBot3 — Isolation Plan

Status: draft  
Date: 2026-05-28  
Goal: parallel Albert-first architecture without touching production QBot2.

---

## 1. File Audit — KEEP_AS_TOOL

Files that provide DB access, connectors, readers, writers, or tool implementations.
These are pure data/infrastructure layers — no intent routing, no slot filling.

| File | Purpose | Lines |
|---|---|---|
| `api_db.py` | DB init, migration runner | 508 |
| `db.py` | Connection pool, query helpers | 553 |
| `qbot_nutrition_db.py` | Nutrition DB models | 674 |
| `qbot_nutrition_tools.py` | Nutrition read/write tools | 442 |
| `qbot_calendar_core.py` | Calendar DB models + `build_snapshot` | 1253 |
| `qbot_planning_memory.py` | Planning facts DB | 427 |
| `qbot_wellness_store.py` | Wellness/sleep DB store | 847 |
| `qbot_health_db.py` | Health events DB | 405 |
| `qbot_energy_store.py` | Energy/Garmin store | 176 |
| `qbot_garage_tools.py` | Garage raw DB tools | 786 |
| `qbot_route_tools.py` | RWGPS read tools | 1202 |
| `qbot_integration_tools.py` | Xert/Intervals/weather/Garmin connectors | 1578 |
| `qbot_garmin_history.py` | Garmin history reader | 204 |
| `qbot_readiness.py` | Readiness calculator | 105 |
| `qbot_recovery.py` | Recovery/anomaly logic | 248 |
| `qbot_report_tools.py` | Report generators | 1062 |
| `qbot_roadmap_runner.py` | Roadmap runner (project mgmt tool) | 1789 |
| `qbot_artifact_tools.py` | Artifact CRUD tools | 204 |
| `qbot_assistant_inbox.py` | Inbox tool | 223 |
| `qbot_tool_registry.py` | Central tool registry (TOOLS, TOOLS_META) | 1920 |
| `qbot_tools.py` | QBot status/health/service tools | 705 |
| `qbot_operator_tools.py` | Operator readiness/smoke tools | 700 |
| `qbot_ops_tools.py` | Ops tools (backup, errors, logs) | 1241 |
| `qbot_telegram_tools.py` | Telegram config/audit/transport tools (NOT agent_chat) | 1436 |
| `qbot_telegram_client.py` | Telegram HTTP client (sendMessage etc.) | 96 |
| `qbot_mcp_adapter.py` | MCP adapter + action_exec handlers | 1905 |
| `qbot_mcp_client.py` | MCP HTTP client | 124 |
| `qgpt_client.py` | LLM client (OpenAI + Anthropic) | 211 |
| `qbot_config.py` | Config loader | 78 |
| `qbot_cache.py` | Simple cache | 58 |
| `garmin_auth.py` | Garmin auth flow | 113 |
| `hammerhead_auth.py` | Hammerhead auth | 250 |
| `gate_hikconnect.py` | Gate API connector | 254 |
| `qbot_task_queue.py` | Task queue | 206 |
| `qbot_health_advisor.py` | Health advice engine | 430 |
| `qbot_legacy_*.py` (8 files) | Legacy parity/wrapper/shadow tools | ~3500 total |
| `qbot_external_llm_tools.py` | External LLM tool connectors | 571 |
| `sql/` | SQL migration scripts | — |

## 2. File Audit — LEGACY_DO_NOT_USE_IN_QBOT3

Files containing intent routing, regex classification, slot filling, domain handlers, or query processing that must NOT be called from QBot3.

| File | Why Legacy | Lines |
|---|---|---|
| `qbot_query_router.py` | **4950 lines of mixed intent routing.** Contains `classify_intent()`, `_INTENT_PATTERNS` (regex routing), `_init_dispatch()`, `canonicalize_query_intent()`, `_llm_classify_intent()`, `_heuristic_canonicalize()`, `_parse_nutrition_draft()`, `_parse_event_draft()`, `_parse_reminder_draft()`, `_match_meal_template()`, `_alias_match_template()`. The `query()` function at line 4853 is the legacy router entrypoint. QBot3 must NOT call `query()` — it calls `orchestrate_query()` directly. | **4962** |
| `qbot_query_processor.py` | `process_query()` function — the old Telegram agent chat backend. Contains intent-driven tool selection, slot filling, and multi-tool orchestration. QBot3 bypasses this entirely. | 1551 |
| `qbot_qcal_telegram.py` | Telegram conversational gateway. Has its own draft/confirm flow, `_parse_event_draft`, `_ALLOWED_ACTIONS` for Telegram. QBot3 Telegram is thin transport — no domain logic. | 416 |
| `qbot_capabilities.py` | Capability registry with keyword matching, domain mapping. QBot3 Albert decides capabilities dynamically. | 496 |
| `qbot_nutrition_parser.py` | Regex nutrition text parser. Albert in QBot3 uses structured tools + DB, not regex from raw text. | 394 |
| `qbot_nutrition_planner.py` | Nutrition planning logic with domain rules. QBot3: Albert plans with data. | 287 |
| `qbot_coach.py` | Coaching advice with hardcoded rules. Albert generates advice from data. | 287 |
| `qbot_context_resolver.py` | Context resolution with heuristics. QBot3: Albert resolves from conversation state. | 232 |
| `qbot_llm_planner.py` | LLM planner — superseded by `qbot_orchestrator.py` Albert planner. | 395 |
| `qbot_query_planner.py` | Query planner — superseded by Orchestrator. | 623 |
| `qbot_report_status.py` | Status report generator with legacy assumptions. | 99 |
| `daily_report.py` | Full daily report with legacy scheduling. | 649 |
| `ride_report.py` | Legacy ride report generator. | 969 |
| `email_reply_processor.py` | Email reply with intent classification. | 479 |
| `email_template.py` | Email templates with legacy assumptions. | 901 |
| `telegram_reply_processor.py` | Old Telegram reply handler (not used). | 309 |
| `telegram_reply_processor.py` | Duplicate/old Telegram code. | 309 |

## 3. File Audit — UNKNOWN_REVIEW

Files that contain both infrastructure and decision logic, or whose role in QBot3 needs design review.

| File | Why Review | Lines |
|---|---|---|
| `qbot_orchestrator.py` | **Core of QBot3.** Contains Albert's plan, execute, and final answer. Currently mixed with QBot2 keeps. For QBot3, extract the orchestrator core and remove dependency on `qbot_query_router._READER_REGISTRY`, `_TOOL_DISPATCH`, `_resolve_date_context`, etc. | 1330 |
| `qbot_api.py` | FastAPI layer. Routes serve both QBot2 and QBot3. Need to separate: `/mcp/` (QBot3), `/telegram/` (thin adapter), legacy endpoints. | 1118 |
| `qbot_mcp_adapter.py` | MCP adapter with action_exec handlers. Most is KEEP, but `_dispatch_local_qbot_tool` (line 349) bridges to legacy dispatch. QBot3 should dispatch through Albert only. | 1905 |
| `qbot_tools.py` | Contains `_tool_qbot_query` which bridges to `qbot_query_router.query`. QBot3 needs its own query tool that calls `orchestrate_query` directly. | 705 |
| `qbot_telegram_tools.py` | `_tool_qbot_telegram_agent_chat` (line 722) is legacy. QBot3 replaces with thin `telegram_adapter.py`. Telegram config/transport tools are KEEP. | 1436 |
| `qbot_health_cli.py` | CLI for health features — review whether Albert should handle health. | 500 |
| `qbot_nutrition_cli.py` | CLI for nutrition — review whether CLI is needed in QBot3. | 1034 |
| `qbot_calendar_cli.py` | CLI for calendar — review. | 260 |
| `qbot_planning_cli.py` | CLI for planning — review. | 141 |
| `qbot_qcal_cli.py` | QCal CLI — review. | 326 |
| `qbot_ask_cli.py` | Ask CLI — review. | 484 |
| `qgpt_chat_terminal.py` | GPT terminal — review. | 45 |
| `qlab_replay_export.py` | QLab export — review if still needed. | 237 |
| `deploy_ride.py` | Ride deploy tool — belongs in tools/. | 479 |
| `sync_nutrition.py` | Nutrition sync — belongs in tools/. | 68 |
| `mcp_server.py` | Standalone MCP server (old). QBot3 uses FastAPI + adapter. | 3152 |
| `qbot_qlab_server.py` | QLab standalone server — review. | 600 |
| `weekly_review.py` | Weekly review generator — review. | 149 |
| `monitor.py` | System monitor — tool. | 73 |

## 4. Proposed QBot3 Directory Structure

```
app/qbot3/
├── __init__.py
│
├── agent_runtime.py          # Albert runtime: orchestrate_query(), _final_answer(), plan/execute loop
│                             # Pure Albert — no legacy router imports. Uses tool_registry + state_store.
│
├── tool_registry.py          # QBot3 tool registry. Wraps existing TOOLS/TOOLS_META from qbot_tool_registry.
│                             # Exposes {name: {callable, schema, safety}} for Albert.
│
├── state_store.py            # Conversation state, user context, planning facts.
│                             # Wraps qbot_planning_memory, qbot_cache, plus new conversation store.
│
├── safety.py                 # Write safety, idempotency, audit logging, doc allowlist.
│                             # Extracted from qbot_mcp_adapter.py action_exec handlers.
│
├── adapters/
│   ├── __init__.py
│   ├── telegram_adapter.py   # Thin Telegram transport. Input → agent_runtime.orchestrate_query() → output.
│   │                         # NO domain logic, NO intent routing, NO slot filling.
│   │                         # Adds metadata: source_channel=telegram, chat_id, timezone.
│   │                         # Renders final_llm.answer as sendMessage.
│   │
│   └── mcp_adapter.py        # Thin MCP adapter for QBot3. Only two tools:
│                             #   qbot.query → agent_runtime.orchestrate_query()
│                             #   qbot.action_execute → safety.exec_action()
│                             # NO dispatch_local_qbot_tool, NO legacy bridges.
│
├── tools/
│   ├── __init__.py
│   ├── db_tools.py           # DB access wrappers. Wraps api_db, db.py, qbot_nutrition_db, etc.
│   ├── calendar_tools.py     # QCal event/reminder read/write tools.
│   ├── nutrition_tools.py    # Nutrition DB read/write tools (template lookup, meal log, catalog).
│   ├── connector_tools.py    # External connector wrappers: Garmin, Xert, Intervals, RWGPS, weather.
│   ├── garage_tools.py       # Garage DB read tools.
│   ├── wellness_tools.py     # Wellness/sleep DB read tools.
│   ├── planning_tools.py     # Planning facts tools.
│   ├── report_tools.py       # Report generators.
│   └── docs_tools.py         # Canonical document reader tools.
│
└── migrations/
    └── qbot3_setup.sql       # Any new tables for QBot3 state (if needed).
```

## 5. Migration Plan — No Production Impact

### Phase A: Directory + Adapter (hours)
1. Create `app/qbot3/` directory structure
2. Create `agent_runtime.py` — copy `orchestrate_query()`, `_final_answer()`, `_execute_reader()` from `qbot_orchestrator.py`
   - Remove all `import qbot_query_router as qr` dependencies
   - Use `qbot3/tool_registry.py` instead of `_READER_REGISTRY`/`_TOOL_DISPATCH`
   - Use `qbot3/state_store.py` instead of `_resolve_date_context`
3. Create `tool_registry.py` — wrap `qbot_tool_registry.TOOLS` + `TOOLS_META`
   - Add QBot3-only reader definitions
   - NO legacy readers from `_READER_REGISTRY`
4. Create `safety.py` — extract write safety from `qbot_mcp_adapter.py`
   - Idempotency, audit, doc allowlist, action_execute allowlist
5. Create `mcp_adapter.py` in `adapters/` — thin two-tool MCP
   - `qbot.query` → `agent_runtime.orchestrate_query()`
   - `qbot.action_execute` → `safety.exec_action()`

### Phase B: Wire Without Cutover (days)
6. Add `QBOT3_ENABLED=1` env flag (parallel to `QBOT_LLM_ORCHESTRATOR=1`)
7. In `qbot_api.py`, add:
   ```python
   if os.getenv("QBOT3_ENABLED") == "1":
       from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
       return handle_qbot3_mcp(payload)
   ```
8. Run side-by-side: QBot2 handles production, QBot3 handles test queries
9. `tools/list` shows same 2 tools, but QBot3 backend

### Phase C: Shadow Mode (weeks)
10. Route 10% of production qbot.query to QBot3 (shadow), compare results
11. Fix gaps without touching QBot2

### Phase D: Cutover (when QBot3 passes all acceptance tests)
12. Flip `QBOT3_ENABLED=1` for 100%
13. Remove `QBOT_LLM_ORCHESTRATOR=1` flag
14. Archive QBot2 legacy modules

## 6. Risks

| Risk | Mitigation |
|---|---|
| `qbot_orchestrator.py` depends on `qbot_query_router._READER_REGISTRY`, `_TOOL_DISPATCH`, `_resolve_date_context` | Extract those into `qbot3/tool_registry.py` and `qbot3/state_store.py`. Don't import from legacy router. |
| `_execute_reader()` has two code paths (tool_registry + reader_registry). Reader_registry path calls `qr._TOOL_DISPATCH.get(tool)`. | QBot3 tool_registry wraps both paths into one unified lookup. |
| `action_exec` handlers in `qbot_mcp_adapter.py` are 800+ lines of domain logic (nutrition, qcal, docs). | Extract into `safety.py` + domain-specific tool files in `qbot3/tools/`. |
| Legacy `_tool_qbot_query` in `qbot_tools.py` bridges to `qbot_query_router.query`. QBot3 must not call this. | QBot3 mcp_adapter calls `agent_runtime.orchestrate_query()` directly, NOT `_tool_qbot_query`. |
| No existing tests for qbot3/ | First 5 MVP tests (see section 7) become the CI gate. |
| DB schema might need small adjustments for QBot3 state (conversation store, trace store). | Add to `migrations/qbot3_setup.sql`, run separately, no existing table changes. |

## 7. First 5 MVP Tests

Run these against QBot3 **before** any cutover. All must pass.

### Test 1: Raw query passthrough
```
Input: "status qbot"
Expected: QBot process running... (same as QBot2)
Check: orchestrator.name == "Albert", orchestrator.enabled == True
Check: NO qbot_query_router imports in traceback
```

### Test 2: Nutrition with catalog (no legacy drafting)
```
Input: "dodaj białko z wodą z katalogu posiłków"
Expected: action_draft with template_id from DB
Check: meal_name == "Białko z wodą", template_id present
Check: NO _parse_nutrition_draft() in call chain
```

### Test 3: Calendar events (no _parse_event_draft)
```
Input: "jakie mam wydarzenia w kalendarzu?"
Expected: calendar_events + reminders from DB
Check: NO _parse_event_draft() in call chain
Check: answer contains event titles from DB
```

### Test 4: Noisy input stripped
```
Input: "Dodaj do dzisiejszego spożycia 0,5 kg truskawek. Przygotuj action_draft nutrition_log_add."
Expected: meal_name clean ("0,5 kg truskawek")
Check: NO "action_draft" in meal_name
Check: NO "nutrition_log_add" in meal_name
```

### Test 5: tools/list unchanged
```
Input: tools/list (MCP)
Expected: exactly 2 tools: ["qbot.query", "qbot.action_execute"]
Check: qbot.query description says "przekaż oryginalne pytanie, NIE enrichuj"
```

## 8. Summary of Architecture Change

```
QBot2 (production):               QBot3 (parallel):
┌─────────────────────┐           ┌──────────────────────┐
│ Telegram (own brain)│           │ Telegram (thin UI)   │
│ MCP (procedural)    │           │ MCP (thin transport) │
│ query_router (regex)│           │                      │
│ query_processor     │           │ Albert Agent Runtime │
│ _TOOL_DISPATCH      │           │  (plan → execute →   │
│ _INTENT_PATTERNS    │           │   final answer)      │
│ slot_filling        │           │                      │
│ domain handlers     │           │ Tool Registry        │
│                     │           │  (DB + connectors)   │
│         ↓           │           │                      │
│  DB + Connectors    │           │  DB + Connectors     │
│  (same PostgreSQL)  │           │  (same PostgreSQL)   │
└─────────────────────┘           └──────────────────────┘
```

QBot3 removes: intent classification, regex routing, slot filling, domain handlers, Telegram domain logic, legacy query processor, capability keyword mapping.

QBot3 keeps: all DB tables, all connectors, all readers/writers as tools, PostgreSQL, safety/idempotency, audit.

QBot3 adds: Albert-first orchestration, structured tool registry, thin transport adapters, trace/debug, canonical task extraction.
