#!/usr/bin/env python3
"""QBot Capability Registry v1 — central catalog of what QBot can do."""

from __future__ import annotations

import json, os, re
from typing import Any

CAPABILITIES: dict[str, dict] = {
    "nutrition_balance": {
        "name": "nutrition_balance",
        "status": "ready",
        "domains": ["nutrition", "energy_balance"],
        "intents": ["balance", "nutrition_lookup"],
        "keywords": ["bilans odżywiania","bilans kalorii","kcal in","kcal out","kalorie z dnia",
                     "przyjęte kalorie","zjedzone","makro","białko","węgle","tłuszcz","bilans","żywienie"],
        "reader": "semantic_daily_nutrition_balance",
        "tables": ["nutrition_daily_summary", "daily_energy_expenditure"],
        "required_fields": ["kcal_total", "protein_total", "carbs_total", "fat_total"],
        "optional_fields": ["fluids_total", "fiber_total", "sodium_total"],
        "output_type": "table",
        "safety": "read_only",
        "description": "Dzienny bilans kalorii i makroskładników z nutrition_daily_summary i daily_energy_expenditure.",
        "limitations": ["Wymaga obu tabel do pełnego bilansu. Training calories to osobna capability."],
    },
    "training_summary": {
        "name": "training_summary",
        "status": "ready",
        "domains": ["training"],
        "intents": ["training_lookup", "training_analysis"],
        "keywords": ["trening","jazda","aktywność","kcal treningowe","training load","training effect",
                     "dystans","czas treningu","spalanie","spalone","przejechane"],
        "reader": "semantic_training_summary",
        "tables": ["training_sessions"],
        "required_fields": ["date", "calories_kcal"],
        "optional_fields": ["distance_km","elevation_gain_m","duration_sec","training_load","training_effect","avg_hr"],
        "output_type": "table",
        "safety": "read_only",
        "description": "Podsumowanie treningów: kcal, dystans, czas, load, effect.",
        "limitations": ["calories_kcal może być NULL dla starszych/niektórych importów."],
    },
    "route_list": {
        "name": "route_list",
        "status": "ready",
        "domains": ["routes", "rwgps"],
        "intents": ["route_lookup", "route_list"],
        "keywords": ["trasy","rwgps","route","najnowsze trasy","dystans","przewyższenie",
                     "bez gpx","bez eksportu","bez artefaktów","bez analizy"],
        "reader": "rwgps_route_list",
        "tables": ["route_artifacts"],
        "required_fields": ["route_id"],
        "optional_fields": ["distance_km","elevation_m","name"],
        "output_type": "list",
        "safety": "read_only",
        "description": "Lista tras RWGPS z nazwą, dystansem i przewyższeniem.",
        "limitations": ["Nazwy z RWGPS API, distance/elevation z metadata_json lub API."],
    },
    "weight_body": {
        "name": "weight_body",
        "status": "ready",
        "domains": ["weight", "body_composition"],
        "intents": ["weight_lookup", "body_comp_lookup"],
        "keywords": ["waga","masa ciała","body fat","tkanka tłuszczowa","bmi","skład ciała","ważę","ważył"],
        "reader": "weight_body_table",
        "tables": ["weight_history", "body_composition"],
        "required_fields": ["weight_kg"],
        "optional_fields": ["body_fat_pct","bmi","muscle_mass_kg","bone_mass_kg"],
        "output_type": "table",
        "safety": "read_only",
        "description": "Historia wagi i składu ciała (body fat, BMI).",
        "limitations": ["Body composition tylko dla pomiarów INDEX_SCALE (2 dni)."],
    },
    "calendar_day_context": {
        "name": "calendar_day_context",
        "status": "ready",
        "domains": ["calendar", "daily_context"],
        "intents": ["calendar_day_context", "daily_summary"],
        "keywords": ["co qbot wie o","wszystko o dniu","dzisiaj","wczoraj","dzień","kalendarz dnia",
                     "pokaż wszystko","co wiesz o"],
        "reader": "calendar_daily_snapshot",
        "tables": ["calendar_daily_snapshots", "calendar_events", "reminders"],
        "required_fields": ["snapshot_json"],
        "optional_fields": ["completeness_score"],
        "output_type": "summary",
        "safety": "read_only",
        "description": "Pełny kontekst dnia z Calendar Core: nutrition, training, sleep, events, reminders.",
        "limitations": ["Completeness zależy od dostępnych danych w snapshot."],
    },
    "qcal_reminders": {
        "name": "qcal_reminders",
        "status": "ready",
        "domains": ["qcal", "reminders", "calendar"],
        "intents": ["reminder_lookup", "reminder_read"],
        "keywords": ["przypomnienia","przypomnij","reminder","deadline","zrobione","snooze",
                     "odwołaj przypomnienie","pending","done"],
        "reader": "qcal_reminder_reader",
        "tables": ["reminders"],
        "required_fields": ["title", "date"],
        "optional_fields": ["time","reminder_type","status","channel"],
        "output_type": "list",
        "safety": "read_only",
        "description": "Lista przypomnień QCal. Write tylko przez dedykowane MCP writer tools.",
        "limitations": ["Query read-only. Write przez qbot.qcal_reminder_add/done/cancel (MCP/CLI)."],
    },
    "qcal_events": {
        "name": "qcal_events",
        "status": "ready",
        "domains": ["qcal", "events", "calendar"],
        "intents": ["event_lookup", "event_read"],
        "keywords": ["wydarzenie","event","termin","spotkanie","planowany trening","odwołaj wydarzenie",
                     "kalendarz wydarzeń"],
        "reader": "qcal_event_reader",
        "tables": ["calendar_events"],
        "required_fields": ["title", "date_start"],
        "optional_fields": ["time_start","event_type","status"],
        "output_type": "list",
        "safety": "read_only",
        "description": "Lista wydarzeń QCal.",
        "limitations": ["Query read-only. Write przez MCP writer tools."],
    },
    "xert_status": {
        "name": "xert_status",
        "status": "missing",
        "domains": ["fitness", "readiness", "recovery", "training"],
        "intents": ["fitness_status", "readiness_check"],
        "keywords": ["forma","gotowość","xert","freshness","fitness","fatigue","xss","zmęczenie",
                     "threshold","ftp","readiness"],
        "reader": "read_xert_status",
        "tables": ["xert_metrics"],
        "required_fields": ["threshold_power_w"],
        "optional_fields": ["freshness","fatigue","fitness","strain"],
        "output_type": "assessment",
        "safety": "read_only",
        "description": "Status Xert: FTP, freshness, fatigue, fitness, strain.",
        "limitations": ["Brak tabeli xert_metrics w DB. Xert credentials skonfigurowane ale dane nie są zapisywane historycznie."],
    },
    "garmin_sleep": {
        "name": "garmin_sleep",
        "status": "ready",
        "domains": ["sleep", "recovery"],
        "intents": ["sleep_lookup", "recovery_check"],
        "keywords": ["sen","sleep","długość snu","jakość snu","głęboki sen","rem","spał"],
        "reader": "read_garmin_sleep",
        "tables": ["qbot_sleep_daily"],
        "required_fields": ["sleep_duration_min"],
        "optional_fields": ["deep_sleep_min","rem_sleep_min","sleep_score"],
        "output_type": "summary",
        "safety": "read_only",
        "description": "Dane snu z Garmin: długość, fazy, score.",
        "limitations": ["Dane dostępne od 2026-05-01, 25 dni."],
    },
    "garmin_wellness": {
        "name": "garmin_wellness",
        "status": "ready",
        "domains": ["recovery", "wellness", "readiness"],
        "intents": ["wellness_lookup", "recovery_check"],
        "keywords": ["hrv","tętno spoczynkowe","resting hr","body battery","stress","wellness","regeneracja","rhr"],
        "reader": "read_garmin_wellness",
        "tables": ["qbot_wellness_daily"],
        "required_fields": ["hrv_ms", "resting_hr_bpm"],
        "optional_fields": ["sleep_duration_min","sleep_score","body_battery_start","body_battery_end"],
        "output_type": "summary",
        "safety": "read_only",
        "description": "Dane wellness z Garmin: HRV, RHR, body battery, sen.",
        "limitations": ["Dane od 2026-05-01, 52 dni."],
    },
    "latest_training_session": {
        "name": "latest_training_session", "status": "ready",
        "domains": ["training", "activity"],
        "intents": ["latest_training_analysis", "training_assessment"],
        "keywords": ["jak mi poszła jazda","jak poszedł trening","oceń jazdę","oceń trening",
                     "ostatnia jazda","ostatni trening","dzisiejsza aktywność","jak mi dziś poszło",
                     "jak wyszła jazda","jak mi poszło","jak wyszła aktywność"],
        "reader": "read_latest_training_session",
        "tables": ["training_sessions"],
        "required_fields": ["date","calories_kcal"],
        "output_type": "assessment","safety":"read_only",
        "description": "Ocena ostatniej aktywności treningowej z danych QBot DB.",
        "limitations": ["Używa zaimportowanych danych Garmin. Nie wymaga live API."],
    },
    "food_product_catalog": {
        "name": "food_product_catalog", "status": "ready",
        "domains": ["nutrition", "food_catalog"],
        "intents": ["product_list", "food_catalog_lookup"],
        "keywords": ["produkty","baza produktów","katalog produktów","food products","food catalog",
                     "wszystkie produkty","lista produktów","pokaż produkty"],
        "reader": "read_food_product_catalog",
        "tables": ["food_items"],
        "required_fields": ["name"],
        "output_type": "list","safety":"read_only",
        "description": "Katalog produktów żywieniowych (food_items). 41 produktów.",
        "limitations": ["Źródło prawdy dla nazw produktów. Meal logs z food_item_id=null (17 wpisów) to osobna kategoria."],
    },
    "saved_meals_catalog": {
        "name": "saved_meals_catalog", "status": "ready",
        "domains": ["nutrition", "meal_templates"],
        "intents": ["meal_template_list", "saved_meal_lookup"],
        "keywords": ["zdefiniowane posiłki","saved meals","templates","standardowe posiłki",
                     "moje posiłki","brokuł sport","wiejski hp","szablony posiłków"],
        "reader": "read_saved_meals_catalog",
        "tables": ["meal_templates"],
        "required_fields": ["name","kcal"],
        "output_type": "list","safety":"read_only",
        "description": "Zdefiniowane szablony posiłków (meal_templates). 7 szablonów.",
        "limitations": ["Szablony Cronometer: Brokuł sport 2000, Wiejski HP, Białko/*."],
    },
    "meal_log_inventory": {
        "name": "meal_log_inventory", "status": "ready",
        "domains": ["nutrition", "meal_logs"],
        "intents": ["meal_log_list", "meal_history"],
        "keywords": ["wpisy żywieniowe","logi posiłków","dzisiejsze posiłki","historia posiłków",
                     "lista posiłków","meal logs","co zjadłem"],
        "reader": "read_meal_log_inventory",
        "tables": ["meal_logs", "meal_log_items"],
        "required_fields": ["id","eaten_at"],
        "output_type": "list","safety":"read_only",
        "description": "Wpisy posiłków. 11 logów, 21 items (4 linked do food_items).",
        "limitations": ["17 wpisów meal_log_items ma food_item_id=null — niepołączone z katalogiem."],
    },
    "food_link_audit": {
        "name": "food_link_audit", "status": "ready",
        "domains": ["nutrition", "data_quality"],
        "intents": ["food_link_audit", "data_quality_check"],
        "keywords": ["food_item_id null","niepołączone produkty","produkty z logów",
                     "kandydaci do produktów","uporządkuj produkty","braki w katalogu",
                     "produkty bez katalogu","niepołączone","link audit"],
        "reader": "read_food_link_audit",
        "tables": ["meal_log_items", "food_items"],
        "required_fields": ["food_item_id"],
        "output_type": "audit","safety":"read_only",
        "description": "Audyt połączeń meal_log_items → food_items. 17/21 wpisów bez linku.",
    },
}


