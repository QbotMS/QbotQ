# QBot Implementation Roadmap

Audit-informed roadmap for the next phase after the full legacy source audit.

Audit inputs:
- [docs/qbot_full_legacy_source_audit.md](/opt/qbot/app/docs/qbot_full_legacy_source_audit.md)
- [docs/qbot_integrations_auth_audit.md](/opt/qbot/app/docs/qbot_integrations_auth_audit.md)
- current git history and live read-only status surfaces

## 1. Executive Summary

The current QBot deployment is operational and cut over:
- `qbot-api.service` is active.
- `qbot-qlab-server.service` is active.
- Public `/q` and `/health` remain blocked with `404`.
- Public `/mcp/` and `/ride-readiness` are available.
- Telegram is cutover-aware.
- The wellness / sleep / nutrition PostgreSQL patch is already deployed.

The legacy source audit showed that the old QBot was smaller, more script-driven, and centered on:
- Telegram polling and reply ingestion
- a FastMCP / SSE bridge
- ride-readiness
- Garmin, Xert, Intervals, Cronometer, weather
- garage SQLite data and packing lists
- daily / ride reports
- a monitor script that assumed `q-bot` and `ngrok`

The main remaining work is not random bug fixing. It is block-by-block completion of the system:
- make Telegram a reliable agent rather than a command router
- stabilize integration auth and local stores
- finish route / GPX / FIT / TCX persistence
- preserve garage 1:1 source fidelity
- keep reports and scheduler safe
- gate all mutating integrations behind preview and approval
- harden QExt2/Karoo readiness snapshots
- tighten ops, backup, logs, and legacy-monitor removal

Guiding rule:
- one large block at a time
- no feature drift
- no silent mutation
- no legacy ngrok/q-bot regression

## 2. Current Deployment Snapshot

- HEAD commit: `2b294a5` (`docs: audit real legacy Qbot source versus new deployment`)
- Repository status: clean at audit start
- `qbot-api.service`: active
- `qbot-qlab-server.service`: active
- Public `/q`: `404`
- Public `/health`: `404`
- Public `/mcp/tools`: `200`
- Public `/ride-readiness`: `200 JSON`
- Tool policy count: `186`
- Public MCP tool count: `52`
- `qbot_operator_final_smoke_test`: `WARN`
- `qbot_operator_final_smoke_test` readiness: `100`
- `qbot_operator_final_smoke_test` warning sources: readiness warning plus `29 real error candidates`
- `qbot_api` health: OK / DB connected
- `qbot_backup_timer_status`: OK
- Current DB/store picture:
  - PostgreSQL wellness store exists and is queried through `qbot_wellness_store.py`
  - SQLite garage store exists at `data/garage.db`
  - artifact storage exists both on filesystem and in PostgreSQL-backed tooling
- Known external blocker:
  - OpenWeatherMap-specific parity is blocked by missing secret/config and current weather remains on the Open-Meteo path

## 3. Strategic Principles

- Do not patch individual symptoms when a block-level design is still incomplete.
- Prefer QBot tools and local stores first.
- Use public web only for public data, not for private operational data.
- Keep private data in integrations and local PostgreSQL / SQLite stores.
- Preserve original artifacts; add projections and indexes around them.
- Let deterministic parsers own source data.
- Let LLMs synthesize and explain, but not invent source facts.
- `READ_ONLY` tools may auto-execute.
- Mutating actions must remain previewable and approval-gated.
- Every Telegram answer should include sources or explicit source context.
- Do not revive legacy `q-bot.service` or `ngrok` as operational requirements.

## 4. Work Blocks

### P0. Telegram Agent Reliability

Objective:
- Telegram should behave like a short QBot agent, not a command router.

Scope:
- conversation memory
- follow-up resolution
- real tool execution
- integration status aggregator
- no raw tool dumps
- source attribution
- self-checks

