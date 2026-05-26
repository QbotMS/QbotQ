# QBot Task Spec

## Task ID
TS-2026-05-26-RWGPS-GPX-PARSE

## Context
RWGPS export currently writes local GPX/TCX/JSON artifacts and returns metadata. Parsing the artifact is a separate concern and should not be mixed into export behavior.

## Goal
Add a separate read-only GPX artifact parsing tool that summarizes an existing artifact by path/name and returns track-point, distance, elevation, and bounding-box metadata without changing RWGPS export behavior.

## Scope
- Inspect existing RWGPS export and artifact summary helpers
- Add a new read-only QBot tool for GPX artifact parsing
- Expose the tool in the registry and public MCP adapter
- Add safe routing for explicit parse requests
- Add smoke tests for the new tool and routing

## Out of scope
- Changing RWGPS export behavior
- Adding base64 transport to the parse tool
- Parsing non-artifact remote content
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
- Existing RWGPS artifact summary helpers
- Existing artifact path resolution rules
- Local smoke test baseline

## Allowed changes
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- `task_specs/TS-2026-05-26-RWGPS-GPX-PARSE.md`

## Forbidden changes
- RWGPS export contract changes
- Secret logging
- Non-artifact storage writes
- Unrelated tool behavior

## Implementation steps
1. Inspect the listed files and classify the current artifact summary path.
2. Implement a thin GPX artifact parse wrapper that normalizes existing summary data.
3. Register the tool in QBot routing and public MCP metadata.
4. Add smoke tests for the tool and for explicit parse routing.
5. Validate locally and report any missing data or blocked assumptions.

## Tests
- `python3 -m py_compile tools/rwgps/client.py qbot_route_tools.py qbot_tool_registry.py qbot_mcp_adapter.py qbot_query_processor.py scripts/qbot_smoke_tests.py`
- Local smoke test covering `qbot_gpx_artifact_parse`
- Local smoke test covering explicit parse routing

## Acceptance criteria
- [ ] Export behavior remains metadata-only by default
- [ ] A separate `qbot_gpx_artifact_parse` tool returns normalized artifact summary data
- [ ] The tool is available in the registry and MCP adapter
- [ ] Explicit parse requests route to the new tool instead of RWGPS status

## Final report format
1. Files changed
2. Validation performed
3. Outstanding risks or missing data
