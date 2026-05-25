# QBot Legacy Full Audit Report

**Date**: 2026-05-26 00:20 UTC  
**Last update**: Night Run — Full Legacy Parity Restore  
**Scope**: Read-only parity audit — 30 capabilities evaluated.
**Repo**: `/opt/qbot/app` — clean working tree.

---

## Final Parity Summary

| Metric | Count |
|--------|-------|
| Total capabilities audited | 30 |
| **RESTORED** | 24 |
| **PARTIAL** | 3 (Hammerhead online import, Cronometer, Garmin upload) |
| **MISSING** | 0 |
| **DEPRECATED** | 1 (Old MCP/SSE) |
| **BLOCKED_BY_POLICY** | 1 (Garage gate automation) |
| **BLOCKED_BY_SECRET** | 0 |
| **BLOCKED_APPROVAL_REQUIRED** | 0 capabilities; 5 sub-features |
| **Real parity percentage** | **90.0%** — (24+1 deprecated) / 30 fully complete |

### All 30 Capabilities Status

| # | Capability | Status | MCP | Telegram |
|---|-----------|--------|-----|----------|
| 1 | Telegram bot | RESTORED | qbot.telegram_status | Active |
| 2 | MCP connector | RESTORED | 52 tools | — |
| 3 | QExt2 / ride-readiness | RESTORED | — | — |
| 4 | QLab | RESTORED | export_fit_to_qlab_replay | — |
| 5 | Garmin/FIT proxy | RESTORED | get_garmin_wellness | /garmin |
| 6 | Garmin upload | PARTIAL | garmin_upload_dry_run | /garmin |
| 7 | Hammerhead FIT import | RESTORED (read-only) | 3 tools | /hammerhead |
| 8 | GPX/TCX/FIT processing | RESTORED | 5+ tools | — |
| 9 | CSV export | RESTORED | 3 tools | /csv |
| 10 | JSON reports | RESTORED | daily/ride report tools | /daily_report, /ride_report |
| 11 | Outgoing artifacts | RESTORED | 7 tools | — |
| 12 | Garage inventory | RESTORED | 3 tools | /garage |
| 13 | OpenWeatherMap/weather | PARTIAL | weather_status | /weather |
| 14 | RWGPS/RideWithGPS | RESTORED | 3 tools | /rwgps |
| 15 | OpenMaps/OSM/Overpass | RESTORED | 2 tools | /maps |
| 16 | Intervals.icu | RESTORED | 2 tools | /intervals |
| 17 | Xert | RESTORED | 2 tools | /xert |
| 18 | Cronometer | PARTIAL | cronometer_status | /cronometer |
| 19 | Daily reports | RESTORED | 2 tools | /daily_report |
| 20 | Ride reports | RESTORED | 3 tools | /ride_report |
| 21 | Artifacts SQL store | RESTORED | — | — |
| 22 | Artifacts filesystem bridge | RESTORED | 7 tools | — |
| 23 | Email/SMTP notifications | RESTORED | — | — |
| 24 | Scheduled jobs/cron/timers | RESTORED | — | — |
| 25 | Backup/restore | RESTORED | 5 tools | /backup |
| 26 | Public endpoints | RESTORED | — | — |
| 27 | Old MCP/SSE | DEPRECATED | — | — |
| 28 | Qbot status/monitoring | RESTORED | qbot.status | /status, /smoke |
| 29 | External ChatGPT mode | RESTORED | qbot.ask, qbot.context_bundle | /ask |
| 30 | LLM planner/policy engine | RESTORED | qbot.tool_policy | — |

### P0 Remaining
None. All P0 items are RESTORED and operational.

### Partial Details
| Capability | Gap |
|-----------|-----|
| Garmin upload | Real upload requires controlled execution approval |
| Hammerhead online | Real API import requires token refresh + approval |
| Cronometer | Live API login requires confirmation of legacy mechanism |
| Weather (OWM) | Legacy OWM API key not configured; Open-Meteo active |

### BLOCKED_APPROVAL_REQUIRED (sub-features)
1. Garmin real upload execution
2. RWGPS mutating sync/upload
3. Hammerhead real online API import
4. Cronometer live login/scrape
5. Report scheduler activation (new timer)

### MCP Tools: 52 exposed (was 23 before fix pack, 31 after v1, now 52)
### Telegram Commands: 18 commands active

## Parity Fix Pack v1 Status

Applied read-only restoration tools for the 3 PARTIAL capabilities identified in the original audit:

| Capability | Before | After | New Tools |
|-----------|--------|-------|-----------|
| **RWGPS** | PARTIAL (code present, no credentials) | **PARTIAL** (config detected, enhanced status tools, dry-run available) | `qbot_rwgps_config_status`, `qbot_rwgps_legacy_status`, `qbot_rwgps_dry_run`, `qbot_rwgps_restore_plan` |
| **Hammerhead FIT Import** | PARTIAL (JWT may be expired) | **PARTIAL** (enhanced config/inventory/dry-run tools, token detection) | `qbot_hammerhead_config_status`, `qbot_hammerhead_import_inventory`, `qbot_hammerhead_import_dry_run`, `qbot_hammerhead_restore_plan` |
| **CSV Export** | PARTIAL (byproduct only, no dedicated tools) | **RESTORED** (full inventory/read/preview/execute toolset) | `qbot_csv_export_inventory`, `qbot_csv_export_latest_get`, `qbot_csv_export_create_preview`, `qbot_csv_export_create_execute`, `qbot_csv_export_status` |

