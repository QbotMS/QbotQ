# QBot — inwentaryzacja bazowa (2026-07-24)
_Auto-zebrane przez scripts/audit_inventory.py. To DOWODY, nie werdykt — ocena w sesji porannej._
_Wygenerowano: 2026-07-23T23:28:34_

## 1. Uslugi i timery systemd

### Jednostki qbot*
```
UNIT                          LOAD   ACTIVE SUB     DESCRIPTION
  qbot-api.service              loaded active running Q API — FastAPI thin layer
  qbot-dev-mcp.service          loaded active running QBot Dev MCP (development control plane)
  qbot-mcp-bridge.service       loaded active running QBot MCP SSE bridge
  qbot-qlab-server.service      loaded active running QBot QLab export HTTP server
  qbot-web.service              loaded active running qbot-web - publiczny serwis HTML (Faza 1)
  qbot-backup.timer             loaded active waiting Daily Qbot PostgreSQL backup
  qbot-komoot-watch.timer       loaded active waiting Uruchamia qbot-komoot-watch co 5 minut (polling tras Komoot)
  qbot-nutrition-watchdog.timer loaded active waiting QBot nutrition watchdog codziennie 08:00 Europe/Warsaw

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.
        SUB    → The low-level unit activation state, values depend on unit type.

8 loaded units listed. Pass --all to see loaded but inactive units, too.
To show all installed unit files use 'systemctl list-unit-files'.
```
### Wszystkie timery (szukaj nieudokumentowanych)
```
NEXT                                  LEFT LAST                             PASSED UNIT                           ACTIVATES
Thu 2026-07-23 23:30:48 CEST      2min 13s Thu 2026-07-23 16:04:19 CEST     7h ago apt-daily.timer                apt-daily.service
Thu 2026-07-23 23:33:01 CEST      4min 26s Thu 2026-07-23 23:28:01 CEST    33s ago qbot-komoot-watch.timer        qbot-komoot-watch.service
Fri 2026-07-24 00:00:00 CEST         31min Thu 2026-07-23 00:00:10 CEST    23h ago dpkg-db-backup.timer           dpkg-db-backup.service
Fri 2026-07-24 00:00:00 CEST         31min Thu 2026-07-23 00:00:10 CEST    23h ago logrotate.timer                logrotate.service
Fri 2026-07-24 02:20:15 CEST      2h 51min Thu 2026-07-23 03:50:02 CEST    19h ago man-db.timer                   man-db.service
Fri 2026-07-24 03:24:01 CEST      3h 55min Thu 2026-07-23 03:23:11 CEST    20h ago qbot-backup.timer              qbot-backup.service
Fri 2026-07-24 08:00:00 CEST            8h Thu 2026-07-23 08:00:01 CEST    15h ago qbot-nutrition-watchdog.timer  qbot-nutrition-watchdog.service
Fri 2026-07-24 08:32:06 CEST            9h Thu 2026-07-23 17:26:08 CEST     6h ago motd-news.timer                motd-news.service
Fri 2026-07-24 09:24:47 CEST            9h Thu 2026-07-23 11:40:11 CEST    11h ago apt-daily-upgrade.timer        apt-daily-upgrade.service
Fri 2026-07-24 14:22:01 CEST           14h Thu 2026-07-23 14:22:01 CEST     9h ago update-notifier-download.timer update-notifier-download.service
Fri 2026-07-24 14:30:01 CEST           15h Thu 2026-07-23 14:30:01 CEST     8h ago systemd-tmpfiles-clean.timer   systemd-tmpfiles-clean.service
Sun 2026-07-26 03:10:39 CEST        2 days Sun 2026-07-19 03:11:11 CEST 4 days ago xfs_scrub_all.timer            xfs_scrub_all.service
Sun 2026-07-26 03:10:54 CEST        2 days Sun 2026-07-19 03:11:11 CEST 4 days ago e2scrub_all.timer              e2scrub_all.service
Sun 2026-08-02 01:55:57 CEST 1 week 2 days Sun 2026-07-19 06:19:34 CEST 4 days ago update-notifier-motd.timer     update-notifier-motd.service
-                                        - -                                     - apport-autoreport.timer        apport-autoreport.service
-                                        - -                                     - fstrim.timer                   fstrim.service
-                                        - -                                     - fwupd-refresh.timer            fwupd-refresh.service
-                                        - -                                     - snapd.snap-repair.timer        snapd.snap-repair.service
-                                        - -                                     - systemd-sysupdate-reboot.timer systemd-sysupdate-reboot.service
-                                        - -                                     - systemd-sysupdate.timer        systemd-sysupdate.service
-                                        - -                                     - ua-timer.timer                 ua-timer.service

21 timers listed.
```

