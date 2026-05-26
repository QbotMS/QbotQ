# QBot Task Spec

## Task ID
TS-2026-05-26-GATE-QNATIVE

## Context
The current gate runtime still exposes bridge/upstream configuration as if it were required, while the desired runtime is Q-native HikConnect direct with bridge mode preserved only as a legacy fallback.

## Goal
Make `qbot_qlab_server.py` treat HikConnect direct as the default gate mode, document the runtime configuration in the state files, keep bridge/upstream envs only as optional legacy fallback, and expose safe diagnostics without logging secrets.

## Scope
- Inspect and update gate runtime handling in `qbot_qlab_server.py`
- Add safe gate diagnostics/startup logging
- Update `.env.example`
- Update `QBOT_CURRENT_STATE.md`
- Update `scripts/qbot_operational_state.py` and regenerated `data/qbot_operational_state.json`

## Out of scope
- Creating a persistent `gate_hikconnect.py` file
- Logging secrets or raw tokens
- Changing unrelated integrations or services

## Files to inspect
- `qbot_qlab_server.py`
- `QBOT_CURRENT_STATE.md`
- `data/qbot_operational_state.json`
- `scripts/qbot_operational_state.py`
- `.env.example`
- `qbot_tools.py`

## Required data
- Current local runtime state from `/gate/status`
- Existing env variable names in the repository

## Allowed changes
- `qbot_qlab_server.py`
- `.env.example`
- `QBOT_CURRENT_STATE.md`
- `scripts/qbot_operational_state.py`
- `data/qbot_operational_state.json`

## Forbidden changes
- Secrets or token values
- Any `gate_hikconnect.py` file on disk
- Unrelated service configuration

## Implementation steps
1. Inspect the listed files and classify the current gate runtime behavior.
2. Implement a Q-native gate runtime snapshot and safe diagnostics.
3. Update the docs/state files to reflect the runtime and legacy fallback.
4. Validate locally and report any missing data or blocked assumptions.

## Tests
- `python3 -m py_compile qbot_qlab_server.py scripts/qbot_operational_state.py`
- `systemctl restart qbot-qlab-server`
- `curl -s http://127.0.0.1:8899/gate/status`

## Acceptance criteria
- [ ] Direct HikConnect is the default documented gate mode
- [ ] Bridge/upstream envs are treated as legacy fallback only
- [ ] Diagnostics report token/credentials/configuration state without secrets
- [ ] State docs and generated state JSON include the new gate runtime fields

## Final report format
1. Files changed
2. Validation performed
3. Outstanding risks or missing data
