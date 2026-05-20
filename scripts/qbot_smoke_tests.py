#!/usr/bin/env python3
"""Local smoke tests for critical QBot paths."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")

import db
import email_template
import mcp_server
import email_reply_processor as email_reply
import qbot_cache
import qbot_coach
import qbot_report_status
import scripts.qbot_operational_state as op_state
import telegram_reply_processor as tg_reply
from qbot_garage_mapper import classify_gear_text
from qbot_readiness import evaluate_readiness
from qbot_recovery import select_recovery_records
from ride_report import build_ride_protocol


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


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
    protocol = build_ride_protocol({
        "aktywnosc": {
            "distance": 90000,
            "moving_time": 12000,
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
        "nawierzchnia": {},
        "bike": {},
        "porownanie_podobne": [],
        "ostatnie_dlugie_jazdy": [],
    })
    assert_equal(protocol["health"]["verdict"], "ODPUSC", "ride protocol red flag")
    assert_equal(protocol["long_rides"]["split"]["available"], True, "long ride split available")


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
        test_daily_coach_decision_and_alerts,
        test_ride_lesson_decoupling,
        test_weekly_review_flags_blockers,
        test_ride_protocol,
        test_recovery_select_morning_cross_midnight,
        test_recovery_ignores_incomplete_today,
        test_recovery_sleep_without_hrv,
        test_recovery_latest_end_time_wins,
        test_recovery_no_records,
        test_route_surface_cache_helpers,
        test_telegram_failed_message_dead_letter,
        test_email_failed_reply_dead_letter,
        test_cached_call_uses_last_good_value,
        test_operational_health_summary,
        test_report_status_helpers,
    ]
    for test in tests:
        test()
        print(f"OK {test.__name__}")
    print(f"OK {len(tests)} smoke tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
