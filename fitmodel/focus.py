from __future__ import annotations

"""FITMODEL T2 -- auto-focus (route / deficit). Spec sek. 6.3.

Zwraca wagi emphasis (low, high, peak; suma=1) + zrodlo focus:
  Stan A (event/trasa z GPX) -> z profilu trasy:
     duzy dystans/wielodniowka      -> Low + durability
     wysoka gestosc przewyzszen m/km -> High
     duzy udzial luznej nawierzchni  -> Peak/neuro
     + dryf w czasie: daleko od daty -> baza Low; blizej -> ku specyfice trasy
  Stan B (horyzont pusty) -> auto-balans ku NAJSLABSZEMU wiadru (rolling-load).
Degradacja lagodna: brak eventu/trasy -> automatycznie Stan B.

Trasa wskazywana przez route_artifact_id (z eventu gdy bedzie link, albo recznie/NL).
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Nawierzchnie "luzne" (koszt neuro/technika) — etykiety PL z route_surface_segments
LOOSE_SURFACES = {
    "grunt", "ziemia/grunt", "gravel/żwir", "gravel drobny", "nieutwardzona",
    "ubita nawierzchnia", "piasek", "sand", "trawa",
}
BASE_WEIGHTS = {"low": 0.50, "high": 0.30, "peak": 0.20}


def _normalize(w: dict[str, float]) -> dict[str, float]:
    s = sum(w.values()) or 1.0
    return {k: round(v / s, 3) for k, v in w.items()}


def _recent_props(db_conn, as_of: date, window_days: int = 28) -> dict[str, float]:
    start = as_of - timedelta(days=window_days)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(low_strain),0), COALESCE(SUM(high_strain),0), "
            "COALESCE(SUM(peak_strain),0) FROM qbot_v2.fitmodel_ride_buckets "
            "WHERE started_at::date > %s AND started_at::date <= %s",
            (start, as_of),
        )
        low, high, peak = (float(x) for x in cur.fetchone())
    s = (low + high + peak) or 1.0
    return {"low": low / s, "high": high / s, "peak": peak / s}


def _route_metrics(db_conn, route_artifact_id: int) -> dict[str, Any] | None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT distance_km, elevation_gain_m FROM qbot_v2.route_parse_results "
            "WHERE route_artifact_id=%s ORDER BY parsed_at DESC LIMIT 1",
            (route_artifact_id,),
        )
        pr = cur.fetchone()
        if not pr:
            return None
        distance_km = float(pr[0] or 0.0)
        elev_gain = float(pr[1] or 0.0)
        cur.execute(
            "SELECT id FROM qbot_v2.route_surface_profiles "
            "WHERE route_artifact_id=%s ORDER BY enriched_at DESC LIMIT 1",
            (route_artifact_id,),
        )
        prof = cur.fetchone()
        loose_frac = 0.0
        if prof:
            cur.execute(
                "SELECT surface, COALESCE(SUM(distance_m),0) "
                "FROM qbot_v2.route_surface_segments WHERE route_surface_profile_id=%s "
                "GROUP BY surface",
                (prof[0],),
            )
            tot = 0.0
            loose = 0.0
            for surf, dist in cur.fetchall():
                dist = float(dist or 0.0)
                if (surf or "").lower() == "nieznana":
                    continue  # nieznana nie liczy sie ani jako luzna ani twarda
                tot += dist
                if (surf or "").lower() in LOOSE_SURFACES:
                    loose += dist
            loose_frac = (loose / tot) if tot > 0 else 0.0
    climb_density = (elev_gain / distance_km) if distance_km > 0 else 0.0
    return {"distance_km": round(distance_km, 1), "elev_gain_m": round(elev_gain),
            "climb_density_m_per_km": round(climb_density, 1),
            "loose_frac": round(loose_frac, 3)}


def _route_weights(rm: dict[str, Any]) -> dict[str, float]:
    # surowe scory; im wyzszy parametr, tym wiekszy nacisk danego systemu
    score_low = 1.0 + rm["distance_km"] / 80.0          # dystans -> baza/durability
    score_high = 0.4 + rm["climb_density_m_per_km"] / 12.0  # m/km -> prog
    score_peak = 0.2 + rm["loose_frac"] * 2.0           # luzna nawierzchnia -> neuro
    return _normalize({"low": score_low, "high": score_high, "peak": score_peak})


def compute_focus(db_conn, as_of: date, route_artifact_id: int | None = None,
                  days_to_event: int | None = None) -> dict[str, Any]:
    # Stan A: trasa znana
    if route_artifact_id is not None:
        rm = _route_metrics(db_conn, route_artifact_id)
        if rm:
            route_w = _route_weights(rm)
            # dryf czasu: daleko -> baza (Low), blisko -> specyfika trasy
            if days_to_event is None:
                w_spec = 0.6
                drift = "brak daty -> w_spec=0.6"
            else:
                w_spec = max(0.2, min(1.0, 1.0 - days_to_event / 42.0))
                drift = f"{days_to_event} dni do daty -> w_spec={w_spec:.2f}"
            weights = _normalize({
                k: BASE_WEIGHTS[k] * (1 - w_spec) + route_w[k] * w_spec
                for k in BASE_WEIGHTS
            })
            note = (f"trasa #{route_artifact_id}: {rm['distance_km']}km, "
                    f"{rm['climb_density_m_per_km']}m/km, luzna {rm['loose_frac']:.0%}; {drift}")
            return {"weights": weights, "source": "route", "note": note, "route": rm}

    # Stan B: deficyt -> nacisk na najslabszy wiadro (odwrotnosc udzialow)
    props = _recent_props(db_conn, as_of)
    inv = {k: max(0.0, 1.0 - v) for k, v in props.items()}
    weights = _normalize(inv) if sum(inv.values()) > 0 else dict(BASE_WEIGHTS)
    weakest = min(props, key=props.get)
    note = (f"deficyt: udzialy 4-tyg low={props['low']:.0%}/high={props['high']:.0%}/"
            f"peak={props['peak']:.0%} -> nacisk na najslabszy ({weakest})")
    return {"weights": weights, "source": "deficit", "note": note, "route": None}


if __name__ == "__main__":
    import argparse
    from fitmodel.ftp_resolver import _db_connect, _coerce_date
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--route-id", type=int, default=None, help="route_artifact_id (Stan A)")
    ap.add_argument("--days-to-event", type=int, default=None)
    args = ap.parse_args()
    conn = _db_connect()
    try:
        f = compute_focus(conn, _coerce_date(args.as_of), args.route_id, args.days_to_event)
        print("FOCUS:")
        print("  source :", f["source"])
        print("  weights:", f["weights"])
        print("  note   :", f["note"])
        if f["route"]:
            print("  route  :", f["route"])
    finally:
        conn.close()
