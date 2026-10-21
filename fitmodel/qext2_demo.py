"""Jazdy z trybu NAGRANIE QExt2 (QExt2 0.4.20, sesja demo-2110, 21.10.2026).

Tryb NAGRANIE sluzy do nagrania ekranu Karoo w domu, bez roweru (film o QBocie). Gdyby na Karoo wcisnieto START,
w pliku FIT kazdy rekord ma pole developerskie qext2_demo=1. Takiej jazdy QBot NIE importuje: nie trafia do
activity_record, ModelQ, raportu jazdy ani statystyk (qbot_activity_ingest.ingest_one, fitmodel/fit_ingest.py).
Strava / intervals.icu dostaja jazde z Garmina bez QBota -- dlatego jazde nagrania i tak trzeba ODRZUCIC na Karoo.
Opis: docs/wiki/qext2/tryb-demo.md.
"""
from __future__ import annotations

import io
from typing import Any, Iterable

DEMO_FIELD = "qext2_demo"
# QExt2 pisze znacznik co sekunde od poczatku zapisu -- wystarczy przejrzec poczatek pliku (30 min rekordow).
SCAN_RECORDS = 1800
SKIP_REASON = "qext2_demo: jazda z trybu NAGRANIE QExt2 - pominieta"


def scan_messages(messages: Iterable[Any], limit: int = SCAN_RECORDS) -> bool:
    """True, gdy ktorys z pierwszych `limit` rekordow ma qext2_demo >= 1."""
    for i, m in enumerate(messages):
        if i >= limit:
            break
        try:
            v = m.get_value(DEMO_FIELD)
        except Exception:
            v = None
        if v is None:
            continue
        try:
            if float(v) >= 0.5:
                return True
        except (TypeError, ValueError):
            continue
    return False


def is_demo_fit(src: Any) -> bool:
    """src: bajty pliku FIT albo sciezka. Blad czytania -> False (zwykly import i tak zglosi blad pliku)."""
    try:
        from fitparse import FitFile
        fit = FitFile(io.BytesIO(bytes(src)) if isinstance(src, (bytes, bytearray)) else src)
        return scan_messages(fit.get_messages("record"))
    except Exception:
        return False
