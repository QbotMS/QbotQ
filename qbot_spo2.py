"""SpO2 nocne (2026-10-20, sesja spo2-2010): odczyty co minute z Garmina -> noc spokojna / niespokojna.

Zrodlo: qbot_v2.garmin_daily_raw (kind='sleep'), pole wellnessEpochSPO2DataDTOList -- pelna odpowiedz
get_sleep_data zapisywana przez qbot_garmin_extra (Garmin oddaje odczyty minutowe ok. 4,5 miesiaca
wstecz, dlatego historia zaczyna sie 01.06.2026). Data wiersza = dzien pobudki. epochTimestamp = GMT.

Miary nocy:
  med        -- mediana SpO2 nocy (wlasny poziom odniesienia tej nocy)
  drop_min   -- minuty >= DROP_PTS ponizej mediany nocy (glowna miara "niespokojnosci")
  events     -- spadki: ciagi minut spadkowych (przerwa <= GAP_MIN min laczy w jeden)
  below90    -- minuty < 90 %
Ocena nocy wzgledem WLASNEJ normy z NORM_NIGHTS poprzednich nocy (min. NORM_MIN):
  drop_min <= p75 -> spokojna, <= p90 -> do obserwacji, wiecej -> niespokojna.
Co idzie w parze (factors): alkohol dzien wczesniej, mocna jazda dzien wczesniej (TSS >= HARD_TSS)
-> minuty spadkow; niespokojna noc -> HRV i ocena snu rano. Pokazywane tylko wyrazne roznice.
Poranne ostrzezenie (morning_signal, 2026-10-20): >= 2 z 3 ostatnich nocy 'do obserwacji'/'niespokojna'
LUB tempo oddechu >= norma + RESP_UP (dodane 20.10), ORAZ tetno spoczynkowe dzis >= norma + 3 bpm (norma i zrodlo jak fitmodel/body_signal: srednia 60 nocy,
qbot_wellness_daily garmin). Historia 06-10.2026: 3 razy (13.08, 28.09, 12.10), zawsze bez sygnalu temp. skory.
Oddech w nocy (2026-10-20, ten sam zapis snu): wahania oddechu Garmina (breathingDisruptionData, poziom 1-2),
tempo oddechu (wellnessEpochRespirationDataDTOList), stres nocny, przyrost Body Battery, niespokojne momenty/h,
najnizsze tetno. Tempo oddechu vs wlasna norma (mediana 60 nocy) -- wzrost >= RESP_UP = sygnal (choroba).
Dok.: docs/SPO2.md.
"""
from __future__ import annotations

import statistics as st
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
DROP_PTS = 4
GAP_MIN = 3
NORM_NIGHTS = 60
NORM_MIN = 20
HARD_TSS = 100
RESP_UP = 1.0
LABEL = {"good": "spokojna", "warn": "do obserwacji", "bad": "niespokojna"}


def _q(vals: list[float], p: float) -> float:
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _ts(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).split(".")[0]).replace(tzinfo=timezone.utc).astimezone(TZ)
    except ValueError:
        return None


def _series(payload: dict) -> list[tuple[datetime, int]]:
    out = []
    for e in payload.get("wellnessEpochSPO2DataDTOList") or []:
        t, v = _ts(e.get("epochTimestamp")), e.get("spo2Reading")
        if t is not None and isinstance(v, (int, float)) and 70 <= v <= 100:
            out.append((t, int(v)))
    out.sort()
    return out


