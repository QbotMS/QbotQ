# QBot — inwentaryzacja bazowa (2026-10-15)
_Auto-zebrane przez scripts/audit_inventory.py. To DOWODY, nie werdykt — ocena w sesji porannej._
_Wygenerowano: 2026-10-15T11:35:10_

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
  qbot-garmin-watch.timer       loaded active waiting Sprawdza co 10 min, czy Garmin ma nowa jazde
  qbot-guest-forecast.timer     loaded active waiting QBot G4 - prognoza dla gosci 07:00 i 18:00 Europe/Warsaw
  qbot-komoot-watch.timer       loaded active waiting Uruchamia qbot-komoot-watch co 5 minut (polling tras Komoot)
  qbot-nutrition-watchdog.timer loaded active waiting QBot nutrition watchdog codziennie 08:00 Europe/Warsaw

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.
        SUB    → The low-level unit activation state, values depend on unit type.

10 loaded units listed. Pass --all to see loaded but inactive units, too.
To show all installed unit files use 'systemctl list-unit-files'.
```
### Wszystkie timery (szukaj nieudokumentowanych)
```
NEXT                             LEFT LAST                                   PASSED UNIT                           ACTIVATES
Thu 2026-10-15 11:37:13 CEST  2min 2s Thu 2026-10-15 11:27:13 CEST         7min ago qbot-garmin-watch.timer        qbot-garmin-watch.service
Thu 2026-10-15 11:39:15 CEST  4min 4s Thu 2026-10-15 11:34:15 CEST          55s ago qbot-komoot-watch.timer        qbot-komoot-watch.service
Thu 2026-10-15 12:51:22 CEST 1h 16min Wed 2026-10-14 11:24:11 CEST          24h ago apt-daily-upgrade.timer        apt-daily-upgrade.service
Thu 2026-10-15 14:44:16 CEST  3h 9min Wed 2026-10-14 14:44:16 CEST          20h ago update-notifier-download.timer update-notifier-download.service
Thu 2026-10-15 14:52:50 CEST 3h 17min Wed 2026-10-14 14:52:50 CEST          20h ago systemd-tmpfiles-clean.timer   systemd-tmpfiles-clean.service
Thu 2026-10-15 17:49:23 CEST       6h Thu 2026-10-15 05:37:54 CEST     5h 57min ago apt-daily.timer                apt-daily.service
Thu 2026-10-15 17:52:42 CEST       6h Thu 2026-10-15 03:41:11 CEST           7h ago motd-news.timer                motd-news.service
Thu 2026-10-15 18:00:00 CEST       6h Thu 2026-10-15 07:00:01 CEST     4h 35min ago qbot-guest-forecast.timer      qbot-guest-forecast.service
Fri 2026-10-16 00:00:00 CEST      12h Thu 2026-10-15 00:00:00 CEST          11h ago dpkg-db-backup.timer           dpkg-db-backup.service
Fri 2026-10-16 00:00:00 CEST      12h Thu 2026-10-15 00:00:00 CEST          11h ago logrotate.timer                logrotate.service
Fri 2026-10-16 02:08:01 CEST      14h Thu 2026-10-15 08:49:43 CEST     2h 45min ago man-db.timer                   man-db.service
Fri 2026-10-16 03:20:02 CEST      15h Thu 2026-10-15 03:23:03 CEST           8h ago qbot-backup.timer              qbot-backup.service
Fri 2026-10-16 08:00:00 CEST      20h Thu 2026-10-15 08:00:01 CEST     3h 35min ago qbot-nutrition-watchdog.timer  qbot-nutrition-watchdog.service
Sat 2026-10-17 22:19:07 CEST   2 days Tue 2026-10-06 16:58:27 CEST 1 week 1 day ago update-notifier-motd.timer     update-notifier-motd.service
Sun 2026-10-18 03:10:41 CEST   2 days Sun 2026-10-11 03:10:11 CEST       4 days ago xfs_scrub_all.timer            xfs_scrub_all.service
Sun 2026-10-18 03:10:52 CEST   2 days Sun 2026-10-11 03:10:46 CEST       4 days ago e2scrub_all.timer              e2scrub_all.service
-                                   - -                                           - apport-autoreport.timer        apport-autoreport.service
-                                   - -                                           - fstrim.timer                   fstrim.service
-                                   - -                                           - fwupd-refresh.timer            fwupd-refresh.service
-                                   - -                                           - snapd.snap-repair.timer        snapd.snap-repair.service
-                                   - -                                           - systemd-sysupdate-reboot.timer systemd-sysupdate-reboot.service
-                                   - -                                           - systemd-sysupdate.timer        systemd-sysupdate.service
-                                   - -                                           - ua-timer.timer                 ua-timer.service

