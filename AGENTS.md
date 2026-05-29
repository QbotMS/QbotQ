# QBot / OpenCode working instructions

Before working in this repository, read:
- QBOT_INSTRUCTIONS.md
- QBOT_CURRENT_STATE.md
- tools/rwgps/README_RWGPS.md when working on RideWithGPS / routes

## QBot3 Architecture (2026-05-29)

### Principle: Albert is the brain
qbot.query is a TRANSPARENT GATEWAY to Albert. No pre-router makes final intent decisions.
Write/read classification happens IN Albert (LLM), not before it.

### Allowed before Albert (context only)
- auth/context injection
- date/time/timezone
- source/channel metadata
- safety envelope (destructive block)
- mode hint (read_only / plan_only)

### NOT allowed before Albert
- final intent routing
- converting "add_nutrition_entry" → CAPABILITY_MISSING
- treating write requests as read-only
- slot extraction before Albert decides the action type

### Flow
```
qbot.query → context injection → safety envelope → Albert LLM → post-LLM write resolver → plan validation → execute tools → answer
```

### Post-LLM write intent resolver
If Albert returns `intent=add_nutrition_entry, mode=read_only, no_tools`, the post-LLM resolver maps it to `mode=write, write_action=nutrition_log_add`. This handles cases where the LLM identifies the correct intent but selects the wrong mode.

### DB Introspection (transparent read-only)
Albert has 4 DB introspection tools (NOT public MCP):
- `db_schema_list` — list schemas and tables
- `db_table_describe` — describe columns (name, type, nullable, pk)
- `db_sample_rows` — sample rows with LIMIT
- `db_select_readonly` — safe SELECT with guard (no INSERT/UPDATE/DELETE)

These give Albert full visibility of the database schema when readers fail.

### Reader error handling
Reader errors are NOT masked as "no_data":
- `SCHEMA_MISMATCH` — column not found in DB but referenced by reader
- `READER_ERROR` — reader-specific error (SQL error, connector error)
- `TIMEOUT` — query exceeded timeout
- `BLOCKED` — safety block

### Write flow
1. qbot.query → Albert decides write action → builds action_draft (no write)
2. qbot.action_execute → confirm + idempotency → validate → execute

### action_execute semantics
- `dry_run=true` → `status=DRY_RUN_OK, write_committed=false`
- `confirm=false` → `status=BLOCKED`
- Real execute (nutrition_log_add) → `status=OK, execution_mode=real_write, write_committed=true, inserted_id=...`
- Unavailable writers → `status=WRITE_NOT_AVAILABLE, execution_mode=mock`

### Nutrition write
Complex queries with macros are supported:
```python
# "Brokuł Sport 2000: 2011 kcal, białko 118 g, węglowodany 196 g, tłuszcz 79 g, sól 9,5 g"
# → meal_name, kcal_total, protein_g, carbs_g, fat_g, salt_g all extracted
```
template_id detection: `template_id=4` → `template_id=4`

General rules:
- Work from /opt/qbot/app.
- Do not guess project architecture. Inspect files first.
- Do not use Google/web unless explicitly requested.
- Do not print secrets or tokens.
- Do not write non-garage data into Garage.
- Use QBot Task Specs for non-trivial changes.
- If required data, source material, or a target module is missing, report it
  instead of inventing a location or schema.

RWGPS Route Lab rules:
- Work with any RWGPS route provided by the user or discovered from current state.
- Never overwrite or modify the original RWGPS route by default.
- For every source route, create or use a working copy with suffix " - QBot".
- All automatic edits must target the QBot copy, not the source route.
- Concrete route IDs from QBOT_CURRENT_STATE.md are historical/session context only, not hardcoded defaults.
- Before any write operation, state exactly which route ID will be changed.
- If unsure, stop and produce a read-only report.
