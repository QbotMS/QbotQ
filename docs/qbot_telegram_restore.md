# QBot Telegram — Restore & Runtime

**Date**: 2026-05-26

## Architecture
- Webhook: `POST https://qbot.cytr.us/telegram/webhook/{secret}` → Cloudflare → nginx → `127.0.0.1:8002`
- Reply: `sendMessage` via webhook JSON response or direct API call
- Auth: webhook secret in URL + optional `X-Telegram-Bot-Api-Secret-Token` header
- Chat allowlist: `TELEGRAM_ALLOWED_CHAT_IDS`

## Commands (18)
| Command | Description | Reply via |
|---------|-------------|----------|
| `/start`, `/help` | Command list | sendMessage |
| `/status` | Qbot status — API, DB, takeover | sendMessage |
| `/legacy` | Legacy cutover status | sendMessage |
| `/ready` | Readiness report | sendMessage |
| `/smoke` | Final smoke test | sendMessage |
| `/backup` | Backup status | sendMessage |
| `/errors` | Error summary | sendMessage |
| `/takeover` | Legacy takeover % | sendMessage |
| `/weather_status` | Weather status | sendMessage |
| `/garage_status` | Garage legacy status | sendMessage |
| `/artifacts` | Artifacts status | sendMessage |
| `/integrations` | Integrations report | sendMessage |
| `/rwgps` | RWGPS status | sendMessage |
| `/hammerhead` | Hammerhead import status | sendMessage |
| `/csv` | CSV export status | sendMessage |
| `/xert` | Xert training status | sendMessage |
| `/intervals` | Intervals wellness | sendMessage |
| `/garmin` | Garmin config/upload | sendMessage |
| `/cronometer` | Cronometer status | sendMessage |
| `/weather` | Weather config | sendMessage |
| `/maps` | OpenMaps status | sendMessage |
| `/garage` | Garage inventory | sendMessage |
| `/daily_report`, `/daily` | Daily report status | sendMessage |
| `/ride_report`, `/reports` | Ride report status | sendMessage |
| `/ask <query>` | Natural language query via policy engine | sendMessage |

## Runtime Self-Check
- Tool: `qbot_telegram_runtime_self_check`
- Sends real test message to first allowed chat
- Simulates `/status` dispatch
- Returns: OK/WARN/ERROR with issues list

## Security
- Every command returns `sendMessage` via webhook JSON response
- No command returns raw JSON without reply
- Fallback text for unknown commands
- No secrets in responses
- No stack traces in replies
- No CONTROLLED_ACTION via Telegram
- `/ask` routed through policy engine
