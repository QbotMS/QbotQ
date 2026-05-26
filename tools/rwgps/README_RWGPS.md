# RWGPS routes module

This module backs QBot route-planning tools for Ride With GPS.

## Data source order

1. Local manifest stored at `data/routes/rwgps_manifest.json`.
2. Optional RWGPS API sync if the account is configured.

## Environment

- `RWGPS_API_BASE` - base URL, default `https://ridewithgps.com`
- `RWGPS_AUTH_TOKEN` - required for remote RWGPS API access
- `RWGPS_API_KEY` - optional API key header
- `RWGPS_USER_ID` - required for remote RWGPS account-scoped queries
- `RWGPS_PLANNED_COLLECTION_ID` - optional collection used to mark planned routes

## MCP tools

- `get_rwgps_routes`
- `get_rwgps_route`
- `get_rwgps_planned_routes`
- `get_rwgps_collections`

## Notes

- Tools must remain visible in `tools/list` even when RWGPS is not configured.
- When remote RWGPS credentials are missing, tools should return a stable JSON
  payload with `ok: false` or a partial/local-manifest response and an explicit
  integration status block.
- The endpoint paths in `tools/rwgps/client.py` are centralized and may need
  adjustment if the account uses a different RWGPS API variant.
- Route list tools should return record arrays plus `count`/`total`, not only a
  summary string.
