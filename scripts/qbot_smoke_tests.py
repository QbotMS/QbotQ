#!/usr/bin/env python3
"""Local smoke tests for critical QBot paths."""
from __future__ import annotations

import os
import json
import io
import logging
import asyncio
import math
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("HIKCONNECT_ACCOUNT", "test-account")
os.environ.setdefault("HIKCONNECT_PASSWORD", "test-password")
os.environ.setdefault("GATE_TOKEN", "test-gate-token")
os.environ.setdefault("GATE_DEVICE_SERIAL", "Q13393992")
os.environ.setdefault("GATE_LOCK_CHANNEL", "1")
os.environ.setdefault("GATE_LOCK_INDEX", "0")
os.environ.setdefault("GATE_RATE_LIMIT_SEC", "60")
try:
    from pydantic_settings.sources.providers import dotenv as pydantic_dotenv

    pydantic_dotenv.DotEnvSettingsSource._read_env_files = lambda self: {}
except Exception:
    pass

try:
    import dotenv
    import dotenv.main

    dotenv.load_dotenv = lambda *args, **kwargs: False
    dotenv.main.load_dotenv = lambda *args, **kwargs: False
except Exception:
    pass

sys.path.insert(0, "/opt/qbot/app")

import db
import email_template
import mcp_server
import email_reply_processor as email_reply
import qbot_cache
import qbot_coach
import qbot_report_status
import qbot_qlab_server
import scripts.qbot_operational_state as op_state
import telegram_reply_processor as tg_reply
import tools.rwgps.client as rwgps_client
from qbot_garage_mapper import classify_gear_text
from qbot_readiness import evaluate_readiness
from qbot_recovery import select_recovery_records, sleep_data_date_marker
from ride_report import build_ride_protocol, generate_html, interpret_decoupling


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _load_rwgps_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = Path("/opt/qbot/app/.env")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key.startswith("RWGPS_"):
            values[key] = raw_value.strip().strip('"').strip("'")
    return values


def test_readiness():
    assert_equal(
        evaluate_readiness(hrv=60, hrv_norm=70, illness_context=True).verdict,
        "ODPUSC",
        "illness + low HRV verdict",
    )
    assert_equal(
        evaluate_readiness(hrv=80, hrv_norm=70, body_battery=85, sleep_hours=8, form=5).verdict,
        "TAK",
        "good readiness verdict",
    )


def test_gear_mapper():
    assert_equal(classify_gear_text("kask MIPS").tool, "save_gear", "helmet -> gear")
    assert_equal(classify_gear_text("łańcuch do wymiany").tool, "save_component", "chain -> component")
    assert_equal(classify_gear_text("opona trzyma na piachu").payload["category"], "tires", "tire category")
    assert_equal(classify_gear_text("nowy rower gravel").tool, "save_bike", "new bike -> bike")
    assert_equal(classify_gear_text("wysokość siodła 775 mm").label, "fitting:memory", "fitting -> fitting memory")


def test_memory_append():
    orig = db.DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "garage.db"
        db.init()
        assert_equal(db.save_memory_append("t", "abc")["action"], "created", "memory create")
        assert_equal(db.save_memory_append("t", "abc")["action"], "skipped_duplicate", "memory dedupe")
        assert_equal(db.save_memory_append("t", "def")["action"], "appended", "memory append")
        content = db.search_garage("t")["memories"][0]["content"]
        if "abc" not in content or "def" not in content:
            raise AssertionError("memory append content missing")
    db.DB_PATH = orig


def test_email_template_single_call():
    calls = []

    def fake_ai(prompt, max_t=0):
        calls.append((prompt, max_t))
        return json.dumps({
            "tldr": "TLDR test. Drugie zdanie. Trzecie zdanie.",
            "kom_sen": "Sen test.",
            "kom_reg": "HRV test.",
            "kom_frm": "Forma test.",
            "kom_bil": "Bilans test.",
            "verdict": "TAK",
            "skrot": "60 min endurance",
            "kom_rek": "Zrób 60 minut w Z2. Trzymaj nisko. Uzasadnij HRV. Nie dociskaj. Zakończ spokojnie.",
            "kom_rad": "Nie rób z tego testu formy.",
        }, ensure_ascii=False)

    html = email_template.render({
        "dzisiaj": "2026-05-19",
        "pogoda": {},
        "sen": {},
        "regeneracja": {},
        "forma": {},
        "bilans": {},
        "wyjazdy": [],
    }, fake_ai)
    assert_equal(len(calls), 1, "daily email AI call count")
    if "TLDR test" not in html:
        raise AssertionError("daily email HTML missing generated text")


def test_email_template_weight_fallback_label():
    html = email_template.render({
        "dzisiaj": "2026-05-20",
        "pogoda": {},
        "sen": {},
        "regeneracja": {},
        "forma": {},
        "bilans": {
            "waga_dzis_kg": 101.2,
            "waga_dzis_date": "2026-05-18",
            "waga_dzis_fallback": True,
            "waga_tydzien_temu_kg": 102.0,
            "waga_tydzien_temu_date": "2026-05-13",
            "waga_anchor_kg": 103.6,
            "waga_anchor_date": "2026-05-05",
        },
        "wyjazdy": [],
    }, lambda prompt, max_t=0: json.dumps({
        "tldr": "TLDR test.",
        "kom_sen": "Sen test.",
        "kom_reg": "HRV test.",
        "kom_frm": "Forma test.",
        "kom_bil": "Bilans test.",
        "verdict": "TAK",
        "skrot": "60 min endurance",
        "kom_rek": "Zrób spokojny trening.",
        "kom_rad": "Bez dociskania.",
    }, ensure_ascii=False))
    if "Ostatnia waga" not in html or "Ostatnie ważenie (18.05)" not in html:
        raise AssertionError("daily email HTML missing weight fallback label/date")


def test_email_template_event_banner_local_cid():
    html = email_template.render({
        "dzisiaj": "2026-05-20",
        "pogoda": {},
        "sen": {},
        "regeneracja": {},
        "forma": {},
        "bilans": {},
        "wyjazdy": [{"name": "Tuscany Trail", "days_to": 12}],
    }, lambda prompt, max_t=0: json.dumps({
        "tldr": "TLDR test.",
        "kom_sen": "Sen test.",
        "kom_reg": "HRV test.",
        "kom_frm": "Forma test.",
        "kom_bil": "Bilans test.",
        "verdict": "TAK",
        "skrot": "60 min endurance",
        "kom_rek": "Zrób spokojny trening.",
        "kom_rad": "Bez dociskania.",
    }, ensure_ascii=False), banner_cid="tuscany-gravel-banner")
    if "source.unsplash" in html:
        raise AssertionError("daily email HTML still uses remote event image")
    if 'src="cid:tuscany-gravel-banner"' not in html:
        raise AssertionError("daily email HTML missing Tuscany banner CID")
    if 'alt="Tuscany Trail banner"' not in html:
        raise AssertionError("daily email HTML missing Tuscany banner alt text")


def test_daily_coach_decision_and_alerts():
    coach = qbot_coach.build_daily_coach({
        "sen": {"czas_h": 5.5},
        "regeneracja": {"hrv": 60, "hrv_norma": 70, "body_battery_rano": 40},
        "forma": {"swiezosc": -10},
        "bilans": {
            "wczoraj_kcal": -900,
            "srednia_7d_kcal": -600,
            "waga_dzis_kg": 101.2,
            "waga_dzis_date": "2026-05-18",
            "waga_dzis_fallback": True,
        },
        "wyjazdy": [{"name": "Tuscany Trail", "days_to": 12}],
    }, future_events=[{"date": "2026-05-21", "name": "Interwały Z4"}])
    assert_equal(coach["decision"]["verdict"], "ODPUSC", "daily coach red decision")
    if not coach["risk_alerts"]:
        raise AssertionError("daily coach missing risk alerts")
    assert_equal(coach["event"]["focus"], "taper, sen, paliwo i sprawdzenie listy pakowania", "event focus")


def test_ride_lesson_decoupling():
    lesson = qbot_coach.build_ride_lesson({
        "coach": {"decoupling_bad": True},
        "health": {},
        "long_rides": {"split": {}},
    })
    assert_equal(lesson["title"], "Kontroluj narastanie tętna", "ride lesson decoupling")


def test_weekly_review_flags_blockers():
    review = qbot_coach.build_weekly_review(
        [{"id": "2026-05-19", "hrv": 60, "sleepSecs": 18000, "comments": "Zjedzone: 1800 kcal\nSpalone: 2700 kcal"}],
        [{"moving_time": 1800, "icu_training_load": 20}],
        [],
    )
    if "deficyt kalorii był za głęboki" not in review["blockers"]:
        raise AssertionError("weekly review missing calorie blocker")
    if "brak długiej jazdy" not in review["blockers"]:
        raise AssertionError("weekly review missing long ride blocker")


