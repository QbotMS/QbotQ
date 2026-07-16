#!/usr/bin/env python3
"""
komoot_analyze_worker.py — odlaczony worker analizy trasy z Komoot.

Uruchamiany przez telegram_reply_processor (Popen, start_new_session=True) po
wcisnieciu przycisku Analizuj. Robi PELNA, dzisiejsza sekwencje przez
komoot_watch.analyze_tour (ingest -> nawierzchnia -> precompute -> finalizacja)
i na koncu SAM wysyla wynik na Telegram (sukces / blad). Dzieki temu ciezka
trasa nie blokuje 2-minutowego crona i status zawsze wraca.

Uzycie:  python scripts/komoot_analyze_worker.py <tour_id> [--atrakcje]
"""
import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import httpx
import qbot_config as cfg

LOG_PATH = "/opt/qbot/logs/komoot_analyze.log"
TG_BASE = f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}"


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def tg(text: str) -> None:
    try:
        httpx.post(
            TG_BASE + "/sendMessage",
            json={"chat_id": str(cfg.TELEGRAM_CHAT_ID), "text": text},
            timeout=15,
        )
    except Exception as e:
        log("tg blad: " + str(e))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tour_id")
    ap.add_argument("--atrakcje", action="store_true")
    args = ap.parse_args()
    tour_id = str(args.tour_id)

    log(f"START analiza tour={tour_id} atrakcje={args.atrakcje}")
    try:
        if args.atrakcje:
            from qbot3.routes.route_poi_store import set_route_poi_attractions
            set_route_poi_attractions("komoot-" + tour_id, True)
        import komoot_watch
        res = komoot_watch.analyze_tour(tour_id)
        nm = (res or {}).get("name") or ("#" + tour_id)
        log(f"OK analiza tour={tour_id} name={nm}")
        prefix = "\u2705 Zanalizowano z atrakcjami: " if args.atrakcje else "\u2705 Zanalizowano: "
        tg(prefix + str(nm) + "\nGotowe w QBot - wygeneruj raport i wyslij na Karoo.")
        return 0
    except Exception as e:
        log(f"BLAD analiza tour={tour_id}: {e!r}")
        suffix = " (+atrakcje)" if args.atrakcje else ""
        tg("\u26a0\ufe0f Analiza #" + tour_id + suffix + " nie powiodla sie: " + str(e)[:200])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
