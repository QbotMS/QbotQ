# QBot optimization diagnostic - 2026-05-19

## Executive summary

QBot is not resource-heavy at rest. The main optimization opportunities are
operational: repeated failing jobs, duplicated MCP client code, repeated LLM
calls, weak state handling, and missing log/data retention policy.

Baseline at inspection time:

- `q-bot.service`: active, about 74 MB RAM, low CPU.
- `qbot_qlab_server.py`: active, about 48 MB RAM, low CPU.
- `ngrok-qbot.service`: active, about 41 MB RAM, low CPU.
- App directory: about 176 MB.
- Largest growth sources: QLab replay logs, Garmin proxy CSV/FIT outputs, and
  Hammerhead sync logs.

## Fixes applied during this diagnostic

### 1. Hammerhead sync no longer fails on fitparse CSV/report decode

Problem:

- `qbot-hammerhead-sync` ran every 10 minutes.
- It repeatedly failed at `write_csv_if_possible()` because `fitparse` could not
  decode a developer field:
  `FitParseError: No such field 2 for dev_data_index 3`.
- This created repeated tracebacks and prevented successful completion.

Change:

- CSV export and strict FIT validation are now best-effort.
- If `fitparse` cannot decode developer fields, sync continues and writes the
  decode problem into report warnings.
- Verified one sync run completed with `qbot-hammerhead-sync done`.
- Garmin upload still succeeded in the test run.

Files changed:

- `qbot-hammerhead-sync`

Residual risk:

- The latest report can show empty `recordCount`/`sessionMetrics` for files
  that `fitparse` cannot decode. The FIT file may still be valid enough for
  Garmin, but metrics in QBot's report are degraded for that file.

### 2. Local MCP client protocol is centralized and initialized correctly

Problem:

- Local scripts duplicated `mcp_call()` and sent `initialize`, but some did not
  send the required `notifications/initialized` notification before calling
  tools.
- This caused errors such as `request before initialization was complete`.
- This was also the direct cause of missing Xert data in the daily report,
  even though `mcp_server.get_xert_status()` worked directly.

Change:

- Added shared `qbot_mcp_client.py`.
- Refactored daily report, ride report, Telegram reply processor, and email
  reply processor to use the shared helper.
- Shared helper now performs:
  - `initialize`;
  - `notifications/initialized`;
  - `tools/call`;
  - common SSE/JSON parsing;
  - common error logging.

Files changed:

- `qbot_mcp_client.py`
- `daily_report.py`
- `ride_report.py`
- `telegram_reply_processor.py`
- `email_reply_processor.py`

Verification:

- `get_xert_status` through the shared helper returned TP `245.7 W`, status
  `Fresh`, form score `4.2`.
- `get_weather` through the shared helper returned `teraz`, `hourly_forecast`
  and `prognoza`.
- `py_compile` passes for all refactored scripts.

### 3. Ride report state no longer marks failed sends as reported

Problem:

- `ride_report.py` marked an activity as reported before fetching all data,
  generating HTML, sending email, and sending Telegram.
- If a later step failed, the activity would be skipped forever.

Change:

- Replaced the one-shot `mark_reported()` behavior with statuses:
  `in_progress`, `sent`, `failed`.
- An activity is considered complete only when status is `sent`.
- `failed` activities are retriable.
- Delivery channels are tracked separately as `email` and `telegram`.
- Stale `in_progress` entries older than 6 hours no longer block retry.

File changed:

- `ride_report.py`

Verification:

- Temporary state test confirmed that `failed` does not block retry, while
  `sent` and `in_progress` do.
- Temporary state test confirmed old `in_progress` does not block retry and
  fresh `in_progress` still does.

### 4. QBot log rotation added

Problem:

- QBot logs under `/opt/qbot/logs` and `/opt/qbot/app/logs` had no dedicated
  retention policy.

Change:

- Added `/etc/logrotate.d/qbot`.
- Rotates daily, keeps 14 compressed rotations, uses `copytruncate` because
  cron and long-running services append directly to log files.

Verification:

- `logrotate -d /etc/logrotate.d/qbot` parsed the config successfully.

### 5. Generated artifact retention added

Problem:

- Hammerhead/Garmin and QLab generated FIT/CSV/JSON artifacts had no retention
  policy.

Change:

- Added `scripts/prune_qbot_artifacts.py`.
- Root cron runs it daily at 03:17.
- Current limits:
  - 60 Hammerhead original FIT files;
  - 60 Garmin proxy FIT/CSV files;
  - 120 Hammerhead report JSON files;
  - 20 detailed QLab replay/validation JSON files;
  - 60 QLab replay summaries.

Verification:

- Dry run completed successfully and would currently remove `0` files because
  existing counts are below limits.

