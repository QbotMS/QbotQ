# QBot Legacy Full Audit Report

Scope: read-only audit of the legacy QBot surface versus the current QBot architecture, verified on 2026-05-25.

Methodology:
- I only read files, configs, logs, and local HTTP/systemd status.
- I did not execute legacy scripts.
- I did not import legacy modules in the audit process.
- I did not read or print `.env.local` values.
- I did not change application code.
- I did not touch public `/q` or `/health` routing.

Environment snapshot:
- `qbot-api.service`: active
- `qbot-qlab-server.service`: active
- `q-bot.service`: inactive, disabled
- `qbot-backup.timer`: active, enabled
- `ngrok-qbot.service`: inactive
- Cron jobs present for Hammerhead/Garmin sync and artifact pruning
- `/ride-readiness`: `200 JSON`
- `/q`: `404`
- `/health`: `404`
- `/mcp/tools`: `200`, 23 exposed MCP tools
- `qbot_operator_final_smoke_test`: `100%` operational readiness, `WARN` only because the worktree is dirty
- `qbot_telegram_status`: `OK`
- `qbot_legacy_takeover_status`: `100%`

Current new Qbot surface observed:
- `qbot_api_self_check` reports 112 available tools
- Public MCP adapter exposes read-only tools and blocks write tools unless token-gated
- Public endpoints allowed today are `/telegram/webhook/`, `/mcp/`, and `/ride-readiness`
- Public `/q` and `/health` remain intentionally blocked

Verified read-only diagnostic surfaces:
- `qbot_api_tools_list`
- `qbot_tool_policy_list`
- `qbot_legacy_parity_matrix`
- `qbot_legacy_full_parity_audit`
- `qbot_weather_legacy_status`
- `qbot_garage_legacy_status`
- `qbot_artifacts_legacy_status`
- `qbot_external_integrations_report`

## Main Audit Table