def test_ride_protocol():
    sample_data = {
        "aktywnosc": {
            "distance": 90000,
            "moving_time": 12000,
            "decoupling": 5.7,
            "description": "kaszel",
            "fit_streams": {
                "power": {"probki_co_30s": [100, 100, 90, 80]},
                "heart_rate": {"probki_co_30s": [120, 125, 135, 140]},
                "cadence": {"probki_co_30s": [70, 72, 68, 66]},
            },
        },
        "wellness_dzis": {"hrv": 60},
        "wellness_7dni": [{"id": "a", "hrv": 72, "comments": "infekcja"}],
        "garmin": {"body_battery_rano": 90},
        "nawierzchnia": {
            "dominujaca": "ubita nawierzchnia",
            "kontekst_kadencji": "Ubita nawierzchnia — kadencja 72–85 rpm",
            "nawierzchnia": {
                "ubita nawierzchnia": "42%",
                "nieutwardzona": "20%",
                "asfalt": "10%",
                "earth": "1%",
                "unhewn_cobblestone": "2%",
                "nieznana": "25%",
            },
        },
        "bike": {},
        "porownanie_podobne": [],
        "ostatnie_dlugie_jazdy": [],
    }
    protocol = build_ride_protocol(sample_data)
    assert_equal(protocol["health"]["verdict"], "ODPUSC", "ride protocol red flag")
    assert_equal(protocol["long_rides"]["split"]["available"], True, "long ride split available")
    assert_equal(protocol["route"]["surface"]["summary"], "mieszana, przewaga ubita nawierzchnia 42%", "surface summary")
    if "earth" in (protocol["route"]["surface"]["detail"] or "") or "unhewn_cobblestone" in (protocol["route"]["surface"]["detail"] or ""):
        raise AssertionError("surface detail leaked raw tags")
    assert_equal(protocol["coach"]["decoupling"], "5.7%", "decoupling display")
    assert_equal(protocol["coach"]["decoupling_bad"], True, "decoupling threshold")
    assert_equal(protocol["route"]["cadence_rule"], "Kadencja oceniana po sprawdzeniu nawierzchni i typu roweru.", "cadence rule wording")
    html = generate_html({
        "dzisiaj": "2026-05-24",
        **sample_data,
    }, "Afternoon Ride")
    for marker in ("Analiza trenera", "Rekomendacja", "Lekcja na następną jazdę", "Protokół 6 — jazda długa"):
        if marker not in html:
            raise AssertionError(f"ride HTML missing expected section: {marker}")


def test_decoupling_display():
    assert_equal(interpret_decoupling(None), ("—", "brak danych", False), "missing decoupling")
    assert_equal(interpret_decoupling(0), ("0.0%", "brak dryfu — HR stabilne względem mocy", False), "zero decoupling")


def test_recovery_select_morning_cross_midnight():
    recovery = select_recovery_records(
        [{
            "localDate": "2026-05-19",
            "startTime": "2026-05-18T23:42:00+02:00",
            "endTime": "2026-05-19T07:18:00+02:00",
            "durationMin": 456,
        }],
        [{
            "localDate": "2026-05-19",
            "sourceTime": "2026-05-19T07:18:00+02:00",
            "value": 58,
        }],
    )
    assert_equal(recovery["sleepTodayH"], 7.6, "cross-midnight sleep hours")
    assert_equal(recovery["hrvToday"], 58.0, "cross-midnight hrv")
    assert_equal(recovery["recoverySource"]["sleepStartTime"], "2026-05-18T23:42:00+02:00", "sleep start")


def test_recovery_ignores_incomplete_today():
    recovery = select_recovery_records(
        [
            {
                "localDate": "2026-05-19",
                "startTime": "2026-05-18T23:50:00+02:00",
                "durationMin": 120,
            },
            {
                "localDate": "2026-05-18",
                "startTime": "2026-05-17T23:10:00+02:00",
                "endTime": "2026-05-18T06:50:00+02:00",
                "durationMin": 460,
            },
        ],
        [{"localDate": "2026-05-18", "value": 61}],
    )
    assert_equal(recovery["recoverySource"]["sleepLocalDate"], "2026-05-18", "ignore incomplete today")
    assert_equal(recovery["sleepTodayH"], 7.67, "complete fallback sleep hours")


def test_recovery_sleep_without_hrv():
    recovery = select_recovery_records(
        [{
            "localDate": "2026-05-19",
            "startTime": "2026-05-18T22:40:00+02:00",
            "endTime": "2026-05-19T06:40:00+02:00",
            "durationMin": 480,
        }],
        [],
    )
    assert_equal(recovery["sleepTodayH"], 8.0, "sleep returned when hrv missing")
    assert_equal(recovery["hrvToday"], None, "missing hrv -> null")
    assert_equal(recovery["recoverySource"]["hrvFallback"], False, "no hrv fallback")


def test_recovery_latest_end_time_wins():
    recovery = select_recovery_records(
        [
            {
                "localDate": "2026-05-18",
                "startTime": "2026-05-17T23:00:00+02:00",
                "endTime": "2026-05-18T07:00:00+02:00",
                "durationMin": 480,
            },
            {
                "localDate": "2026-05-19",
                "startTime": "2026-05-18T23:30:00+02:00",
                "endTime": "2026-05-19T06:30:00+02:00",
                "durationMin": 420,
            },
        ],
        [{"localDate": "2026-05-19", "value": 57}],
    )
    assert_equal(recovery["recoverySource"]["sleepLocalDate"], "2026-05-19", "latest end wins")
    assert_equal(recovery["sleepTodayH"], 7.0, "latest end sleep hours")


def test_recovery_no_records():
    recovery = select_recovery_records([], [])
    assert_equal(recovery["sleepTodayH"], None, "no records sleep null")
    assert_equal(recovery["hrvToday"], None, "no records hrv null")
    assert_equal(recovery["recoverySource"]["isComplete"], False, "no records incomplete source")


def test_sleep_data_date_marker():
    source = {"sleepLocalDate": "2026-05-23"}
    assert_equal(sleep_data_date_marker(source), "2026-05-23", "sleep marker value")
    assert_equal(sleep_data_date_marker(dict(source)), "2026-05-23", "sleep marker stability")
    assert_equal(sleep_data_date_marker({"sleepLocalDate": "2026-05-24"}), "2026-05-24", "sleep marker change")
    assert_equal(sleep_data_date_marker({}), None, "sleep marker missing")