### 6. Central config and core prompt added

Problem:

- Config was spread across scripts through repeated `.env` loading and direct
  `os.getenv` calls.
- QBot did not have a single shared instruction loaded into all LLM calls.

Change:

- Added `qbot_config.py` for common env values, paths, Intervals auth headers,
  MCP URL, and active LLM provider diagnostics.
- Added `QBOT_INSTRUCTIONS.md`.
- `qgpt_client.py` now merges the shared QBot instruction into system prompts.

Verification:

- Config diagnostic reports provider `anthropic`, Anthropic model
  `claude-sonnet-4-6`, local MCP URL, and configured Intervals/Telegram/Gmail.
- `py_compile` passes.

### 7. Ride report now has deterministic protocol sections

Problem:

- `ride_report.py` fetched useful data, but the project protocol was mostly
  implicit in prompts and LLM interpretation.

Change:

- Added `build_ride_protocol()`.
- Added HTML sections for:
  - health context and readiness;
  - athlete comment from `description`/`notes`;
  - route and surface before cadence judgement;
  - power, HR, cadence;
  - similar ride comparison;
  - long rides when current activity is >3h or >80 km.
- Implemented the hard health rule:
  illness/fatigue context plus HRV more than 5 points below weekly norm
  produces a red readiness warning.

Verification:

- `py_compile` passes.
- Synthetic protocol sample renders HTML and produces red readiness when the
  data meets red-flag conditions.

### 8. Daily report LLM calls reduced

Problem:

- `email_template.py` made multiple independent LLM calls for daily report
  narrative blocks, verdict, recommendation and self-review.

Change:

- Replaced the sequence with one structured JSON call returning all narrative
  fields.
- Added deterministic fallback when JSON parsing fails.

Verification:

- Local render test confirmed exactly one AI call and successful HTML output.

### 9. Long-ride split analysis added

Problem:

- Long-ride protocol listed previous long rides, but did not compute current
  ride first-half/second-half power and HR drift.

Change:

- Added split analysis from FIT samples returned every 30 seconds by
  `get_activity_details`.
- Reports first-half/second-half power, power fade, HR drift and cadence when
  samples are available.

Verification:

- Synthetic split test produced expected power fade and HR drift values.

### 10. Garage memory append/deduplication added

Problem:

- MCP `save_memory` replaced the whole memory topic, which was risky for
  ongoing notes.

Change:

- Added `db.save_memory_append()`.
- MCP `save_memory` now appends and skips exact duplicates.
- Added MCP `replace_memory` for explicit snapshot replacement.

Verification:

- Local SQLite test and MCP call confirmed create, duplicate skip and append.

### 11. Gear routing into proper garage tables added

Problem:

- Telegram and email processors previously sent all gear-related notes to
  `save_memory`, even when the note clearly described personal gear or a bike
  component.

Change:

- Added `qbot_garage_mapper.py`.
- `telegram_reply_processor.py` and `email_reply_processor.py` now classify
  each gear note and route it to:
  - `save_gear` for personal equipment;
  - `save_component` for bike parts and consumables;
  - `save_memory` only when the note is ambiguous.

Verification:

- Local classifier tests map examples like helmet, jersey and shoes to
  `save_gear`, and chain or tire notes to `save_component`.
- Direct MCP calls to `save_gear` and `save_component` succeeded.

### 11. Weather fallback removed from daily report

Problem:

- Project rule says weather should go through QBot `get_weather`.

Change:

- Removed direct Open-Meteo fallback from `daily_report.py`.
- If MCP weather fails, the report continues with missing weather data rather
  than silently using a different source path.

### 12. Operational status command added

Change:

- Added `scripts/qbot_status.py`.
- It reports LLM provider, models, MCP URL, daily report state, Xert status,
  weather MCP keys, service states, crons and recent logs.

Verification:

- Command currently reports Anthropic provider, Xert TP `245.7`, status
  `Fresh`, and all three QBot services active.

### 13. Ride report cron enabled

Change:

- Added `ride_report.py` to the qbot crontab every 30 minutes.

Verification:

- `crontab -u qbot -l` now includes the ride report entry.

### 14. Shared readiness module added

Change:

- Added `qbot_readiness.py`.
- Daily report, email template fallback and ride report protocol now use the
  same readiness rules.

Verification:

- Smoke tests cover green readiness, low HRV with illness, and low Body Battery.

### 15. Smoke tests and operational JSON added

Change:

- Added `scripts/qbot_smoke_tests.py`.
- Added `scripts/qbot_operational_state.py`.
- qbot cron refreshes `/opt/qbot/app/data/qbot_operational_state.json` every
  30 minutes.

Verification:

- Smoke tests pass locally.
- Operational JSON reports Anthropic provider, Xert TP/status, weather MCP keys,
  report status, service status and cron entries.

