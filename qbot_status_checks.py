#!/usr/bin/env python3
"""Status funkcji QBota -- JEDNO zrodlo dla: SETUP > Polaczenia > Status (qbot_status_api.py)
oraz narzedzi Alberta (hammerhead_sync_status, withings_sync_status, qbot_status_overview).

Kazdy check zwraca: {id, name, state, text, last, details}
  state: ok | warn | bad | off   (off = swiadomie wylaczone / nieuzywane)
  text:  jedno zdanie prostym jezykiem; daty DD.MM HH:MM (czas polski)
Tylko odczyt: pliki stanu, logi, systemd (show/is-active). Nic nie uruchamia.
Dok.: docs/STATUS.md (2026-10-15).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

APP = Path("/opt/qbot/app")
TZ = ZoneInfo("Europe/Warsaw")


# ---------------------------------------------------------------- pomocnicze
def _now() -> datetime:
    return datetime.now(TZ)


def _dt(v: Any) -> datetime | None:
    """ISO / epoch(s|ms) -> datetime w czasie polskim."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)):
            x = float(v)
            if x > 1e12:
                x /= 1000.0
            return datetime.fromtimestamp(x, TZ)
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ)
    except Exception:
        return None


def _fmt(d: datetime | None) -> str:
    return d.strftime("%d.%m %H:%M") if d else "—"


def _age_h(d: datetime | None) -> float | None:
    return None if d is None else (_now() - d).total_seconds() / 3600.0


def _json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _mtime(p: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, TZ)
    except Exception:
        return None


def _tail(p: Path, n: int = 60) -> list[str]:
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 16000))
            return f.read().decode("utf-8", "replace").splitlines()[-n:]
    except Exception:
        return []


def _systemd(unit: str, props: str) -> dict[str, str]:
    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", props], capture_output=True, text=True, timeout=5).stdout
        return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    except Exception:
        return {}


def _r(id_: str, name: str, state: str, text: str, last: datetime | None = None, **details: Any) -> dict[str, Any]:
    return {"id": id_, "name": name, "state": state, "text": text,
            "last": last.isoformat(timespec="seconds") if last else None, "details": details}


# ---------------------------------------------------------------- checki
def hammerhead() -> dict[str, Any]:
    """Hammerhead (Karoo) -> Garmin jako TACX. Program co 10 min (cron root): qbot-hammerhead-sync."""
    name = "Hammerhead → Garmin"
    state_f = APP / "state/processed_hammerhead_activities.json"
    log_f = APP / "logs/hammerhead-garmin-sync.log"
    try:
        items = _json(state_f).get("processed") or []
    except Exception as e:
        return _r("hammerhead", name, "bad", f"Nie mogę odczytać stanu synchronizacji ({type(e).__name__}).")
    up = [x for x in items if x.get("status") == "uploaded"]
    # 409 "Duplicate Activity" = jazda JUZ jest w Garminie -> nie liczymy jako blad
    failed = [x for x in items if x.get("status") not in ("uploaded", "skipped", "duplicate")
              and "Duplicate Activity" not in str(x.get("error") or "")]
    last_up = max((_dt(x.get("updatedAt")) for x in up), default=None, key=lambda d: d or datetime.min.replace(tzinfo=TZ))
    lines = _tail(log_f)
    last_run = None
    for ln in reversed(lines):
        if ln.startswith("[") and "] qbot-hammerhead-sync" in ln:
            last_run = _dt(ln[1:ln.index("]")])
            break
    run_err = any(("Traceback" in ln or "ERROR" in ln) for ln in lines[-12:])
    age = _age_h(last_run)
    if last_run is None or (age is not None and age > 1):
        st, txt = "bad", f"Program nie sprawdzał nowych jazd od {_fmt(last_run)} (powinien co 10 min)."
    elif run_err:
        st, txt = "warn", f"Ostatnie sprawdzenie {_fmt(last_run)} zgłosiło błąd — zajrzyj do logu."
    elif failed:
        st, txt = "warn", f"Działa (sprawdzone {_fmt(last_run)}), ale {len(failed)} jazd(a) nie przeszło do Garmina."
    else:
        st, txt = "ok", f"Działa: ostatnia jazda przesłana {_fmt(last_up)}, sprawdzanie co 10 min (ostatnie {_fmt(last_run)})."
    return _r("hammerhead", name, st, txt, last_run, rides_total=len(items), uploaded=len(up),
              failed=[{"activity_time": _fmt(_dt(x.get("activityTime"))), "error": str(x.get("error") or "")[:160]} for x in failed][-5:],
              last_upload=_fmt(last_up), last_check=_fmt(last_run))


