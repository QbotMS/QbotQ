"""Forma -> Trendy: ANALIZA AI v2 (2026-10-12) - silnik odkryc + interpretacja AI. Wynik NIE jest zapisywany.

Po co: v1 opisywala to, co widac na wykresie, i liczyla pary definicyjne (forma<->CP, zmeczenie<->swiezosc).
v2 najpierw LICZY rzeczy niewidoczne golym okiem (wzgledem osobistej normy z 28 dni), AI tylko je interpretuje:
  1. reakcja na ciezka jazde (HRV/RHR/sen/gotowosc +1..+3 dni vs dni wolne) i czas powrotu do normy,
  2. zaleznosci z opoznieniem 0-3 dni WYLACZNIE miedzy rodzinami (trening <-> wellness, sen <-> HRV/RHR, jedzenie <-> wellness),
     na odchyleniach od normy, z istotnoscia i efektem w jednostkach,
  3. czy sluchasz sygnalow (ciezkie jazdy w dni niskiej gotowosci i ich skutek nastepnego dnia),
  4. dawka-odpowiedz tygodniami (obciazenie tygodnia -> zmiana HRV w kolejnym),
  5. deficyt kaloryczny -> regeneracja nastepnego dnia,
  6. ukryte przeciazenie: forma rosnie, a bazowe HRV spada / RHR rosnie.
POST /api/trendy/ai  {from, to, rows:[{day,xss,ctl,atl,tsb,sleep,hrv,rhr,rdy3,rdy1,body,ramp,weight,cp,ltp}], focus:[...], ill:[...]}
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request

WELL = {"hrv": ("HRV", "ms", +1), "rhr": ("tętno spoczynkowe", "bpm", -1), "sleep": ("sen (score)", "pkt", +1), "rdy3": ("gotowość 3 dni", "", +1)}
LOADF = {"xss": ("obciążenie dnia (XSS)", ""), "atl": ("zmęczenie faktyczne", ""), "bal": ("bilans kcal dnia", "kcal")}


def _num(v):
    try:
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
    except (TypeError, ValueError):
        return None


def _mean(a):
    a = [x for x in a if x is not None]
    return sum(a) / len(a) if a else None


def _sd(a):
    a = [x for x in a if x is not None]
    if len(a) < 3:
        return None
    m = sum(a) / len(a)
    return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1)) or None


def _baseline(vals, i, win=28, minn=8):
    """Norma osobista: srednia i SD z poprzednich `win` dni (bez dnia i)."""
    a = [v for v in vals[max(0, i - win):i] if v is not None]
    if len(a) < minn:
        return None, None
    return sum(a) / len(a), _sd(a)


def _pearson(xs, ys):
    p = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(p)
    if n < 10:
        return None, n
    mx = sum(x for x, _ in p) / n
    my = sum(y for _, y in p) / n
    sxy = sum((x - mx) * (y - my) for x, y in p)
    sx = sum((x - mx) ** 2 for x, _ in p)
    sy = sum((y - my) ** 2 for _, y in p)
    if not sx or not sy:
        return None, n
    return sxy / math.sqrt(sx * sy), n


def _pval(r, n):
    if r is None or n < 4 or abs(r) >= 1:
        return 0.0 if r is not None and abs(r) >= 1 else 1.0
    t = abs(r) * math.sqrt((n - 2) / (1 - r * r))
    return 2 * (1 - 0.5 * (1 + math.erf(t / math.sqrt(2))))   # przyblizenie normalne


def _slope_per_week(vals):
    p = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(p) < 7:
        return None
    n = len(p)
    mx = sum(i for i, _ in p) / n
    my = sum(v for _, v in p) / n
    sxx = sum((i - mx) ** 2 for i, _ in p)
    return (sum((i - mx) * (v - my) for i, v in p) / sxx) * 7 if sxx else None


def _fmt(v, d=1):
    return ("%+." + str(d) + "f") % v if v is not None else "–"


def discover(rows: list[dict], a: int, b: int) -> dict:
    """Silnik odkryc. rows = caly zakres (dla norm), [a, b] = analizowane okno (indeksy)."""
    N = len(rows)
    col = lambda k: [_num(r.get(k)) for r in rows]
    C = {k: col(k) for k in ("xss", "ctl", "atl", "tsb", "sleep", "hrv", "rhr", "rdy3", "rdy1", "weight", "bal", "cp", "ltp")}
    C["xss"] = [v if v is not None else 0.0 for v in C["xss"]]
    # odchylenia od osobistej normy (delta w jednostkach i z)
    dlt, z = {}, {}
    for k in list(WELL) + ["xss", "atl", "bal"]:
        dlt[k], z[k] = [None] * N, [None] * N
        for i in range(N):
            v = C[k][i]
            if v is None:
                continue
            m, s = _baseline(C[k], i)
            if m is None:
                continue
            dlt[k][i] = v - m
            z[k][i] = (v - m) / s if s else None
    W = range(a, b + 1)
    rides = [i for i in W if C["xss"][i] > 0]
    pos = sorted(C["xss"][i] for i in range(N) if C["xss"][i] > 0)
    q75 = pos[int(len(pos) * 0.75)] if len(pos) >= 4 else None
    hard = [i for i in W if q75 and C["xss"][i] >= q75]
    rest = [i for i in W if C["xss"][i] == 0]
    F = []

    # 1. reakcja na ciezka jazde
    if q75 and len(hard) >= 3 and len(rest) >= 3:
        resp = {}
        for k, (nm, un, good) in WELL.items():
            row = []
            for lag in (1, 2, 3):
                h = _mean([dlt[k][i + lag] for i in hard if i + lag < N])
                r0 = _mean([dlt[k][i + lag] for i in rest if i + lag < N])
                nh = len([1 for i in hard if i + lag < N and dlt[k][i + lag] is not None])
                row.append({"lag": lag, "hard": h, "rest": r0, "n_hard": nh})
            sd = _mean([_sd(C[k][max(0, i - 28):i]) for i in hard if i >= 10])
            rec = next((x["lag"] for x in row if x["hard"] is not None and sd and abs(x["hard"]) < 0.3 * sd), None)
            resp[k] = {"name": nm, "unit": un, "by_lag": row, "sd": sd, "recovery_day": rec}
        F.append({"type": "reakcja_na_ciezka_jazde", "prog_xss": q75, "n_ciezkich": len(hard), "n_wolnych": len(rest), "wyniki": resp})

    # 2. zaleznosci z opoznieniem, tylko miedzy rodzinami, na odchyleniach od normy
    pairs = [(x, y) for x in ("xss", "atl", "bal") for y in WELL] + [("sleep", "hrv"), ("sleep", "rhr"), ("sleep", "rdy3"), ("hrv", "xss"), ("rdy3", "xss")]
    cand = []
    for x, y in pairs:
        best = None
        for lag in range(0, 4):
            xs = [z[x][i] for i in W if i + lag < N]
            ys = [z[y][i + lag] for i in W if i + lag < N]
            r, n = _pearson(xs, ys)
            if r is None:
                continue
            p = _pval(r, n)
            if best is None or abs(r) > abs(best["r"]) + 0.05:
                # efekt w jednostkach: o ile zmienia sie y (w jedn.) przy +1 SD x
                ys_d = [dlt[y][i + lag] for i in W if i + lag < N and dlt[y][i + lag] is not None]
                eff = r * (_sd(ys_d) or 0)
                best = {"x": x, "y": y, "lag": lag, "r": round(r, 2), "n": n, "p": round(p, 3), "efekt": round(eff, 1)}
        if best and abs(best["r"]) >= 0.25 and best["p"] < 0.1:
            cand.append(best)
    cand.sort(key=lambda q: -abs(q["r"]))
    names = {**{k: v[0] for k, v in WELL.items()}, **{k: v[0] for k, v in LOADF.items()}}
    units = {**{k: v[1] for k, v in WELL.items()}, "xss": "", "atl": "", "bal": "kcal"}
    for q in cand:
        q["x_nazwa"], q["y_nazwa"], q["y_jedn"] = names.get(q["x"], q["x"]), names.get(q["y"], q["y"]), units.get(q["y"], "")
    F.append({"type": "zaleznosci_z_opoznieniem", "uwaga": "r na odchyleniach od osobistej normy 28 dni; lag = o ile dni y jest po x; efekt = zmiana y w jednostkach przy x o 1 SD powyzej normy",
              "wyniki": cand[:8]})

    # 3. czy sluchasz sygnalow
    low = [i for i in W if z["rdy3"][i] is not None and z["rdy3"][i] < -0.5]
    good = [i for i in W if z["rdy3"][i] is not None and z["rdy3"][i] > 0.3]
    if q75 and len(low) >= 3:
        hard_low = [i for i in low if C["xss"][i] >= q75]
        hard_good = [i for i in good if C["xss"][i] >= q75]
        nxt = lambda idx: _mean([dlt["rdy3"][i + 1] - (dlt["rdy3"][i] or 0) for i in idx if i + 1 < N and dlt["rdy3"][i + 1] is not None and dlt["rdy3"][i] is not None])
        F.append({"type": "sluchanie_sygnalow", "dni_niskiej_gotowosci": len(low), "ciezkie_w_niskiej": len(hard_low),
                  "ciezkie_w_dobrej": len(hard_good), "zmiana_gotowosci_dzien_po_ciezkiej_w_niskiej": nxt(hard_low),
                  "zmiana_gotowosci_dzien_po_ciezkiej_w_dobrej": nxt(hard_good)})

    # 4. dawka-odpowiedz tygodniami
    weeks = {}
    for i in W:
        d = date.fromisoformat(rows[i]["day"][:10])
        wk = d - timedelta(days=d.weekday())
        weeks.setdefault(wk, []).append(i)
    wl = sorted(weeks)
    if len(wl) >= 5:
        xs, ys = [], []
        for k in range(len(wl) - 1):
            load = sum(C["xss"][i] for i in weeks[wl[k]])
            nh = _mean([C["hrv"][i] for i in weeks[wl[k + 1]]])
            th = _mean([C["hrv"][i] for i in weeks[wl[k]]])
            if nh is not None and th is not None:
                xs.append(load)
                ys.append(nh - th)
        r, n = _pearson(xs, ys) if len(xs) >= 5 else (None, len(xs))
        if r is not None:
            sl = r * (_sd(ys) or 0) / (_sd(xs) or 1) * 100
            F.append({"type": "dawka_odpowiedz_tygodnie", "tygodni": n, "r": round(r, 2), "hrv_ms_na_100_xss": round(sl, 2)})

    # 5. deficyt -> regeneracja
    big = [i for i in W if C["bal"][i] is not None and C["bal"][i] < -700]
    oth = [i for i in W if C["bal"][i] is not None and C["bal"][i] >= -700]
    if len(big) >= 3 and len(oth) >= 3:
        res = {}
        for k, (nm, un, _) in WELL.items():
            res[k] = {"name": nm, "unit": un, "po_duzym_deficycie": _mean([dlt[k][i + 1] for i in big if i + 1 < N]),
                      "po_pozostalych": _mean([dlt[k][i + 1] for i in oth if i + 1 < N])}
        F.append({"type": "deficyt_a_regeneracja", "dni_duzy_deficyt": len(big), "dni_pozostale": len(oth), "wyniki": res})
    else:
        F.append({"type": "deficyt_a_regeneracja", "za_malo_danych": True, "dni_z_bilansem": len(big) + len(oth)})

    # 6. ukryte przeciazenie: trend formy vs trend norm HRV/RHR (srednie 7 dni)
    ma = lambda k: [_mean(C[k][max(0, i - 6):i + 1]) for i in W]
    F.append({"type": "trend_formy_vs_regeneracji", "forma_na_tydz": _slope_per_week([C["ctl"][i] for i in W]),
              "hrv_na_tydz": _slope_per_week(ma("hrv")), "rhr_na_tydz": _slope_per_week(ma("rhr")), "sen_na_tydz": _slope_per_week(ma("sleep")),
              "waga_na_tydz": _slope_per_week([C["weight"][i] for i in W])})
    return {"okno": [rows[a]["day"][:10], rows[b]["day"][:10]], "dni": b - a + 1, "jazdy": len(rides), "odkrycia": F}


def _r(v, d=1):
    return None if v is None else round(v, d)


PROMPT = (
    "Jesteś bardzo dobrym trenerem kolarskim i fizjologiem z zacięciem analityka. Zawodnik: kolarz gravel ~104 kg, redukcja wagi, "
    "trenuje z planem, sam umie czytać wykresy – NIE opisuj trendów widocznych na wykresie i NIE komentuj zależności definicyjnych "
    "(forma/zmęczenie/świeżość/CP to jeden model). Dostajesz WYŁĄCZNIE policzone odkrycia (względem jego osobistej normy z 28 dni): "
    "reakcję na ciężką jazdę, zależności z opóźnieniem między treningiem/snem/jedzeniem a wellness, to czy słucha sygnałów, dawkę-odpowiedź, "
    "deficyt vs regenerację, trend formy vs regeneracji. Nie licz własnych liczb, nie wymyślaj danych; gdy n jest małe lub p > 0,05 – powiedz wprost, "
    "że to hipoteza. Szukaj tego, czego nie widać od razu: opóźnień, asymetrii, czasu regeneracji, sprzeczności (forma rośnie, a regeneracja słabnie), "
    "konsekwencji dla planu i jedzenia. Mów konkretnie, z liczbami i jednostkami, krótko, po polsku, z charakterem (bez lania wody i ogólników typu "
    "'sen jest ważny'). Zwróć WYŁĄCZNIE JSON: {\"naglowek\": \"jedno mocne zdanie – najważniejsze odkrycie\", "
    "\"odkrycia\": [{\"tytul\": \"...\", \"co\": \"co wynika z liczb (1-2 zdania)\", \"znaczenie\": \"co z tym zrobić w treningu/jedzeniu\", \"pewnosc\": \"wysoka|średnia|niska\"}], "
    "\"eksperyment\": \"jeden konkretny test na 2 tygodnie, który potwierdzi lub obali najciekawszą hipotezę\", "
    "\"brakuje\": \"czego brakuje w danych, żeby powiedzieć więcej (1 zdanie)\"} – odkryć 3 do 5, od najciekawszego.")


def _fill_food(rows):
    """Bilans kcal dnia (zjedzone - spalone realne) dla dni z wpisami - z bazy QBota."""
    try:
        import qbot_food_plan as FP
        days = [r["day"][:10] for r in rows]
        with FP._conn() as c:
            itk = {x["date"].isoformat(): float(x["k"]) for x in c.execute(
                "SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                "WHERE l.date BETWEEN %s AND %s GROUP BY l.date", (days[0], days[-1])).fetchall() if x["k"]}
            for r in rows:
                d = r["day"][:10]
                if d in itk:
                    ex = FP.expend(c, date.fromisoformat(d))
                    if ex["src"] == "realne":
                        r["bal"] = itk[d] - ex["kcal"]
    except Exception:
        pass
    return rows


def build_router(current_user, owner_user):
    r = APIRouter(prefix="/api/trendy")

    @r.post("/ai")
    async def trend_ai(request: Request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="zły JSON")
        rows = b.get("rows") or []
        if len(rows) < 14 or len(rows) > 800:
            raise HTTPException(status_code=400, detail="potrzeba 14–800 dni danych")
        days = [str(x.get("day", ""))[:10] for x in rows]
        a = days.index(b["from"]) if b.get("from") in days else 0
        e = days.index(b["to"]) if b.get("to") in days else len(rows) - 1
        if e - a + 1 < 10:
            raise HTTPException(status_code=400, detail="zaznacz co najmniej 10 dni")
        rows = _fill_food(rows)
        disc = discover(rows, a, e)
        disc["infekcje"] = b.get("ill") or []
        disc["skupienie_uzytkownika"] = b.get("focus") or []
        import qbot_food_log as F
        try:
            j = F._ai_json(PROMPT, [{"type": "text", "text": json.dumps(disc, ensure_ascii=False, default=lambda o: _r(o) if isinstance(o, float) else str(o))}])
        except Exception as ex:
            raise HTTPException(status_code=502, detail="AI niedostępne: %s" % type(ex).__name__)
        ai = {"naglowek": str(j.get("naglowek") or "")[:400], "eksperyment": str(j.get("eksperyment") or "")[:500],
              "brakuje": str(j.get("brakuje") or "")[:300],
              "odkrycia": [{k: str((o or {}).get(k) or "")[:500] for k in ("tytul", "co", "znaczenie", "pewnosc")} for o in (j.get("odkrycia") or [])][:5]}
        return {"ai": ai, "policzone": json.loads(json.dumps(disc, default=lambda o: str(o)))}

    return r