# ── DB Inventory ──

def _db_check():
    try:
        import psycopg; from psycopg.rows import dict_row
        c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),
            dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),
            password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        return c
    except: return None


def update_statuses():
    """Update capability statuses based on actual DB state."""
    conn = _db_check()
    if not conn: return
    cur = conn.cursor()
    try:
        for name, cap in CAPABILITIES.items():
            tables = cap.get("tables", [])
            if not tables: continue
            exists = True; has_fields = True
            for t in tables:
                try:
                    cur.execute(f"SELECT 1 FROM {t} LIMIT 0")
                except: exists = False; break
                # Check required fields
                required = cap.get("required_fields", [])
                for f in required:
                    try:
                        cur.execute(f"SELECT {f} FROM {t} LIMIT 0")
                    except: has_fields = False
            if not exists:
                cap["status"] = "missing"
            elif not has_fields:
                cap["status"] = "partial"
            else:
                cap["status"] = "ready"
    except: pass
    finally: conn.close()


def get_capabilities(domain: str = None) -> dict:
    """Return capability registry, optionally filtered by domain."""
    update_statuses()
    if not domain: return dict(CAPABILITIES)
    return {k: v for k, v in CAPABILITIES.items() if domain in v.get("domains", [])}


def list_capabilities() -> list[dict]:
    caps = get_capabilities()
    result = []
    conn = _db_check()
    for name, c in caps.items():
        entry = {"name": name, "status": c["status"], "domains": c["domains"],
                 "reader": c["reader"], "tables": c["tables"], "limitations": c.get("limitations",[])}
        if conn:
            try:
                cur = conn.cursor()
                for t in c.get("tables",[]):
                    try:
                        cur.execute(f"SELECT COUNT(*) c FROM {t}")
                        entry[f"{t}_rows"] = cur.fetchone()["c"]
                    except: pass
            except: pass
        result.append(entry)
    if conn: conn.close()
    return result


