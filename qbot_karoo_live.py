"""Jazda na zywo z Karoo (QExt2) -- sygnal 'jestem tu' co ~5 min -> ostrzezenie o deszczu z radaru w miejscu jazdy.

Decyzje Michala 14.10.2026 (dok.: docs/POGODA_OSTRZEZENIE.md):
- JEDEN rodzaj sygnalu: pozycja co ~5 min (takze w pauzie). Pierwszy sygnal = start jazdy, brak sygnalu przez GAP_MIN = koniec.
- Zapisywana tylko OSTATNIA pozycja biezacej jazdy (1 wiersz na jazde). Kasowanie: gdy QBot wczyta plik tej jazdy
  (training_sessions), awaryjnie po KEEP_H godzinach.
- Ostrzezenie liczy petla radaru w qbot-web (qbot_pogoda_alert.check) dla miejsca z ostatniego sygnalu; jazda z Karoo
  ma pierwszenstwo przed planem z Trenera (bez dubli). Odpowiedz na sygnal = biezace ostrzezenie (rain_for) dla KOKPITU.
Wywolanie: mcp_server.py POST /qext2/ping (token urzadzenia jak /ride-readiness).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
GAP_MIN = 15
KEEP_H = 24
MATCH_BEFORE_MIN = 30
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.karoo_live (id bigserial PRIMARY KEY, started_at timestamptz NOT NULL,
  last_at timestamptz NOT NULL, lat double precision, lon double precision, n int NOT NULL DEFAULT 1)"""


def sila(mmh: float) -> str:
    return "słaby" if mmh < 1 else "umiarkowany" if mmh < 4 else "silny" if mmh < 10 else "ulewa"


def ping(cur, lat: float, lon: float, now: dt.datetime | None = None) -> dict:
    """Zapis sygnalu: przedluza biezaca jazde (ostatni sygnal <= GAP_MIN temu) albo zaczyna nowa. Zwraca odpowiedz dla Karoo."""
    now = now or dt.datetime.now(TZ)
    import qbot_pogoda_alert as RA
    RA.ensure(cur)   # kolumny src/data w pogoda_alert (rain_for)
    cur.execute(DDL)
    cur.execute("SELECT id, last_at FROM qbot_v2.karoo_live ORDER BY last_at DESC LIMIT 1")
    r = cur.fetchone()
    if r and now - r["last_at"] <= dt.timedelta(minutes=GAP_MIN):
        rid = r["id"]
        cur.execute("UPDATE qbot_v2.karoo_live SET last_at=%s, lat=%s, lon=%s, n=n+1 WHERE id=%s", (now, lat, lon, rid))
        nowa = False
    else:
        cur.execute("INSERT INTO qbot_v2.karoo_live (started_at, last_at, lat, lon) VALUES (%s,%s,%s,%s) RETURNING id",
                    (now, now, lat, lon))
        rid = cur.fetchone()["id"]
        nowa = True
    return {"status": "OK", "ride": rid, "new_ride": nowa, "rain": rain_for(cur, rid, now)}


def active(cur, now: dt.datetime) -> dict | None:
    """Trwajaca jazda z Karoo (ostatni sygnal <= GAP_MIN temu) albo None."""
    cur.execute(DDL)
    cur.execute("SELECT id, started_at, last_at, lat, lon FROM qbot_v2.karoo_live WHERE last_at >= %s ORDER BY last_at DESC LIMIT 1",
                (now - dt.timedelta(minutes=GAP_MIN),))
    return cur.fetchone()


def ended_recently(cur, now: dt.datetime) -> list[int]:
    """Jazdy z Karoo zakonczone w ostatniej godzinie (do zamkniecia powiadomien w dzwonku)."""
    cur.execute("SELECT id FROM qbot_v2.karoo_live WHERE last_at < %s AND last_at >= %s",
                (now - dt.timedelta(minutes=GAP_MIN), now - dt.timedelta(minutes=GAP_MIN + 60)))
    return [x["id"] for x in cur.fetchall()]


def cleanup(cur, now: dt.datetime) -> int:
    """Kasuje pozycje jazd: zakonczonych, ktorych plik jest juz w QBocie (training_sessions), albo starszych niz KEEP_H."""
    cur.execute(DDL)
    cur.execute(f"""DELETE FROM qbot_v2.karoo_live k WHERE k.last_at < %s AND (k.last_at < %s OR EXISTS (
                      SELECT 1 FROM qbot_v2.training_sessions t
                      WHERE t.started_at BETWEEN k.started_at - interval '{MATCH_BEFORE_MIN} minutes' AND k.last_at))""",
                (now - dt.timedelta(minutes=GAP_MIN), now - dt.timedelta(hours=KEEP_H)))
    return cur.rowcount or 0


def short(a: dict, now: dt.datetime) -> dict | None:
    """Czysta funkcja: ostrzezenie z pogoda_alert -> krotki komunikat dla KOKPITU (None = nieaktualne)."""
    eta = a["eta"]
    d = a.get("data") or {}
    dur = int(d.get("dur") or 0)
    mmh = float(d.get("mmh") or 0)
    koniec = eta + dt.timedelta(minutes=dur)
    if now > koniec + dt.timedelta(minutes=5):
        return None
    za = max(0, round((eta - now).total_seconds() / 60))
    pada = za <= 2
    zostalo = max(5, round((koniec - max(now, eta)).total_seconds() / 60))
    s = sila(mmh)
    tekst = (f"pada · {s} · jeszcze ~{zostalo} min" if pada else f"deszcz za {za} min · {s} · ~{dur} min")
    return {"kind": "radar", "eta": eta.astimezone(TZ).strftime("%H:%M"), "za_min": za, "pada": pada, "mmh": round(mmh, 1),
            "sila": s, "dur_min": dur, "otwarte": bool(d.get("otwarte")), "short": tekst}


def rain_for(cur, rid: int, now: dt.datetime) -> dict | None:
    """Biezace ostrzezenie z radaru dla jazdy z Karoo (najnowsze, jesli epizod jeszcze trwa) albo None."""
    cur.execute("""SELECT eta, data FROM qbot_v2.pogoda_alert WHERE src='karoo' AND ride_id=%s AND kind='radar'
                   ORDER BY sent_at DESC LIMIT 1""", (rid,))
    a = cur.fetchone()
    return short(a, now) if a else None
