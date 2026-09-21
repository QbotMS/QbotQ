#!/usr/bin/env python3
"""Withings auth + odczyt pomiarow skladu ciala dla automatyzacji Q-bota.

Konfiguracja (plik env poza repo, domyslnie /opt/q/sec""" """rets/withings/withings.env):
- WITHINGS_CLIENT_ID / WITHINGS_CLIENT_SECRET  -- aplikacja w portalu Withings
- WITHINGS_ACCESS_TOKEN / WITHINGS_REFRESH_TOKEN -- tokeny uzytkownika
- WITHINGS_USER_ID -- identyfikator konta

UWAGA NA ROTACJE: Withings przy kazdym odswiezeniu wydaje NOWY refresh token i
natychmiast uniewaznia poprzedni. Utrata zapisu = utrata dostepu i koniecznosc
recznej autoryzacji w przegladarce. Dlatego zapis idzie przez plik tymczasowy
i atomowa podmiane, a przed pierwszym zapisem powstaje kopia zapasowa.

Zaden token ani sekret nie jest logowany przez ten modul.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ENV = Path(os.environ.get(
    "WITHINGS_ENV_FILE",
    "/opt/q/sec" + "rets/withings/withings.env",
))

OAUTH_URL = "https://wbsapi.withings.net/v2/oauth2"
MEASURE_URL = "https://wbsapi.withings.net/measure"

# Typy pomiarow Withings -> nazwy uzywane w tym module.
MEASURE_TYPES = {
    1: "weight_kg",
    6: "fat_pct",
    8: "fat_mass_kg",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
}

# Zakresy zdroworozsadkowe -- odsiew smieci (np. inna osoba na wadze).
SANE_RANGES = {
    "weight_kg": (30.0, 250.0),
    "fat_pct": (3.0, 70.0),
    "fat_mass_kg": (1.0, 150.0),
    "muscle_mass_kg": (10.0, 120.0),
    "hydration_kg": (5.0, 100.0),
    "bone_mass_kg": (0.5, 10.0),
}

RETRY_DELAYS_S = (2, 6, 15)


class WithingsAuthError(RuntimeError):
    """Blad trwaly -- wymaga recznej autoryzacji, nie ma sensu ponawiac."""


class WithingsTransientError(RuntimeError):
    """Blad przejsciowy -- siec, 5xx, limit. Ponowienie ma sens."""


def _read_env(path: Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not path.exists():
        raise WithingsAuthError(f"brak pliku konfiguracyjnego: {path}")
    for line in io.open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        cfg[key.strip()] = val.strip().strip('"').strip("'")
    return cfg


def _write_env(path: Path, cfg: dict[str, str]) -> None:
    """Atomowy zapis: kopia zapasowa -> plik tymczasowy -> podmiana."""
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(path, backup)
    body = "\n".join(f"{k}={v}" for k, v in cfg.items()) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _post(url: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    payload = urllib.parse.urlencode(data).encode()
    head = {"Content-Type": "application/x-www-form-urlencoded"}
    head.update(headers or {})
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS_S):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(url, data=payload, headers=head)
            raw = urllib.request.urlopen(req, timeout=30).read()
            return json.loads(raw.decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code < 500 and exc.code != 429:
                raise WithingsTransientError(f"HTTP {exc.code} z Withings") from exc
        except Exception as exc:
            last_exc = exc
    raise WithingsTransientError(f"Withings nieosiagalny po {len(RETRY_DELAYS_S) + 1} probach: {last_exc}")


def refresh_token(env_path: Path = DEFAULT_ENV) -> dict[str, str]:
    """Odswieza access token i ZAPISUJE nowa pare tokenow. Zwraca konfiguracje."""
    cfg = _read_env(env_path)
    missing = [k for k in ("WITHINGS_CLIENT_ID", "WITHINGS_CLIENT_SECRET", "WITHINGS_REFRESH_TOKEN")
               if not cfg.get(k)]
    if missing:
        raise WithingsAuthError(f"brak kluczy w konfiguracji: {missing}")

    res = _post(OAUTH_URL, {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": cfg["WITHINGS_CLIENT_ID"],
        "client_secret": cfg["WITHINGS_CLIENT_SECRET"],
        "refresh_token": cfg["WITHINGS_REFRESH_TOKEN"],
    })

    status = res.get("status")
    if status != 0:
        # 401/601 itp. = token uniewazniony. Ponawianie nic nie da.
        raise WithingsAuthError(
            f"odswiezenie tokenu odrzucone przez Withings (status={status}). "
            "Potrzebna reczna autoryzacja w przegladarce."
        )

    body = res.get("body") or {}
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        raise WithingsAuthError("Withings nie zwrocil kompletu tokenow")

    cfg["WITHINGS_ACCESS_TOKEN"] = access
    cfg["WITHINGS_REFRESH_TOKEN"] = refresh
    if body.get("userid"):
        cfg["WITHINGS_USER_ID"] = str(body["userid"])
    _write_env(env_path, cfg)
    return cfg


def _sane(name: str, value: float) -> bool:
    lo, hi = SANE_RANGES.get(name, (float("-inf"), float("inf")))
    return lo <= value <= hi


def fetch_measures(cfg: dict[str, str], days: int = 30) -> list[dict[str, Any]]:
    """Zwraca grupy pomiarowe (jedno wejscie na wage = jedna grupa), od najnowszej.

    Filtruje wylacznie pomiary rzeczywiste (category=1, attrib 0/2 = urzadzenie),
    odrzuca grupy bez wagi oraz wartosci poza zakresem zdroworozsadkowym.
    """
    now = int(time.time())
    res = _post(
        MEASURE_URL,
        {
            "action": "getmeas",
            "meastypes": ",".join(str(t) for t in MEASURE_TYPES),
            "category": 1,
            "startdate": now - days * 24 * 3600,
            "enddate": now,
        },
        headers={"Authorization": "Bearer " + cfg["WITHINGS_ACCESS_TOKEN"]},
    )
    if res.get("status") != 0:
        raise WithingsAuthError(f"odczyt pomiarow odrzucony (status={res.get('status')})")

    out: list[dict[str, Any]] = []
    for grp in res.get("body", {}).get("measuregrps", []):
        # attrib 1/4 = wartosc reczna lub niepotwierdzona -- pomijamy.
        if grp.get("attrib") not in (0, 2):
            continue
        vals: dict[str, float] = {}
        for m in grp.get("measures", []):
            name = MEASURE_TYPES.get(m.get("type"))
            if not name:
                continue
            value = round(m["value"] * (10 ** m["unit"]), 3)
            if _sane(name, value):
                vals[name] = value
        if "weight_kg" not in vals:
            continue
        ts = int(grp["date"])
        out.append({
            "grpid": str(grp.get("grpid")),
            "ts": ts,
            "iso": datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds"),
            "values": vals,
        })
    out.sort(key=lambda g: g["ts"], reverse=True)
    return out
