# QBot current state - 2026-05-26

## Purpose

This file records the current operating state of QBot after the report delivery fixes
made on 2026-05-19. It is meant as a human-readable snapshot, not as executable
configuration.

## LLM provider

- Current active LLM provider: Anthropic.
- Configured secret in `/opt/qbot/app/.env`: `ANTHROPIC_API_KEY`.
- No `OPENAI_API_KEY` or `QGPT_API_KEY` is currently configured in `.env`.
- Central config: `qbot_config.py`.
- Shared client: `qgpt_client.py`.
- Shared core prompt: `QBOT_INSTRUCTIONS.md`, automatically merged by
  `qgpt_client.py` into LLM calls.
- Shared readiness rules: `qbot_readiness.py`.
- Default Anthropic model in code: `claude-sonnet-4-6`.
- OpenAI-compatible mode is still supported by `qgpt_client.py` if
  `OPENAI_API_KEY` or `QGPT_API_KEY` is added later.
- If no LLM is available, `daily_report.py` has deterministic fallback text so
  Telegram/email reports are not empty.

## Daily report

- Script: `daily_report.py`.
- Sends to Telegram and email.
- State file: `/opt/qbot/app/data/daily_report_sent.json`.
- State file owner should be `qbot:qbot`, so the qbot cron can update it.
- MCP access is now through shared `qbot_mcp_client.py`.
- Xert is available again in the daily report path after fixing the MCP
  initialize flow.
- Email narrative generation in `email_template.py` uses one structured JSON
  LLM call with deterministic fallback instead of multiple separate calls.
- Weather is fetched through MCP `get_weather`; direct Open-Meteo fallback was
  removed from `daily_report.py`.
- Sleep-data behavior:
  - Garmin is the primary post-wake sleep source; Intervals wellness is the fallback.
  - from 06:00 to 08:50 it retries if Garmin sleep data has not arrived;
  - at 09:00 it sends anyway, using Intervals as fallback if Garmin still has no sleep.
- Current cron entries:
  - `*/10 6-8 * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python daily_report.py >> /opt/qbot/logs/daily_report.log 2>&1`
  - `0 9 * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python daily_report.py >> /opt/qbot/logs/daily_report.log 2>&1`
- Last known fixed behavior:
  - report was manually sent on 2026-05-19 after enabling Anthropic fallback;
  - `daily_report_sent.json` then contained `{"date": "2026-05-19"}`.

## Telegram

- Telegram token and chat id are configured in `.env`.
- `telegram_reply_processor.py` uses the shared LLM client.
- `telegram_reply_processor.py` uses shared `qbot_mcp_client.py` for MCP calls.
- Gear observations are now classified into `save_gear`, `save_component`, or
  `save_memory` instead of always landing in memory.
- With the current `.env`, Telegram reply fallback uses Anthropic through
  `qgpt_client.py`.
- Daily report Telegram send now rejects empty message bodies.

## Public MCP

- Public ChatGPT connector URL stays `https://qbot.cytr.us/mcp/`.
- Public `/mcp/` is routed through nginx to `qbot-api.service` on `127.0.0.1:8001`.
- Public `/q` and `/health` remain blocked with `404`.
- Adapter file: `qbot_mcp_adapter.py`.
- Exposed MCP tools:
  - `qbot.status`
  - `qbot.readiness`
  - `qbot.ask`
  - `qbot.runbook`
  - `qbot.context_bundle`
  - `qbot.artifact_create` requires MCP token and is disabled without one
  - `qbot.artifact_list`
  - `qbot.artifact_get`
  - `qbot.tool_policy`
  - `qbot.telegram_status`
- Diagnostics added:
  - `qbot_mcp_status`
  - `qbot_mcp_tools_list`
  - `qbot_mcp_call_preview`
- Added query/runbook support:
  - `mcp status` / `czy mcp działa`
  - `mcp tools` / `lista narzędzi mcp`
  - `mcp_connector_review`
- Current adapter status: `WARN` because no MCP token is configured, but read-only
  MCP routes are live and `/mcp/health` and `/mcp/tools` work locally and through nginx.

## Gate

- Current gate mode: `hikconnect_direct`
- Current runtime endpoint: `/gate/status`
- Required runtime variables:
  - `GATE_TOKEN` configured
  - `HIKCONNECT_ACCOUNT` configured
  - `HIKCONNECT_PASSWORD` configured
  - `GATE_DEVICE_SERIAL` configured
  - `GATE_LOCK_CHANNEL` configured
  - `GATE_LOCK_INDEX` configured
  - `GATE_RATE_LIMIT_SEC` configured
- Legacy bridge envs are optional fallback only:
  - `GATE_BRIDGE_URL`
  - `HIKCONNECT_GATE_URL`
  - `GATE_UPSTREAM_URL`
- Runtime diagnostics now expose configured/unconfigured state only for secrets and bridge fallback, without logging token/password values.
- `qbot-qlab-server.service` remains the gate runtime host.

## Email

- Gmail credentials are configured in `.env` as `GMAIL_USER`,
  `GMAIL_APP_PASSWORD`, and `EMAIL_TO`.
- `daily_report.py` sends HTML email through Gmail SMTP.
- `email_reply_processor.py` uses the shared LLM client for parsing replies.
- `email_reply_processor.py` uses shared `qbot_mcp_client.py` for MCP calls.
- Gear usage and equipment notes are now classified into `save_gear`,
  `save_component`, or `save_memory` instead of always landing in memory.