def _metrics(day: date, ser: list[tuple[datetime, int]]) -> dict:
    vals = [v for _, v in ser]
    med = st.median(vals)
    thr = med - DROP_PTS
    events, last = [], None
    for t, v in ser:
        if v <= thr:
            if events and last is not None and (t - last).total_seconds() <= GAP_MIN * 60:
                events[-1]["end"], events[-1]["min"] = t, min(events[-1]["min"], v)
                events[-1]["n"] += 1
            else:
                events.append({"start": t, "end": t, "min": v, "n": 1})
            last = t
    return {
        "day": day.isoformat(), "n": len(vals), "avg": round(sum(vals) / len(vals), 1), "med": med,
        "min": min(vals), "drop_min": sum(1 for v in vals if v <= thr),
        "below90": sum(1 for v in vals if v < 90), "events": len(events),
        "start": ser[0][0].strftime("%H:%M"), "end": ser[-1][0].strftime("%H:%M"),
        "_events": events,
    }


def _hm(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).astimezone(TZ).strftime("%H:%M")


def _num_list(p: dict, key: str, vk: str = "value") -> list[float]:
    return [float(e[vk]) for e in p.get(key) or [] if isinstance(e.get(vk), (int, float)) and e[vk] >= 0]


def _extras(p: dict, n_min: int) -> dict:
    """Pozostale dane z zapisu snu Garmina (te same co SpO2, wczesniej pomijane)."""
    bd = [e for e in p.get("breathingDisruptionData") or [] if e.get("startGMT") and e.get("endGMT")]
    bvm = lambda lv: round(sum((int(e["endGMT"]) - int(e["startGMT"])) / 60000 for e in bd if e.get("value") in lv))
    resp = [v for v in _num_list(p, "wellnessEpochRespirationDataDTOList", "respirationValue") if v > 0]
    stress = _num_list(p, "sleepStress")
    bb = _num_list(p, "sleepBodyBattery")
    hr = [v for v in _num_list(p, "sleepHeartRate") if v > 0]
    dto = p.get("dailySleepDTO") or {}
    hours = (dto.get("sleepTimeSeconds") or n_min * 60) / 3600
    rc = p.get("restlessMomentsCount")
    return {"bv_min": bvm((1, 2)), "bv2_min": bvm((2,)),
            "resp": round(st.mean(resp), 1) if resp else None,
            "stress": round(st.mean(stress)) if stress else None,
            "bb_gain": round(max(bb) - bb[0]) if bb else None,
            "hr_min": round(min(hr)) if hr else None,
            "restless_h": round(rc / hours, 1) if isinstance(rc, (int, float)) and hours > 1 else None}


def _load(c, since: date, until: date | None = None) -> list[tuple[date, dict]]:
    q = ("SELECT date, payload FROM qbot_v2.garmin_daily_raw WHERE kind='sleep' AND date >= %s "
         "AND jsonb_typeof(payload->'wellnessEpochSPO2DataDTOList')='array'")
    args: list = [since]
    if until is not None:
        q += " AND date <= %s"
        args.append(until)
    rows = c.execute(q + " ORDER BY date", args).fetchall()
    return [(r["date"], r["payload"]) for r in rows]


def nights(c, days: int = 120) -> list[dict]:
    """Noce z ostatnich `days` dni z ocena wzgledem normy z NORM_NIGHTS wczesniejszych nocy."""
    today = datetime.now(TZ).date()
    out = []
    for d, p in _load(c, today - timedelta(days=days + NORM_NIGHTS * 2)):
        ser = _series(p)
        if len(ser) >= 60:
            m = _metrics(d, ser)
            m.pop("_events")
            m.update(_extras(p, len(ser)))
            out.append(m)
    for i, m in enumerate(out):
        prev = [x["drop_min"] for x in out[max(0, i - NORM_NIGHTS):i]]
        if len(prev) >= NORM_MIN:
            p75, p90 = _q(prev, .75), _q(prev, .9)
            m["norm"], m["p75"], m["p90"] = st.median(prev), round(p75, 1), round(p90, 1)
            m["status"] = "good" if m["drop_min"] <= p75 else "warn" if m["drop_min"] <= p90 else "bad"
        else:
            m["norm"] = m["p75"] = m["p90"] = m["status"] = None
    for i, m in enumerate(out):   # tempo oddechu vs wlasna norma
        prev = [x["resp"] for x in out[max(0, i - NORM_NIGHTS):i] if x.get("resp")]
        m["resp_norm"] = round(st.median(prev), 1) if len(prev) >= NORM_MIN else None
        m["resp_delta"] = round(m["resp"] - m["resp_norm"], 1) if m.get("resp") and m["resp_norm"] else None
    cut = (today - timedelta(days=days)).isoformat()
    return [m for m in out if m["day"] >= cut]