Done definition:
- "co poszło nie tak?" uses conversation context
- "sprawdź status wszystkich integracji" executes the relevant tools and returns a concise summary
- no plan-only responses when execution is allowed
- no raw `tool=status` dumps
- every response has source context

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P0-1 | Normalize Telegram agent entrypoints and reply routing around one context-aware path | `qbot_telegram_tools.py`, `telegram_reply_processor.py`, `qbot_query_processor.py` | `qbot_telegram_agent_chat_self_check`, `qbot_telegram_conversation_self_check` | Medium | Follow-up turns resolve against prior context | Yes | No |
| P0-2 | Add a stable integration-status aggregator for Telegram answers | `qbot_telegram_tools.py`, `qbot_report_tools.py`, `qbot_tool_registry.py` | `qbot_external_integrations_report`, `qbot_telegram_status` | Medium | Telegram can summarize all key integrations in one response | Yes | No |
| P0-3 | Enforce source attribution and citation discipline in Telegram replies | `telegram_reply_processor.py`, `qbot_query_processor.py`, `qbot_report_tools.py` | `qbot_telegram_answer_context`, `qbot_answer_context` | Medium | Every answer includes sources or source context | Yes | No |
| P0-4 | Remove plan-only behavior where execution is safe and the tool is already read-only | `qbot_query_processor.py`, `qbot_operator_tools.py` | `qbot_query`, `qbot_operator_runbook` | Medium | Allowed read-only actions execute instead of returning only plans | Yes | No |
| P0-5 | Add Telegram self-checks for context, memory, and tool selection | `qbot_telegram_tools.py`, `qbot_tool_registry.py` | `qbot_telegram_agent_chat_self_check`, `qbot_telegram_llm_chat_self_check` | Low | Self-checks verify context and tool selection | Yes | No |
| P0-6 | Define the Telegram answer contract for source-backed short replies | `docs/qbot_telegram_restore.md`, `qbot_telegram_tools.py` | `qbot_telegram_status` | Low | Replies are concise, sourced, and cutover-aware | Yes | No |

### P1. Integration Auth and Local Stores

Objective:
- Stabilize Xert, Garmin, Intervals, Cronometer, Weather, RWGPS, and Hammerhead status/read-only surfaces.

Scope:
- auth status
- historical import
- wellness / sleep / nutrition DB
- Intervals comments from `2026-05-01`
- Cronometer nutrition

Done definition:
- data query tools work from local DB/store
- live API status is explicit
- missing data, missing auth, and missing implementation are distinct

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P1-1 | Stabilize the integration auth inventory and make blockers explicit | `docs/qbot_integrations_auth_audit.md`, `qbot_integration_tools.py`, `qbot_tool_registry.py` | `qbot_weather_config_status`, `qbot_intervals_config_status`, `qbot_garmin_config_status` | Low | Auth status is explicit and non-ambiguous | Yes | No |
| P1-2 | Finish local wellness / sleep / nutrition query behavior on PostgreSQL | `qbot_wellness_store.py`, `qbot_report_tools.py`, `qbot_tools.py` | `qbot_wellness_db_status`, `qbot_sleep_day_get`, `qbot_nutrition_day_get` | Medium | DB-backed queries are the default path for wellness data | Yes | No |
| P1-3 | Keep Intervals comments and note imports reliable from `2026-05-01` onward | `qbot_wellness_store.py`, `email_reply_processor.py`, `daily_report.py` | `qbot_intervals_wellness_import_execute`, `qbot_intervals_comments_import_execute` | Medium | Imports preserve date and comment semantics | Yes | Yes |
| P1-4 | Make weather status explicit about provider and secret dependency | `qbot_weather_status`, `qbot_readiness.py`, `daily_report.py` | `qbot_weather_config_status`, `qbot_weather_current` | Low | Weather answers clearly distinguish provider path and blockers | Yes | No |
| P1-5 | Keep Garmin / Xert / Hammerhead / RWGPS status surfaces stable and comparable | `qbot_legacy_parity_tools.py`, `qbot_tool_registry.py`, `qbot_report_tools.py` | `qbot_xert_readiness_status`, `qbot_garmin_proxy_status`, `qbot_hammerhead_import_dry_run`, `qbot_rwgps_readonly_smoke` | Medium | Read-only status tools remain trustworthy | Yes | No |