| legacy capability | evidence files | evidence artifacts | old endpoint/service/handler | current new Qbot equivalent | status | risk | safety class | exposed in Telegram | exposed in MCP | required work | priority | can restore today |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Telegram bot | `qbot_api.py`, `qbot_telegram_tools.py`, `qbot_telegram_client.py`, `telegram_reply_processor.py`, `docs/qbot_telegram_restore.md` | `data/telegram_state.json`, `data/telegram_chat_history.json`, `logs/telegram_reply.log` | `/telegram/webhook/{secret}`, `/status`, `/legacy`, `/weather_status`, `/garage_status`, `/artifacts`, `/integrations` | `qbot_telegram_status`, `qbot_telegram_transport_status`, webhook handler in `qbot_api.py` | RESTORED | LOW | READ_ONLY | yes | yes | Maintain cutover-aware command handling and webhook secret protection | P2 | yes |
| MCP connector | `qbot_api.py`, `qbot_mcp_adapter.py`, `mcp_server.py`, `docs/qbot_mcp_connector.md` | `systemd/qbot-api.service.example`, `systemd/qbot-mcp-bridge.service` traces | Legacy `mcp_server.py` streamable HTTP / SSE, `/mcp/`, `/sse`, `/messages/` | `qbot_api.py` `/mcp/`, `qbot_mcp_status`, `qbot_mcp_tools_list`, `qbot_mcp_call_preview` | RESTORED | MEDIUM | READ_ONLY | no | yes | Keep the public adapter read-only; if write tools ever return, require explicit token gating | P2 | yes |
| QExt2 / ride-readiness | `qbot_api.py`, `mcp_server.py`, `docs/qbot_operational_readiness.md` | `outgoing/ride_report_previews/*.html`, `outgoing/qbot_hammerhead_sync_latest_report.json` | Legacy `@mcp.custom_route("/ride-readiness")` in `mcp_server.py`; public Karoo/QExt2 URL used the old route | `qbot_ride_readiness_status`, `GET /ride-readiness`, nginx proxy to `127.0.0.1:8001` | RESTORED | LOW | READ_ONLY | no | no | Keep the lightweight read-only readiness payload stable | P2 | yes |
| QLab | `qbot_qlab_server.py`, `README_QLAB_EXPORTS.md`, `systemd/qbot-qlab-server.service.example` | `qlab_exports/*.json`, `outgoing/ride_report_previews/*.html` | `qbot-qlab-server.service`, `/health`, `/files`, `/export-fit` | `qbot_qlab_server.py`, `qbot_legacy_qlab_status`, `qbot_legacy_qlab_smoke_check` | RESTORED | MEDIUM | READ_ONLY | no | no | Keep the export server and smoke check aligned with file layouts | P2 | yes |
| Garmin/FIT proxy | `garmin_auth.py`, `qbot_legacy_parity_tools.py`, `qbot_legacy_wrapper_tools.py`, `scripts/run_hammerhead_garmin_sync.sh` | `outgoing/garmin_proxy/*.csv`, `outgoing/garmin_proxy/*.fit`, `qbot_garmin_proxy.csv`, `qbot_garmin_proxy.fit` | Old Garmin proxy/upload helpers and sync scripts | `qbot_garmin_proxy_status`, `qbot_legacy_garmin_status` | PARTIAL | MEDIUM | READ_ONLY | no | yes | Finish the direct parity bridge from proxy artifacts to a single surfaced status/report path | P0 | yes |
| Garmin upload | `garmin_auth.py`, `qbot_legacy_execution_tools.py`, `qbot_legacy_wrapper_tools.py`, `scripts/run_hammerhead_garmin_sync_profile.sh` | `config/profiles/*.env`, `outgoing/garmin_proxy/*`, `logs/hammerhead-garmin-sync*.log` | Legacy Garmin upload code paths and profile sync scripts | `qbot_garmin_upload_status`, `qbot_legacy_garmin_dry_run` | PARTIAL | MEDIUM | CONTROLLED_ACTION | no | yes | Restore a complete preview/report path for upload parity and keep any write step operator-gated | P0 | yes |
| Hammerhead FIT import | `hammerhead_auth.py`, `qbot-hammerhead-sync`, `scripts/add_hammerhead_garmin_profile.sh` | `outgoing/hammerhead_originals/*.fit`, `state/*processed_hammerhead_activities.json`, `logs/hammerhead-garmin-sync*.log` | Hammerhead/Karoo sync and import pipeline | `qbot_hammerhead_import_status` | PARTIAL | MEDIUM | READ_ONLY | no | yes | Add a dedicated read-only import coverage report and keep imports separated from write flows | P0 | yes |
| GPX / TCX / FIT processing | `qlab_replay_export.py`, `tools/fit-export/fit_export.py`, `qbot-fit-rewrite`, `fit_rewrite_diff.txt`, `scripts/qbot_smoke_tests.py` | `qbot_garmin_proxy.fit`, `outgoing/hammerhead_originals/*.fit`, `qlab_exports/*.json` | FIT parsing, replay export, export-fit handlers | `qbot_qlab_server.py` export-fit endpoint, `qlab_replay_export.py`, `tools/fit-export/*` | RESTORED | LOW | READ_ONLY | no | no | Keep the parsing/export code paths and smoke tests stable | P2 | yes |
| CSV export | `qbot_garmin_proxy.csv`, `qbot_garmin_proxy_latest.csv`, `tools/fit-export/fit_export.py` | `outgoing/garmin_proxy/*.csv`, `qbot_garmin_proxy_latest.csv` | Old CSV export helpers and Garmin proxy CSV output | `qbot_legacy_export_status`, `qbot_legacy_export_dry_run`, export surfaces in artifact tools | RESTORED | LOW | READ_ONLY | no | no | Preserve current CSV export naming and artifact emission | P2 | yes |
| JSON reports | `daily_report.py`, `weekly_review.py`, `ride_report.py`, `qbot_report_status.py` | `data/daily_report_sent.json`, `data/weekly_review_sent.json`, `outgoing/reports/*.json` | Report generators and sent-state files | `qbot_operator_final_smoke_test`, `qbot_maintenance_report`, `qbot_operator_snapshot`, `qbot_report_status` | RESTORED | LOW | READ_ONLY | no | no | Keep the report generation and completion-state semantics intact | P2 | yes |
| Outgoing artifacts | `outgoing/`, `scripts/prune_qbot_artifacts.py`, `qbot_artifact_tools.py` | `outgoing/reports/*`, `outgoing/ride_report_previews/*`, `outgoing/qbot_hammerhead_sync_latest_report.json` | Legacy outgoing artifact folders and preview generation | `qbot_artifact_create`, `qbot_artifact_list`, `qbot_artifact_get`, `qbot_workspace_write_file_preview`, `qbot_artifacts_legacy_status` | PARTIAL | MEDIUM | READ_ONLY | yes | yes | Unify outgoing file generation with the artifact bridge and keep prune jobs aligned | P1 | yes |
| Garage inventory | `data/garage.db`, `qbot_garage_mapper.py`, `data_registry/modules.yaml`, `data_registry/routing_rules.yaml`, `email_reply_processor.py`, `governance/data_routing.md` | `data/garage.db` | Legacy garage inventory tables and routing into Garage | `data/garage.db`, `qbot_garage_mapper.py`, `email_reply_processor.py`, Garage routing rules | RESTORED | LOW | READ_ONLY | no | no | Maintain the Garage schema and data-routing rules; no actuation path is implied here | P2 | yes |
| OpenWeatherMap / weather | `qbot_legacy_parity_tools.py`, `mcp_server.py`, `qbot_telegram_tools.py`, `qbot_query_processor.py`, `scripts/qbot_operational_state.py` | `data/daily_external_cache.json`, weather-related cache/state files | Legacy weather handlers and weather status texts | `qbot_weather_status`, `qbot_weather_current`, `qbot_weather_forecast`, `qbot_weather_legacy_status` | PARTIAL | MEDIUM | READ_ONLY | yes | yes | Restore or explicitly replace the OpenWeatherMap-specific path; current weather is Open-Meteo-based | P0 | yes |
| RWGPS / RideWithGPS | `tools/rwgps/client.py`, `tools/rwgps/README_RWGPS.md`, `data/routes/rwgps_manifest.json` | `data/routes/rwgps_route_cache.json`, `outgoing/*route*` artifacts | Legacy RWGPS route export/import helpers | `tools/rwgps/client.py`, route artifact exporters, legacy parity tools | RESTORED | MEDIUM | READ_ONLY | no | no | Keep route export and manifest generation working; expose a dedicated status if desired | P2 | yes |
| OpenMap / OSM / Overpass / maps | `mcp_server.py`, `scripts/qbot_smoke_tests.py`, `qbot_legacy_parity_tools.py` | route surface caches and route analysis artifacts in `data/` and `outgoing/` | Legacy OpenMap / OSM / Overpass analysis tools | `mcp_server.py` openmaps tools, legacy parity scan/status | RESTORED | MEDIUM | READ_ONLY | no | no | Preserve current map-analysis code paths; no public adapter exposure is needed today | P2 | yes |
| Artifacts container / filesystem | `qbot_artifact_tools.py`, `sql/init_qbot.sql`, `qbot_legacy_parity_tools.py`, `mcp_server.py` | `/opt/qbot/artifacts/*`, `outgoing/*`, `sql/llm_planner_v1.sql` | Legacy filesystem artifacts and artifact bridge logic | `qbot_artifact_create`, `qbot_artifact_list`, `qbot_artifact_get`, `qbot_artifacts_legacy_status`, `qbot_artifacts_filesystem_inventory` | PARTIAL | MEDIUM | READ_ONLY | yes | yes | Finish the filesystem↔SQL bridge and keep artifact inventory/export/import consistent | P0 | yes |
| Email / SMTP notifications | `daily_report.py`, `weekly_review.py`, `ride_report.py`, `email_reply_processor.py` | `data/daily_report_sent.json`, `data/weekly_review_sent.json`, `logs/*email*` | Legacy Gmail SMTP report delivery and email reply processor | `send_email` helpers in report scripts, `qbot_maintenance_report`, report generators | RESTORED | MEDIUM | READ_ONLY | no | no | Keep SMTP-based delivery stable; no new mail providers are required | P2 | yes |
| Scheduled jobs / cron / timers | `scripts/run_hammerhead_garmin_sync.sh`, `scripts/run_hammerhead_garmin_sync_profile.sh`, `scripts/prune_qbot_artifacts.py`, `scripts/qbot_backup.sh` | systemd timer files, crontab entries, `logs/hammerhead-garmin-sync*.log` | Cron and timer-backed legacy jobs | `qbot_backup_timer_status`, `qbot_maintenance_report`, existing cron/timer inventory | RESTORED | LOW | READ_ONLY | yes | no | Keep timer and cron inventory documented; ensure old scripts are not mistaken for active service code | P2 | yes |
| Backup / restore | `scripts/qbot_backup.sh`, `docs/qbot_backup_recovery.md`, `qbot_recovery.py`, `systemd/qbot-backup.service.example`, `systemd/qbot-backup.timer.example` | `/opt/qbot/backups/qbot_*.sql.gz`, `data/qbot_operational_state.json` | Backup script, backup service, restore drill docs | `qbot_backup_status`, `qbot_backup_timer_status`, `qbot_restore_drill_status`, `qbot_backup_plan`, `qbot_restore_drill_plan` | RESTORED | LOW | READ_ONLY | yes | no | Keep backup/restore drill current and never restore onto production by mistake | P1 | yes |
| Public endpoints | `qbot_api.py`, `/etc/nginx/sites-available/q365`, `docs/qbot_operational_readiness.md` | nginx vhost config, current public response snapshots | Legacy public `/q`, `/health`, `/mcp/`, `/telegram/webhook/`, and `/ride-readiness` routing | `GET /mcp/`, `GET /mcp/health`, `GET /mcp/tools`, `POST /telegram/webhook/{secret}`, `GET /ride-readiness` | PARTIAL | MEDIUM | READ_ONLY | yes | yes | Keep `/q` and `/health` blocked publicly; the allowed public set is already the intended one | P1 | no |
| Old MCP / SSE | `mcp_server.py`, `qbot_mcp_adapter.py`, `scripts/qbot_operational_state.py`, `systemd/qbot-mcp-bridge.service`, `ngrok-qbot.service` traces | legacy SSE/streamable HTTP logs, old bridge references | Old streamable MCP transport and SSE bridge | `qbot_api.py` `/mcp/` and `qbot_mcp_adapter.py` | DEPRECATED | MEDIUM | READ_ONLY | no | yes | Retire the old SSE bridge path and keep the new adapter as the public connector | P1 | no |
| Qbot status / monitoring | `qbot_tools.py`, `qbot_operator_tools.py`, `qbot_ops_tools.py`, `scripts/qbot_status.py`, `scripts/qbot_operational_state.py`, `qbot_readiness.py`, `qbot_report_status.py` | `data/qbot_operational_state.json`, `logs/*`, recent tool-call history in PostgreSQL | Legacy status/health/monitoring scripts and status reports | `qbot_api_self_check`, `qbot_readiness_report`, `qbot_operator_final_smoke_test`, `qbot_services_status`, `qbot_test_error_classification`, `qbot_legacy_takeover_status`, `qbot_telegram_status`, `qbot_mcp_status`, `qbot_ride_readiness_status` | RESTORED | LOW | READ_ONLY | yes | yes | Keep the monitoring stack cutover-aware and avoid reintroducing legacy service expectations | P2 | yes |

