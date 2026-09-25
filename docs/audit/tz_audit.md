# Audyt stref czasowych (auto)

Podsumowanie wzorcow: now_utc=95, sqlite_now=25, toISOString=14, getUTC=6, fmt_Z=5, utcnow=1, pg_utc=1, iso_slice=1

## Postgres: kolumny timestamp BEZ strefy (0)

## garage.db: kolumny z domyslnym czasem
- bikes.created_at default=datetime('now')
- components.created_at default=datetime('now')
- fitting.created_at default=datetime('now')
- gear.created_at default=datetime('now')
- memories.created_at default=datetime('now')
- memories.updated_at default=datetime('now')
- trips.created_at default=datetime('now')
- packing_lists.created_at default=datetime('now')
- reminders.created_at default=datetime('now')
- tires.created_at default=datetime('now')
- ride_gear_log.created_at default=datetime('now')
- ride_gear_log.updated_at default=datetime('now')
- color_map.updated_at default=datetime('now')
- equipment.created_at default=datetime('now')
- ui_prefs.updated_at default=datetime('now')
- instructions.created_at default=datetime('now')
- instructions.updated_at default=datetime('now')
- bike_geometry.updated_at default=CURRENT_TIMESTAMP
- rider_body.created_at default=CURRENT_TIMESTAMP

