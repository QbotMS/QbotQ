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
            out.append(m)
    for i, m in enumerate(out):
        prev = [x["drop_min"] for x in out[max(0, i - NORM_NIGHTS):i]]
        if len(prev) >= NORM_MIN:
            p75, p90 = _q(prev, .75), _q(prev, .9)
            m["norm"], m["p75"], m["p90"] = st.median(prev), round(p75, 1), round(p90, 1)
            m["status"] = "good" if m["drop_min"] <= p75 else "warn" if m["drop_min"] <= p90 else "bad"
        else:
            m["norm"] = m["p75"] = m["p90"] = m["status"] = None
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
