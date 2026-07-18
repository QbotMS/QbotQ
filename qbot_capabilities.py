#!/usr/bin/env python3
"""QBot Capability Registry v1 — central catalog of what QBot can do."""

from __future__ import annotations

import json, os, re, sys
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
    "rwgps_gpx_import": {
        "name": "rwgps_gpx_import",
        "status": "ready",
        "domains": ["routes", "rwgps", "write"],
        "intents": ["rwgps_gpx_import_draft"],
        "keywords": ["zapisz gpx","importuj gpx","zaimportuj gpx","wgraj gpx", "zapisz do rwgps"],
        "writer": "qbot_rwgps_route_import_gpx",
        "tables": [],
        "required_fields": ["gpx_path", "name"],
        "optional_fields": ["description", "privacy", "collection_id"],
        "output_type": "result",
        "safety": "write_safe",
        "description": "Importuje lokalny plik GPX jako nową trasę RWGPS. Wymaga confirm=true.",
        "limitations": ["Tylko format GPX. Wymaga RWGPS_AUTH_TOKEN."],
    },
    "weight_body": {
        "name": "weight_body",
        "status": "ready",
        "domains": ["weight", "body_composition"],
        "intents": ["weight_lookup", "body_comp_lookup"],
        "keywords": ["waga","masa ciała","body fat","tkanka tłuszczowa","bmi","skład ciała","ważę","ważył"],
        "reader": "weight_body_table",
        "tables": ["qbot_v2.body_measurements"],
        "required_fields": ["weight_kg"],
        "optional_fields": ["body_fat_pct","bmi","muscle_mass_kg","bone_mass_kg","body_water_pct"],
        "output_type": "table",
        "safety": "read_only",
        "description": "Historia wagi i składu ciała (body fat, BMI). Kanoniczne źródło: Garmin Index Scale → qbot_v2.body_measurements.",
        "limitations": [],
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
    "nutrition_food_search": {
        "name": "nutrition_food_search", "status": "ready",
        "domains": ["nutrition", "food_search"],
        "intents": ["product_search", "food_query"],
        "keywords": ["znajdź produkt","szukaj produktu","ile kcal ma","ile białka ma",
                     "wartości odżywcze","co zawiera","skład produktu","policz kalorie",
                     "wyszukaj jedzenie","ile ma kalorii","sprawdź produkt"],
        "reader": "read_food_product_catalog",
        "tables": ["food_items"],
        "required_fields": ["name", "kcal_per_100g"],
        "output_type": "list","safety":"read_only",
        "description": "Wyszukiwanie produktów w katalogu food_items po nazwie lub składnikach.",
        "limitations": ["Szuka po pełnej nazwie lub fragmencie. 41 produktów w bazie."],
    },
    "nutrition_log_add": {
        "name": "nutrition_log_add", "status": "ready",
        "domains": ["nutrition", "meal_logs", "write_nutrition"],
        "intents": ["log_meal", "add_food_entry"],
        "keywords": ["dodaj posiłek","dodaj jedzenie","zaloguj posiłek","wpisz jedzenie",
                     "dodaj do logu","zapisz posiłek","log-add","log_add",
                     "dodaj meal","zamów jedzenie","wpisz co zjadłem"],
        "writer": "qbot.nutrition_log_add",
        "tables": ["meal_logs", "meal_log_items", "nutrition_write_audit"],
        "required_fields": ["date", "name", "kcal"],
        "optional_fields": ["protein_g", "carbs_g", "fat_g"],
        "output_type": "confirmation","safety":"write_nutrition_only",
        "description": "Dodanie wpisu posiłku do meal_logs przez MCP/CLI z idempotency key.",
        "limitations": ["Wymaga confirm=true i idempotency_key. Po dodaniu: daily_summary_compute."],
    },
    "training_latest_activity": {
        "name": "training_latest_activity", "status": "ready",
        "domains": ["training", "activity"],
        "intents": ["latest_training_analysis", "training_assessment"],
        "keywords": ["jak mi poszła jazda","jak poszedł trening","oceń jazdę","oceń trening",
                     "ostatnia jazda","ostatni trening","dzisiejsza aktywność","jak mi dziś poszło",
                     "jak wyszła jazda","jak mi poszło","jak wyszła aktywność"],
        "reader": "read_latest_training_session",
        "tables": ["training_sessions"],
        "required_fields": ["date", "calories_kcal"],
        "output_type": "assessment","safety":"read_only",
        "description": "Ocena ostatniej aktywności treningowej z danych QBot DB.",
        "limitations": ["Używa zaimportowanych danych Garmin. Nie wymaga live API."],
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
    try:
        for name, cap in CAPABILITIES.items():
            tables = cap.get("tables", [])
            if not tables: continue
            exists = True; has_fields = True
            for t in tables:
                try:
                    conn.execute(f"SELECT 1 FROM {t} LIMIT 0")
                except:
                    conn.rollback()
                    exists = False; break
                # Check required fields
                required = cap.get("required_fields", [])
                for f in required:
                    try:
                        conn.execute(f"SELECT {f} FROM {t} LIMIT 0")
                    except:
                        conn.rollback()
                        has_fields = False
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
        handler = c.get("reader") or c.get("writer") or c.get("handler") or "missing_handler"
        entry = {"name": name, "status": c.get("status", "missing"), "safety": c.get("safety", "read_only"),
                 "domains": c.get("domains", []), "handler": handler, "tables": c.get("tables", []),
                 "limitations": c.get("limitations",[])}
        if conn:
            for t in c.get("tables",[]):
                try:
                    r = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()
                    entry[f"{t}_rows"] = r["c"]
                except:
                    conn.rollback()
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
    ready = {k: v for k, v in matched.items() if v.get("status") == "ready"}
    partial = {k: v for k, v in matched.items() if v.get("status") == "partial"}
    missing = {k: v for k, v in matched.items() if v.get("status") == "missing"}
    return {
        "query": question,
        "matched": list(matched.keys()),
        "ready": list(ready.keys()),
        "partial": list(partial.keys()),
        "missing": list(missing.keys()),
        "capabilities": {k: {"status": v.get("status", "missing"), "reader": v.get("reader") or v.get("writer") or "missing_handler", "tables": v.get("tables", [])} for k, v in matched.items()},
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


# ── CLI ──

def _print_table(caps: dict, domain: str = None):
    """Print capabilities as a formatted table."""
    if domain:
        header = f"QBot Capabilities (domain: {domain})"
        caps = {k: v for k, v in caps.items() if domain in v.get("domains", [])}
    else:
        header = "QBot Capabilities (all)"

    if not caps:
        print(f"{header}\n  (none)")
        return

    print(header)
    print("-" * len(header))
    print(f"{'capability':35s} {'status':10s} {'safety':22s} {'tables':50s} {'handler':35s}")
    print("-" * 155)
    for name, cap in sorted(caps.items()):
        status = cap.get("status", "?")
        safety = cap.get("safety", "read_only")
        tables = ", ".join(cap.get("tables", []))[:50]
        handler = cap.get("reader") or cap.get("writer") or "missing_handler"
        print(f"{name:35s} {status:10s} {safety:22s} {tables:50s} {handler:35s}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QBot Capability Registry CLI")
    parser.add_argument("command", nargs="?", default="query-capabilities",
                        help="Subcommand (default: query-capabilities)")
    parser.add_argument("--domain", "-d", default=None,
                        help="Filter capabilities by domain (nutrition, training, routes, ...)")

    args = parser.parse_args()

    if args.command == "query-capabilities":
        caps = get_capabilities()
        _print_table(caps, args.domain)
    else:
        print(f"Unknown command: {args.command}")
        print("Usage: python qbot_capabilities.py query-capabilities [--domain <domain>]")


if __name__ == "__main__":
    main()
