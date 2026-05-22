# QBot Task Spec

## Task ID
TS-2026-05-22-001

## Context
Garage was historically used as a general data store. Under the new data routing
policy (governance/data_routing.md), Garage is restricted to bike hardware,
parts, service, wear tracking, and mechanical setup. This task audits the current
state of Garage to find data that violates the new policy and locations in code
that hardcode Garage as a general destination.

## Goal
Produce a read-only audit report identifying:
1. Data in Garage that belongs in other modules.
2. Code locations where Garage is hardcoded as a data sink.
3. Recommendations for what needs to be migrated (in a future task).

## Scope
- Inspect `data/garage.db` contents.
- Inspect all Python files under `/opt/qbot/app/` for hardcoded Garage references.
- Classify existing data against `data_registry/modules.yaml` routing rules.
- Produce an audit report.

## Out of scope
- Do NOT migrate any data.
- Do NOT change the Garage schema.
- Do NOT move or delete any files.
- Do NOT create new storage for other modules.
- Do NOT refactor `db.py` or `qbot_garage_mapper.py`.

## Files to inspect
- `data/garage.db` (read-only, via `db.py`)
- `db.py`
- `qbot_garage_mapper.py`
- `mcp_server.py` (Garage-related MCP tools)
- `telegram_reply_processor.py`
- `email_reply_processor.py`
- `QBOT_INSTRUCTIONS.md`
- `data_registry/modules.yaml`
- `governance/data_routing.md`

## Required data
- Garage database content (via `db.garage_overview()`)
- Full text search across `*.py` files for garage-related patterns

## Allowed changes
- Read-only inspection only.
- Produce a markdown report file.

## Forbidden changes
- Writing to any file in `/opt/qbot/app/`.
- Modifying `data/garage.db`.
- Changing any Python source file.

## Implementation steps
1. Read `governance/data_routing.md` and `data_registry/modules.yaml`.
2. Connect to `data/garage.db` and run `db.garage_overview()`.
3. For each record in `memories` table, classify the topic/content against routing rules.
4. Search all `*.py` files for patterns: `"garage"`, `"save_memory"`, `"save_gear"`, `"save_component"`, `"save_bike"`, `db.`.
5. List any non-garage data found in Garage tables.
6. List any code paths that route non-garage data to Garage.
7. Write the audit report to `task_specs/generated/TS-2026-05-22-001_audit_report.md`.

## Tests
- Verify `db.garage_overview()` returns data without errors.
- Verify grep for garage patterns produces complete results.
- Verify the audit report file exists and is not empty.

## Acceptance criteria
- [ ] All `memories` records are classified (garage vs non-garage).
- [ ] All hardcoded garage references in Python files are listed with file:line.
- [ ] Report clearly separates "in-policy" data from "needs migration" data.
- [ ] No files were modified during the audit.
- [ ] Report saved to `task_specs/generated/TS-2026-05-22-001_audit_report.md`.

## Final report format
1. Summary: total records inspected, how many are in-policy vs misrouted.
2. Misrouted data table: topic, content preview, recommended target module.
3. Code hot spots table: file:line, current behavior, recommended change.
4. Migration priority: critical / high / medium / low.
5. Recommended next task spec.