def test_ride_readiness_sleep_data_date_payload():
    original_icu = mcp_server.icu
    original_get_garmin = mcp_server.get_garmin_wellness
    original_recovery = mcp_server._garmin_recovery_records
    original_xert = mcp_server.get_xert_status
    original_async_client = mcp_server.httpx.AsyncClient

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            now_str = now_utc.strftime("%Y-%m-%dT%H:00")
            ago24_str = (now_utc - __import__("datetime").timedelta(hours=24)).strftime("%Y-%m-%dT%H:00")
            return {
                "current": {"relativehumidity_2m": 50},
                "hourly": {
                    "time": [ago24_str, now_str],
                    "surface_pressure": [1010.0, 1015.0],
                },
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return FakeResponse()

    async def fake_icu(endpoint, params=None):
        today = "2026-05-23"
        return [
            {"id": today, "ctl": 40.0, "atl": 50.0, "hrv": 60, "sleepSecs": 18000, "restingHR": 45, "weight": 80.0},
            {"id": "2026-05-22", "hrv": 59, "sleepSecs": 17000, "restingHR": 46, "weight": 79.5},
        ]

    def fake_get_garmin(date_str):
        return json.dumps({
            "body_battery": {"naladowana": 82},
            "sen": {"czas_h": 8.0, "score": 80, "ocena": "dobry"},
        })

    def fake_recovery(date_count):
        sleep_date = fake_recovery.sleep_date
        return {
            "sleepRecords": [{
                "localDate": sleep_date,
                "startTime": f"{sleep_date}T23:40:00+02:00",
                "endTime": f"{sleep_date}T07:20:00+02:00",
                "durationMin": 460,
            }],
            "hrvRecords": [{
                "localDate": sleep_date,
                "sourceTime": f"{sleep_date}T07:20:00+02:00",
                "value": 58,
            }],
        }

    fake_recovery.sleep_date = "2026-05-23"

    def fake_xert():
        return json.dumps({
            "tp_ftp_watts": 265,
            "ltp_watts": 250,
            "hie_kj": 18,
            "forma": {"status": "Fresh", "form_score": 4},
        })

    async def run_once():
        response = await mcp_server.ride_readiness(None)
        return json.loads(response.body.decode("utf-8"))

    try:
        mcp_server.icu = fake_icu
        mcp_server.get_garmin_wellness = fake_get_garmin
        mcp_server._garmin_recovery_records = fake_recovery
        mcp_server.get_xert_status = fake_xert
        mcp_server.httpx.AsyncClient = FakeAsyncClient

        payload1 = asyncio.run(run_once())
        payload2 = asyncio.run(run_once())
        assert_equal(payload1["sleepDataDate"], "2026-05-23", "sleep data date payload")
        assert_equal(payload1["sleepDataDate"], payload2["sleepDataDate"], "sleep data date stability")
        assert_equal(payload1["todayFactor"], payload2["todayFactor"], "todayFactor stable")
        assert_equal(payload1["signals"]["sleepDataDate"], "2026-05-23", "sleep data date in signals")

        fake_recovery.sleep_date = "2026-05-24"
        payload3 = asyncio.run(run_once())
        assert_equal(payload3["sleepDataDate"], "2026-05-24", "sleep data date changes after new sleep")
        if payload3["todayFactor"] != payload1["todayFactor"]:
            raise AssertionError("todayFactor changed after sleep marker update")

        encoded = json.loads(json.dumps(payload3, ensure_ascii=False))
        assert_equal(encoded["sleepDataDate"], "2026-05-24", "sleep data date serializes")
    finally:
        mcp_server.icu = original_icu
        mcp_server.get_garmin_wellness = original_get_garmin
        mcp_server._garmin_recovery_records = original_recovery
        mcp_server.get_xert_status = original_xert
        mcp_server.httpx.AsyncClient = original_async_client


def test_route_surface_cache_helpers():
    original = mcp_server.ROUTE_SURFACE_CACHE
    with tempfile.TemporaryDirectory() as tmp:
        mcp_server.ROUTE_SURFACE_CACHE = Path(tmp) / "route_surface_cache.json"
        payload = {"activity_id": "a1", "nawierzchnia": {"asfalt": "100%"}}
        mcp_server._save_route_surface_cache("a1", payload)
        cached = json.loads(mcp_server._cached_route_surface("a1", "timeout"))
        assert_equal(cached["cache_hit"], True, "route surface cache hit")
        assert_equal(cached["cache_reason"], "timeout", "route surface cache reason")
        assert_equal(cached["nawierzchnia"]["asfalt"], "100%", "route surface cached payload")
    mcp_server.ROUTE_SURFACE_CACHE = original


def test_rwgps_manifest_fallback_is_explicit():
    original_manifest = rwgps_client.RWGPS_MANIFEST_PATH
    original_auth = rwgps_client.RWGPS_AUTH_TOKEN
    original_user = rwgps_client.RWGPS_USER_ID
    original_key = rwgps_client.RWGPS_API_KEY
    original_collection = rwgps_client.RWGPS_PLANNED_COLLECTION_ID

    try:
        rwgps_client.RWGPS_AUTH_TOKEN = None
        rwgps_client.RWGPS_USER_ID = None
        rwgps_client.RWGPS_API_KEY = None
        rwgps_client.RWGPS_PLANNED_COLLECTION_ID = None
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "rwgps_manifest.json"
            manifest_path.write_text(json.dumps({
                "routes": [{
                    "id": "local-1",
                    "name": "Local fallback route",
                    "status": "planned",
                    "source": "local_manifest",
                    "collections": [{"id": "planned", "name": "Planned routes"}],
                }],
                "collections": [{"id": "planned", "name": "Planned routes", "route_count": 1, "source": "local_manifest"}],
                "events": [],
                "metadata": {},
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            rwgps_client.RWGPS_MANIFEST_PATH = manifest_path

            routes = rwgps_client.list_routes(limit=10)
            assert_equal(routes["source"], "local_manifest", "rwgps list source")
            assert_equal(routes["origin"], "local_manifest", "rwgps list origin")
            assert_equal(routes["integration"]["configured"], False, "rwgps configured false")
            assert_equal(routes["integration"]["source"], "local_manifest", "rwgps integration source")
            if "warning" not in routes["integration"]:
                raise AssertionError("rwgps integration missing fallback warning")
            assert_equal(routes["routes"][0]["source"], "local_manifest", "rwgps route source")
            assert_equal(routes["routes"][0]["origin"], "local_manifest", "rwgps route origin")

            collections = rwgps_client.list_collections()
            assert_equal(collections["source"], "local_manifest", "rwgps collections source")
            assert_equal(collections["origin"], "local_manifest", "rwgps collections origin")
            assert_equal(collections["collections"][0]["origin"], "local_manifest", "rwgps collections item origin")

            route = rwgps_client.get_route("local-1")
            assert_equal(route["source"], "local_manifest", "rwgps get route source")
            assert_equal(route["origin"], "local_manifest", "rwgps get route origin")
            assert_equal(route["route"]["origin"], "local_manifest", "rwgps get route origin")

            planned = rwgps_client.list_planned_routes(limit=10)
            assert_equal(planned["source"], "local_manifest", "rwgps planned source")
            assert_equal(planned["origin"], "local_manifest", "rwgps planned origin")
            if not planned["planned_strategy"].startswith("local_manifest"):
                raise AssertionError("rwgps planned strategy not labeled as local manifest")
    finally:
        rwgps_client.RWGPS_MANIFEST_PATH = original_manifest
        rwgps_client.RWGPS_AUTH_TOKEN = original_auth
        rwgps_client.RWGPS_USER_ID = original_user
        rwgps_client.RWGPS_API_KEY = original_key
        rwgps_client.RWGPS_PLANNED_COLLECTION_ID = original_collection


def test_rwgps_error_payload_has_origin():
    original_manifest_routes = rwgps_client._manifest_routes
    original_auth = rwgps_client.RWGPS_AUTH_TOKEN
    original_user = rwgps_client.RWGPS_USER_ID
    original_key = rwgps_client.RWGPS_API_KEY
    original_collection = rwgps_client.RWGPS_PLANNED_COLLECTION_ID
    try:
        rwgps_client.RWGPS_AUTH_TOKEN = None
        rwgps_client.RWGPS_USER_ID = None
        rwgps_client.RWGPS_API_KEY = None
        rwgps_client.RWGPS_PLANNED_COLLECTION_ID = None
        rwgps_client._manifest_routes = lambda: []
        payload = rwgps_client.list_routes(limit=10)
        assert_equal(payload["ok"], False, "rwgps error payload ok")
        assert_equal(payload["source"], "fallback", "rwgps error payload source")
        assert_equal(payload["origin"], "fallback", "rwgps error payload origin")
        if "error" not in payload:
            raise AssertionError("rwgps error payload missing error")
    finally:
        rwgps_client._manifest_routes = original_manifest_routes
        rwgps_client.RWGPS_AUTH_TOKEN = original_auth
        rwgps_client.RWGPS_USER_ID = original_user
        rwgps_client.RWGPS_API_KEY = original_key
        rwgps_client.RWGPS_PLANNED_COLLECTION_ID = original_collection


def test_rwgps_live_route_details_and_exports():
    original_values = {
        "RWGPS_API_KEY": rwgps_client.RWGPS_API_KEY,
        "RWGPS_AUTH_TOKEN": rwgps_client.RWGPS_AUTH_TOKEN,
        "RWGPS_USER_ID": rwgps_client.RWGPS_USER_ID,
        "RWGPS_PLANNED_COLLECTION_ID": rwgps_client.RWGPS_PLANNED_COLLECTION_ID,
    }
    live_values = _load_rwgps_env_values()
    try:
        for key, value in live_values.items():
            setattr(rwgps_client, key, value)

        route = rwgps_client.get_route("52537422")
        assert_equal(route["ok"], True, "rwgps live route ok")
        assert_equal(route["source"], "rwgps_api", "rwgps live route source")
        assert_equal(route["origin"], "rwgps_api", "rwgps live route top-level origin")
        assert_equal(route["route"]["origin"], "rwgps_api", "rwgps live route origin")
        assert_equal(route["route"]["source"], "rwgps_api", "rwgps live route nested source")
        assert_equal(route["route"]["geometry"]["origin"], "rwgps_api", "rwgps geometry origin")
        assert_equal(route["route"]["cue_sheet"]["origin"], "rwgps_api", "rwgps cue origin")
        assert_equal(route["route"]["export_links"]["origin"], "rwgps_api", "rwgps export links origin")
        assert_equal(route["route"]["raw"]["origin"], "rwgps_api", "rwgps raw meta origin")

        routes = rwgps_client.list_routes(limit=5)
        assert_equal(routes["source"], "rwgps_api", "rwgps live list source")
        assert_equal(routes["origin"], "rwgps_api", "rwgps live list origin")

        collections = rwgps_client.list_collections()
        assert_equal(collections["source"], "rwgps_api", "rwgps live collections source")
        assert_equal(collections["origin"], "rwgps_api", "rwgps live collections origin")
        if collections["collections"]:
            assert_equal(collections["collections"][0]["origin"], "rwgps_api", "rwgps live collections item origin")

        planned = rwgps_client.list_planned_routes(limit=5)
        assert_equal(planned["source"], "rwgps_api", "rwgps live planned source")
        assert_equal(planned["origin"], "rwgps_api", "rwgps live planned origin")

        assert_equal(route["route"]["distance_km"], 28.599, "rwgps live distance km")
        assert_equal(route["route"]["geometry"]["available"], True, "rwgps geometry available")
        assert_equal(route["route"]["cue_sheet"]["available"], True, "rwgps cue sheet available")
        assert_equal(route["route"]["geometry"]["point_count"] > 0, True, "rwgps geometry point count")
        assert_equal(route["route"]["cue_sheet"]["count"] > 0, True, "rwgps cue count")
        assert_equal(route["route"]["export_links"]["missing_features"], ["gpx_url", "tcx_url", "fit_url"], "rwgps missing direct export urls")
        assert_equal(route["integration"]["capabilities"]["can_get_geometry"], True, "rwgps geometry capability")
        assert_equal(route["integration"]["capabilities"]["can_export_gpx"], True, "rwgps gpx capability")
        assert_equal(route["integration"]["capabilities"]["can_export_fit"], False, "rwgps fit capability")

        geometry = rwgps_client.get_route_geometry("52537422")
        assert_equal(geometry["ok"], True, "rwgps geometry helper ok")
        assert_equal(geometry["source"], "rwgps_api", "rwgps geometry source")
        assert_equal(geometry["geometry"]["available"], True, "rwgps geometry helper available")

        cue_sheet = rwgps_client.get_route_cue_sheet("52537422")
        assert_equal(cue_sheet["ok"], True, "rwgps cue helper ok")
        assert_equal(cue_sheet["source"], "rwgps_api", "rwgps cue source")
        assert_equal(cue_sheet["cue_sheet"]["available"], True, "rwgps cue helper available")

        export_links = rwgps_client.get_route_export_links("52537422")
        assert_equal(export_links["ok"], True, "rwgps export links ok")
        assert_equal(export_links["source"], "rwgps_api", "rwgps export source")
        if export_links["export_links"]["gpx_url"] is not None or export_links["export_links"]["tcx_url"] is not None or export_links["export_links"]["fit_url"] is not None:
            raise AssertionError("rwgps unexpected direct export links leaked")

        gpx = rwgps_client.download_route_gpx("52537422")
        assert_equal(gpx["ok"], True, "rwgps gpx build ok")
        if not gpx["content"].startswith("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"):
            raise AssertionError("rwgps gpx content missing xml header")

        tcx = rwgps_client.download_route_tcx("52537422")
        assert_equal(tcx["ok"], True, "rwgps tcx build ok")
        if "<TrainingCenterDatabase" not in tcx["content"]:
            raise AssertionError("rwgps tcx content missing root element")

        fit = rwgps_client.download_route_fit("52537422")
        assert_equal(fit["ok"], False, "rwgps fit unavailable")
        if "FIT export" not in fit["warning"]:
            raise AssertionError("rwgps fit warning missing")

        payload = json.dumps(route, ensure_ascii=False)
        for secret in (rwgps_client.RWGPS_API_KEY, rwgps_client.RWGPS_AUTH_TOKEN):
            if secret and secret in payload:
                raise AssertionError("rwgps route payload leaked a secret")
    finally:
        for key, value in original_values.items():
            setattr(rwgps_client, key, value)


def test_rwgps_cache_source_is_explicit():
    original_cache_path = rwgps_client.RWGPS_ROUTE_CACHE_PATH
    original_request_json = rwgps_client._request_json
    original_values = {
        "RWGPS_API_KEY": rwgps_client.RWGPS_API_KEY,
        "RWGPS_AUTH_TOKEN": rwgps_client.RWGPS_AUTH_TOKEN,
        "RWGPS_USER_ID": rwgps_client.RWGPS_USER_ID,
        "RWGPS_PLANNED_COLLECTION_ID": rwgps_client.RWGPS_PLANNED_COLLECTION_ID,
    }
    live_values = _load_rwgps_env_values()
    with tempfile.TemporaryDirectory() as tmp:
        rwgps_client.RWGPS_ROUTE_CACHE_PATH = Path(tmp) / "rwgps_route_cache.json"
        try:
            for key, value in live_values.items():
                setattr(rwgps_client, key, value)
            import httpx

            headers = {
                "Accept": "application/json",
                "x-rwgps-api-key": rwgps_client.RWGPS_API_KEY,
                "x-rwgps-auth-token": rwgps_client.RWGPS_AUTH_TOKEN,
            }
            raw_route = httpx.get(
                "https://ridewithgps.com/api/v1/routes/52537422.json",
                headers=headers,
                timeout=20,
            ).json()

            def fake_request_json(path, params=None):
                return raw_route

            rwgps_client._request_json = fake_request_json
            initial = rwgps_client.get_route("52537422")
            assert_equal(initial["source"], "rwgps_api", "rwgps cache warm source")

            def fail_request_json(path, params=None):
                raise rwgps_client.RWGPSError("timeout", "RWGPS request timed out")

            rwgps_client._request_json = fail_request_json
            cached = rwgps_client.get_route("52537422")
            assert_equal(cached["source"], "cache", "rwgps cache source")
            assert_equal(cached["origin"], "rwgps_api", "rwgps cache top-level origin")
            assert_equal(cached["route"]["origin"], "rwgps_api", "rwgps cache origin")
            assert_equal(cached["integration"]["source"], "cache", "rwgps cache integration source")
            if not cached["integration"]["warning"]:
                raise AssertionError("rwgps cache missing warning")
        finally:
            rwgps_client._request_json = original_request_json
            rwgps_client.RWGPS_ROUTE_CACHE_PATH = original_cache_path
            for key, value in original_values.items():
                setattr(rwgps_client, key, value)


def test_gate_open_endpoint():
    original_unlock = qbot_qlab_server._unlock_gate_via_hikconnect
    original_last_success = qbot_qlab_server._gate_last_success_monotonic
    original_in_progress = qbot_qlab_server._gate_unlock_in_progress
    root_logger = logging.getLogger()
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    try:
        qbot_qlab_server._gate_last_success_monotonic = 0.0
        qbot_qlab_server._gate_unlock_in_progress = False

        async def fake_unlock():
            return {"status": "ok"}

        qbot_qlab_server._unlock_gate_via_hikconnect = fake_unlock
        missing = asyncio.run(qbot_qlab_server.gate_open())
        assert_equal(missing.status_code, 403, "gate missing token")

        bad = asyncio.run(qbot_qlab_server.gate_open(token="bad"))
        assert_equal(bad.status_code, 403, "gate bad token")

        qbot_qlab_server._gate_last_success_monotonic = time.monotonic()
        limited = asyncio.run(qbot_qlab_server.gate_open(token="test-gate-token"))
        assert_equal(limited.status_code, 429, "gate rate limit")

        qbot_qlab_server._gate_last_success_monotonic = 0.0
        ok = asyncio.run(qbot_qlab_server.gate_open(token="test-gate-token"))
        assert_equal(ok.status_code, 200, "gate open success")
        if ok.body != b'{"status":"ok"}':
            raise AssertionError("gate success body mismatch")

        logs = buffer.getvalue()
        for secret in ("test-account", "test-password", "test-gate-token"):
            if secret in logs:
                raise AssertionError("gate logs leaked a secret")
    finally:
        root_logger.removeHandler(handler)
        qbot_qlab_server._unlock_gate_via_hikconnect = original_unlock
        qbot_qlab_server._gate_last_success_monotonic = original_last_success
        qbot_qlab_server._gate_unlock_in_progress = original_in_progress


def test_qbot_artifact_helpers_and_save_tool():
    original_root = mcp_server.ARTIFACT_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        mcp_server.ARTIFACT_ROOT = Path(tmp)

        assert_equal(
            mcp_server.validate_artifact_relative_path("routes/tuscany/test.md"),
            "routes/tuscany/test.md",
            "artifact path normalization",
        )
        assert_equal(
            mcp_server.artifact_absolute_path("routes/tuscany/test.md"),
            Path(tmp) / "routes" / "tuscany" / "test.md",
            "artifact absolute path",
        )

        rejected_cases = [
            ("../x", "relative_path must not contain .."),
            ("/tmp/x", "relative_path must be relative"),
            ("", "relative_path must not be empty"),
        ]
        for relative_path, error_text in rejected_cases:
            result = json.loads(mcp_server.save_qbot_artifact(relative_path, "x"))
            assert_equal(result["status"], "rejected", f"artifact reject {relative_path!r} status")
            if error_text not in result["error"]:
                raise AssertionError(f"artifact reject {relative_path!r}: missing error text")

        ok = json.loads(mcp_server.save_qbot_artifact("routes/tuscany/test.md", "# note"))
        assert_equal(ok["status"], "ok", "artifact create status")
        assert_equal(ok["overwritten"], False, "artifact create overwritten flag")
        assert_equal(ok["bytes_written"], len("# note".encode("utf-8")), "artifact bytes written")
        if (Path(tmp) / "routes" / "tuscany" / "test.md").read_text(encoding="utf-8") != "# note":
            raise AssertionError("artifact file content mismatch after create")

        reject_existing = json.loads(mcp_server.save_qbot_artifact("routes/tuscany/test.md", "new"))
        assert_equal(reject_existing["status"], "rejected", "existing artifact reject status")
        assert_equal(reject_existing["overwritten"], False, "existing artifact reject overwritten")

        overwrite = json.loads(
            mcp_server.save_qbot_artifact("routes/tuscany/test.md", "updated", overwrite=True)
        )
        assert_equal(overwrite["status"], "ok", "artifact overwrite status")
        assert_equal(overwrite["overwritten"], True, "artifact overwrite overwritten flag")
        if (Path(tmp) / "routes" / "tuscany" / "test.md").read_text(encoding="utf-8") != "updated":
            raise AssertionError("artifact file content mismatch after overwrite")
    mcp_server.ARTIFACT_ROOT = original_root


def test_qbot_artifact_read_list_and_search():
    listing = json.loads(mcp_server.list_qbot_artifacts(limit=1000))
    assert_equal(listing["status"], "ok", "artifact list status")
    paths = [item.get("relative_path") for item in listing.get("artifacts", [])]
    if "routes/tuscany/PROJEKT_Toskania_plan_etapow.md" not in paths:
        raise AssertionError("artifact list missing PROJEKT_Toskania_plan_etapow.md")

    artifact = json.loads(mcp_server.read_qbot_artifact("routes/tuscany/PROJEKT_Toskania_plan_etapow.md"))
    assert_equal(artifact["status"], "ok", "artifact read status")
    assert_equal(artifact["truncated"], False, "artifact read truncated")
    if "Toskania" not in artifact.get("content", ""):
        raise AssertionError("artifact read missing expected content")

    invalid = json.loads(mcp_server.read_qbot_artifact("../x"))
    assert_equal(invalid["status"], "INVALID_PATH", "artifact invalid path status")

    for query in ["Toskania", "Tuscany", "55256628", "55257604", "Bolgheri", "Pienza", "Monteriggioni", "E5"]:
        results = db.search_garage(query)
        artifact_hits = results.get("artifacts", [])
        if not any(item.get("relative_path") == "routes/tuscany/PROJEKT_Toskania_plan_etapow.md" for item in artifact_hits):
            raise AssertionError(f"artifact search missing exact match for query {query!r}")


def test_analyze_rwgps_artifact_surface():
    original_extract = mcp_server.rwgps_extract_artifact_points
    original_client = mcp_server.httpx.Client

    # Pre-built test points: [lat, lon, ele]
    test_points = [
        [52.200, 21.000, 100.0],
        [52.205, 21.005, 105.0],
        [52.210, 21.010, 110.0],
        [52.215, 21.015, 108.0],
        [52.220, 21.020, 112.0],
        [52.225, 21.025, 115.0],
        [52.230, 21.030, 117.0],
        [52.235, 21.035, 120.0],
        [52.240, 21.040, 119.0],
        [52.245, 21.045, 122.0],
    ]

    def mock_extract(path_or_name):
        return test_points

    mcp_server.rwgps_extract_artifact_points = mock_extract

    mock_ways = [
        {
            "geometry": [
                {"lat": 52.200, "lon": 21.000},
                {"lat": 52.205, "lon": 21.005},
                {"lat": 52.210, "lon": 21.010},
            ],
            "tags": {"highway": "residential", "surface": "asphalt", "smoothness": "good"},
        },
        {
            "geometry": [
                {"lat": 52.215, "lon": 21.015},
                {"lat": 52.220, "lon": 21.020},
            ],
            "tags": {"highway": "track", "surface": "gravel", "tracktype": "grade2", "smoothness": "intermediate"},
        },
        {
            "geometry": [
                {"lat": 52.225, "lon": 21.025},
                {"lat": 52.230, "lon": 21.030},
                {"lat": 52.235, "lon": 21.035},
            ],
            "tags": {"highway": "path", "surface": "dirt", "tracktype": "grade3", "smoothness": "bad"},
        },
    ]

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return MockResponse(200, {"elements": mock_ways})

    mcp_server.httpx.Client = MockClient

    try:
        result_json = mcp_server.analyze_rwgps_artifact_surface(
            "rwgps_55257604.gpx", sample_distance_m=777
        )
        result = json.loads(result_json)

        assert_equal(result["ok"], True, "analyze surface ok")
        assert_equal(result["status"], "OK", "analyze surface status")
        assert_equal(result["source"], "rwgps_artifact", "analyze surface source")
        assert_equal(result["point_count"], 10, "analyze point count")
        if "distance_km" not in result:
            raise AssertionError("analyze surface missing distance_km")
        if result["distance_km"] <= 0:
            raise AssertionError("analyze surface distance_km zero")
        if "surface_percentages" not in result:
            raise AssertionError("analyze surface missing surface_percentages")
        if "dominant_surface" not in result:
            raise AssertionError("analyze surface missing dominant_surface")
        if "road_type_percentages" not in result:
            raise AssertionError("analyze surface missing road_type_percentages")
        if "tracktype_percentages" not in result:
            raise AssertionError("analyze surface missing tracktype_percentages")
        if "smoothness_summary" not in result:
            raise AssertionError("analyze surface missing smoothness_summary")
        if not result["smoothness_summary"]:
            raise AssertionError("analyze surface smoothness_summary empty")
        if "confidence" not in result:
            raise AssertionError("analyze surface missing confidence")
        if result["matched_points"] == 0:
            raise AssertionError("analyze surface no matched points")
        if "bounds" not in result:
            raise AssertionError("analyze surface missing bounds")
        if "coverage_pct" not in result:
            raise AssertionError("analyze surface missing coverage_pct")
        if "sampled_points" not in result:
            raise AssertionError("analyze surface missing sampled_points")
    finally:
        mcp_server.httpx.Client = original_client
        mcp_server.rwgps_extract_artifact_points = original_extract


def test_telegram_failed_message_dead_letter():
    original = tg_reply.FAILED_MESSAGES_FILE
    with tempfile.TemporaryDirectory() as tmp:
        tg_reply.FAILED_MESSAGES_FILE = Path(tmp) / "failed.json"
        tg_reply.save_failed_message(123, "test msg", RuntimeError("boom"))
        data = json.loads(tg_reply.FAILED_MESSAGES_FILE.read_text(encoding="utf-8"))
        assert_equal(data[0]["update_id"], 123, "telegram failed update id")
        assert_equal(data[0]["text"], "test msg", "telegram failed text")
    tg_reply.FAILED_MESSAGES_FILE = original


def test_email_failed_reply_dead_letter():
    original = email_reply.FAILED_REPLIES_FILE
    with tempfile.TemporaryDirectory() as tmp:
        email_reply.FAILED_REPLIES_FILE = Path(tmp) / "email_failed.json"
        email_reply.mark_failed_reply("<msg-1>", {"type": "ride", "error": "boom"})
        data = json.loads(email_reply.FAILED_REPLIES_FILE.read_text(encoding="utf-8"))
        assert_equal(data[0]["message_id"], "<msg-1>", "email failed message id")
        assert_equal(data[0]["type"], "ride", "email failed type")
    email_reply.FAILED_REPLIES_FILE = original


def test_cached_call_uses_last_good_value():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cache.json"
        assert_equal(qbot_cache.cached_call(path, "k", lambda: {"value": 1})["value"], 1, "cache initial value")
        cached = qbot_cache.cached_call(path, "k", lambda: {"error": "timeout"})
        assert_equal(cached["value"], 1, "cache fallback value")
        assert_equal(cached["cache_hit"], True, "cache fallback flag")
        assert_equal(cached["cache_reason"], "timeout", "cache fallback reason")


def test_operational_health_summary():
    state = {
        "services": {"q-bot.service": "active"},
        "reports": {"ride_report_cron_enabled": True},
        "messages": {"telegram_failed_count": 0},
        "recent_logs": {"ride_report": ["OK"]},
    }
    assert_equal(op_state.health_summary(state)["level"], "OK", "operational health ok")
    state["messages"]["telegram_failed_count"] = 1
    assert_equal(op_state.health_summary(state)["level"], "WARN", "operational health warning")


def test_openmaps_healthcheck():
    result = json.loads(mcp_server.openmaps_healthcheck())
    assert_equal(isinstance(result.get("ok"), bool), True, "openmaps ok is bool")
    assert_equal(result["status"] in ("OK", "DEGRADED", "ERROR"), True, "openmaps status valid")
    assert_equal(isinstance(result.get("reason"), str) and len(result["reason"]) > 0, True, "openmaps reason not empty")
    assert_equal(result.get("overpass_endpoint"), "https://overpass-api.de/api/interpreter", "openmaps endpoint")
    assert_equal(result.get("cache_status") in ("OK", "DISABLED"), True, "openmaps cache_status valid")


def test_openmaps_query_bbox_mock_overpass_response():
    original_client = mcp_server.httpx.Client

    mock_elements = [
        {"type": "way", "id": 1, "tags": {"highway": "residential", "surface": "asphalt"}},
        {"type": "node", "id": 2, "tags": {"amenity": "cafe"}},
    ]

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return MockResponse(200, {"elements": mock_elements})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_query_bbox(
            south=52.2, west=21.0, north=52.25, east=21.05,
            features=["roads", "amenities"],
        ))
        assert_equal(result["ok"], True, "mock bbox ok")
        assert_equal(result["status"], "OK", "mock bbox status")
        assert_equal(result["source"], "overpass", "mock bbox source")
        assert_equal(len(result["elements"]), 2, "mock bbox elements count")
        assert_equal(bool(result.get("reason")), True, "mock bbox reason not empty")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_query_bbox_no_data():
    original_client = mcp_server.httpx.Client

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return MockResponse(200, {"elements": []})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_query_bbox(
            south=52.2, west=21.0, north=52.25, east=21.05,
        ))
        assert_equal(result["ok"], True, "no_data ok")
        assert_equal(result["status"], "NO_DATA", "no_data status")
        assert_equal(result["elements"], [], "no_data elements empty")
        assert_equal(len(result["reason"]) > 0, True, "no_data reason not empty")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_query_bbox_invalid():
    result1 = json.loads(mcp_server.openmaps_query_bbox(south=91, west=21, north=92, east=22))
    assert_equal(result1["ok"], False, "invalid lat ok")
    assert_equal(result1["status"], "ERROR", "invalid lat status")
    assert_equal(len(result1["reason"]) > 0, True, "invalid lat reason")

    result2 = json.loads(mcp_server.openmaps_query_bbox(south=52, west=21, north=51, east=22))
    assert_equal(result2["ok"], False, "south >= north ok")
    assert "south" in result2["reason"].lower(), "south >= north reason mentions south"

    result3 = json.loads(mcp_server.openmaps_query_bbox(south=52, west=22, north=53, east=21))
    assert_equal(result3["ok"], False, "west >= east ok")
    assert "west" in result3["reason"].lower(), "west >= east reason mentions west"

    result4 = json.loads(mcp_server.openmaps_query_bbox(south=52, west=21, north=62, east=22))
    assert_equal(result4["ok"], False, "too large bbox ok")
    assert_equal(result4["status"], "ERROR", "too large bbox status")
    assert "too large" in result4["reason"].lower() or "exceeds" in result4["reason"].lower(), "too large bbox reason"

    result5 = json.loads(mcp_server.openmaps_query_bbox(south=52, west=21, north=52.1, east=21.1, features=["bogus"]))
    assert_equal(result5["ok"], False, "bogus features ok")
    assert result5["reason"], "bogus features reason"

    result6 = json.loads(mcp_server.openmaps_query_bbox(south=-91, west=0, north=0, east=1))
    assert_equal(result6["ok"], False, "negative out of range ok")


def test_openmaps_enrich_mock_segments():
    original_client = mcp_server.httpx.Client

    test_points = json.dumps([
        {"lat": 52.200, "lon": 21.000, "ele": 100.0},
        {"lat": 52.205, "lon": 21.005, "ele": 105.0},
        {"lat": 52.210, "lon": 21.010, "ele": 110.0},
        {"lat": 52.215, "lon": 21.015, "ele": 108.0},
        {"lat": 52.220, "lon": 21.020, "ele": 112.0},
        {"lat": 52.225, "lon": 21.025, "ele": 115.0},
        {"lat": 52.230, "lon": 21.030, "ele": 117.0},
        {"lat": 52.235, "lon": 21.035, "ele": 120.0},
        {"lat": 52.240, "lon": 21.040, "ele": 119.0},
        {"lat": 52.245, "lon": 21.045, "ele": 122.0},
    ])

    mock_ways = [
        {"geometry": [{"lat": 52.200, "lon": 21.000}, {"lat": 52.205, "lon": 21.005}, {"lat": 52.210, "lon": 21.010}],
         "tags": {"highway": "residential", "surface": "asphalt", "smoothness": "good"}},
        {"geometry": [{"lat": 52.215, "lon": 21.015}, {"lat": 52.220, "lon": 21.020}],
         "tags": {"highway": "track", "surface": "gravel", "tracktype": "grade2", "smoothness": "intermediate"}},
        {"geometry": [{"lat": 52.225, "lon": 21.025}, {"lat": 52.230, "lon": 21.030}, {"lat": 52.235, "lon": 21.035}],
         "tags": {"highway": "path", "surface": "dirt", "tracktype": "grade3", "smoothness": "bad"}},
    ]

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return MockResponse(200, {"elements": mock_ways})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_enrich_rwgps_track(
            points_json=test_points, track_id="test-track", sample_step_m=200))
        assert_equal(result["ok"], True, "enrich ok")
        assert_equal(result["status"], "OK", "enrich status OK")
        assert_equal(result["track_id"], "test-track", "enrich track_id")
        assert_equal(result["source"], "osm_overpass", "enrich source")
        assert_equal(len(result["reason"]) > 0, True, "enrich reason not empty")

        segments = result["segments"]
        assert_equal(len(segments) >= 1, True, "enrich has segments")

        classes = {s["surface_class"] for s in segments}
        assert "paved" in classes or "fast_gravel" in classes or "rough_gravel" in classes or "dirt" in classes, "enrich has valid surface_class"

        for seg in segments:
            assert_equal(seg["source"], "osm_overpass", "segment source")
            assert_equal(isinstance(seg["confidence"], (int, float)), True, "segment confidence is number")
            assert 0.0 <= seg["confidence"] <= 1.0, f"segment confidence {seg['confidence']} out of range"
            assert_equal(len(seg["reason"]) > 0, True, "segment reason not empty")
            assert_equal(seg["from_m"] <= seg["to_m"], True, "segment from <= to")
            assert seg["surface_class"] in ("paved", "fast_gravel", "rough_gravel", "dirt", "unknown"), f"invalid class: {seg['surface_class']}"

        summary = result["summary"]
        for key in ("distance_m", "paved_m", "gravel_m", "rough_m", "unknown_m"):
            assert key in summary, f"summary missing {key}"
            val = summary[key]
            assert isinstance(val, (int, float)), f"summary {key} not a number"
            assert not (isinstance(val, float) and (math.isnan(val) or math.isinf(val))), f"summary {key} NaN/Inf"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_enrich_no_osm_data():
    original_client = mcp_server.httpx.Client

    test_points = json.dumps([
        {"lat": 52.200, "lon": 21.000},
        {"lat": 52.205, "lon": 21.005},
        {"lat": 52.210, "lon": 21.010},
    ])

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code; self._json = json_data
        def json(self): return self._json
        def raise_for_status(self):
            if self.status_code >= 400: raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw): return MockResponse(200, {"elements": []})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_enrich_rwgps_track(
            points_json=test_points, sample_step_m=150))
        assert_equal(result["ok"], True, "no_osm ok")
        assert_equal(result["status"] in ("OK", "NO_DATA", "PARTIAL"), True, "no_osm status valid")
        # When no OSM data, all segments should be unknown with low confidence
        for seg in result["segments"]:
            assert_equal(seg["surface_class"], "unknown", "no_osm unknown class")
            assert seg["confidence"] <= 0.3, f"no_osm confidence {seg['confidence']} <= 0.3"
        assert_equal(len(result["reason"]) > 0, True, "no_osm reason")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_enrich_invalid_json():
    result = json.loads(mcp_server.openmaps_enrich_rwgps_track(
        points_json="not valid json", track_id="x"))
    assert_equal(result["ok"], False, "invalid_json ok")
    assert_equal(result["status"], "ERROR", "invalid_json status")
    assert_equal(len(result["reason"]) > 0, True, "invalid_json reason")
    assert "JSON" in result["reason"], "invalid_json reason mentions JSON"


