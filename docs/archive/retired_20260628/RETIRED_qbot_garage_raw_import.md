# QBot Garage — Raw 1:1 Import to PostgreSQL

**Date**: 2026-05-26

## Purpose
Import legacy garage data (gear, bikes, components, clothing, memories) from SQLite `data/garage.db` into PostgreSQL tables — 1:1, no normalization.

## Tables (sql/garage_raw_import_v1.sql)
- `qbot_garage_sources` — tracks source files with SHA256 dedup
- `qbot_garage_raw_records` — stores raw data as JSONB per source table
- `qbot_garage_import_runs` — records each import run

## Tools
| Tool | Safety | Description |
|------|--------|-------------|
| `qbot_garage_legacy_file_audit` | READ_ONLY | Find candidate source files |
| `qbot_garage_import_preview` | READ_ONLY | Preview source data before import |
| `qbot_garage_import_execute` | WRITE_SAFE | Import 1:1 with SHA256 dedup (dry_run=true default) |
| `qbot_garage_raw_status` | READ_ONLY | Show imported data status |
| `qbot_garage_raw_list` | READ_ONLY | List raw records (paginated) |
| `qbot_garage_raw_get` | READ_ONLY | Get single record by ID |
| `qbot_garage_raw_search` | READ_ONLY | LIKE search across records |

## MCP Exposure
- `qbot.garage_status` → raw_status
- `qbot.garage_list` → raw_list
- `qbot.garage_search` → raw_search

## Telegram
- `/garage` — status overview
- `/garage_search <text>` — via /ask query

## Security
- SHA256 dedup prevents duplicate imports
- dry_run=true default — nothing written unless explicitly approved
- No normalization — data preserved exactly as found
- Source file never modified or deleted