## 2. Cron i harmonogramy

### /etc/crontab
```
# /etc/crontab: system-wide crontab
# Unlike any other crontab you don't have to run the `crontab'
# command to install the new version when you edit this file
# and files in /etc/cron.d. These files also have username fields,
# that none of the other crontabs do.

SHELL=/bin/sh
# You can also override PATH, but by default, newer versions inherit it from the environment
#PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Example of job definition:
# .---------------- minute (0 - 59)
# |  .------------- hour (0 - 23)
# |  |  .---------- day of month (1 - 31)
# |  |  |  .------- month (1 - 12) OR jan,feb,mar,apr ...
# |  |  |  |  .---- day of week (0 - 6) (Sunday=0 or 7) OR sun,mon,tue,wed,thu,fri,sat
# |  |  |  |  |
# *  *  *  *  * user-name command to be executed
32 *	* * *	root	cd / && run-parts --report /etc/cron.hourly
12 6	* * *	root	test -x /usr/sbin/anacron || { cd / && run-parts --report /etc/cron.daily; }
53 6	* * 7	root	test -x /usr/sbin/anacron || { cd / && run-parts --report /etc/cron.weekly; }
19 6	1 * *	root	test -x /usr/sbin/anacron || { cd / && run-parts --report /etc/cron.monthly; }
#