def test_openmaps_enrich_fewer_than_2_points():
    result = json.loads(mcp_server.openmaps_enrich_rwgps_track(
        points_json='[{"lat": 52.2, "lon": 21.0}]'))
    assert_equal(result["ok"], False, "few points ok")
    assert_equal(result["status"], "ERROR", "few points status")
    assert "2 points" in result["reason"].lower(), "few points reason"


def test_openmaps_enrich_nan_infinity():
    result_clean = json.loads(mcp_server.openmaps_enrich_rwgps_track(
        points_json='[{"lat": 1.0, "lon": 2.0}, {"lat": "NaN", "lon": 3.0}]'))
    assert_equal(result_clean["ok"], False, "nan_inf ok")
    assert_equal(result_clean["status"], "ERROR", "nan_inf status")


def test_openmaps_pois_mock_overpass():
    original_client = mcp_server.httpx.Client

    test_points = json.dumps([
        {"lat": 52.200, "lon": 21.000},
        {"lat": 52.205, "lon": 21.005},
        {"lat": 52.210, "lon": 21.010},
        {"lat": 52.215, "lon": 21.015},
        {"lat": 52.220, "lon": 21.020},
    ])

    mock_elements = [
        {"type": "node", "id": 1, "lat": 52.203, "lon": 21.003,
         "tags": {"amenity": "drinking_water", "name": "Zrodelko"}},
        {"type": "node", "id": 2, "lat": 52.212, "lon": 21.012,
         "tags": {"amenity": "cafe", "name": "Kawiarnia Rowerowa"}},
        {"type": "node", "id": 3, "lat": 52.218, "lon": 21.018,
         "tags": {"shop": "bicycle", "name": "Serwis Rowerowy"}},
        {"type": "node", "id": 4, "lat": 52.230, "lon": 21.040,
         "tags": {"amenity": "shelter"}},
        {"type": "node", "id": 5, "lat": 52.207, "lon": 21.007,
         "tags": {"shop": "convenience", "name": "Zabka"}},
    ]

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code; self._json = json_data
        def json(self): return self._json
        def raise_for_status(self):
            if self.status_code >= 400: raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw): return MockResponse(200, {"elements": mock_elements})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json=test_points, radius_m=500))
        assert_equal(result["ok"], True, "pois ok")
        assert_equal(result["status"], "OK", "pois status")
        assert_equal(result["source"], "osm_overpass", "pois source")
        assert_equal(len(result["pois"]) >= 1, True, "pois has entries")

        types_found = {p["type"] for p in result["pois"]}
        assert "drinking_water" in types_found, "pois has drinking_water"
        assert "cafe" in types_found, "pois has cafe"

        for poi in result["pois"]:
            assert poi["type"] in ("drinking_water", "cafe", "shelter", "shop", "bicycle_service"), f"invalid type {poi['type']}"
            assert_equal(poi["source"], "osm_overpass", "poi source")
            assert isinstance(poi["confidence"], (int, float)), "poi confidence is number"
            assert_equal(len(poi["reason"]) > 0, True, "poi reason not empty")
            assert "lat" in poi and "lon" in poi, "poi has lat/lon"
            assert isinstance(poi["distance_from_track_m"], (int, float)), "poi has distance"
            assert not math.isnan(poi["distance_from_track_m"]), "poi distance not NaN"
            assert isinstance(poi["tags"], dict), "poi has tags"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_pois_no_data():
    original_client = mcp_server.httpx.Client

    class MockR:
        def __init__(self, s, j): self.status_code = s; self._j = j
        def json(self): return self._j
        def raise_for_status(self):
            if self.status_code >= 400: raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw): return MockR(200, {"elements": []})

    mcp_server.httpx.Client = MockClient

    try:
        result = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json='[{"lat":52.2,"lon":21.0},{"lat":52.21,"lon":21.01}]', radius_m=200))
        assert_equal(result["ok"], True, "no_data ok")
        assert_equal(result["status"], "NO_DATA", "no_data status")
        assert_equal(result["pois"], [], "no_data pois empty")
        assert_equal(len(result["reason"]) > 0, True, "no_data reason")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_pois_invalid_json():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json="not json"))
        assert_equal(result["ok"], False, "invjson ok")
        assert_equal(result["status"], "ERROR", "invjson status")
        assert "JSON" in result["reason"], "invjson mentions JSON"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_pois_invalid_radius():
    original_client = mcp_server.httpx.Client
    class _MockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            class _R:
                status_code = 200
                def json(self): return {"elements": []}
                def raise_for_status(self): pass
            return _R()
    mcp_server.httpx.Client = _MockClient
    try:
        result = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json='[{"lat":52.2,"lon":21.0},{"lat":52.21,"lon":21.01}]', radius_m=10))
        assert_equal(result["ok"], True, "radius too small clamped ok")
        assert result["status"] in ("OK", "NO_DATA"), f"small radius clamped {result['status']}"

        result2 = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json='[{"lat":52.2,"lon":21.0},{"lat":52.21,"lon":21.01}]', radius_m=5000))
        assert_equal(result2["ok"], True, "radius too big clamped ok")
        assert result2["status"] in ("OK", "NO_DATA"), f"big radius clamped {result2['status']}"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_pois_fewer_than_2():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_find_pois_near_track(
            points_json='[{"lat":52.2,"lon":21.0}]'))
        assert_equal(result["ok"], False, "few ok")
        assert_equal(result["status"], "ERROR", "few status")
        assert "2 points" in result["reason"].lower(), "few reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_unknown_surface():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        pts = json.dumps([{"lat": 52.2 + i * 0.01, "lon": 21.0 + i * 0.01} for i in range(4)])
        segs = json.dumps([
            {"from_m": 0, "to_m": 1000, "surface_class": "unknown", "confidence": 0.25, "source": "osm_overpass"},
            {"from_m": 1000, "to_m": 2500, "surface_class": "unknown", "confidence": 0.3, "source": "osm_overpass"},
        ])
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json=pts, enriched_segments_json=segs))
        assert_equal(result["ok"], True, "unknown ok")
        types = {r["type"] for r in result["risks"]}
        assert "unknown_surface" in types, "has unknown_surface"
        for r in result["risks"]:
            assert r["type"] in ("unknown_surface",), f"unexpected type {r['type']}"
            assert r["severity"] in ("LOW", "MEDIUM", "HIGH"), f"bad severity {r['severity']}"
            assert isinstance(r["confidence"], (int, float)), "conf not number"
            assert bool(r["reason"]), "reason empty"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_private_access():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        pts = json.dumps([{"lat": 52.2, "lon": 21.0}, {"lat": 52.21, "lon": 21.01}])
        segs = json.dumps([
            {"from_m": 0, "to_m": 500, "surface_class": "paved", "confidence": 0.9, "access": "private", "source": "osm_overpass"},
            {"from_m": 500, "to_m": 1000, "surface_class": "fast_gravel", "confidence": 0.8, "bicycle": "no", "source": "osm_overpass"},
        ])
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json=pts, enriched_segments_json=segs))
        assert_equal(result["ok"], True, "access ok")
        types = {r["type"] for r in result["risks"]}
        assert "private_access" in types, "has private_access"
        pa = [r for r in result["risks"] if r["type"] == "private_access"]
        assert_equal(len(pa), 2, "two private_access risks")
        for r in pa:
            assert_equal(r["severity"], "HIGH", "private_access severity HIGH")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_steep_climb_and_rough_descent():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        pts = json.dumps([
            {"lat": 52.2, "lon": 21.0, "ele": 100, "distance_m": 0},
            {"lat": 52.201, "lon": 21.001, "ele": 250, "distance_m": 200},
            {"lat": 52.202, "lon": 21.002, "ele": 260, "distance_m": 400},
            {"lat": 52.203, "lon": 21.003, "ele": 150, "distance_m": 600},
            {"lat": 52.204, "lon": 21.004, "ele": 50, "distance_m": 800},
        ])
        segs = json.dumps([
            {"from_m": 0, "to_m": 200, "surface_class": "rough_gravel", "confidence": 0.7, "source": "osm_overpass"},
            {"from_m": 500, "to_m": 800, "surface_class": "dirt", "confidence": 0.65, "source": "osm_overpass"},
        ])
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json=pts, enriched_segments_json=segs))
        assert_equal(result["ok"], True, "climb ok")
        types = {r["type"] for r in result["risks"]}
        assert "steep_unpaved_climb" in types, "has climb"
        climbers = [r for r in result["risks"] if r["type"] == "steep_unpaved_climb"]
        for r in climbers:
            assert_equal(r["severity"], "HIGH", "climb severity HIGH")
            assert_equal(r["source"], "track_elevation", "climb source")
            assert "grade" in r["reason"] or "%" in r["reason"], "climb reason mentions grade"
        descenders = [r for r in result["risks"] if r["type"] == "rough_descent"]
        for r in descenders:
            assert_equal(r["severity"], "MEDIUM", "descent severity MEDIUM")
            assert_equal(r["source"], "track_elevation", "descent source")
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_long_no_resupply():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        pts = json.dumps([{"lat": 52.2 + i * 0.1, "lon": 21.0 + i * 0.1} for i in range(10)])
        pois = json.dumps([
            {"type": "drinking_water", "nearest_track_distance_m_on_route": 5000, "source": "osm_overpass", "confidence": 0.9},
            {"type": "cafe", "nearest_track_distance_m_on_route": 60000, "source": "osm_overpass", "confidence": 0.8},
            {"type": "shop", "nearest_track_distance_m_on_route": 90000, "source": "osm_overpass", "confidence": 0.8},
        ])
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json=pts, pois_json=pois))
        assert_equal(result["ok"], True, "supply ok")
        types = {r["type"] for r in result["risks"]}
        assert "long_no_resupply" in types, "has long_no_resupply"
        for r in result["risks"]:
            if r["type"] == "long_no_resupply":
                assert "km" in r["reason"].lower(), "resupply reason mentions km"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_invalid_json():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_detect_route_risks(points_json="bad"))
        assert_equal(result["ok"], False, "bad points ok")
        assert_equal(result["status"], "ERROR", "bad points status")
        assert "JSON" in result["reason"], "bad points reason"

        result2 = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json='[{"lat":52,"lon":21},{"lat":52.1,"lon":21.1}]',
            enriched_segments_json="bad"))
        assert_equal(result2["ok"], False, "bad segs ok")
        assert "JSON" in result2["reason"], "bad segs reason"

        result3 = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json='[{"lat":52,"lon":21},{"lat":52.1,"lon":21.1}]',
            pois_json="bad"))
        assert_equal(result3["ok"], False, "bad pois ok")
        assert "JSON" in result3["reason"], "bad pois reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_fewer_than_2():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json='[{"lat":52.2,"lon":21.0}]'))
        assert_equal(result["ok"], False, "few ok")
        assert_equal(result["status"], "ERROR", "few status")
        assert "2 points" in result["reason"].lower(), "few reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_risks_no_risks():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        pts = json.dumps([{"lat": 52.2, "lon": 21.0}, {"lat": 52.21, "lon": 21.01}])
        segs = json.dumps([
            {"from_m": 0, "to_m": 1000, "surface_class": "paved", "confidence": 0.95,
             "access": "yes", "bicycle": "yes", "source": "osm_overpass"},
        ])
        result = json.loads(mcp_server.openmaps_detect_route_risks(
            points_json=pts, enriched_segments_json=segs))
        assert_equal(result["ok"], True, "no risks ok")
        assert_equal(result["status"], "NO_DATA", "no risks status")
        assert_equal(result["risks"], [], "no risks empty")
        assert "no" in result["reason"].lower() or "detected" in result["reason"].lower(), "no risks reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_snapshot_happy_path():
    original_client = mcp_server.httpx.Client
    original_enrich = mcp_server.openmaps_enrich_rwgps_track
    original_pois = mcp_server.openmaps_find_pois_near_track
    original_risks = mcp_server.openmaps_detect_route_risks

    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")

    mcp_server.httpx.Client = _BlockClient

    mock_segs = json.dumps({"ok": True, "status": "OK", "segments": [
        {"from_m": 0, "to_m": 1500, "distance_m": 1500, "road_type": "residential",
         "surface": "asphalt", "surface_class": "paved", "confidence": 0.9,
         "source": "osm_overpass", "reason": "matched at 5m"},
        {"from_m": 1500, "to_m": 3000, "distance_m": 1500, "road_type": "track",
         "surface": "gravel", "surface_class": "fast_gravel", "tracktype": "grade2",
         "confidence": 0.8, "source": "osm_overpass", "reason": "matched at 3m"},
    ], "summary": {"distance_m": 3000, "paved_m": 1500, "gravel_m": 1500, "rough_m": 0, "dirt_m": 0, "unknown_m": 0},
     "source": "osm_overpass", "reason": "2 segments"})

    mock_pois = json.dumps({"ok": True, "status": "OK", "pois": [
        {"type": "drinking_water", "name": "Zrodelko", "lat": 52.203, "lon": 21.003,
         "distance_from_track_m": 50, "nearest_track_distance_m": 50,
         "nearest_track_distance_m_on_route": 500, "tags": {"amenity": "drinking_water"},
         "source": "osm_overpass", "confidence": 0.9, "reason": "drinking_water: Zrodelko"},
    ], "source": "osm_overpass", "reason": "1 POI"})

    mock_risks = json.dumps({"ok": True, "status": "OK", "risks": [
        {"type": "unknown_surface", "from_m": 1500, "to_m": 3000, "lat": 52.21, "lon": 21.01,
         "severity": "LOW", "confidence": 0.8, "source": "osm_overpass",
         "reason": "segment surface unknown"},
    ], "source": "route_analysis", "reason": "1 risk"})

    try:
        mcp_server.openmaps_enrich_rwgps_track = lambda **kw: mock_segs
        mcp_server.openmaps_find_pois_near_track = lambda **kw: mock_pois
        mcp_server.openmaps_detect_route_risks = lambda **kw: mock_risks

        pts = json.dumps([{"lat": 52.2 + i * 0.01, "lon": 21.0 + i * 0.01} for i in range(4)])
        result = json.loads(mcp_server.openmaps_build_route_snapshot(
            points_json=pts, track_id="t1", route_id="r1"))

        assert_equal(result["ok"], True, "snapshot ok")
        assert_equal(result["status"], "OK", "snapshot status")
        assert_equal(result["route_id"], "r1", "route_id")
        assert_equal(result["track_id"], "t1", "track_id")
        assert_equal(result["source"], "openmaps_pipeline", "source")

        assert result.get("generated_at") and "T" in result["generated_at"], "has ISO timestamp"
        assert_equal(len(result.get("input_track_hash", "")), 16, "hash length 16")
        assert_equal(result.get("osm_query_version"), "openmaps_v1", "osm_query_version")

        assert_equal(len(result["segments"]), 2, "2 segments")
        assert_equal(len(result["pois"]), 1, "1 POI")
        assert_equal(len(result["risks"]), 1, "1 risk")

        s = result["summary"]
        assert_equal(s["distance_m"], 3000, "summary dist")
        assert_equal(s["paved_m"], 1500, "summary paved")
        assert_equal(s["gravel_m"], 1500, "summary gravel")
        assert_equal(s["poi_count"], 1, "poi_count")
        assert_equal(s["risk_count"], 1, "risk_count")

        assert_equal(bool(result["reason"]), True, "reason not empty")
    finally:
        mcp_server.httpx.Client = original_client
        mcp_server.openmaps_enrich_rwgps_track = original_enrich
        mcp_server.openmaps_find_pois_near_track = original_pois
        mcp_server.openmaps_detect_route_risks = original_risks