23 timers listed.
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
mcp_server.py:1245  await asyncio.sleep(min(delay, 30))
mcp_server.py:1249  await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
mcp_server.py:1255  await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
qbot_web.py:304  await _asyncio.sleep(_LOGIN_FAIL_DELAY_S)
scripts/audit_inventory.py:76  # harmonogramy w kodzie (APScheduler / petle / godziny)
scripts/audit_inventory.py:78  pat = re.compile(r"(apscheduler|BackgroundScheduler|add_job|on-calendar|OnCalendar|04:45|every\s+15|asyncio\.sleep|sched
scripts/run_wellness_imports.py:7  pojawienia sie danych. Wczesniej readiness liczyl TYLKO daily_job o 04:45 --
qbot3/connectors/import_garmin_sleep.py:4  Runs every 15 min 05:00-09:00.
qbot3/connectors/import_garmin_training.py:4  Runs every 15 min 09:00-23:59.
```

## 3. Zlogi — pliki tymczasowe / kopie / archiwum

### Kandydaci do kasacji (80)
```
_bak_archive/cleanup_20260923fitmodel/form_projection.py.bak.1790183573
_bak_archive/cleanup_20260923qbot3/llm/albert.py.bak.1790193494
_bak_archive/cleanup_20260923qbot3/routes/ride_invite.py.bak.1790181540
_bak_archive/cleanup_20260923qbot3/routes/ride_invite.py.bak.1790194142
_bak_archive/cleanup_20260923qbot3/routes/route_attraction_sources.py.bak.1790177501
_bak_archive/cleanup_20260923qbot3/routes/route_meteo_engine.py.bak.1790152403
_bak_archive/cleanup_20260923qbot3/routes/route_meteo_engine.py.bak.1790160380
_bak_archive/cleanup_20260923qbot3/routes/route_ride_sim.py.bak.1790159359
_bak_archive/cleanup_20260923qbot3/tool_registry.py.bak.1790193494
_bak_archive/cleanup_20260923qbot_web.py.bak.1790152415
_bak_archive/cleanup_20260923qbot_web.py.bak.1790160847
_bak_archive/cleanup_20260923qbot_web.py.bak.1790162822
_bak_archive/cleanup_20260923qbot_web.py.bak.1790164717
_bak_archive/cleanup_20260923qbot_web.py.bak.1790167854
_bak_archive/cleanup_20260923qbot_web.py.bak.1790169367
_bak_archive/cleanup_20260923qbot_web.py.bak.1790174995
_bak_archive/cleanup_20260923qbot_web.py.bak.1790175985
_bak_archive/cleanup_20260923qbot_web.py.bak.1790176387
_bak_archive/cleanup_20260923qbot_web.py.bak.1790177830
_bak_archive/cleanup_20260923qbot_web.py.bak.1790181571
_bak_archive/cleanup_20260923qbot_web.py.bak.1790185554
_bak_archive/cleanup_20260923qbot_web.py.bak.1790191783
_bak_archive/cleanup_20260923qbot_web.py.bak.1790194142
_bak_archive/cleanup_20260923scripts/_tmp_check_1909.py.bak.1789911983
_bak_archive/cleanup_20260923scripts/_tmp_check_1909.py.bak.1789911990
_bak_archive/cleanup_20260923scripts/_tmp_check_1909.py.bak.1789911997
_bak_archive/cleanup_20260923scripts/_tmp_fit_power_probe.py.bak.1790057691
_bak_archive/cleanup_20260923scripts/_tmp_schema_check.py.bak.1789192008
_bak_archive/cleanup_20260923scripts/_tmp_wellness_14d.py.bak.1789192003
_bak_archive/cleanup_20260923scripts/_tmp_wellness_14d.py.bak.1789192017
_bak_archive/cleanup_20260923/opt/qbot/web/public/forma2-data.js.bak.1789906128
_bak_archive/cleanup_20260923/opt/qbot/web/public/forma2-data.js.bak.1789918686
_bak_archive/cleanup_20260923/opt/qbot/web/public/index.html.bak.stats
_bak_archive/cleanup_20260923/opt/qbot/web/public/kalendarz2-data.js.bak.1789906007
_bak_archive/cleanup_20260923/opt/qbot/web/public/kalendarz2-data.js.bak.1789917649
_bak_archive/cleanup_20260923/opt/qbot/web/public/kalendarz2-data.js.bak.1789918840
_bak_archive/cleanup_20260923/opt/qbot/web/public/kalendarz2-data.js.bak.1790090681
_bak_archive/cleanup_20260923/opt/qbot/web/public/kalendarz2-data.js.bak.1790183657
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-gosc.js.bak.1790177876
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-gosc.js.bak.1790181599
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-jazdy.html.bak.1790185623
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-jazdy2-gear.js.bak.1790185888
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-render.js.bak.1790175085
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-render.js.bak.1790176287
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy.html.bak.1790149512
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy.html.bak.1790175131
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2-plan.js.bak.1790177876
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2-plan.js.bak.1790181652
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2-plan.js.bak.1790183920
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2-plan.js.bak.1790184431
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2-plan.js.bak.1790192399
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790176287
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790177875
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790181651
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790183920
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790184227
_bak_archive/cleanup_20260923/opt/qbot/web/public/raport-trasy2.js.bak.1790192399
_bak_archive/cleanup_20260923/opt/qbot/web/public/start2.js.bak.1789904435
_bak_archive/cleanup_20260923/opt/qbot/web/public/start2.js.bak.1789906058
docs/POGODA_OSTRZEZENIE.md.bak.1791988749
mcp_server.py.bak.20261014_163759
mcp_server.py.bak.20261014_164621
qbot3/rides/ride_report_builder.py.bak.20261014171025
qbot3/rides/ride_report_facts.py.bak.20261014171025
qbot_gear_scrape.py.bak.20261013162605
qbot_gear_scrape.py.bak.20261013162934
qbot_pogoda_alert.py.bak.1791988653
qbot_trener_engine.py.bak.20261014164508
qbot_trener_notify.py.bak.20261014164508
qbot_web.py.bak.20261013-201627
qbot_web.py.bak.20261013170138
qbot_web.py.bak.20261013171208
qbot_web.py.bak.20261014171025
qbot_webpush.py.bak.20261013171208
scripts/_tmp_backfill_plan_xss.py.bak.1791987242
scripts/_tmp_check_karoo_live.py.bak.1791988716
scripts/_tmp_patch_tsb_kanon.py.bak.1791990642
telegram_reply_processor.py.bak.20261014155126
tests/test_heat_drift.py.bak.1791998285
tests/test_sleep_target.py.bak.1791995900
```
### archive/ obecny — 35 plikow (przejrzec czy potrzebne)

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
fitmodel/brief.py
claude_funcs_src.py
deploy_ride.py
email_reply_processor.py
email_template.py
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
qbot3/connectors/import_garmin_heart.py
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
qbot_garage_audit_api.py
qbot_garage_mapper.py
qbot_garage_tools.py
qbot_garmin_extra.py
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
qbot_start.py
qbot_task_queue.py
qbot_telegram_tools.py
qbot_time.py
qbot_tool_registry.py
qbot_tools.py
qbot_trend_ai.py
qbot_trener_api.py
qbot_wellness_store.py
qgpt_chat_terminal.py
qlab_replay_export.py
qbot3/connectors/rebuild_garmin_body_measurements.py
reminder_daemon.py
fitmodel/rsrv_v2.py
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
withings_auth.py
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

### Endpointy w qbot_web.py (199)
```
/api/bike-notes/delete
/api/bike-notes/list
/api/bike-notes/save
/api/bike-tasks
/api/bike-tasks/done
/api/bike-tasks/save
/api/bike/bike/delete
/api/bike/bike/save
/api/bike/body/delete
/api/bike/body/save
/api/bike/component/delete
/api/bike/component/save
/api/bike/component/toggle
/api/bike/config
/api/bike/fitting/delete
/api/bike/fitting/save
/api/bike/geometry/save
/api/bike/tire/delete
/api/bike/tire/save
/api/brokul/session
/api/brokul/session/status
/api/calendar
/api/calendar/delete
/api/calendar/edit
/api/calendar/entry
/api/calendar/route
/api/calendar/wx
/api/config/map
/api/equipment/delete
/api/equipment/list
/api/equipment/save
/api/equipment/toggle
/api/forma/activities
/api/forma/activity
/api/forma/analyze
/api/forma/data
/api/forma/ecg
/api/forma/ecg.pdf
/api/forma/ecg/ai
/api/forma/event-prep
/api/forma/heart
/api/forma/heart/report.pdf
/api/forma/season
/api/forma/season/analyze
/api/garage/delete
/api/garage/list
/api/garage/photo
/api/garage/photo/delete
/api/garage/photo/from-url
/api/garage/prefs
/api/garage/ratings
/api/garage/save
/api/garage/scrape
/api/garage/scrape-page
/api/garage/toggle
/api/guest/{token}
/api/guest/{token}/gpx
/api/guest/{token}/rsvp
/api/hammerhead/refresh-token
/api/instructions/delete
/api/instructions/list
/api/instructions/save
/api/instructions/toggle
/api/invites
/api/invites/preview
/api/invites/revoke
/api/invites/send
/api/komoot/session
/api/komoot/session/status
/api/mail-groups
/api/mail-groups/import-rsvp
/api/mail-groups/{group_id}
/api/mail-groups/{group_id}/members
/api/mail-groups/{group_id}/members/{member_id}
/api/mail-groups/{group_id}/sync
/api/modelq2/data
/api/modelq2/recompute
/api/noclegi
/api/notif
/api/notif/dismiss
/api/notif/history
/api/notif/read
/api/nutrition/analyze
/api/nutrition/data
/api/nutrition/day-summary
/api/nutrition/item/delete
/api/nutrition/item/update
/api/nutrition/items
/api/nutrition/preset/apply
/api/nutrition/preset/values
/api/nutrition/status
/api/planer/atrakcja
/api/planer/dodaj-do-qbot
/api/planer/dzien
/api/planer/dzien/gpx
/api/planer/forma-plus
/api/planer/foto/{place_id}
/api/planer/opis
/api/planer/opis-dni
/api/planer/planned-load/recompute
/api/planer/pogoda
/api/planer/termin
/api/planer/tlo
/api/planer/ubior
/api/planer/wykonalnosc
/api/planer/wyposazenie/bags
/api/planer/wyposazenie/garage-add
/api/planer/wyposazenie/garage-options
/api/planer/wyposazenie/generate
/api/planer/wyposazenie/kategorie
/api/planer/wyposazenie/list
/api/planer/wyposazenie/pogoda
/api/planer/wyposazenie/save
/api/planer/wyposazenie/summary
/api/planer/wyposazenie/termin
/api/planer/wyposazenie/zasady
/api/pogoda/charakter
/api/pogoda/dom
/api/pogoda/kwadraty
/api/pogoda/mail
/api/pogoda/mapa/korekta
/api/pogoda/mapa/meta
/api/pogoda/mapa/{layer}/{rid}.png
/api/pogoda/model
/api/pogoda/okno
/api/pogoda/ostrzezenie
/api/pogoda/sprawdzalnosc
/api/pogoda/sprawdzalnosc-radar
/api/pogoda/sprawdzalnosc-szansa
/api/pogoda/warunki
/api/pogoda/weekend
/api/pogoda/weekend/{key}.png
/api/prefs
/api/push/key
/api/push/subscribe
/api/push/test
/api/push/unsubscribe
/api/radar/frame/{fid}.png
/api/radar/meta
/api/radar/punkt
/api/report/attractions/fetch
/api/report/data
/api/report/day-pack
/api/report/day-pack/status
/api/report/day-packs
/api/report/gpx
/api/report/history
/api/report/kit
/api/report/kit/manual
/api/report/mail-recipients
/api/report/outfit
/api/report/outfit/fav
/api/report/outfit/gear
/api/report/outfit/lessons
/api/report/outfit/note
/api/report/plan
/api/report/plan/save
/api/report/push-karoo
/api/report/schedule
/api/report/schedule/{schedule_id}
/api/report/schedule/{schedule_id}/run
/api/report/schedules
/api/report/send-email
/api/report/snapshot/{snapshot_id}
/api/ride-gear/options
/api/ride-gear/save
/api/ride-report/analyze
/api/ride-report/correlate
/api/ride-report/data
/api/ride-report/status
/api/ride-report/tiles
/api/ride-report/w2
/api/rides/ready
/api/route-intro
/api/routes/ready
/api/routes/{route_id}/geometry
/api/routes/{route_id}/segments/candidate
/api/routes/{route_id}/spine
/api/routes/{route_id}/surface-categories
/api/routes/{route_id}/surface-segments
/api/routes/{route_id}/tiles
/api/setup/notif
/api/setup/qext2
/api/stats/rides
/api/wyprawa/pdf
/api/wyprawa/pdf-start
/api/wyprawa/rsvp
/api/wyprawa/rsvp-list
/api/wyprawa/send-email
/brokul-dostep
/g/assets/{name}
/g/{token}
/hammerhead-dostep
/healthz
/kanon
/komoot-dostep
/login
/reports/{fn}
/wyprawa-rsvp
```
### Nieudokumentowane (brak w RAPORT_WEB/FORMA/CONTEXT)
```
/api/bike-notes/delete
/api/bike-notes/list
/api/bike-notes/save
/api/bike-tasks
/api/bike-tasks/done
/api/bike-tasks/save
/api/bike/bike/delete
/api/bike/bike/save
/api/bike/body/delete
/api/bike/body/save
/api/bike/component/delete
/api/bike/component/save
/api/bike/component/toggle
/api/bike/config
/api/bike/fitting/delete
/api/bike/fitting/save
/api/bike/geometry/save
/api/bike/tire/delete
/api/bike/tire/save
/api/brokul/session
/api/brokul/session/status
/api/calendar
/api/calendar/delete
/api/calendar/edit
/api/calendar/entry
/api/calendar/route
/api/calendar/wx
/api/config/map
/api/equipment/delete
/api/equipment/list
/api/equipment/save
/api/equipment/toggle
/api/forma/ecg
/api/forma/ecg.pdf
/api/forma/ecg/ai
/api/forma/event-prep
/api/forma/heart
/api/forma/heart/report.pdf
/api/forma/season
/api/forma/season/analyze
/api/garage/delete
/api/garage/list
/api/garage/photo
/api/garage/photo/delete
/api/garage/photo/from-url
/api/garage/prefs
/api/garage/ratings
/api/garage/save
/api/garage/scrape
/api/garage/scrape-page
/api/garage/toggle
/api/guest/{token}
/api/guest/{token}/gpx
/api/guest/{token}/rsvp
/api/hammerhead/refresh-token
/api/instructions/delete
/api/instructions/list
/api/instructions/save
/api/instructions/toggle
/api/invites
/api/invites/preview
/api/invites/revoke
/api/invites/send
/api/komoot/session
/api/komoot/session/status
/api/mail-groups
/api/mail-groups/import-rsvp
/api/mail-groups/{group_id}
/api/mail-groups/{group_id}/members
/api/mail-groups/{group_id}/members/{member_id}
/api/mail-groups/{group_id}/sync
/api/modelq2/data
/api/modelq2/recompute
/api/noclegi
/api/notif
/api/notif/dismiss
/api/notif/history
/api/notif/read
/api/nutrition/analyze
/api/nutrition/data
/api/nutrition/day-summary
/api/nutrition/item/delete
/api/nutrition/item/update
/api/nutrition/items
/api/nutrition/preset/apply
/api/nutrition/preset/values
/api/nutrition/status
/api/planer/atrakcja
/api/planer/dodaj-do-qbot
/api/planer/dzien
/api/planer/dzien/gpx
/api/planer/forma-plus
/api/planer/foto/{place_id}
/api/planer/opis
/api/planer/opis-dni
/api/planer/planned-load/recompute
/api/planer/pogoda
/api/planer/termin
/api/planer/tlo
/api/planer/ubior
/api/planer/wykonalnosc
/api/planer/wyposazenie/bags
/api/planer/wyposazenie/garage-add
/api/planer/wyposazenie/garage-options
/api/planer/wyposazenie/generate
/api/planer/wyposazenie/kategorie
/api/planer/wyposazenie/list
/api/planer/wyposazenie/pogoda
/api/planer/wyposazenie/save
/api/planer/wyposazenie/summary
/api/planer/wyposazenie/termin
/api/planer/wyposazenie/zasady
/api/pogoda/charakter
/api/pogoda/dom
/api/pogoda/kwadraty
/api/pogoda/mail
/api/pogoda/mapa/korekta
/api/pogoda/mapa/meta
/api/pogoda/mapa/{layer}/{rid}.png
/api/pogoda/model
/api/pogoda/okno
/api/pogoda/ostrzezenie
/api/pogoda/sprawdzalnosc
/api/pogoda/sprawdzalnosc-radar
/api/pogoda/sprawdzalnosc-szansa
/api/pogoda/warunki
/api/pogoda/weekend
/api/pogoda/weekend/{key}.png
/api/push/key
/api/push/subscribe
/api/push/test
/api/push/unsubscribe
/api/radar/frame/{fid}.png
/api/radar/meta
/api/radar/punkt
/api/report/attractions/fetch
/api/report/day-pack
/api/report/day-pack/status
/api/report/day-packs
/api/report/gpx
/api/report/kit
/api/report/kit/manual
/api/report/mail-recipients
/api/report/outfit
/api/report/outfit/fav
/api/report/outfit/gear
/api/report/outfit/lessons
/api/report/outfit/note
/api/report/plan
/api/report/plan/save
/api/report/push-karoo
/api/report/schedule
/api/report/schedule/{schedule_id}
/api/report/schedule/{schedule_id}/run
/api/report/schedules
/api/report/snapshot/{snapshot_id}
/api/ride-gear/options
/api/ride-gear/save
/api/ride-report/analyze
/api/ride-report/status
/api/ride-report/tiles
/api/route-intro
/api/routes/{route_id}/geometry
/api/routes/{route_id}/segments/candidate
/api/routes/{route_id}/spine
/api/routes/{route_id}/surface-categories
/api/routes/{route_id}/surface-segments
/api/setup/notif
/api/setup/qext2
/api/stats/rides
/api/wyprawa/pdf
/api/wyprawa/pdf-start
/api/wyprawa/rsvp
/api/wyprawa/rsvp-list
/api/wyprawa/send-email
/brokul-dostep
/g/assets/{name}
/g/{token}
/hammerhead-dostep
/kanon
/komoot-dostep
/reports/{fn}
/wyprawa-rsvp
```

## 7. Tabele — kod vs schemat bazy

### Tabele qbot_v2.* uzywane w kodzie (201)
```
activity_device, activity_event, activity_fit_raw, activity_lap, activity_record, albert_day_view, app_settings, artifact_status, artifact_type, artifacts, athlete_profile, bak_20261008_, bak_20261008_modelq2_anchor, bak_20261008b_, bak_20261008c_, bak_20261014_, bak_20261014b_, bak_20261014c_, bike_odometer, bike_sensor, blood_pressure, body_circumference, body_daily, body_latest_full_composition, body_latest_weight, body_measurements, body_measurements_backup_20261013, body_measurements_staging, body_trend_full_composition, body_trend_weight, brokul_delivery_days, brokul_meals, brokul_notify, calendar_day_route, calendar_entry, calendar_reminder_fired, change_log, cp_breakthrough, cp_bt_checked, daily_summary, days, ecg_recording, energy_daily, fitmodel_daily, fitmodel_ingest_status, fitmodel_param, fitmodel_qext2_ride, fitmodel_ride_buckets, fitmodel_ride_quarantine, fitmodel_segment, fitmodel_surface_cal, fitmodel_wbal_ride, fitmodel_week_plan, fitmodel_xert_bench, food_analysis, food_catalog, food_day, food_entries, food_items, food_week_ai, fueling_events, garmin_daily_raw, gear_cassette, geo_rev_cache, google_places_cache, google_places_usage, heart_ai, hr_at_power, hr_xss_calib, hydration_events, incident_tickets, intake_items, intake_logs, karoo_live, komoot_seen_tours, load_guard, lthr_daily, lthr_ride, lthr_window, mail_group, mail_group_member, meal_log_items, meal_logs, meal_templates, meteo_point_cache, meter_phys, modelq2_anchor, modelq2_ride, modelq2_signature, modelq2_xert_bench, modelq_guard_log, mutation_type, notif, nutrition_daily_summary, nutrition_day_plan_meals, nutrition_day_plans, outfit_lessons, planer_pogoda_cache, planer_route_opis, planer_route_opis_dni, planer_route_tlo, planned_load_daily, pogoda_alert, pogoda_eps_verif, pogoda_obs, pogoda_prog, pogoda_radar_verif, pogoda_stacja, power_meter_guard, projects, push_sub, qbot_memory, qbot_planning_facts, qbot_sleep_daily, qbot_wellness_daily, qext2_cassette_report, qext2_settings, quality_status, real_load_guard_log, report_mail_recipients, report_schedule, report_schedule_sent, ride_cassette, ride_climb_efforts, ride_companion, ride_drivetrain, ride_frames, ride_heat_drift, ride_hrr, ride_invite, ride_report_ask, ride_report_data, route_admin_cache, route_artifacts, route_attraction_layer, route_attraction_run, route_axis_segments, route_base, route_climb_events, route_day_pack, route_elevation_samples, route_frame_weather, route_frames, route_intro, route_kit, route_landcover_layer, route_outfit, route_outfit_fav, route_parse_results, route_poi_layer, route_poi_meta, route_poi_prefs, route_point_geo_cache, route_precompute_jobs, route_report_snapshots, route_shade_layer, route_stage_lineage, route_surface_context, route_surface_layer, route_surface_profiles, route_surface_segments, route_wind_clim, season_ai, sleep_daily, sleep_wake_label, spo2_daily, strava_activity, strava_auth, strava_gear_map, strava_photo, strava_publish, strava_taste, supplement, supplement_dose, supplement_log, tabela, threshold_sync_log, trainer_, trainer_auto_cache, trainer_change, trainer_day, trainer_exercise, trainer_exercise_user, trainer_goal, trainer_notify_log, trainer_rating, trainer_rule, trainer_session, trainer_settings, trainer_workout, training_sessions, trip_story, ui_prefs, wbal_feel, web_device_auth_requests, web_sessions, wellness_daily, worldcover_classes, wyprawa_report, wyprawa_rsvp, xert_profile_snapshots
```
### Kod odwoluje sie do tabel NIEISTNIEJACYCH w bazie (POWAZNE)
```
artifact_status
artifact_type
bak_20261008_
bak_20261008b_
bak_20261008c_
bak_20261014_
bak_20261014b_
bak_20261014c_
modelq_guard_log
mutation_type
quality_status
tabela
trainer_
```
### Tabele w bazie nieuzywane w kodzie (41 — moga byc sieroty lub uzywane z SQL/dashboardow)
```
bak_20260928_fitmodel_daily, bak_20260928_modelq2_ride, bak_20260928_modelq2_signature, bak_20261008_fitmodel_daily, bak_20261008_modelq2_ride, bak_20261008_modelq2_signature, bak_20261008b_fitmodel_daily, bak_20261008b_fitmodel_ride_quarantine, bak_20261008b_modelq2_ride, bak_20261008b_modelq2_signature, bak_20261008c_fitmodel_daily, bak_20261008c_modelq2_ride, bak_20261008c_modelq2_signature, bak_20261014_fitmodel_daily, bak_20261014_modelq2_anchor, bak_20261014_modelq2_ride, bak_20261014_modelq2_signature, bak_20261014b_fitmodel_daily, bak_20261014b_modelq2_ride, bak_20261014b_modelq2_signature, bak_20261014c_fitmodel_daily, bak_20261014c_modelq2_ride, bak_20261014c_modelq2_signature, body_daily_backup_20260531_2002, fitmodel_daily_v1_backup, fitmodel_ingest_status_bak_20261004, fitmodel_segment_bak_20260707, fitmodel_segment_bak_20261004, fitmodel_wbal_ride_v1_backup, garmin_workout_write_audit, qbot_artifacts, qbot_doc_write_audit, qbot_import_runs, qbot_nutrition_daily, qbot_plans, qbot_wellness_notes, ride_report_data_v1_backup, route_analysis_run, start_trip, tool_calls, trainer_lab
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
qbot_dashboard.py
mcp_server.py
qbot_web.py
qbot_context_resolver.py
qbot_query_router.py
qbot_report_tools.py
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
scripts/mq2_add_anchor_20261014.py
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
fitmodel/tp_recheck.py
fitmodel/ingest_qext2_fit.py
fitmodel/modelq_guard.py
fitmodel/buckets.py
fitmodel/daily_job.py
fitmodel/ftp_resolver.py
fitmodel/modelq2/publish.py
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

tests/test_pogoda_conditions.py::Warunki::test_godziny_z_poprzedniej_godziny
tests/test_pogoda_conditions.py::Warunki::test_komplet_pol
  /opt/qbot/app/qbot_wbgt_tools.py:80: RuntimeWarning: invalid value encountered in sqrt
    return 2.6693e-6 * np.sqrt(M_AIR * tk) / (sigma * sigma * omega)

tests/test_pogoda_conditions.py::Warunki::test_godziny_z_poprzedniej_godziny
tests/test_pogoda_conditions.py::Warunki::test_komplet_pol
  /opt/qbot/app/qbot_wbgt_tools.py:99: RuntimeWarning: invalid value encountered in scalar power
    return a * (tk / tcrit12) ** b * pcrit13 * tcrit512 * mmix / patm * 1e-4

tests/test_pogoda_conditions.py::Warunki::test_godziny_z_poprzedniej_godziny
tests/test_pogoda_conditions.py::Warunki::test_komplet_pol
  /opt/qbot/app/qbot_wbgt_tools.py:67: RuntimeWarning: overflow encountered in exp
    return 1.004 * 6.1121 * np.exp(17.502 * y)

tests/test_pogoda_conditions.py::Warunki::test_godziny_z_poprzedniej_godziny
tests/test_pogoda_conditions.py::Warunki::test_komplet_pol
  /opt/qbot/app/qbot_wbgt_tools.py:178: RuntimeWarning: invalid value encountered in scalar divide
    - _evap(tref) / RATIO * (ewick - eair) / (pair - ewick) * (PR / sc) ** 0.56

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_route_gpx_not_modified_by_enriched_gpx
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_route_with_selected_poi_gpx_has_track_and_wpt
FAILED scripts/test_route_logistics_commit_poi_gpx_wpt.py::TestCommitPoiGpxWpt::test_selected_poi_output_files
FAILED scripts/test_rwgps_export_artifact_store_registration.py::test_export_and_registration
FAILED tests/test_capability_fallback.py::test_capability_fallback_daily_report_status
FAILED tests/test_heart_ai.py::Laczna::test_fakty_bez_szeregow - AssertionErr...
FAILED tests/test_meter_physics.py::Physics::test_luggage - AssertionError: 1...
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_query_b
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_query_c
FAILED tests/test_report_validation.py::TestArtifactSearchRouting::test_handle_artifact_search_returns_envelope
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_google_supply_status_is_separate_from_overpass_completeness
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_overpass_fallback_used_when_google_empty
FAILED tests/test_route_poi_google_primary.py::TestRoutePoiGooglePrimary::test_partial_chunk_reports_reason
FAILED tests/test_tz_display.py::TestNoUtcForUser::test_js_no_utc_today_or_label
ERROR qbot3/capabilities/test_harness.py::test_capability
ERROR scripts/test_gpx_artifact_geometry_readout.py::test_dump_summary
14 failed, 1006 passed, 18 skipped, 18242 warnings, 2 errors in 98.22s (0:01:38)
```

## 10. Git — stan i tydzien commitow

### git status --short
```
M  docs/GARMIN_DANE.md
A  docs/MODELQ.md
M  docs/MODELQ_PRZEGLAD.md
M  docs/TODO.md
 M fitmodel/daily_job.py
M  fitmodel/meter_physics.py
M  fitmodel/modelq2/publish.py
A  fitmodel/modelq_guard.py
M  fitmodel/vo2max.py
M  qbot3/rides/ride_report_builder.py
M  qbot_web.py
 M scripts/audit_inventory.py
?? config/speed_model_candidate.json
?? scripts/_pogoda_punkt_viz.js
?? scripts/cleanup_bak.py
?? tests/test_modelq_guard.py
```
### Commity z 7 dni
```
b03483f ModelQ: pytanie o odczucie po jezdzie z niskim zapasem (wbal_feel, Telegram wf:), krok w daily_job; test_wbal_feel 4; LTHR 148 w DECISIONS
29eb4d8 ModelQ: regula TP 0,45 W/CTL z CTL sprzed 14 dni (r2 0,85, test vs Xert >90 dni MAE 7,9->3,6 W); przeliczone 358 jazd; LTHR 151->148 skutek uboczny
f6bc6df ModelQ: wlasna kotwica 14.10 (TP 238,8 / HIE 20,0 / PP 988,8) + czulosc HIE 0,11 (+-10%) z rocznych danych; test 4 jazd W'bal 6-9%; MODELQ_PRZEGLAD etap 1-3
f7d5769 Kalendarz: ocena planu 1-5 + komentarz w oknie treningu (zniknela 08.10 przy zastapieniu widoku Tydzien; backend /api/trener/rating bez zmian)
4c39962 E4.5: ostatnie wlasne pobieranie Open-Meteo na wspolny transport -- Okno jazdy (slonce), ride_verdict (+ poprawka godziny opadu), mcp_server (get_weather, cisnienie) przez qbot_wx
bf271d0 E4.4: ostatnie sciezki Open-Meteo na wspolny transport qbot_wx -- WBGT (zgodnosc identyczna), gear_kit, sprawdzalnosc (tylko Open-Meteo), archiwum opadu w qbot_web; jeden silnik pogody we wszystkich modulach
3af4b8f E4.3: koniec OpenWeatherMap -- route_weather (Planer Wyposazenie, pogoda per pudelko) i feasibility na wspolnym silniku; poprawka godziny opadu w route_weather._fetch_open_meteo (tez raport z jazdy); klucz OWM z konfiguracji; opisy bez OWM; ostatni test OWM usuniety
c9ea379 E4.2: stare narzedzia pogody (current, daily_report/forecast, config_status) na wspolnym silniku -- te same pola, bez OpenWeatherMap; usuniety martwy daily_report.py + adapter (artefakt z poczatkow QBota); testy OWM -> testy formatu na rdzeniu
6bbb0e0 E4.2: Albert weather_forecast ('pogoda w miescie X') na wspolnym silniku (geokodowanie + Warunki, odczuwalna, na rowerze, szansa z zespolu, droga, charakter dnia) zamiast OpenWeatherMap + wpis w _SYSTEM; usuniety martwy event_morning_report.py
01ff325 E4.1: Trener na wspolnym silniku -- forecast (plan, powiadomienia) i hourly (poranna korekta) z rdzenia Pogody; jedna funkcja odczucia odczucie_calc; progi z historii jazd nowa odczuwalna (370 jazd: chlod -1, upal 33); Okno jazdy na nowej odczuwalnej; pokrywa sniegu w warunkach
30d79cf Test silnika tras: warunki drogi (road_flags, alerty oblodzenie/mgla/bloto, brak widocznosci != mgla)
57daf66 E3.2: warunki drogi (oblodzenie, mgla, bloto) i charakter dnia w silniku tras -- jedna funkcja regul road_flags dla Pogody i tras, alerty w formacie deszczu/burzy (Analiza trasy, Planer, Albert); cache e3c
876c50e GARMIN-DANE 7b: wspolny silnik oceny upalu heat_advice() (prognoza >=60 min >=25 C lub klimat tmax >=25 C; aklimatyzacja + rada); test_heat_drift 10; podpiecie w 3 miejscach czeka na silnik POGODY
96ec1bc E3.1 poprawka: 'odczuwalna' w Pogodzie = ten sam wzor co na trasie (Steadman + slonce przez Tmrt, per_segment.feels); UTCI w jezdzie jako osobne pole (na trasie tylko do flag zimna)
1d15ed5 E3.1: odczucie dla punktu jak w silniku tras -- UTCI w jezdzie (bilans slonca + ped), 'na rowerze' (kalibracja Karoo + osobista), WBGT; Warunki: strefy ubioru wg 'na rowerze'; Okno jazdy porownuje progi Trenera z dawna odczuwalna (odcz_om)
6532c57 Silnik tras: wielkosci, ktorych model kanoniczny nie podaje (HARMONIE: cisnienie, CAPE, szansa), uzupelniane z best_match -- WBGT wychodzil NaN na calej trasie i burze byly niewykrywalne (takze w Planerze); opis uzupelnien w polu model; cache e3b
c28befc E3: jedna regula modelu w silniku tras -- bez modelu kanon zamiast best_match (Analiza = Planer = Albert = raport z jazdy); w PL na 1-3 dni temp/wiatr/porywy/opad wg sprawdzalnosci, szansa opadu z zespolu ICON-EU-EPS; opis zrodla kazdej wielkosci w polu model
1348cc3 GARMIN-DANE etap 7: dryf tetna (pasmo 0,55-0,92 CP) + czas >25 C na jazdach >1,5 h -- raport jazdy (kafel tetno, v=49), Trendy pigulka Dryf (v=66), cache ride_heat_drift + backfill; test_heat_drift 6; TODO 7b
0dd67a2 E1/E2: wspolny transport Open-Meteo qbot_wx.get_url (cache, tylko adresy Open-Meteo) -- silnik tras (prognoza, 6 modeli, klimat ERA5, klimat wiatru) i Trener (plan, poranna korekta, kalibracja) przepiete bez zmiany parametrow; zgodnosc przed/po identyczna
5d73dba E1 cz.1: rdzen danych pogodowych qbot_wx (klient Open-Meteo + cache + PREV_HOUR/next_hour + szansa z zespolu); Pogoda i Okno jazdy pobieraja przez rdzen; zgodnosc przed/po identyczna
aac9b50 Pogoda NAPRAWA: pola kier/skad (kierunek wiatru) wyciete przez komentarz w E0 5eafccb; test regresyjny conditions_point (komplet pol + godziny opadu/porywow/sniegu, bez sieci)
ec95e21 Trener plan_week: notka 'gotowosc dzis < prog' tylko gdy minimum wynika z gotowosci (przy minimum z sygnalow Sezonu rt bywa puste -> TypeError round(None) wywracal plan); test_regen_not_ok_cuts_today przechodzi
72f6025 GARMIN-DANE etap 5: wlasny cel snu (baza z danych 7:45 + dodatki) w wiadomosci 20:00, przycisk Pobudka przed budzikiem (sleep_wake_label), sen tygodnia i miesieczna analiza pobudek w rozliczeniu; test_sleep_target 9; TODO 5b
46f5636 E0 Trener: opad, szansa opadu, porywy i kod pogody z wlasciwej godziny (Open-Meteo = poprzedzajaca godzina) w forecast (plan + powiadomienia), window_wx (poranna korekta) i weather_auto (kalibracja progow) -- wczesniej o 1 h za wczesnie; test propozycji poprawiony (zakladal bledne przypisanie godzin)
6113a70 web_mirror: ikony i manifest aplikacji na telefon w lustrze (KEEP_ROOT) - wczesniej wypadaly; usuniety jednorazowy skrypt _tmp_validate_kind (archiwum scripts_tmp_2026-10-14)
0a2c3d0 Kalendarz: pominiete treningi tylko w panelu dnia (sekcja Pominiete), nie w siatce (praca z 13.10)
6543ad8 Przelom CP z krzywej moc-czas -> pytanie na Telegramie (wariant B): cp_breakthrough, krok w daily_job i run_after_ride, potwierdzenie/odrzucenie w qcal_telegram, testy 5 (praca z 08.10)
2b91f73 Swiezosc/zmeczenie: jeden kanon = faktyczne (atl_real/tsb_real, treningi + stan ciala) w raporcie jazdy, Starcie, Formie, Albercie, prognozie, Sezonie i wyprawach; raport pokazuje rozbicie trening + cialo
846f47a E0: silnik tras -- opad/szansa/porywy z godziny, w ktora wypada przejazd (_interval), bez interpolacji po srodkach (rozmazywala deszcz 30 min przed poczatkiem)
5eafccb E0 jeden silnik pogody: poprawka godzin opadu, szansy opadu i porywow (Open-Meteo = poprzedzajaca godzina) w silniku tras (opad ~30 min za wczesnie) i porywow w Pogodzie; spis 6 sciezek pogodowych i plan E1-E4 (docs/POGODA_SILNIK.md)
59963db Pogoda: panel U Ciebie o 30% szerszy (330 -> 430 px)
c669973 Trener: (1) sila - zamiana cwiczen / nowy zestaw / ocena AI (praca z 09.10); (2) obciazenie planu po zmianie/dodaniu sesji, AI zmienia rodzaj treningu, zapas xss w silniku i raporcie jazdy; (3) przelicznik obciazenia roweru uczony co noc z jazd ModelQ (k=1,27)
f6e5a64 Deszcz: sygnal z Karoo przez POST /ride-readiness {ping:{lat,lon}} zamiast /qext2/ping (publiczny most przepuszcza tylko znane sciezki, 404)
5128a31 GARMIN-DANE etap 6: walidacja ModelQ vs obciazenie Garmina (norma ln(G/X)~ln(h), rozbieznosc >1.5 SD) w raporcie jazdy (kafel obciazenie, v=47) i tygodniowym rozliczeniu Trenera; test_garmin_load_check 6; TODO 6b
48367b5 Deszcz: sygnal jazdy z Karoo (POST /qext2/ping) -> radar w miejscu jazdy; jazda z Karoo przed planem Trenera; Telegram tylko 1. ostrzezenie na jazde; kasowanie pozycji po wczytaniu pliku jazdy / 24 h; testy test_karoo_live 6
270b770 Pogoda Warunki: kolejne dni (dzis + 4, godz. 06-22) z pewnoscia ze sprawdzalnosci (wysoka / srednia / orientacyjna); linki 'warunki tego dnia' z Okna jazdy i Gdzie jechac; /api/pogoda/warunki?dzien=
9fe93f8 GARMIN-DANE etap 4: temp. skory + sygnal Organizm pod obciazeniem (temp>=+0,4 + HRV-5/RHR+3) w karcie snu, punktach Serca i porannej wiadomosci; test_body_signal 8; TODO
c38aec5 Pogoda: mapa centruje sie na POZYCJI PROGNOZY (strzalka) w odslonietej czesci -- panel, resize, Wysrodkuj, start, wybor rejonu weekendu
6f4d511 Pogoda: centrowanie mapy po faktycznym koncu animacji panelu (zwijanie/przelaczanie uciekalo o ~80 px)
7a5b3f6 Pogoda: mapa centruje sie na widocznej czesci przy otwarciu/zwinieciu panelu i zmianie rozmiaru okna; panel Warunkow szerszy (do 80% ekranu, 1200 px); weekend dopasowuje widok do odslonietej czesci mapy
87aa28c Trener: (1) sila - zamiana cwiczen / nowy zestaw / ocena zestawu AI (swap w prosbie do AI, /sessions/{id}/workout, cofanie) - praca z 09.10; (2) planowane obciazenie po zmianie/dodaniu sesji (AI i recznie), AI zmienia rodzaj treningu, zapas xss w silniku i raporcie jazdy
56a2966 Pogoda Warunki: wizualizacja w stylu Analizy trasy (kafelki, niebo, temp+odczuwalna na strefach ubioru, szansa deszczu, strzalki wiatru, ryzyka drogi); NAPRAWA: przywrocone pole wiatr w conditions_point (wyciete przez komentarz w b8ba5d4); + chmury/dzien/szansa
baf7937 GARMIN-DANE etap 3: status HRV QBota (7 nocy vs norma 60 nocy +-0.5 SD, 4 statusy) w Zdrowie-Serce: pas normy, naglowek, karta snu, regula cisnienie-regeneracja; test_hrv_status 6; TODO etap 3b
841ded1 Pogoda: charakter dnia (przelotne / burzowe / stabilnie) z CAPE + lifted index -- chip w panelu U Ciebie (dzis/jutro), linia u Alberta; /api/pogoda/charakter; progi skalibrowane na ulewie 14.10
7f9c6ad GARMIN-DANE etap 2: VO2max QBota z krzywej ModelQ (P5=CP+W/300, ACSM, na kg) w /api/forma/data + Trendy pigulka VO2max (forma2-data.js v=64); test_vo2max 5; TODO: backfill etapu 1 zrobiony
17985d9 Pogoda pasek: 1. godzina modelu nie dubluje pozycji konca prognozy radaru (byla nieosiagalna -- skok 17:00 -> 19:00); strzalki <- -> o 1 krok
2018e6f Strava: jazda bez czujnikow (restart Karoo) -> pytanie o rower na Telegramie (sb:<rower>:<id>), classify_bike + testy; nie zgadujemy Monstera
27b7b9f Pogoda: ostrzezenie o deszczu w czasie jazdy z Trenera -- radar (do 60 min: godzina, sila, czas trwania) + szansa z zespolu dla dalszej czesci jazdy; dzwonek (zrodlo radar) + Telegram + pasek na Pogodzie; max 3 na jazde; /api/pogoda/ostrzezenie
4616a8a Okno jazdy: ostrzejsza kara za szanse opadu (>= 40%: x6, 20-40%: x2) -- 75% szansy = ok. 55/100 zamiast 85 (przypadek 14.10)
921b4b3 GARMIN-DANE etap 1: pelne dane snu/HRV z Garmina (garmin_daily_raw) + temp. skory, potrzeba snu, status/norma HRV; backfill wznawialny; test_garmin_extra 5
b8ba5d4 Pogoda: poprawka godziny opadu z Open-Meteo (wartosc o T = godzina przed T) w model_point, conditions_point i szansie Okna jazdy -- deszcz wychodzil o 1 h za wczesnie (przypadek 14.10: start 14:30 dostal 8% zamiast 75%)
bd1471c UI: tokeny kolorow ui2 wydzielone do ui2-tokens.css (jedno zrodlo, import w ui2.css); Pogoda w palecie ui2 (bez theme.css, kolory danych z tokenow, jasny/ciemny), ocena weekendu w barwach ui2; regula w docs/UI_PALETA.md: nowe strony tylko w palecie ui2
60984b3 Router: pytania o pogode / przesuniecie jazdy / gdzie jechac -> Albert (intencja pogoda w OPEN_DOMAIN_INTENTS, przed garazem -- 'jazde na rowerze' trafialo do garage_status); zweryfikowane na zywo qbot_query
2f4626b Albert: narzedzia pogody weather_now, ride_window, ride_where, weather_skill (tylko odczyt, modul Pogoda) + wpis w _SYSTEM (kiedy ktore; radar do ~1 h; pogoda trasy nadal route_day_plan/route_report)
4c60257 Pogoda: sprawdzalnosc szansy opadu z zespolu vs radar -- co godzine, krzywa wiarygodnosci i BSS wg wyprzedzenia; archiwum szans 3 doby; /api/pogoda/sprawdzalnosc-szansa; sekcja w Sprawdzalnosci
c802190 Pogoda weekend: wybrany rejon podswietlony na pomaranczowo (tylko jego okrag zasiegu), slabsza warstwa ocen, radar ukryty w panelu, wieksze odstepy etykiet, osobny link 'ustaw tu prognoze'
0fb7671 Pogoda weekend: przy podobnej pogodzie blizsze miejsce wygrywa (kara 3 pkt / 100 km od pozycji)
e3ead6c Pogoda weekend: limit odleglosci (50-250 km / bez limitu) od pozycji prognozy, rekomendowane miejsca na mapie (etykiety) z okregiem zasiegu podobnej pogody i okregiem limitu; PM.rejony()
4c256da Pogoda krok 3: Gdzie jechac (weekend) -- ocena 0-100 miejsc w PL w oknie Trenera, mapa ocen, najlepsze rejony (GeoNames, polskie nazwy) wg oceny i odleglosci; mapa modelu do +120 h; szansa z zespolu tylko do +60 h; /api/pogoda/weekend
0e854ac Pogoda: pasek czasu o stalej dlugosci w pikselach -- opis i legenda o stalej szerokosci (dluzszy opis prognozy kurczyl pasek i przesuwal podzial)
10914e1 Pogoda: staly pasek czasu -- czesci o stalej szerokosci (radar 28% | radar +1 h 12% | prognoza 60%), pozycja proporcjonalna do czasu, czesci bez danych wyszarzone, kreski dni w prognozie, legenda zgodna z widokiem
bbd0189 Pogoda krok 2: Okno jazdy -- starty co 30 min w oknach Trenera (bez zajetosci), pogoda wg sprawdzalnosci + szansa z zespolu + radar na najblizsza godzine, progi Trenera, ocena 0-100, karty plan/wczesniej/pozniej, siatka startow; /api/pogoda/okno
9e0a8c5 Pogoda: po radarze mapa SZANSY opadu z zespolu ICON-EU-EPS (40 wariantow, >= 0,2 mm/h) zamiast deterministycznego opadu; os nie resetuje wybranej chwili przy dociaganiu klatek; ostrzezenie o rozjezdzie model-radar
69a3e32 Pogoda: spojnosc radar -> model -- przebiegi ICON-EU co 6 h, opad modelu w skali radaru, korekta polozenia wg aktualnego radaru z bezpiecznikiem (tylko gdy zgodnosc rosnie), plynne przejscie 2 h; /api/pogoda/mapa/korekta
96d1567 Pogoda: sprawdzalnosc radaru (etap 2) -- przy kazdej klatce prognozy 10-120 min vs to, co radar pokazal, ~1000 punktow nad PL, CSI vs bez przesuwania; pole ruchu per klatka; horyzont osi radaru z wynikow (dzis 60 min); /api/pogoda/sprawdzalnosc-radar
201bfad Pogoda: mapy modelu ICON-EU (DWD) do +60 h -- opad, temperatura, wiatr, porywy, mgla (przybl.), oblodzenie; generowanie w tle (przebiegi 00/12 UTC, podproces nice 15, ~2,6 min); /api/pogoda/mapa/*; dolne zakladki, os Opadu radar -> radar +2 h -> model. eccodes w venv
d99db04 Pogoda: automatyczny przydzial modeli wg sprawdzalnosci -- build_stats raz na dobe (per stacja x model x wyprzedzenie), przydzial(lat,lon): najmniejszy blad u Ciebie (<=100 km) albo wg Polski; warunki punktu i os opadu z przydzielonych modeli; notka Modele na stronie
201e78a Pogoda sprawdzalnosc: aliasy kolumn w score (kursor qbot-web = slowniki, zdublowane nazwy -> 500)
2d192a8 Pogoda: sprawdzalnosc modeli (etap 1) -- 61 stacji synop IMGW (archiwum + API co godzine) vs prognozy 1-3 doby wczesniej (Open-Meteo Previous Runs: HARMONIE DMI/KNMI, ICON-EU, ECMWF, GFS); MAE/bias temp/wiatr/porywy, opad 6 h trafione/falszywe/przegapione; widok u Ciebie (100 km, waga odleglosci) / Polska; petla w tle qbot-web; /api/pogoda/sprawdzalnosc; zakladka na stronie. docs/POGODA_SPRAWDZALNOSC.md
36ee696 Pogoda: radar mocniejsze kolory z przezroczystoscia (60/85%), bez przygaszania podkladu (podklad w wersji QBota); przycisk Radar: mocny/delikatny
e6de871 Pogoda: warunki dla roweru w punkcie (temp/odczuwalna, wiatr/porywy m/s, mgla, oblodzenie, nawierzchnia, rosa; teraz, 12 h, paski 24 h w zakladce Warunki; wykres temperatura i wiatr), standardowe menu mapy (Wysrodkuj/Mapa/Kwadraty/Radar wyrazny), kwadraty StatsHunters w widoku, czytelniejszy radar (wlasna warstwa, przygaszony podklad). /api/pogoda/warunki|kwadraty
e11b8b1 Pogoda: menu glowne (nav.css), dolny pasek rozciagany uchwytem (wykres osi punktu po rozciagnieciu), lewy panel do dolnego paska, prognoza radaru na mapie do +120 min (2. godzina orientacyjnie), przycisk podkladu kolor/szara/ciemna/czarna
63f79e9 Menu: Pogoda w produkcyjnym (po Analizie trasy) -> /pogoda.html. Dok.: docs/POGODA_RADAR.md
5288d92 Pogoda krok 1: strona pogoda.html (mapa + lewy panel + dolny pasek, radar 2 h + prognoza radaru do 60 min na mapie, pozycja dom/przegladarka/klik, os punktu radar->model ICON z ostrzezeniem o rozjezdzie); /api/pogoda/dom|model (qbot_pogoda.py, Open-Meteo icon_seamless); przecinki w werdykcie radaru; mockup krokow 1-4. docs/POGODA_RADAR.md
5873ee5 Trendy: dymek jazdy z km, czasem i przewyzszeniem (suma dnia, /api/jedzenie/rides_day)
4fae50e Trendy: odpoczynek HR (HRR60) zolty - odroznia sie od wagi z bilansu (turkus)
35f3644 Trendy: jazdy rozowe z wielkoscia kropki wg obciazenia (XSS), odpoczynek HR (HRR60) cyjan - odroznia sie od wagi
dfeee16 Pogoda krok 1: radar opadu EUMETNET OPERA (co 5 min, 1 km, 10 radarow IMGW, CC BY 4.0) -- qbot_radar.py: petla w tle qbot-web (2 h klatek + PNG pod mape), ruch opadu (korelacja kafelkow + filtr zgodnosci, zgodny z wiatrem 700 hPa), prognoza punktowa 0-120 min + werdykt; /api/radar/meta|frame|punkt. Testy test_radar 5. docs/POGODA_RADAR.md
58b6353 HRR60: tetno odpoczynku po akcentach liczone automatycznie z FIT (qbot_hrr.py, ride_hrr, rok wstecz), Serce/Trendy/Analiza AI; seria cisnienia + tryb kontrolny z EKG; prognoza spalania odporna na opoznione dane Garmina
d434754 Wlasny zakres dat obok gotowych okresow: range-custom.js; Trendy, Sezon, Serce; ModelQ Zastosuj odznacza gotowy okres
fd16d3e Waga: cala historia z Garmina (379 dni od 2017, bylo 51) + fitmodel_daily tylko puste dni (maks. 14 dni od pomiaru); wykres Trendy: punkty pomiarow + przerywana linia (weight_meas w /api/forma/data)
187f68a Powiadomienia: wyglad + QBot jako aplikacja (Safari Dodaj do Docka -> ikona i nazwa QBot w powiadomieniach): manifest.webmanifest + ikony z favicon.svg, linki wstrzykiwane przez nav.js, publiczne w bramce; tytuly bez emoji
d696e7e Powiadomienia dzwonka na komputerze (Web Push): stan na zywo liczony w tle co 60 s (petla w qbot-web, wczesniej tylko przy otwarciu dzwonka), nowe/zmienione pozycje -> powiadomienia systemowe Safari/Chrome; qbot_webpush.py (push_sub, notif.pushed_at, VAPID poza repo, slad webpush.tick), sw-push.js, SETUP > Powiadomienia Wlacz/Test/Wylacz, /api/push/*. Testy test_webpush 5. iPhone = TODO [WEBPUSH-IPHONE]
c678657 Zakupy Szukaj ceny: slowa zmieniajace produkt (Quarq/PM, zestaw, uzywany...) na stronie, a nie w pozycji -> inny produkt. Testy 7
eafe105 Zakupy Szukaj ceny - bledne oferty: Ceneo tylko oferty tego produktu (data-productid) + link do oferty sklepu; kody z cyframi (CH012, E1) i wariant z notatki (160mm) obowiazkowe, wariant do AI. Testy 7
921b937 Zakupy: naprawa Szukaj ceny - brak uprawnien do logu nie blokuje startu (bylo 500 + status utkniety w running -> 409), blad startu cofa status; przegladarka Playwright dla uzytkownika qbot
c3ee903 Zakupy: etap 4 (Gmail) odrzucony - zakupy potwierdzane recznie; ryzyka i ewentualne bezpieczne warianty w docs
249889a Zakupy: glowne zdjecie pobiera przegladarka (zakladka 'Dodaj do QBota') -> kopia w gear/shop; CDN Allegro nie odpowiada serwerowi. _fetch_image czyta kopie z dysku (miniatura przy zapisie), obrazki z naglowkami przegladarki. Testy 7.
35ddb9e Zakupy etap 3: Szukaj ceny - AI web_search + Ceneo (przegladarka) + Twoj link; kazda cena sprawdzona na stronie sklepu (przegladarka przy blokadzie), zgodnosc wariantu (liczby, rdzen nazwy, EAN), NBP, do 5 ofert + niesprawdzone osobno, wybierz, historia, Dzwonek. Worker w tle. Testy test_zakupy_ceny 6
8cc9cc2 Zakupy: przycisk w przegladarce 'Dodaj do QBota' (Safari/Chrome, Mac/iPhone) dla sklepow blokujacych serwer (Allegro 403): qbot-dodaj.html + /api/garage/scrape-page (ten sam potok co Pobierz dane) + JSON-LD ImageObject. Testy 5 + E2E.
82e2670 Zakupy etap 2: zapas rzeczy zuzywalnych (opakowanie + zuzycie reczne albo z Zdrowie > Suplementy), Dzwonek live:zakupy, linia + przyciski w porannej wiadomosci (zk:r Kup ponownie, zk:z +7 dni). Testy test_zakupy 9
01dc6c7 Suplementy: wplyw na noc (wziete vs pominiete: sen, HRV, tetno, SpO2; d Cohena) + Albert supplements (odczyt) z promptem. Testy 8.
7ce3047 Odziez: uzupelnienie zima 2025 - rozdzial 11 w OUTFIT_ADVISOR_RULES + skrypt notatek Garazu (Castelli 2nd Layer id 250)
c828dd9 Garaz: zakladka Zakupy (etap 1) - lista Do kupienia z priorytetem i Kupione, dodawanie z linku (garage scrape), propozycja dodania do Garazu po zakupie. shop_items w garage.db, /api/zakupy. Testy test_zakupy 4
e9b3a52 Suplementy i leki: lista z wersjami dawek, potwierdzenie rano za wczoraj (tr:supl, 'Wszystkie'), Zdrowie > Suplementy (edycja, kalendarz przyjec, regularnosc), lista w raporcie dla lekarza. Testy test_supplements 4.
7734865 Dzwonek: Okno 10-20 do potwierdzenia i Zamknij dzien (wczoraj do 12:00, dzis od 19:30) z akcja jednym kliknieciem i linkiem do dnia; Telegram: przycisk Okno OK
287a48b Poranna wiadomosc: potwierdzenie wczorajszego okna 10-20 (linia + przyciski Dotrzymane/Zlamane), tylko gdy niepotwierdzone i niezwolnione
efdb5b4 Serce: 3 zdania lacznej analizy AI na gorze zakladki (fakty QBota, pamiec po hashu). Testy test_heart_ai 5.
a8ef825 Mini kalendarz (qpicker.js, wspolny): klik w nazwe miesiaca w Trening -> Kalendarz oraz w zakres tygodnia w Zdrowie -> Analiza i Brokul; widok dni i 12 miesiecy z przewijaniem lat, Dzis, Esc
405936b Serce: wykres saturacji nocnej (najnizsza, trend 7 nocy, srednia we snie/doby, prog 90%; historia od 04.2026) + klikalne etykiety wykresow jak w Trendach (pamietane)
b8e37de Alkohol: rozpoznanie z pozycji wpisow (bez piwa 0%/bezalkoholowego), noc po alkoholu wylaczona z analiz AI, znacznik na wykresach, linia rano, koszt wieczoru w Serce
73eee57 Serce: cisnienie a regeneracja (reguly), cialo (waga, BMI, talia/wzrost), sen i SpO2 nocne (najnizsza, spo2_daily); raport dla lekarza strona 2 + pola badan. Testy test_heart 11.
c52d0b0 Serce AI: komentarz kontekstowy do EKG (sen, trening, cisnienie; tylko gdy cos odstaje) + raport dla lekarza PDF po serii (podsumowanie AI na faktach QBota, tabele, strony EKG). qbot_v2.heart_ai. Testy test_heart_ai 4.
3f9baed EKG: interpretacja wyniku (rytm, niemiarowosc oddechowa, HRV na tle nagran z tej samej pory, cisnienie z sesji, jakosc) na stronie i w PDF. Testy test_ecg 10.
7783fde EKG: przebieg z Garmina (GHS 128 Hz), analiza uderzen qbot_ecg (RR, HRV RMSSD/SDNN/pNN50, przedwczesne/przerwy, ksztalt osobno), wykres interaktywny w Zdrowie > Serce, PDF do pobrania (/api/forma/ecg.pdf). Testy test_ecg 5.
f65f3de Zdrowie > Serce: cisnienie (kazdy pomiar w dymku, srednia dnia, progi 135/85) i znaczniki EKG na wykresie; interaktywnosc jak w Trendach (zoom przeciagnieciem, dwuklik/Pokaz calosc, wspolny kursor i dymki na obu wykresach)
6b1e793 Trendy AI v3: obciazenie tylko treningowe, fizjologia tylko kolejne noce (lag 1-3), HRV rano->jazda jako zachowanie, bez efektu dnia tygodnia, pewnosc z n/p liczona przez QBota (AI nie zmienia), okno <28 dni orientacyjnie, zakaz wymyslonych mechanizmow
8ec4a51 Trendy AI: srodek - 3-4 odkrycia z liczbami i mechanizmem, ~280 slow
cf64607 TRENER: poranna propozycja korekty jazdy z uwagi na pogode (okno jazdy, wx.fallback, Zmien/Zostaw + Cofnij; reczne = ostrzezenie). Testy test_trener_weather 10.
bf48b5d Trendy AI: krotko - maks. 3 odkrycia (pewnosc srednia/wysoka), twarde limity slow w poleceniu i obcinanie na serwerze, zwiezly panel (Sprawdz / Brakuje)
348ce43 Jedzenie -> Zdrowie (Dni, Analiza, Cialo, Serce, Passa, Brokul): Serce przeniesione z Formy + HRV z norma roczna i serce a jedzenie/waga (/api/jedzenie/heart_plus); /jedzenie.html i forma#serce przekierowuja; nav Zdrowie (nav.js v16); linki i teksty Telegrama
1ae5401 Trendy: Analiza AI v2 - silnik odkryc wzgledem normy 28 dni (reakcja na ciezka jazde i czas powrotu, zaleznosci z opoznieniem tylko miedzy rodzinami z p i efektem, sluchanie sygnalow, dawka-odpowiedz, deficyt vs regeneracja, forma vs regeneracja); AI tylko interpretuje: naglowek, odkrycia z pewnoscia, eksperyment
0226ce1 Karta dnia: Dzis + Co jeszcze zjesc w jednej karcie, normy przy makrach (bialko/wegle/tluszcz), sklad z diety; deficyt w planie z budzetu tygodnia zamiast stalego celu bilansu
777f2b4 Forma -> Trendy: Analiza AI w panelu bocznym (bez zapisu) - widoczne serie w zaznaczonym okresie/powiekszeniu, korelacje Pearsona liczone w przegladarce po usunieciu trendu (opoznienie 0-3 dni), AI tylko interpretuje; POST /api/trendy/ai (qbot_trend_ai.py)
c7fc0e4 Jedzenie -> Analiza tygodniami (pn-nd): budzet tygodnia (plan vs realizacja, ile zostalo, porownanie z poprzednim), dni tygodnia, skladniki, wzorce 4 tyg. (weekend, jazda, sen), top produkty, zalecenia AI tygodnia (same w ndz 21:00); Co jeszcze zjesc -> karta dnia (dzis)
cfc5474 Dni -> Obwody: karta pokazuje pomiar dnia ze zmiana od poprzedniego (albo ostatni pomiar), przycisk Zmierz otwiera okno z pustymi polami (Enter zapisuje, Esc zamyka)
07197a4 Jedzenie: obwody wpisywane w karcie dnia (Dni), z Bilansu usuniety formularz; Bilans i waga: sklad ciala w 2. wierszu przelacznikow, trend spalania 7 dni, sekcje 50/50, os kcal od 1500
cf97760 Bilans i waga: zmiana wysokosci wykresu uchwytem (jak Forma -> Trendy), zapamietana
959d03f Obwody ciala: tabela, API, kafelek z formularzem w Bilans i waga, seria talia cm (Bilans i waga + Forma Trendy Wellness), talia/wzrost, poniedzialkowe przypomnienie co 14 dni; gotowosc tylko na wykresie formy
721422a Bilans i waga: dwie sekcje (gora linie wagi/skladu, dol pas slupkow kcal), przelaczniki w jednym ciagu, zwarty pasek statusu zamiast kart (cel -> Trener Cele, tygodnie w Analizie), plan redukcji nie liczony wstecz przed startem
cc8350e Forma -> Trendy: wellness jak pozostale wykresy (pigulki po lewej, opis po prawej), pusta lewa os ukryta gdy brak sen/HRV/RHR
d713960 Bilans i waga: bez kreski zjedzone, slupki w dolnej polowie, sklad ciala - kazda seria we wlasnej skali (widac ksztalt i zaleznosci) z wartoscia na koncu linii, cel jedzenia tylko od startu redukcji 10.10
adf9ef3 Forma -> Trendy: wskazniki okresu (jazdy, dystans, czas, CP, W/kg) w pasku zakresu 30/90/rok z trendem vs poprzedni okres (zielony/czerwony trojkat); zrodlo jazd jak w Statystykach
58148c3 Forma -> Trendy: jednolite etykiety (pigulki jak w wykresie formy) dla CP/LTP i Wellness, bez legend Chart.js; bilans skumulowany jako waga z bilansu na osi wagi (start = waga z dnia rozpoczecia serii + bilans/7700)
39f4151 Bilans i waga: slupek = spalone (spoczynek BMR + aktywne), kreska = zjedzone, deficyt zielony / nadwyzka czerwona; caly sklad ciala (kg: tluszcz, miesnie, kosci; %: tluszcz, woda); przelaczniki w grupach z wyjasnieniami, plan redukcji 99-95-90 i prognoza przy obecnym tempie; API: podzial spalania, kosci
dcf1da4 Forma -> Trendy: wyrownane obszary 3 wykresow (ten sam dzien w pionie), dymki na wszystkich wykresach naraz, jasnozielone punkty jazd, bilans skumulowany tylko w okresach logowania (przerwa >2 dni = nowa seria od 0)
b815706 Forma -> Trendy: uchwyty wysokosci wykresow (zapamietane), wspolny kursor na 3 wykresach, punkty jazd na linii formy, daty na osi X, wellness: bilans skumulowany (linia, tooltip w kcal i kg) zamiast slupkow dziennych
b08d7ed Jedzenie -> Bilans i waga: JEDEN interaktywny wykres (kcal: zjedzone/spalone/cel; kg: waga, plan 99-95-90 z korytarzem, prognoza; sklad: tluszcz/miesnie kg z przelomem trybu sportowca), zakresy 45/90/180/rok/do celu/daty, dymek, powiekszanie przeciagnieciem, dwuklik, klik = dzien; pod spodem zwiezle karty
ee8eb8c Forma -> Trendy: powiekszanie przeciagnieciem (forma, moc, wellness razem), dwuklik / przycisk cala skala, zmiana zakresu 30/90/rok kasuje powiekszenie
7b8aa33 Sklad ciala w Jedzenie -> Bilans i waga (kg tluszczu, kg miesni, % tluszczu, przelom Athlete mode 12.10, pomiary podejrzane, srednia z 3 i zmiana); Forma -> Trendy: wykres wellness 300 px, waga domyslnie, nowa seria bilans kcal (zjedzone - spalone, slupki)
7903995 Withings sync: weryfikacja przez get_weigh_ins (get_body_composition nie pokazuje skladu) - bez petli ponownych wysylek
656c8c4 Withings sklad ciala: dzien z sama waga w Garminie (wpis MFP) nie blokuje wysylki pelnego pomiaru; weryfikacja wymaga skladu; import_garmin_body: wpis ze skladem wygrywa, sama waga nie nadpisuje dnia ze skladem. Utracone od 09.2026: 01.10 i 08.10 do ponownej wysylki
f509f33 Serce: wykres zweryfikowany; korekta blednej notatki o Chart.js (AppleScript JS = odizolowany swiat)
a0f93fc Serce: cisnienie Withings->Garmin->QBot, EKG z Garmina (ghs), tetno przy 140-180 W (hr_at_power), Forma > Serce (/api/forma/heart, forma-serce.js), Albert heart_health + prompt. Withings 601 = blad przejsciowy. Testy test_heart 7. Dok.: docs/SERCE.md
a4a46d7 Jedzenie: choroba = dzien bez deficytu, bezpiecznik 3 dni z rzedu deficyt >900 (linia rano), niedzielne rozliczenie z linia jedzenia tygodnia
ee02fb3 TODO: odlozony pomysl - nagrody za passe przez Plan zakupow w Garazu
d9afb9f Jedzenie: naglowek jak w Formie (zakladki .tabs w naglowku), rowne plakietki passy (stala wysokosc, ikona w stalym polu), telefon: passa pod zakladkami
0ea8978 Budzet tygodniowy deficytu (pn-nd): dzien lekki -300 (Brokul + przekaska ~200 o 16:00), dni z jazda reszta tygodnia proporcjonalnie do treningu (min -300, maks -900), tydzien domyka sie realnymi danymi; poranna rekomendacja: przekaska w dni lekkie
8f694a3 Analiza: tydzien = poniedzialek-niedziela (do dnia analizy), nie ostatnie 7 dni
1bbbe46 Model spalania w 3 czesciach: spoczynek (BMR Garmina 14 dni, nadaza za waga) + ruch codzienny bez treningu (aktywne - treningi, wg dnia tygodnia, cala historia) + trening (507 kcal/h); strona pokazuje rozbicie
2d02d51 Model spalania na calej historii Garmina (od 28.02, do 365 dni): dni z treningiem tez (calosc - kcal treningow), 17-27 probek na dzien tygodnia zamiast 6-12
47b5838 Prognoza spalania: baza dnia bez treningu wg dnia tygodnia (182 dni, sciagana do sredniej), dzien biezacy = Garmin do teraz + reszta dnia; strona: Garmin do HH:MM, ikona sportu
ef49af1 Dni minione w jezyku bilansu (zjedzone - spalone vs plan), cel dnia minionego bez zaokraglen (1912 zamiast 1900), kalendarz Trenera: bil. +102; Telegram: bilans +102 (plan -519) - 621 ponad plan
60da13f Ocena dnia symetryczna: minione dni za malo/za duzo/w celu z bilansem, pomarancz gdy deficyt za mocny (>300 kcal ponizej celu); strona, kalendarz Trenera, Telegram
a9a4cc9 Jedzenie: Analiza dziala tez przy wejsciu prosto w #analiza (data lokalna, zanim wczytaja sie dni)
f1ead9f Jedzenie: zakladka Analiza (co jeszcze zjesc, tydzien vs normy, zalecenia AI), interaktywny Bilans (45/90/180/daty, dymek, serie, waga, klik=dzien), Menu Brokula po tygodniach z podsumowaniem vs normy; kalendarz Trenera: zjedzone/cel w kafelku dnia z linkiem; Forma: usuniete makieta Odzywianie i Bilans i waga (przekierowanie do Jedzenia), kafelek Jedzenie dzis z prawdziwych danych
6387fdc Telegram: mniej i krocej - JEDNA poranna wiadomosc (trening, wazenie, rekomendacja jedzenia z normami skladnikow, wczoraj otwarty, koniec diety, weekend), zwiezla wiadomosc dnia 20:00 (kamienie milowe jako linia), niedziela: rozliczenie + plan w jednej; usuniete osobne: zwaz sie, 21:30, piatkowy weekend, koniec diety, kamienie. Dok.: docs/BROKUL.md
4a4962c Passa Treningu od pierwszego dnia w Trenerze (23.09), delegacja/urlop/wyprawa neutralnie, zdublowana sesja plan = wykonana (18 dni zamiast 2); nazwa Pasy -> Passa (strona, Telegram)
4eda25e Jedzenie: telefon - posilki Brokula w dwoch wierszach (nazwa nad przyciskami)
8f3f2f9 Strona Jedzenie (albert.cytr.us/jedzenie.html): Dni (Brokul, lodowka, wpisy poza dieta z dodawaniem/poprawka/skala/przeniesieniem/usunieciem, szybkie przyciski, okno, zamkniecie), Pasy (liczniki, mapa dni), Bilans i waga (wykres 42 dni, cel wagi, rozbieznosc, tygodnie), Menu Brokula; API /api/jedzenie/* (qbot_food_api.py), pozycja w menu. Dok.: docs/BROKUL.md
0129c03 Jedzenie etapy 3-7: model spalania + cel kcal dnia + dokladka do Brokula pod trening (7:00 Trener, 20:00 dzien), pasy Trening i Redukcja, piatkowy plan weekendu (AI), przypomnienie 21:30, podpowiedz lodowki przy delegacji, Open Food Facts jako podpowiedz AI, wykres celu wagi (plan+korytarz, wazenia, prognoza) w Trener > Cele. Dok.: docs/BROKUL.md
e62274e Etap 4: cel wagi z etapami 99/95/90 kg (aktywny etap steruje statusem i celem bilansu, etapy i prognoza w Celach), przypomnienie o wazeniu 7:00 (co >=2 dni od realnego wazenia, bez delegacji/urlopu/wyprawy i dnia po jezdzie >=3 h)
d87a899 Jedzenie: pasy 🔥 Jedzenie i 🕗 Okno 10-20 (zaufanie, przycisk do 12:00, zwolnienia trening>=90 min/delegacja/urlop/wyprawa, pora z wpisu), mrozenie, kamienie milowe; monitor waga vs jedzenie z realnych wazen (body_measurements) w rozliczeniu Trenera. Testy test_food_log 15
ca41676 Jedzenie: czytelne potwierdzenie - naglowek z suma, makra w 1 linii, tabela kcal|pozycja (blok stalej szerokosci), krotkie nazwy z iloscia od AI, znaczniki ?/~ z legenda
ba2e1c9 Jedzenie: historia Michala jako punkt odniesienia dla AI (chrupki 60 g, McCrispy 880 z wlasnych wpisow), pewnosc kazdej pozycji (pewne/srednie/zgrubne) w potwierdzeniu, poprawka pojedynczej pozycji odpowiedzia na potwierdzenie
7e68e0f Jedzenie: lista wielu pozycji bez pytan (typowe porcje opisane wprost), wymuszony JSON z jedna poprawka, komunikat o bledzie tylko raz
2856633 Wiadomosc dnia: dzien bez diety bez Brokula i bez Nic poza dieta, przyciski posilkow S/M/L (sniadanie/obiad/kolacja), legenda zamiast ucinanych etykiet
729119d Jedzenie etap 1-2: harmonogram dostaw Brokula (odwolane dni, koniec zamowienia), lodowka, wiadomosc dnia 20:00 (tez dni bez diety), Telegram: tekst/zdjecie = jedzenie (zapis surowy najpierw, dzien z tekstu, AI kcal+makra, porcje przyciskami, katalog, mniej/OK/wiecej), szybkie przyciski, zamkniecie dnia. Stary parser wellness/gear z Telegrama wylaczony. Testy test_food_log 8. Dok.: docs/BROKUL.md
d7a8de8 Brokul: import jadlospisu Diety od Brokula (sesja /brokul-dostep - reCAPTCHA blokuje haslo), qbot_v2.brokul_meals, cron */15 brokul_tick (import co 3 h, keepalive 20 min), Telegram od 20:00 z przyciskami Zjadlem/Pominalem/cofnij; do bilansu tylko po potwierdzeniu. Testy test_brokul 3. Dok.: docs/BROKUL.md
ba50d86 Dok.: ubior i sprzet w Analizie trasy - zmiany danych Garazu (blotniki, widelec Grizla + RaceDay 2, Grail 11.10), CURRENT + TODO (ZROBIONE). Tylko wpisy tej sesji.
f42be4a Rower: zasady Michala (Monster tylko zima/ciezkie warunki, nie trasy ~80 km; serwis nie wplywa na wybor), reczny wybor roweru w Sprzecie (/api/report/kit/manual) jako wzorzec dla AI, blotniki per rower (components bike_id). Testy test_gear_kit 5. Dok.: docs/OUTFIT_FAVORITES.md
96a08b5 SETUP > QExt2: pelne zestawienie kolorow KOKPIT 2 (PALETTE, probki kolorow, pozycje zalezne od ustawien)
3e85390 Garaz: kategoria Sprzetu Blotniki (EQUIP_CATEGORIES) - panel Sprzet (gear_kit) rozpoznaje blotniki po kategorii
a6247bc Sprzet: rower i akcesoria (gear_kit.py) - pogoda wstecz 7 dni/24 h z Open-Meteo w 4 punktach trasy -> stan nawierzchni (sucho/wilgotno/mokro/bloto, takze do doboru ubioru), wybor roweru przez AI (qbot_v2.route_kit, /api/report/kit), lampki (wschod/zachod/widocznosc) i blotniki (reguly). Panel Sprzet na cala szerokosc, wieksza czcionka, zestawy A/B obok siebie. Testy test_gear_kit 4. Dok.: docs/OUTFIT_FAVORITES.md
90419c1 QExt2 etap 3: qext2Config w /ride-readiness mcp_server.py (to pyta Karoo; q-bot.service)
4324086 QExt2 etap 3: /ride-readiness zwraca qext2Config (ustawienia z Setup > QExt2)
49ad17e Uwagi do AI (ubior, Analiza trasy -> Sprzet): uwaga poprawia biezacy zestaw od razu, AI proponuje wniosek na przyszlosc -> zapis po zatwierdzeniu (qbot_v2.outfit_lessons), wnioski z priorytetem w kazdym doborze; autokorekta kolorow nie cofa rzeczy zgodnie z Twoja uwaga. Endpointy /api/report/outfit/note|lessons (qbot_web.py wszedl w 83571f8). Testy test_outfit_notes 3. Dok.: docs/OUTFIT_FAVORITES.md
83571f8 SETUP > QExt2 etap 2: edycja i zapis komunikatow i kolorow pol (POST /api/setup/qext2, walidacja, reset, for_karoo)
2f243fe SETUP > QExt2 (Karoo) etap 1: podglad regul komunikatow i kolorow pol KOKPIT 2 (qext2_config.py, GET /api/setup/qext2, docs/QEXT2_CONFIG.md)
be7808c Faworyci ubioru (Analiza trasy -> Sprzet): przycisk + okno Rodzaj|Rzecz, faworyci per trasa+data (qbot_v2.route_outfit_fav, /api/report/outfit/fav, /api/report/outfit/gear); dobor A z faworytami + B AI bez faworytow (to samo tempo) + zrozumienie wyboru (outfit_fav.py). Testy test_outfit_fav 4. Dok.: docs/OUTFIT_FAVORITES.md
509068a Garaz: zakladka Notatki (bike_notes, tagi rowerow, /api/bike-notes/*) + notatka o lancuchach
d3f8303 E3.3: /ride-readiness przyjmuje token takze w X-QExt2-Token. Uwaga: most MCP (/root/qbot-mcp/server.py, poza repo) przekazywal tylko gole GET -- poprawiony 09.10 (naglowki tokenu, parametry, POST); kopia server.py.bak.planv2-20261009
a2203ab E7.1 (QExt2 plan v2): /ride-readiness POST {settings} zapisuje kopie ustawien SETUP (qbot_v2.qext2_settings), GET z tokenem oddaje deviceSettings do odtworzenia po reinstalacji
30f7cab Strava: nowe kwadraty liczone tez wzgledem migawki StatsHunters sprzed jazdy (cala historia; squadratinhos nie liczymy; brak migawki = brak linijki), migawka raz na dobe; bez atrakcji w promieniu 25 km od Warszawy; skrypt podgladu scripts/strava_publish_preview.py
426c581 E6.4 (QExt2 plan v2): /ride-readiness cadenceModel = naturalna kadencja per rower (nr ANT AXS / none) x %CP x nachylenie, p10/p25 z 90 dni, rower >= 15 jazd; budowa w tle co 24 h (data/cadence_model.json)
f845df3 Strava: Monster = Kloc MTB (gear b14851840), komplet mapowania rowerow
893c590 strava.html: autoryzacja Stravy w nowej karcie (w ramce Polaczen Strava gubila logowanie) + samoodswiezanie statusu
7d94072 E4.4 (QExt2 plan v2): /ride-readiness shortStopsMinPerKm = mediana krotkich postojow (<=20 min) / km z jazd >=40 km, 120 dni, cache 12 h
66e2f6b Strava: MyBiom/do Mamy (uczone z nazw, walidacja 88 jazd), wysilek z tetna/mocy bez W bal w tekscie, tytul [Qbot] A-B etykieta+ikona jazdy+pogoda tylko w miejsce domyslnej nazwy, bez obiektow religijnych. Testy 10. Dok.: docs/STRAVA_PUBLISH.md
93d073c E3.3 (QExt2 plan v2): /ride-readiness sprawdza token urzadzenia (QEXT_READINESS_TOKEN); tryb przejsciowy do instalacji nowego APK (READINESS_REQUIRE_TOKEN=1 wymusza); zgloszenie kasety jako POST tylko z tokenem
6110038 E-FIT (QExt2 plan v2): fit_ingest czyta qext2_schema i qext2_np5_w; model_schema w fitmodel_qext2_ride (1 = stare pliki z cf/starym XSS, 2 = plan v2); wbal_zero_seconds z timestampow (+testy)
78f1530 Strava: automatyczny rower (AXS 10625 Grizl / 27856 Grail / brak AXS Monster) + opis Albert.QBot (region, km, asfalt/szuter/ujeby, wysilek XSS+W bal, nowe kwadraty, atrakcja z Wikidanych oceniana przez AI, przerwa). qbot_strava_publish.py, scope +activity:write,profile:read_all. Testy test_strava_publish 5. Dok.: docs/STRAVA_PUBLISH.md
e00f18b smoke: todayFactor opcjonalny (pole pomijane bez wiersza ModelQ)
e8220b6 FIX krytyczny: /ride-readiness 500 gdy pressureChange24h=None (format +.1f na None w logu) -> Karoo bez danych przed jazda
757f12d RSRV v2: wzorzec fitmodel/rsrv_v2.py + tests/test_rsrv_v2.py (te same przypadki co QExt2 ReserveModelV2Test, QExt2 48a4e4b). Dok.: DECISIONS 2026-10-08, TODO ZROBIONE
c7e0188 fitmodel._db_connect: brak prawa do /etc/qbot/qbot-api.env nie wywraca polaczenia -> /ride-readiness (q-bot) znow wysyla lthrBpm=148 i durability dla Karoo. Dok.: DECISIONS 2026-10-08
58fad1d Karoo /ride-readiness: todayFactor z ModelQ readiness_effective (dzisiejszy wiersz), baroMultiplier=1.0 (brak zwiazku cisnienia na 645 dniach/282 jazdach); stare wartosci w signals jako legacy. Dok.: DECISIONS 2026-10-08
65bde99 CI smoke: przypiete mcp/pydantic jak na serwerze (nowy pydantic zepsul import mcp); scripts/ci_smoke_repro.sh - odtworzenie CI lokalnie. XSS z tetna: korekta temperatury (hr_xss.temp_factor, kalibracja w lthr), test. Dok.: DECISIONS/TODO 2026-10-08
b2a8cd5 Zbiorczy commit sesji 08.10: Centrum powiadomien - ustawienia (/api/setup/notif, qbot_notif, sql/app_settings_v1, test_notif_setup), logowanie/landing (qbot_web_auth, qbot_web_landing), Forma>Statystyki zestawienie aktywnosci (/api/stats/rides items) + kompaktowy wykres (forma-stats v6), Forma zegary (gotowosc teraz, podpisy skali, znacznik wczoraj; forma2-data v58), raport jazdy LTHR (raport-jazdy2-ws v45), menu nav v12, mockupy (porownanie 1:1, kalendarz, trening, plan), qdate.js, skrypty diagnostyczne (date_audit, garmin_*), lustro web_public. Dok.: NOTIF_CENTER, TRENER, WEB_DEMO_AUTH, DECISIONS 2026-10-08
808ee7a ModelQ 08.10: kotwica EF 11.08 usunieta (TP 255->239 W), kwarantanna 22.07-03.08 (XSS z HR), dynamiczne LTHR (fitmodel/lthr.py, dzis 148; hr_xss, raport, Trener, QExt2, intervals/Karoo + strefy HR), glikogen z bazy (930 s -> 0.4 s), Gotowosc TERAZ (readiness_now). Testy: lthr 7, readiness_now 5, glycogen_db 4. Dok.: DECISIONS 2026-10-08
6da34ae Menu: ikony 24 px, wszystkie na jednej osi (srodek 28 px, takze burger, dzwonek, dzien/noc). nav.css v12
d92a356 SETUP: Polaczenia (Strava/Komoot/Hammerhead w ramkach), Dostepy (dawna klodka, qLockMount, ?klodka=1 -> Setup), Trening>Sezony (sezon_ust), Kontakty (grupy mailowe); Wyloguj w prawym gornym rogu (#qlogout). nav v12, trener.js v35. Dok.: docs/SETUP.md
c1ee7bd SETUP > Trening: podzakladki u gory (Dostepnosc | Ustawienia Trenera), adres #trening-dostep|kalib, stary #kalib z Treningu trafia wprost. trener.js v34. Dok.: docs/SETUP.md
e698c58 Centrum powiadomien: krok 2 (jazdy, pogoda, system, demo QR, nieudane logowania) + krzyzyk usun z listy (dismissed_at, notif_v2.sql) + Historia 90 dni (/api/notif/history). nav v8. Testy test_notif_step2 4. Dok.: docs/NOTIF_CENTER.md
75572ad Centrum powiadomien krok 1: dzwonek w menu (nav.js qBell, plakietka, kropka na przycisku menu), panel wysuwany obok dzwonka; qbot_notif.py + qbot_v2.notif + /api/notif*; zrodla: rower do zrobienia, trasy do potwierdzenia, brak swiezych danych, wiadomosci Trenera. Lustro web_public (nav v7). Testy test_notif 4. Dok.: docs/NOTIF_CENTER.md
4dff630 Raport z jazdy: przycisk Ubior/rower (okno) + rower po jezdzie do zrobienia (garage.db bike_task, /api/bike-tasks*), Telegram 2 h przed jazda Trenera (tr:bt). Zawiera wczesniejsze niezacommitowane okno Z kim jechalem. Testy test_bike_tasks 5.
433073c Model czasu v3_2026-10-08b: odblokowany szuter -4..-2% = 24,3 km/h (decyzja Michala)
```

## 11. Web — pliki html/js/css bez odwolan (kandydaci na sieroty)

Pliki w web/public: 103. Szum mozliwy (adresy wpisywane recznie, zakladki).
### Nikt nie odsyla (12)
```
kalendarz-mockup.html
plan-mockup.html
planer-wyprawy2.html
planer-wyprawy3.html
pogoda-mockup.html
porownanie-1na1-mockup.html
porownanie-mockup.html
raport-jazdy2-sections.js
raport-jazdy2.html
raport-jazdy3.html
start2.js
tabs.css
```
### Nazwy sugerujace makiety/stare wersje (9)
```
forma-mockup.html
kalendarz-mockup.html
mapy-test.html
mockup-trener-sub.html
plan-mockup.html
pogoda-mockup.html
porownanie-1na1-mockup.html
porownanie-mockup.html
trening-mockup.html
```

## 12. Resztki po przebudowach i reguly formatu

### OpenWeatherMap (od 14.10 ma nie byc) — 57
```
qbot_legacy_parity_tools.py:270  "openweathermap",
qbot_legacy_parity_tools.py:279  env_presence = _env_presence(["OPENWEATHERMAP_API_KEY", "WEATHER_API_KEY", "OWM_API_KEY"])
qbot_legacy_parity_tools.py:282  current_status = "weather available via MCP get_weather (Open-Meteo); OpenWeatherMap integration is not presen
qbot_legacy_parity_tools.py:284  if evidence and any("openweathermap" in kw for item in evidence for kw in item.get("keywords_matched", [])):
qbot_legacy_parity_tools.py:288  "capability": "weather_openweathermap",
qbot_legacy_parity_tools.py:297  "notes": "Legacy OpenWeatherMap is not directly present; current weather path is read-only Open-Meteo via MCP.
qbot_legacy_parity_tools.py:310  env_presence = _env_presence(["OPENWEATHERMAP_API_KEY", "WEATHER_API_KEY", "OWM_API_KEY"])
qbot_legacy_parity_tools.py:327  "notes": "Read-only weather compatibility status; OpenWeatherMap-specific integration remains absent.",
qbot_legacy_parity_tools.py:802  "Weather uses current MCP/Open-Meteo path; OpenWeatherMap legacy is missing.",
qbot_legacy_parity_tools.py:1005  "legacy_capability": "weather_openweathermap",
qbot_legacy_parity_tools.py:1006  "label": "Weather / OpenWeatherMap",
qbot_legacy_parity_tools.py:1007  "keywords": ["openweathermap", "weather", "forecast", "pogoda", "open-meteo"],
qbot_legacy_parity_tools.py:1017  "notes": "Weather status/current/forecast surfaces exist and are read-only; OpenWeatherMap-specific parity is 
qbot_legacy_parity_tools.py:1127  "keywords": ["requests.get", "requests.post", "httpx", "webhook", "callback", "oauth", "openai", "deepseek", "
qbot_legacy_parity_tools.py:1153  "notes": "Telegram, Garmin/RWGPS, weather, email, webhooks, and MCP are present; OpenWeatherMap and home autom
qbot_legacy_parity_tools.py:1207  weather = next((row for row in rows if row["legacy_capability"] == "weather_openweathermap"), {})
qbot_legacy_parity_tools.py:1229  "weather_openweathermap": weather.get("new_qbot_status", "UNKNOWN"),
qbot_legacy_parity_tools.py:1254  f"weather/OpenWeatherMap: {weather.get('new_qbot_status', 'UNKNOWN')}",
qbot_legacy_parity_tools.py:1261  "OpenWeatherMap-specific parity is not present; current weather path is Open-Meteo-based.",
qbot_config.py:52  # E4.3 (14.10.2026): OpenWeatherMap usuniety -- pogoda wylacznie ze wspolnego silnika QBota (Open-Meteo bez kl
qbot_telegram_tools.py:924  owm_err = weather_status.get("openweathermap_error_message", "nie skonfigurowany")
qbot_telegram_tools.py:932  f"Wspólny silnik pogody (Open-Meteo): {om_err or owm_err or 'brak danych'}. "
qbot_integration_tools.py:755  """Raport pogody (teraz + godzinowo + dni) -- E4.2: wspolny silnik (bylo: OpenWeatherMap). Pola jak dawniej; u
qbot_integration_tools.py:791  OpenWeatherMap usuniety. Nie ujawnia sekretow."""
qbot_integration_tools.py:794  "weather_restored_status": "RESTORED", "openweathermap": "usunięty 2026-10-14 (wspólny silnik QBota)",
qbot_integration_tools.py:795  "openweathermap_key_present": False, "location_envs": location_presence,
qbot_integration_tools.py:950  #  WEATHER TOOLS — OpenWeatherMap primary, Open-Meteo fallback
qbot_integration_tools.py:1175  # ---------------------------------------------------------------- E4.2 (14.10.2026): WSPOLNY SILNIK zamiast O
qbot_integration_tools.py:1203  """Pogoda biezaca -- E4.2: wspolny silnik (bylo: OpenWeatherMap). Pola jak dawniej (+ na_rowerze_c, gusts_mps)
qbot_integration_tools.py:1207  "openweathermap_attempted": False, "open_meteo_attempted": True}
qbot_integration_tools.py:1243  "source": report.get("source", "OpenWeatherMap"),
qbot_integration_tools.py:1281  "source": report.get("source", "OpenWeatherMap"),
qbot_integration_tools.py:1314  "known_public_sources": ["Open-Meteo/ECMWF", "OpenStreetMap/Overpass", "OpenWeatherMap"],
qbot_integration_tools.py:1369  owm_ok = config.get("openweathermap_key_present", False)
qbot_integration_tools.py:1393  "openweathermap_active": owm_ok,
qbot_pogoda_albert.py:183  """E4.2 (14.10.2026): 'pogoda w miescie X' na WSPOLNYM SILNIKU (zastepuje OpenWeatherMap): geokodowanie + qbot
qbot_wbgt_tools.py:5  krotkofalowa (shortwave_radiation), ktorej OpenWeatherMap nie ma.
_bak_archive/1781719274_test_qbot3_acceptance.py:508  """Daily-report weather should use OpenWeatherMap and fail safely."""
_bak_archive/1781719274_test_qbot3_acceptance.py:610  self.assertIn("OPENWEATHERMAP_API_KEY", cfg.WEATHER_API_KEY_NAMES)
_bak_archive/1781719274_test_qbot3_acceptance.py:611  self.assertIn("OWM_API_KEY", cfg.WEATHER_API_KEY_NAMES)
_bak_archive/1781719274_test_qbot3_acceptance.py:614  with patch.dict(os.environ, {"OPENWEATHERMAP_API_KEY": "FAKE-OWM-SECRET"}, clear=False):
_bak_archive/1781719274_test_qbot3_acceptance.py:618  self.assertTrue(result["openweathermap_key_present"])
_bak_archive/1781719274_test_qbot3_acceptance.py:619  self.assertIn("OPENWEATHERMAP_API_KEY", result["owm_envs_checked"])
_bak_archive/1781719274_test_qbot3_acceptance.py:624  """OpenWeatherMap provider returns daily-report payload with structured fields."""
_bak_archive/1781719274_test_qbot3_acceptance.py:628  with patch("qbot_config.OPENWEATHERMAP_API_KEY", "FAKE-OWM-KEY"):
_bak_archive/1781719274_test_qbot3_acceptance.py:632  self.assertEqual(result["source"], "OpenWeatherMap")
_bak_archive/1781719274_test_qbot3_acceptance.py:646  "source": "OpenWeatherMap",
_bak_archive/1781719274_test_qbot3_acceptance.py:687  self.assertEqual(result["source"], "OpenWeatherMap")
_bak_archive/1781719274_test_qbot3_acceptance.py:695  with patch("qbot_config.OPENWEATHERMAP_API_KEY", ""):
_bak_archive/1781719274_test_qbot3_acceptance.py:700  self.assertEqual(result["source"], "OpenWeatherMap")
_bak_archive/1781720404_tool_registry.py:154  "Live fetch prognozy pogody z OpenWeatherMap — pobiera bezpośrednio z API, "
_bak_archive/1781720264_tool_registry.py:154  "Live fetch prognozy pogody z OpenWeatherMap — pobiera bezpośrednio z API, "
tools/feasibility.py:243  """Pogoda startu (najblizsza godzina >= start_hour) -- E4.3 (14.10.2026): wspolny silnik QBota (qbot_pogoda), 
tools/rwgps/route_weather.py:4  Zrodlo pogody: OpenWeatherMap PRIMARY, Open-Meteo FALLBACK (spec: OWM primary).
tools/rwgps/route_weather.py:96  """Open-Meteo przez wspolny transport QBota (qbot_wx). E4.3 (14.10.2026): OpenWeatherMap usuniety. Dok.: docs/
qbot3/tool_registry.py:121  """E4.2 (14.10.2026): wspolny silnik pogody (qbot_pogoda_albert.weather_city) zamiast OpenWeatherMap."""
qbot3/llm/albert.py:226  • „pogoda w <miejscowosc> / jutro w <miejscowosc> / na weekend w <miejscowosc>” (miejsce inne niz dom, albo ko
```
### Planner v2 / core.planner (nie istnieje) — 13
```
qbot_query_handler.py:5079  from core.planner import set_active_provider, _get_active_provider
qbot_query_handler.py:5152  from core.planner import plan_routes
qbot_mcp_adapter.py:655  from core.planner import plan_routes
qbot_mcp_adapter.py:688  from core.planner import plan_routes
qbot_mcp_adapter.py:719  from core.planner import plan_routes
_bak_archive/1781719274_test_qbot3_acceptance.py:88  with patch.dict(os.environ, {"QBOT_QUERY_VNEXT_ENABLED": "1", "QBOT_DISABLE_ALBERT_FALLBACK": "1"}, clear=Fals
_bak_archive/1781719274_test_qbot3_acceptance.py:121  patch("core.planner._run_openai_tool_loop", return_value={
_bak_archive/1781719274_test_qbot3_acceptance.py:262  with patch("core.planner._planner_config", return_value=("sk-test", "https://api.openai.com/v1", "gpt-4.1-mini
_bak_archive/1781719274_test_qbot3_acceptance.py:263  patch("core.planner._load_route_tools", return_value=(tool_spec, tool_map)), \
_bak_archive/1781719274_test_qbot3_acceptance.py:308  with patch("core.planner._planner_config", return_value=("sk-test", "https://api.openai.com/v1", "gpt-4.1-mini
_bak_archive/1781719274_test_qbot3_acceptance.py:309  patch("core.planner._load_route_tools", return_value=(tool_spec, tool_map)), \
_bak_archive/1781719108_opt_qbot_app_qbot_query_handler.py:4856  from core.planner import set_active_provider, _get_active_provider
_bak_archive/1781719108_opt_qbot_app_qbot_query_handler.py:4929  from core.planner import plan_routes
```
### Garmin w Trenerze (usuniety) — 15
```
qbot_trener_engine.py:1091  # obciazenie wykonanej jazdy = XSS ModelQ; TSS Garmina tylko gdy ModelQ jeszcze nie przeliczyl (~15 min po wgr
qbot_trener_engine.py:1098  "is_long": (r["duration_s"] or 0) >= float(P(ov, "yoga.long_h")) * 3600 * 0.8, "src": "garmin"})
qbot_trener_notify.py:268  elif act == "wake":  # [GARMIN-DANE] Etap 5: pobudka przed budzikiem (oznaczenie uzytkownika)
qbot_trener_notify.py:444  try:   # [GARMIN-DANE] Etap 6: ModelQ vs Garmin w rozliczanym tygodniu (fitmodel/garmin_load_check.py)
qbot_trener_notify.py:445  from fitmodel.garmin_load_check import week_line as _gwl
qbot_trener_notify.py:450  conn.rollback(); log.append(f"garmin-check: błąd {str(e)[:120]}")
qbot_trener_notify.py:451  try:   # [GARMIN-DANE] Etap 5: sen tygodnia; miesieczna analiza pobudek gdy tydzien obejmuje koniec miesiaca
qbot_trener_notify.py:461  conn.rollback(); log.append(f"garmin-check: błąd {str(e)[:120]}")
qbot_trener_notify.py:510  try:   # [GARMIN-DANE] Etap 4: temp. skory + HRV/tetno -> jedno zdanie, TYLKO gdy sygnal (fitmodel/body_signal
qbot_trener_notify.py:537  try:  # [GARMIN-DANE] Etap 5: przycisk 'Pobudka przed budzikiem' (zawsze; klikam tylko gdy sam sie obudzilem)
qbot_trener_ops.py:46  """Zrobione z Garmina -> status done w planie (ten sam dzien i sport, najblizsza godzina)."""
qbot_trener_ops.py:77  """Wykonanie dopasowanych sesji: realny czas (min) i obciazenie (XSS ModelQ; TSS Garmina tylko do czasu przeli
qbot_trener_ops.py:83  THEN 'modelq' WHEN t.tss IS NOT NULL THEN 'garmin' ELSE 'czas' END AS src
qbot_trener_review.py:68  "zrobione_z_garmina": [{"sport": a.get("sport_type"), "nazwa": a.get("activity_name"), "km": round((a.get("dis
qbot_trener_ask.py:283  day.pop("zrobione_z_garmina", None)
```
### Wiatr w km/h (regula: m/s) — 10
```
qbot_route_analysis_tool.py:276  seg.append(f"sr. {wind_avg:g} km/h")
qbot_route_analysis_tool.py:278  seg.append(f"max {wind_max:g} km/h")
qbot_route_report_tool.py:2204  """Bloki pod wiatr z analizy planu z m/s i km/h -> [(km_start, km_end, wind_ms, wind_kmh), ...].
qbot_route_report_tool.py:2243  return f"~{wind_ms:.1f} m/s / {wind_kmh:.0f} km/h"
qbot_telegram_tools.py:999  "WAŻNE: wiatr zawsze podawaj TYLKO w m/s (nie km/h), pole wind_mps. NIE dodawaj przeliczenia na km/h. "
qbot_pogoda.py:92  z route_meteo_engine._thermal_solve), utci = UTCI w jezdzie (wiatr + ped ~20 km/h), wbgt. Brak danych -> None.
qbot_pogoda.py:120  efektywny = wiatr 10 m + ped ~20 km/h; na trasie tylko do flag zimna), 'na_rowerze' = temp. do ubioru (ride_th
tools/feasibility.py:112  if wind>40: issues.append("Silny wiatr: {:.0f}km/h".format(wind)); weather_score-=1
tools/feasibility.py:113  elif wind>25: issues.append("Wiatr: {:.0f}km/h".format(wind))
tools/feasibility.py:233  if w and not w.get("_error"): lines.append("Pogoda: {:.0f}C (odcz.{:.0f}C) | {}km/h | {}".format(w["temp_c"],w
```
### Tydzien jako ostatnie 7 dni (regula: pn-nd) - do oceny — 33
```
qbot_trener_engine.py:163  if x["a"] < w["s"] + timedelta(days=7) and x["b"] >= w["s"]:
qbot_trener_engine.py:1103  pw0, pw1 = ws - timedelta(days=7), ws - timedelta(days=1)
qbot_dashboard.py:137  "where started_at >= now() - interval '7 days'"
qbot_trener_notify.py:456  if ws.month != (ws + timedelta(days=7)).month:
qbot_trener_notify.py:471  send_plan = ws + timedelta(days=7)
qbot_food_api.py:221  pws, prev_sum, prev_n = ws - timedelta(days=7), 0.0, 0
qbot_food_api.py:267  "prev": (ws - timedelta(days=7)).isoformat(), "next": (ws + timedelta(days=7)).isoformat() if ws + timedelta(d
qbot_food_api.py:446  "prev": (ws - timedelta(days=7)).isoformat() if rng and rng["a"] and rng["a"] < ws else None,
qbot_food_api.py:447  "next": (ws + timedelta(days=7)).isoformat() if rng and rng["b"] and rng["b"] > we else None,
qbot_query_router.py:2985  deadline_date = today + timedelta(days=7)  # default: a week out
qbot_heart.py:430  d7 = [well[d][0] for d in well if d > today - timedelta(days=7) and well[d][0]]
qbot_heart.py:431  d28 = [well[d][0] for d in well if today - timedelta(days=35) < d <= today - timedelta(days=7) and well[d][0]]
qbot_heart.py:432  hrv7 = _mean([float(well[d][2]) for d in well if d > today - timedelta(days=7) and well[d][2]])
qbot_food_streaks.py:223  ws += timedelta(days=7)
qbot_food_streaks.py:270  first_ok = START + timedelta(days=7)          # 1. tydzien diety = woda, nie oceniamy
qbot_trener_ops.py:286  a, b = hz[0] - timedelta(days=3), hz[-1] + timedelta(days=7)
qbot_query_handler.py:2715  date_from = today - timedelta(days=7)
ride_report.py:464  {"oldest": (act_date - timedelta(days=7)).isoformat(), "newest": act_date.isoformat()})
ride_report.py:469  {"oldest": (act_date - timedelta(days=7)).isoformat(),
_bak_archive/1781720404_tool_registry.py:1492  cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(day
_bak_archive/1781719108_opt_qbot_app_qbot_query_handler.py:2603  date_from = today - timedelta(days=7)
_bak_archive/1781720264_tool_registry.py:1492  cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(day
_bak_archive/20260716_calendar_core/qbot_qcal_cli.py:52  dt = _rd(args.date_to) if args.date_to else (date.today() + timedelta(days=7)).isoformat()
tools/rwgps/poi_open_window.py:454  close_dt += timedelta(days=7)
fitmodel/season.py:98  ws += dt.timedelta(days=7)
fitmodel/season.py:607  ws += dt.timedelta(days=7)
fitmodel/season.py:930  "FROM qbot_v2.fitmodel_daily WHERE day >= %s", (s0 - dt.timedelta(days=7),))}
fitmodel/week_planner.py:112  (wk_start - timedelta(days=7), wk_start),
fitmodel/lthr.py:186  p7 = pub.get(d - dt.timedelta(days=7))
qbot3/tool_registry.py:1423  cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(day
qbot3/routes/gear_kit.py:80  (d0 - _dt.timedelta(days=7)).isoformat(), d0.isoformat()))
qbot3/rides/ride_report_facts.py:238  "WHERE day BETWEEN %s AND %s ORDER BY day", (day - timedelta(days=1), day + timedelta(days=7)))
qbot3/rides/ride_report_facts.py:245  "ORDER BY day, id", (day, day + timedelta(days=7)))
```
