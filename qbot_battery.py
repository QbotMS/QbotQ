"""Bateria dnia (2026-10-20, sesja spo2-2010): Body Battery i stres co 3 min z Garmina + drzemki -> jak noc naladowala,
ile i czym dzien rozladowal, wieczor przed snem.

Zrodla: qbot_v2.garmin_daily_raw kind='stress' (get_stress_data, import_garmin_heart.import_stress, od 01.06.2026),
kind='sleep' (dailySleepDTO.dailyNapDTOS -- drzemki), qbot_sleep_daily (pora snu i pobudki), training_sessions (TSS),
energy_daily (kroki). Dzien d = od pobudki dnia d do zasniecia w noc d->d+1 (sleep_start wiersza d+1).

Wnioski z danych 06-10.2026 (141 dni, docs/BATERIA.md):
  * dzien zuzywa ~70 pkt (rano ~83 -> do lozka ~10); noc laduje ~72;
  * rozladowanie wiaze sie z krokami (0,33), NIE z TSS ani minutami stresu;
  * 2 h przed snem: spokojny wieczor (stres <= p25) -> noc +73, sen 86, HRV 82; nerwowy (>= p75) -> +64, 79, 77;
  * do lozka z BB <= p25 -> rano ~67, z BB >= p75 -> rano ~95.
Progi licza sie na biezaco z 60 poprzednich dni (wlasna norma), teksty pokazuja liczby z Twoich danych.
"""
from __future__ import annotations

import statistics as st
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
PRE_H = 2
NORM_DAYS = 60
NORM_MIN = 20
HI_STRESS = 51


def _loc(ms) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).astimezone(TZ)


def _q(v: list[float], p: float) -> float:
    s = sorted(v); k = (len(s) - 1) * p; lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _gmt(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s)[:19]).replace(tzinfo=timezone.utc).astimezone(TZ)
    except ValueError:
        return None


def _curves(p: dict):
    s = [(_loc(t), v) for t, v in (p.get("stressValuesArray") or []) if t is not None and v is not None]
    b = [(_loc(x[0]), x[2]) for x in (p.get("bodyBatteryValuesArray") or []) if len(x) > 2 and x[2] is not None]
    return s, b


def _naps(sleep_payload: dict | None) -> list[dict]:
    out = []
    for n in ((sleep_payload or {}).get("dailySleepDTO") or {}).get("dailyNapDTOS") or []:
        a, e = _gmt(n.get("napStartTimestampGMT")), _gmt(n.get("napEndTimestampGMT"))
        if a and e:
            out.append({"start": a, "end": e, "min": round((e - a).total_seconds() / 60)})
    return out


def _load(c, since: date):
    raw = {r["date"]: r["payload"] for r in c.execute(
        "SELECT date, payload FROM qbot_v2.garmin_daily_raw WHERE kind='stress' AND date >= %s", (since,)).fetchall()}
    slr = {r["date"]: r["payload"] for r in c.execute(
        "SELECT date, payload FROM qbot_v2.garmin_daily_raw WHERE kind='sleep' AND date >= %s AND (payload->'dailySleepDTO'->>'napTimeSeconds') NOT IN ('0')",
        (since,)).fetchall()}
    slp = {r["date"]: r for r in c.execute(
        "SELECT date, min(sleep_start) ss, max(sleep_end) se, max(sleep_score) sc, avg(hrv_ms) h FROM qbot_v2.qbot_sleep_daily "
        "WHERE date >= %s GROUP BY date", (since,)).fetchall()}
    tss = {r["date"]: float(r["t"] or 0) for r in c.execute(
        "SELECT date, sum(tss) t FROM qbot_v2.training_sessions WHERE date >= %s GROUP BY date", (since,)).fetchall()}
    steps = {r["date"]: r["steps"] for r in c.execute("SELECT date, steps FROM qbot_v2.energy_daily WHERE date >= %s", (since,)).fetchall()}
    return raw, slr, slp, tss, steps