def night_detail(c, day: date) -> dict | None:
    rows = _load(c, day, day)
    ser = _series(rows[0][1]) if rows else []
    if not ser:
        return None
    m = _metrics(day, ser)
    ev = m.pop("_events")
    m["series"] = [[t.strftime("%H:%M"), v] for t, v in ser]
    m["events_list"] = [{"start": e["start"].strftime("%H:%M"), "end": e["end"].strftime("%H:%M"),
                         "min": e["min"], "minutes": e["n"]} for e in ev]
    m["thr"] = m["med"] - DROP_PTS
    p = rows[0][1]
    m.update(_extras(p, len(ser)))
    m["resp_series"] = [[_hm(e["startTimeGMT"]), e["respirationValue"]] for e in p.get("wellnessEpochRespirationDataDTOList") or []
                        if e.get("startTimeGMT") and isinstance(e.get("respirationValue"), (int, float)) and e["respirationValue"] > 0]
    m["hr_series"] = [[_hm(e["startGMT"]), e["value"]] for e in p.get("sleepHeartRate") or []
                      if e.get("startGMT") and isinstance(e.get("value"), (int, float)) and e["value"] > 0]
    m["bv_segments"] = [{"start": _hm(e["startGMT"]), "end": _hm(e["endGMT"]), "level": e["value"]}
                        for e in p.get("breathingDisruptionData") or [] if e.get("value") in (1, 2) and e.get("startGMT") and e.get("endGMT")]
    return m


def context(c, start: date, end: date) -> dict:
    """Dane do 'co idzie w parze': alkohol, TSS dnia, HRV i ocena snu rano (klucze = ISO dnia)."""
    import qbot_food_plan as FP
    alc = {d.isoformat() for d in FP.alcohol_days(c, start - timedelta(days=1), end)}
    tss = {r["date"].isoformat(): float(r["t"]) for r in c.execute(
        "SELECT date, sum(tss) t FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s AND tss IS NOT NULL GROUP BY date",
        (start - timedelta(days=1), end)).fetchall()}
    slp = c.execute("SELECT date, avg(hrv_ms) h, max(sleep_score) s FROM qbot_v2.qbot_sleep_daily "
                    "WHERE date BETWEEN %s AND %s GROUP BY date", (start, end)).fetchall()
    return {"alcohol": alc, "tss": tss,
            "hrv": {r["date"].isoformat(): float(r["h"]) for r in slp if r["h"] is not None},
            "score": {r["date"].isoformat(): float(r["s"]) for r in slp if r["s"] is not None}}


