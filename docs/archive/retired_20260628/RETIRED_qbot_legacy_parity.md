# Qbot Legacy Parity Audit

This document records the scope expansion of the legacy parity audit so it covers all historical QBot service classes, not only cycling / Garmin / routes.

## Scope

The audit now covers:

- Core QBot API
- Telegram bot
- MCP connector
- QLab
- Backup / restore
- Garmin upload / proxy
- FIT processing
- CSV / JSON reporting
- Hammerhead import
- RWGPS
- OpenMap / OSM
- Weather / OpenWeatherMap
- Garage / gate / home automation
- Artifacts / filesystem containers / PostgreSQL artifacts
- Scheduled jobs
- Email notifications
- Public endpoints
- External API integrations

## Read-only tools

- `qbot_legacy_full_parity_audit`
- `qbot_legacy_parity_matrix`
- `qbot_weather_legacy_status`
- `qbot_garage_legacy_status`
- `qbot_artifacts_legacy_status`
- `qbot_external_integrations_report`

## Safety model

- Garage / gate / home automation is treated as `CONTROLLED_ACTION`.
- No new remote open/close execution path is exposed.
- Weather status remains read-only and does not use API keys in output.
- Artifact reporting is read-only and does not write files.
- Telegram and MCP expose only allowlisted read-only status/report tools for this audit.

## Telegram commands

- `/weather_status`
- `/garage_status`
- `/artifacts`
- `/integrations`

These commands are informational only.

## How to test

```bash
python -m py_compile qbot*.py
pip check
systemctl restart qbot-api.service
sleep 2
curl -s http://127.0.0.1:8001/health | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_legacy_full_parity_audit","args":{}}' | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_legacy_parity_matrix","args":{}}' | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_weather_legacy_status","args":{}}' | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_garage_legacy_status","args":{}}' | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_artifacts_legacy_status","args":{}}' | jq
curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d '{"tool":"qbot_external_integrations_report","args":{}}' | jq
```

## Public endpoint checks

- `/mcp/` must remain public.
- `/telegram/webhook/` must remain public.
- `/q` must remain blocked publicly.
- `/health` must remain blocked publicly.

## Policy notes

- Legacy garage / gate references are evidence only.
- No autonomous gate or garage action is implemented here.
- OpenWeatherMap-specific parity is currently missing; weather is served through the current MCP weather path.

