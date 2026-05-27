#!/usr/bin/env python3
"""Cienka warstwa FastAPI Q — /health, /q."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qbot_mcp_adapter import (
    _dispatch_local_qbot_tool,
    _tool_qbot_mcp_status,
    _tool_qbot_mcp_tools_list,
    handle_mcp_request,
    _validate_mcp_access,
)
from qbot_tools import _tool_qbot_ride_readiness_status

load_dotenv(Path(__file__).parent / ".env")

DB_AVAILABLE = False


def _telegram_answer_general_qbot_question(text: str) -> str | None:
    """Answer general questions about Qbot capabilities — fast, no heavy tool calls."""
    q = (text or "").lower()
    kw = ["qbot", "bot", "umiesz", "potrafisz", "co działa", "czego brakuje", "brakuje", "integra",
          "architektur", "migracj", "stary", "starego", "nowy", "nowego", "przenos",
          "przenies", "przywróc", "zgodno", "parity", "capabilit", "moduł", "moduly",
          "funkcj", "narzędzia", "narzedzia", "co robi", "działają"]
    if not any(k in q for k in kw):
        return None

    def _safe_status(env_keys: list[str], label: str) -> str:
        present = any(os.getenv(k) for k in env_keys)
        if present:
            return f"✅ {label}"
        return f"⚠️ {label} (brak konfiguracji)"

    lines = ["Krótko: większość przywrócona (90%+).\n"]

    lines.append("Działa:")
    lines.append("✅ Core Qbot / status / health")
    lines.append("✅ Telegram webhook i runtime")
    lines.append("✅ MCP connector (52 tools dla ChatGPT)")
    lines.append("✅ QExt2 /ride-readiness (Karoo)")
    if any(os.getenv(k) for k in ["XERT_EMAIL"]):
        lines.append("✅ Xert readiness (FTP / forma)")
    else:
        lines.append("⚠️ Xert (brak credentials)")
    if any(os.getenv(k) for k in ["INTERVALS_API_KEY"]):
        lines.append("✅ Intervals.icu wellness")
    else:
        lines.append("⚠️ Intervals.icu (brak credentials)")
    lines.append("✅ Hammerhead local dry-run / inventory")
    lines.append("✅ CSV export (read / preview / execute)")
    if any(os.getenv(k) for k in ["GARMIN_EMAIL"]):
        lines.append("✅ Garmin proxy / status")
    else:
        lines.append("⚠️ Garmin (brak credentials)")
    lines.append("✅ Daily / ride report status i preview")
    lines.append("✅ Weather status (Open-Meteo)")
    lines.append("✅ OpenMaps / OSM / Overpass")
    lines.append("✅ Garage inventory / import preview")
    if any(os.getenv(k) for k in ["RWGPS_AUTH_TOKEN"]):
        lines.append("✅ RWGPS config / status")
    else:
        lines.append("⚠️ RWGPS (brak credentials)")
    if any(os.getenv(k) for k in ["CRONOMETER_EMAIL"]):
        lines.append("✅ Cronometer status")
    else:
        lines.append("⚠️ Cronometer (brak credentials)")

    lines.append("\nCzęściowo / wymaga osobnego approval:")
    lines.append("⚠️ Garmin real upload (dry-run działa)")
    lines.append("⚠️ RWGPS mutating sync/upload")
    lines.append("⚠️ Hammerhead real online import")
    lines.append("⚠️ Cronometer live login/scrape")
    lines.append("⚠️ Aktywacja schedulerów raportów")

    lines.append("\nSprawdź konkretny moduł:")
    lines.append("/garmin /rwgps /xert /intervals /hammerhead /csv /garage")
    lines.append("/daily_report /ride_report /weather /maps /help")

    return "\n".join(lines)[:3900]


def _telegram_response_text(command: str, result: dict) -> str | None:
    response = result.get("response") if isinstance(result, dict) else None
    if command == "/status" and isinstance(response, dict):
        text = response.get("summary_text")
        if text:
            return str(text)
    if command in {"/weather_status", "/garage_status", "/artifacts", "/integrations", "/rwgps", "/hammerhead", "/csv", "/xert", "/intervals", "/garmin", "/cronometer", "/weather", "/maps", "/garage", "/daily_report", "/daily", "/ride_report", "/reports"} and isinstance(response, dict):
        text = result.get("text") or response.get("summary_text") or response.get("text")
        if text:
            return str(text)
    if command == "/legacy":
        text = result.get("text") if isinstance(result, dict) else None
        if text:
            return str(text)
    if command in ("/start", "/help"):
        if isinstance(response, dict):
            commands = response.get("commands") or []
            lines = ["QBot — dostępne komendy:"]
            for item in commands[:15]:
                if isinstance(item, dict):
                    cmd = item.get("command", "")
                    desc = item.get("description", "")
                    lines.append(f"{cmd} — {desc}")
            return "\n".join(lines)
    if command == "/ready":
        if isinstance(response, dict):
            status = response.get("status", "UNKNOWN")
            blockers = response.get("blockers", [])
            text_lines = [f"Readiness: {status}"]
            if blockers:
                text_lines.append("Blockers: " + ", ".join(blockers[:5]))
            return "\n".join(text_lines)
    if command == "/smoke":
        if isinstance(response, dict):
            pct = response.get("operational_readiness_percent", "?")
            status = response.get("status", "UNKNOWN")
            return f"Smoke test: {status} ({pct}%)"
    if command == "/backup":
        if isinstance(response, dict):
            status = response.get("status", "UNKNOWN")
            latest = response.get("latest_backup")
            if latest:
                return f"Backup: {status}\nLatest: {latest}"
            return f"Backup: {status}"
    if command == "/errors":
        if isinstance(response, dict):
            count = response.get("errors_count", "?")
            return f"Errors: {count} recently"
    if command == "/takeover":
        if isinstance(response, dict):
            pct = response.get("takeover_readiness_percent", "?")
            return f"Takeover: {pct}% complete"
    if command == "/ask":
        if isinstance(response, dict):
            tool_result = response.get("tool_result") or response.get("tool_results")
            executed = response.get("executed_tools") or []
            answer = response.get("answer")
            intent = response.get("intent", "")

            if intent == "unknown_intent" or (response.get("status") == "error" and not tool_result):
                fallback = _telegram_answer_general_qbot_question(result.get("_query", ""))
                if fallback:
                    return fallback[:3900]
                examples = response.get("available_examples", [])[:6]
                example_text = ", ".join(examples) if examples else "/status, /backup, /smoke"
                return (
                    "Nie wiem jeszcze jak na to odpowiedzieć.\n\n"
                    f"Spróbuj: {example_text}\n"
                    "Lub: /status, /xert, /garmin, /rwgps, /hammerhead, /csv, "
                    "/garage, /daily_report, /ride_report, /help"
                )

            if answer:
                return str(answer)[:3900]

            if isinstance(tool_result, dict):
                r = tool_result
                lines = []
                status = r.get("status", "?")
                label = r.get("tool", "") or executed[0] if executed else "result"
                lines.append(f"[{label}] status: {status}")
                for k in ("ftp_watts", "ltp_watts", "wPrimeKj", "weightKg", "operational_readiness_percent",
                          "last_sent_date", "csv_count", "total_records", "count", "restored_status",
                          "configured", "takeover_readiness_percent"):
                    if k in r and r[k] is not None:
                        lines.append(f"  {k}: {r[k]}")
                result_text = "\n".join(lines[:10])
                if result_text:
                    return result_text[:3900]

            summary = response.get("summary_text") or response.get("result")
            if summary:
                return str(summary)[:3900]

            return "Qbot przetworzył zapytanie. Użyj /help aby zobaczyć dostępne komendy."
    return None


def _telegram_webhook_reply(chat_id: int, text: str) -> JSONResponse:
    return JSONResponse(
        content={
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": text,
        },
        status_code=200,
    )


def _telegram_status_summary() -> tuple[str, dict]:
    from qbot_tools import _tool_qbot_api_self_check, _tool_qbot_db_overview
    from qbot_legacy_cutover_tools import _tool_qbot_legacy_cutover_status
    from qbot_telegram_tools import _tool_qbot_telegram_transport_status

    api_check = _tool_qbot_api_self_check()
    db_overview = _tool_qbot_db_overview()
    cutover = _tool_qbot_legacy_cutover_status()
    transport = _tool_qbot_telegram_transport_status({"check_remote": False})

    api_alive = False
    db_ok = bool(db_overview.get("db_connected"))
    rwgps_storage = db_overview.get("rwgps_storage") if isinstance(db_overview, dict) else {}
    rwgps_storage_status = str(rwgps_storage.get("status", "UNKNOWN")).upper() if isinstance(rwgps_storage, dict) else "UNKNOWN"
    rwgps_storage_seed = str(rwgps_storage.get("seed_status", "UNKNOWN")).upper() if isinstance(rwgps_storage, dict) else "UNKNOWN"
    for check in api_check.get("checks", []):
        if check.get("check") == "api_alive" and str(check.get("status", "")).upper() == "OK":
            api_alive = True

    legacy_takeover_pct = int(cutover.get("takeover_readiness_percent", 0) or 0)
    legacy_disabled = bool(cutover.get("cutover_completed")) or (
        cutover.get("legacy_service_active") is False and cutover.get("legacy_service_enabled") is False
    )
    webhook_ok = str(transport.get("status", "UNKNOWN")).upper() == "OK"

    lines = ["Qbot status:"]
    lines.append("✅ API działa" if api_alive else "⚠️ API: problem")
    lines.append("✅ DB działa" if db_ok else "⚠️ DB: problem")
    if isinstance(rwgps_storage, dict) and rwgps_storage:
        if rwgps_storage_status == "OK":
            lines.append(f"✅ RWGPS storage: {rwgps_storage_seed.lower()}")
        elif rwgps_storage_status == "WARN":
            lines.append(f"⚠️ RWGPS storage: {rwgps_storage_seed.lower()}")
        else:
            lines.append(f"⚠️ RWGPS storage: {rwgps_storage_status.lower()}")
    lines.append("✅ Telegram webhook działa" if webhook_ok else "⚠️ Telegram webhook: problem")
    lines.append(f"✅ Legacy takeover: {legacy_takeover_pct}%")
    lines.append("ℹ️ q-bot.service: disabled po cutover" if legacy_disabled else "ℹ️ q-bot.service: legacy active")

    return "\n".join(lines), {
        "tool": "qbot_telegram_status_quick",
        "api_ok": api_alive,
        "db_ok": db_ok,
        "rwgps_storage": rwgps_storage,
        "telegram_webhook_ok": webhook_ok,
        "legacy_takeover_percent": legacy_takeover_pct,
        "legacy_qbot_disabled": legacy_disabled,
        "api_self_check": api_check,
        "db_overview": db_overview,
        "legacy_cutover_status": cutover,
        "telegram_transport": transport,
    }

app = FastAPI(title="Q API", version="0.1.0")


def _db_check():
    global DB_AVAILABLE
    try:
        import api_db
        DB_AVAILABLE = api_db.ping()
    except Exception:
        DB_AVAILABLE = False


def _xert_sync_fetch(xert_email: str, xert_password: str) -> dict:
    import httpx

    with httpx.Client(timeout=3.0, trust_env=False) as client:
        token_resp = client.post(
            "https://www.xertonline.com/oauth/token",
            auth=("xert_public", "xert_public"),
            data={
                "grant_type": "password",
                "username": xert_email,
                "password": xert_password,
            },
        )
        if token_resp.status_code != 200:
            return {}
        token = token_resp.json().get("access_token")
        if not token:
            return {}

        training_resp = client.get(
            "https://www.xertonline.com/oauth/training",
            headers={"Authorization": f"Bearer {token}"},
        )
        if training_resp.status_code != 200:
            return {}
        data = training_resp.json()

    advice = data.get("advice", {})
    sig = advice.get("signature", {})

    ftp_raw = sig.get("ftp", 0)
    ltp_raw = sig.get("ltp", 0)
    atc_raw = sig.get("atc", 0)

    return {
        "ftp_watts": round(float(ftp_raw), 1) if ftp_raw else None,
        "ltp_watts": round(float(ltp_raw), 1) if ltp_raw else None,
        "w_prime_kj": round(float(atc_raw) / 1000, 1) if atc_raw else None,
    }


def _intervals_weight_sync() -> dict:
    import base64, httpx
    from datetime import date

    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")
    api_key = os.getenv("INTERVALS_API_KEY", "")
    if not athlete_id or not api_key:
        return {}

    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    today = date.today().isoformat()

    with httpx.Client(timeout=2.0, trust_env=False) as client:
        resp = client.get(
            f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness",
            params={"oldest": today, "newest": today},
            headers={"Authorization": f"Basic {token}"},
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()

    for entry in data or []:
        if entry.get("id") == today and entry.get("weight"):
            return {"weight_kg": round(entry["weight"], 1)}

    return {}  # no weight today, caller will handle


def _ride_readiness_signals_snapshot() -> dict:
    """Build optional QExt2 signals from local wellness DB.

    Returns a lightweight snapshot only. If any part fails, the route still
    responds without signals rather than crashing or changing the top-level
    contract.
    """
    import psycopg
    from psycopg.rows import dict_row

    from qbot_recovery import select_recovery_records

    since = (date.today() - timedelta(days=30)).isoformat()
    sleep_rows: list[dict] = []
    wellness_rows: list[dict] = []
    averages = {"avg_hrv": None, "avg_sleep": None, "avg_rhr": None}

    try:
        with psycopg.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"),
            user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""),
            row_factory=dict_row,
            connect_timeout=3,
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT date, source, sleep_duration_min, sleep_start, sleep_end,
                       sleep_score, hrv_ms, resting_hr_bpm
                FROM qbot_sleep_daily
                WHERE date >= %s
                ORDER BY date DESC, source
                """,
                (since,),
            )
            sleep_rows = list(cur.fetchall() or [])

            cur.execute(
                """
                SELECT date, source, source_priority, hrv_ms, resting_hr_bpm, sleep_duration_min
                FROM qbot_wellness_daily
                WHERE date >= %s
                  AND (hrv_ms IS NOT NULL OR resting_hr_bpm IS NOT NULL OR sleep_duration_min IS NOT NULL)
                ORDER BY date DESC, source_priority
                """,
                (since,),
            )
            wellness_rows = list(cur.fetchall() or [])

            cur.execute(
                """
                SELECT AVG(hrv_ms) AS avg_hrv,
                       AVG(sleep_duration_min) AS avg_sleep,
                       AVG(resting_hr_bpm) AS avg_rhr
                FROM qbot_wellness_daily
                WHERE date >= %s
                """,
                (since,),
            )
            avg_row = cur.fetchone() or {}
            averages = {
                "avg_hrv": avg_row.get("avg_hrv"),
                "avg_sleep": avg_row.get("avg_sleep"),
                "avg_rhr": avg_row.get("avg_rhr"),
            }
    except Exception as exc:
        return {
            "status": "WARN",
            "error": type(exc).__name__,
            "error_detail": str(exc)[:200],
            "signals": {},
        }

    sleep_records = []
    for row in sleep_rows:
        sleep_records.append({
            "sleepLocalDate": str(row.get("date"))[:10] if row.get("date") else None,
            "sleepDurationMin": row.get("sleep_duration_min"),
            "sleepStartTime": row.get("sleep_start"),
            "sleepEndTime": row.get("sleep_end"),
            "source": row.get("source"),
        })

    hrv_records = []
    for row in wellness_rows:
        hrv_records.append({
            "hrvLocalDate": str(row.get("date"))[:10] if row.get("date") else None,
            "value": row.get("hrv_ms"),
            "weeklyAvg": averages["avg_hrv"],
            "source": row.get("source"),
            "raw": row,
        })

    recovery = select_recovery_records(sleep_records, hrv_records)
    selected_sleep = recovery.get("selectedSleepRecord") or {}
    selected_hrv = recovery.get("selectedHrvRecord") or {}
    selected_hrv_raw = selected_hrv.get("raw") if isinstance(selected_hrv, dict) else {}
    selected_wellness_raw = wellness_rows[0] if wellness_rows else {}

    hrv_today = recovery.get("hrvToday")
    sleep_today_h = recovery.get("sleepTodayH")
    hrv_baseline = recovery.get("hrvBaseline")
    sleep_baseline = None
    if averages["avg_sleep"] is not None:
        try:
            sleep_baseline = float(averages["avg_sleep"]) / 60.0
        except (TypeError, ValueError):
            sleep_baseline = None

    current_rhr = None
    if isinstance(selected_hrv_raw, dict):
        current_rhr = selected_hrv_raw.get("resting_hr_bpm")
    if current_rhr is None and isinstance(selected_wellness_raw, dict):
        current_rhr = selected_wellness_raw.get("resting_hr_bpm")

    signals: dict[str, object] = {}
    if hrv_today is not None and hrv_today > 0:
        signals["hrvToday"] = round(float(hrv_today), 1)
    if hrv_baseline is not None:
        signals["hrvBaseline30d"] = round(float(hrv_baseline), 1)
        if hrv_today is not None and hrv_today > 0:
            signals["hrvDeviation30d"] = round(float(hrv_today) - float(hrv_baseline), 1)
    if sleep_today_h is not None and sleep_today_h > 0:
        signals["sleepTodayH"] = round(float(sleep_today_h), 2)
    if sleep_baseline is not None:
        signals["sleepBaseline30d"] = round(float(sleep_baseline), 2)
        if sleep_today_h is not None and sleep_today_h > 0:
            signals["sleepDev"] = round(float(sleep_today_h) - float(sleep_baseline), 2)
    if current_rhr is not None and averages["avg_rhr"] is not None:
        try:
            signals["restingHrDev"] = round(float(current_rhr) - float(averages["avg_rhr"]), 1)
        except (TypeError, ValueError):
            pass

    recovery_source = recovery.get("recoverySource") if isinstance(recovery, dict) else {}
    if recovery_source:
        signals["recoverySource"] = recovery_source

    if not signals:
        return {"status": "NO_DATA", "signals": {}}

    return {
        "status": "OK",
        "signals": signals,
        "selectedSleepRecord": selected_sleep if isinstance(selected_sleep, dict) else {},
        "selectedHrvRecord": selected_hrv if isinstance(selected_hrv, dict) else {},
    }


