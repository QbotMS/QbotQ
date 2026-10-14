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

WELL = {"hrv": ("HRV", "ms", +1), "rhr": ("tętno spoczynkowe", "bpm", -1), "sleep": ("sen (score)", "pkt", +1), "rdy3": ("gotowość 3 dni", "", +1),
        "hrr": ("tętno odpoczynku po akcentach (HRR60)", "bpm", +1)}
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


def _r(v, d=1):
    return None if v is None else round(v, d)

def _conf(n, p, short=False):
    """Pewnosc liczona przez QBota (AI jej nie zmienia)."""
    if short or n is None or p is None:
        return "niska"
    if n >= 30 and p < 0.01:
        return "wysoka"
    if n >= 15 and p < 0.05:
        return "średnia"
    return "niska"


def _deweek(series, days):
    """Usuwa efekt dnia tygodnia: od wartosci odejmuje srednia dla danego dnia tygodnia (w calym zakresie)."""
    by = {}
    for v, d in zip(series, days):
        if v is not None:
            by.setdefault(d.weekday(), []).append(v)
    mw = {k: sum(x) / len(x) for k, x in by.items() if len(x) >= 3}
    return [None if v is None else v - mw.get(d.weekday(), 0.0) for v, d in zip(series, days)]


def discover(rows: list[dict], a: int, b: int) -> dict:
    """Silnik odkryc v3. rows = caly zakres (normy osobiste 28 dni), [a, b] = analizowane okno (indeksy)."""
    N = len(rows)
    days = [date.fromisoformat(r["day"][:10]) for r in rows]
    col = lambda k: [_num(r.get(k)) for r in rows]
    C = {k: col(k) for k in ("xss", "ctl", "atl", "sleep", "hrv", "rhr", "rdy3", "weight", "bal", "hrr")}
    C["xss"] = [v if v is not None else 0.0 for v in C["xss"]]
    short = (b - a + 1) < 28
    # noc po alkoholu = odstajacy punkt: wylaczona z norm i korelacji (osobno liczony koszt wieczoru z alkoholem)
    alc_n = [i for i in range(1, N) if rows[i - 1].get("alc")]
    raw_well = {k: list(C[k]) for k in WELL}
    for i in alc_n:
        for k in WELL:
            C[k][i] = None
    dlt, z = {}, {}
    for k in list(WELL) + ["xss", "atl", "bal"]:
        dlt[k], zz = [None] * N, [None] * N
        for i in range(N):
            v = C[k][i]
            if v is None:
                continue
            m, sd = _baseline(C[k], i)
            if m is None:
                continue
            dlt[k][i] = v - m
            zz[i] = (v - m) / sd if sd else None
        z[k] = _deweek(zz, days)          # bez efektu dnia tygodnia
    W = range(a, b + 1)
    pos = sorted(C["xss"][i] for i in range(N) if C["xss"][i] > 0)
    q75 = pos[int(len(pos) * 0.75)] if len(pos) >= 4 else None
    hard = [i for i in W if q75 and C["xss"][i] >= q75]
    rest = [i for i in W if C["xss"][i] == 0]
    F, CONF = [], {}

    # 1. reakcja na ciezka jazde: NASTEPNE noce (+1..+3) vs po dniu wolnym
    if q75 and len(hard) >= 3 and len(rest) >= 3:
        resp = {}
        for k, (nm, un, good) in WELL.items():
            row = []
            for lag in (1, 2, 3):
                h = _mean([dlt[k][i + lag] for i in hard if i + lag < N])
                r0 = _mean([dlt[k][i + lag] for i in rest if i + lag < N])
                row.append({"lag": lag, "po_ciezkiej": _r(h), "po_wolnym": _r(r0)})
            sd = _mean([_sd(C[k][max(0, i - 28):i]) for i in hard if i >= 10])
            rec = next((x["lag"] for x in row if x["po_ciezkiej"] is not None and sd and abs(x["po_ciezkiej"]) < 0.3 * sd), None)
            resp[k] = {"name": nm, "unit": un, "by_lag": row, "sd": _r(sd), "powrot_do_normy_dzien": rec}
        cf = "niska" if short or len(hard) < 8 else ("wysoka" if len(hard) >= 20 else "średnia")
        F.append({"id": "R1", "type": "reakcja_na_ciezka_jazde", "pewnosc": cf, "prog_xss": q75, "n_ciezkich": len(hard), "n_wolnych": len(rest), "wyniki": resp})
        CONF["R1"] = cf

    # 2. fizjologia: przyczyna -> skutek w KOLEJNYCH nocach (lag 1-3), bez par definicyjnych, bez efektu dnia tygodnia
    pairs = [(x, y) for x in ("xss", "atl", "bal") for y in WELL] + [("sleep", "hrv"), ("sleep", "rhr")]
    names = {**{k: v[0] for k, v in WELL.items()}, "xss": "obciążenie dnia (XSS)", "atl": "zmęczenie z treningów (ATL+)", "bal": "bilans kcal dnia"}
    units = {**{k: v[1] for k, v in WELL.items()}, "xss": "", "atl": "", "bal": "kcal"}
    cand = []
    for x, y in pairs:
        best = None
        for lag in (1, 2, 3):
            xs = [z[x][i] for i in W if i + lag < N]
            ys = [z[y][i + lag] for i in W if i + lag < N]
            r, n = _pearson(xs, ys)
            if r is None:
                continue
            if best is None or abs(r) > abs(best["r"]) + 0.05:
                p = _pval(r, n)
                ys_d = [dlt[y][i + lag] for i in W if i + lag < N and dlt[y][i + lag] is not None]
                best = {"x": x, "y": y, "lag": lag, "r": round(r, 2), "n": n, "p": round(p, 3), "efekt": round(r * (_sd(ys_d) or 0), 1)}
        if best and abs(best["r"]) >= 0.25 and best["p"] < 0.1:
            cand.append(best)
    cand.sort(key=lambda q: (q["p"], -abs(q["r"])))
    for k2, q in enumerate(cand[:6], 1):
        q["id"] = "Z%d" % k2
        q["pewnosc"] = _conf(q["n"], q["p"], short)
        q["x_nazwa"], q["y_nazwa"], q["y_jedn"] = names[q["x"]], names[q["y"]], units[q["y"]]
        CONF[q["id"]] = q["pewnosc"]
    F.append({"type": "zaleznosci_fizjologiczne", "uwaga": "przyczyna dnia d -> skutek w nocy d+lag (lag 1-3); odchylenia od normy 28 dni, bez efektu dnia tygodnia; "
              "obciazenie tylko treningowe; efekt = zmiana skutku w jednostkach przy przyczynie +1 SD", "wyniki": cand[:6]})

    # 3. ZACHOWANIE (nie fizjologia): czy jezdzisz mocniej w dni wysokiego HRV / gotowosci (ten sam dzien, HRV mierzone rano)
    beh = []
    for x in ("hrv", "rdy3"):
        r, n = _pearson([z[x][i] for i in W], [z["xss"][i] for i in W])
        if r is not None:
            p = _pval(r, n)
            beh.append({"id": "B_" + x, "x": names[x], "r": round(r, 2), "n": n, "p": round(p, 3), "pewnosc": _conf(n, p, short)})
            CONF["B_" + x] = beh[-1]["pewnosc"]
    low = [i for i in W if z["rdy3"][i] is not None and z["rdy3"][i] < -0.5]
    F.append({"type": "zachowanie_vs_sygnaly", "uwaga": "HRV/gotowosc mierzone rano PRZED jazda; to opis decyzji/planu (po usunieciu efektu dnia tygodnia), nie fizjologia",
              "wyniki": beh, "dni_niskiej_gotowosci": len(low), "ciezkie_jazdy_w_niskiej": len([i for i in low if q75 and C["xss"][i] >= q75])})

    # 4. deficyt -> regeneracja nastepnej nocy
    big = [i for i in W if C["bal"][i] is not None and C["bal"][i] < -700]
    oth = [i for i in W if C["bal"][i] is not None and C["bal"][i] >= -700]
    if len(big) >= 3 and len(oth) >= 3:
        res = {k: {"name": nm, "unit": un, "po_duzym_deficycie": _r(_mean([dlt[k][i + 1] for i in big if i + 1 < N])),
                   "po_pozostalych": _r(_mean([dlt[k][i + 1] for i in oth if i + 1 < N]))} for k, (nm, un, _) in WELL.items()}
        cf = "niska" if short or len(big) < 10 else ("wysoka" if len(big) >= 20 else "średnia")
        F.append({"id": "D1", "type": "deficyt_a_regeneracja", "pewnosc": cf, "dni_duzy_deficyt": len(big), "dni_pozostale": len(oth), "wyniki": res})
        CONF["D1"] = cf
    else:
        F.append({"type": "deficyt_a_regeneracja", "za_malo_danych": True, "dni_z_bilansem": len(big) + len(oth)})

    # 4b. koszt wieczoru z alkoholem (noc po) vs norma
    an = [i for i in alc_n if a <= i <= b + 1]
    if an:
        cost = {}
        for k, (nm, un, _) in WELL.items():
            vals = []
            for i in an:
                m, _sd0 = _baseline(C[k], i)
                if m is not None and raw_well[k][i] is not None:
                    vals.append(raw_well[k][i] - m)
            cost[k] = {"name": nm, "unit": un, "noc_po_alkoholu": _r(_mean(vals))}
        F.append({"id": "A1", "type": "alkohol", "pewnosc": "niska" if len(an) < 5 else "średnia", "wieczorow": len(an), "koszt": cost,
                  "uwaga": "noce po alkoholu wylaczone z pozostalych analiz"})
        CONF["A1"] = "niska" if len(an) < 5 else "średnia"

    # 5. trend formy vs regeneracji (srednie 7 dni)
    ma = lambda k: [_mean(C[k][max(0, i - 6):i + 1]) for i in W]
    F.append({"id": "T1", "type": "trend_formy_vs_regeneracji", "pewnosc": "niska" if short else "średnia",
              "forma_na_tydz": _r(_slope_per_week([C["ctl"][i] for i in W]), 2), "hrv_na_tydz": _r(_slope_per_week(ma("hrv")), 2),
              "rhr_na_tydz": _r(_slope_per_week(ma("rhr")), 2), "sen_na_tydz": _r(_slope_per_week(ma("sleep")), 2),
              "waga_na_tydz": _r(_slope_per_week([C["weight"][i] for i in W]), 2)})
    CONF["T1"] = "niska" if short else "średnia"
    return {"okno": [rows[a]["day"][:10], rows[b]["day"][:10]], "dni": b - a + 1, "krotkie_okno": short,
            "jazdy": len([i for i in W if C["xss"][i] > 0]), "odkrycia": F, "_conf": CONF}



