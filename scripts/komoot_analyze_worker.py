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


def _attractions(route_id: str) -> str:
    """Kanoniczny silnik atrakcji; przy brakach OSM jedna ponowna proba
    (gotowe odcinki sa w cache, wiec dociaga tylko brakujace)."""
    try:
        from qbot3.routes.route_attraction_store import ensure_route_attractions
        from qbot3.routes.route_poi_store import set_route_poi_attractions
        # Ten sam trwaly przelacznik co POBIERZ na stronie - inaczej Planer/raport
        # nie pokaze policzonych atrakcji (incydent 2026-10-05, komoot-3331694546).
        set_route_poi_attractions(route_id, True)
        out = ensure_route_attractions(route_id=route_id, force=True)
        miss = int(((out.get("source_status") or {}).get("missing_chunks")) or 0)
        if miss:
            log(f"atrakcje {route_id}: OSM brak {miss} odcinkow - ponawiam")
            out = ensure_route_attractions(route_id=route_id, force=True)
            miss = int(((out.get("source_status") or {}).get("missing_chunks")) or 0)
        summ = out.get("summary") or {}
        log(f"atrakcje {route_id}: run={out.get('run_id')} status={out.get('status')} summary={summ} osm_missing={miss}")
        names = []
        try:
            from qbot3.routes.route_poi_store import _db_conn
            conn = _db_conn()
            try:
                rows = conn.execute(
                    "SELECT name, km_on_route FROM qbot_v2.route_attraction_layer "
                    "WHERE run_id=%s AND is_recommended ORDER BY km_on_route",
                    (int(out.get("run_id")),),
                ).fetchall()
            finally:
                conn.close()
            for r in rows:
                nm_ = r["name"] if isinstance(r, dict) else r[0]
                km_ = r["km_on_route"] if isinstance(r, dict) else r[1]
                names.append("km %d %s" % (round(float(km_ or 0)), nm_))
        except Exception as e:
            log("atrakcje: lista nazw blad: " + repr(e))
        txt = "Atrakcje: %s polecanych z %s kandydatow" % (summ.get("recommended", "?"), summ.get("candidates", "?"))
        if names:
            txt += ":\n- " + "\n- ".join(names)
        if miss:
            txt += "\n(OpenStreetMap niepelny - brak %d odcinkow; w raporcie nacisnij POBIERZ jeszcze raz)" % miss
        return txt
    except Exception as e:
        log(f"atrakcje {route_id} BLAD: {e!r}")
        return "\u26a0\ufe0f Atrakcje nie pobrane: " + str(e)[:150] + " (sprobuj POBIERZ w raporcie)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tour_id")
    ap.add_argument("--atrakcje", action="store_true")
    args = ap.parse_args()
    tour_id = str(args.tour_id)

    log(f"START analiza tour={tour_id} atrakcje={args.atrakcje}")
    try:
        # 2026-10-03: atrakcje NIE przez stara flage route_poi (samo Google co 3 km),
        # tylko przez kanoniczny silnik (OSM+Wikipedia+Wikidata+Google), ten sam
        # co Planer wypraw / zakladka Atrakcje (POBIERZ) / Albert.
        import komoot_watch
        res = komoot_watch.analyze_tour(tour_id)
        nm = (res or {}).get("name") or ("#" + tour_id)
        log(f"OK analiza tour={tour_id} name={nm}")
        if args.atrakcje:
            attr_txt = _attractions("komoot-" + tour_id)
            tg("\u2705 Zanalizowano z atrakcjami: " + str(nm) + "\n" + attr_txt
               + "\nGotowe w QBot - wygeneruj raport i wyslij na Karoo.")
        else:
            tg("\u2705 Zanalizowano: " + str(nm) + "\nGotowe w QBot - wygeneruj raport i wyslij na Karoo.")
        return 0
    except Exception as e:
        log(f"BLAD analiza tour={tour_id}: {e!r}")
        suffix = " (+atrakcje)" if args.atrakcje else ""
        tg("\u26a0\ufe0f Analiza #" + tour_id + suffix + " nie powiodla sie: " + str(e)[:200])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