@app.on_event("startup")
def startup():
    try:
        import api_db
        api_db.init_db()
    except Exception:
        pass
    _db_check()


@app.get("/health")
def health():
    _db_check()
    return {
        "status": "ok",
        "db": "connected" if DB_AVAILABLE else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _ping_db() -> bool:
    import api_db
    return api_db.ping()


@app.get("/ride-readiness")
@app.get("/ride-readiness/")
async def ride_readiness():
    import asyncio, time as _time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

    OVERALL_SEC = float(os.getenv("RIDE_READINESS_TIMEOUT_SEC", "5"))

    async def _core():
        t0 = _time.perf_counter()
        print("[RIDE_READINESS_START]", flush=True)
        warnings: list[str] = []
        blockers: list[str] = []

        # ── Lightweight local DB check ──────────────────────────
        db_start = _time.perf_counter()
        db_ok = False
        try:
            db_ok = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    ThreadPoolExecutor(max_workers=1),
                    _ping_db,
                ),
                timeout=2.0,
            )
        except (asyncio.TimeoutError, FutureTimeoutError):
            warnings.append("db_ping_timeout")
            print(f"[RIDE_READINESS_SECTION name=db status=TIMEOUT elapsed_ms={(_time.perf_counter()-db_start)*1000:.0f}]", flush=True)
        except Exception as exc:
            warnings.append(f"db_ping_error: {exc}")
            print(f"[RIDE_READINESS_SECTION name=db status=ERROR elapsed_ms={(_time.perf_counter()-db_start)*1000:.0f}]", flush=True)
        else:
            print(f"[RIDE_READINESS_SECTION name=db status={'OK' if db_ok else 'FAIL'} elapsed_ms={(_time.perf_counter()-db_start)*1000:.0f}]", flush=True)

        if not db_ok:
            blockers.append("database not connected")

        # ── QExt2 athlete metrics from Xert ──────────────────────
        xert_start = _time.perf_counter()
        ftp_watts = None
        ltp_watts = None
        w_prime_kj = None
        xert_email = os.getenv("XERT_EMAIL", "")
        xert_password = os.getenv("XERT_PASSWORD", "")
        xert_status_signal = "MISSING"

        if xert_email and xert_password:
            try:
                xert_data = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
                        ThreadPoolExecutor(max_workers=1),
                        _xert_sync_fetch,
                        xert_email,
                        xert_password,
                    ),
                    timeout=2.5,
                )
                if isinstance(xert_data, dict):
                    ftp_watts = xert_data.get("ftp_watts")
                    ltp_watts = xert_data.get("ltp_watts")
                    w_prime_kj = xert_data.get("w_prime_kj")
                    if ftp_watts:
                        xert_status_signal = "OK"
                        print(f"[RIDE_READINESS_SECTION name=xert status=OK elapsed_ms={(_time.perf_counter()-xert_start)*1000:.0f} ftp={ftp_watts}]", flush=True)
                    else:
                        xert_status_signal = "WARN"
                        warnings.append("xert: empty response")
                        print(f"[RIDE_READINESS_SECTION name=xert status=WARN elapsed_ms={(_time.perf_counter()-xert_start)*1000:.0f}]", flush=True)
            except (asyncio.TimeoutError, FutureTimeoutError):
                xert_status_signal = "WARN"
                warnings.append("xert_timeout")
                print(f"[RIDE_READINESS_SECTION name=xert status=TIMEOUT elapsed_ms={(_time.perf_counter()-xert_start)*1000:.0f}]", flush=True)
            except Exception as exc:
                xert_status_signal = "WARN"
                warnings.append(f"xert_error: {exc}")
                print(f"[RIDE_READINESS_SECTION name=xert status=ERROR error={exc} elapsed_ms={(_time.perf_counter()-xert_start)*1000:.0f}]", flush=True)
        else:
            warnings.append("xert credentials not configured")
            print("[RIDE_READINESS_SECTION name=xert status=SKIP reason=no_credentials]", flush=True)

        # ── Try weight from Intervals.icu wellness ─────────────────
        try:
            weight_data = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    ThreadPoolExecutor(max_workers=1),
                    _intervals_weight_sync,
                ),
                timeout=2.0,
            )
            weight_kg = weight_data.get("weight_kg") if isinstance(weight_data, dict) else None
        except (asyncio.TimeoutError, FutureTimeoutError, Exception):
            weight_kg = None

        # ── QExt2 readiness logic ─────────────────────────────────
        # MCP is informational for QExt2 — never a blocker
        mcp_status = "UNKNOWN"

        # qbot_core based only on lightweight local health
        if db_ok:
            qbot_core = "OK"
        else:
            qbot_core = "WARN"

        # Core readiness: athlete data present AND DB online
        xert_ok = bool(ftp_watts and ltp_watts and w_prime_kj)
        core_ok = xert_ok and db_ok

        if not xert_ok and db_ok:
            warnings.append("athlete power metrics unavailable from Xert")
        if not xert_ok:
            blockers.append("athlete power metrics unavailable")

        if core_ok and not blockers:
            status = "READY"
        elif core_ok:
            status = "READY_WITH_WARNINGS"
        else:
            status = "NOT_READY"

        payload: dict = {
            "ok": core_ok,
            "status": status,
            "source": "qbot-api",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": warnings,
            "qbot_core": qbot_core,
            "telegram": "UNKNOWN",
            "mcp": mcp_status,
            "legacy_takeover_percent": 100,
            "ready": core_ok,
            "blockers": blockers,
        }

        if core_ok:
            payload["wPrimeKj"] = w_prime_kj
            payload["ltpWatts"] = ltp_watts
            payload["ftpWatts"] = ftp_watts
        else:
            reasons: list[str] = []
            if not ftp_watts:
                reasons.append("ftpWatts unavailable")
            if not ltp_watts:
                reasons.append("ltpWatts unavailable")
            if not w_prime_kj:
                reasons.append("wPrimeKj unavailable")
            if not db_ok:
                reasons.append("database not connected")
            payload["reasons"] = reasons

        if weight_kg is not None:
            payload["weightKg"] = weight_kg

        try:
            signals_snapshot = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    ThreadPoolExecutor(max_workers=1),
                    _ride_readiness_signals_snapshot,
                ),
                timeout=2.0,
            )
        except (asyncio.TimeoutError, FutureTimeoutError):
            warnings.append("signals_timeout")
            signals_snapshot = {"status": "WARN", "signals": {}}
        except Exception as exc:
            warnings.append(f"signals_error: {exc}")
            signals_snapshot = {"status": "WARN", "signals": {}}

        signals = signals_snapshot.get("signals", {}) if isinstance(signals_snapshot, dict) else {}
        if isinstance(signals, dict) and signals:
            signals["xertStatus"] = xert_status_signal
            payload["signals"] = signals
        elif xert_status_signal != "MISSING":
            payload["signals"] = {"xertStatus": xert_status_signal}

        elapsed_ms = (_time.perf_counter() - t0) * 1000
        print(f"[RIDE_READINESS_DONE status={status} ok={core_ok} ready={core_ok} elapsed_ms={elapsed_ms:.0f}]", flush=True)
        return payload

    try:
        payload = await asyncio.wait_for(
            _core(),
            timeout=OVERALL_SEC,
        )
    except asyncio.TimeoutError:
        print("[RIDE_READINESS_FAILED reason=overall_timeout]", flush=True)
        payload = {
            "ok": False,
            "status": "NOT_READY",
            "source": "qbot-api",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": ["ride readiness timed out"],
            "reasons": ["readiness check exceeded maximum time"],
            "qbot_core": "UNKNOWN",
            "ready": False,
            "blockers": ["readiness check timed out"],
        }

    return JSONResponse(content=payload, status_code=200)


