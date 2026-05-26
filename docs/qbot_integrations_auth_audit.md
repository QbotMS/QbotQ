# QBot Integrations Auth Audit — 2026-05-26

## OpenWeatherMap

| Field | Value |
|---|---|
| Key present in .env.local | No |
| Key present in .env | No |
| Key present in legacy backups | No |
| Key present in old QBot config | No |
| Key copied/action | N/A — key not found anywhere |
| Primary provider | Open-Meteo/ECMWF (free, no key required) |
| OWM status | BLOCKED_BY_SECRET |
| Fallback | Open-Meteo works, returns wind_mps + wind_kmh |
| API key check env vars | OPENWEATHERMAP_API_KEY, OWM_API_KEY, WEATHER_API_KEY |

## Wind units

| Field | Value |
|---|---|
| User-facing unit | m/s (not km/h) |
| Data layer | wind_mps (primary) + wind_kmh (preserved) |
| Weather answer format | "Wiatr **16,2 m/s**" |
| Clothing answer format | "wiatr 16.2 m/s" |
| Clothing wind thresholds | >8 m/s: vest, >4 m/s: windbreaker, >12 m/s: strong wind warning |
| LLM prompt | Explicitly forbids km/h conversion |

## Intervals

| Field | Value |
|---|---|
| INTERVALS_ATHLETE_ID | Present in .env/.env.local |
| INTERVALS_API_KEY | Present in .env/.env.local |
| Auth status | OK (Basic auth) |
| API fix applied | Removed empty `oldest=&newest=` query params causing HTTP 422 |
| Wellness status | OK |
| Latest wellness date | 2026-05-26 |
| Weight | null (not filled today) |
| HRV | 82.0 |
| Resting HR | 44 |
| Sleep | 5.8 h |
| Wellness records count | 2963 |
| Status values | OK, BLOCKED_BY_SECRET, AUTH_ERROR, API_ERROR, PARTIAL_NO_TODAY_DATA |
| Next action | None needed — working |

## Changes summary

- `qbot_integration_tools.py`: Fixed intervals wellness API call (removed broken params), enhanced output with proper statuses, reason field, auth_ok
- `qbot_telegram_tools.py`: All user-facing wind converted to m/s, LLM prompts forbid km/h, clothing thresholds in m/s, intervals keywords added to triggers
