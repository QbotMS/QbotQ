# QBot Task Spec

## Task ID
TS-2026-05-26-RWGPS-ARTIFACT-STORE

## Context
RWGPS route exports currently write GPX/TCX/JSON artifacts to disk and expose read-only parse/enrichment tools. The storage model should be hybrid:
- files store original artifacts and large derived outputs,
- PostgreSQL stores artifact metadata, parsed summaries, surface profiles, history, and cache state.

## Goal
Define and implement a durable hybrid storage model for RWGPS route artifacts that keeps source files on disk, stores normalized summaries and enrichment results in PostgreSQL, and uses hashes and parser versions to track freshness.

## Scope
- Inspect existing RWGPS export, parse, and enrichment helpers
- Define PostgreSQL-backed tables or table extensions for artifact metadata and parsed results
- Keep original artifacts as files under `/opt/qbot/artifacts`
- Store large or heavy derived outputs as files with DB pointers
- Add cache invalidation rules based on source artifact hash and parser version
- Add read-only tool support if needed for querying stored summaries

## Out of scope
- Changing the semantics of RWGPS export itself
- Moving source artifacts out of the filesystem
- Storing raw secrets or remote credentials
- Changing Garage routing
- Building new mutating sync flows

## Files to inspect
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- `mcp_server.py`
- `docs/qbot_implementation_roadmap.md`
- `governance/data_routing.md`
- `data_registry/modules.yaml`

## Required data
- Existing RWGPS export artifact path conventions
- Existing GPX parse helper and surface enrichment helper
- Existing PostgreSQL schema conventions in QBot
- Current artifact directory layout under `/opt/qbot/artifacts`

## Storage model

### Filesystem
Keep original and heavy derived artifacts as files:
- `exports/rwgps/<filename>.gpx`
- `analysis/routes/<filename>_summary.json`
- `analysis/routes/<filename>_surface.geojson`
- `analysis/routes/<filename>_overpass_raw.json`
- any other large derived artifact that is expensive to keep inline

### PostgreSQL
Store normalized state and lookup data:
- artifact metadata
- parse summary
- enrichment summary
- surface profile summary
- segment index
- cache freshness and history

## Proposed tables

### `route_artifacts`
One row per stored route artifact.

Fields:
- `id`
- `route_id`
- `source` (`rwgps`)
- `export_format` (`gpx_track`, `tcx_track`, `json_detail`)
- `artifact_path`
- `artifact_relative_path`
- `filename`
- `file_size_bytes`
- `sha256`
- `created_at`
- `updated_at`
- `parser_version`
- `source_artifact_sha256`
- `status` (`ok`, `stale`, `missing`, `error`)

### `route_parse_results`
One row per parsed artifact revision.

Fields:
- `id`
- `route_artifact_id`
- `parsed_at`
- `parser_version`
- `source_artifact_sha256`
- `track_points`
- `distance_m`
- `distance_km`
- `elevation_gain_m`
- `elevation_loss_m`
- `bbox_min_lat`
- `bbox_min_lon`
- `bbox_max_lat`
- `bbox_max_lon`
- `start_lat`
- `start_lon`
- `end_lat`
- `end_lon`
- `min_ele`
- `max_ele`
- `looks_valid`
- `summary_json`

### `route_surface_profiles`
One row per artifact enrichment run.

Fields:
- `id`
- `route_artifact_id`
- `enriched_at`
- `enrichment_version`
- `source_artifact_sha256`
- `surface_source` (`gpx`, `rwgps`, `osm`, `unknown`)
- `sample_every_m`
- `confidence`
- `coverage_pct`
- `sampled_points`
- `matched_points`
- `unmatched_points`
- `dominant_surface`
- `surface_summary_json`
- `surface_segments_path` or `surface_segments_json`

### `route_surface_segments`
Optional segment-level table for detailed analysis.

Fields:
- `id`
- `route_surface_profile_id`
- `segment_index`
- `distance_m`
- `surface`
- `confidence`
- `source`
- `start_lat`
- `start_lon`
- `end_lat`
- `end_lon`
- `geometry_json` or `geometry`

## Cache policy

Use the following freshness rules:
- A stored parse/enrichment row is valid only if `source_artifact_sha256` matches the current file hash.
- A change in `parser_version` or `enrichment_version` invalidates prior cached results.
- Heavy raw outputs may be retained on disk, but DB rows should mark them stale when the source hash changes.
- If `surface_source` is `unknown`, keep the result as an explicit negative cache entry instead of re-running immediately.

## Tool contract expectations

The storage model should support:
- `qbot_rwgps_route_export_file` for file creation and metadata only
- `qbot_gpx_artifact_parse` for lightweight parse summary
- `qbot_route_artifact_enrich` for optional surface enrichment
- a future read-only lookup tool if needed, e.g. `qbot_route_artifact_status`

## Allowed changes
- PostgreSQL schema files or migration scripts
- RWGPS artifact helper code
- read-only tool wrappers that query stored summaries
- route artifact docs and task specs

## Forbidden changes
- Changing RWGPS export to default to DB storage
- Removing source artifact files
- Writing secrets or raw API tokens to DB
- Moving Garage data into this model

## Implementation steps
1. Inspect the listed files and confirm the current artifact path and helper layout.
2. Define the PostgreSQL schema or schema extension for route artifacts and analysis results.
3. Wire parse/enrichment helpers to persist normalized results and cache metadata.
4. Keep original artifacts as files and large derived outputs as files with DB pointers.
5. Add or update smoke tests for metadata, parse freshness, and enrichment cache invalidation.

## Tests
- `python3 -m py_compile tools/rwgps/client.py qbot_route_tools.py qbot_tool_registry.py qbot_mcp_adapter.py qbot_query_processor.py scripts/qbot_smoke_tests.py`
- Local smoke test for export metadata
- Local smoke test for parse summary freshness
- Local smoke test for enrichment cache invalidation

## Acceptance criteria
- [ ] Original RWGPS artifacts remain files on disk
- [ ] PostgreSQL stores artifact metadata and normalized analysis results
- [ ] Surface profile data is cached and invalidated by artifact hash/version
- [ ] Heavy derived outputs can remain on disk with DB pointers
- [ ] No source artifact is embedded as the primary storage format in PostgreSQL

## Final report format
1. Files changed
2. Validation performed
3. Outstanding risks or missing data
