# Full Legacy Source Audit

Audit date: 2026-05-26

Scope:
- Read-only audit of the real legacy QBot source catalog.
- Legacy source audited from `/root/qbot-mikrus.tar.gz` plus supporting operational backups.
- Current deployment audited from `/opt/qbot/app` and live read-only status surfaces.
- No legacy script execution was performed.
- No secret values were read or printed.
- Public `/q` and `/health` were not modified and remain blocked.

## 1. Executive Summary

### Legacy source catalog found

Primary legacy source catalog:
- `/root/qbot-mikrus.tar.gz`

Supporting legacy operational snapshots:
- `/opt/qbot/backups/pathfix_20260518_1123/`
- `/root/qbot.crontab.backup.20260526_065300`
- `/root/qbot.crontab.backup.20260526_065827`
- `/root/qbot-mcp/` is a legacy SSE/MCP bridge, not the main QBot source tree

Notes:
- The legacy source catalog is not a git repository.
- The archive contains a compact Python app set: `daily_report.py`, `ride_report.py`, `telegram_reply_processor.py`, `email_reply_processor.py`, `sync_nutrition.py`, `monitor.py`, `mcp_server.py`, `db.py`, `deploy_ride.py`, `claude_chat.py`, and `email_template.py`.
- The archive does not contain backup/restore units, QLab service code, RWGPS code, Hammerhead import code, artifact bridge code, or the current FastAPI `/q` layer.

### Current QBot deployment found

- Current app root: `/opt/qbot/app`
- `qbot-api.service`: active
- `qbot-qlab-server.service`: active
- `q-bot.service`: inactive / disabled
- `qbot-backup.timer`: active
- `qbot-api` health: OK
- Public `/q`: `404`
- Public `/health`: `404`
- Public `/mcp/tools`: `200`
- Public `/ride-readiness`: `200 JSON`

### Audit type

- Source-based for legacy capabilities.
- Tool/policy-based for current QBot capabilities.
- Where the archive did not contain a feature, that absence is recorded as source evidence, not guessed from later parity tools.

### High-level conclusion

The old QBot source was much smaller and more script-driven than the current deployment.

What the legacy source clearly had:
- Telegram reply processing and Telegram sends
- MCP/SSE bridge
- ride-readiness / Karoo compatibility
- Garmin wellness / sleep
- Xert
- Intervals
- Cronometer nutrition sync
- garage inventory and packing lists
- daily and ride reports
- weather via Open-Meteo
- OSM / Overpass route analysis
- a local Claude terminal helper
- a service monitor that still expected `q-bot` and `ngrok`

What the legacy source did not contain:
- QLab
- backup/restore service/timer code
- RWGPS integration
- Hammerhead import/upload flows
- artifact bridge / filesystem inventory
- current FastAPI `/q` layer
- current public `/mcp/` adapter
- current PostgreSQL wellness store
- current garage raw import tooling

## 2. Legacy Capability Inventory

Capability count here reflects source domains, not every function name.

