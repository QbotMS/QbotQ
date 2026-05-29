# MCP Public Surface Audit — 2026-05-28

## Current Public Tools

### QBot3 (new architecture, qbot3/adapters/mcp_adapter.py)

| Tool | Status | Should Stay | Notes |
|---|---|---|---|
| `qbot.query` | ✅ Active | YES | Main Albert interface |
| `qbot.action_execute` | ✅ Active | YES | Safety-validated write execution |

### QBot2 (legacy, mcp_server.py, qbot_mcp_adapter.py)

The QBot2 MCP server (`mcp_server.py`, 3152 lines) exposes ~30+ legacy tools. However, the production FastAPI app (`qbot_api.py`) only exposes 2 tools when `QBOT3_ENABLED=1`:

| Legacy Tool | Status | Should Stay | Notes |
|---|---|---|---|
| Ride readiness tools | Legacy only | NO | QBot3 handles via Albert |
| RWGPS tools | Legacy only | NO | QBot3 tool_registry wraps |
| Weather tools | Legacy only | NO | QBot3 wraps via tool_registry |
| Nutrition tools | Legacy only | NO | QBot3 wraps real handlers |
| Garage tools | Legacy only | NO | QBot3 wraps real handlers |
| Wellness tools | Legacy only | NO | QBot3 wraps real handlers |

## MCP Tools List Endpoint

When `QBOT3_ENABLED=1`:
```
tools/list → [qbot.query, qbot.action_execute]
```

When `QBOT3_ENABLED=0`:
```
tools/list → [qbot.query, qbot.action_execute]  (also only 2 tools via QBot2 MCP adapter)
```

## Disabling Legacy Micro-Tools

Already done. The QBot2 MCP adapter (`qbot_mcp_adapter.py`) was already trimmed to only 2 public tools. No action needed for micro-tool removal.

## OpenAI / ChatGPT UI Caching

**Risk**: If OpenAI UI was previously used with QBot2 and cached a tool list containing 30+ tools, it may continue showing stale tools.

**Mitigation**:
1. OpenAI UI refreshes tool list on new conversation
2. Each MCP `tools/list` call returns current tools only
3. No server-side caching of tool definitions

**If stale tools appear in UI**:
- Start new conversation in ChatGPT/OpenAI UI
- Old conversations retain old tool list (expected behavior)

## Plan

| Phase | Action | Status |
|---|---|---|
| 1 | Trim QBot2 MCP to 2 tools | ✅ Done |
| 2 | Route QBot3 under QBOT3_ENABLED=1 | ✅ Done |
| 3 | Test fresh OpenAI UI conversation | ⏳ Next |
| 4 | Archive legacy mcp_server.py | ⏳ After cutover |
