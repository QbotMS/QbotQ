"""Ostrzezenie o deszczu w czasie jazdy (radar + zespol). Dok.: docs/POGODA_OSTRZEZENIE.md

Decyzje Michala 14.10.2026 (po ulewie 14:50 przy ocenie 'jedz'): TYLKO deszcz; strona (dzwonek w menu + pasek na Pogodzie)
i Telegram; ostrzezenie dla CALEJ dlugosci jazdy.
- Jazdy: (1) JAZDA Z KAROO (qbot_karoo_live: sygnal pozycji co ~5 min) -- ma PIERWSZENSTWO; punkt = ostatnia pozycja,
  jazda otwarta (bez znanego konca), tylko radar. (2) Zapas, gdy Karoo nie nadaje: Trener (sport rower, status plan) --
  pilnowanie od LEAD_MIN przed startem do konca jazdy, punkt = dom. Gdy trwa jazda z Karoo, plany Trenera sa pomijane (bez dubli).
- Czesc jazdy w zasiegu radaru (HOR min, wg sprawdzalnosci radaru ~60): prognoza radaru (nowcast_point) -> 'radar' z godzina,
  sila (mm/h) i czasem trwania epizodu. Dalsza czesc jazdy (tylko plan Trenera): szansa z zespolu ICON-EU-EPS >= PROB -> 'prognoza'.
- Bez zasypywania: max MAX_MSG ostrzezen na jazde (dzwonek); radar -- kolejne tylko dla NOWEGO epizodu (poprzedni minal) albo gdy
  godzina przesunela sie o > ETA_SHIFT min; prognoza -- raz na jazde i tylko zanim radar cokolwiek zobaczyl.
  TELEGRAM: tylko PIERWSZE ostrzezenie na jazde (decyzja 14.10); kolejne tylko dzwonek + Karoo.
- Zrodlo w dzwonku: 'radar' (klucz radar:<id> / radar:k<id> dla Karoo), mozna wylaczyc w ustawieniach powiadomien -- wtedy tez bez Telegrama.
Wywolanie: petla radaru w qbot-web (co nowa klatke, ~5 min). Stan: qbot_v2.pogoda_alert (src: trener | karoo, data: mmh/dur/otwarte).
"""
from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
LEAD_MIN = 60
HOR = 60
PROB = 0.4
MAX_MSG = 3
ETA_SHIFT = 15
URL = "/pogoda.html"
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_alert (id bigserial PRIMARY KEY, ride_id bigint, day date, kind text,
  eta timestamptz, sent_at timestamptz NOT NULL DEFAULT now(), text text, tg_ok boolean)"""
MIGR = ["ALTER TABLE qbot_v2.pogoda_alert ADD COLUMN IF NOT EXISTS src text NOT NULL DEFAULT 'trener'",
        "ALTER TABLE qbot_v2.pogoda_alert ADD COLUMN IF NOT EXISTS data jsonb"]


def ensure(cur) -> None:
    cur.execute(DDL)
    for q in MIGR:
        cur.execute(q)


def sila(mmh: float) -> str:
    return "słaby" if mmh < 1 else "umiarkowany" if mmh < 4 else "silny" if mmh < 10 else "ulewa"


def _pl(x) -> str:
    return str(round(x, 1)).replace(".", ",")


def decide(ride: dict, now: dt.datetime, nowcast: list[dict], prob: dict, prev: list[dict], hor: int = HOR) -> dict | None:
    """Czysta decyzja. ride: {id, nazwa, start, koniec (datetime), otwarta?}; nowcast: [{t: datetime, udzial, mmh}] (prognoza radaru);
    prob: {'RRRR-MM-DDTHH': szansa 0-1 dla godziny HH..HH+1}; prev: wyslane [{kind, eta}].
    Zwraca {kind, eta, text, mmh?, dur?, otwarte?} albo None. Jazda otwarta (Karoo): koniec nieznany -> tylko radar."""
    if len(prev) >= MAX_MSG or now > ride["koniec"]:
        return None
    a, e = max(now, ride["start"]), ride["koniec"]
    lim = min(e, now + dt.timedelta(minutes=hor))
    sl = [p for p in nowcast if a - dt.timedelta(minutes=4) <= p["t"] <= lim and p.get("udzial") is not None]
    jz = f"trwająca od {ride['start']:%H:%M}" if ride.get("otwarta") else f"„{ride['nazwa']}” {ride['start']:%H:%M}–{e:%H:%M}"
    rain = [i for i, p in enumerate(sl) if p["udzial"] >= 0.5]
    if rain:
        i0 = rain[0]; i1 = i0
        while i1 + 1 < len(sl) and sl[i1 + 1]["udzial"] >= 0.5:
            i1 += 1
        eta = sl[i0]["t"]; mx = max(sl[k]["mmh"] or 0 for k in range(i0, i1 + 1))
        dur = (i1 - i0 + 1) * 5; otwarte = i1 == len(sl) - 1
        last = next((p for p in reversed(prev) if p["kind"] == "radar"), None)
        nowy = last is None or abs((eta - last["eta"]).total_seconds()) / 60 > ETA_SHIFT or (last["eta"] < now - dt.timedelta(minutes=20) and eta > now)
        if not nowy:
            return None
        za = max(0, round((eta - now).total_seconds() / 60))
        kiedy = "już pada u Ciebie" if za <= 2 else f"deszcz u Ciebie ok. {eta:%H:%M} (za {za} min)"
        trwa = f"potrwa ponad {dur} min (dalej poza zasięgiem radaru)" if otwarte else f"potrwa ok. {dur} min"
        return {"kind": "radar", "eta": eta, "mmh": mx, "dur": dur, "otwarte": otwarte,
                "text": f"🌧 Radar: {kiedy}, {sila(mx)} (do {_pl(mx)} mm/h), {trwa}. Jazda {jz}."}
    if ride.get("otwarta") or any(p["kind"] in ("radar", "prognoza") for p in prev):
        return None
    b = max(a, now + dt.timedelta(minutes=hor))
    best, h = None, b.replace(minute=0, second=0, microsecond=0)
    while h < e:
        pv = prob.get(h.strftime("%Y-%m-%dT%H"))
        if pv is not None and pv >= PROB and (best is None or pv > best[1]):
            best = (h, pv)
        h += dt.timedelta(hours=1)
    if best:
        h, pv = best
        return {"kind": "prognoza", "eta": h, "text": f"🌦 Prognoza: {round(pv * 100)}% szans na deszcz ok. {h:%H}:00–{(h + dt.timedelta(hours=1)):%H}:00 "
                                                      f"w czasie jazdy {jz}. Radar na razie nic nie widzi — sprawdzam co 5 min i dam znać, gdy zobaczy opad."}
    return None


def _rides(cur, now: dt.datetime) -> list[dict]:
    cur.execute("""SELECT id, day, name, start_time, dur_min FROM qbot_v2.trainer_session WHERE username='admin' AND sport='rower'
                   AND status='plan' AND day=%s AND start_time IS NOT NULL""", (now.date(),))
    out = []
    for r in cur.fetchall():
        s = dt.datetime.combine(r["day"], r["start_time"], tzinfo=TZ)
        out.append({"id": r["id"], "nazwa": r["name"], "start": s, "koniec": s + dt.timedelta(minutes=int(r["dur_min"] or 60)), "src": "trener"})
    return out


def _live_ride(live: dict, now: dt.datetime) -> dict:
    return {"id": live["id"], "nazwa": "jazda (Karoo)", "start": live["started_at"].astimezone(TZ),
            "koniec": now + dt.timedelta(minutes=HOR), "src": "karoo", "otwarta": True, "lat": live["lat"], "lon": live["lon"]}


def _key(r: dict) -> str:
    return f"radar:k{r['id']}" if r.get("src") == "karoo" else f"radar:{r['id']}"


def _nowcast(lat: float, lon: float, now: dt.datetime) -> list[dict]:
    import qbot_radar as RAD
    n = RAD.nowcast_point(lat, lon, lead_max=HOR)
    nc = []
    for p in n.get("prognoza") or []:
        t = dt.datetime.fromisoformat(p["iso"]).astimezone(TZ) if p.get("iso") else dt.datetime.combine(now.date(), dt.time.fromisoformat(p["t"]), tzinfo=TZ)
        nc.append({"t": t, "udzial": p.get("udzial"), "mmh": p.get("mmh")})
    return nc


def check(conn, send: bool = True, now: dt.datetime | None = None) -> list[dict]:
    from psycopg.rows import dict_row
    import qbot_notif as NF
    import qbot_pogoda as PG
    import qbot_karoo_live as KL
    cur = conn.cursor(row_factory=dict_row)
    ensure(cur)
    now = now or dt.datetime.now(TZ)
    out = []
    KL.cleanup(cur, now)
    for kid in KL.ended_recently(cur, now):
        NF.resolve(cur, f"radar:k{kid}")
    rides = _rides(cur, now)
    for r in rides:
        if now > r["koniec"]:
            NF.resolve(cur, _key(r))
    live = KL.active(cur, now)
    if live:   # jazda z Karoo ma pierwszenstwo -- plany Trenera pomijane (bez dubli)
        act = [_live_ride(live, now)]
    else:
        act = [r for r in rides if r["start"] - dt.timedelta(minutes=LEAD_MIN) <= now <= r["koniec"]]
    if not act:
        return out
    on = NF.enabled_map(cur).get("radar", True)
    home = None
    prob = {}
    for r in act:
        if r.get("src") == "karoo":
            nc = _nowcast(r["lat"], r["lon"], now)
        else:
            if home is None:
                home = PG.home(cur) or {"lat": 52.23, "lon": 21.01}
                import qbot_pogoda_okno as PO
                prob = PO._ens_prob(home["lat"], home["lon"])
                nc_home = _nowcast(home["lat"], home["lon"], now)
            nc = nc_home
        cur.execute("SELECT kind, eta, tg_ok FROM qbot_v2.pogoda_alert WHERE ride_id=%s AND src=%s ORDER BY sent_at", (r["id"], r.get("src", "trener")))
        prev_rows = cur.fetchall()
        prev = [{"kind": x["kind"], "eta": x["eta"]} for x in prev_rows]
        d = decide(r, now, nc, prob, prev)
        if not d:
            continue
        ok = None
        tg_juz = any(x["tg_ok"] for x in prev_rows)   # Telegram: tylko pierwsze ostrzezenie na jazde
        if send and on and not tg_juz:
            import qbot_trener_notify as TN
            ok, _ = TN.send(d["text"] + f"\nalbert.cytr.us{URL}")
        data = {k: d[k] for k in ("mmh", "dur", "otwarte") if k in d}
        cur.execute("INSERT INTO qbot_v2.pogoda_alert (ride_id, day, kind, eta, text, tg_ok, src, data) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (r["id"], now.date(), d["kind"], d["eta"], d["text"], ok, r.get("src", "trener"), json.dumps(data) if data else None))
        if on:
            NF.push(cur, _key(r), "pogoda", "Deszcz w czasie jazdy" if d["kind"] == "radar" else "Możliwy deszcz w czasie jazdy",
                    d["text"], URL)
        out.append(dict(d, ride=r["id"], src=r.get("src", "trener"), telegram=ok))
    return out


def current(cur) -> dict:
    """Ostatnie ostrzezenie dla jazdy trwajacej (Karoo) albo z planu Trenera trwajacej / zaczynajacej sie w ciagu LEAD_MIN (pasek na Pogodzie)."""
    import qbot_karoo_live as KL
    ensure(cur)
    now = dt.datetime.now(TZ)
    live = KL.active(cur, now)
    if live:
        cur.execute("SELECT kind, eta, text, sent_at FROM qbot_v2.pogoda_alert WHERE src='karoo' AND ride_id=%s ORDER BY sent_at DESC LIMIT 1",
                    (live["id"],))
        x = cur.fetchone()
        if not x:
            return {"status": "BRAK", "jazda": "jazda (Karoo)"}
        return {"status": "OK", "kind": x["kind"], "text": x["text"], "eta": x["eta"].isoformat() if x["eta"] else None,
                "sent_at": x["sent_at"].isoformat(), "jazda": "jazda (Karoo)"}
    act = {r["id"]: r for r in _rides(cur, now) if r["start"] - dt.timedelta(minutes=LEAD_MIN) <= now <= r["koniec"]}
    if not act:
        return {"status": "BRAK"}
    cur.execute("SELECT ride_id, kind, eta, text, sent_at FROM qbot_v2.pogoda_alert WHERE src='trener' AND ride_id = ANY(%s) ORDER BY sent_at DESC LIMIT 1",
                (list(act),))
    x = cur.fetchone()
    if not x:
        return {"status": "BRAK"}
    return {"status": "OK", "kind": x["kind"], "text": x["text"], "eta": x["eta"].isoformat() if x["eta"] else None,
            "sent_at": x["sent_at"].isoformat(), "jazda": act[x["ride_id"]]["nazwa"]}
