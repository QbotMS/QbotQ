# CLAUDE.md — QBot repo workflow

Primary instructions for Claude working in `/opt/qbot/app`.

## Read first

1. `CLAUDE.md`
2. `docs/CURRENT.md` (session handoff) and `docs/DECISIONS.md` (decision log) — both are in the repo.
3. `docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md`
4. `QBOT_INSTRUCTIONS.md` only when changing the QBot runtime prompt.

Note on `docs/CONTEXT.md`: it is the full live source of truth, but it is auto-generated (`scripts/build_context.py`) and intentionally git-ignored (`.gitignore`), so it lives only on the server, not in the repo. When working on the server/SSH, read it from `/opt/qbot/app/docs/CONTEXT.md`. When docs disagree with code, the live system wins.

`PROJECT_STATE.md` is historical. `QBOT_CURRENT_STATE.md` is deprecated.

Old instruction files from before this cleanup are archived in:

```text
docs/archive/instructions_backup_20260627/
```

Archive index: `docs/archive/README.md`.

## Context-budget discipline

Work economically with repository context.

- Use `grep`, `find`, symbols, and targeted tests before opening files.
- Read the smallest useful file slice.
- Do not load large files blindly.
- Ignore historical/noisy paths unless explicitly needed: `_bak_archive/`, `_patch_archive/`, `*.bak*`, `docs/reports/`, old `task_specs/`, caches.
- Verify live code before trusting architecture docs.
- Keep reports short: finding, evidence, decision, next step.

## Current QBot3 model

- Public MCP handler: `qbot3/adapters/mcp_adapter.py`.
- Current public `tools/list`: `qbot_query` only.
- `qbot.action_execute` exists in backend/legacy/admin paths but is not public in current `tools/list`.
- `QBOT_QUERY_VNEXT_ENABLED=1`: `qbot_query` first tries `qbot_query_handler.handle_query()`.
- `UNRECOGNIZED`, `ACTION_REQUIRED`, or query_vnext error falls back to `qbot3.agent_runtime.orchestrate_query()`.
- Albert runtime: `qbot3/agent_runtime.py`, `qbot3/llm/albert.py`, `qbot3/tool_registry.py`.
- `core/planner.py` does not exist. Do not describe route handling as Planner v2.

## Editing workflow

- Check `git status --short` first.
- Identify exact target files.
- Prepare candidate files first, then replace targets.
- After replacement check `git status --short`, `git diff --stat`, and targeted diff.
- Do not commit, push, restart, or deploy without explicit user approval.

## Boundaries

Do not touch runtime code, operational configuration, service state, or database state unless the user explicitly requests it.

Documentation cleanup may edit only the agreed instruction/documentation files.

## Tool registry rule

Any change to `qbot3/tool_registry.py` or a new domain/intent must be reflected in `_SYSTEM` in `qbot3/llm/albert.py` in the same work step.

A tool change without an Albert prompt update is incomplete.

## Tests

Use targeted tests matching touched modules.

Known caveat: `tests/test_qbot3_acceptance.py` is partly stale. It still contains old assumptions about `core.planner` and two public MCP tools. Do not use it as the only acceptance gate until updated.