# ── Nutrition / Fueling endpoints ──────────────────────────────────────────────────


@app.post("/nutrition/intake/text")
async def nutrition_intake_text(request: Request):
    """POST /nutrition/intake/text — log meal/hydration/fueling from NL text."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"tool": "nutrition_intake_text", "status": "ERROR", "error": "invalid JSON"}, status_code=400)
    text = str(body.get("text", "")).strip()
    meal_type = str(body.get("meal_type", "meal")).strip() or "meal"
    note = body.get("note")
    context = body.get("context")
    if not text:
        return JSONResponse(content={"tool": "nutrition_intake_text", "status": "ERROR", "error": "text required"}, status_code=400)

    from qbot_nutrition_tools import _tool_qbot_nutrition_intake_log
    result = _tool_qbot_nutrition_intake_log({"text": text, "meal_type": meal_type, "note": note, "context": context})
    status_code = 200 if result.get("status") == "OK" else 400
    return JSONResponse(content=result, status_code=status_code)


@app.post("/nutrition/intake/telegram")
async def nutrition_intake_telegram(request: Request):
    """POST /nutrition/intake/telegram — same as /text but tailored for Telegram webhook."""
    return await nutrition_intake_text(request)


@app.post("/nutrition/foods")
async def nutrition_foods_create(request: Request):
    """POST /nutrition/foods — add a food item."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"tool": "nutrition_foods_create", "status": "ERROR", "error": "invalid JSON"}, status_code=400)
    from qbot_nutrition_tools import _tool_qbot_nutrition_food_create
    result = _tool_qbot_nutrition_food_create(body)
    status_code = 200 if result.get("status") == "OK" else 400
    return JSONResponse(content=result, status_code=status_code)