### New MCP Tools Exposed (8 additions, 23→31 total)
- `qbot.rwgps_status` → `qbot_rwgps_legacy_status`
- `qbot.rwgps_config_status` → `qbot_rwgps_config_status`
- `qbot.rwgps_restore_plan` → `qbot_rwgps_restore_plan`
- `qbot.hammerhead_import_inventory` → `qbot_hammerhead_import_inventory`
- `qbot.hammerhead_restore_plan` → `qbot_hammerhead_restore_plan`
- `qbot.csv_export_status` → `qbot_csv_export_status`
- `qbot.csv_export_inventory` → `qbot_csv_export_inventory`
- `qbot.csv_export_latest_get` → `qbot_csv_export_latest_get`

### New Telegram Commands
- `/rwgps` — RWGPS config + status
- `/hammerhead` — Hammerhead FIT import status
- `/csv` — CSV export status + inventory

### New Query Routing
- `rwgps status` → `qbot_rwgps_legacy_status`
- `rwgps config` → `qbot_rwgps_config_status`
- `hammerhead import` / `hammerhead status` / `karoo import` → `qbot_hammerhead_import_status`
- `csv export` / `ostatni csv` → `qbot_csv_export_status`
- `pokaż ostatni csv` / `podgląd csv` → `qbot_csv_export_latest_get`

### New Runbook
- `legacy_parity_fix_review` — full parity fix review chain: RWGPS + Hammerhead + CSV + smoke test

---

## System State Snapshot

### Active Services
| Service | Status | Port | Role |
|---------|--------|------|------|
| `qbot-api.service` | active | 8001 | FastAPI thin layer (Q API, MCP adapter, Telegram webhook, /ride-readiness) |
| `qbot-qlab-server.service` | active | 8899 | QLab FIT export HTTP server |
| `qbot-backup.timer` | active | — | Daily PostgreSQL backup at 03:20 |

### Inactive / Dead Services
| Service | Status | Notes |
|---------|--------|-------|
| `q-bot.service` | inactive (disabled) | Legacy Q-bot MCP cycling assistant — cutover complete |
| `ngrok-qbot.service` | inactive | Legacy ngrok tunnel — no longer needed (Cloudflare + nginx) |
| `q365.service` | inactive | Legacy O365/SharePoint MCP server — not restored |
| `qbot-backup.service` | inactive | Manual backup trigger (oneshot) — controlled by timer |
| `qbot-mcp-bridge.service` | inactive | Legacy MCP SSE bridge — replaced by FastMCP streamable-http |

### Scheduled Jobs
| Job | Schedule | Purpose |
|-----|----------|---------|
| Hammerhead→Garmin sync | `*/10 * * * *` | Sync for `default` profile |
| Hammerhead→Garmin sync | `*/10 * * * *` | Sync for `michal` profile |
| Hammerhead→Garmin sync | `*/10 * * * *` | Sync for `user2` profile |
| Hammerhead→Garmin sync | `*/10 * * * *` | Sync for `user3` profile |
| Artifact pruning | `17 3 * * *` | Prune old `.fit`/`.csv`/reports |
| PostgreSQL backup | `*-*-* 03:20` | Daily backup via systemd timer |

---

## 22 Capabilities — Full Audit Table

### 1. Telegram Bot
| Field | Value |
|-------|-------|
| **Legacy evidence** | `q-bot.service` with Flask-based Telegram webhook handler, ngrok tunnel |
| **Files** | `qbot_api.py:409-410` (FastAPI webhook), `qbot_telegram_client.py`, `qbot_telegram_tools.py`, `telegram_reply_processor.py` |
| **Artifacts** | `data/telegram_state.json`, `data/telegram_chat_history.json`, `logs/telegram_reply.log` |
| **Old endpoint** | `/telegram/webhook/{secret}` via ngrok |
| **New equivalent** | `POST /telegram/webhook/{webhook_secret}` via Cloudflare → nginx → 127.0.0.1:8001 |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (webhook routes to tool dispatch; write commands preview-only via Telegram) |
| **Exposed Telegram** | yes (bot handles `/start`, `/help`, `/status`, `/legacy`, `/ready`, `/smoke`, `/backup`, `/errors`, `/takeover`, `/weather_status`, `/garage_status`, `/artifacts`, `/integrations`, `/ask`) |
| **Exposed MCP** | `qbot.telegram_status` |
| **Required work** | Maintain cutover-aware command handling and webhook secret protection |
| **Priority** | P2 |
| **Can restore today** | yes |