### P2. Route / GPX / FIT / TCX PostgreSQL Store

Objective:
- Parsed routes become queryable DB objects.

Scope:
- original artifact
- parsed JSON artifact
- routes table
- points
- segments
- waypoints
- route briefing
- route import preview / execute

Done definition:
- GPX preview works
- execute stores route
- `route_id` can answer segment / waypoint questions

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P2-1 | Define the route persistence schema and artifact mapping | `sql/`, `qbot_route_tools.py`, `api_db.py` | schema inventory, route status tools | Medium | Tables exist for routes, points, segments, waypoints | Yes | No |
| P2-2 | Build a preview-only route import path for GPX / TCX / FIT | `qbot_route_tools.py`, `qbot_artifact_tools.py`, `tools/fit-export/` | `qbot_route_import_preview`, `qbot_route_brief_preview` | Medium | Preview shows exactly what will be stored | Yes | No |
| P2-3 | Persist original artifacts and derived JSON together | `qbot_artifact_tools.py`, `qbot_route_tools.py` | artifact inventory / route import tests | Medium | Original and parsed artifacts are linked | Yes | No |
| P2-4 | Support route briefing queries from stored route IDs | `qbot_route_tools.py`, `qbot_query_processor.py` | route question smoke tests | Medium | Agent can answer route questions from DB data | Yes | No |
| P2-5 | Add read-only route QA for segment / waypoint / surface queries | `qbot_route_tools.py`, `qbot_mcp_adapter.py` | route brief, surface, and preview tests | Low | Route QA works without mutating data | Yes | No |

### P3. Garage 1:1 Store and Agent Use

Objective:
- Preserve old garage data 1:1 and make it searchable and useful.

Scope:
- raw import
- no category invention
- search / list / get
- equipment / clothing / bike context for the agent

Done definition:
- garage raw status OK
- search works
- clothing advice can use garage if available

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P3-1 | Preserve the raw garage schema mapping without inventing categories | `qbot_garage_tools.py`, `qbot_garage_mapper.py`, `sql/garage_raw_import_v1.sql` | `qbot_garage_raw_status`, `qbot_garage_legacy_file_audit` | Medium | Raw import remains 1:1 | Yes | No |
| P3-2 | Keep garage search and retrieval queryable from current data stores | `qbot_garage_tools.py`, `qbot_tool_registry.py` | `qbot_garage_raw_search`, `qbot_garage_raw_get`, `qbot_garage_raw_list` | Medium | Search and list/get work on current source data | Yes | No |
| P3-3 | Keep clothing / bike / equipment advice grounded in garage data when present | `qbot_garage_mapper.py`, `qbot_telegram_tools.py`, `email_reply_processor.py` | clothing self-checks, garage-backed advice tests | Medium | Agent uses garage facts instead of inventing them | Yes | No |
| P3-4 | Separate raw garage inventory from any actuation semantics | `qbot_garage_tools.py`, `qbot_legacy_parity_tools.py` | safety / policy checks | Low | No actuation path is implied by garage inventory | Yes | No |
| P3-5 | Keep bike / component / memory / trip / packing semantics stable | `db.py`, `qbot_garage_tools.py`, `qbot_query_processor.py` | garage QA and smoke tests | Medium | Data model remains readable and consistent | Yes | No |

### P4. Reports and Scheduler

Objective:
- Daily and ride reports remain safe and predictable.

Scope:
- preview
- Telegram send test
- email if configured
- scheduler status
- approval before activation

