from __future__ import annotations

"""FITMODEL E9 -- modularne sekcje do briefu (dobowy + tygodniowy).

Spec E9. Sekcje sa MODULARNE (raport tygodniowy wciaz w szlifowaniu):
  daily_section()  -> FTP_est, W/kg, glikogen, sugestia fuelingu
  weekly_section() -> rozklad wiader vs target + tryb tygodnia
Kazda zwraca string (markdown telegramowy) albo "" gdy brak danych -> wpiecie
do raportu jest fail-safe. Wlasne polaczenie DB bez root-only env (jak fitmodel.api).
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2


def _db_connect():
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _week_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _fuel_hint(glyco: float | None, peak_share: float) -> str:
    if glyco is None:
        return "fueling: brak danych glikogenu"
    if glyco < 40:
        base = "nisko (<40%) -> przed jazda solidne sniadanie 1.5-2 g CHO/kg"
    elif glyco < 65:
        base = "srednio -> lekkie sniadanie + tankuj w trasie"
    else:
        base = "pelny zbiornik -> standardowo"
    inten = "60-90 g CHO/h (intensywnie)" if peak_share >= 0.35 else "40-60 g CHO/h"
    return f"fueling: {base}; na jezdzie {inten}"


def daily_section(db_conn=None) -> str:
    own = db_conn is None
    conn = db_conn or _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ftp_est_w, w_per_kg, weight_kg FROM qbot_v2.fitmodel_daily "
                "WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                return ""
            ftp, wkg, wt = row
            ftp = float(ftp) if ftp is not None else None
            wkg = float(wkg) if wkg is not None else (
                round(ftp / float(wt), 2) if (ftp and wt) else None)
            cur.execute(
                "SELECT glycogen_pct FROM qbot_v2.fitmodel_daily "
                "WHERE glycogen_pct IS NOT NULL ORDER BY day DESC LIMIT 1"
            )
            g = cur.fetchone()
            glyco = float(g[0]) if g and g[0] is not None else None
            # udzial peak z biezacego tygodnia (do podpowiedzi fuelingu)
            week = _week_monday(date.today())
            cur.execute(
                "SELECT COALESCE(SUM(peak_strain),0), COALESCE(SUM(total_strain),0) "
                "FROM qbot_v2.fitmodel_ride_buckets WHERE started_at::date >= %s",
                (week,),
            )
            pk, tot = (float(x) for x in cur.fetchone())
        peak_share = (pk / tot) if tot > 0 else 0.0

        if ftp is None:
            return ""
        wkg_txt = f", {round(wkg, 2)} W/kg" if wkg else ""
        wt_txt = f", {round(float(wt))} kg" if wt else ""
        lines = ["\U0001f6b4 *FITMODEL — forma*",
                 f"- FTP_est (wlasne, submax): {round(ftp)} W{wkg_txt}{wt_txt}"]
        if glyco is not None:
            lines.append(f"- Glikogen: {round(glyco)}%")
        lines.append(f"- {_fuel_hint(glyco, peak_share)}")
        return "\n".join(lines)
    finally:
        if own:
            conn.close()


def weekly_section(db_conn=None) -> str:
    own = db_conn is None
    conn = db_conn or _db_connect()
    try:
        week = _week_monday(date.today())
        with conn.cursor() as cur:
            cur.execute(
                "SELECT mode, time_budget_h, focus_source, target_low, target_high, "
                "target_peak, feasible, note FROM qbot_v2.fitmodel_week_plan "
                "WHERE week <= %s ORDER BY week DESC LIMIT 1",
                (week,),
            )
            plan = cur.fetchone()
            if not plan:
                return ""
            mode, budget, focus, t_low, t_high, t_peak, feasible, note = plan
            t_low = float(t_low or 0); t_high = float(t_high or 0); t_peak = float(t_peak or 0)
            cur.execute(
                "SELECT COALESCE(SUM(low_strain),0), COALESCE(SUM(high_strain),0), "
                "COALESCE(SUM(peak_strain),0) FROM qbot_v2.fitmodel_ride_buckets "
                "WHERE started_at::date >= %s",
                (week,),
            )
            f_low, f_high, f_peak = (float(x) for x in cur.fetchone())

        def pct(f, t):
            return f"{round(f/t*100)}%" if t > 0 else "—"

        lines = [f"\U0001f4ca *FITMODEL — tydzien* (tryb: {mode}, budzet {budget}h, focus: {focus})",
                 f"- Tlenowe: {pct(f_low, t_low)} z celu ({round(f_low)}/{round(t_low)})",
                 f"- Progowe: {pct(f_high, t_high)} z celu ({round(f_high)}/{round(t_high)})",
                 f"- Neuro:   {pct(f_peak, t_peak)} z celu ({round(f_peak)}/{round(t_peak)})"]
        if feasible is False:
            lines.append("- ⚠️ plan niewykonalny w budzecie — patrz alternatywa")
        return "\n".join(lines)
    finally:
        if own:
            conn.close()


def full_brief(db_conn=None) -> str:
    parts = [s for s in (daily_section(db_conn), weekly_section(db_conn)) if s.strip()]
    return "\n\n".join(parts)


if __name__ == "__main__":
    print(full_brief())
