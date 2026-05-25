# QBot Route Integrations — Restore Status

**Parity Fix Pack v1** | 2026-05-25

## RWGPS (RideWithGPS)

### Status: PARTIAL

**What's working:**
- RWGPS client code: 1,781 lines in `tools/rwgps/client.py`, smoke-tested
- Local route manifest: `data/routes/rwgps_manifest.json` (1 cached route: Tuscany Trail 2026)
- Route cache: `data/routes/rwgps_route_cache.json` (3.3 MB)
- Backup: `/opt/qbot/backups/rwgps/` (4 files, original + QBot working copies)

**Config detection:**
- `RWGPS_AUTH_TOKEN`: PRESENT (from `.env`)
- `RWGPS_USER_ID`: MISSING
- `RWGPS_API_KEY`: MISSING
- `RIDEWITHGPS_USER_ID`: MISSING

**What's needed for live API:**
1. Set `RWGPS_USER_ID` in `.env.local`
2. (Optional) Set `RWGPS_API_KEY` for API v3 features
3. Run `qbot_rwgps_dry_run operation=list_routes` to verify connectivity

**Read-only tools available:**
- `qbot_rwgps_config_status` — config presence check (no values)
- `qbot_rwgps_legacy_status` — comprehensive code/config/artifact status
- `qbot_rwgps_dry_run` — safe dry-run with allowlist (list_routes, get_user, export_preview)
- `qbot_rwgps_restore_plan` — step-by-step restore plan

**MCP exposure:** `qbot.rwgps_status`, `qbot.rwgps_config_status`, `qbot.rwgps_restore_plan`

**Telegram:** `/rwgps`

**Do NOT execute:** upload, sync, create_route, delete_route, modify_route — all blocked by policy

---

## Hammerhead FIT Import

### Status: PARTIAL (read-only restored)

**What's working:**
- Tokenstore: `.hammerhead_tokens/` active (owned by qbot, readable by service)
- Bearer token + refresh token: both present in env
- JWT expiration: parsed from token payload
- 18 local FIT files in inventory (14 michal, 4 originals)
- Dry-run `source=latest`: returns local artifacts, `would_fetch=false`

**Config detection:**
- `HAMMERHEAD_BEARER_TOKEN`: PRESENT
- `HAMMERHEAD_REFRESH_TOKEN`: PRESENT
- `HAMMERHEAD_TOKENSTORE`: PRESENT (env var + on disk)
- `HAMMERHEAD_EMAIL`: MISSING (optional fallback — not required)
- `HAMMERHEAD_PASSWORD`: MISSING (optional fallback — not required)
- `HAMMERHEAD_USER_ID`: MISSING (optional for read-only local operations)

**Key features:**
- Email/password are OPTIONAL fallback — tokenstore + bearer/refresh is primary
- Dry-run works on local artifacts without API connection
- `restored_status`: `RESTORED_FOR_READONLY` when tokenstore active
- Real online import requires controlled execution approval

**Read-only tools available:**
- `qbot_hammerhead_config_status` — token/JWT/email presence check
- `qbot_hammerhead_import_status` — provenance + config + inventory overview
- `qbot_hammerhead_import_inventory` — list FIT files per profile
- `qbot_hammerhead_import_dry_run` — safe dry-run (no download, no sync)
- `qbot_hammerhead_restore_plan` — step-by-step restore plan

**MCP exposure:** `qbot.hammerhead_import_status`, `qbot.hammerhead_import_inventory`, `qbot.hammerhead_restore_plan`

**Telegram:** `/hammerhead`

**Do NOT execute:** real Hammerhead API download, Garmin upload, profile sync — all require controlled execution

---

## CSV Export

### Status: RESTORED

**What's working:**
- CSV inventory: 18 CSV files detected in `outgoing/`
- Latest CSV: `outgoing/qbot_garmin_proxy_latest.csv` (1.7 MB)
- CSV read: preview with configurable row limit (max 200)
- CSV export create: dry_run by default, writes to `outgoing/exports/`
- Auto-timestamping on filename conflict (prevents overwrites)

**Read-only tools available:**
- `qbot_csv_export_inventory` — list CSV files, directory breakdown
- `qbot_csv_export_latest_get` — read latest CSV with column + sample rows
- `qbot_csv_export_create_preview` — what would be generated (no write)
- `qbot_csv_export_create_execute` — controlled export (dry_run=true by default)
- `qbot_csv_export_status` — comprehensive status overview

**MCP exposure:** `qbot.csv_export_status`, `qbot.csv_export_inventory`, `qbot.csv_export_latest_get`

**Telegram:** `/csv`

**Security:** All writes go to `outgoing/exports/` only; path traversal prevented via `os.path.basename`; no overwrites on conflict; no arbitrary path inputs.

---

## What's Read-Only
- All config status tools
- All legacy status tools
- All inventory tools
- All dry-run operations
- All preview operations
- All MCP tools exposed (safety_class: READ_ONLY)

## What Requires Approval
- RWGPS live API calls (even read-only GET)
- Hammerhead API token refresh
- Hammerhead profile sync execution
- CSV export with `dry_run=false` (WRITE_SAFE, but controlled)
- Garmin upload execution

## What NOT to Execute Without Separate Step
- `qbot_rwgps_dry_run` operation=list_routes with live API (needs credentials first)
- `qbot_hammerhead_import_dry_run` source=latest (needs token refresh)
- Any real Hammerhead activity download or Garmin upload
- Any RWGPS route modification, creation, or deletion
