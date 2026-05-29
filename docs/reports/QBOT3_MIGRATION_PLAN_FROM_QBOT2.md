# QBot3 Migration Plan — from QBot2

Date: 2026-05-28
Status: draft

## What stays from QBot2

- PostgreSQL schema and all tables
- All connectors: Garmin, Xert, Intervals, RWGPS, weather, Cronometer
- All DB readers/writers: nutrition, calendar, reminders, planning, wellness, garage
- `qbot_tool_registry.py` — TOOLS and TOOLS_META (wrapped by QBot3)
- `qgpt_client.py` — LLM client (wrapped by QBot3 LLM providers)
- Safety: idempotency, audit tables (`qbot_doc_write_audit`, `nutrition_write_audit`, `qcal_write_audit`)
- `qbot_legacy_*.py` — tool implementations (used by QBot2 only)
- All environment variables and config

## What QBot3 takes over

| Layer | QBot2 | QBot3 |
|---|---|---|
| Brain | `qbot_query_router.query()` → `classify_intent()` + `_TOOL_DISPATCH` | `qbot3.agent_runtime.orchestrate_query()` → LLM plan → tool registry |
| Planning | Regex patterns + heuristic + LLM classifier | LLM-only via provider interface |
| Tool selection | `_READER_REGISTRY` + `_TOOL_DISPATCH` | `qbot3/tool_registry.py` — explicit capability definitions |
| Write safety | Mixed: some writes in MCP adapter, some in routers | Centralized in `qbot3/safety.py` |
| Memory | None (planning_facts only) | `qbot3/memory.py` — JSONL-based |
| Provider | Hardcoded OpenAI + Anthropic | Provider-agnostic via `ALBERT_LLM_PROVIDER` ENV |
| MCP | `handle_mcp_request()` + `_dispatch_local_qbot_tool()` | `qbot3/adapters/mcp_adapter.py` — exactly 2 tools |
| Telegram | `_tool_qbot_telegram_agent_chat()` — own brain | Transparent adapter (planned) |
| Error codes | Mixed/undefined | `qbot3/errors.py` — 13 standard codes |

## What is LEGACY (QBot2 only, DO NOT CALL from QBot3)

- `qbot_query_router.py` — all of it (4962 lines)
- `qbot_query_processor.py` — `process_query()`
- `qbot_qcal_telegram.py` — Telegram domain logic
- `qbot_capabilities.py` — keyword-based capability registry
- `qbot_nutrition_parser.py` — regex nutrition parser
- `qbot_llm_planner.py` — superseded
- `qbot_query_planner.py` — superseded
- `daily_report.py`, `ride_report.py` — legacy generators
- `telegram_reply_processor.py` — dead code

## How to disable legacy MCP micro-tools

Currently exposed via `/mcp/`: only `qbot.query` and `qbot.action_execute`.
Legacy micro-tools were removed in earlier builds — no action needed.

## How to switch Telegram to QBot3

1. Ensure `QBOT3_ENABLED=1` in `.env.local`
2. In `qbot_api.py` telegram webhook, change `_tool_qbot_telegram_agent_chat` to `_tool_qbot_query` (natural language path)
3. Test: send natural language messages via Telegram, verify they go through Albert

Current status: Natural language path already uses `_tool_qbot_query` (changed in earlier fix).

## How to switch qbot.query to QBot3

Set `QBOT3_ENABLED=1` in `.env.local`. The `/mcp/` POST handler detects this and calls `qbot3/adapters/mcp_adapter.handle_qbot3_mcp()` instead of the legacy `handle_mcp_request()`.

Rollback: remove `QBOT3_ENABLED=1` and restart.

## Migration Phases

### Phase 1: Mock Tests ✅ (done)
- `ALBERT_LLM_PROVIDER=mock` — all plan/answer logic through mock provider
- Verified: 12/12 contract tests pass, zero legacy imports, zero procedural handlers
- 35 capabilities registered, all compile and load

### Phase 2: Local MCP Tests ✅ (done)
- `ALBERT_LLM_PROVIDER=openai` (wraps qgpt_client)
- 2 public MCP tools verified: `qbot.query` + `qbot.action_execute`
- All write actions produce P4-standardized action_draft
- Dry run supported for all write actions
- Safety layer validates: action_type allowlist, idempotency, confirm flag

### Phase 3: OpenAI UI Tests ⏳ (next)
- Test qbot.query from ChatGPT/OpenAI UI
- Verify: no micro-tools visible, qbot.query returns structured results with trace/orchestrator metadata
- Verify action_draft is returned as structuredContent (not raw text)

### Phase 4: Telegram Read-Only ✅ (done)
- Natural language Telegram path already uses `_tool_qbot_query` → QBot3 agent_runtime
- Fallback to QBot2 if `QBOT3_ENABLED=0`
- Documented in `docs/QBOT3_TELEGRAM_TRANSPARENT_UI.md`

### Phase 5: Telegram Write Draft ⏳
- action_draft flows through Telegram (same path as query)
- No "dodano/zapisano" claims — draft-only
- Dedicated `adapters/telegram_adapter.py` planned but not critical

### Phase 6: action_execute Production ⏳
- `safety.py` validates: action_type allowlist, idempotency, confirm
- Dry run works for all action types
- Real write execution needs handler wiring for nutrition/calendar/reminder
- Currently returns mock "write executed" for non-doc actions

### Phase 7: Disable Legacy Micro-Tools ✅ (done)
- QBot2 MCP adapter already trimmed to 2 tools only
- All QBot3 code in `qbot3/` directory — isolated from QBot2

## Rollback Plan

If QBot3 fails:
```bash
# Remove flag, restart
sed -i '/^QBOT3_ENABLED/d' /opt/qbot/app/.env.local
systemctl restart qbot-api.service
# QBot2 resumes full operation
```

All QBot3 code is in `qbot3/` directory — delete it to remove:
```bash
rm -rf /opt/qbot/app/qbot3/
```