def test_openmaps_snapshot_poi_no_data():
    original_enrich = mcp_server.openmaps_enrich_rwgps_track
    original_pois = mcp_server.openmaps_find_pois_near_track
    original_risks = mcp_server.openmaps_detect_route_risks
    original_client = mcp_server.httpx.Client

    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")

    mcp_server.httpx.Client = _BlockClient

    mock_segs = json.dumps({"ok": True, "status": "OK", "segments": [
        {"from_m": 0, "to_m": 1000, "distance_m": 1000, "surface_class": "paved",
         "confidence": 0.9, "source": "osm_overpass", "reason": "ok"},
    ], "summary": {"distance_m": 1000, "paved_m": 1000, "gravel_m": 0, "rough_m": 0, "dirt_m": 0, "unknown_m": 0},
     "source": "osm_overpass", "reason": "1 segment"})

    mock_pois = json.dumps({"ok": True, "status": "NO_DATA", "pois": [],
                             "source": "osm_overpass", "reason": "no POIs"})

    mock_risks = json.dumps({"ok": True, "status": "NO_DATA", "risks": [],
                              "source": "route_analysis", "reason": "no risks"})

    try:
        mcp_server.openmaps_enrich_rwgps_track = lambda **kw: mock_segs
        mcp_server.openmaps_find_pois_near_track = lambda **kw: mock_pois
        mcp_server.openmaps_detect_route_risks = lambda **kw: mock_risks

        pts = json.dumps([{"lat": 52.2, "lon": 21.0}, {"lat": 52.21, "lon": 21.01}])
        result = json.loads(mcp_server.openmaps_build_route_snapshot(points_json=pts))

        assert_equal(result["ok"], True, "nodata ok")
        assert result["status"] in ("OK", "PARTIAL"), f"nodata status {result['status']}"
        assert_equal(len(result["pois"]), 0, "empty pois")
        assert_equal(len(result["risks"]), 0, "empty risks")
        assert_equal(result["summary"]["poi_count"], 0, "zero poi_count")
        assert_equal(result["summary"]["risk_count"], 0, "zero risk_count")
        has_poi_warning = any(w.get("stage") == "pois" for w in result.get("warnings", []))
        assert has_poi_warning, "has pois warning"
    finally:
        mcp_server.httpx.Client = original_client
        mcp_server.openmaps_enrich_rwgps_track = original_enrich
        mcp_server.openmaps_find_pois_near_track = original_pois
        mcp_server.openmaps_detect_route_risks = original_risks