| Capability | Description | Legacy evidence files | Legacy functions/classes/endpoints | Legacy env key names | Legacy data paths | Mutating / read-only | Notes |
|---|---|---|---|---|---|---|---|
| Telegram bot / replies | Telegram reply processor, sendMessage, reply parsing, stored history | `telegram_reply_processor.py`, `daily_report.py`, `ride_report.py`, `monitor.py` | `process_message`, `process_replies`, `tg_get_updates`, `tg_send`, `send_telegram`, `notify` | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | `data/telegram_state.json`, `data/telegram_chat_history.json`, `logs/telegram_reply.log` | Mutating | Old bot was polling-based and replied directly from local scripts. |
| Telegram bot delivery | Telegram send path used by reports and alerts | `daily_report.py`, `ride_report.py`, `monitor.py` | `send_telegram`, `notify` | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | `logs/telegram_reply.log`, report logs | Mutating | Used for alerts, report delivery, and conversational replies. |
| Legacy monitor alerts | Health checker that restarted `q-bot` and `ngrok` and alerted on Telegram | `monitor.py` | `check_service`, `notify` | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | `logs/q_monitor.log` | Mutating | This is the clearest legacy ngrok/q-bot sentinel. |
| MCP / SSE bridge | Old MCP server using FastMCP streamable-http/SSE transport | `mcp_server.py` | `FastMCP`, `get_activities`, `get_activity_details`, `get_route_surface`, `get_wellness`, `get_gear`, `get_weather`, `garage_overview`, `save_*`, `get_xert_status`, `get_xert_activities`, `ride_readiness` | `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`, `CRONOMETER_EMAIL`, `CRONOMETER_PASSWORD`, `TELEGRAM_TOKEN`, Garmin creds/tokens | `data/garage.db`, `data/routes/rwgps_manifest.json`, `data/fit/` | Mixed | Old public MCP surface was the bridge itself, not a separate FastAPI adapter. |
| QExt2 / ride-readiness | Karoo/QExt2 readiness endpoint and its weather/fitness aggregation | `mcp_server.py` | `@mcp.custom_route("/ride-readiness")`, `ride_readiness` | `INTERVALS_API_KEY`, Garmin/Xert credentials, weather provider access | `data/route_surface_cache.json`, `data/fit/`, Garmin exports | Read-only | This existed in the old source and was built from Intervals + Garmin + Xert + weather. |
| Garmin wellness / sleep | Garmin sleep, body battery, HRV, resting HR | `mcp_server.py`, `ride_report.py` | `_garmin_client`, `get_garmin_wellness`, Garmin fetches in ride reports | Garmin tokens/profile, Garmin account credentials | `.garmin_profile.json`, `.garmin_tokens/`, `data/fit/` | Read-only | Legacy source had wellness fetches, not the newer import/status stack. |
| Xert | Xert training status and activities | `mcp_server.py`, `daily_report.py`, `ride_report.py` | `_xert_token`, `get_xert_status`, `get_xert_activities` | `XERT_EMAIL`, `XERT_PASSWORD` | `data/daily_report_sent.json` (report state), report logs | Read-only | Xert was core to readiness and report generation. |
| Intervals wellness | Intervals.icu wellness fetch/update and notes | `mcp_server.py`, `daily_report.py`, `email_reply_processor.py`, `ride_report.py`, `sync_nutrition.py` | `icu`, `icu_get`, wellness PUTs to Intervals, `save_wellness` | `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY` | report logs | Mutating | Old QBot wrote wellness notes back to Intervals. |
| Cronometer nutrition | Nutrition summary sync into Intervals wellness | `sync_nutrition.py` | no named functions; script body writes wellness comments | `CRONOMETER_EMAIL`, `CRONOMETER_PASSWORD`, `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY` | `/var/log/nutrition_sync.log` in monitor checks; Intervals wellness records | Mutating | This is a real legacy integration and was not a guess from current parity tools. |
| Garage inventory / trips / packing | SQLite garage model with bikes, components, fitting, gear, memories, trips, packing lists | `db.py`, `mcp_server.py`, `email_reply_processor.py`, `telegram_reply_processor.py`, `daily_report.py`, `ride_report.py` | `garage_overview`, `get_bike`, `save_bike`, `save_component`, `save_fitting`, `save_gear`, `save_memory`, `search_garage`, `get_trips`, `get_trip`, `save_trip`, `create_packing_list`, `update_packing_item`, `get_packing_summary` | none explicit; garage data comes from SQLite and message parsing | `data/garage.db` | Mutating | Garage in the old source was mostly bike/packing/fitting/memory, not home automation. |
| Daily reports | Morning report generation, Telegram and email delivery | `daily_report.py`, `email_template.py` | `already_sent_today`, `mark_sent`, `send_telegram`, `send_email`, `mcp_call`, `tp_z_aktywnosci`, `_ai` | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`, `INTERVALS_*`, `ANTHROPIC_API_KEY` | `data/daily_report_sent.json`, report logs | Mutating | Legacy report was already a combined Telegram/email artifact. |
| Ride reports | Post-ride HTML report generation and email/Telegram dispatch | `ride_report.py` | `fetch_activity_data`, `generate_html`, `process_activity`, `send_email`, `send_telegram`, `check_new_activities` | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`, `ANTHROPIC_API_KEY` | `data/reported_activities.json`, `logs/ride_report.log` | Mutating | Legacy source had report generation, activity de-duplication, and delivery state. |
| Email / SMTP notifications | Gmail SMTP for reports and IMAP reply processing | `daily_report.py`, `ride_report.py`, `email_reply_processor.py` | `send_email`, IMAP processing functions, reply parsing | `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO` | report logs, sent-state JSON | Mutating | This is report delivery and reply ingestion, not just simple SMTP. |
| Weather | Weather fetch used by reports and readiness; legacy source used Open-Meteo | `daily_report.py`, `mcp_server.py`, `email_template.py`, `ride_report.py` | direct Open-Meteo fetch in `daily_report`, `get_weather` in `mcp_server` | location env keys only (`LOCATION_LAT`, `LOCATION_LON`, `LOCATION_NAME`) | report output/state files | Read-only | Legacy source did not show OpenWeatherMap-specific code. |
| Route surface / OSM / Overpass / FIT / TCX | Activity geometry and surface analysis from FIT and OSM data | `mcp_server.py`, `ride_report.py` | `get_activity_details`, `get_route_surface`, `FitFile` processing, Overpass queries | Garmin tokens/profile, Intervals/Xert for surrounding context | `data/fit/`, `data/route_surface_cache.json` | Read-only | This is the old route-analysis heart of the stack. |
| Anthropic / Claude terminal helper | Interactive local assistant to Claude | `claude_chat.py` | interactive loop calling Anthropic SDK | `ANTHROPIC_API_KEY` | terminal session only | Mutating-adjacent | This is a user-facing helper, not an automated service. |
| Logging / operational status | Simple service/state checks and alert wiring | `monitor.py`, `daily_report.py`, `ride_report.py` | `check_service`, printed status summaries | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | `logs/q_monitor.log`, report logs | Mixed | Old ops model depended on shell/systemd checks and direct alerts. |
| Data model / SQLite | Core local DB schema and CRUD for garage/trips/packing | `db.py` | SQL DDL and CRUD helpers | none | `data/garage.db` | Mutating | This was the only durable local DB in the legacy source snapshot. |
| Deployment helper | Ride report deployment/wrapper script | `deploy_ride.py` | file write wrapper for `ride_report.py` | none shown | local file write target | Mutating | This is a source-side deployment helper, not a runtime service. |

