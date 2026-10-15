# Martwy kod -- kandydaci (2026-10-15)
_scripts/audit_deadcode.py. Graf importow (AST + napisy) od punktow startowych: uslugi qbot*, wykonywalne w katalogu glownym (cron root), scripts/, tests/._
_UWAGA: crontab roota jest niewidoczny dla kanalu DEV -- skrypty odpalane tylko z crona moga byc falszywie 'nieuzywane'. Werdykt = czlowiek._

Punkty startowe uslug: garmin_auth, hammerhead_auth, komoot_watch, qbot3, qbot3.capabilities.reports, qbot3.connectors, qbot3.connectors.import_garmin_heart, qbot_activity_ingest, qbot_api, qbot_config, qbot_qlab_server, qbot_task_queue, qbot_web, tools, withings_auth
Wykonywalne w katalogu glownym: qbot-qlab-server, qbot-hammerhead-sync, qbot-withings-sync, qbot-fit-rewrite, qbot-task

Modulow rdzenia: 350 | osiagalne z produkcji: 326 | tylko z testow/skryptow: 12 | nieosiagalne: 12

## A. Nieosiagalne z niczego (najmocniejsi kandydaci)
| modul | linii | ostatni commit |
|---|---|---|
| fitmodel.ingest_qext2_fit | 38 | 2026-07-07 |
| fitmodel.modelq2.breakthrough | 93 | 2026-07-08 |
| modules.nutrition | 0 | 2026-06-14 |
| modules.nutrition.manifest | 42 | 2026-06-14 |
| modules.routes | 0 | 2026-06-14 |
| modules.routes.manifest | 25 | 2026-06-14 |
| qbot.tools | 0 | 2026-05-29 |
| qbot3.capabilities.nutrition | 0 | 2026-05-29 |
| qbot3.capabilities.routes | 0 | 2026-05-29 |
| qbot3.routes.geonames_places | 91 | 2026-07-02 |
| qbot3.tools | 0 | 2026-05-29 |
| reminder_daemon | 208 | 2026-09-25 |

## B. Uzywane TYLKO przez testy/skrypty (produkcja ich nie laduje)
| modul | linii | ostatni commit |
|---|---|---|
| email_reply_processor | 479 | 2026-05-22 |
| email_template | 901 | 2026-05-25 |
| fitmodel.brief | 149 | 2026-06-19 |
| fitmodel.energy_fallback | 190 | 2026-09-20 |
| fitmodel.rsrv_v2 | 83 | 2026-10-08 |
| qbot3.connectors.import_garmin_body | 350 | 2026-10-12 |
| qbot3.connectors.import_garmin_energy | 109 | 2026-10-08 |
| qbot3.connectors.import_garmin_sleep | 61 | 2026-05-30 |
| qbot3.connectors.import_garmin_training | 91 | 2026-07-04 |
| qbot3.connectors.rebuild_garmin_body_measurements | 408 | 2026-06-01 |
| qbot3.routes.google_places_cache | 101 | 2026-10-06 |
| qbot_cache | 58 | 2026-05-20 |