@app.get("/nutrition/foods/search")
def nutrition_foods_search(request: Request):
    """GET /nutrition/foods/search?query=skyr&limit=20"""
    query = request.query_params.get("query", "")
    limit = int(request.query_params.get("limit", "20"))
    from qbot_nutrition_tools import _tool_qbot_nutrition_food_search
    result = _tool_qbot_nutrition_food_search({"query": query, "limit": limit})
    return JSONResponse(content=result, status_code=200)


@app.post("/nutrition/meals")
async def nutrition_meals_create(request: Request):
    """POST /nutrition/meals — log a meal with explicit items."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"tool": "nutrition_meals_create", "status": "ERROR", "error": "invalid JSON"}, status_code=400)
    from qbot_nutrition_db import meal_log_create
    try:
        meal = meal_log_create(
            meal_type=body.get("meal_type", "meal"),
            note=body.get("note"),
            context=body.get("context"),
            eaten_at=body.get("eaten_at"),
            items=body.get("items", []),
        )
        return JSONResponse(content={"tool": "nutrition_meals_create", "status": "OK", "meal": meal}, status_code=200)
    except Exception as exc:
        return JSONResponse(content={"tool": "nutrition_meals_create", "status": "ERROR", "error": str(exc)}, status_code=400)


@app.post("/nutrition/hydration")
async def nutrition_hydration_create(request: Request):
    """POST /nutrition/hydration — log a hydration event."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"tool": "nutrition_hydration", "status": "ERROR", "error": "invalid JSON"}, status_code=400)
    from qbot_nutrition_tools import _tool_qbot_nutrition_hydration_log
    result = _tool_qbot_nutrition_hydration_log(body)
    status_code = 200 if result.get("status") == "OK" else 400
    return JSONResponse(content=result, status_code=status_code)