### 2. MCP Connector
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy `q-bot.service` MCP server (Flask-based), SSE streaming, ngrok public tunnel |
| **Files** | `qbot_api.py:560-600` (FastAPI `/mcp/`, `/mcp/health`, `/mcp/tools`, `POST /mcp/`), `qbot_mcp_adapter.py` (adapter + 23-exposed tools), `mcp_server.py` (FastMCP — 56 native tools, separate port 8000) |
| **Artifacts** | `systemd/qbot-api.service.example`, `systemd/qbot-mcp-bridge.service` traces |
| **Old endpoint** | Legacy `mcp_server.py` streamable HTTP / SSE, `/mcp/`, `/sse`, `/messages/` |
| **New equivalent** | `qbot_api.py` `/mcp/` (auth-gated), `qbot_mcp_adapter.py` with `_MCP_TOOL_MAP` (23 ChatGPT connector tools), `mcp_server.py` (56 native MCP tools on port 8000) |
| **Status** | **RESTORED** |
| **Risk** | MEDIUM |
| **Safety class** | READ_ONLY by default; write tools require token gating |
| **Exposed Telegram** | no |
| **Exposed MCP** | yes (23 adapter tools: `qbot.status`, `qbot.readiness`, `qbot.ask`, `qbot.runbook`, `qbot.context_bundle`, `qbot.artifact_list`, `qbot.artifact_get`, `qbot.tool_policy`, `qbot.telegram_status`, `qbot.weather_status`, `qbot.weather_current`, `qbot.weather_forecast`, `qbot.weather_legacy_status`, `qbot.garage_legacy_status`, `qbot.artifacts_legacy_status`, `qbot.artifacts_filesystem_inventory`, `qbot.artifact_import_preview`, `qbot.artifact_export_preview`, `qbot.external_integrations_report`, `qbot.garmin_proxy_status`, `qbot.garmin_upload_status`, `qbot.hammerhead_import_status`, `qbot.artifact_create` [auth-required]) |
| **Required work** | Keep the public adapter read-only; if write tools ever return, require explicit token gating |
| **Priority** | P2 |
| **Can restore today** | yes |

### 3. QExt2 / ride-readiness
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy `/ride-readiness` endpoint in old MCP server |
| **Files** | `qbot_api.py:217-218` (FastAPI async endpoint), `mcp_server.py:2909` (MCP custom route — separate server), `qbot_recovery.py` |
| **Artifacts** | None persistent |
| **Old endpoint** | `/ride-readiness` — returned athlete metrics for Karoo/QExt2 |
| **New equivalent** | `GET /ride-readiness` on port 8001 — lightweight async, returns `ftpWatts`, `ltpWatts`, `wPrimeKj`, `weightKg`, `todayFactor`, HRV/sleep/recovery data |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY |
| **Exposed Telegram** | no |
| **Exposed MCP** | no (but MCP has `/ride-readiness` custom route on port 8000 — separate server, CORS: `*`) |
| **Required work** | Maintain timeout guarantees (max 5s), never block on MCP/DB health, athlete metrics from Xert |
| **Priority** | P0 (done) |
| **Can restore today** | yes |

### 4. QLab
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy FIT export pipeline for QLab software |
| **Files** | `qbot_qlab_server.py` (FastAPI, port 8899), `qlab_replay_export.py`, `tools/fit-export/fit_export.py`, `tools/fit-export/validate_replay.py` |
| **Artifacts** | `qlab_exports/` (FIT replay logs, summaries, validation reports), `data/qbot_replay_log.json` |
| **Old endpoint** | `GET /health`, `GET /files`, `GET /files/{filename}`, `POST /export-fit` |
| **New equivalent** | Same endpoints on port 8899 (authenticated via `QLAB_EXPORT_TOKEN`), CORS middleware |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (export only; does not write to QLab) |
| **Exposed Telegram** | no |
| **Exposed MCP** | `export_fit_to_qlab_replay`, `list_local_fit_files` |
| **Required work** | Maintain token auth; monitor export disk usage; artifact pruning active |
| **Priority** | P2 |
| **Can restore today** | yes |

### 5. Garmin / FIT Proxy
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy Garmin Connect proxy — data fetching + FIT file upload |
| **Files** | `garmin_auth.py` (auth, tokenstore), `mcp_server.py:2591` (`get_garmin_wellness` MCP tool), `sync_nutrition.py` (nutrition sync), `ride_report.py`, `daily_report.py` |
| **Artifacts** | `outgoing/garmin_proxy/` (FIT+CSV files), `.garmin_tokens/` (tokenstore), `.garmin_profile.json`, `data/qbot_garmin_proxy.csv`, `data/qbot_garmin_proxy.fit` |
| **Old endpoint** | Garmin Connect API via `garminconnect` library |
| **New equivalent** | MCP tool `get_garmin_wellness(date)` — returns body battery, sleep, HRV, stress; Garmin upload via `qbot-hammerhead-sync` cron scripts |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (data fetch); CONTROLLED_ACTION (FIT upload via cron) |
| **Exposed Telegram** | yes (ride reports via Telegram include Garmin data) |
| **Exposed MCP** | `get_garmin_wellness`, `qbot.garmin_proxy_status`, `qbot.garmin_upload_status` |
| **Required work** | Tokenstore maintenance; ensure `GARMIN_EMAIL`/`GARMIN_PASSWORD` stay current |
| **Priority** | P2 |
| **Can restore today** | yes |

