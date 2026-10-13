"""Serce (2026-10-12) -- jedno zrodlo danych dla zakladki Forma > Serce i narzedzia Alberta heart_health.

Dane (tylko odczyt):
  * tetno spoczynkowe  -- qbot_v2.qbot_wellness_daily.resting_hr_bpm (Garmin)
  * tetno przy mocy    -- qbot_v2.hr_at_power (140-180 W, 15.-120. min jazdy)
  * cisnienie          -- qbot_v2.blood_pressure (Withings -> Garmin -> QBot)
  * EKG                -- qbot_v2.ecg_recording (zegarek Garmin)
Import: qbot3/connectors/import_garmin_heart.py. Dokumentacja: docs/SERCE.md.

Progi to orientacyjne sygnaly do obserwacji, NIE diagnoza (QBot nie jest lekarzem).
"""
from __future__ import annotations

import os
import statistics
import sys
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

# --- progi ----------------------------------------------------------------
RHR_WARN, RHR_BAD = 3.0, 5.0          # ud./min powyzej normy (srednia 28 dni vs mediana roku)
HRP_WARN, HRP_BAD = 5.0, 8.0          # ud./min przy 140-180 W powyzej normy
HRP_MIN_SEC = 300                     # jazda liczy sie, gdy >= 5 min w pasmie mocy
FRESH_DAYS = 90                       # starsze pomiary cisnienia / EKG = "brak aktualnych"

ECG_LABELS = {
    "SINUS_NORMAL": "rytm zatokowy (prawidłowy)",
    "SINUS_RHYTHM": "rytm zatokowy (prawidłowy)",
    "ATRIAL_FIBRILLATION": "migotanie przedsionków",
    "AFIB": "migotanie przedsionków",
    "HIGH_HEART_RATE": "za wysokie tętno (wynik niemożliwy do oceny)",
    "LOW_HEART_RATE": "za niskie tętno (wynik niemożliwy do oceny)",
    "INCONCLUSIVE": "niejednoznaczny",
    "INCONCLUSIVE_HIGH_HEART_RATE": "niejednoznaczny (wysokie tętno)",
    "INCONCLUSIVE_LOW_HEART_RATE": "niejednoznaczny (niskie tętno)",
    "POOR_RECORDING": "słaba jakość nagrania",
}
ECG_OK = {"SINUS_NORMAL", "SINUS_RHYTHM"}


def ecg_label(code: str | None) -> str:
    if not code:
        return "brak wyniku"
    return ECG_LABELS.get(code, f"wynik Garmina: {code}")


def bp_category(sys_: float, dia: float) -> tuple[str, str]:
    """Kategoria dla POMIARÓW DOMOWYCH (średnia z serii). Zwraca (status, opis)."""
    if sys_ >= 180 or dia >= 110:
        return "bad", "bardzo wysokie — skontaktuj się z lekarzem bez zwłoki"
    if sys_ >= 135 or dia >= 85:
        return "bad", "podwyższone (próg dla pomiarów domowych: 135/85)"
    if sys_ >= 130 or dia >= 80:
        return "warn", "wysokie prawidłowe"
    return "good", "prawidłowe"


def _pl(x: float) -> str:
    """Roznica ze znakiem, 1 miejsce po przecinku, polski przecinek."""
    return f"{x:+.1f}".replace(".", ",")