def _prev(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def factors(ns: list[dict], ctx: dict) -> list[dict]:
    """Krotkie wnioski, tylko gdy roznica jest wyrazna i jest dosc nocy w obu grupach."""
    out = []

    def cmp_drop(name, test, min_n=8):
        a = [n["drop_min"] for n in ns if test(n)]
        b = [n["drop_min"] for n in ns if not test(n)]
        if len(a) < min_n or len(b) < 10:
            return
        ma, mb = st.median(a), st.median(b)
        if mb > 0 and ma >= mb * 1.3 + 2:
            out.append({"level": "bad", "text": f"{name}: spadków nocą ok. {round(ma / mb, 1)}× więcej niż zwykle ({len(a)} nocy)."})
        elif ma <= mb * 0.7:
            out.append({"level": "good", "text": f"{name}: noce spokojniejsze niż zwykle ({len(a)} nocy)."})

    cmp_drop("Po dniu z alkoholem", lambda n: _prev(n["day"]) in ctx["alcohol"])
    cmp_drop(f"Po mocnej jeździe (TSS ≥ {HARD_TSS})", lambda n: ctx["tss"].get(_prev(n["day"]), 0) >= HARD_TSS)

    rated = [n for n in ns if n.get("status")]
    for key, name, unit in (("hrv", "HRV rano", "%"), ("score", "ocena snu", "%")):
        src = ctx[key]
        hb = [src[n["day"]] for n in rated if n["status"] == "bad" and n["day"] in src]
        hg = [src[n["day"]] for n in rated if n["status"] == "good" and n["day"] in src]
        if len(hb) < 5 or len(hg) < 10:
            continue
        mb, mg = st.median(hb), st.median(hg)
        diff = (mb - mg) / mg * 100
        if diff <= -5:
            out.append({"level": "bad", "text": f"Po niespokojnej nocy {name} niższe o {abs(round(diff))}{unit}."})
        elif abs(diff) < 3 and key == "hrv":
            out.append({"level": "good", "text": "Niespokojne noce nie obniżają HRV rano – regeneracja na tym nie cierpi."})
    return out


def verdict(ns: list[dict]) -> dict:
    """Wniosek dla kafla: ostatnia noc + tydzien (pn-nd nie dotyczy -- 7 ostatnich nocy) vs norma."""
    rated = [n for n in ns if n.get("status")]
    if not rated:
        return {"status": None, "text": "Za mało nocy z odczytami, żeby ocenić."}
    last = rated[-1]
    wk = rated[-7:]
    base = [n["drop_min"] for n in rated[-37:-7]]
    out = {"last": last, "status": last["status"], "label": LABEL[last["status"]]}
    bad_wk = sum(1 for n in wk if n["status"] == "bad")
    if base:
        wk_avg = sum(n["drop_min"] for n in wk) / len(wk)
        b = st.median(base)
        out["trend"] = {"week_avg": round(wk_avg, 1), "norm": b, "bad_nights": bad_wk, "n": len(wk)}
        if bad_wk >= 3 or wk_avg > b * 1.6 + 3:
            out["trend_text"], out["trend_level"] = f"Ostatnie noce gorsze niż zwykle: {bad_wk} z {len(wk)} niespokojnych.", "bad"
        elif wk_avg < b * 0.7:
            out["trend_text"], out["trend_level"] = "Ostatnie noce spokojniejsze niż zwykle.", "good"
        else:
            out["trend_text"], out["trend_level"] = "Ostatnie noce w Twojej normie.", "good"
    if last.get("status") in ("warn", "bad") and last.get("bv_min") is not None:
        bvs = sorted(n["bv_min"] for n in rated[-61:-1] if n.get("bv_min") is not None)
        if bvs:
            hi = last["bv_min"] >= _q(bvs, .75)
            out["breath_text"] = ("Spadki SpO2 potwierdzone wahaniami oddechu (" + str(last["bv_min"]) + " min) — to prawdziwe zmiany oddechu, nie błąd pomiaru."
                                  if hi else "Wahania oddechu tej nocy w normie — spadki SpO2 bez potwierdzenia drugim czujnikiem.")
    prev60 = [n for n in rated[-61:-1]]
    bbs = sorted(n["bb_gain"] for n in prev60 if n.get("bb_gain") is not None)
    sts = sorted(n["stress"] for n in prev60 if n.get("stress") is not None)
    if len(bbs) >= NORM_MIN and len(sts) >= NORM_MIN and last.get("bb_gain") is not None and last.get("stress") is not None:
        if last["bb_gain"] <= _q(bbs, .25) and last["stress"] >= _q(sts, .75):
            out["bb_text"] = (f"Noc słabo naładowała Body Battery (+{last['bb_gain']}, zwykle ok. +{round(st.median(bbs))}) — "
                              f"wysoki stres w nocy ({last['stress']}, zwykle {round(st.median(sts))}): organizm nie odpoczywał w pełni.")
            out["bb_level"] = "warn"
    if last.get("resp_delta") is not None:
        d = last["resp_delta"]
        pl = lambda x: str(x).replace(".", ",")
        out["resp_text"] = (f"Tempo oddechu {pl(last['resp'])}/min — o {pl(d)} powyżej Twojej normy. Wczesny sygnał choroby — obserwuj." if d >= RESP_UP
                            else f"Tempo oddechu {pl(last['resp'])}/min — w Twojej normie ({pl(last['resp_norm'])}).")
        out["resp_level"] = "warn" if d >= RESP_UP else "good"
    return out


def summary(c, days: int = 120) -> dict:
    ns = nights(c, days)
    if not ns:
        return {"nights": [], "verdict": verdict([]), "factors": []}
    ctx = context(c, date.fromisoformat(ns[0]["day"]), date.fromisoformat(ns[-1]["day"]))
    for n in ns:
        n["alcohol"] = _prev(n["day"]) in ctx["alcohol"]
        n["tss_prev"] = round(ctx["tss"].get(_prev(n["day"]), 0))
        n["hrv"] = ctx["hrv"].get(n["day"])
        n["score"] = ctx["score"].get(n["day"])
    return {"nights": ns, "verdict": verdict(ns), "factors": factors(ns, ctx),
            "params": {"drop_pts": DROP_PTS, "norm_nights": NORM_NIGHTS, "hard_tss": HARD_TSS}}


MORNING_RHR_BPM = 3.0


def morning_signal(today: date) -> str | None:
    """Jedno zdanie do porannej wiadomosci albo None. Tylko gdy dzisiejsza noc jest juz w danych."""
    import qbot_food_plan as FP
    from fitmodel.body_signal import load_rows, _mean
    with FP._conn() as c:
        back = (datetime.now(TZ).date() - today).days + 10   # dziala tez dla dat wstecz (testy)
        ns = [n for n in nights(c, back) if n["day"] <= today.isoformat()]
        rows = load_rows(c.cursor(), today)
    if not ns or ns[-1]["day"] != today.isoformat():
        return None
    last3 = ns[-3:]
    n_bad = sum(1 for n in last3 if n.get("status") in ("warn", "bad"))
    rd = ns[-1].get("resp_delta")
    sp_ok, resp_ok = n_bad >= 2, rd is not None and rd >= RESP_UP
    if not (sp_ok or resp_ok):
        return None
    r_today = next((x[3] for x in rows if str(x[0])[:10] == today.isoformat()), None)
    base = [x[3] for x in rows if str(x[0])[:10] < today.isoformat()][-60:]
    rn = _mean(base)
    if r_today is None or rn is None or float(r_today) < rn + MORNING_RHR_BPM:
        return None
    pl = lambda x: f"{x:.1f}".replace(".", ",")
    hr = f"tętno spocz. {float(r_today):.0f} (norma {rn:.0f})"
    br = f"oddech {pl(ns[-1]['resp'])}/min (norma {pl(ns[-1]['resp_norm'])})" if resp_ok else ""
    if sp_ok and resp_ok:
        return (f"Oddech w nocy: {n_bad} z {len(last3)} ostatnich nocy ze spadkami SpO2 ponad normę, {br}, {hr} — "
                "trzy sygnały naraz, możliwy początek choroby. Rozważ lżejszy dzień.")
    if resp_ok:
        return f"Oddech w nocy: szybszy {br}, {hr} — możliwy początek choroby lub przemęczenie."
    return (f"Oddech w nocy: {n_bad} z {len(last3)} ostatnich nocy ze spadkami SpO2 ponad normę, "
            f"{hr} — możliwy początek choroby lub przemęczenie.")