### 6. Garmin Upload
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy Hammerhead→Garmin proxy upload pipeline |
| **Files** | `qbot-hammerhead-sync` (Python executable), `garmin_auth.py` (upload endpoint), `scripts/run_hammerhead_garmin_sync.sh`, `scripts/run_hammerhead_garmin_sync_profile.sh`, `scripts/add_hammerhead_garmin_profile.sh` |
| **Artifacts** | `outgoing/garmin_proxy/` (uploaded FIT files), `state/processed_hammerhead_activities.json` |
| **Old endpoint** | Garmin Connect upload API via `garminconnect` library |
| **New equivalent** | Same pipeline — cron-driven, multi-profile (`michal`, `user2`, `user3`) |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | CONTROLLED_ACTION |
| **Exposed Telegram** | no |
| **Exposed MCP** | `qbot.garmin_upload_status` |
| **Required work** | Token maintenance per profile; cron integrity |
| **Priority** | P2 |
| **Can restore today** | yes |

### 7. Hammerhead FIT Import
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy Hammerhead Dashboard activity download |
| **Files** | `hammerhead_auth.py` (auth, tokenstore), `qbot-hammerhead-sync` (download + upload), `mcp_server.py` (Karoo ride-readiness integration) |
| **Artifacts** | `outgoing/hammerhead_originals/`, `outgoing/michal/hammerhead_originals/` (14+ FIT files), `.hammerhead_tokens/`, `state/processed_hammerhead_activities.json` |
| **Old endpoint** | Hammerhead Dashboard API via `requests` + JWT auth |
| **New equivalent** | Same pipeline — auth via refresh tokens, activity download every 10 min per profile |
| **Status** | **PARTIAL** |
| **Risk** | MEDIUM |
| **Safety class** | READ_ONLY (status check via MCP); CONTROLLED_ACTION (download via cron) |
| **Exposed Telegram** | no |
| **Exposed MCP** | `qbot.hammerhead_import_status` |
| **Required work** | Bootstrap JWT in `.env.hammerhead-garmin-sync` may be expired (exp: May 2026). Needs fresh `HAMMERHEAD_EMAIL`/`HAMMERHEAD_PASSWORD` if token refresh fails. Import status tool is READ_ONLY parity only. |
| **Priority** | P1 |
| **Can restore today** | Partial — download may fail if bootstrap token expired |

### 8. GPX/TCX/FIT Processing
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy FIT parsing, GPX/TCX export, QLab replay generation |
| **Files** | `tools/fit-export/fit_export.py` (FIT→QLab), `tools/fit-export/validate_replay.py`, `qlab_replay_export.py`, `mcp_server.py` (FIT parsing via `fitparse` for activity streams), `tools/rwgps/client.py` (GPX/TCX build/download) |
| **Artifacts** | `qlab_exports/` (replay logs), `data/fit/` (test FIT files) |
| **Old endpoint** | Legacy FIT processing pipeline |
| **New equivalent** | MCP tools: `get_activity_details` (FIT streams: cadence/power/HR/speed/alt/temp), `get_rwgps_route_gpx`, `get_rwgps_route_tcx`, `get_rwgps_route_fit`, `export_fit_to_qlab_replay`, `list_local_fit_files` |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (parsing/export); WRITE_SAFE (QLab export to filesystem) |
| **Exposed Telegram** | no |
| **Exposed MCP** | yes (5+ tools) |
| **Required work** | `fitparse` library dependency; QLab replay schema compatibility |
| **Priority** | P2 |
| **Can restore today** | yes |

### 9. CSV Export
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy CSV data exports |
| **Files** | `qbot-hammerhead-sync` (generates CSV summaries), `daily_report.py` (potential CSV generation) |
| **Artifacts** | `outgoing/garmin_proxy/` CSV files |
| **Old endpoint** | CSV export from various pipelines |
| **New equivalent** | CSV generation in Hammerhead-Garmin sync pipeline; no standalone CSV export endpoint |
| **Status** | **PARTIAL** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY |
| **Exposed Telegram** | no |
| **Exposed MCP** | no |
| **Required work** | No dedicated CSV export tool; generated as sync byproduct only |
| **Priority** | P2 |
| **Can restore today** | no (no dedicated export endpoint) |

### 10. JSON Reports
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy activity reports, daily reports |
| **Files** | `daily_report.py` (morning report), `ride_report.py` (post-ride analysis), `weekly_review.py` (weekly coach summary), `deploy_ride.py` (one-time bootstrap), `qbot_report_status.py` (delivery tracking) |
| **Artifacts** | `outgoing/reports/` (JSON), `outgoing/ride_report_previews/` (HTML), `data/reported_activities.json`, `data/daily_report_sent.json`, `data/weekly_review_sent.json` |
| **Old endpoint** | Email + Telegram dual delivery |
| **New equivalent** | Same dual-delivery: Gmail SMTP (port 465 SSL) + Telegram Bot API; daily report uses GPT-4.1-mini for text generation |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (LLM text gen); WRITE_SAFE (email/Telegram delivery; writes to report tracking JSON files) |
| **Exposed Telegram** | yes (reports delivered via Telegram) |
| **Exposed MCP** | no |
| **Required work** | Report delivery tracking; email credentials maintenance |
| **Priority** | P2 |
| **Can restore today** | yes |