Done definition:
- preview works
- one send test works
- scheduler is not activated without approval

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P4-1 | Keep daily report preview and send behavior deterministic | `daily_report.py`, `qbot_report_tools.py` | `qbot_daily_report_preview`, `qbot_daily_report_status` | Medium | Preview and send state are accurate | Yes | No |
| P4-2 | Keep ride report preview and send behavior deterministic | `ride_report.py`, `qbot_report_tools.py` | `qbot_ride_report_preview`, `qbot_ride_report_status` | Medium | Report state and channel delivery are stable | Yes | No |
| P4-3 | Keep email delivery optional but explicitly statused | `daily_report.py`, `weekly_review.py`, `ride_report.py` | email-related report status tools | Medium | Email config and delivery status are visible | Yes | No |
| P4-4 | Keep scheduler inventory and activation state visible | `scripts/`, `qbot_report_tools.py`, `qbot_ops_tools.py` | `qbot_reports_schedule_status`, `qbot_backup_timer_status` | Low | Scheduled jobs are documented and checkable | Yes | No |
| P4-5 | Keep report send tests safe and approval-gated | `qbot_report_tools.py`, `qbot_telegram_tools.py` | Telegram send test, email send test | Medium | Send tests prove readiness without spamming | Yes | Yes |

### P5. Controlled Mutating Integrations

Objective:
- Restore Garmin upload, RWGPS sync/upload, and Hammerhead online import safely.

Scope:
- dry-run
- preview
- explicit approval
- audit log

Done definition:
- dry-run proves readiness
- real action is blocked without approval
- the approval path is tested intentionally

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P5-1 | Keep Garmin upload as a previewable controlled action | `garmin_auth.py`, `qbot_garmin_*` tools | `qbot_garmin_upload_dry_run`, `qbot_garmin_upload_status` | High | Upload readiness is explicit and not auto-executed | Yes | Yes |
| P5-2 | Keep RWGPS sync/upload preview-only until explicit approval exists | `tools/rwgps/client.py`, `qbot_route_tools.py` | `qbot_rwgps_dry_run`, `qbot_rwgps_restore_plan` | High | Dry run shows readiness and blocked execution remains blocked | Yes | Yes |
| P5-3 | Keep Hammerhead online import safely previewable | `hammerhead_auth.py`, `qbot-hammerhead-sync` wrappers | `qbot_hammerhead_import_dry_run`, `qbot_hammerhead_import_inventory` | High | Import state is visible without mutating remote state | Yes | Yes |
| P5-4 | Log approval boundaries for every mutating external integration | `qbot_operator_tools.py`, `qbot_legacy_execution_tools.py`, `qbot_tool_registry.py` | approval / policy checks | High | Mutating paths cannot run implicitly | Yes | Yes |
| P5-5 | Distinguish preview, dry-run, and execution in all integration UIs | `qbot_query_processor.py`, `qbot_tool_registry.py`, `qbot_mcp_adapter.py` | preview / dry-run / execute tests | Medium | User and agent can see the mode clearly | Yes | No |

### P6. QExt2 / Karoo Expansion

Objective:
- Support ride-readiness snapshots for Karoo / QExt2 without making the field heavy.

Scope:
- ride-readiness improvements
- route / climb / battery snapshots
- no live field dependency

Done definition:
- QExt2 endpoint remains stable
- route snapshot available pre-ride

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P6-1 | Keep `/ride-readiness` stable for QExt2 / Karoo clients | `qbot_api.py`, `qbot_tools.py` | `qbot_ride_readiness_status` | Low | Endpoint remains JSON and backward compatible | Yes | No |
| P6-2 | Add route / climb / battery summaries to readiness snapshots | `qbot_tools.py`, `qbot_route_tools.py`, `qbot_wellness_store.py` | readiness smoke tests | Medium | Pre-ride status is richer without field dependency | Yes | No |
| P6-3 | Ensure readiness is sourced from local stores plus live integration status | `qbot_tools.py`, `qbot_operator_tools.py` | `qbot_readiness_report`, `qbot_legacy_takeover_status` | Medium | Snapshot explains what is live and what is stored | Yes | No |
| P6-4 | Keep public readiness light and safe | `qbot_api.py`, nginx config, `qbot_mcp_adapter.py` | public endpoint checks | Low | Public access stays narrow and controlled | Yes | No |
| P6-5 | Add route-aware pre-ride summaries for mobile / head unit consumption | `qbot_report_tools.py`, `qbot_route_tools.py` | route briefing / readiness tests | Medium | The pre-ride view is actionable | Yes | No |