## Additional Safety-Only Legacy Traces

These were found in the repository and in the legacy parity audit, but they are not counted in the 22 capability rows above because they are policy-blocked control surfaces rather than inventory/reporting surfaces.

| legacy trace | evidence files | old handler / service | status | risk | safety class | exposed in Telegram | exposed in MCP | required work |
|---|---|---|---|---|---|---|---|---|
| garage_gate | `qbot_legacy_parity_tools.py`, `qbot_garage_mapper.py`, `data_registry/routing_rules.yaml`, `governance/data_routing.md` | garage / gate / home automation traces, relay / switch / MQTT / Zigbee / Tuya / Shelly references | BLOCKED_BY_POLICY | HIGH | CONTROLLED_ACTION | no | no | Requires a separate safety gate and explicit operator approval before any actuation is even considered |
| home_automation | `qbot_legacy_parity_tools.py`, `data_registry/modules.yaml`, `data_registry/routing_rules.yaml` | Home Assistant / MQTT / Zigbee / Tuya / Shelly traces | BLOCKED_BY_POLICY | HIGH | CONTROLLED_ACTION | no | no | Keep it blocked unless a dedicated safety design is approved |

## Counts

Main audited capabilities: `22`

- RESTORED: `14`
- PARTIAL: `7`
- MISSING: `0`
- DEPRECATED: `1`
- BLOCKED: `0`

