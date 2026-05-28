# QBot MCP Connector

ChatGPT connector URL stays:

`https://qbot.cytr.us/mcp/`

## How it works

- Public traffic reaches nginx on `https://qbot.cytr.us/mcp/`.
- nginx proxies `/mcp/` to the local FastAPI service on `127.0.0.1:8002`.
- `qbot_api.py` handles the public MCP routes and forwards tool calls to local QBot dispatch.
- Tool execution stays inside QBot policy and tool allowlists.
- Tool calls are recorded in PostgreSQL `tool_calls`.

## Exposed MCP tools

- `qbot.query`
- `qbot.action_execute`

## What MCP cannot do

- It cannot execute arbitrary QBot tools by name.
- It cannot bypass the QBot policy engine.
- It cannot run shell commands directly.
- It cannot use arbitrary SQL.
- It cannot expose public `/q`.
- It cannot expose public `/health`.
- It cannot use real external LLM API calls from the MCP adapter.

## Authentication

- The adapter supports a simple token if `MCP_SHARED_SECRET` or `QBOT_MCP_TOKEN` is configured.
- If no token is configured, the adapter reports `WARN` and stays in read-only mode for the public connector.
- `qbot.artifact_create` is blocked without a configured MCP token.

## Testing

Local MCP health:

```bash
curl -s http://127.0.0.1:8001/mcp/health | jq
curl -s http://127.0.0.1:8001/mcp/tools | jq
```

Local MCP protocol check:

```bash
curl -i http://127.0.0.1:8001/mcp/ | head -80
```

Public MCP checks:

```bash
curl -i https://qbot.cytr.us/mcp/ | head -80
curl -s https://qbot.cytr.us/mcp/health | jq
curl -s https://qbot.cytr.us/mcp/tools | jq
```

## Public blocks

Verify public blocks stay in place:

```bash
curl -i https://qbot.cytr.us/q | head -40
curl -i https://qbot.cytr.us/health | head -40
```

Expected result: `404` or `403`, not `200`.

## Policy behavior

- `qbot.ask` routes through QBot query/policy logic.
- `qbot.runbook` uses the operator runbook allowlist.
- `execute=true` still goes through QBot policy boundaries.
- The adapter does not auto-run controlled actions.