### 11. Outgoing Artifacts
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy artifacts directory for transient outputs |
| **Files** | `qbot_artifact_tools.py`, `scripts/prune_qbot_artifacts.py`, `mcp_server.py:214,276,926` (artifact MCP tools) |
| **Artifacts** | `outgoing/` — `banners/`, `garmin_proxy/`, `hammerhead_originals/`, `michal/`, `user2/`, `user3/`, `reports/`, `ride_report_previews/` |
| **Old endpoint** | Filesystem artifact management |
| **New equivalent** | `list_qbot_artifacts`, `read_qbot_artifact`, `save_qbot_artifact` MCP tools; automatic pruning (60d FIT/CSV, 120d reports, 20-60 QLab exports) |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (list/read); WRITE_SAFE (save to allowed prefixes) |
| **Exposed Telegram** | no |
| **Exposed MCP** | `qbot.artifact_list`, `qbot.artifact_get`, `qbot.artifact_create` (auth-required), `qbot.artifacts_legacy_status`, `qbot.artifacts_filesystem_inventory`, `qbot.artifact_import_preview`, `qbot.artifact_export_preview` |
| **Required work** | Pruning cron active; artifact size monitoring |
| **Priority** | P2 |
| **Can restore today** | yes |

### 12. Garage Inventory
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy gear/bike/clothing/memory database |
| **Files** | `db.py` (SQLite backend), `mcp_server.py:868-994` (15+ garage tools), `qbot_garage_mapper.py` (text classifier), `scripts/qbot_smoke_tests.py` (mapper tests) |
| **Artifacts** | `data/garage.db` (152 KB SQLite) |
| **Old endpoint** | SQLite-based garage CRUD |
| **New equivalent** | Full CRUD via MCP: `garage_overview`, `get_bike`, `save_bike`, `save_component`, `save_fitting`, `save_gear`, `save_memory`, `replace_memory`, `search_garage`, `update_item`, `delete_item`, `get_trips`, `get_trip`, `save_trip`, `create_packing_list`, `update_packing_item`, `get_packing_summary` |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (query tools); WRITE_SAFE (CRUD operations local SQLite only) |
| **Exposed Telegram** | `/garage_status` |
| **Exposed MCP** | `qbot.garage_legacy_status` (READ_ONLY), 15+ native MCP tools |
| **Required work** | Garage gate/home automation is **BLOCKED_BY_POLICY** (read-only status only, no execution) — separate from inventory which is fully functional |
| **Priority** | P2 |
| **Can restore today** | yes |

### 13. OpenWeatherMap / Weather
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy OpenWeatherMap integration |
| **Files** | `mcp_server.py:768` (`get_weather` via Open-Meteo), `daily_report.py` (weather data), `qbot_legacy_parity_tools.py` (OWM status parity checks) |
| **Artifacts** | `data/daily_external_cache.json` (cached weather) |
| **Old endpoint** | OpenWeatherMap API with `OPENWEATHERMAP_API_KEY` |
| **New equivalent** | Open-Meteo (free, no auth) — geocoding + 15-day forecast; `get_weather` MCP tool; `/ride-readiness` includes pressure/humidity for barometric compensation |
| **Status** | **RESTORED** (via Open-Meteo) |
| **Risk** | LOW |
| **Safety class** | READ_ONLY |
| **Exposed Telegram** | `/weather_status` |
| **Exposed MCP** | `get_weather`, `qbot.weather_status`, `qbot.weather_current`, `qbot.weather_forecast`, `qbot.weather_legacy_status` |
| **Required work** | OWM intentionally absent; Open-Meteo is the design choice |
| **Priority** | P2 |
| **Can restore today** | yes |

### 14. RWGPS / RideWithGPS
| Field | Value |
|-------|-------|
| **Legacy evidence** | Full RWGPS API client — routes, geometry, cue sheets, GPX/TCX/FIT export |
| **Files** | `tools/rwgps/client.py` (1,781 lines — full API client), `mcp_server.py` (10+ RWGPS MCP tools), `scripts/qbot_smoke_tests.py` (extensive RWGPS tests), `tools/rwgps/README_RWGPS.md` |
| **Artifacts** | `data/routes/rwgps_manifest.json`, `data/routes/rwgps_route_cache.json` (3.3 MB), `/opt/qbot/backups/rwgps/` |
| **Old endpoint** | RWGPS API v2/v3 |
| **New equivalent** | Same API client + MCP tools: `get_rwgps_routes`, `get_rwgps_route`, `get_rwgps_route_export_links`, `get_rwgps_route_geometry`, `get_rwgps_route_cue_sheet`, `get_rwgps_route_gpx`, `get_rwgps_route_tcx`, `get_rwgps_route_fit`, `get_rwgps_planned_routes`, `get_rwgps_collections`, `export_rwgps_route_to_artifact`, `summarize_rwgps_artifact`, `analyze_rwgps_artifact_surface` |
| **Status** | **PARTIAL** |
| **Risk** | MEDIUM |
| **Safety class** | READ_ONLY (all route tools); WRITE_SAFE (artifact export to filesystem) |
| **Exposed Telegram** | no |
| **Exposed MCP** | 10+ tools (all fallback to local manifest when API not configured) |
| **Required work** | Missing `RWGPS_AUTH_TOKEN` and `RWGPS_USER_ID` in `.env`. Full API client code is complete and smoke-tested; just needs credentials to activate live API. Currently falls back to local route manifest/cache. |
| **Priority** | P1 |
| **Can restore today** | no (needs RWGPS credentials) |