def withings() -> dict[str, Any]:
    """Withings -> Garmin (waga, sklad ciala, cisnienie). Program qbot-withings-sync (cron root)."""
    name = "Withings → Garmin"
    state_f = APP / "state/processed_withings_measures.json"
    alert_f = APP / "state/withings_sync_alert_state.json"
    try:
        s = _json(state_f)
    except Exception as e:
        return _r("withings", name, "bad", f"Nie mogę odczytać stanu synchronizacji ({type(e).__name__}).")

    def _last(sec: str) -> datetime | None:
        ds = [_dt(v.get("sent_at")) for v in (s.get(sec) or {}).values() if v.get("status") in ("uploaded", "duplicate")]
        ds = [d for d in ds if d]
        return max(ds) if ds else None

    w, bp, upd = _last("measures"), _last("bp"), _dt(s.get("updated_at"))
    if alert_f.exists():
        st, txt = "bad", f"Ostatnia próba się nie udała (wysłano ostrzeżenie na Telegram). Ostatnio OK: waga {_fmt(w)}, ciśnienie {_fmt(bp)}."
    elif upd is None or (_age_h(upd) or 0) > 72:
        st, txt = "warn", f"Brak nowych pomiarów od {_fmt(upd)} — sprawdź wagę/ciśnieniomierz albo program."
    else:
        st, txt = "ok", f"Działa: waga wysłana {_fmt(w)}, ciśnienie {_fmt(bp)}."
    return _r("withings", name, st, txt, upd, last_weight=_fmt(w), last_bp=_fmt(bp),
              weight_count=len(s.get("measures") or {}), bp_count=len(s.get("bp") or {}))


def garmin_import() -> dict[str, Any]:
    """Garmin -> QBot (jazdy, sen, serce, energia, sklad ciala).
    Straznik qbot-garmin-watch co 10 min sprawdza, czy w Garminie cos sie zmienilo; import robi przy zmianie
    albo co 3 h (siatka bezpieczenstwa, scripts/garmin_watch.py FULL_EVERY_S)."""
    name = "Garmin → QBot (import)"
    try:
        g = _json(APP / "state/garmin_watch.json")
    except Exception as e:
        return _r("garmin", name, "bad", f"Nie mogę odczytać stanu importu ({type(e).__name__}).")
    lr = g.get("last_run") or {}
    at = _dt(lr.get("at")) if isinstance(lr, dict) else None
    rc = (lr.get("rc") or {}) if isinstance(lr, dict) else {}
    bad = sorted(k for k, v in rc.items() if v not in (0, None))
    fails = int(g.get("fail_runs") or 0)
    w = _timer_service("garmin", name, "qbot-garmin-watch.service", 10 / 60, "")
    watch_last = _dt(w.get("last"))
    if w["state"] == "bad":
        return _r("garmin", name, "bad", f"Strażnik importu zakończył się błędem ({_fmt(watch_last)}).", watch_last)
    if watch_last is None or (_age_h(watch_last) or 0) > 0.75:
        return _r("garmin", name, "bad", f"Strażnik importu nie sprawdzał Garmina od {_fmt(watch_last)} (powinien co 10 min).", watch_last)
    if at is None or (_age_h(at) or 0) > 4:
        return _r("garmin", name, "warn", f"Brak importu od {_fmt(at)} (powinien najpóźniej co 3 h).", watch_last)
    if bad or fails:
        return _r("garmin", name, "warn", f"Ostatni import {_fmt(at)}: problem z {', '.join(bad) or 'pobieraniem'} (kolejne nieudane: {fails}).",
                  watch_last, failed_parts=bad, fail_runs=fails)
    return _r("garmin", name, "ok", f"Działa: ostatni import {_fmt(at)}, sprawdzanie zmian co 10 min (ostatnie {_fmt(watch_last)}).",
              watch_last, failed_parts=bad, fail_runs=fails)