def _day(d, raw, slr, slp, tss, steps, now) -> dict | None:
    if d not in raw:
        return None
    s, b = _curves(raw[d])
    if len(b) < 30:
        return None
    if (d + timedelta(days=1)) in raw:   # zasniecie po polnocy: koncowka dnia lezy w pliku nastepnego dnia
        s2, b2 = _curves(raw[d + timedelta(days=1)])
        s, b = s + [x for x in s2 if x[0].hour < 6], b + [x for x in b2 if x[0].hour < 6]
    wake = slp.get(d, {}).get("se")
    wake = wake.astimezone(TZ) if wake else None
    nb = slp.get(d + timedelta(days=1), {}).get("ss")
    bed = nb.astimezone(TZ) if nb else None
    end = bed or now
    rec = {"day": d.isoformat(), "wake": wake.strftime("%H:%M") if wake else None, "bed": bed.strftime("%H:%M") if bed else None,
           "complete": bed is not None, "tss": round(tss.get(d, 0)), "steps": steps.get(d)}
    if wake:
        w = [v for t, v in b if wake - timedelta(minutes=30) <= t <= wake + timedelta(minutes=60)]
        rec["bb_wake"] = max(w) if w else None
    else:
        rec["bb_wake"] = None
    tail = [(t, v) for t, v in b if t <= end]
    rec["bb_now"] = tail[-1][1] if tail else None
    rec["bb_now_at"] = tail[-1][0].strftime("%H:%M") if tail else None
    if bed:
        bb = [v for t, v in b if bed - timedelta(minutes=20) <= t <= bed]
        rec["bb_bed"] = bb[-1] if bb else None
        pre = [v for t, v in s if bed - timedelta(hours=PRE_H) <= t < bed and v >= 0]
        rec["pre"] = round(st.mean(pre)) if pre else None
    else:
        rec["bb_bed"] = rec["pre"] = None
    if wake:
        ds = [v for t, v in s if wake <= t < end]
        val = [v for v in ds if v >= 0]
        rec["stress"] = round(st.mean(val)) if val else None
        rec["hi_min"] = sum(1 for v in val if v >= HI_STRESS) * 3
        rec["act_min"] = sum(1 for v in ds if v == -2) * 3
    else:
        rec["stress"] = rec["hi_min"] = rec["act_min"] = None
    top = rec["bb_wake"]; low = rec["bb_bed"] if bed else rec["bb_now"]
    rec["drain"] = (top - low) if top is not None and low is not None else None
    naps = _naps(slr.get(d))
    for n in naps:
        bef = [v for t, v in b if n["start"] - timedelta(minutes=10) <= t <= n["start"]]
        aft = [v for t, v in b if n["end"] <= t <= n["end"] + timedelta(minutes=15)]
        n["bb_gain"] = (aft[0] - bef[-1]) if bef and aft else None
    rec["naps"] = [{"start": n["start"].strftime("%H:%M"), "end": n["end"].strftime("%H:%M"), "min": n["min"], "bb_gain": n["bb_gain"]} for n in naps]
    rec["nap_min"] = sum(n["min"] for n in naps)
    nx = slp.get(d + timedelta(days=1), {})
    rec["n_score"], rec["n_hrv"] = nx.get("sc"), (round(float(nx["h"])) if nx.get("h") else None)
    return rec


def days(c, n: int = 120) -> list[dict]:
    today = datetime.now(TZ).date()
    since = today - timedelta(days=n + NORM_DAYS + 2)
    data = _load(c, since)
    now = datetime.now(TZ)
    out = []
    d = since
    while d <= today:
        r = _day(d, *data, now)
        if r:
            out.append(r)
        d += timedelta(days=1)
    by = {r["day"]: r for r in out}
    for r in out:   # noc po dniu d laduje: BB rano d+1 - BB do lozka d
        nx = by.get((date.fromisoformat(r["day"]) + timedelta(days=1)).isoformat())
        r["charge"] = (nx["bb_wake"] - r["bb_bed"]) if nx and nx.get("bb_wake") is not None and r.get("bb_bed") is not None else None
    cut = (today - timedelta(days=n)).isoformat()
    return [r for r in out if r["day"] >= cut], out


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 1) if xs else None


def insights(hist: list[dict]) -> dict:
    """Wnioski z calej historii (liczby z Twoich danych) + progi p25/p75 do ocen."""
    full = [r for r in hist if r["complete"]]
    pre = [r["pre"] for r in full if r.get("pre") is not None]
    bed = [r["bb_bed"] for r in full if r.get("bb_bed") is not None]
    if len(pre) < NORM_MIN or len(bed) < NORM_MIN:
        return {}
    plo, phi, blo, bhi = _q(pre, .25), _q(pre, .75), _q(bed, .25), _q(bed, .75)
    byd = {r["day"]: r for r in hist}
    def nxt(r, k):
        n = byd.get((date.fromisoformat(r["day"]) + timedelta(days=1)).isoformat())
        return n.get(k) if n else None
    calm = [r for r in full if r.get("pre") is not None and r["pre"] <= plo]
    nerv = [r for r in full if r.get("pre") is not None and r["pre"] >= phi]
    low = [r for r in full if r.get("bb_bed") is not None and r["bb_bed"] <= blo]
    high = [r for r in full if r.get("bb_bed") is not None and r["bb_bed"] >= bhi]
    return {"pre_lo": round(plo), "pre_hi": round(phi), "bed_lo": round(blo), "bed_hi": round(bhi),
            "calm": {"charge": _med([r["charge"] for r in calm]), "score": _med([r["n_score"] for r in calm]), "hrv": _med([r["n_hrv"] for r in calm]), "n": len(calm)},
            "nerv": {"charge": _med([r["charge"] for r in nerv]), "score": _med([r["n_score"] for r in nerv]), "hrv": _med([r["n_hrv"] for r in nerv]), "n": len(nerv)},
            "low_bed": {"morning": _med([nxt(r, "bb_wake") for r in low]), "score": _med([r["n_score"] for r in low])},
            "high_bed": {"morning": _med([nxt(r, "bb_wake") for r in high]), "score": _med([r["n_score"] for r in high])},
            "drain_med": _med([r["drain"] for r in full]), "charge_med": _med([r["charge"] for r in full]),
            "wake_med": _med([r["bb_wake"] for r in full]), "bed_med": _med(bed), "steps_med": _med([r["steps"] for r in full]),
            "naps": sum(len(r["naps"]) for r in hist)}