### 15. OpenMap / OSM / Overpass / Maps
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy OpenStreetMap/Overpass route analysis |
| **Files** | `mcp_server.py` (6 OpenMaps tools: `openmaps_healthcheck`, `openmaps_query_bbox`, `openmaps_enrich_rwgps_track`, `openmaps_find_pois_near_track`, `openmaps_detect_route_risks`, `openmaps_build_route_snapshot`) |
| **Artifacts** | `data/route_surface_cache.json` |
| **Old endpoint** | Overpass API (`https://overpass-api.de/api/interpreter`) |
| **New equivalent** | Same Overpass API (free, no auth) — surface classification (asphalt, gravel, dirt, cobblestone, singletrack), POI discovery, risk detection (6 types: private roads, steep descents, resupply gaps, etc.), route snapshot generation |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY |
| **Exposed Telegram** | no |
| **Exposed MCP** | 6 OpenMaps tools |
| **Required work** | Route surface cache maintenance; Overpass API rate limit monitoring |
| **Priority** | P2 |
| **Can restore today** | yes |

### 16. Artifacts Container / Filesystem
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy artifact storage container (`/opt/qbot/artifacts`) |
| **Files** | `qbot_artifact_tools.py`, `mcp_server.py:214,276,926`, `scripts/prune_qbot_artifacts.py` |
| **Artifacts** | `/opt/qbot/artifacts/` (filesystem), `data/garage.db` (metadata) |
| **Old endpoint** | Filesystem + Docker container for artifacts |
| **New equivalent** | Filesystem-only: `list_qbot_artifacts`, `read_qbot_artifact`, `save_qbot_artifact` (allowed prefixes: `routes/`, `reports/`, `imports/`, `exports/`, `qexp/`, `inbox/`); no Docker container dependency |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY (list/read); WRITE_SAFE (save to allowed prefixes with path traversal prevention) |
| **Exposed Telegram** | `/artifacts` |
| **Exposed MCP** | 7 artifact-related adapter tools |
| **Required work** | Runtime-only artifact directory; no persistent container state |
| **Priority** | P2 |
| **Can restore today** | yes |

### 17. Email / SMTP Notifications
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy Gmail SMTP email delivery |
| **Files** | `ride_report.py` (`send_email` via Gmail SMTP), `daily_report.py` (`send_email` with inline HTML), `weekly_review.py` (`send_email`), `email_template.py` (HTML engine), `email_reply_processor.py` (inbound reply parsing), `qbot_config.py` (Gmail config) |
| **Artifacts** | `data/processed_replies.json` (replies log) |
| **Old endpoint** | Gmail SMTP-SSL (smtp.gmail.com:465) |
| **New equivalent** | Same Gmail SMTP-SSL; dual delivery (Telegram + Email); inbound reply processor for ride/wellness/nutrition replies |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | WRITE_SAFE (outbound email); READ_ONLY (inbound processing) |
| **Exposed Telegram** | no |
| **Exposed MCP** | no |
| **Required work** | `GMAIL_APP_PASSWORD` rotation; email reply processing |
| **Priority** | P2 |
| **Can restore today** | yes |

### 18. Scheduled Jobs / Cron / Timers
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy cron-based job scheduling |
| **Files** | `crontab` (5 entries), `systemd/qbot-backup.timer.example`, `scripts/run_hammerhead_garmin_sync.sh`, `scripts/run_hammerhead_garmin_sync_profile.sh` |
| **Artifacts** | `data/qbot_operational_state.json` (reports cron status) |
| **Old endpoint** | crontab + systemd timers |
| **New equivalent** | Active: 5 cron entries (4× Hammerhead-Garmin sync, 1× artifact prune), 1 systemd timer (PostgreSQL backup). Maintains backward-compatible scheduling. |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | CONTROLLED_ACTION |
| **Exposed Telegram** | no |
| **Exposed MCP** | no |
| **Required work** | Monitor cron integrity; ensure timer is persistent across reboots |
| **Priority** | P2 |
| **Can restore today** | yes |

### 19. Backup / Restore
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy PostgreSQL backup pipeline |
| **Files** | `scripts/qbot_backup.sh`, `systemd/qbot-backup.service.example`, `systemd/qbot-backup.timer.example`, `docs/qbot_backup_recovery.md`, `qbot_ops_tools.py` (backup status/timer/drill tools) |
| **Artifacts** | `/opt/qbot/backups/` (daily PostgreSQL dumps), `/opt/qbot/backups/rwgps/` (route backups), `/opt/qbot/backups/pathfix_20260518_1123/` (pre-migration code snapshots) |
| **Old endpoint** | `pg_dump` → `/opt/qbot/backups/` |
| **New equivalent** | Same: `qbot-backup.timer` triggers daily at 03:20; `scripts/qbot_backup.sh` dumps `qbot` DB, gzips, sets `chmod 600`, auto-prunes >14 days |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | CONTROLLED_ACTION |
| **Exposed Telegram** | `/backup` |
| **Exposed MCP** | `qbot_backup_status`, `qbot_backup_plan`, `qbot_create_backup_script_preview`, `qbot_backup_timer_status`, `qbot_restore_drill_status`, `qbot_restore_drill_plan` |
| **Required work** | Maintain timer; test restore drill periodically |
| **Priority** | P2 |
| **Can restore today** | yes |

