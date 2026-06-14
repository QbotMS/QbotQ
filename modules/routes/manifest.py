
MANIFEST = {
    "name": "routes",
    "domain": "open",
    "planner_tools": [
        "rwgps_route_find", "rwgps_route_list", "rwgps_route_fetch",
        "rwgps_route_last", "rwgps_route_import_gpx",
        "route_poi_analyze", "route_stage_plan_analyze", "stage_gpx_analyze",
        "rwgps_route_surface_analyze",
        "artifact_search", "artifacts_list", "artifact_save",
        "planning_facts", "planning_fact_lookup", "weather_forecast",
    ],
    "write_actions": [
        "rwgps_route_import_gpx",
        "route_poi_analyze",
        "rwgps_poi_push",
    ],
    "read_intents": [
        "rwgps_route_find", "rwgps_route_import_gpx", "rwgps_route_profile_sample",
        "route_poi_analyze", "route_generate", "route_climbs", "route_feasibility",
        "route_workflow_fetch", "route_workflow_upload", "route_workflow_list",
        "rwgps_recent_routes", "rwgps_poi_push",
        "trip_stages", "trip_summary", "trip_attractions", "trips_status",
    ],
}