## Findings

### P0/P1: Repeated failures and noisy loops

1. Hammerhead sync was the biggest active reliability/cost issue.
   Status: fixed as above.

2. Old Telegram `409 Conflict` errors exist in logs.
   Likely caused by multiple `getUpdates` pollers running at the same time in
   the past. Current process list does not show duplicate Telegram pollers.

3. Old MCP errors `request before initialization was complete` exist in
   `q-bot.err.log`.
   Status: fixed in the local MCP clients by sending `notifications/initialized`
   after `initialize`.

4. Old nutrition sync errors mention `No module named garminconnect`.
   Current `/opt/qbot/cronometer-venv` has `garminconnect` available. Treat the
   log entries as historical unless they reappear.

### P1: Duplicated MCP client implementation

Status: fixed.

The same local `mcp_call()` protocol implementation previously existed in:

- `daily_report.py`
- `ride_report.py`
- `telegram_reply_processor.py`
- `email_reply_processor.py`

This already caused the Xert bug. It has been extracted to
`qbot_mcp_client.py`, with:

- one implementation of initialize/initialized/tools-call;
- common parsing of SSE/JSON responses;
- consistent timeout/retry behavior;
- structured error logging.

Benefit:

- fewer regressions;
- easier retries/backoff;
- less code duplication;
- safer future MCP protocol changes.

### P1: Daily report uses many sequential network calls

`daily_report.py` performs several network-bound operations sequentially:

- Intervals wellness
- Intervals activities
- Intervals profile
- MCP weather
- Xert status
- Xert activities
- Garmin wellness
- Anthropic calls for Telegram/email text sections

Current behavior is acceptable for a once-daily report, but latency can be high
and failures are coupled. Suggested improvements:

- use a shared timeout/retry wrapper;
- cache Xert status for a short TTL, e.g. 10-30 minutes;
- avoid fetching Xert activities if Xert status is already enough for the daily
  report, unless TP history is required;
- generate fewer LLM sections or batch them into one structured LLM call.

### P1: LLM cost/latency can be reduced

`email_template.py` makes many independent LLM calls:

- TL;DR
- sleep comment
- HRV comment
- form comment
- balance comment
- verdict JSON
- recommendation/rada
- self-review

This is robust in terms of layout, but expensive and slow. A better shape:

- one LLM call returning structured JSON for all narrative blocks;
- local deterministic validation/fallback for verdict;
- optional self-review only when JSON is malformed or contradictory.

Expected benefit:

- lower Anthropic cost;
- faster report generation;
- fewer partial failures.

### P1: Ride report state handling is unsafe

Status: fixed at activity-level. `ride_report.py` now uses `in_progress`,
`sent`, and `failed`, and marks `sent` only after email and Telegram complete.

Remaining improvement:

- channel-level status would be more precise if email succeeds but Telegram
  fails, or the other way around.

### P2: Log and output retention

Largest files include:

- QLab replay log: about 12.5 MB
- FIT replay log copy: about 6 MB
- Garmin proxy CSV files: up to about 4.9 MB each
- Hammerhead logs: growing with each run

Status: fixed for logs and generated artifacts. Remaining optional improvement:

- compress large old CSV/JSON artifacts before deletion if long-term audit
  history becomes useful.

### P2: Cron frequency review

Current qbot cron:

- daily report retries from 06:00 to 09:00: good.
- nutrition sync every 2h: acceptable.
- monitor every 30 min: acceptable.
- email replies every 10 min: acceptable.
- Telegram replies every 2 min: acceptable, but polling can conflict if another
  poller is started manually.
- Hammerhead sync every 10 min: acceptable after the fitparse failure fix, but
  consider backoff if no new activities are found for many cycles.

### P2: Direct imports and environment coupling

Several scripts load `/opt/qbot/app/.env` directly and duplicate constants.
This is workable, but harder to reason about.

Suggested improvement:

- central `qbot_config.py`;
- central paths, API keys, model names, log paths, location, and cron metadata;
- one place for "active LLM provider" diagnostics.

### P2: QBot project compliance

Optimization is not only performance. Some reliability comes from making the
project rules executable:

- central Q instruction file loaded into all LLM prompts;
- shared garage save helper with deduplication;
- daily report and ride report using the same source-priority rules;
- ride report pipeline split into explicit steps with hard validation.

## Recommended next implementation order

1. Refactor daily report LLM generation to one structured call plus local
   verdict fallback.
2. Dopracować mapowanie odpowiedzi o sprzęcie do `save_component`/`save_gear`
   zamiast ogólnego `save_memory`.
3. Observe the first few scheduled `ride_report.py` runs and confirm there are
   no duplicate sends or unexpected failures.