def match_capabilities(question: str) -> dict:
    """Match query against capabilities based on keywords."""
    ql = question.lower()
    matched = {}
    for name, cap in CAPABILITIES.items():
        for kw in cap.get("keywords", []):
            if kw in ql:
                matched[name] = cap
                break
    # Status report
    ready = {k: v for k, v in matched.items() if v["status"] == "ready"}
    partial = {k: v for k, v in matched.items() if v["status"] == "partial"}
    missing = {k: v for k, v in matched.items() if v["status"] == "missing"}
    return {
        "query": question,
        "matched": list(matched.keys()),
        "ready": list(ready.keys()),
        "partial": list(partial.keys()),
        "missing": list(missing.keys()),
        "capabilities": {k: {"status": v["status"], "reader": v["reader"], "tables": v["tables"]} for k, v in matched.items()},
    }


def validate_plan(capabilities_matched: dict, domains: list) -> dict:
    """Validate that the matched capabilities cover the requested domains."""
    issues = []
    domain_caps = {}
    for name, cap in CAPABILITIES.items():
        for d in cap.get("domains",[]):
            domain_caps.setdefault(d,[]).append(name)

    for d in domains:
        caps = domain_caps.get(d, [])
        if not caps:
            issues.append(f"Domain '{d}': no capability registered")
            continue
        ready = [c for c in caps if CAPABILITIES.get(c,{}).get("status") == "ready"]
        if not ready:
            issues.append(f"Domain '{d}': no ready capabilities (available: {caps})")

    missing_caps = [k for k, v in capabilities_matched.items() if v.get("status") == "missing"]
    if missing_caps:
        issues.append(f"Missing capabilities: {missing_caps}")

    return {"valid": not issues, "issues": issues, "ready_caps": [k for k, v in capabilities_matched.items() if v.get("status") == "ready"]}