def test_openmaps_snapshot_invalid_json():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_build_route_snapshot(points_json="bad"))
        assert_equal(result["ok"], False, "invjson ok")
        assert_equal(result["status"], "ERROR", "invjson status")
        assert "JSON" in result["reason"], "invjson reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_snapshot_fewer_than_2():
    original_client = mcp_server.httpx.Client
    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")
    mcp_server.httpx.Client = _BlockClient
    try:
        result = json.loads(mcp_server.openmaps_build_route_snapshot(
            points_json='[{"lat":52.2,"lon":21.0}]'))
        assert_equal(result["ok"], False, "few ok")
        assert_equal(result["status"], "ERROR", "few status")
        assert "2 points" in result["reason"].lower(), "few reason"
    finally:
        mcp_server.httpx.Client = original_client


def test_openmaps_snapshot_no_nan():
    original_enrich = mcp_server.openmaps_enrich_rwgps_track
    original_pois = mcp_server.openmaps_find_pois_near_track
    original_risks = mcp_server.openmaps_detect_route_risks
    original_client = mcp_server.httpx.Client

    class _BlockClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            raise RuntimeError(f"real Overpass POST blocked in smoke test: {url}")

    mcp_server.httpx.Client = _BlockClient

    mock_all = json.dumps({"ok": True, "status": "OK", "segments": [
        {"from_m": 0, "to_m": 1000, "distance_m": 1000, "surface_class": "paved",
         "confidence": 0.9, "source": "osm_overpass", "reason": "ok"},
    ], "summary": {"distance_m": 1000, "paved_m": 1000, "gravel_m": 0, "rough_m": 0, "dirt_m": 0, "unknown_m": 0},
     "source": "osm_overpass", "reason": "ok"})

    mock_pois = json.dumps({"ok": True, "status": "OK", "pois": [], "source": "osm_overpass", "reason": "none"})
    mock_risks = json.dumps({"ok": True, "status": "NO_DATA", "risks": [], "source": "route_analysis", "reason": "none"})

    try:
        mcp_server.openmaps_enrich_rwgps_track = lambda **kw: mock_all
        mcp_server.openmaps_find_pois_near_track = lambda **kw: mock_pois
        mcp_server.openmaps_detect_route_risks = lambda **kw: mock_risks

        pts = json.dumps([{"lat": 52.2, "lon": 21.0}, {"lat": 52.21, "lon": 21.01}])
        result = json.loads(mcp_server.openmaps_build_route_snapshot(points_json=pts))

        def _check_no_nan(obj, path=""):
            import math
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    raise AssertionError(f"NaN/Inf at {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check_no_nan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check_no_nan(v, f"{path}[{i}]")
        _check_no_nan(result, "root")
    finally:
        mcp_server.httpx.Client = original_client
        mcp_server.openmaps_enrich_rwgps_track = original_enrich
        mcp_server.openmaps_find_pois_near_track = original_pois
        mcp_server.openmaps_detect_route_risks = original_risks


def test_report_status_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        single = Path(tmp) / "daily.json"
        qbot_report_status.mark_single_report(single, "2026-05-19", {"telegram": "sent", "email": "failed"})
        assert_equal(qbot_report_status.single_report_complete(single, "2026-05-19"), False, "partial daily report incomplete")
        qbot_report_status.mark_single_report(single, "2026-05-19", {"telegram": "sent", "email": "sent"})
        assert_equal(qbot_report_status.single_report_complete(single, "2026-05-19"), True, "complete daily report")

        activity = Path(tmp) / "rides.json"
        qbot_report_status.mark_activity_report(activity, "a1", "Ride", "sent", channels={"telegram": "sent", "email": "sent"})
        assert_equal(qbot_report_status.activity_report_complete(activity, "a1"), True, "complete ride report")


def main() -> int:
    tests = [
        test_readiness,
        test_gear_mapper,
        test_memory_append,
        test_email_template_single_call,
        test_email_template_weight_fallback_label,
        test_email_template_event_banner_local_cid,
        test_daily_coach_decision_and_alerts,
        test_ride_lesson_decoupling,
        test_weekly_review_flags_blockers,
        test_ride_protocol,
        test_decoupling_display,
        test_recovery_select_morning_cross_midnight,
        test_recovery_ignores_incomplete_today,
        test_recovery_sleep_without_hrv,
        test_recovery_latest_end_time_wins,
        test_recovery_no_records,
        test_sleep_data_date_marker,
        test_ride_readiness_sleep_data_date_payload,
        test_route_surface_cache_helpers,
        test_rwgps_manifest_fallback_is_explicit,
        test_rwgps_error_payload_has_origin,
        test_rwgps_live_route_details_and_exports,
        test_rwgps_cache_source_is_explicit,
        test_gate_open_endpoint,
        test_qbot_artifact_helpers_and_save_tool,
        test_qbot_artifact_read_list_and_search,
        test_analyze_rwgps_artifact_surface,
        test_telegram_failed_message_dead_letter,
        test_email_failed_reply_dead_letter,
        test_cached_call_uses_last_good_value,
        test_operational_health_summary,
        test_openmaps_healthcheck,
        test_openmaps_query_bbox_mock_overpass_response,
        test_openmaps_query_bbox_no_data,
        test_openmaps_query_bbox_invalid,
        test_openmaps_enrich_mock_segments,
        test_openmaps_enrich_no_osm_data,
        test_openmaps_enrich_invalid_json,
        test_openmaps_enrich_fewer_than_2_points,
        test_openmaps_enrich_nan_infinity,
        test_openmaps_pois_mock_overpass,
        test_openmaps_pois_no_data,
        test_openmaps_pois_invalid_json,
        test_openmaps_pois_invalid_radius,
        test_openmaps_pois_fewer_than_2,
        test_openmaps_risks_unknown_surface,
        test_openmaps_risks_private_access,
        test_openmaps_risks_steep_climb_and_rough_descent,
        test_openmaps_risks_long_no_resupply,
        test_openmaps_risks_invalid_json,
        test_openmaps_risks_fewer_than_2,
        test_openmaps_risks_no_risks,
        test_openmaps_snapshot_happy_path,
        test_openmaps_snapshot_poi_no_data,
        test_openmaps_snapshot_invalid_json,
        test_openmaps_snapshot_fewer_than_2,
        test_openmaps_snapshot_no_nan,
        test_report_status_helpers,
    ]
    for test in tests:
        test()
        print(f"OK {test.__name__}")
    print(f"OK {len(tests)} smoke tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