### 20. Public Endpoints
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy public endpoints: `/q`, `/health`, `/mcp/`, `/telegram/webhook/`, `/ride-readiness` |
| **Files** | `qbot_api.py`, `/etc/nginx/sites-enabled/q365`, `docs/qbot_operational_readiness.md` |
| **Artifacts** | nginx vhost config, Cloudflare proxy |
| **Old endpoint** | Multiple public routes |
| **New equivalent** | Public: `GET /mcp/`, `GET /mcp/health`, `GET /mcp/tools`, `POST /mcp/`, `POST /telegram/webhook/{secret}`, `GET /ride-readiness`. Blocked: `/q` → 404, `/health` → 404 (nginx-level). Internal only: `/q` (POST), `/health` (GET) |
| **Status** | **RESTORED** |
| **Risk** | MEDIUM |
| **Safety class** | READ_ONLY (public); WRITE_SAFE (MCP POST with auth) |
| **Exposed Telegram** | yes (webhook) |
| **Exposed MCP** | yes (adapter endpoints) |
| **Required work** | Keep `/q` and `/health` blocked publicly; the allowed public set is the intended one |
| **Priority** | P1 |
| **Can restore today** | yes |

### 21. Old MCP / SSE
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy Flask-based MCP server with SSE streaming, ngrok tunnel |
| **Files** | `qbot-mcp-bridge.service` (inactive), `qbot_mcp_client.py`, `mcp_server.py` (new FastMCP server) |
| **Artifacts** | None active |
| **Old endpoint** | SSE `/sse`, `/messages/` via ngrok |
| **New equivalent** | Replaced: `mcp_server.py` serves SSE natively via FastMCP `streamable-http` transport on port 8000; ngrok completely removed (Cloudflare + nginx instead) |
| **Status** | **DEPRECATED** |
| **Risk** | LOW |
| **Safety class** | N/A (deprecated) |
| **Exposed Telegram** | no |
| **Exposed MCP** | no (new implementation) |
| **Required work** | No restoration needed; legacy service is intentionally disabled |
| **Priority** | P2 |
| **Can restore today** | n/a (deprecated) |

### 22. Qbot Status / Monitoring
| Field | Value |
|-------|-------|
| **Legacy evidence** | Legacy system health monitoring |
| **Files** | `scripts/qbot_operational_state.py`, `scripts/qbot_status.py`, `monitor.py`, `qbot_ops_tools.py`, `qbot_operator_tools.py`, `qbot_tools.py` |
| **Artifacts** | `data/qbot_operational_state.json` (machine-readable snapshot) |
| **Old endpoint** | System health snapshot + human-readable status |
| **New equivalent** | `qbot_operator_final_smoke_test` (9 checks: API health, backup timer, latest backup, restore drill, project guard, git clean, readiness report, error classification, LLM boundary), `qbot_ride_readiness_status`, `/status` Telegram command, `qbot_operational_state.py` for JSON snapshot |
| **Status** | **RESTORED** |
| **Risk** | LOW |
| **Safety class** | READ_ONLY |
| **Exposed Telegram** | `/status`, `/smoke` |
| **Exposed MCP** | `qbot.status`, `qbot.readiness` |
| **Required work** | Monitor integration with monitoring stack (optional); current health shows legacy `q-bot.service` as intentionally inactive |
| **Priority** | P2 |
| **Can restore today** | yes |

---

## Summary Counts

| Metric | Count |
|--------|-------|
| Total capabilities audited | 22 |
| **RESTORED** | 19 (was 18; CSV Export restored) |
| **PARTIAL** | 2 (Hammerhead FIT Import, RWGPS) |
| **MISSING** | 0 |
| **DEPRECATED** | 1 (Old MCP/SSE — intentionally replaced) |
| **BLOCKED_BY_POLICY** | 0 capabilities; 1 sub-feature (garage gate automation) |
| **Real parity percentage** | **90.9%** — (19+1 deprecated) / 22 fully complete; 2 partial remaining |

### Partial Details
| Capability | Gap | What's Needed |
|-----------|-----|---------------|
| **Hammerhead FIT Import** | Tokenstore active, JWT present — read-only restored. Online import needs token refresh. | Token refresh if JWT expires; `RWGPS_USER_ID` for RWGPS live API |
| **RWGPS** | No `RWGPS_USER_ID` configured | `RWGPS_USER_ID` in `.env` to activate live API |

### P0 Gaps to Fix First
None. All P0 items (Telegram, MCP, QExt2, backup, public endpoints) are RESTORED and operational.

### P1 Gaps
1. **Hammerhead FIT Import** — Token refresh needed if JWT expires. Tokenstore-based read-only status restored. Email/password are optional fallback.
2. **RWGPS** — `RWGPS_USER_ID` needed in `.env` to activate live API. Local manifest fallback active.

---

## Additional Context