Additional safety-only legacy traces detected outside the 22-capability table: `2` (`garage_gate`, `home_automation`)

Operational parity score for the 22 audited capabilities:

```text
(RESTORED + 0.5 * PARTIAL) / 22 = (14 + 3.5) / 22 = 79.5%
```

## P0 Gaps To Fix First

1. OpenWeatherMap-specific weather parity is still missing; current weather is Open-Meteo-based compatibility, not the legacy OWM flow.
2. The filesystem↔SQL artifacts bridge is still partial.
3. Garmin proxy/upload and Hammerhead FIT import remain partial and depend on external auth/state.

## Do Not Run Without Separate Approval

- `qbot-hammerhead-sync`
- `scripts/run_hammerhead_garmin_sync.sh`
- `scripts/run_hammerhead_garmin_sync_profile.sh`
- `qbot-fit-rewrite`
- any Garage / gate / home automation actuation path
- any restore operation against the production `qbot` database
- any script or command that reads or prints `.env.local` values
- the old standalone MCP / SSE bridge service path

## Conclusion

The new Qbot architecture already restores the core control plane, Telegram, MCP, QExt2 readiness, QLab, backup/restore, scheduling, status monitoring, and most route/report flows.

The main remaining parity gaps are the OpenWeatherMap-specific weather path, the unified artifacts bridge, and the Garmin/Hammerhead external sync flows.

Garage inventory itself is present as data and routing, but garage / gate / home automation actuation remains policy-blocked and should be treated separately from the inventory migration.