### P7. Ops / Backup / Monitoring Hardening

Objective:
- Make QBot maintainable and remove legacy alerting assumptions.

Scope:
- backup / restore drill
- logs / errors
- cron / timer audit
- no legacy `q-bot` / `ngrok` alerts
- health internal / public policy

Done definition:
- backup status OK
- restore preview exists
- legacy alerts disabled

Task queue:

| Task ID | Description | Files likely touched | Tools / tests | Risk | Done criteria | Autonomous | Approval |
|---|---|---|---|---|---|---|---|
| P7-1 | Keep backup / restore drill visible and safe | `qbot_recovery.py`, `scripts/qbot_backup.sh`, `qbot_ops_tools.py` | `qbot_backup_status`, `qbot_restore_drill_status` | Medium | Backups are visible and drill status is explicit | Yes | No |
| P7-2 | Keep log and error reporting cutover-aware | `qbot_ops_tools.py`, `scripts/qbot_operational_state.py` | `qbot_error_summary`, `qbot_logs_overview`, `qbot_test_error_classification` | Medium | Historical test noise is separated from real blockers | Yes | No |
| P7-3 | Audit cron / timers and keep them documented | `scripts/`, systemd examples, `docs/` | schedule inventory tools | Low | Timers and cron jobs are discoverable | Yes | No |
| P7-4 | Retire legacy `q-bot` / `ngrok` alert assumptions | `monitor.py`, `qbot_ops_tools.py`, `qbot_legacy_cutover_tools.py` | status / smoke checks | High | No operational dependency remains on the legacy alerting pattern | Yes | No |
| P7-5 | Keep internal versus public health policy explicit | `qbot_api.py`, nginx config, `qbot_report_tools.py` | health and public web checks | Low | `/q` and `/health` remain blocked publicly | Yes | No |

## 5. Dependencies

- P1 wellness DB and integration status need to settle before Telegram can reliably answer sleep / nutrition / readiness questions.
- P2 route store needs to come before route briefing and route-question answering.
- P3 garage 1:1 import needs to come before clothing / equipment personalization can trust the garage context.
- P4 reports should wait until P1 and P2 are stable enough to produce trustworthy source-backed reports.
- P5 mutating integrations should come after their read-only auth / status surfaces are stable.
- P6 QExt2 readiness depends on P1 integration clarity and P2 route / snapshot availability.
- P7 ops hardening should trail the major data and integration blocks so the maintenance surface reflects the finished architecture.

## 6. Stop Conditions

- Repo becomes dirty unexpectedly during this roadmap work.
- `python3 -m py_compile qbot*.py` fails.
- Public `/q` or `/health` starts returning `200`.
- A secret value appears in the diff or in this roadmap.
- A mutating action would run without approval.
- Any step would require executing legacy scripts or importing legacy modules.

## 7. Recommended Next Action

Recommended next block:
- `P0. Telegram Agent Reliability`

Why:
- Every later block depends on the agent being able to ask the right question, keep context, and produce source-backed answers.
- Without reliable Telegram agent behavior, each integration block keeps behaving like a separate legacy command path.
- This is the best leverage point for end-to-end usefulness with the least risk of reintroducing legacy operational patterns.

## 8. Roadmap Notes

- The archive-backed audit is the source of truth for what the old QBot actually had.
- The current deployment already restores much of the control plane and several integration surfaces.
- The roadmap intentionally treats legacy monitor/ngrok behavior as a negative pattern, not a target.
- OpenWeatherMap-specific parity remains blocked by missing secret/config; current weather should continue via the supported fallback path.
- The roadmap is a work plan, not an implementation request.