def verdict(sel: list[dict], ins: dict) -> dict:
    if not sel or not ins:
        return {"text": "Za mało danych krzywej Body Battery."}
    last_full = next((r for r in reversed(sel) if r["complete"]), None)
    today = sel[-1]
    out = {"today": today, "last_full": last_full, "facts": []}
    F = out["facts"]
    if last_full:
        e = last_full
        if e.get("pre") is not None:
            if e["pre"] >= ins["pre_hi"]:
                F.append({"l": "warn", "t": f"Wieczór {e['day'][8:10]}.{e['day'][5:7]} nerwowy: stres przed snem {e['pre']} (spokojnie ≤ {ins['pre_lo']}). "
                                           f"Po takich wieczorach noc ładuje ok. {ins['nerv']['charge']:.0f} zamiast {ins['calm']['charge']:.0f}, sen {ins['nerv']['score']:.0f} zamiast {ins['calm']['score']:.0f}."})
            elif e["pre"] <= ins["pre_lo"]:
                F.append({"l": "good", "t": f"Wieczór {e['day'][8:10]}.{e['day'][5:7]} spokojny (stres przed snem {e['pre']}) — to najlepszy prognostyk dobrej nocy."})
        if e.get("bb_bed") is not None and e["bb_bed"] <= ins["bed_lo"]:
            F.append({"l": "warn", "t": f"Do łóżka z baterią {e['bb_bed']} — przy ≤ {ins['bed_lo']} rano masz zwykle ok. {ins['low_bed']['morning']:.0f}, a przy ≥ {ins['bed_hi']} ok. {ins['high_bed']['morning']:.0f}."})
    if today.get("nap_min"):
        g = [n["bb_gain"] for n in today["naps"] if n.get("bb_gain") is not None]
        F.append({"l": "good", "t": f"Drzemka dziś: {today['nap_min']} min" + (f", bateria {'+' if sum(g) >= 0 else ''}{sum(g)}" if g else "") + " — wliczona do snu doby."})
    out["rules"] = [
        f"Dzień zużywa typowo {ins['drain_med']:.0f} pkt (rano ~{ins['wake_med']:.0f} → do łóżka ~{ins['bed_med']:.0f}), noc ładuje ~{ins['charge_med']:.0f}.",
        f"Spokojne 2 h przed snem (stres ≤ {ins['pre_lo']}): noc +{ins['calm']['charge']:.0f}, sen {ins['calm']['score']:.0f}, HRV {ins['calm']['hrv']:.0f}; "
        f"nerwowe (≥ {ins['pre_hi']}): +{ins['nerv']['charge']:.0f}, {ins['nerv']['score']:.0f}, {ins['nerv']['hrv']:.0f}.",
        "Baterię w ciągu dnia rozładowują głównie kroki (chodzenie) — trening i minuty stresu mniej, niż się wydaje.",
    ]
    return out


def summary(c, n: int = 120) -> dict:
    sel, hist = days(c, n)
    ins = insights([r for r in hist if r["day"] < (datetime.now(TZ).date() - timedelta(days=0)).isoformat()][-NORM_DAYS * 3:])
    return {"days": sel, "insights": ins, "verdict": verdict(sel, ins)}


def day_curve(c, d: date) -> dict | None:
    raw, slr, slp, tss, steps = _load(c, d - timedelta(days=1))
    if d not in raw:
        return None
    s, b = _curves(raw[d])
    ses = c.execute("SELECT started_at, duration_s, sport_type FROM qbot_v2.training_sessions WHERE date=%s AND started_at IS NOT NULL", (d,)).fetchall()
    rec = _day(d, raw, slr, slp, tss, steps, datetime.now(TZ)) or {}
    return {"day": d.isoformat(), "stress": [[t.strftime("%H:%M"), v] for t, v in s], "bb": [[t.strftime("%H:%M"), v] for t, v in b],
            "rides": [{"start": r["started_at"].astimezone(TZ).strftime("%H:%M"),
                       "end": (r["started_at"] + timedelta(seconds=int(r["duration_s"] or 0))).astimezone(TZ).strftime("%H:%M"),
                       "name": r["sport_type"]} for r in ses],
            "rec": rec}


def evening_hint(today: date) -> str | None:
    """Do wieczornej linii snu: drzemka dzis (wliczona do snu doby). Bez nowych wiadomosci."""
    try:
        import qbot_food_plan as FP
        with FP._conn() as c:
            r = c.execute("SELECT payload FROM qbot_v2.garmin_daily_raw WHERE kind='sleep' AND date=%s", (today,)).fetchone()
        naps = _naps(r["payload"] if r else None)
        m = sum(n["min"] for n in naps)
        return f"dziś drzemka {m} min" if m else None
    except Exception:
        return None
