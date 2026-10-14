#!/usr/bin/env python3
"""debug_garmin_sleep_hrv_raw.py — Etap 0 (dane Garmin): PELNA odpowiedz Garmina dla snu i HRV.

Cel: potwierdzic dokladne nazwy pol (temperatura skory, potrzeba snu, status/norma HRV),
ktore obecny importer (qbot_wellness_store._garmin_fetch_wellness) wycina.
Tylko odczyt z Garmina, nic nie zapisuje do bazy.

Wynik: pelny JSON -> /opt/qbot/artifacts/garmin_sleep_hrv_raw_<data>.json
       na konsoli: lista kluczy + pola pasujace do skin/temp/need/hrv/baseline/status.

Uzycie (krotkie, kilka sekund na dzien):
    .venv/bin/python3 scripts/debug_garmin_sleep_hrv_raw.py
    .venv/bin/python3 scripts/debug_garmin_sleep_hrv_raw.py --dates 2026-10-14,2026-06-01
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
OUT_DIR = Path("/opt/qbot/artifacts")
PROFILE = APP_DIR / ".garmin_profile.json"
TOKENS = APP_DIR / ".garmin_tokens"
INTEREST = re.compile(r"(skin|temp|need|baseline|status|balanced|weekly|feedback|insight)", re.I)


def _client():
    from garminconnect import Garmin
    profile = json.loads(PROFILE.read_text())
    g = Garmin("", "")
    g.client.load(str(TOKENS))
    g.display_name = profile["display_name"]
    return g


def _walk(obj, path=""):
    """Zwraca (sciezka, wartosc) dla lisci; listy skraca do pierwszego elementu."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], (dict, list)):
            yield from _walk(obj[0], f"{path}[0]")
        else:
            yield path, f"<lista {len(obj)} el.>"
    else:
        yield path, obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dates", default=date.today().isoformat())
    args = p.parse_args()

    g = _client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for d in [x.strip() for x in args.dates.split(",") if x.strip()]:
        out = {"date": d}
        for name, fn in (("sleep", g.get_sleep_data), ("hrv", g.get_hrv_data)):
            try:
                out[name] = fn(d)
            except Exception as e:  # noqa: BLE001
                out[name] = {"_error": str(e)[:300]}
        path = OUT_DIR / f"garmin_sleep_hrv_raw_{d}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))

        print("=" * 70)
        print(f"{d}  ->  {path}")
        for name in ("sleep", "hrv"):
            data = out[name]
            top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
            print(f"\n[{name}] klucze glowne: {top}")
            hits = [(k, v) for k, v in _walk(data) if INTEREST.search(k)]
            for k, v in hits:
                print(f"   {k} = {v}")
            if not hits:
                print("   (brak pol pasujacych do skin/temp/need/baseline/status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