def fmt_d(d: date | datetime | str | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    return d.strftime("%d.%m.%Y")


def bp_series_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Ostatnia seria pomiarów: wszystko do 8 dni wstecz od ostatniego pomiaru.

    Pierwszy dzień serii odrzucany, gdy seria ma >= 3 dni (przyzwyczajenie do pomiaru).
    rows: [{'local': datetime, 'sys': int, 'dia': int, 'pulse': int|None}], dowolna kolejność.
    """
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["local"])
    last = rows[-1]["local"]
    series = [r for r in rows if r["local"] >= last - timedelta(days=8)]
    days = sorted({r["local"].date() for r in series})
    dropped = None
    used = series
    if len(days) >= 3:
        dropped = days[0]
        used = [r for r in series if r["local"].date() != days[0]]

    def avg(items, key):
        vals = [r[key] for r in items if r.get(key) is not None]
        return round(sum(vals) / len(vals)) if vals else None

    morning = [r for r in used if r["local"].hour < 12]
    evening = [r for r in used if r["local"].hour >= 12]
    s, d = avg(used, "sys"), avg(used, "dia")
    status, label = bp_category(s, d)
    return {
        "from": days[0].isoformat(), "to": days[-1].isoformat(), "days": len(days),
        "n": len(used), "dropped_first_day": dropped.isoformat() if dropped else None,
        "sys": s, "dia": d, "pulse": avg(used, "pulse"),
        "morning": {"n": len(morning), "sys": avg(morning, "sys"), "dia": avg(morning, "dia")},
        "evening": {"n": len(evening), "sys": avg(evening, "sys"), "dia": avg(evening, "dia")},
        "status": status, "label": label,
        "protocol_ok": len(days) >= 7 and len(morning) >= 6 and len(evening) >= 6,
    }


def trend_vs_norm(recent: list[float], norm: list[float], warn: float, bad: float) -> dict[str, Any]:
    if len(recent) < 2 or len(norm) < 10:
        return {"status": "info", "recent": None, "norm": None, "delta": None}
    r = sum(recent) / len(recent)
    n = statistics.median(norm)
    delta = r - n
    st = "bad" if delta >= bad else "warn" if delta >= warn else "good"
    return {"status": st, "recent": round(r, 1), "norm": round(n, 1), "delta": round(delta, 1)}


# --- dane -----------------------------------------------------------------

def _connect():
    from fitmodel.api import _db_connect
    return _db_connect()


def build_heart_data(days: int = 180, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=max(days, 365))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT date, coalesce(max(resting_hr_bpm) FILTER (WHERE source = 'garmin'), max(resting_hr_bpm)),
                      max(hrv_ms)
               FROM qbot_v2.qbot_wellness_daily WHERE date >= %s AND date <= %s
               GROUP BY date ORDER BY date""", (start, today))
        rhr = [{"date": d.isoformat(), "rhr": r, "hrv": round(h) if h is not None else None}
               for d, r, h in cur.fetchall() if r]
        cur.execute(
            """SELECT ride_date, hr_avg, power_avg, sec, external_id FROM qbot_v2.hr_at_power
               WHERE ride_date >= %s AND sec >= %s AND hr_avg IS NOT NULL ORDER BY ride_date""",
            (start, HRP_MIN_SEC))
        hrp = [{"date": d.isoformat(), "hr": round(h, 1), "w": round(w), "min": round(s / 60), "id": e}
               for d, h, w, s, e in cur.fetchall()]
        cur.execute(
            """SELECT measured_local, systolic, diastolic, pulse FROM qbot_v2.blood_pressure
               ORDER BY measured_local""")
        bp_rows = [{"local": l, "sys": s, "dia": d, "pulse": p} for l, s, d, p in cur.fetchall()]
        cur.execute(
            """SELECT started_local, classification, hr_avg, rmssd_hrv, symptoms, device, detail_id,
                      analysis - 'r_idx' - 'r_t' - 'rr_ms' AS an
               FROM qbot_v2.ecg_recording ORDER BY started_local""")
        ecg = [{"local": l.isoformat(timespec="minutes") if l else None, "code": c, "label": ecg_label(c),
                "hr": h, "hrv": round(v) if v is not None else None, "symptoms": sy or [], "device": dv,
                "ok": c in ECG_OK, "id": did, "an": _ecg_an(an)} for l, c, h, v, sy, dv, did, an in cur.fetchall()]
    finally:
        conn.close()

    d28, d365 = today - timedelta(days=28), today - timedelta(days=365)
    rhr_recent = [x["rhr"] for x in rhr if x["date"] > d28.isoformat()]
    rhr_norm = [x["rhr"] for x in rhr if d365.isoformat() <= x["date"] <= d28.isoformat()]
    hrp_recent = [x["hr"] for x in hrp if x["date"] > d28.isoformat()]
    hrp_norm = [x["hr"] for x in hrp if d365.isoformat() <= x["date"] <= d28.isoformat()]
    t_rhr = trend_vs_norm(rhr_recent, rhr_norm, RHR_WARN, RHR_BAD)
    t_hrp = trend_vs_norm(hrp_recent, hrp_norm, HRP_WARN, HRP_BAD)
    t_rhr["last"] = rhr[-1] if rhr else None
    t_rhr["last7"] = round(sum(rhr_recent[-7:]) / len(rhr_recent[-7:]), 1) if rhr_recent else None
    t_hrp["rides"] = len(hrp_recent)

    bp = bp_series_summary(bp_rows)
    if bp:
        bp["fresh"] = (today - date.fromisoformat(bp["to"])).days <= FRESH_DAYS
    last_ecg = ecg[-1] if ecg else None
    ecg_fresh = bool(last_ecg and last_ecg["local"]
                     and (today - date.fromisoformat(last_ecg["local"][:10])).days <= FRESH_DAYS)

    cut = (today - timedelta(days=days)).isoformat()
    data = {
        "today": today.isoformat(), "days": days,
        "rhr": {"series": [x for x in rhr if x["date"] >= cut], **t_rhr},
        "hrp": {"series": [x for x in hrp if x["date"] >= cut], "band": "140–180 W", **t_hrp},
        "bp": {"summary": bp, "all": [{"local": r["local"].isoformat(timespec="minutes"), "sys": r["sys"],
                                       "dia": r["dia"], "pulse": r["pulse"]} for r in bp_rows]},
        "ecg": {"list": ecg, "last": last_ecg, "fresh": ecg_fresh},
    }
    data["points"] = verdict_points(data)
    data["analysis"] = analysis_text(data)
    return data


