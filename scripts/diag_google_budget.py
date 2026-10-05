#!/usr/bin/env python3
"""Pokazuje efektywne limity Google Places (po wczytaniu env uslugi) i zuzycie. Bez sekretow."""
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
src = {}
for p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env", "/opt/qbot/app/.env"):
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                if k.startswith("GOOGLE_PLACES_") and k.endswith("_LIMIT"):
                    src[k] = (p, v.strip().strip('"').strip("'"))
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))
    except OSError as exc:
        print("brak", p, type(exc).__name__)
print("limity w plikach env:", src or "brak (dziala domyslna wartosc z kodu)")
from qbot3.routes import google_places_budget as b  # noqa: E402

print("efektywnie: dzien", b._daily_limit(), "| miesiac", b._monthly_limit())
print("zuzycie:", b.usage_snapshot())