## Ride reports

- `ride_report.py` still uses the shared LLM client and therefore uses Anthropic
  with the current `.env`.
- As of this snapshot, `ride_report.py` is not scheduled in the qbot crontab.
- `ride_report.py` is scheduled every 30 minutes in the qbot crontab.
- Report HTML now starts with deterministic protocol sections:
  health context, athlete comment, route/surface before cadence, power/HR/cadence,
  similar ride comparison, and long-ride block when applicable.
- Long-ride protocol can estimate first-half/second-half power, HR drift and
  cadence from FIT samples every 30 seconds when available.
- Safe preview mode exists:
  `ride_report.py --html <activity_id> [activity name]`.
- Critical health rule is implemented at report layer: illness/fatigue context
  plus HRV more than 5 points below weekly norm creates a red readiness warning.
- Report state now uses `in_progress`, `sent`, and `failed`.
- Failed reports are retriable; an activity is marked `sent` only after email
  and Telegram sending complete.
- Email and Telegram channel delivery statuses are recorded separately.
- `in_progress` older than 6 hours no longer blocks retry.

## Other scheduled jobs

Current qbot crontab:

```cron
*/15 6-8 * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python daily_report.py >> /opt/qbot/logs/daily_report.log 2>&1
0 9 * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python daily_report.py >> /opt/qbot/logs/daily_report.log 2>&1
0 */2 * * * cd /opt/qbot/app && /opt/qbot/cronometer-venv/bin/python sync_nutrition.py >> /opt/qbot/logs/nutrition_sync.log 2>&1
*/30 * * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python monitor.py >> /opt/qbot/logs/q_monitor.log 2>&1
*/10 * * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python email_reply_processor.py >> /opt/qbot/logs/email_reply_processor.log 2>&1
*/2 * * * * cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python telegram_reply_processor.py >> /opt/qbot/logs/telegram_reply_cron.log 2>&1
```

Root crontab includes Hammerhead/Garmin sync:

```cron
*/10 * * * * /opt/qbot/app/scripts/run_hammerhead_garmin_sync.sh
17 3 * * * /opt/qbot/app/.venv/bin/python /opt/qbot/app/scripts/prune_qbot_artifacts.py >> /opt/qbot/app/logs/artifact_prune.log 2>&1
```

## Known open issues

- Weather API can occasionally return an empty/non-JSON response; `daily_report.py`
  logs this and continues.
- OpenAI API is not currently active because no OpenAI API key is configured.
  ChatGPT Plus does not provide API credits.
- Hammerhead/Garmin sync no longer aborts on `fitparse` developer-field decode
  errors, but report metrics can be degraded for FIT files that `fitparse`
  cannot decode.
- Log rotation exists for `/opt/qbot/logs/*.log` and `/opt/qbot/app/logs/*.log`
  in `/etc/logrotate.d/qbot`.
- Artifact retention exists in `scripts/prune_qbot_artifacts.py`.
- Operational status command exists: `scripts/qbot_status.py`.
- Machine-readable operational state exists at
  `/opt/qbot/app/data/qbot_operational_state.json` and is refreshed by qbot cron
  every 30 minutes.
- Local smoke tests exist in `scripts/qbot_smoke_tests.py`.

## Fix log - 2026-05-19

- Fixed local MCP clients in `daily_report.py`, `ride_report.py`,
  `telegram_reply_processor.py`, and `email_reply_processor.py` by sending
  `notifications/initialized` after `initialize`.
- Root cause of missing Xert in the daily report: tool calls were sent before
  the MCP session was fully initialized. `get_xert_status` itself works.
- Verified Xert through MCP:
  - TP: 245.7 W
  - form: Fresh
  - form score: 4.2
  - recommended type: Endurance
- `daily_report.py` now uses MCP `get_weather` first, matching the project
  instruction. Direct Open-Meteo remains only as fallback.
- Added shared MCP helper `qbot_mcp_client.py` and refactored local clients to
  use it.
- Fixed `ride_report.py` state handling so failed sends can retry.
- Added channel-level delivery state and stale `in_progress` retry behavior to
  `ride_report.py`.
- Added `build_ride_protocol()` and protocol HTML blocks to `ride_report.py`.
- Reduced daily report LLM narrative generation to one JSON call.
- Added long-ride split analysis from FIT 30 s samples.
- Changed MCP `save_memory` to append with exact duplicate detection; added
  `replace_memory` for explicit replacement/snapshot use.
- Added `qbot_garage_mapper.py` and routed gear observations into the proper
  garage tables.
- Added `qbot_readiness.py` and wired daily/email/ride readiness to shared rules.
- Added `scripts/qbot_smoke_tests.py`.
- Added `scripts/qbot_operational_state.py` and scheduled it in qbot cron.
- Extended gear mapping to explicit new-bike notes and fitting notes.
- Removed direct Open-Meteo fallback from `daily_report.py`.
- Added `scripts/qbot_status.py`.
- Added safe ride report HTML preview mode and verified it on activity
  `i149025218`.
- Enabled `ride_report.py` cron at `*/30`.
- Made Hammerhead/Garmin sync tolerate `fitparse` developer-field errors.
- Added QBot logrotate config.
- Added `qbot_config.py` as a central configuration layer.
- Added `QBOT_INSTRUCTIONS.md` and made `qgpt_client.py` merge it into LLM
  system prompts.
- Added daily root cron artifact pruning at 03:17.
