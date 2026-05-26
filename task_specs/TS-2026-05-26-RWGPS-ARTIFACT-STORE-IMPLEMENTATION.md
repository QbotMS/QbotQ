# QBot Task Spec

## Task ID
TS-2026-05-26-RWGPS-ARTIFACT-STORE-IMPLEMENTATION

## Context
The hybrid storage model for RWGPS route artifacts has been defined:
- source artifacts stay on disk,
- PostgreSQL stores metadata, parse summaries, enrichment summaries, surface profiles, and cache freshness,
- heavy derived outputs may stay on disk with DB pointers.

This task implements the schema and write path needed to persist parse/enrichment results and cache state.

## Goal
Implement PostgreSQL-backed storage for RWGPS artifact metadata, parse summaries, and optional surface enrichment results, with freshness tracking based on artifact hash and parser/enrichment version, while preserving filesystem artifacts as the source of truth for raw files.

## Scope
- Inspect existing PostgreSQL schema and artifact helper code
- Add or extend PostgreSQL tables for route artifacts and analysis results
- Persist summary parse results and optional surface enrichment results
- Store cache freshness fields and versioning
- Keep original GPX/TCX/JSON artifacts on disk
- Add read-only lookup support only if needed to verify persistence
- Add smoke tests for stored summaries and cache invalidation

## Out of scope
- Changing RWGPS export defaults
- Moving original artifacts into PostgreSQL as the primary storage format
- Adding mutating sync/import flows
- Storing secrets or raw external credentials
- Changing Garage schema or routing

## Files to inspect
- `sql/init_qbot.sql`
- `sql/llm_planner_v1.sql`
- `db.py`
- `api_db.py`
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- `mcp_server.py`
- `docs/qbot_implementation_roadmap.md`

## Required data
- Current PostgreSQL schema style used by QBot
- Existing RWGPS artifact path conventions
- Existing parse and surface enrichment helpers
- Existing artifact root layout under `/opt/qbot/artifacts`

## Proposed schema

### `route_artifacts`
Stores one row per exported route artifact.

Suggested columns:
- `id`
- `route_id`
- `source`
- `export_format`
- `artifact_path`
- `artifact_relative_path`
- `filename`
- `file_size_bytes`
- `sha256`
- `created_at`
- `updated_at`
- `parser_version`
- `source_artifact_sha256`
- `status`
- `metadata_json`

### `route_parse_results`
Stores normalized parse results for a specific artifact revision.

Suggested columns:
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
Stores optional surface enrichment results.

Suggested columns:
- `id`
- `route_artifact_id`
- `enriched_at`
- `enrichment_version`
- `source_artifact_sha256`
- `surface_source`
- `sample_every_m`
- `confidence`
- `coverage_pct`
- `sampled_points`
- `matched_points`
- `unmatched_points`
- `dominant_surface`
- `surface_summary_json`
- `surface_segments_path`
- `surface_segments_json`

### `route_surface_segments`
Optional segment-level table for detailed or future map queries.

Suggested columns:
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
- `geometry_json`

## Cache policy
- A stored parse or enrichment row is valid only if `source_artifact_sha256` matches the current file hash.
- A change in `parser_version` or `enrichment_version` invalidates cached rows.
- Negative surface results should be stored explicitly as cache entries with `surface_source=unknown`.
- Heavy raw outputs may remain on disk, but the database must carry the pointer and freshness metadata.

## Allowed changes
- `sql/*.sql` migrations or schema files
- `db.py` and `api_db.py` helpers if needed for writes or reads
- `tools/rwgps/client.py`
- `qbot_route_tools.py`
- `qbot_tool_registry.py`
- `qbot_mcp_adapter.py`
- `qbot_query_processor.py`
- `scripts/qbot_smoke_tests.py`
- related docs/task specs

## Forbidden changes
- Making PostgreSQL the primary store for source GPX/TCX/JSON files
- Writing secrets or raw API payloads into the database
- Changing Garage storage or schema
- Adding unrelated route-import mutation flows

## Implementation steps
1. Inspect the current schema and identify where route artifact tables should live.
2. Add the minimum schema or migration needed for artifact metadata and analysis persistence.
3. Wire export/parse/enrich helpers to write normalized rows with hash/version freshness fields.
4. Keep artifact files on disk and store only pointers, hashes, and summaries in PostgreSQL.
5. Add smoke tests for write/readback and cache invalidation.

## Tests
- `python3 -m py_compile db.py api_db.py tools/rwgps/client.py qbot_route_tools.py qbot_tool_registry.py qbot_mcp_adapter.py qbot_query_processor.py scripts/qbot_smoke_tests.py`
- Local smoke test for export metadata persistence
- Local smoke test for parse summary persistence
- Local smoke test for enrichment persistence and invalidation

## Acceptance criteria
- [ ] Source artifacts remain files on disk
- [ ] PostgreSQL stores route artifact metadata and normalized analysis results
- [ ] Parse and enrichment rows are invalidated by artifact hash/version changes
- [ ] Surface enrichment remains opt-in and can persist summary state
- [ ] The implementation does not turn PostgreSQL into the primary store for raw source files

## Final report format
1. Files changed
2. Validation performed
3. Outstanding risks or missing data