```
### /etc/cron.d: .placeholder, sysstat, e2scrub_all
### Harmonogramy/petle w kodzie (9 trafien)
```
mcp_server.py:1212  await asyncio.sleep(min(delay, 30))
mcp_server.py:1216  await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
mcp_server.py:1222  await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
scripts/audit_inventory.py:76  # harmonogramy w kodzie (APScheduler / petle / godziny)
scripts/audit_inventory.py:78  pat = re.compile(r"(apscheduler|BackgroundScheduler|add_job|on-calendar|OnCalendar|04:45|every\s+15|asyncio\.sleep|sched
scripts/run_wellness_imports.py:7  pojawienia sie danych. Wczesniej readiness liczyl TYLKO daily_job o 04:45 --
qbot3/connectors/import_garmin_sleep.py:4  Runs every 15 min 05:00-09:00.
qbot3/connectors/import_garmin_training.py:4  Runs every 15 min 09:00-23:59.
qbot3/connectors/import_garmin_energy.py:6  05:00-08:59 every 15min → yesterday's finalization (quality_status=full if complete)
```

## 3. Zlogi — pliki tymczasowe / kopie / archiwum

### Kandydaci do kasacji (25)
```
data/garage.db.bak.20260623_101007
data/garage.db.bak.20260623_101204
data/garage.db.bak.20260623_101714
docs/DECISIONS.md.bak.20260718_200343
docs/DECISIONS.md.bak.20260718_2030
docs/DECISIONS.md.bak.20260718_203930
docs/DECISIONS.md.bak.20260718_204942
docs/DECISIONS.md.bak.20260718_205355
docs/DECISIONS.md.bak.20260718_220853
docs/DECISIONS.md.bak.20260718_223903
docs/DECISIONS.md.bak.20260718_planer_atrakcje
docs/DECISIONS.md.bak.20260719_200644
docs/TODO.md.bak.1784411540
docs/architecture/MODELQ_V2.md.bak.20260718_200343
fitmodel/expedition_feasibility.py.bak.1784554083
outgoing/garmin_proxy/hammerhead_44954.activity.c9eea138-3c5a-476a-ab9a-09ab3e5e0cea_garmin_proxy.fit.bak.20260719_201939
qbot3/routes/planer_stage_export.py.bak.1784384731
qbot3/routes/planer_stage_export.py.bak.1784385176
qbot3/routes/route_attraction_store.py.bak.1784384492
scripts/_tmp_push_endurance.sh
scripts/_tmp_roundtrip_test.fit
tests/test_planer_stage_export.py.bak.1784384737
tests/test_planer_stage_export.py.bak.1784385183
tests/test_route_attraction_store.py.bak.1784382058
tests/test_route_attraction_store.py.bak.1784384509
```
### archive/ obecny — 29 plikow (przejrzec czy potrzebne)

## 4. Zlogi — moduly nieimportowane (kandydaci na martwy kod)

Heurystyka: modul, ktorego nazwa nie pada nigdzie poza wlasnym plikiem. Szum mozliwy (entrypointy, dynamiczne importy) — WYMAGA oceny.
```
_bak_archive/1781719108_opt_qbot_app_qbot_query_handler.py
_bak_archive/1781719163_qbot_query_handler.py
_bak_archive/1781719274_core_planner.py
_bak_archive/1781719274_test_qbot3_acceptance.py
_bak_archive/1781720264_tool_registry.py
_bak_archive/1781720370_agent_runtime.py
_bak_archive/1781720404_tool_registry.py
_bak_archive/1781720619_agent_runtime.py
_bak_archive/20260618_201630_mcp_server.py
_bak_archive/20260618_201630_qbot_api.py
fitmodel/_verify.py
fitmodel/modelq2/breakthrough.py
claude_funcs_src.py
deploy_ride.py
email_reply_processor.py
event_morning_report.py
fetch_google_all_stages.py
fetch_google_attr2.py
fetch_google_attractions.py
fetch_google_places_stage01.py
fetch_overpass_stage01.py
fetch_tuscany_gpx.py
find_rwgps_routes.py
tools/fit-export/fit_export.py
garmin_auth.py
qbot3/connectors/import_garmin_body.py
qbot3/connectors/import_garmin_energy.py
qbot3/connectors/import_garmin_sleep.py
qbot3/connectors/import_garmin_training.py
qbot3/connectors/import_withings_body.py
fitmodel/ingest_qext2_fit.py
monitor.py
qbot_activity_ingest.py
qbot_api.py
qbot_artifact_tools.py
qbot_ask_cli.py
qbot_assistant_inbox.py
qbot_cache.py
_bak_archive/20260716_calendar_core/qbot_calendar_cli.py
_bak_archive/20260716_calendar_core/qbot_calendar_core.py
qbot_capabilities.py
qbot_coach.py
qbot_context_resolver.py
qbot_dashboard.py
qbot_energy_store.py
qbot_external_llm_tools.py
qbot_file_tools.py
qbot_garage_mapper.py
qbot_garage_tools.py
qbot_garmin_history.py
qbot_garmin_workouts.py
qbot_health_advisor.py
qbot_health_cli.py
qbot_health_db.py
qbot_integration_tools.py
qbot_legacy_cutover_tools.py
qbot_legacy_execution_tools.py
qbot_legacy_inventory_tools.py
qbot_legacy_parity_tools.py
qbot_legacy_shadow_tools.py
qbot_legacy_tools.py
qbot_legacy_wrapper_tools.py
qbot_llm_planner.py
qbot_mcp_adapter.py
qbot_mcp_client.py
qbot_nutrition_cli.py
qbot_nutrition_parser.py
qbot_nutrition_planner.py
qbot_nutrition_tools.py
qbot_operator_tools.py
qbot_ops_tools.py
qbot_orchestrator.py
qbot_planning_cli.py
qbot_planning_memory.py
_bak_archive/20260716_calendar_core/qbot_qcal_cli.py
qbot_qcal_telegram.py
qbot_qlab_server.py
qbot_query_handler.py
qbot_query_planner.py
qbot_query_processor.py
qbot_readiness.py
qbot_recovery.py
qbot_reminder_tools.py
qbot_report_data_provider.py
qbot_report_status.py
qbot_report_tools.py
qbot_report_validator.py
qbot_roadmap_runner.py
qbot_task_queue.py
qbot_telegram_tools.py
qbot_tool_registry.py
qbot_tools.py
qbot_web.py
qbot_wellness_store.py
qgpt_chat_terminal.py
qgpt_client.py
qlab_replay_export.py
qbot3/connectors/rebuild_garmin_body_measurements.py
reminder_daemon.py
qbot3/secrets_reader.py
setup_analytical_env.py
smoke_analytical.py
smoke_p1p2p3.py
smoke_p2.py
smoke_r5n1r6.py
smoke_router.py
smoke_v3.py
smoke_v7.py
smoke_v9.py
sync_nutrition.py
telegram_reply_processor.py
tmp_add_20260703.py
tmp_delete_intake_231.py
tools/fit-export/validate_replay.py
```

## 5. Spojnosc: narzedzia (tool_registry) vs prompt Alberta (_SYSTEM)

### Narzedzia wykryte w rejestrze (3)
```
qbot.action_execute, qbot.query, rwgps_poi_push
```
### NIE wspomniane w prompcie Alberta (potencjalne narzedzia-widma)
```
qbot.query
rwgps_poi_push
```
### Opisy narzedzi > 500 znakow (zostana obciete): 0
```
(brak)
```

## 6. Endpointy web vs dokumentacja

### Endpointy w qbot_web.py (56)
```
/api/calendar
/api/calendar/delete
/api/calendar/edit
/api/calendar/entry
/api/calendar/route
/api/forma/activities
/api/forma/activity
/api/forma/analyze
/api/forma/data
/api/modelq2/data
/api/modelq2/recompute
/api/noclegi
/api/nutrition/analyze
/api/nutrition/data
/api/nutrition/day-summary
/api/nutrition/preset/apply
/api/nutrition/preset/values
/api/nutrition/status
/api/planer/atrakcja
/api/planer/dodaj-do-qbot
/api/planer/dzien
/api/planer/dzien/gpx
/api/planer/foto/{place_id}
/api/planer/opis
/api/planer/opis-dni
/api/planer/tlo
/api/planer/wykonalnosc
/api/prefs
/api/report/attractions/fetch
/api/report/data
/api/report/gpx
/api/report/history
/api/report/mail-recipients
/api/report/push-karoo
/api/report/send-email
/api/report/snapshot/{snapshot_id}
/api/ride-report/correlate
/api/ride-report/data
/api/ride-report/w2
/api/rides/ready
/api/routes/ready
/api/routes/{route_id}/geometry
/api/routes/{route_id}/segments/candidate
/api/routes/{route_id}/surface-categories
/api/routes/{route_id}/surface-segments
/api/routes/{route_id}/tiles
/api/wyprawa/pdf
/api/wyprawa/pdf-start
/api/wyprawa/rsvp
/api/wyprawa/rsvp-list
/api/wyprawa/send-email
/healthz
/kanon
/login
/reports/{fn}
/wyprawa-rsvp
```
### Nieudokumentowane (brak w RAPORT_WEB/FORMA/CONTEXT)
```
/api/calendar
/api/calendar/delete
/api/calendar/edit
/api/calendar/entry
/api/calendar/route
/api/modelq2/data
/api/modelq2/recompute
/api/noclegi
/api/nutrition/analyze
/api/nutrition/data
/api/nutrition/day-summary
/api/nutrition/preset/apply
/api/nutrition/preset/values
/api/nutrition/status
/api/planer/atrakcja
/api/planer/dodaj-do-qbot
/api/planer/dzien
/api/planer/dzien/gpx
/api/planer/foto/{place_id}
/api/planer/opis
/api/planer/opis-dni
/api/planer/tlo
/api/planer/wykonalnosc
/api/report/attractions/fetch
/api/report/gpx
/api/report/mail-recipients
/api/report/push-karoo
/api/report/snapshot/{snapshot_id}
/api/routes/{route_id}/geometry
/api/routes/{route_id}/segments/candidate
/api/routes/{route_id}/surface-categories
/api/routes/{route_id}/surface-segments
/api/wyprawa/pdf
/api/wyprawa/pdf-start
/api/wyprawa/rsvp
/api/wyprawa/rsvp-list
/api/wyprawa/send-email
/kanon
/reports/{fn}
/wyprawa-rsvp
```

## 7. Tabele — kod vs schemat bazy

### Tabele qbot_v2.* uzywane w kodzie (95)
```
activity_event, activity_fit_raw, activity_lap, activity_record, albert_day_view, artifact_status, artifact_type, artifacts, athlete_profile, body_daily, body_latest_full_composition, body_latest_weight, body_measurements, body_measurements_staging, body_trend_full_composition, body_trend_weight, calendar_day_route, calendar_entry, calendar_reminder_fired, change_log, daily_summary, days, energy_daily, fitmodel_daily, fitmodel_param, fitmodel_qext2_ride, fitmodel_ride_buckets, fitmodel_segment, fitmodel_surface_cal, fitmodel_wbal_ride, fitmodel_week_plan, fitmodel_xert_bench, food_items, fueling_events, google_places_usage, hydration_events, incident_tickets, intake_items, intake_logs, komoot_seen_tours, meal_log_items, meal_logs, meal_templates, modelq2_anchor, modelq2_ride, modelq2_signature, modelq2_xert_bench, mutation_type, nutrition_daily_summary, nutrition_day_plan_meals, nutrition_day_plans, planer_route_opis, planer_route_opis_dni, planer_route_tlo, projects, qbot_memory, qbot_planning_facts, qbot_wellness_daily, quality_status, report_mail_recipients, ride_frames, ride_report_data, route_admin_cache, route_artifacts, route_attraction_layer, route_attraction_run, route_axis_segments, route_base, route_climb_events, route_elevation_samples, route_frame_weather, route_frames, route_landcover_layer, route_parse_results, route_poi_layer, route_poi_meta, route_poi_prefs, route_point_geo_cache, route_precompute_jobs, route_report_snapshots, route_shade_layer, route_stage_lineage, route_surface_context, route_surface_layer, route_surface_profiles, route_surface_segments, route_wind_clim, sleep_daily, training_sessions, ui_prefs, wellness_daily, worldcover_classes, wyprawa_report, wyprawa_rsvp, xert_profile_snapshots
```
### Kod odwoluje sie do tabel NIEISTNIEJACYCH w bazie (POWAZNE)
```
artifact_status
artifact_type
mutation_type
quality_status
```
### Tabele w bazie nieuzywane w kodzie (15 — moga byc sieroty lub uzywane z SQL/dashboardow)
```
body_daily_backup_20260531_2002, fitmodel_daily_v1_backup, fitmodel_segment_bak_20260707, fitmodel_wbal_ride_v1_backup, garmin_workout_write_audit, qbot_artifacts, qbot_doc_write_audit, qbot_import_runs, qbot_nutrition_daily, qbot_plans, qbot_sleep_daily, qbot_wellness_notes, ride_report_data_v1_backup, route_analysis_run, tool_calls
```

## 8. Wlasciwe zrodla danych — inwarianty kanonu

### CP/W' liczone z plikow FIT zamiast activity_record (nie powinno)
```
fitmodel/fit_ingest.py
fitmodel/surface_tag.py
```
### Slad mitu 'zamrozenie ingestu 2026-06-28'
```
scripts/audit_inventory.py:214 # 8b. slad 'zamrozenia 2026-06-28' (bledny mit — nie powinno byc w kodzie)
scripts/audit_inventory.py:219 if "2026-06-28" in line and re.search(r"(frozen|zamro|freeze|ingest)", line, re.I):
scripts/audit_inventory.py:223 findings.append(("Slad mitu 'zamrozenie ingestu 2026-06-28'", frozen or ["(brak — dobrze)"]))
scripts/build_context.py:131 "- WSZYSTKIE dane 1Hz SA W BAZIE. Tabela qbot_v2.activity_record ma strumienie sekundowe (ts, power_
```
### Pliki mieszajace Xert z FTP/CP/W' (sprawdz czy tylko benchmark, nie input)
```
qbot_route_report_tool.py
qbot_capabilities.py
qbot_tool_registry.py
daily_report.py
qbot_dashboard.py
mcp_server.py
qbot_web.py
qbot_context_resolver.py
qbot_query_router.py
qbot_report_tools.py
event_morning_report.py
qbot_report_data_provider.py
qbot_telegram_tools.py
qbot_query_handler.py
qbot_orchestrator.py
qbot_api.py
qbot_report_validator.py
qbot_integration_tools.py
ride_report.py
qbot_query_processor.py
qbot_mcp_adapter.py
daily_report_adapter.py
tests/test_report_data_provider.py
tests/test_qbot3_acceptance.py
_bak_archive/20260618_201630_qbot_api.py
_bak_archive/1781719274_test_qbot3_acceptance.py
_bak_archive/1781720404_tool_registry.py
_bak_archive/1781719163_qbot_query_handler.py
_bak_archive/1781720619_agent_runtime.py
_bak_archive/1781720370_agent_runtime.py
_bak_archive/1781719108_opt_qbot_app_qbot_query_handler.py
_bak_archive/20260618_201630_mcp_server.py
_bak_archive/1781720264_tool_registry.py
_bak_archive/20260716_calendar_core/qbot_calendar_core.py
scripts/mq2_backfill.py
scripts/debug_xert_raw.py
scripts/test_query_vnext_mcp_shape.py
scripts/qbot_smoke_tests.py
scripts/audit_inventory.py
scripts/mq2_seed_anchors.py
scripts/qbot_operational_state.py
scripts/test_query_vnext_adapter_activation.py
archive/modelq_v1/cp_wprime.py
archive/modelq_v1/cp_v3.py
tools/feasibility.py
fitmodel/wbal_replay.py
fitmodel/ingest_qext2_fit.py
fitmodel/buckets.py
fitmodel/daily_job.py
fitmodel/ftp_resolver.py
fitmodel/modelq2/progression.py
fitmodel/modelq2/decay.py
fitmodel/modelq2/signature.py
qbot3/tool_registry.py
qbot3/agent_runtime.py
qbot3/routes/route_report_canonical.py
qbot3/llm/mock_provider.py
qbot3/llm/albert.py
qbot3/adapters/mcp_adapter.py
qbot3/rides/ride_report_builder.py
qbot3/rides/ride_report_w2.py
qbot3/connectors/import_xert_profile_snapshot.py
```

## 9. Testy jednostkowe

rc=1
```
.venv/lib/python3.12/site-packages/fastapi/applications.py:4579
  /opt/qbot/app/.venv/lib/python3.12/site-packages/fastapi/applications.py:4579: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

scripts/test_gpx_artifact_geometry_readout.py::test_by_route_id
  /opt/qbot/app/.venv/lib/python3.12/site-packages/_pytest/python.py:170: PytestReturnNotNoneWarning: Test functions should return None, but scripts/test_gpx_artifact_geometry_readout.py::test_by_route_id returned <class 'dict'>.
  Did you mean to use `assert` instead of `return`?
  See https://docs.pytest.org/en/stable/how-to/assert.html#return-not-none for more information.
    warnings.warn(

scripts/test_intake_logs_0531.py::test_intake_logs_0531
  /opt/qbot/app/.venv/lib/python3.12/site-packages/_pytest/python.py:170: PytestReturnNotNoneWarning: Test functions should return None, but scripts/test_intake_logs_0531.py::test_intake_logs_0531 returned <class 'bool'>.
  Did you mean to use `assert` instead of `return`?
  See https://docs.pytest.org/en/stable/how-to/assert.html#return-not-none for more information.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_route_gpx_not_modified_by_enriched_gpx
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_route_with_selected_poi_gpx_has_track_and_wpt
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_selected_poi_output_files
FAILED scripts/test_rwgps_export_artifact_store_registration.py::test_export_and_registration
FAILED tests/test_capability_fallback.py::test_capability_fallback_daily_report_status
FAILED tests/test_report_data_provider.py::TestReportDataProvider::test_daily_partial_data
FAILED tests/test_report_data_provider.py::TestReportDataProvider::test_daily_partial_ok
FAILED tests/test_report_validation.py::TestReportDiagnosticHandlers::test_daily_report_handler_returns_data
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_query_b
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_query_c
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_returns_envelope
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_google_supply_status_is_separate_from_overpass_completeness
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_overpass_fallback_used_when_google_empty
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_partial_chunk_reports_reason
ERROR qbot3/capabilities/test_harness.py::test_capability
ERROR scripts/test_gpx_artifact_geometry_readout.py::test_dump_summary
14 failed, 437 passed, 14 skipped, 4 warnings, 2 errors in 36.08s
```

## 10. Git — stan i tydzien commitow

### git status --short
```
M fitmodel/daily_job.py
 M qbot_activity_ingest.py
?? scripts/_mast.b64
?? scripts/_tmp_push_endurance.sh
?? scripts/audit_inventory.py
```
### Commity z 7 dni
```
ecf0a9e raport trasy: karta Forma wylacznie z ModelQ (fitmodel_daily), nie Xert; XSS zaokraglony
41bc4e5 readiness: przelicz gotowosc po imporcie wellness (run_wellness_imports) -- fix float todayFactor; wczesniej readiness tylko o 04:45 PRZED importem, teraz odswiezany co 15 min rano
0bab326 docs: wpis 2026-07-23 bezpiecznik Google Places + guard atrakcji (DECISIONS + CURRENT)
aef6cce Places: bezpiecznik dzienny/miesieczny (200/1000) + guard atrakcji (force=false czyta z bazy, przycisk Odswiez z Google)
3d7dbfc Wyprawa: PDF cache/email/RSVP + tla tytuly; checkpoint przed przebudowa planera
583a232 planer: build_tlo — tlo historyczne (do 1945) + geograficzno-przyrodnicze dla Planera ALL; cache qbot_v2.planer_route_tlo
8900829 raport trasy: komentarze_ryzyka - wnioskowanie z route_surface_context (teren/nawierzchnia/sand_risk) + rozroznienie piach z tagu (fakt) vs z regionu (domysl); waga wg pewnosci
d3b2ba7 raport trasy: komentarze_ryzyka - wnioskowanie z kontekstem terenu (las/pola/otwarty), bez cytowania surowych tagow OSM
e61a8e6 raport trasy: komentarze_ryzyka tylko identyfikacja+opis ryzyka (bez rad, bez beletrystyki)
3b3096d glycogen: fix jednostek cho_burn (J->kcal /4184) + usuniecie nieosiagalnego full-refill + flaga confidence high/low/none dla dni z niepelnym logiem + test regresyjny
924bfcc ModelQ W-prime z drogi (Wariant b): replay_deficit + wprime_road.py (max dolnej granicy z Wbal=0) w daily_job; kotwica pewnosci utwardzona (data z activity_record); /ride-readiness W-prime = max(MQ2, road)
abf2ade docs: handoff CURRENT + TODO dla verify_dupes (scheduled weryfikacja duplikatow)
7fb7aaa scheduled: verify_dupes.py -- poranna weryfikacja duplikatow jazd (tylko zglasza; cron root 05:30; Telegram tylko o nowych grupach; stan data/verify_dupes_seen.json)
1651e05 Tor1: unifikacja XSS trasy na fizyke (route_xss_phys wspolny dla raportu i planera; predkosc v2 -> moc -> compute_xss); werdykt Planera na model dwoch scian (demonstrowany/metaboliczny/tydzien z BMR) + fix kolejnosci regeneracji TSB
9dd885c context: auto sekcja Ostatnie commity (z gita) + regula higieny TODO/CURRENT w build_context
8623b4d tools: worklock (tablica robocza sesji, blokada kolizji edycji) + regula w CONTEXT przez build_context; ignoruj .worklock.json
96b6fe7 docs(CLAUDE.md): read-first -> CURRENT+DECISIONS (w repo); CONTEXT.md zywy na serwerze, poza repo
2b2c676 docs: dokumentacja silnika wykonalnosci wyprawy + aktualizacje planer/route_store/TODO/MODELQ; handoff CURRENT+DECISIONS (19-20.07)
ff1f8a8 planer: fizyczny XSS trasy (predkosc v2 -> moc -> compute_xss) + wiatr klimatologiczny + endpoint wykonalnosci; silnik expedition_feasibility
12d4227 ride_report: cog_time_pct pokazuje wszystkie 13 pozycji kasety AXS, wypelniajac zerem nieuzyte (2026-07-19)
1462707 RSRV: todayFactor z readiness_effective (k=0.10, zacisk 0.70-1.10) + decyzja dryf-przy-tej-samej-mocy i skala 3/x3/18
a95f802 web(mail): historia odbiorcow po stronie serwera (tabela report_mail_recipients + endpoint + zapis przy wysylce)
dd41ce6 web(mail): pogoda pod profilem trasy + wieksza skala (mapa/wykres 700px, mail 760px)
e9408e5 web(mail): usun strategie z maila, atrakcje z opisem (extract) + wbudowane zdjecia CID; endpoint atrakcji zwraca summary+source_status
eea9287 attractions: broaden global landmark discovery
ef2d82c attractions: publish sparse quality results
3b4bf88 web: przycisk POBIERZ atrakcje w raporcie trasy (endpoint /api/report/attractions/fetch -> ensure_route_attractions)
ef872bf raport jazdy: ModelQ ride_impact - delty CP/LTP/Wprime/PP (wplyw jazdy per parametr)
9393936 docs: document planner attractions and day routes
d4238e3 planer: purge superseded day routes
74e31d2 planer: hide superseded day splits
c972a5a planer: create day GPX routes with shared attractions
692b029 planer: restore attraction media and source links
f577e34 routes: alias attraction schema probes for dict rows
270e4a3 routes: separate candidate quality from recommendation spacing
a246600 routes: keep landmarks separate from historic towns
575838a routes: retry Google attraction samples
b4fbbcb routes: filter palace ancillary attraction noise
edf7693 routes: support Planer tuple row connections
08e3339 routes: publish only dense semantic attraction sets
15016ed routes: extend open-data canary retry budget
31ff192 routes: gate Google candidates through semantic ranking
b3746d1 routes: separate OSM discovery from Google evidence
2e141ae routes: enable OSM attraction discovery
b6a2398 db: grant attraction store access to qbot
84e94aa routes: make Google attraction errors fail open
1f15659 routes: accept canonical attraction route ids
bcd01e9 routes: add canonical attraction ranking
d56922d docs: CURRENT/TODO/FORMA_UI
88b0d86 web: qbot_web.py
7f3cdc9 rdzen: agent/registry/albert + narzedzia + fix przestarzalych testow
b6e62fc fitmodel: wprime_anchor + hidden_fatigue
957d419 kalendarz v2: nowy rdzen, usuniecie starego CLI
f4ec8d6 zywienie: presety + CLI
db21142 web: dev_fetch.py (weryfikacja za brama logowania) + docs (CONTEXT via build_context, DECISIONS)
4fa369e raport trasy: proza LLM split+retry; szczegoly UI; kalendarz dzwonek (+docs)
13cee0c Doradca: uwzglednia plan z kalendarza (_forma_planned_events)
162a20d forma/activity: has_report + panel szczegolow jazdy
9fbd3f0 forma: /api no-store + szczegoly jazdy (/api/forma/activity)
9fc9c5e DZIS: server-side prefs (ui_prefs + /api/prefs GET/POST)
65a3edb fix(db): repoint refresh_day_flags trigger to calendar_entry; deprecate calendar_core_v1
3744613 Odzywianie: sklad ciala z body_trend_full_composition (Garmin INDEX_SCALE, dane do lipca) zamiast stale body_daily
df78213 forma: Sen jako sleep_score (join qbot_wellness_daily) + mapa analizy
```