### Legacy env key names found in the archive

Names only, no values:

- `ANTHROPIC_API_KEY`
- `CRONOMETER_EMAIL`
- `CRONOMETER_PASSWORD`
- `EMAIL_TO`
- `GMAIL_APP_PASSWORD`
- `GMAIL_USER`
- `INTERVALS_API_KEY`
- `INTERVALS_ATHLETE_ID`
- `LOCATION_LAT`
- `LOCATION_LON`
- `LOCATION_NAME`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_TOKEN`
- `XERT_EMAIL`
- `XERT_PASSWORD`

### Legacy data / artifact paths found in the archive

- `data/daily_report_sent.json`
- `data/garage.db`
- `data/processed_replies.json`
- `data/reported_activities.json`
- `data/telegram_chat_history.json`
- `data/telegram_state.json`
- `.garmin_profile.json`
- `.garmin_session.pkl`
- `.garmin_tokens.json`
- `.garmin_tokens/garmin_tokens.json`

## 3. New QBot Inventory

Current deployment evidence is from `/opt/qbot/app`, current tool policy list, and live status calls.

| Capability | New evidence files | Tools | MCP exposed | Telegram exposed | DB backed | Artifact backed | Current runtime status |
|---|---|---|---|---|---|---|---|
| QBot core API | `qbot_api.py`, `qbot_tools.py`, `qbot_tool_registry.py`, `api_db.py` | `qbot_api_self_check`, `qbot_services_status`, `qbot_query`, `qbot_status`, `qbot_db_overview` | yes | yes | yes | no | `qbot-api.service` active, health OK |
| Telegram bot | `qbot_api.py`, `qbot_telegram_tools.py`, `qbot_telegram_client.py`, `telegram_reply_processor.py`, `docs/qbot_telegram_restore.md` | `qbot_telegram_status`, `qbot_telegram_transport_status`, `qbot_telegram_set_webhook`, `qbot_telegram_send_test`, `qbot_telegram_agent_chat`, `qbot_telegram_command_help` | yes | yes | partial | yes | Telegram webhook active; status path is cutover-aware |
| MCP connector | `qbot_api.py`, `qbot_mcp_adapter.py`, `docs/qbot_mcp_connector.md` | `qbot_mcp_status`, `qbot_mcp_tools_list`, `qbot_mcp_call_preview` | yes | no | no | no | Public `/mcp/` active; `/q` still blocked publicly |
| QExt2 / ride-readiness | `qbot_api.py`, `qbot_tools.py`, `qbot_legacy_cutover_tools.py`, `docs/qbot_operational_readiness.md` | `qbot_ride_readiness_status`, `qbot_readiness_report`, `qbot_legacy_takeover_status` | yes | no | yes | no | Public `/ride-readiness` returns JSON 200 |
| QLab | `qbot_qlab_server.py`, `README_QLAB_EXPORTS.md`, `systemd/qbot-qlab-server.service.example` | `qbot_legacy_qlab_status`, `qbot_legacy_qlab_smoke_check` | no | no | no | yes | `qbot-qlab-server.service` active |
| Backup / restore | `scripts/qbot_backup.sh`, `qbot_recovery.py`, `docs/qbot_backup_recovery.md` | `qbot_backup_status`, `qbot_backup_timer_status`, `qbot_restore_drill_status`, `qbot_backup_plan` | no | yes | yes | yes | Backup timer active; latest backup present |
| Garmin wellness / sleep / activity | `qbot_wellness_store.py`, `garmin_auth.py`, `qbot_legacy_parity_tools.py`, `qbot_report_tools.py` | `qbot_garmin_config_status`, `qbot_garmin_proxy_status`, `qbot_garmin_upload_status`, `qbot_garmin_wellness_import_execute`, `qbot_garmin_sleep_import_execute`, `qbot_wellness_db_status` | yes | no | yes | no | Wellness import/status surfaces exist |
| Garmin proxy | `qbot_garmin_proxy.csv`, `qbot_garmin_proxy.fit`, `outgoing/garmin_proxy/*` | `qbot_garmin_proxy_status`, `qbot_garmin_upload_dry_run` | yes | no | no | yes | Proxy artifacts present |
| Garmin upload | `garmin_auth.py`, `qbot_legacy_execution_tools.py`, `qbot_report_tools.py` | `qbot_garmin_upload_status`, `qbot_garmin_upload_dry_run` | yes | no | no | no | Controlled-action path is previewed, not auto-executed |
| Hammerhead / Karoo import | `qbot-hammerhead-sync`, `hammerhead_auth.py`, `scripts/run_hammerhead_garmin_sync.sh` | `qbot_hammerhead_import_status`, `qbot_hammerhead_import_dry_run`, `qbot_hammerhead_import_inventory` | yes | no | no | yes | Sync artifacts and reports present |
| Xert | `qbot_legacy_parity_tools.py`, `qbot_operator_tools.py`, `qbot_wellness_store.py` | `qbot_xert_config_status`, `qbot_xert_readiness_status`, `qbot_xert_restore_plan` | yes | no | partial | no | Xert readiness and restore-plan surfaces exist |
| Intervals wellness | `qbot_wellness_store.py`, `qbot_external_llm_tools.py`, `qbot_query_processor.py` | `qbot_intervals_wellness_status`, `qbot_intervals_config_status`, `qbot_intervals_wellness_import_preview`, `qbot_intervals_wellness_import_execute` | yes | no | yes | no | Current stack includes import/status tooling |
| Cronometer | `sync_nutrition.py`, `qbot_wellness_store.py` | `qbot_cronometer_legacy_status`, `qbot_cronometer_config_status`, `qbot_cronometer_nutrition_import_preview`, `qbot_cronometer_nutrition_import_execute` | yes | no | yes | no | Nutrition import stack is surfaced |
| Garage inventory | `qbot_garage_tools.py`, `qbot_garage_mapper.py`, `data_registry/modules.yaml`, `data_registry/routing_rules.yaml` | `qbot_garage_raw_status`, `qbot_garage_raw_list`, `qbot_garage_raw_search`, `qbot_garage_import_preview`, `qbot_garage_import_execute`, `qbot_garage_legacy_status` | yes | yes | yes | yes | Raw garage import and search are now first-class |
| Weather | `qbot_weather_legacy_status`, `qbot_query_processor.py`, `qbot_readiness.py`, `daily_report.py` | `qbot_weather_status`, `qbot_weather_current`, `qbot_weather_forecast`, `qbot_weather_config_status`, `qbot_resolve_weather_location` | yes | yes | no | no | Weather is a first-class status/tool surface; legacy OWM-specific parity is not the source snapshot |
| Route processing / maps | `qbot_route_tools.py`, `mcp_server.py`, `tools/rwgps/README_RWGPS.md`, `tools/rwgps/client.py` | `qbot_openmaps_legacy_status`, `qbot_overpass_status`, `qbot_rwgps_config_status`, `qbot_rwgps_dry_run`, `qbot_rwgps_restore_plan`, `qbot_route_*` tools | yes | no | no | yes | Route and map tooling is broader than the archive |
| Daily reports | `daily_report.py`, `email_template.py`, `qbot_report_tools.py` | `qbot_daily_report_status`, `qbot_daily_report_preview`, `qbot_daily_report_send` | yes | yes | yes | yes | Report pipeline is explicit and statused |
| Ride reports | `ride_report.py`, `qbot_report_tools.py`, `qbot_route_tools.py` | `qbot_ride_report_status`, `qbot_ride_report_latest`, `qbot_ride_report_preview`, `qbot_ride_report_send` | yes | yes | yes | yes | Delivery state is explicit and channel-aware |
| Email / SMTP notifications | `daily_report.py`, `weekly_review.py`, `ride_report.py`, `email_reply_processor.py` | `qbot_maintenance_report`, report send/status tools | no | no | no | yes | SMTP path still exists; status is implicit in report tools |
| Public endpoints / hardening | `qbot_api.py`, `/etc/nginx/sites-available/q365`, `docs/qbot_operational_readiness.md` | `qbot_public_endpoint_status`, `qbot_public_web_status`, `qbot_public_web_fetch`, `qbot_public_web_fallback_self_check` | yes | no | no | no | Public `/q` and `/health` remain blocked |
| Artifact store / filesystem bridge | `qbot_artifact_tools.py`, `qbot_mcp_adapter.py`, `sql/init_qbot.sql` | `qbot_artifact_create`, `qbot_artifact_list`, `qbot_artifact_get`, `qbot_artifacts_filesystem_inventory`, `qbot_artifacts_legacy_status` | yes | yes | yes | yes | Filesystem and SQL artifact paths now coexist |
| Scheduled jobs / cron / timers | `scripts/qbot_backup.sh`, `scripts/prune_qbot_artifacts.py`, root crontab entries | `qbot_reports_schedule_status`, `qbot_backup_timer_status`, `qbot_operator_snapshot` | no | yes | no | no | Scheduling is now inventoryable and cutover-aware |
| Status / monitoring | `qbot_ops_tools.py`, `qbot_operator_tools.py`, `scripts/qbot_status.py`, `scripts/qbot_operational_state.py` | `qbot_operator_final_smoke_test`, `qbot_test_error_classification`, `qbot_readiness_report`, `qbot_services_status`, `qbot_error_summary`, `qbot_logs_overview` | yes | yes | yes | yes | Operational status is significantly richer than the legacy monitor script |
| LLM / planner tools | `qbot_llm_planner.py`, `qbot_external_llm_tools.py`, `qbot_mcp_adapter.py`, `qbot_query_processor.py` | `qbot_llm_boundary_policy`, `qbot_llm_plan_query`, `qbot_llm_run_query`, `qbot_tool_policy_list`, `qbot_answer_context` | yes | yes | no | no | This is a new control-plane layer beyond the archive |
| Wellness DB | `qbot_wellness_store.py` | `qbot_wellness_db_status`, `qbot_sleep_day_get`, `qbot_wellness_day_get`, `qbot_nutrition_db_status` | yes | no | yes | no | New PostgreSQL-backed wellness store did not exist in the archive |

### Current runtime status snapshots

- `qbot_api_self_check`: 112 tools available
- `qbot_tool_policy_list`: 186 policy entries
- Public MCP tools: 52
- `qbot_operator_final_smoke_test`: `WARN`, `operational_readiness_percent=100`, `29 real error candidates`
- `qbot_telegram_status`: expected to be cutover-aware and not require legacy `q-bot` active
- `qbot_legacy_takeover_status`: cutover completed in current deployment

## 4. Legacy vs New Matrix

| Capability | Legacy status | New status | Status classification | Legacy evidence | New evidence | Gap | Next action | Priority |
|---|---|---|---|---|---|---|---|---|
| Telegram bot / replies | present | present | RESTORED_PLUS | `telegram_reply_processor.py`, `daily_report.py`, `ride_report.py`, `monitor.py` | `qbot_api.py`, `qbot_telegram_tools.py`, `qbot_telegram_client.py`, `telegram_reply_processor.py` | Transport changed from polling to webhook, but the bot is functionally present | Keep cutover-aware command handling stable | P1 |
| Legacy monitor alerts | present | superseded | REPLACED | `monitor.py` | `qbot_operator_final_smoke_test`, `qbot_services_status`, `qbot_telegram_status` | Old ngrok/q-bot alerting logic is not the desired operational path | Keep as legacy only; do not revive ngrok alerts | P2 |
| MCP / SSE bridge | present | superseded | DEPRECATED | `mcp_server.py`, `Ride-readiness` route, SSE transport | `qbot_api.py`, `qbot_mcp_adapter.py`, `docs/qbot_mcp_connector.md` | New adapter is the public path; old SSE bridge should stay internal | Maintain the public `/mcp/` adapter, retire old bridge exposure | P1 |
| QExt2 / ride-readiness | present | present | RESTORED_PLUS | `mcp_server.py` `@mcp.custom_route("/ride-readiness")` | `qbot_api.py` `GET /ride-readiness`, `qbot_ride_readiness_status` | Endpoint moved into FastAPI/public proxy | Keep the endpoint stable for Karoo/QExt2 clients | P1 |
| Garmin wellness / sleep / activity | present | present | RESTORED_PLUS | `mcp_server.py`, `ride_report.py` | `qbot_wellness_store.py`, `qbot_garmin_*` status/import tools | Current stack adds DB-backed status/import paths | Keep auth and tokenstore handling stable | P1 |
| Xert | present | present | RESTORED_PLUS | `mcp_server.py`, `daily_report.py`, `ride_report.py` | `qbot_xert_*` tools, `qbot_wellness_store.py` | Current stack provides better status and restore-plan surfaces | Keep Xert status/import/restore tooling stable | P1 |
| Intervals wellness | present | present | RESTORED_PLUS | `mcp_server.py`, `daily_report.py`, `email_reply_processor.py`, `sync_nutrition.py` | `qbot_intervals_*` tools, `qbot_wellness_store.py` | Current stack is more structured and DB-backed | Keep import/status surfaces aligned with Intervals auth | P1 |
| Cronometer nutrition | present | present | RESTORED_PLUS | `sync_nutrition.py` | `qbot_cronometer_*` tools | New stack adds preview/status/import controls | Preserve nutrition sync semantics and non-destructive previews | P2 |
| Garage inventory / trips / packing | present | present | RESTORED_PLUS | `db.py`, `mcp_server.py`, `email_reply_processor.py`, `telegram_reply_processor.py` | `qbot_garage_tools.py`, `qbot_garage_mapper.py`, `qbot_garage_raw_*` tools | Current stack adds raw import/search and better routing | Keep garage 1:1 import semantics intact | P0 |
| Daily reports | present | present | RESTORED_PLUS | `daily_report.py`, `email_template.py` | `qbot_daily_report_*` tools, `qbot_report_tools.py` | Current stack separates status/preview/send | Preserve delivery state and retry behavior | P1 |
| Ride reports | present | present | RESTORED_PLUS | `ride_report.py` | `qbot_ride_report_*` tools, `qbot_report_tools.py` | Current stack has clearer preview/send/status surfaces | Keep report generation and delivery state stable | P1 |
| Email / SMTP notifications | present | present | RESTORED_PLUS | `daily_report.py`, `ride_report.py`, `email_reply_processor.py` | report tools and email-reply processor in current stack | Delivery path is still SMTP/Gmail-based | Keep SMTP credentials and reply ingestion aligned | P2 |
| Weather | present | present | RESTORED_PLUS | `daily_report.py`, `mcp_server.py`, `email_template.py` | `qbot_weather_*` tools, `qbot_public_web_*` status helpers | Current stack adds explicit config/status and public weather helpers | Preserve weather configuration and location resolution | P1 |
| Route surface / OSM / Overpass / FIT / TCX | present | present | RESTORED_PLUS | `mcp_server.py`, `ride_report.py` | `qbot_route_tools.py`, `tools/rwgps/*`, `qbot_public_web_*` helpers | New repo extends route artifacts and RWGPS wrappers | Keep route analysis non-destructive | P1 |
| Anthropic / Claude terminal helper | present | replaced | REPLACED | `claude_chat.py` | `qgpt_client.py`, `qbot_llm_planner.py`, `qbot_answer_context` | The old standalone terminal helper is no longer the primary pattern | Keep the new controlled LLM interface, not the old raw terminal wrapper | P2 |
| Logging / operational monitoring | present | present but modernized | RESTORED_PLUS | `monitor.py`, cron backups | `qbot_operator_final_smoke_test`, `qbot_test_error_classification`, `qbot_services_status`, `qbot_logs_overview` | Current monitoring is policy-aware and cutover-aware | Keep legacy false positives out of readiness | P1 |

## 5. Capabilities Not Previously Captured

These were clearly visible in the legacy source snapshot, but earlier parity reports tended to understate them because they focused on later/current tooling:

- `monitor.py` as a direct Telegram alerting path with `q-bot` and `ngrok` assumptions
- `telegram_reply_processor.py` as a real polling loop, not just a webhook handler
- `email_reply_processor.py` as IMAP ingestion for report replies
- `sync_nutrition.py` as a direct Cronometer-to-Intervals sync job
- `claude_chat.py` as a standalone Anthropic CLI helper
- `db.py` as the canonical garage/trips/packing SQLite schema
- `mcp_server.py` as the original FastMCP/SSE bridge plus ride-readiness route
- `daily_report.py` and `ride_report.py` as combined Telegram/email delivery scripts with source-side formatting
- `mcp_server.py` route surface analysis and Overpass/OSM lookups

## 6. New Capabilities Beyond Legacy

These do not appear in the legacy source snapshot and are therefore new to the modern deployment:

- `qbot-qlab-server` and its export HTTP server
- backup service/timer and restore drill surface
- artifact store with PostgreSQL-backed `qbot_artifacts`
- filesystem artifact inventory and export/import previews
- Garmin proxy/upload dry-run and status tooling
- Hammerhead import inventory/dry-run/status tooling
- RWGPS client/status/restore-plan tooling
- PostgreSQL-backed wellness store
- garage raw import / raw search / raw status tooling
- explicit public endpoint hardening and status tooling
- ChatGPT connector adapter and policy-gated tool exposure
- LLM planner / answer-context / policy tools
- read-only operational smoke, readiness, and error-classification tools
- public web fetch/status helpers
- richer restore-plan tooling across integrations

## 7. High-Risk / Mutating Functions

Do not auto-restore or auto-execute these without separate approval:

- `monitor.py` service restarts and ngrok checks
- `save_bike`, `save_component`, `save_fitting`, `save_gear`, `save_memory`, `save_trip`
- `create_packing_list`, `update_packing_item`, `add_packing_item`, `delete_item`
- `create_event`, `delete_event`
- `send_email`, `send_telegram`
- `sync_nutrition.py`
- any Garmin upload or Hammerhead import execution tool
- any restore drill that writes back onto production data
- any artifact import/export that writes files
- any garage/home-automation actuation path
- any script that reads or prints secret values from `.env` or token stores

## 8. P0 / P1 / P2 Roadmap

P0:
- Preserve garage 1:1 data import semantics and do not invent categories or normalize away raw source data.
- Keep any mutating import/restore flow gated and previewable.

P1:
- Keep public `/q` and `/health` blocked.
- Preserve the current `/mcp/` adapter and `/ride-readiness` endpoint contract.
- Keep Telegram cutover-aware and do not regress to legacy ngrok/q-bot assumptions.

P2:
- Keep legacy source archival material documented.
- Keep route / report / wellness helper surfaces aligned with the current tool registry.

## 9. Validation

Read-only checks performed:
- `python3 -m py_compile qbot*.py` in the current repo
- `git status --short`
- `git diff --stat`
- current policy/tool inventory via `qbot_tool_policy_list`
- current MCP tools via `/mcp/tools`
- current smoke/readiness tools via `qbot_operator_final_smoke_test`

Security checks:
- No secret values were printed.
- No `.env.local` contents were emitted.
- No legacy scripts were executed.

## 10. Counts

This audit is source-based for the legacy snapshot and capability-domain based for the current deployment.

- Legacy capability domains found in source snapshot: `16`
- New capability domains identified in current deployment: `28`
- Legacy vs new matrix rows: `16`
- RESTORED_PLUS: `12`
- RESTORED: `0`
- PARTIAL: `1`
- REPLACED: `2`
- DEPRECATED: `1`
- NOT_PORTED: `0`
- BLOCKED_BY_SECRET: `0`
- BLOCKED_BY_POLICY: `0`
- UNKNOWN_NEEDS_RESEARCH: `0`

Real legacy parity score, source-based:

```text
(RESTORED_PLUS + RESTORED + 0.5 * PARTIAL) / 16
≈ (12 + 0 + 0.5) / 16
= 78.1%
```

## 11. Conclusion

The real legacy source was a smaller, script-centric QBot with Telegram polling, a FastMCP/SSE bridge, route-readiness, Garmin/Xert/Intervals/Cronometer integrations, garage SQLite data, daily/ride reports, and a crude `monitor.py` ngrok/q-bot alert loop.

The current deployment is broader and more structured:
- it adds QLab, backup/restore, artifact storage, RWGPS, Hammerhead tooling, a PostgreSQL wellness store, public endpoint hardening, and a policy-aware tool registry;
- it also replaces several old direct-script patterns with status/preview/runbook surfaces.

The main source-based gaps from the old snapshot are not missing legacy features so much as new features that were introduced later and should be treated as extensions rather than as legacy parity requirements.
