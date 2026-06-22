# Wycofane narzedzia/skrypty trasowe — 2026-06-21

## Powod
Stary stack "G" (gravel intelligence: g1-g15) oraz jednorazowe skrypty analizy POI
i logistyki zostaly zastapione skonsolidowanym pipeline'em na siatce 80 m:
- tools/rwgps/{route_frames,route_weather,route_brief,ride_overlay,ride_verdict}.py
- narzedzia Alberta: route_plan_analysis (analiza ZAPLANOWANEJ trasy/track),
  ride_analysis (ocena WYKONANEJ jazdy/FIT).

## Weryfikacja przed przeniesieniem (2026-06-21)
- 0 importow w calym repo (poza samym plikiem, .bak, archive/).
- Brak w cronie (cron ma tylko fitmodel.daily_job).
- Zaden zywy entrypoint (qbot_api.py, scripts/surface_enrich_route.py) ich nie wola.

## Przeniesione (git mv)
Z scripts/: g1_analyze_surface, g2_detect_risks, g3_build_gravel_import_gpx,
g7b_gravel_batch_process, g8_stage_gravel_reports, g9_surface_quality_review,
g10_osm_cascade_scoring, g11_weather_modifier, g12_apply_manual_overrides,
g13_risk_briefing, g14_reroute_hints, g14b_reroute_alternatives,
g14e_build_candidate_route_gpx, g14f_validate_candidate_geometry,
g14g_candidate_review_package, g15_build_combined_poi_warnings_gpx,
analyze_route_poi_within_1km, analyze_route_poi_within_track_buffer,
analyze_rwgps_surface, route_logistics_candidates, route_logistics_commit_poi,
smoke_route_logistics.
Z tools/rwgps/: overpass_cache.py (0 importow).

## Przywrocenie
git mv archive/route_legacy_2026-06/<plik> <oryginalna_sciezka>