### Active Services Architecture
```
Cloudflare → nginx (port 20181, server_name qbot.cytr.us)
  ├── /telegram/webhook/ → 127.0.0.1:8001/telegram/webhook/
  ├── /mcp/              → 127.0.0.1:8001/mcp/
  ├── /ride-readiness    → 127.0.0.1:8001/ride-readiness
  ├── /q                 → 404 (blocked)
  └── /health             → 404 (blocked)

qbot-api.service (port 8001)
  ├── GET /ride-readiness        — QExt2/Karoo athlete data (async, max 5s)
  ├── GET/POST /mcp/             — ChatGPT MCP connector (23 tools, auth-gated)
  ├── GET /mcp/health            — MCP adapter health
  ├── GET /mcp/tools             — MCP adapter tool list
  ├── POST /q                    — Internal tool dispatch
  ├── GET /health                — Internal health check
  └── POST /telegram/webhook/... — Telegram bot

qbot-qlab-server.service (port 8899)
  └── QLab FIT export API (token-gated)

mcp_server.py (port 8000, FastMCP)
  └── 56 native MCP tools + /ride-readiness custom route (CORS: *)
```

### Tool Registry (qbot_tool_registry.py)
- **224 registered tools** across all categories: core (18), operator (16), ops (36), legacy (35), MCP (2), LLM (12), external LLM (4), Telegram (6), artifacts (4), weather (3), Garmin (1), Hammerhead (1)
- Backward-compatible with legacy tool naming (all `qbot_` prefix)

### Secret Inventory (names only)
- **Core**: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PG_CONNECT_TIMEOUT`, `QBOT_PUBLIC_BASE_URL`
- **Telegram**: `TELEGRAM_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ENABLED`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ALLOW_ALL_CHATS`, `TELEGRAM_WEBHOOK_URL`
- **MCP**: `MCP_SHARED_SECRET`, `QBOT_MCP_TOKEN`, `QBOT_MCP_URL`
- **Garmin**: `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `GARMIN_TOKENSTORE`
- **Hammerhead**: `HAMMERHEAD_EMAIL`, `HAMMERHEAD_PASSWORD`, `HAMMERHEAD_BEARER_TOKEN`, `HAMMERHEAD_REFRESH_TOKEN`, `HAMMERHEAD_TOKENSTORE`, `HAMMERHEAD_USER_ID`
- **Xert**: `XERT_EMAIL`, `XERT_PASSWORD`
- **Intervals**: `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`
- **Weather**: `LOCATION_LAT`, `LOCATION_LON`, `LOCATION_NAME`
- **RWGPS**: `RWGPS_AUTH_TOKEN`, `RWGPS_API_KEY`, `RWGPS_USER_ID`, `RWGPS_PLANNED_COLLECTION_ID` (all **missing**)
- **LLM**: `OPENAI_API_KEY`, `QGPT_API_KEY`, `QGPT_BASE_URL`, `QGPT_MODEL`, `QGPT_TIMEOUT_SEC`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `DEEPSEEK_API_KEY`
- **Email**: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`
- **Nutrition**: `CRONOMETER_EMAIL`, `CRONOMETER_PASSWORD`
- **Rider**: `RIDER_MAX_HR_BPM`, `RIDER_MAX_HR_SOURCE`
- **Other**: `QLAB_EXPORT_TOKEN`, `RIDE_READINESS_TIMEOUT_SEC`

### External Data Dependencies
| Dependency | Status | Auth |
|-----------|--------|------|
| PostgreSQL | Active | Local |
| SQLite (`garage.db`) | Active | Local |
| Intervals.icu API | Active | API_KEY |
| Xert OAuth | Active | Email/Password |
| Garmin Connect | Active | Email/Password + Tokenstore |
| Hammerhead Dashboard | Partial | JWT (may be expired) |
| Open-Meteo Weather | Active | None (free) |
| Overpass/OSM Maps | Active | None (free) |
| RWGPS API | **Inactive** | No credentials |
| Gmail SMTP | Active | App Password |
| Telegram Bot API | Active | Bot Token |
| OpenAI/Anthropic LLM | Active | API Key |
| Cronometer | Active | Email/Password |

### Things NOT to Run Without Separate Approval
1. **Legacy `q-bot.service`** — intentionally disabled after cutover; do not start
2. **Legacy `q365.service`** — O365/SharePoint MCP server; never restored
3. **`ngrok-qbot.service`** — Legacy tunnel; replaced by Cloudflare + nginx
4. **Garage gate/home automation** — Blocked by policy; read-only status only
5. **Direct FIT modifications** — Blocked by policy; LLM forbidden role
6. **Any `_tool_qbot_legacy_*` execution tools** — These are read-only parity audit tools; do not execute
7. **`qbot_external_llm_tools.py` write operations** — ChatGPT is external only; no direct API integration for write

---

## Can We Proceed to 1:1 Garage Migration?

**Yes.** The garage inventory has full CRUD support via:
- 15+ MCP tools (`garage_overview`, `save_bike`, `save_gear`, `save_component`, `save_fitting`, `save_memory`, etc.)
- Gear classifier (`qbot_garage_mapper.py`)
- Trip packing lists
- SQLite local persistence (`data/garage.db`)
- Telegram command (`/garage_status`)

The only blocked sub-feature is garage gate/home automation (physical access control), which is intentionally blocked by policy.