## Kod (plik: linia [wzorzec] tresc)
### app/qbot_web.py (13)
- 2675 [now_utc] `_esc(name or "QBot"), _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))]`
- 2675 [fmt_Z] `_esc(name or "QBot"), _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))]`
- 6464 [sqlite_now] `"VALUES (?,?,?,?, datetime('now')) "`
- 6466 [sqlite_now] `"gear_id=excluded.gear_id, value=excluded.value, updated_at=datetime('now')",`
- 6520 [sqlite_now] `"VALUES (?,?, 'llm', datetime('now'))", (c, q))`
- 7369 [sqlite_now] `gc.execute("UPDATE bike_geometry SET %s, updated_at=CURRENT_TIMESTAMP WHERE bike_id=?"`
- 7603 [sqlite_now] `gc.execute("INSERT INTO ui_prefs (key, value, updated_at) VALUES (?,?, datetime('now')) "`
- 7604 [sqlite_now] `"ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",`
- 7674 [sqlite_now] `gc.execute("UPDATE instructions SET %s, updated_at=datetime('now') WHERE id=?"`
- 7701 [sqlite_now] `gc.execute("UPDATE instructions SET active=?, updated_at=datetime('now') WHERE id=?",`
- 9152 [sqlite_now] `"VALUES(?,?,datetime('now'))", (_ckey, _json.dumps(_res)))`
- 9415 [sqlite_now] `"VALUES(?,?,?,?,1,datetime('now'))", (category, None, name, season))`
- 9461 [sqlite_now] `"VALUES(?,?,?,?,datetime('now'),?)",`
### app/db.py (10)
- 32 [sqlite_now] `created_at    TEXT DEFAULT (datetime('now'))`
- 39 [sqlite_now] `created_at TEXT DEFAULT (datetime('now'))`
- 70 [sqlite_now] `created_at    TEXT DEFAULT (datetime('now'))`
- 90 [sqlite_now] `created_at     TEXT DEFAULT (datetime('now'))`
- 112 [sqlite_now] `created_at          TEXT DEFAULT (datetime('now'))`
- 129 [sqlite_now] `created_at     TEXT DEFAULT (datetime('now'))`
- 136 [sqlite_now] `created_at TEXT DEFAULT (datetime('now')),`
- 137 [sqlite_now] `updated_at TEXT DEFAULT (datetime('now'))`
- 289 [sqlite_now] `"UPDATE memories SET content=?, updated_at=datetime('now') WHERE topic=?",`
- 313 [sqlite_now] `"UPDATE memories SET content=?, updated_at=datetime('now') WHERE topic=?",`
### web/public/trener.js (6)
- 26 [toISOString] `function iso(ms) { return new Date(ms).toISOString().slice(0, 10); }`
- 27 [getUTC] `function pl(ms) { var d = new Date(ms); return ("0" + d.getUTCDate()).slice(-2) + "." + ("0" + (d.getUTCMonth() + 1)).slice(-2); }`
- 30 [getUTC] `function monday(ms) { var dow = (new Date(ms).getUTCDay() + 6) % 7; return ms - dow * DAY; }`
- 56 [getUTC] `var d = new Date(ms), k = (d.getUTCMonth() + 1) * 100 + d.getUTCDate(), f = ddmm(p.f), t = ddmm(p.t);`
- 226 [getUTC] `(r.issues || []).map(function (i) { var c = SEVC[i.severity] || SEVC["średnia"]; return "<div class='tr-note' style='border-color:" + c[1] + ";margin:`
- 648 [getUTC] `function firstWorkday(prevYear) { var d = Date.UTC(prevYear, 11, 27); while ([0, 6].indexOf(new Date(d).getUTCDay()) >= 0) d += DAY; return d; }`
### app/qbot_integration_tools.py (5)
- 365 [now_utc] `today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")`
- 916 [now_utc] `"timestamp": datetime.now(timezone.utc).isoformat(),`
- 1181 [now_utc] `now = datetime.now(timezone.utc)`
- 1558 [now_utc] `target_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()`
- 1561 [now_utc] `target_date = datetime.now(timezone.utc).date().isoformat()`
### app/scripts/r35_build_poi_gpx_roundtrip.py (4)
- 135 [now_utc] `ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
- 135 [fmt_Z] `ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
- 278 [now_utc] `lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")`
- 445 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_roadmap_runner.py (3)
- 53 [now_utc] `return datetime.now(timezone.utc).isoformat()`
- 1475 [now_utc] `started = datetime.now(timezone.utc)`
- 1486 [now_utc] `elapsed_minutes = (datetime.now(timezone.utc) - started).total_seconds() / 60`
### app/qbot_qlab_server.py (3)
- 419 [now_utc] `_gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()`
- 432 [now_utc] `_gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()`
- 449 [now_utc] `_gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()`
### app/qbot_legacy_tools.py (3)
- 43 [now_utc] `"last_checked_at": datetime.now(timezone.utc).isoformat(),`
- 77 [now_utc] `"last_checked_at": datetime.now(timezone.utc).isoformat(),`
- 289 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_ops_tools.py (3)
- 199 [now_utc] `age_hours = round((datetime.now(timezone.utc).timestamp() - mtime) / 3600, 1)`
- 678 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 1232 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_api.py (3)
- 849 [now_utc] `"timestamp": datetime.now(timezone.utc).isoformat(),`
- 1035 [now_utc] `"updatedAt": datetime.now(timezone.utc).isoformat(),`
- 1103 [now_utc] `"updatedAt": datetime.now(timezone.utc).isoformat(),`
### app/scripts/audit_timezones.py (3)
- 11 [sqlite_now] `("sqlite_now", re.compile(r"datetime\('now'\)|CURRENT_TIMESTAMP", re.I)),`
- 13 [pg_utc] `("pg_utc", re.compile(r"AT TIME ZONE 'UTC'|timezone\('UTC'", re.I)),`
- 59 [sqlite_now] `# SQLite garage.db: domyslne czasy (datetime('now') = UTC)`
### app/scripts/qbot_smoke_tests.py (3)
- 964 [now_utc] `return FakeCursor({"id": 10, "route_id": "55256628", "artifact_path": "/opt/qbot/artifacts/exports/rwgps/rwgps_55256628.gpx", "filename": "rwgps_55256`
- 966 [now_utc] `return FakeCursor({"id": 20, "route_artifact_id": 10, "parser_version": "gpx-summary-v1", "source_artifact_sha256": "abc", "parsed_at": datetime.now(t`
- 968 [now_utc] `return FakeCursor({"id": 30, "route_artifact_id": 10, "enrichment_version": "surface-profile-v1", "source_artifact_sha256": "abc", "enriched_at": date`
### app/tools/rwgps/client.py (3)
- 840 [now_utc] `"cached_at": datetime.now(timezone.utc).isoformat(),`
- 3438 [now_utc] `backup_ts = datetime.now(timezone.utc)`
- 3767 [now_utc] `backup_ts = datetime.now(timezone.utc)`
### app/qbot3/routes/route_precompute_orchestrator.py (3)
- 227 [now_utc] `started_at = datetime.now(timezone.utc)`
- 259 [now_utc] `finished_at = datetime.now(timezone.utc)`
- 284 [now_utc] `finished_at = datetime.now(timezone.utc)`
### app/qbot3/artifacts/store.py (3)
- 174 [now_utc] `return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["tmp"])`
- 176 [now_utc] `return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["import"])`
- 178 [now_utc] `return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["report"])`
### web/public/planer-wyprawy-render.js (3)
- 352 [toISOString] `if (nDays > 1) { var dd = new Date(day); dd.setDate(dd.getDate() + (nDays - 1)); endD = dd.toISOString().slice(0, 10); }`
- 611 [toISOString] `var entry = { id: Date.now(), route_id: sel.value, route_name: name, nDays: nDays, cuts: cuts.slice(), dniData: dniData, departure: currentDeparture()`
- 641 [toISOString] `var entry = { id: Date.now(), route_id: sel.value, route_name: name, nDays: nDays, cuts: cuts.slice(), dniData: dniData, departure: currentDeparture()`
### app/qbot_legacy_parity_tools.py (2)
- 1194 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 1222 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_tools.py (2)
- 105 [now_utc] `"timestamp": datetime.now(timezone.utc).isoformat(),`
- 499 [now_utc] `"timestamp": datetime.now(timezone.utc).isoformat(),`
### app/qbot_legacy_cutover_tools.py (2)
- 162 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 337 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/mcp_server.py (2)
- 810 [now_utc] `now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")`
- 2335 [now_utc] `generated_at = datetime.now(timezone.utc).isoformat()`
### app/qbot_external_llm_tools.py (2)
- 129 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 227 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_operator_tools.py (2)
- 357 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 393 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_mcp_adapter.py (2)
- 556 [now_utc] `"created_at": datetime.now(timezone.utc).isoformat(),`
- 1912 [now_utc] `timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")`
### app/qbot_energy_store.py (2)
- 132 [now_utc] `datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)),`
- 154 [now_utc] `datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)),`
### app/scripts/build_context.py (2)
- 98 [now_utc] `now = datetime.now(timezone.utc)`
- 100 [fmt_Z] `return now.strftime("%Y-%m-%d %H:%M:%S %Z") + tz_note`
### app/scripts/lib/route_logistics.py (2)
- 478 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
- 613 [now_utc] `"committed_at": datetime.now(timezone.utc).isoformat(),`
### app/tools/fit-export/fit_export.py (2)
- 360 [now_utc] `"generatedAt": datetime.now(timezone.utc).isoformat(),`
- 395 [now_utc] `"createdAt": datetime.now(timezone.utc).isoformat(),`
### app/qbot3/routes/worldcover_tiles.py (2)
- 53 [now_utc] `return datetime.now(timezone.utc).isoformat()`
- 246 [now_utc] `cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400`
### app/qbot3/routes/route_attraction_store.py (2)
- 253 [now_utc] `json.dumps(ranked["summary"], ensure_ascii=False), datetime.now(timezone.utc),`
- 254 [now_utc] `datetime.now(timezone.utc)),`
### app/qbot3/routes/route_poi_store.py (2)
- 206 [now_utc] `status = "active" if datetime.now(timezone.utc) <= stale_after else "stale"`
- 592 [now_utc] `fetched_at = datetime.now(timezone.utc)`
### app/qbot3/connectors/import_xert_profile_snapshot.py (2)
- 133 [now_utc] `ts = datetime.now(timezone.utc)`
- 165 [now_utc] `now_utc = datetime.now(timezone.utc)`
### web/public/garaz-fit.js (2)
- 366 [toISOString] `const today=()=>new Date().toISOString().slice(0,10);`
- 399 [toISOString] `["+ Nowy pomiar",()=>{ const d=Object.assign({},bodyM||{}); delete d.id; d.measured_on=new Date().toISOString().slice(0,10);`
### web/public/trener-mock.html (2)
- 881 [toISOString] `function iso(ms){return new Date(ms).toISOString().slice(0,10);}`
- 882 [getUTC] `function pl(ms){var d=new Date(ms);return ("0"+d.getUTCDate()).slice(-2)+"."+("0"+(d.getUTCMonth()+1)).slice(-2);}`
### web/public/forma-render.js (2)
- 659 [toISOString] `const end=new Date().toISOString().slice(0,10);`
- 660 [toISOString] `const s=new Date();s.setDate(s.getDate()-100);const start=s.toISOString().slice(0,10);`
### web/public/mq2-render.js (2)
- 204 [toISOString] `function isoAgo(days){ const d=new Date(); d.setDate(d.getDate()-days); return d.toISOString().slice(0,10); }`
- 205 [toISOString] `function isoToday(){ return new Date().toISOString().slice(0,10); }`
### app/qbot_reminder_tools.py (1)
- 29 [sqlite_now] `created_at TEXT NOT NULL DEFAULT (datetime('now'))`
### app/qbot_assistant_inbox.py (1)
- 18 [now_utc] `return datetime.now(timezone.utc).isoformat()`
### app/qbot_legacy_shadow_tools.py (1)
- 161 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_legacy_execution_tools.py (1)
- 187 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot_report_tools.py (1)
- 888 [now_utc] `now = datetime.now(timezone.utc)`
### app/qbot_wellness_store.py (1)
- 31 [now_utc] `return datetime.now(timezone.utc).isoformat()`
### app/qbot_telegram_tools.py (1)
- 898 [now_utc] `_safe_exec("qbot_intervals_comments_import_preview", {"dry_run": True, "date_to": datetime.now(timezone.utc).strftime("%Y-%m-%d")})`
### app/qbot_route_tools.py (1)
- 1653 [now_utc] `now = datetime.now(timezone.utc).timestamp()`
### app/qbot_query_handler.py (1)
- 5557 [now_utc] `cutoff = datetime.now(timezone.utc) - timedelta(days=days)`
### app/qbot_task_queue.py (1)
- 17 [now_utc] `return datetime.now(timezone.utc).isoformat()`
### app/qlab_replay_export.py (1)
- 193 [now_utc] `"generated_at": datetime.now(timezone.utc).isoformat(),`
### app/reminder_daemon.py (1)
- 137 [sqlite_now] `"AND datetime(deadline) < datetime('now')"`
### app/scripts/test_gpx_artifact_geometry_readout.py (1)
- 301 [fmt_Z] `print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")`
### app/scripts/surface_enrich_route.py (1)
- 123 [now_utc] `"computed_at": datetime.now(timezone.utc).isoformat(),`
### app/scripts/rwgps_web_upload_gpx.py (1)
- 219 [now_utc] `upload_started_at = datetime.now(timezone.utc)`
### app/scripts/benchmark_nutrition_variants.py (1)
- 331 [utcnow] `"timestamp": datetime.utcnow().isoformat() + "Z",`
### app/scripts/test_rwgps_export_artifact_store_registration.py (1)
- 220 [fmt_Z] `print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")`
### app/scripts/data_freshness_check.py (1)
- 10 [now_utc] `start = datetime.now(timezone.utc)`
### app/scripts/lib/manual_surface_overrides.py (1)
- 66 [now_utc] `return datetime.now(timezone.utc).isoformat()`
### app/scripts/q/gravel_intelligence_10.py (1)
- 29 [now_utc] `return datetime.now(timezone.utc).isoformat()`
### app/qbot3/memory.py (1)
- 79 [now_utc] `"created_at": datetime.now(timezone.utc).isoformat(),`
### app/qbot3/observability.py (1)
- 50 [now_utc] `"timestamp": datetime.now(timezone.utc).isoformat(),`
### app/qbot3/safety.py (1)
- 358 [now_utc] `backup_path = f"{resolved}.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"`
### app/qbot3/routes/route_intro.py (1)
- 212 [now_utc] `"created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),`
### app/qbot3/routes/ride_invite.py (1)
- 188 [now_utc] `"prognoza_z": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")},`
### app/qbot3/routes/outfit_advisor.py (1)
- 548 [now_utc] `"created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),`
### app/qbot3/routes/route_surface_store.py (1)
- 117 [now_utc] `"fetched_at": profile.get("enriched_at") or datetime.now(timezone.utc),`
### app/qbot3/routes/planer_stage_export.py (1)
- 535 [now_utc] `now = datetime.now(timezone.utc)`
### app/qbot3/routes/route_day_pack.py (1)
- 300 [now_utc] `"model": model_name, "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),`
### app/qbot3/rides/ride_report_notify.py (1)
- 87 [now_utc] `now = datetime.now(timezone.utc)`
### app/qbot3/connectors/import_garmin_sleep.py (1)
- 16 [now_utc] `now = datetime.now(timezone.utc)`
### app/qbot3/connectors/import_garmin_training.py (1)
- 16 [now_utc] `now = datetime.now(timezone.utc)`
### app/qbot3/connectors/import_garmin_body.py (1)
- 277 [now_utc] `ts = datetime.now(timezone.utc)`
### app/qbot3/connectors/rebuild_garmin_body_measurements.py (1)
- 254 [now_utc] `now_ts = datetime.now(timezone.utc)`
### app/qbot3/connectors/import_withings_body.py (1)
- 42 [now_utc] `now = datetime.now(timezone.utc)`
### web/public/index-old.html (1)
- 137 [toISOString] `function iso(dt){return dt.toISOString().slice(0,10);}`
### web/public/kalendarz-render.js (1)
- 285 [iso_slice] `+(sc.finished_at?(" o "+sc.finished_at.slice(11,16)):"");`
### web/public/planer-wyposazenia.html (1)
- 233 [toISOString] `var dzis=new Date().toISOString().slice(0,10);`
### web/public/nutrition-render.js (1)
- 23 [toISOString] `function iso(dt){return dt.toISOString().slice(0,10);}`
