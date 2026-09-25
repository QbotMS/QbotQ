"""Wspolny czas lokalny QBota (Europe/Warsaw).

Zasada: obliczenia i zapis moga byc w UTC, ale wszystko, co widzi uzytkownik
(Telegram, strony lab, odpowiedzi Alberta, raporty, maile), idzie przez te funkcje.
"""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")


def now_local() -> _dt.datetime:
    """Teraz, ze strefa Europe/Warsaw (aware)."""
    return _dt.datetime.now(WARSAW)


def today_local() -> _dt.date:
    """Dzisiejsza data w Polsce (nie w UTC -- miedzy 00:00 a 02:00 to rozne dni)."""
    return now_local().date()


def to_local(x):
    """datetime/ISO -> aware datetime w Europe/Warsaw. Naiwny czas traktowany jako UTC."""
    if x is None or x == "":
        return None
    if isinstance(x, str):
        s = x.strip().replace("Z", "+00:00")
        x = _dt.datetime.fromisoformat(s)
    if x.tzinfo is None:
        x = x.replace(tzinfo=_dt.timezone.utc)
    return x.astimezone(WARSAW)


def iso_local(x=None, timespec: str = "seconds") -> str:
    """ISO z przesunieciem polskim, np. 2026-09-25T14:05:00+02:00."""
    return (now_local() if x is None else to_local(x)).isoformat(timespec=timespec)


def fmt_local(x, fmt: str = "%Y-%m-%d %H:%M") -> str:
    d = to_local(x)
    return d.strftime(fmt) if d else ""
