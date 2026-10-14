"""Ostrzezenie o deszczu w czasie jazdy (radar + zespol). Dok.: docs/POGODA_OSTRZEZENIE.md

Decyzje Michala 14.10.2026 (po ulewie 14:50 przy ocenie 'jedz'): TYLKO deszcz; strona (dzwonek w menu + pasek na Pogodzie)
i Telegram; ostrzezenie dla CALEJ dlugosci jazdy; QExt2 na razie bez zmian.
- Jazdy: Trener (sport rower, status plan) -- pilnowanie od LEAD_MIN przed startem do konca jazdy. Punkt: dom (Trener).
- Czesc jazdy w zasiegu radaru (HOR min, wg sprawdzalnosci radaru ~60): prognoza radaru (nowcast_point) -> 'radar' z godzina,
  sila (mm/h) i czasem trwania epizodu. Dalsza czesc jazdy: szansa z zespolu ICON-EU-EPS >= PROB -> 'prognoza' (wyraznie oznaczona).
- Bez zasypywania: max MAX_MSG wiadomosci na jazde; radar -- kolejna tylko dla NOWEGO epizodu (poprzedni minal) albo gdy godzina
  przesunela sie o > ETA_SHIFT min; prognoza -- raz na jazde i tylko zanim radar cokolwiek zobaczyl.
- Zrodlo w dzwonku: 'radar' (klucz radar:<id jazdy>), mozna wylaczyc w ustawieniach powiadomien -- wtedy tez bez Telegrama.
Wywolanie: petla radaru w qbot-web (co nowa klatke, ~5 min). Stan: qbot_v2.pogoda_alert.
"""
from __future__ import annotations

import datetime as dt
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


def sila(mmh: float) -> str:
    return "słaby" if mmh < 1 else "umiarkowany" if mmh < 4 else "silny" if mmh < 10 else "ulewa"


def _pl(x) -> str:
    return str(round(x, 1)).replace(".", ",")


def decide(ride: dict, now: dt.datetime, nowcast: list[dict], prob: dict, prev: list[dict], hor: int = HOR) -> dict | None:
    """Czysta decyzja. ride: {id, nazwa, start, koniec (datetime)}; nowcast: [{t: datetime, udzial, mmh}] (prognoza radaru);
    prob: {'RRRR-MM-DDTHH': szansa 0-1 dla godziny HH..HH+1}; prev: wyslane [{kind, eta}]. Zwraca {kind, eta, text} albo None."""
    if len(prev) >= MAX_MSG or now > ride["koniec"]:
        return None
    a, e = max(now, ride["start"]), ride["koniec"]
    lim = min(e, now + dt.timedelta(minutes=hor))
    sl = [p for p in nowcast if a - dt.timedelta(minutes=4) <= p["t"] <= lim and p.get("udzial") is not None]
    jz = f"„{ride['nazwa']}” {ride['start']:%H:%M}–{e:%H:%M}"
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
        return {"kind": "radar", "eta": eta, "text": f"🌧 Radar: {kiedy}, {sila(mx)} (do {_pl(mx)} mm/h), {trwa}. Jazda {jz}."}
    if any(p["kind"] in ("radar", "prognoza") for p in prev):
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
        out.append({"id": r["id"], "nazwa": r["name"], "start": s, "koniec": s + dt.timedelta(minutes=int(r["dur_min"] or 60))})
    return out


def check(conn, send: bool = True, now: dt.datetime | None = None) -> list[dict]:
    from psycopg.rows import dict_row
    import qbot_notif as NF
    import qbot_pogoda as PG
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(DDL)
    now = now or dt.datetime.now(TZ)
    out = []
    rides = _rides(cur, now)
    for r in rides:
        if now > r["koniec"]:
            NF.resolve(cur, f"radar:{r['id']}")
    act = [r for r in rides if r["start"] - dt.timedelta(minutes=LEAD_MIN) <= now <= r["koniec"]]
    if not act:
        return out
    h = PG.home(cur) or {"lat": 52.23, "lon": 21.01}
    import qbot_radar as RAD
    n = RAD.nowcast_point(h["lat"], h["lon"], lead_max=HOR)
    base = dt.datetime.fromisoformat(n["prognoza"][0]["iso"]) if n.get("prognoza") and n["prognoza"][0].get("iso") else None
    nc = []
    for p in n.get("prognoza") or []:
        t = dt.datetime.fromisoformat(p["iso"]).astimezone(TZ) if p.get("iso") else dt.datetime.combine(now.date(), dt.time.fromisoformat(p["t"]), tzinfo=TZ)
        nc.append({"t": t, "udzial": p.get("udzial"), "mmh": p.get("mmh")})
    import qbot_pogoda_okno as PO
    prob = PO._ens_prob(h["lat"], h["lon"])
    on = NF.enabled_map(cur).get("radar", True)
    for r in act:
        cur.execute("SELECT kind, eta FROM qbot_v2.pogoda_alert WHERE ride_id=%s ORDER BY sent_at", (r["id"],))
        prev = [{"kind": x["kind"], "eta": x["eta"]} for x in cur.fetchall()]
        d = decide(r, now, nc, prob, prev)
        if not d:
            continue
        ok = None
        if send and on:
            import qbot_trener_notify as TN
            ok, _ = TN.send(d["text"] + f"\nalbert.cytr.us{URL}")
        cur.execute("INSERT INTO qbot_v2.pogoda_alert (ride_id, day, kind, eta, text, tg_ok) VALUES (%s,%s,%s,%s,%s,%s)",
                    (r["id"], now.date(), d["kind"], d["eta"], d["text"], ok))
        if on:
            NF.push(cur, f"radar:{r['id']}", "pogoda", "Deszcz w czasie jazdy" if d["kind"] == "radar" else "Możliwy deszcz w czasie jazdy",
                    d["text"], URL)
        out.append(dict(d, ride=r["id"], telegram=ok))
    return out


def current(cur) -> dict:
    """Ostatnie ostrzezenie dla jazdy trwajacej / zaczynajacej sie w ciagu LEAD_MIN (pasek na stronie Pogoda)."""
    cur.execute(DDL)
    now = dt.datetime.now(TZ)
    act = {r["id"]: r for r in _rides(cur, now) if r["start"] - dt.timedelta(minutes=LEAD_MIN) <= now <= r["koniec"]}
    if not act:
        return {"status": "BRAK"}
    cur.execute("SELECT ride_id, kind, eta, text, sent_at FROM qbot_v2.pogoda_alert WHERE ride_id = ANY(%s) ORDER BY sent_at DESC LIMIT 1", (list(act),))
    x = cur.fetchone()
    if not x:
        return {"status": "BRAK"}
    return {"status": "OK", "kind": x["kind"], "text": x["text"], "eta": x["eta"].isoformat() if x["eta"] else None,
            "sent_at": x["sent_at"].isoformat(), "jazda": act[x["ride_id"]]["nazwa"]}
