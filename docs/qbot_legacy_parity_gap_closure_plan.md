# Qbot Legacy Parity Gap Closure Plan

Generated from the full legacy parity audit.

## Current position

- Total capabilities detected: `22`
- Status counts: `RESTORED 13`, `PARTIAL 6`, `MISSING 1`, `BLOCKED_BY_POLICY 2`
- Legacy parity: `72.7%`

## What is left to reach 100%

### 1. Weather / OpenWeatherMap

- Current status: `MISSING`
- Why it is still a gap:
  - The current weather path exists and is read-only.
  - OpenWeatherMap-specific legacy parity is not present.
- Concrete next step:
  - Add a dedicated read-only weather compatibility layer that reports legacy OpenWeatherMap coverage separately from the current MCP weather path.
  - If the old QBot really depended on OWM runtime behavior, add status/current/forecast compatibility tools with no secret leakage.
- Proposed tools:
  - `qbot_weather_status`
  - `qbot_weather_current`
  - `qbot_weather_forecast`
- Priority: `high`

### 2. Artifacts / filesystem bridge

- Current status: `PARTIAL`
- Why it is still a gap:
  - Filesystem artifacts exist.
  - PostgreSQL `qbot_artifacts` exists.
  - The generic inventory / import / export bridge is still missing.
- Concrete next step:
  - Add a read-only filesystem inventory tool for artifacts.
  - Add preview-only import/export tools that do not write without explicit approval.
- Proposed tools:
  - `qbot_artifacts_filesystem_inventory`
  - `qbot_artifact_import_from_file_preview`
  - `qbot_artifact_export_preview`
- Priority: `high`

### 3. Garmin proxy / upload / Hammerhead import

- Current status: `PARTIAL`
- Why it is still a gap:
  - Garmin- and Hammerhead-related code exists.
  - The parity surface is still split across multiple helpers and legacy paths.
- Concrete next step:
  - Add explicit read-only status tools for Garmin proxy, Garmin upload readiness, and Hammerhead import readiness.
  - Keep all write / upload actions behind the policy engine and approval gates.
- Proposed tools:
  - `qbot_garmin_proxy_status`
  - `qbot_garmin_upload_status`
  - `qbot_hammerhead_import_status`
- Priority: `high`

### 4. MCP connector

- Current status: `PARTIAL`
- Why it is still a gap:
  - Public `/mcp/` works.
  - The adapter is still token-gated for write-safe artifact creation.
  - The audit classifies the connector as partial because some legacy parity tool surfaces are still missing or indirect.
- Concrete next step:
  - Keep the current read-only surface.
  - Add a small connector readiness summary that is separate from the public tool list, so parity can be checked without inference.
- Proposed tool:
  - `qbot_mcp_connector_parity_status`
- Priority: `medium`

### 5. Garage / gate / home automation

- Current status: `BLOCKED_BY_POLICY`
- Why it is still a gap:
  - Legacy traces exist.
  - The system deliberately does not expose an execution path for remote opening / closing.
- Concrete next step:
  - Treat this as a separate approval stream, not a normal parity backlog item.
  - Add only read-only evidence and inventory if needed.
  - Do not add execution tools unless there is an explicit safety decision.
- Proposed tool:
  - `qbot_home_automation_status` only as read-only evidence, not control
- Priority: `high`, but `blocked`

### 6. External API integrations

- Current status: `PARTIAL`
- Why it is still a gap:
  - Telegram, weather, Garmin, RWGPS, email, and webhooks are present.
  - Some integrations are still represented only indirectly in reports.
- Concrete next step:
  - Add a single summary tool that enumerates integration health by category and points to the underlying read-only status tools.
- Proposed tool:
  - `qbot_external_integrations_health`
- Priority: `medium`

## Already restored

- Core QBot API
- Telegram bot
- QLab
- Backup / restore
- FIT processing
- CSV / JSON reporting
- RWGPS
- OpenMap / OSM
- Filesystem artifacts baseline
- Scheduled jobs
- Email notifications
- Public endpoint blocking for `/q` and `/health`

## Decision boundaries

- `garage/gate` is intentionally policy-blocked.
- `weather` is read-only and must not expose API keys.
- `artifacts` must stay path-safe and must not write by default.
- `MCP` must not accept arbitrary tool names.

## Practical path to 100%

1. Close the read-only gaps first: weather compatibility, artifact bridge, Garmin/Hammerhead status.
2. Keep garage/gate separate and blocked until a safety-approved control design exists.
3. Re-run the parity audit.
4. Recompute parity only after the new read-only surfaces are in place.