def _ecg_an(an: dict | None) -> dict | None:
    """Skrot analizy uderzen (qbot_ecg) do listy / Alberta."""
    if not an or not an.get("ok"):
        return None
    return {k: an.get(k) for k in ("n_beats", "hr_mean", "hr_min", "hr_max", "rmssd", "sdnn", "pnn50",
                                   "n_irregular", "n_shape", "quality")} | {
        "irregular": [{"t_s": i["t_s"], "label": i["label"]} for i in an.get("irregular") or [] if i.get("kind") != "ksztalt"]}


def verdict_points(d: dict[str, Any]) -> list[dict[str, str]]:
    pts: list[dict[str, str]] = []
    r = d["rhr"]
    if r.get("recent") is not None:
        pts.append({"status": r["status"], "text":
                    f"Tętno spoczynkowe: średnio {r['recent']:.0f} z ostatnich 28 dni, Twoja norma z roku "
                    f"{r['norm']:.0f} ({_pl(r['delta'])} ud./min)."})
    h = d["hrp"]
    if h.get("recent") is not None:
        pts.append({"status": h["status"], "text":
                    f"Tętno przy {h['band']}: {h['recent']:.0f} z {h['rides']} jazd w 28 dni, norma "
                    f"{h['norm']:.0f} ({_pl(h['delta'])}). Rośnie też po spadku formy i w chłodzie."})
    bp = d["bp"]["summary"]
    if not bp:
        pts.append({"status": "info", "text": "Ciśnienie: brak pomiarów. Zrób 7-dniową serię (instrukcja niżej)."})
    elif not bp["fresh"]:
        pts.append({"status": "info", "text":
                    f"Ciśnienie: ostatnie pomiary z {fmt_d(bp['to'])} ({bp['sys']}/{bp['dia']}, {bp['label']}) "
                    f"— za stare, zrób nową 7-dniową serię."})
    else:
        extra = "" if bp["protocol_ok"] else " Seria niepełna — do oceny potrzeba 7 dni rano i wieczorem."
        pts.append({"status": bp["status"], "text":
                    f"Ciśnienie (seria {fmt_d(bp['from'])}–{fmt_d(bp['to'])}): średnio {bp['sys']}/{bp['dia']}, "
                    f"{bp['label']}.{extra}"})
    e = d["ecg"]
    if not e["last"]:
        pts.append({"status": "info", "text": "EKG: brak nagrań."})
    else:
        st = "good" if e["last"]["ok"] else "bad"
        if not e["fresh"]:
            st = "info" if e["last"]["ok"] else "bad"
        an = e["last"].get("an") or {}
        extra = ""
        if an.get("n_irregular"):
            extra = f"; nieregularne uderzenia: {an['n_irregular']} ({', '.join(i['label'] for i in an['irregular'][:3])})"
            st = "warn" if st == "good" else st
        if an.get("rmssd") is not None:
            extra += f"; HRV z uderzeń {an['rmssd']:.0f} ms"
        pts.append({"status": st, "text":
                    f"EKG {fmt_d(e['last']['local'][:10])}: {e['last']['label']}, średnio {e['last']['hr']} ud./min{extra}"
                    + ("" if e["fresh"] else " — nagranie stare, zrób nowe.")})
    return pts


