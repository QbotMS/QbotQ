from __future__ import annotations

"""FITMODEL T1 -- warstwa zarzadzania: tryb x budzet czasu x focus -> fitmodel_week_plan.

Spec sek. 6. Kotwica planu = BUDZET CZASU (sek. 6.2), nie strain (i^4 za bardzo
skacze). Tryb skaluje cel i przeksztalca dystrybucje. Tryb jest PROPOZYCJA do
recznego zatwierdzenia (sek. 6.1, "nie auto-apply"). Bez HRV (zapis RR jeszcze
nieaktywny) rekomendacja trybu degraduje sie do sygnalu obciazenia.

Skladowe:
  budzet_h    = 4-tyg srednia krocząca realnego czasu w siodle (training_sessions)
                + opcjonalna korekta (--budget-h, np. z pogody/kalendarza/NL).
  baseline    = 4-tyg srednie tygodniowe: total_strain + proporcje low/high/peak
                (z fitmodel_ride_buckets).
  tryb        -> mnoznik totalu: regeneracja 0.65 / podtrzymanie 1.0 / rozwoj 1.075
                + reshape (regeneracja zeruje High/Peak, caly target do Low).
  bramka      = wymagane godziny (target_total / strain_na_h z okna) <= budzet_h?
                jak nie -> feasible=false + komunikat z alternatywa.

focus_source = 'deficit' (placeholder; route/deficit dolozy T2).
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect, _coerce_date
from fitmodel.focus import compute_focus

MODE_TOTAL_FACTOR = {"regeneracja": 0.65, "podtrzymanie": 1.0, "rozwoj": 1.075}
WINDOW_DAYS = 28

DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.fitmodel_week_plan (
    week          date PRIMARY KEY,
    mode          text,
    time_budget_h numeric,
    focus_source  text,
    target_low    numeric,
    target_high   numeric,
    target_peak   numeric,
    feasible      boolean,
    note          text,
    created_at    timestamptz DEFAULT now()
)
"""


def ensure_table(db_conn) -> None:
    with db_conn.cursor() as cur:
        cur.execute(DDL)
    db_conn.commit()


def _week_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _rolling_inputs(db_conn, as_of: date) -> dict[str, float]:
    """4-tyg srednie tygodniowe: godziny w siodle, total strain, proporcje, strain/h."""
    start = as_of - timedelta(days=WINDOW_DAYS)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(duration_s),0)/3600.0 FROM qbot_v2.training_sessions "
            "WHERE sport_type=%s AND date > %s AND date <= %s",
            ("cycling", start, as_of),
        )
        hours_total = float(cur.fetchone()[0] or 0.0)
        cur.execute(
            "SELECT COALESCE(SUM(total_strain),0), COALESCE(SUM(low_strain),0), "
            "COALESCE(SUM(high_strain),0), COALESCE(SUM(peak_strain),0) "
            "FROM qbot_v2.fitmodel_ride_buckets "
            "WHERE started_at::date > %s AND started_at::date <= %s",
            (start, as_of),
        )
        tot, low, high, peak = (float(x) for x in cur.fetchone())

    weeks = WINDOW_DAYS / 7.0
    strain_per_h = (tot / hours_total) if hours_total > 0 else 0.0
    sum_lhp = (low + high + peak) or 1.0
    return {
        "weekly_hours": round(hours_total / weeks, 2),
        "weekly_total_strain": round(tot / weeks, 1),
        "strain_per_h": round(strain_per_h, 1),
        "prop_low": low / sum_lhp,
        "prop_high": high / sum_lhp,
        "prop_peak": peak / sum_lhp,
        "window_hours": round(hours_total, 1),
        "window_total_strain": round(tot, 1),
    }


def recommend_mode(db_conn, as_of: date, inp: dict[str, float]) -> tuple[str, str]:
    """Propozycja trybu. Z HRV gdy jest; inaczej z trendu obciazenia (degradacja)."""
    # HRV (jesli kiedys ruszy zapis RR): swiezosc nocnego HRV vs baseline 30d
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT hrv_night FROM qbot_v2.fitmodel_daily "
            "WHERE hrv_night IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1",
            (as_of,),
        )
        hrv_row = cur.fetchone()
        # obciazenie POPRZEDNIEGO pelnego tygodnia (propozycja w pn) vs srednia z okna
        wk_start = _week_monday(as_of)
        cur.execute(
            "SELECT COALESCE(SUM(total_strain),0) FROM qbot_v2.fitmodel_ride_buckets "
            "WHERE started_at::date >= %s AND started_at::date < %s",
            (wk_start - timedelta(days=7), wk_start),
        )
        prev_week = float(cur.fetchone()[0] or 0.0)

    avg_week = inp["weekly_total_strain"] or 1.0
    ratio = prev_week / avg_week
    if hrv_row is None:
        basis = "bez HRV (zapis RR nieaktywny) -> z trendu obciazenia"
    else:
        basis = "HRV dostepne"
    if ratio >= 1.4:
        return "regeneracja", f"ostatni tydzien {ratio:.0%} sredniej -> przeciazenie; {basis}"
    if ratio <= 0.6:
        return "rozwoj", f"ostatni tydzien {ratio:.0%} sredniej -> zapas; {basis}"
    return "podtrzymanie", f"ostatni tydzien {ratio:.0%} sredniej -> stabilnie; {basis}"


