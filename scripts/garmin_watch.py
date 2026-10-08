#!/usr/bin/env python3
"""Straznik Garmina (2026-10-08) -- jeden rytm dla WSZYSTKICH importow z Garmina.

Cron: */15 * * * *  (cala doba). Zastepuje okna godzinowe importow snu, wellness, kalorii,
treningow, jazd i wagi. Decyzja Michala 2026-10-08, plan i luki: docs/DECISIONS.md.

Kazdy cykl -- LEKKIE sprawdzenie (2 zapytania):
  * czas ostatniego syncu urzadzenia (fenix)   -> get_device_last_used.lastUsedDeviceUploadTime
  * ostatnia aktywnosc na koncie (tez Karoo)   -> get_activities(0, 1).activityId
Pelne importy uruchamiane, gdy:
  1. ktorys sygnal sie zmienil -> import teraz + jeszcze 3 kolejne cykle (Garmin dolicza
     wynik snu / HRV / Body Battery z opoznieniem po syncu),
  2. minely 3 h od ostatniego pelnego importu (siatka bezpieczenstwa),
  3. noc 03:xx -- domkniecie wczorajszego dnia (raz na dobe).
Sygnaly oznaczane jako obsluzone DOPIERO gdy wszystkie importy zakonczyly sie sukcesem;
nieudany cykl -> ponowienie w kolejnym. Brak polaczenia z Garminem > 1 h -> Telegram (co 6 h).

Uzycie: garmin_watch.py [--check] (tylko lekkie sprawdzenie, bez importow, bez zapisu stanu)
        garmin_watch.py --force   (wymus pelny import teraz)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APP = Path("/opt/qbot/app")
PY = str(APP / ".venv/bin/python3")
LOGS = Path("/opt/qbot/logs")
STATE = APP / "state/garmin_watch.json"
TZ = ZoneInfo("Europe/Warsaw")
sys.path.insert(0, str(APP))

REPEAT_CYCLES = 3          # dodatkowe cykle po wykrytej zmianie
FULL_EVERY_S = 3 * 3600    # siatka bezpieczenstwa
NIGHT_HOUR = 3             # domkniecie wczoraj
ALERT_AFTER_S = 3600
ALERT_COOLDOWN_S = 6 * 3600
IMPORT_TIMEOUT_S = 900
MAX_FAIL_RUNS = 4          # po tylu nieudanych cyklach z rzedu: stop ponawiania co 15 min, alarm, rytm 3 h

# Kolejnosc ma znaczenie: waga przed wellness (wellness przelicza gotowosc i wage ModelQ).
IMPORTS = [
    ("body", ["qbot3/connectors/import_garmin_body.py", "--days", "3"], "garmin_body_import.log"),
    ("sleep", ["qbot3/connectors/import_garmin_sleep.py"], "connector_sleep.log"),
    ("energy", ["qbot3/connectors/import_garmin_energy.py"], "connector_energy.log"),
    ("wellness", ["scripts/run_wellness_imports.py"], "wellness_import.log"),
    ("training", ["qbot3/connectors/import_garmin_training.py"], "connector_training.log"),
    ("activities", ["qbot_activity_ingest.py", "backfill", "20", "0", "2025-01-01", "report"], "activity_ingest.log"),
]


def log(msg: str) -> None:
    print(f"[{datetime.now(TZ).isoformat(timespec='seconds')}] {msg}", flush=True)


def load_state() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, STATE)


def telegram(text: str) -> None:
    try:
        import requests
        import qbot_config as cfg
        requests.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    except Exception as exc:
        log(f"telegram nieudany: {exc}")


def signals() -> dict:
    """Lekkie sprawdzenie: 2 zapytania do Garmina."""
    from garmin_auth import garmin_client
    g = garmin_client()
    dev = g.get_device_last_used() or {}
    acts = g.get_activities(0, 1) or []
    return {
        "sync_ts": dev.get("lastUsedDeviceUploadTime"),
        "act_id": (acts[0].get("activityId") if acts and isinstance(acts[0], dict) else None),
    }


def run_imports() -> dict:
    res = {}
    for name, args, logname in IMPORTS:
        t0 = time.time()
        with open(LOGS / logname, "a", encoding="utf-8") as fh:
            fh.write(f"\n[{datetime.now(TZ).isoformat(timespec='seconds')}] garmin_watch -> {name}\n")
            fh.flush()
            try:
                rc = subprocess.run([PY, *args], cwd=str(APP), stdout=fh, stderr=subprocess.STDOUT,
                                    timeout=IMPORT_TIMEOUT_S).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        res[name] = rc
        log(f"  {name}: rc={rc} ({time.time() - t0:.0f}s)")
    return res


def main() -> int:
    check_only = "--check" in sys.argv
    force = "--force" in sys.argv
    st = load_state()
    now = time.time()
    local = datetime.now(TZ)
    today = local.date().isoformat()

    try:
        sig = signals()
    except Exception as exc:
        log(f"Garmin niedostepny: {type(exc).__name__}: {str(exc)[:200]}")
        if check_only:
            return 1
        st.setdefault("fail_since", now)
        if now - st["fail_since"] >= ALERT_AFTER_S and now - st.get("last_alert", 0) >= ALERT_COOLDOWN_S:
            telegram("Straznik Garmina: brak polaczenia z Garminem od ponad godziny.\n"
                     f"Ostatni blad: {type(exc).__name__}: {str(exc)[:150]}\n"
                     "Sen, wellness, kalorie i jazdy nie trafiaja do QBota.")
            st["last_alert"] = now
        save_state(st)
        return 1

    changed = (sig["sync_ts"] != st.get("sync_ts")) or (sig["act_id"] != st.get("act_id"))
    full_due = now - st.get("last_full", 0) >= FULL_EVERY_S
    night_due = local.hour == NIGHT_HOUR and st.get("night_done") != today
    pending = int(st.get("pending", 0))
    log(f"sygnaly: sync_ts={sig['sync_ts']} act_id={sig['act_id']} zmiana={changed} "
        f"pending={pending} full_due={full_due} night_due={night_due}")

    if check_only:
        return 0

    if st.pop("fail_since", None) is not None:
        log("Garmin znow dostepny")

    if changed:
        pending = REPEAT_CYCLES + 1
    if not (pending > 0 or full_due or night_due or force):
        save_state(st)
        return 0

    reason = "zmiana" if changed else ("dobieranie" if pending > 0 else ("noc" if night_due else ("3h" if full_due else "force")))
    log(f"importy start ({reason})")
    res = run_imports()
    ok = all(rc == 0 for rc in res.values())
    st["last_run"] = {"at": local.isoformat(timespec="seconds"), "reason": reason, "rc": res}

    if ok:
        st["sync_ts"], st["act_id"] = sig["sync_ts"], sig["act_id"]
        st["pending"] = max(0, pending - 1)
        st["last_full"] = now
        st["fail_runs"] = 0
        if night_due:
            st["night_done"] = today
        log("importy OK")
    else:
        st["fail_runs"] = int(st.get("fail_runs", 0)) + 1
        bad = {k: v for k, v in res.items() if v != 0}
        if st["fail_runs"] >= MAX_FAIL_RUNS:
            # Nie mielimy Garmina co 15 min w nieskonczonosc: sygnaly oznaczone, ponowi siatka 3 h.
            st["sync_ts"], st["act_id"] = sig["sync_ts"], sig["act_id"]
            st["pending"] = 0
            st["last_full"] = now
            if now - st.get("last_alert", 0) >= ALERT_COOLDOWN_S:
                telegram(f"Straznik Garmina: importy padaja {st['fail_runs']} cykle z rzedu: {bad}.\n"
                         "Przechodze na rytm co 3 h do czasu naprawy. Logi: /opt/qbot/logs/garmin_watch.log")
                st["last_alert"] = now
            log(f"importy z bledem {st['fail_runs']}x -- przejscie na rytm 3 h: {bad}")
        else:
            st["pending"] = max(pending, 1)   # ponow w kolejnym cyklu; sygnalow NIE oznaczamy
            log(f"importy z bledem ({st['fail_runs']}x) -- ponowienie w kolejnym cyklu: {bad}")
    save_state(st)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