def _timer_service(id_: str, name: str, unit: str, every_h: float, what: str) -> dict[str, Any]:
    p = _systemd(unit, "Result,ExecMainExitTimestamp,ExecMainStatus,ActiveState")
    last = None
    ts = p.get("ExecMainExitTimestamp", "")
    if ts and ts != "n/a":
        try:
            last = datetime.strptime(" ".join(ts.split()[1:3]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        except Exception:
            last = None
    res = p.get("Result", "")
    if not p:
        return _r(id_, name, "warn", "Nie mogę odczytać stanu usługi.")
    if res and res != "success":
        return _r(id_, name, "bad", f"Ostatnie uruchomienie {_fmt(last)} zakończyło się błędem.", last, result=res)
    if last is None or (_age_h(last) or 0) > every_h * 2.5:
        return _r(id_, name, "warn", f"Dawno nie uruchamiane (ostatnio {_fmt(last)}).", last)
    return _r(id_, name, "ok", f"Działa: {what} {_fmt(last)}.", last)


def komoot() -> dict[str, Any]:
    return _timer_service("komoot", "Komoot (nowe trasy)", "qbot-komoot-watch.service", 5 / 60, "ostatnie sprawdzenie")


def backup() -> dict[str, Any]:
    return _timer_service("backup", "Kopia bazy danych", "qbot-backup.service", 24, "ostatnia kopia")


def services() -> dict[str, Any]:
    units = ["qbot-api", "qbot-web", "qbot-mcp-bridge", "qbot-qlab-server"]
    try:
        out = subprocess.run(["systemctl", "is-active", *units], capture_output=True, text=True, timeout=5).stdout.split()
    except Exception:
        out = []
    states = dict(zip(units, out))
    down = [u for u in units if states.get(u) != "active"]
    if not states:
        return _r("services", "Usługi QBota", "warn", "Nie mogę odczytać stanu usług.")
    if down:
        return _r("services", "Usługi QBota", "bad", f"Nie działa: {', '.join(down)}.", None, states=states)
    return _r("services", "Usługi QBota", "ok", "Działają wszystkie: serwer, strona, Albert (MCP), QLab.", None, states=states)


def albert_model() -> dict[str, Any]:
    try:
        from qbot3.llm.model_profiles import public_status
        p = public_status()
    except Exception as e:
        return _r("albert", "Model AI Alberta", "warn", f"Nie mogę odczytać ustawień modelu ({type(e).__name__}).")
    return _r("albert", "Model AI Alberta", "ok", f"Albert działa na: {p.get('label')} ({p.get('model')}).", None,
              profile=p.get("profile"), model=p.get("model"))


def gate() -> dict[str, Any]:
    """Bramka HikConnect -- 15.10.2026: odlaczona od QExt2 (Michal wroci do tematu)."""
    name = "Bramka (HikConnect)"
    try:
        from qbot3.capabilities.system.gate_status import GateStatusCapability
        r = GateStatusCapability().run({})
        d = (r or {}).get("data") or {}
        stt = d.get("status") or {}
    except Exception as e:
        return _r("gate", name, "off", f"Odłączona od QExt2 (stan usługi nieznany: {type(e).__name__}).")
    last = _dt(stt.get("last_success_at_utc"))
    cfg = all(stt.get(k) for k in ("token_configured", "credentials_configured", "device_configured"))
    if not d.get("service_ok"):
        return _r("gate", name, "off", "Odłączona od QExt2; usługa bramki nie odpowiada.")
    return _r("gate", name, "off", f"Odłączona od QExt2. Konfiguracja {'kompletna' if cfg else 'niepełna'}, ostatnie otwarcie: {_fmt(last) if last else 'nigdy'}.", last)


def legacy_usage() -> dict[str, Any]:
    """Licznik uzycia starej warstwy QBota (15.10-22.10.2026) -> decyzja o wycieciu. Dok.: docs/LEGACY_USAGE.md"""
    from qbot_legacy_usage import summary
    s = summary(7)
    nf, nh = len(s["functions"]), len(s["http"])
    return _r("legacy", "Stary QBot (licznik użycia)", "off",
              f"Liczę od {s['since'] or 'teraz'}: użyto {nf} starych funkcji i {nh} adresów serwera. Decyzja o wycięciu 22.10.",
              None, functions=s["functions"], http=s["http"])


def weekly_audit() -> dict[str, Any]:
    """Cotygodniowy audyt (scripts/weekly_audit.py, timer qbot-weekly-audit, pon 02:30). Wynik: state/weekly_audit.json."""
    name = "Audyt tygodniowy"
    try:
        r = _json(APP / "state/weekly_audit.json")
    except FileNotFoundError:
        return _r("weekly", name, "warn", "Jeszcze się nie odbył (pierwszy w najbliższą noc z niedzieli na poniedziałek).")
    except Exception as e:
        return _r("weekly", name, "warn", f"Nie mogę odczytać wyniku ({type(e).__name__}).")
    at = _dt(r.get("at"))
    failed = int(r.get("tests_failed") or 0) + int(r.get("tests_errors") or 0)
    txt = (f"{_fmt(at)}: testy {r.get('tests_passed')} OK" + (f", {failed} padło" if failed else "") +
           (f"; sprzątnięto {r['cleanup_files']} starych kopii" if r.get("cleanup_files") else "") +
           (f"; kandydaci na martwy kod: {r['dead_candidates']}" if r.get("dead_candidates") is not None else "") + ".")
    if at is None or (_age_h(at) or 0) > 8 * 24:
        return _r("weekly", name, "warn", "Nie odbył się od ponad tygodnia. Ostatni: " + txt, at)
    return _r("weekly", name, "bad" if failed else "ok", txt, at, failed=r.get("tests_failed_list"), new=r.get("new_failures"))


CHECKS: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("services", services), ("garmin", garmin_import), ("hammerhead", hammerhead), ("withings", withings),
    ("komoot", komoot), ("backup", backup), ("albert", albert_model), ("gate", gate), ("weekly", weekly_audit), ("legacy", legacy_usage),
]


def all_checks() -> dict[str, Any]:
    items = []
    for id_, fn in CHECKS:
        try:
            items.append(fn())
        except Exception as e:  # jeden check nie kladzie calej strony
            items.append(_r(id_, id_, "warn", f"Błąd sprawdzania: {type(e).__name__}"))
    order = {"bad": 0, "warn": 1, "ok": 2, "off": 3}
    worst = min((order[i["state"]] for i in items if i["state"] != "off"), default=2)
    overall = {0: "bad", 1: "warn", 2: "ok"}[worst]
    n_bad = sum(1 for i in items if i["state"] in ("bad", "warn"))
    summary = "Wszystko działa." if overall == "ok" else f"Uwaga: {n_bad} funkcj{'a wymaga' if n_bad == 1 else 'e wymagają'} sprawdzenia."
    return {"checked_at": _now().isoformat(timespec="seconds"), "checked_at_txt": _fmt(_now()),
            "overall": overall, "summary": summary, "items": items}


if __name__ == "__main__":
    print(json.dumps(all_checks(), ensure_ascii=False, indent=1))