def build_plan(db_conn, as_of: date | None = None, mode: str | None = None,
               budget_h: float | None = None, route_artifact_id: int | None = None,
               days_to_event: int | None = None) -> dict[str, Any]:
    as_of = _coerce_date(as_of)
    week = _week_monday(as_of)
    inp = _rolling_inputs(db_conn, as_of)
    focus = compute_focus(db_conn, as_of, route_artifact_id, days_to_event)
    fw = focus["weights"]

    mode_basis = "tryb wymuszony recznie"
    if mode is None:
        mode, mode_basis = recommend_mode(db_conn, as_of, inp)
    mode = mode.lower()
    if mode not in MODE_TOTAL_FACTOR:
        raise ValueError(f"nieznany tryb: {mode}")

    # Budzet czasu: auto = 4-tyg srednia; override = korekta (pogoda/kalendarz/NL)
    auto_budget = inp["weekly_hours"]
    budget = budget_h if budget_h is not None else auto_budget

    factor = MODE_TOTAL_FACTOR[mode]
    target_total = inp["weekly_total_strain"] * factor

    # Dystrybucja wg FOCUS (T2); regeneracja -> wszystko do Low (zeruje High/Peak)
    if mode == "regeneracja":
        t_low, t_high, t_peak = target_total, 0.0, 0.0
    else:
        t_low = target_total * fw["low"]
        t_high = target_total * fw["high"]
        t_peak = target_total * fw["peak"]

    # Bramka wykonalnosci: ile godzin trzeba na target_total wg strain/h z okna
    sph = inp["strain_per_h"]
    required_h = (target_total / sph) if sph > 0 else 0.0
    feasible = (budget <= 0) or (required_h <= budget * 1.05)  # 5% tolerancji

    note_bits = [f"tryb: {mode_basis}",
                 f"focus[{focus['source']}]: {focus['note']}",
                 f"budzet auto={auto_budget}h" + (f", korekta={budget}h" if budget_h is not None else ""),
                 f"wymagane~={required_h:.1f}h @ {sph} strain/h"]
    if not feasible:
        note_bits.append(
            f"NIEWYKONALNE: {required_h:.1f}h > budzet {budget}h. "
            f"Wybierz: rozwoj JEDNEGO systemu albo podtrzymanie wszystkich w {budget}h."
        )
    note = " | ".join(note_bits)

    return {
        "week": week, "mode": mode, "time_budget_h": round(budget, 1),
        "focus_source": focus["source"],
        "target_low": round(t_low, 1), "target_high": round(t_high, 1),
        "target_peak": round(t_peak, 1),
        "feasible": feasible, "note": note,
        "_inp": inp, "_required_h": round(required_h, 1), "_focus": focus,
    }


def upsert_plan(db_conn, plan: dict[str, Any]) -> None:
    ensure_table(db_conn)
    cols = ("week", "mode", "time_budget_h", "focus_source",
            "target_low", "target_high", "target_peak", "feasible", "note")
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_week_plan
                (week, mode, time_budget_h, focus_source, target_low, target_high,
                 target_peak, feasible, note)
            VALUES (%(week)s,%(mode)s,%(time_budget_h)s,%(focus_source)s,%(target_low)s,
                    %(target_high)s,%(target_peak)s,%(feasible)s,%(note)s)
            ON CONFLICT (week) DO UPDATE SET
                mode=EXCLUDED.mode, time_budget_h=EXCLUDED.time_budget_h,
                focus_source=EXCLUDED.focus_source, target_low=EXCLUDED.target_low,
                target_high=EXCLUDED.target_high, target_peak=EXCLUDED.target_peak,
                feasible=EXCLUDED.feasible, note=EXCLUDED.note
            """,
            {k: plan[k] for k in cols},
        )
    db_conn.commit()


def _print_plan(p: dict[str, Any]) -> None:
    print(f"  tydzien      : {p['week']}")
    print(f"  tryb (PROPOZYCJA, do zatwierdzenia): {p['mode']}")
    print(f"  budzet czasu : {p['time_budget_h']} h   (wymagane ~{p['_required_h']} h)")
    print(f"  targety strain: low={p['target_low']}  high={p['target_high']}  peak={p['target_peak']}")
    print(f"  focus_source : {p['focus_source']}")
    print(f"  feasible     : {p['feasible']}")
    print(f"  note         : {p['note']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FITMODEL T1 -- plan tygodnia")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--mode", default=None, help="regeneracja|podtrzymanie|rozwoj (wymusza)")
    ap.add_argument("--budget-h", type=float, default=None, help="korekta budzetu godzin")
    ap.add_argument("--route-id", type=int, default=None, help="route_artifact_id -> focus Stan A")
    ap.add_argument("--days-to-event", type=int, default=None, help="dni do daty eventu (dryf)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--demo-infeasible", action="store_true",
                    help="pokaz przyklad niewykonalny (rozwoj przy malym budzecie)")
    args = ap.parse_args()

    conn = _db_connect()
    try:
        plan = build_plan(conn, as_of=args.as_of, mode=args.mode, budget_h=args.budget_h,
                          route_artifact_id=args.route_id, days_to_event=args.days_to_event)
        if not args.dry_run:
            upsert_plan(conn, plan)
        print("PLAN" + (" (DRY-RUN)" if args.dry_run else " (zapisany)") + ":")
        _print_plan(plan)
        print("  dane okna   :", plan["_inp"])

        if args.demo_infeasible:
            demo = build_plan(conn, as_of=args.as_of, mode="rozwoj", budget_h=1.0)
            print("\nPRZYKLAD NIEWYKONALNY (rozwoj, budzet 1h):")
            _print_plan(demo)
    finally:
        conn.close()
