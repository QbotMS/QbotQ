# QBot Task Spec

## Task ID
TS-2026-05-26-RWGPS-ARTIFACT-ENRICH

## Context
RWGPS export writes local artifacts and the existing GPX parse tool returns lightweight summary metadata. Surface analysis is a separate enrichment step that may require OSM/Overpass access and should remain opt-in.

## Goal
Add a separate read-only route-artifact enrichment tool that can return summary metadata and, when explicitly requested, an OSM-based surface profile for an existing GPX/TCX/JSON artifact without changing export behavior or default parse behavior.

## Scope
- Inspect existing RWGPS artifact summary and surface analysis helpers
- Add a new read-only enrichment tool for route artifacts
- Expose the tool in the registry and public MCP adapter
- Add routing for explicit enrichment requests
- Add smoke tests for summary-only and surface-enriched paths

## Out of scope
- Changing RWGPS export behavior
- Making surface enrichment the default parse path
- Parsing remote content that is not an existing artifact
- Modifying Garage data or unrelated integrations

## Files to inspect
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- `mcp_server.py`

## Required data
- Existing RWGPS artifact summary helper
- Existing `analyze_rwgps_artifact_surface` helper
- Artifact path resolution rules

## Allowed changes
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- `tools/rwgps/README_RWGPS.md`
- `task_specs/TS-2026-05-26-RWGPS-ARTIFACT-ENRICH.md`

## Forbidden changes
- RWGPS export contract changes
- Secret logging
- Non-artifact storage writes
- Unrelated tool behavior

## Implementation steps
1. Inspect the listed files and classify the current summary and surface-analysis helpers.
2. Implement a thin enrichment wrapper that returns summary-only output by default and surface_profile only when requested.
3. Register the tool in QBot routing and public MCP metadata.
4. Add smoke tests for summary-only and surface-enriched execution.
5. Validate locally and report any missing data or blocked assumptions.

## Tests
- `python3 -m py_compile tools/rwgps/client.py qbot_route_tools.py qbot_tool_registry.py qbot_mcp_adapter.py qbot_query_processor.py scripts/qbot_smoke_tests.py`
- Local smoke test covering `qbot_route_artifact_enrich`
- Local smoke test covering explicit enrichment routing

## Acceptance criteria
- [ ] Summary-only parsing remains lightweight
- [ ] Surface enrichment is opt-in and returns `surface_source`
- [ ] The tool is available in the registry and MCP adapter
- [ ] Explicit enrichment requests route to the new tool

## Final report format
1. Files changed
2. Validation performed
3. Outstanding risks or missing data