PROMPT = (
    "Jesteś trenerem kolarskim i fizjologiem. Zawodnik (kolarz gravel ~104 kg, redukcja) sam czyta wykresy – NIE opisuj trendów "
    "i NIE komentuj par z jednego modelu. Dostajesz policzone odkrycia względem jego normy z 28 dni, po usunięciu efektu dnia tygodnia. "
    "Zasady: (1) nie licz własnych liczb, nie wymyślaj danych; (2) PEWNOŚĆ przepisz z pola 'pewnosc' i podaj 'zrodlo' = pole 'id' odkrycia – nie oceniaj jej sam; "
    "(3) 'zachowanie_vs_sygnaly' to opis decyzji i planu (HRV mierzone rano przed jazdą), NIE fizjologia – nigdy nie pisz, że jazda podnosi HRV tego samego dnia; "
    "(4) nie podawaj mechanizmów fizjologicznych, których nie ma w danych – najwyżej jedno 'możliwe wyjaśnienie' w trybie przypuszczającym; "
    "(5) gdy 'krotkie_okno' = true, zacznij nagłówek od 'Krótki okres –' i traktuj wszystko jako orientacyjne; "
    "(6) jeśli nic nie jest wiarygodne, powiedz to wprost zamiast na siłę szukać wniosków. "
    "Pisz zwięźle i konkretnie, jak trener na odprawie. Limity: naglowek maks. 20 słów; 2-4 odkrycia od najpewniejszego; "
    "tytul maks. 10 słów; co = maks. 2 krótkie zdania (maks. 35 słów) z kluczowymi liczbami; znaczenie = konkretne polecenie maks. 20 słów; "
    "eksperyment maks. 35 słów; brakuje maks. 15 słów albo pusty tekst. "
    "Zwróć WYŁĄCZNIE JSON: {\"naglowek\": \"...\", \"odkrycia\": [{\"zrodlo\": \"id\", \"tytul\": \"...\", \"co\": \"...\", \"znaczenie\": \"...\", "
    "\"pewnosc\": \"...\"}], \"eksperyment\": \"...\", \"brakuje\": \"...\"}.")