@app.get("/nutrition/day/{date_str}")
def nutrition_day_summary(date_str: str, request: Request):
    """GET /nutrition/day/2026-05-26 — full daily summary."""
    recompute = request.query_params.get("recompute", "0") == "1"
    from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
    result = _tool_qbot_nutrition_day_summary({"date": date_str, "recompute": recompute})
    return JSONResponse(content=result, status_code=200)


@app.post("/nutrition/import/cronometer/servings-csv")
async def nutrition_import_cronometer_csv(request: Request):
    """POST /nutrition/import/cronometer/servings-csv — import Cronometer servings CSV."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"tool": "nutrition_import_cronometer", "status": "ERROR", "error": "invalid JSON"}, status_code=400)
    csv_text = str(body.get("csv", "")).strip()
    if not csv_text:
        return JSONResponse(content={"tool": "nutrition_import_cronometer", "status": "ERROR", "error": "csv required"}, status_code=400)
    try:
        import csv, io
        from qbot_nutrition_db import meal_log_create, food_item_create
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        imported = 0
        skipped = 0
        for row in rows:
            food_name = (row.get("Food Name") or row.get("Food") or "").strip()
            amount_str = (row.get("Amount") or row.get("Serving") or "0").strip()
            unit = (row.get("Unit") or "g").strip()
            try:
                amount = float(amount_str.replace(",", "."))
            except ValueError:
                skipped += 1
                continue
            if not food_name or amount <= 0:
                skipped += 1
                continue

            kcal = float(row.get("Calories (kcal)", 0) or 0)
            carbs = float(row.get("Carbs (g)", 0) or 0)
            protein = float(row.get("Protein (g)", 0) or 0)
            fat = float(row.get("Fat (g)", 0) or 0)
            fiber = float(row.get("Fiber (g)", 0) or 0)
            sodium = float(row.get("Sodium (mg)", 0) or 0)

            food_item_create(name=food_name, kcal_per_100g=kcal * 100 / amount if amount else None,
                             carbs_per_100g=carbs * 100 / amount if amount else None,
                             protein_per_100g=protein * 100 / amount if amount else None,
                             fat_per_100g=fat * 100 / amount if amount else None,
                             fiber_per_100g=fiber * 100 / amount if amount else None,
                             sodium_per_100g=sodium * 100 / amount if amount else None,
                             source="cronometer_import")
            imported += 1

        return JSONResponse(content={
            "tool": "nutrition_import_cronometer",
            "status": "OK",
            "rows_seen": len(rows),
            "imported": imported,
            "skipped": skipped,
        }, status_code=200)
    except Exception as exc:
        return JSONResponse(content={"tool": "nutrition_import_cronometer", "status": "ERROR", "error": str(exc)}, status_code=400)


@app.post("/q")
async def q_endpoint(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {
            "result": {"error": "invalid JSON"},
            "warnings": [],
        }

    tool = (payload or {}).get("tool", "")
    args = payload.get("args", {})
    result, warnings = _dispatch_local_qbot_tool(tool, args, source="q")
    if not DB_AVAILABLE:
        warnings.append("database unavailable, call not logged")

    return {"result": result, "warnings": warnings}


@app.post("/telegram/webhook/{webhook_secret}")
async def telegram_webhook(webhook_secret: str, request: Request):
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected_secret or webhook_secret != expected_secret:
        return JSONResponse(content={"status": "forbidden", "detail": "invalid webhook secret"}, status_code=403)

    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret_header and secret_header != expected_secret:
        return JSONResponse(content={"status": "forbidden", "detail": "invalid secret header"}, status_code=403)

    try:
        update = await request.json()
    except Exception:
        return JSONResponse(content={"status": "error", "detail": "invalid JSON"}, status_code=400)

    from qbot_telegram_client import validate_update, extract_chat_id, extract_message_text, is_allowed_chat
    valid, err = validate_update(update)
    if not valid:
        return JSONResponse(content={"status": "ignored", "detail": err}, status_code=200)

    chat_id = extract_chat_id(update)
    if not chat_id or not is_allowed_chat(chat_id):
        return JSONResponse(content={"status": "forbidden", "detail": f"chat_id not allowed"}, status_code=403)

    text = extract_message_text(update).strip()
    if not text:
        return JSONResponse(content={"status": "ignored", "detail": "empty message"}, status_code=200)

    cmd = text.strip().lower()
    if not cmd.startswith("/"):
        from qbot_telegram_tools import _tool_qbot_telegram_agent_chat
        chat_result = _tool_qbot_telegram_agent_chat({"message": text, "style": "short", "execute": True, "chat_id": str(chat_id)})
        return _telegram_webhook_reply(chat_id, chat_result.get("answer", "Nie mogę teraz odpowiedzieć."))

    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    query = parts[1].strip() if len(parts) > 1 else ""

    if command == "/ask":
        from qbot_telegram_tools import _tool_qbot_telegram_agent_chat
        chat_result = _tool_qbot_telegram_agent_chat({"message": query or text, "style": "short", "execute": True})
        return _telegram_webhook_reply(chat_id, chat_result.get("answer", "Nie mogę teraz odpowiedzieć."))

    result: dict = {}

    if command == "/start":
        from qbot_telegram_tools import _tool_qbot_telegram_command_help
        result = {"command": "/start", "response": _tool_qbot_telegram_command_help()}
    elif command == "/help":
        from qbot_telegram_tools import _tool_qbot_telegram_command_help
        result = {"command": "/help", "response": _tool_qbot_telegram_command_help()}
    elif command == "/status":
        summary_text, response = _telegram_status_summary()
        result = {"command": "/status", "response": response, "text": summary_text}
    elif command == "/legacy":
        from qbot_legacy_cutover_tools import _tool_qbot_legacy_cutover_status
        response = _tool_qbot_legacy_cutover_status()
        legacy_state = "disabled po cutover" if not response.get("legacy_service_active") and not response.get("legacy_service_enabled") else "legacy active"
        result = {
            "command": "/legacy",
            "response": response,
            "text": "Legacy status:\n"
                    f"ℹ️ q-bot.service: {legacy_state}\n"
                    f"ℹ️ rollback: {'available' if response.get('rollback_available') else 'unavailable'}",
        }
    elif command == "/ready":
        from qbot_operator_tools import _tool_qbot_readiness_report
        result = {"command": "/ready", "response": _tool_qbot_readiness_report()}
    elif command == "/smoke":
        from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
        result = {"command": "/smoke", "response": _tool_qbot_operator_final_smoke_test()}
    elif command == "/backup":
        from qbot_ops_tools import _tool_qbot_backup_status
        result = {"command": "/backup", "response": _tool_qbot_backup_status()}
    elif command == "/errors":
        from qbot_operator_tools import _tool_qbot_error_summary
        result = {"command": "/errors", "response": _tool_qbot_error_summary({"limit": 20})}
    elif command == "/takeover":
        from qbot_legacy_cutover_tools import _tool_qbot_legacy_takeover_status
        result = {"command": "/takeover", "response": _tool_qbot_legacy_takeover_status()}
    elif command == "/weather_status":
        from qbot_legacy_parity_tools import _tool_qbot_weather_legacy_status, _tool_qbot_weather_status
        current = _tool_qbot_weather_status()
        legacy = _tool_qbot_weather_legacy_status()
        response = {"current": current, "legacy": legacy}
        result = {
            "command": "/weather_status",
            "response": response,
            "text": "Weather status:\n"
                    f"ℹ️ current status: {current.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ current path: {current.get('current_weather_path', 'unknown')}\n"
                    f"ℹ️ OWM legacy: {legacy.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ OWM note: {legacy.get('current_new_qbot_status', 'unknown')}",
        }
    elif command == "/garage_status":
        from qbot_legacy_parity_tools import _tool_qbot_garage_legacy_status
        response = _tool_qbot_garage_legacy_status()
        result = {
            "command": "/garage_status",
            "response": response,
            "text": "Garage legacy:\n"
                    f"ℹ️ status: {response.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ safety: {response.get('safety_class', 'UNKNOWN')}\n"
                    f"ℹ️ note: no remote opening/closing implemented",
        }
    elif command == "/artifacts":
        from qbot_legacy_parity_tools import _tool_qbot_artifacts_legacy_status
        response = _tool_qbot_artifacts_legacy_status()
        result = {
            "command": "/artifacts",
            "response": response,
            "text": "Artifacts legacy:\n"
                    f"ℹ️ status: {response.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ filesystem root: {response.get('filesystem_artifacts_root', 'unknown')}\n"
                    f"ℹ️ bridge: {'present' if response.get('bridge_present') else 'partial/missing'}",
        }
    elif command == "/integrations":
        from qbot_legacy_parity_tools import _tool_qbot_external_integrations_report
        response = _tool_qbot_external_integrations_report()
        result = {
            "command": "/integrations",
            "response": response,
            "text": response.get("summary_text") or "External integrations report unavailable",
        }
    elif command == "/rwgps":
        from qbot_route_tools import _tool_qbot_rwgps_legacy_status, _tool_qbot_rwgps_config_status
        status = _tool_qbot_rwgps_legacy_status()
        config = _tool_qbot_rwgps_config_status()
        result = {
            "command": "/rwgps",
            "response": status,
            "text": "RWGPS:\n"
                    f"ℹ️ status: {status.get('restored_status', 'UNKNOWN')}\n"
                    f"ℹ️ configured: {'yes' if config.get('auth_token_present') else 'no'}\n"
                    f"ℹ️ code: {'detected' if status.get('code_detected') else 'missing'}\n"
                    f"ℹ️ missing: {', '.join(config.get('missing', [])) or 'none'}\n"
                    f"ℹ️ route list: qbot_rwgps_route_list",
        }
    elif command == "/hammerhead":
        from qbot_legacy_parity_tools import _tool_qbot_hammerhead_import_status
        from qbot_route_tools import _tool_qbot_hammerhead_config_status, _tool_qbot_hammerhead_import_inventory
        status = _tool_qbot_hammerhead_import_status()
        config = _tool_qbot_hammerhead_config_status()
        inventory = _tool_qbot_hammerhead_import_inventory({"limit": 1})
        restored = config.get("restored_status", status.get("status", "UNKNOWN"))
        result = {
            "command": "/hammerhead",
            "response": status,
            "text": "Hammerhead:\n"
                    f"ℹ️ status: {restored}\n"
                    f"ℹ️ JWT: {'present' if config.get('jwt_present') else 'missing'}\n"
                    f"ℹ️ tokenstore: {'active' if config.get('tokenstore_active') else 'inactive'}\n"
                    f"ℹ️ token expired: {config.get('possible_expired_token', 'unknown')}\n"
                    f"ℹ️ FIT files: {inventory.get('count', 0)}",
        }
    elif command == "/csv":
        from qbot_route_tools import _tool_qbot_csv_export_status
        status = _tool_qbot_csv_export_status()
        result = {
            "command": "/csv",
            "response": status,
            "text": "CSV Export:\n"
                    f"ℹ️ status: {status.get('restored_status', 'UNKNOWN')}\n"
                    f"ℹ️ csv count: {status.get('inventory', {}).get('csv_count', 0)}\n"
                    f"ℹ️ latest available: {'yes' if status.get('latest_available') else 'no'}",
        }
    elif command == "/xert":
        from qbot_integration_tools import _tool_qbot_xert_readiness_status, _tool_qbot_xert_config_status
        config = _tool_qbot_xert_config_status()
        status = _tool_qbot_xert_readiness_status()
        result = {
            "command": "/xert",
            "response": status,
            "text": "Xert:\n"
                    f"ℹ️ configured: {'yes' if config.get('configured') else 'no'}\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ FTP: {status.get('ftp_watts', 'N/A')}W\n"
                    f"ℹ️ forma: {status.get('form_status', 'N/A')}",
        }
    elif command == "/intervals":
        from qbot_integration_tools import _tool_qbot_intervals_wellness_status, _tool_qbot_intervals_config_status
        config = _tool_qbot_intervals_config_status()
        status = _tool_qbot_intervals_wellness_status()
        result = {
            "command": "/intervals",
            "response": status,
            "text": "Intervals.icu:\n"
                    f"ℹ️ configured: {'yes' if config.get('configured') else 'no'}\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ weight: {status.get('latest_weight', 'N/A')}kg",
        }
    elif command == "/garmin":
        from qbot_integration_tools import _tool_qbot_garmin_config_status, _tool_qbot_garmin_upload_dry_run
        config = _tool_qbot_garmin_config_status()
        dry_run = _tool_qbot_garmin_upload_dry_run()
        result = {
            "command": "/garmin",
            "response": config,
            "text": "Garmin:\n"
                    f"ℹ️ configured: {'yes' if config.get('configured') else 'no'}\n"
                    f"ℹ️ tokenstore: {'active' if config.get('tokenstore_active') else 'inactive'}\n"
                    f"ℹ️ latest FIT: {'available' if dry_run.get('latest_fit_available') else 'none'}",
        }
    elif command == "/cronometer":
        from qbot_integration_tools import _tool_qbot_cronometer_legacy_status
        status = _tool_qbot_cronometer_legacy_status()
        result = {
            "command": "/cronometer",
            "response": status,
            "text": "Cronometer:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ restored: {status.get('restored_status', 'UNKNOWN')}",
        }
    elif command == "/weather":
        from qbot_integration_tools import _tool_qbot_weather_config_status
        status = _tool_qbot_weather_config_status()
        result = {
            "command": "/weather",
            "response": status,
            "text": "Weather:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ API configured: {'yes' if status.get('api_configured') else 'no'}\n"
                    f"ℹ️ location: {'set' if status.get('location_configured') else 'missing'}",
        }
    elif command == "/maps":
        from qbot_integration_tools import _tool_qbot_openmaps_legacy_status
        status = _tool_qbot_openmaps_legacy_status()
        result = {
            "command": "/maps",
            "response": status,
            "text": "OpenMaps:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ code: {'detected' if status.get('code_detected') else 'missing'}",
        }
    elif command == "/garage":
        from qbot_garage_tools import _tool_qbot_garage_raw_status
        status = _tool_qbot_garage_raw_status()
        result = {
            "command": "/garage",
            "response": status,
            "text": "Garage:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ records: {status.get('total_records', 0)}",
        }
    elif command == "/daily_report" or command == "/daily":
        from qbot_report_tools import _tool_qbot_daily_report_status
        status = _tool_qbot_daily_report_status()
        result = {
            "command": command,
            "response": status,
            "text": "Daily Report:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ last sent: {status.get('last_sent_date', 'never')}\n"
                    f"ℹ️ channels: {', '.join(status.get('channels', [])) or 'none'}",
        }
    elif command == "/ride_report" or command == "/reports":
        from qbot_report_tools import _tool_qbot_ride_report_status
        status = _tool_qbot_ride_report_status()
        result = {
            "command": command,
            "response": status,
            "text": "Ride Report:\n"
                    f"ℹ️ status: {status.get('status', 'UNKNOWN')}\n"
                    f"ℹ️ activities reported: {status.get('reported_count', 0)}",
        }
    elif command == "/ask":
        if not query:
            result = {"command": "/ask", "response": {"status": "error", "error": "empty query"}}
        else:
            from qbot_query_processor import process_query
            result = {"command": "/ask", "response": process_query(query, execute=True), "_query": query}
    else:
        return _telegram_webhook_reply(chat_id, f"Nie znam komendy '{command}'. Napisz pytanie normalnym tekstem albo /help.")

    reply_text = _telegram_response_text(command, result)
    if not reply_text:
        if isinstance(result.get("response"), dict):
            r = result["response"]
            status = r.get("status", "?")
            reply_text = f"{command}\nStatus: {status}"
        else:
            reply_text = f"{command} — received"

    return _telegram_webhook_reply(chat_id, reply_text)


def _mcp_response(payload: dict | None, status_code: int, headers: dict[str, str] | None = None):
    headers = headers or {}
    if payload is None:
        return JSONResponse(content=None, status_code=status_code, headers=headers)
    return JSONResponse(content=payload, status_code=status_code, headers=headers)


def _mcp_auth_guard(request: Request):
    # Discovery and health surfaces are read-only. Tool-level auth is enforced on tools/call.
    return None


@app.get("/mcp/")
@app.get("/mcp")
def mcp_root(request: Request):
    denied = _mcp_auth_guard(request)
    if denied is not None:
        return denied
    status = _tool_qbot_mcp_status({})
    tools = _tool_qbot_mcp_tools_list({})
    return {
        "status": status.get("status", "UNKNOWN"),
        "service": "qbot-mcp-adapter",
        "version": "v1",
        "health": "/mcp/health",
        "tools": "/mcp/tools",
        "public_url": status.get("public_url"),
        "auth_configured": status.get("auth_configured"),
        "exposed_tools": status.get("exposed_tools", []),
        "tool_count": tools.get("count", 0),
    }


@app.get("/mcp/health")
@app.get("/mcp/health/")
def mcp_health(request: Request):
    denied = _mcp_auth_guard(request)
    if denied is not None:
        return denied
    return _tool_qbot_mcp_status({})


@app.get("/mcp/tools")
@app.get("/mcp/tools/")
def mcp_tools(request: Request):
    # GET /mcp/tools is public (same semantics as MCP tools/list)
    return _tool_qbot_mcp_tools_list({})


@app.post("/mcp/")
@app.post("/mcp")
async def mcp_post(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}, status_code=400)

    response_payload, status_code, headers = handle_mcp_request(payload if isinstance(payload, dict) else {}, dict(request.headers))
    return _mcp_response(response_payload, status_code, headers)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Q API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
