# QBot Integration Auth Audit

**Date**: 2026-05-26 06:00 UTC

## Secret Inventory (names only, no values)

| Key | Status | Notes |
|-----|--------|-------|
| XERT_EMAIL | present | Active |
| XERT_PASSWORD | present | Active |
| INTERVALS_ATHLETE_ID | present | Active |
| INTERVALS_API_KEY | present | Active |
| GARMIN_EMAIL | present | Active |
| GARMIN_PASSWORD | present | Active |
| GARMIN_TOKENSTORE | missing | Defined in .env.example only, not used at runtime |
| HAMMERHEAD_BEARER_TOKEN | present | Active |
| HAMMERHEAD_REFRESH_TOKEN | present | Active |
| HAMMERHEAD_TOKENSTORE | present | Active |
| HAMMERHEAD_USER_ID | missing | Optional for read-only local operations |
| RWGPS_AUTH_TOKEN | present | Active |
| RWGPS_API_KEY | present | Active |
| RWGPS_USER_ID | present | Active |
| RWGPS_PLANNED_COLLECTION_ID | present | Active |
| RIDEWITHGPS_AUTH_TOKEN | missing | Legacy name, not needed |
| RIDEWITHGPS_USER_ID | missing | Legacy name, not needed |
| OPENWEATHER_API_KEY | missing | Not used (Open-Meteo instead) |
| OPENWEATHERMAP_API_KEY | missing | Not used |
| OWM_API_KEY | missing | Not used |
| MAPBOX_TOKEN | missing | Not used |
| OVERPASS_URL | missing | Uses default free endpoint |
| CRONOMETER_EMAIL | present | Active |
| CRONOMETER_PASSWORD | present | Active |
| TELEGRAM_BOT_TOKEN | present | Active |
| TELEGRAM_ALLOWED_CHAT_IDS | present | Active |
| TELEGRAM_WEBHOOK_SECRET | present | Active |
| QBOT_MCP_TOKEN | missing | MCP is read-only, no token gating needed |
| MCP_SHARED_SECRET | missing | MCP is read-only |
| SMTP_HOST | missing | Uses Gmail SMTP directly |
| SMTP_USER | missing | Uses GMAIL_USER instead |
| SMTP_PASSWORD | missing | Uses GMAIL_APP_PASSWORD instead |

## Integration Auth Status

| Integration | Secrets | Config | Live Smoke | Restored | Action |
|------------|---------|--------|-----------|----------|--------|
| **Xert** | OK | OK | OK — FTP=245.9 | RESTORED | None |
| **Intervals.icu** | OK | OK | WARN — wellness fetch partial | PARTIAL | Investigate wellness response format |
| **Garmin** | OK | OK | OK — upload ready | RESTORED | Real upload needs approval |
| **Hammerhead** | OK | OK | OK — 5 local FIT files | RESTORED_FOR_READONLY | Token refresh if JWT expires |
| **RWGPS** | OK | OK | OK — config complete | RESTORED | Real API calls need approval |
| **OpenWeatherMap** | N/A | Open-Meteo only | WARN — no OWM key | OK (Open-Meteo) | Legacy OWM intentionally absent |
| **OpenMaps/OSM** | Free | Working | OK | RESTORED | None |
| **Cronometer** | OK | OK | OK — PARTIAL | RESTORED | Live login needs approval |
| **Telegram** | OK | Active | OK — agent executes tools | RESTORED | None |
| **MCP** | N/A | Active | 52 tools | RESTORED | None |
| **QExt2** | N/A | Active | OK — ready=true, ftp=245.9 | RESTORED | None |
| **Reports** | OK | Active | OK — daily sent 2026-05-25 | RESTORED | Real send needs approval |
| **Garage** | N/A | Working | WARN — PG tables not created | PARTIAL | Run garage_raw_import_v1.sql |

## Summary

| Metric | Count |
|--------|-------|
| Total integrations | 13 |
| RESTORED | 10 |
| PARTIAL | 3 (Intervals, Hammerhead, Garage) |
| OK (via alternative) | 1 (OpenWeather → Open-Meteo) |
| BLOCKED_BY_SECRET | 0 |
| AUTH_ERROR | 0 |
| APPROVAL_REQUIRED sub-features | 5 (Garmin real upload, RWGPS sync, Hammerhead online import, Cronometer live login, Report scheduler) |

## Next Actions

1. **Garage** — run `sql/garage_raw_import_v1.sql` to create tables, then import
2. **Intervals** — investigate PARTIAL wellness status
3. **Hammerhead** — refresh JWT if token expires
4. **Read-only status tools** — all integrations have working config/status tools
5. **Real operations** — Garmin upload, RWGPS sync, Hammerhead online import, Cronometer login, Report scheduler activation all require separate approval