def _words(txt, n):
    """Twarde obciecie do n slow (gdyby AI przekroczylo limit)."""
    w = str(txt or "").split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


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
            hm = {x["day"].isoformat(): float(x["h"]) for x in c.execute(
                "SELECT day, avg(hrr60) h FROM qbot_v2.ride_hrr WHERE hrr60 IS NOT NULL AND day BETWEEN %s AND %s GROUP BY day", (days[0], days[-1])).fetchall()}
            for r in rows:
                r["hrr"] = hm.get(r["day"][:10])
            alc = FP.alcohol_days(c, date.fromisoformat(days[0]), date.fromisoformat(days[-1]))
            for r in rows:
                r["alc"] = date.fromisoformat(r["day"][:10]) in alc
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
        if (e - a + 1) < 28:
            disc["uwaga_okno"] = "okno krotsze niz 28 dni - wnioski tylko orientacyjne"
        disc["skupienie_uzytkownika"] = b.get("focus") or []
        import qbot_food_log as F
        try:
            j = F._ai_json(PROMPT, [{"type": "text", "text": json.dumps({k: v for k, v in disc.items() if k != "_conf"}, ensure_ascii=False, default=str)}])
        except Exception as ex:
            raise HTTPException(status_code=502, detail="AI niedostępne: %s" % type(ex).__name__)
        LIM = {"tytul": 13, "co": 42, "znaczenie": 24, "pewnosc": 2}
        odk = [o for o in (j.get("odkrycia") or []) if isinstance(o, dict)]
        conf = disc.pop("_conf", {})
        for o in odk:   # pewnosc zawsze z obliczen QBota (po 'zrodlo'); bez zrodla = niska
            o["pewnosc"] = conf.get(str(o.get("zrodlo") or "").strip(), "niska")
        odk = sorted(odk, key=lambda o: {"wysoka": 0, "średnia": 1}.get(str(o.get("pewnosc")), 2))[:4]
        if disc.get("krotkie_okno") and not str(j.get("naglowek") or "").startswith("Krótki okres"):
            j["naglowek"] = "Krótki okres – orientacyjnie. " + str(j.get("naglowek") or "")
        ai = {"naglowek": _words(j.get("naglowek"), 26), "eksperyment": _words(j.get("eksperyment"), 40), "brakuje": _words(j.get("brakuje"), 18),
              "odkrycia": [{k: _words(o.get(k), LIM[k]) for k in LIM} for o in odk]}
        return {"ai": ai, "policzone": json.loads(json.dumps(disc, default=lambda o: str(o)))}

    return r
