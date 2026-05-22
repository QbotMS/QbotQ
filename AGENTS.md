# QBot / OpenCode working instructions

Before working in this repository, read:
- QBOT_INSTRUCTIONS.md
- QBOT_CURRENT_STATE.md
- tools/rwgps/README_RWGPS.md when working on RideWithGPS / routes

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
