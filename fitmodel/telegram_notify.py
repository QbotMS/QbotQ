# -*- coding: utf-8 -*-
"""Wysylanie wiadomosci Telegram z modulow fitmodel (wspolny helper).

Od 2026-10-18 jedyne miejsce tej funkcji. Wczesniej siedziala w fitmodel/power_meter_guard.py
(starym, wycofanym strazniku miernika) i importowalo ja 6 innych modulow.
"""
from __future__ import annotations


def send(msg: str) -> None:
    """Wysyla tekst na czat QBota (dzieli na kawalki po 4000 znakow)."""
    import httpx, sys
    sys.path.insert(0, "/opt/qbot/app")
    import qbot_config as cfg
    for i in range(0, len(msg), 4000):
        r = httpx.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                       json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": msg[i:i + 4000]},
                       timeout=10)
        r.raise_for_status()