def analysis_text(d: dict[str, Any]) -> str:
    lines = ["Serce — stan z danych QBota (to sygnały do obserwacji, nie diagnoza):"]
    icon = {"good": "✓", "warn": "!", "bad": "‼", "info": "·"}
    for p in d["points"]:
        lines.append(f"{icon.get(p['status'], '·')} {p['text']}")
    if any(p["status"] == "bad" for p in d["points"]):
        lines.append("Coś odbiega od normy — warto skonsultować z lekarzem (najlepiej z wynikami serii ciśnienia i EKG).")
    lines.append("Szczegóły i wykresy: Forma → Serce.")
    return "\n".join(lines)


def ecg_record(detail_id: str) -> dict | None:
    """Pelne nagranie EKG (przebieg + analiza) dla wykresu i PDF."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT detail_id, started_local, classification, hr_avg, rmssd_hrv, device, lead, sample_rate,
                              samples, analysis FROM qbot_v2.ecg_recording WHERE detail_id=%s""", (detail_id,))
        r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        return None
    keys = ["detail_id", "started_local", "classification", "hr_avg", "rmssd_hrv", "device", "lead", "sample_rate", "samples", "analysis"]
    d = dict(zip(keys, r))
    d["label"] = ecg_label(d["classification"])
    try:
        import qbot_ecg as Q
        d["interpretation"] = Q.interpret(d, _ecg_ctx(d))
    except Exception as exc:
        d["interpretation"] = [{"status": "info", "text": f"Interpretacja niedostępna ({type(exc).__name__})."}]
    return d


def _ecg_ctx(d: dict) -> dict:
    """Inne nagrania (HRV z uderzen) i cisnienie +-45 min od nagrania."""
    from datetime import timedelta as _td
    when = d.get("started_local")
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT started_local, (analysis->>'rmssd')::float FROM qbot_v2.ecg_recording
                       WHERE detail_id <> %s AND analysis->>'ok' = 'true'""", (d["detail_id"],))
        others = [{"local": l, "rmssd": v} for l, v in cur.fetchall() if l]
        bp = []
        if when:
            cur.execute("""SELECT measured_local, systolic, diastolic FROM qbot_v2.blood_pressure
                           WHERE measured_local BETWEEN %s AND %s""", (when - _td(minutes=45), when + _td(minutes=45)))
            bp = [{"local": l, "sys": s, "dia": di} for l, s, di in cur.fetchall()]
    finally:
        conn.close()
    return {"others": others, "bp": bp}
