"""Writer/job warstwy kontekstu nawierzchni (route_surface_context).

Dla odcinkow BEZ tagu OSM (route_surface_layer.source='osm_contextual') laczy sygnaly:
  - typ drogi (highway) + tracktype,
  - otoczenie z WorldCover (route_shade_layer, klasa dominujaca w zakresie km),
  - sygnal geologii (piach) z risk_flags,
i wnioskuje: szacunek nawierzchni + pewnosc + poziom ryzyka piachu + jednozdaniowe "dlaczego".

Twarde zasady (audyt nawierzchni 2026-07-02):
  - TAG WYGRYWA: dotyczy tylko odcinkow bez tagu (osm_contextual); osm_surface nietkniete.
  - NIE zmienia route_surface_layer.surface (etykieta nawierzchni zostaje silnika) — to warstwa OBOK.
  - Alarm piachu wymaga otwartego otoczenia >=70% (zeby nie krzyczec przy niepewnym otoczeniu).
  - Las >=50% daje efekt stabilizacji. Nizsza zgodnosc -> nizsza pewnosc, nie wieksza pewnosc.
"""
from __future__ import annotations

import argparse
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

WC_PL = {10: "las", 20: "zarosla", 30: "trawy", 40: "uprawy", 50: "zabudowa",
         60: "goly grunt", 70: "snieg/lod", 80: "woda", 90: "mokradla", 95: "namorzyny", 100: "mchy"}
PAVED_HIGHWAYS = {"residential", "living_street", "unclassified", "tertiary",
                  "secondary", "primary", "trunk", "motorway", "cycleway"}
OPEN_CLASSES = {30, 40, 60}  # trawy / uprawy / goly grunt


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def infer_context(highway: str | None, tracktype: str | None, wc_class: int | None,
                  agreement_pct: int, geology_sand: bool) -> dict[str, str]:
    """Reguly wnioskowania dla odcinka bez tagu. Zwraca surface_estimate/confidence/sand_risk/reason."""
    hw = str(highway or "").strip().lower()
    tt = str(tracktype or "").strip().lower()
    forest = wc_class == 10 and agreement_pct >= 50
    forest_sure = wc_class == 10 and agreement_pct >= 70
    openland = (wc_class in OPEN_CLASSES) and agreement_pct >= 70
    built = wc_class == 50 and agreement_pct >= 70

    def r(est, conf, risk, why):
        return {"surface_estimate": est, "estimate_confidence": conf, "sand_risk": risk, "reason": why}

    if hw in {"path", "footway", "bridleway"}:
        if forest:
            return r("singletrack/ubity grunt", "sr" if forest_sure else "ni-sr", "NISKIE",
                     "lesna sciezka: ubity grunt/korzenie, rzadko gleboki piach")
        if openland and geology_sand:
            return r("grunt, mozliwy piach", "ni", "SREDNIE", "otwarta sciezka na piaszczystym podlozu")
        return r("grunt", "ni", "NISKO-SR", "sciezka bez opisu")
    if hw == "track":
        if tt in {"grade1", "grade2", "grade3", "grade4", "grade5"}:
            base = {"grade1": "utwardzona", "grade2": "drobny szuter", "grade3": "szuter",
                    "grade4": "grunt", "grade5": "trawa/grunt"}[tt]
            risk = "SREDNIE" if (tt in {"grade4", "grade5"} and geology_sand) else "NISKO-SR"
            return r(base, "sr", risk, f"track {tt} (ocena jakosci z OSM)")
        if openland and geology_sand:
            return r("MOZLIWY GLEBOKI PIACH", "ni", "WYSOKIE",
                     "polna droga nietagowana na piaszczystym podlozu -> rozwaz objazd")
        if openland:
            return r("grunt/szuter", "ni", "SREDNIE", "polna droga bez opisu")
        if forest:
            return r("grunt/ubity", "ni-sr" if forest_sure else "ni", "UMIARK.",
                     "lesna droga gospodarcza bez oceny jakosci")
        return r("grunt", "ni", "SREDNIE", "track bez opisu i otoczenia")
    if hw in PAVED_HIGHWAYS:
        return r("prawdopodobnie utwardzona", "ni-sr", "NISKIE", "droga utwardzona wg typu (bez tagu)")
    if hw == "service":
        return r("utwardzona" if built else "pewnie utwardzona", "sr" if built else "ni", "NISKIE",
                 "droga dojazdowa")
    return r("nieznana", "ni", "?", "brak sygnalow")


def _route_base_row(conn, *, route_base_id: int | None, route_id: str | None) -> dict[str, Any] | None:
    if route_base_id is not None:
        row = conn.execute(
            "SELECT route_base_id, route_id, route_version_key FROM qbot_v2.route_base "
            "WHERE route_base_id=%s LIMIT 1", (route_base_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT route_base_id, route_id, route_version_key FROM qbot_v2.route_base "
            "WHERE route_id=%s ORDER BY updated_at DESC, route_base_id DESC LIMIT 1", (route_id,)).fetchone()
    return dict(row) if row else None


def _wc_dominant(conn, route_base_id: int, km_from: float, km_to: float) -> tuple[int | None, int, int]:
    rows = conn.execute(
        """
        SELECT sh.class_center AS cc, count(*) AS c
        FROM qbot_v2.route_axis_segments ax
        JOIN qbot_v2.route_shade_layer sh
          ON sh.route_base_id = ax.route_base_id AND sh.segment_index = ax.segment_index
        WHERE ax.route_base_id = %s AND ax.km_from >= %s AND ax.km_from < %s AND sh.coverage_status = 'ok'
        GROUP BY 1 ORDER BY 2 DESC
        """, (route_base_id, km_from, km_to)).fetchall()
    total = sum(r["c"] for r in rows)
    if not total:
        return None, 0, 0
    return int(rows[0]["cc"]), round(rows[0]["c"] / total * 100), total


def ensure_route_surface_context(*, route_id: str | int | None = None,
                                 route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")
    with _db_conn() as conn:
        base = _route_base_row(conn, route_base_id=route_base_id,
                               route_id=str(route_id) if route_id is not None else None)
        if not base:
            raise LookupError(f"No route_base for route_id={route_id!r} base={route_base_id!r}")
        bid = int(base["route_base_id"])
        vkey = str(base["route_version_key"])

        segs = conn.execute(
            """
            SELECT segment_index, highway, tracktype,
                   (surface_meta_json->>'km_from')::float AS km_from,
                   (surface_meta_json->>'km_to')::float AS km_to,
                   surface_meta_json->'risk_flags' AS risk_flags
            FROM qbot_v2.route_surface_layer
            WHERE route_base_id = %s AND source = 'osm_contextual'
            ORDER BY segment_index
            """, (bid,)).fetchall()

        written = 0
        risk_counts: dict[str, int] = {}
        with conn.transaction():
            conn.execute("DELETE FROM qbot_v2.route_surface_context WHERE route_base_id = %s", (bid,))
            for s in segs:
                wc, pct, n = _wc_dominant(conn, bid, s["km_from"], s["km_to"])
                geology_sand = any("sand" in str(x) for x in (s["risk_flags"] or []))
                out = infer_context(s["highway"], s["tracktype"], wc, pct, geology_sand)
                conn.execute(
                    """
                    INSERT INTO qbot_v2.route_surface_context (
                        route_base_id, route_version_key, segment_index, km_from, km_to,
                        highway, tracktype, dominant_class, dominant_pl, agreement_pct, n_nodes,
                        shade_coverage, geology_sand, surface_estimate, estimate_confidence, sand_risk, reason
                    ) VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s)
                    """,
                    (bid, vkey, s["segment_index"], s["km_from"], s["km_to"],
                     s["highway"], s["tracktype"], wc, WC_PL.get(wc) if wc else None, pct, n,
                     "ok" if wc else "none", geology_sand,
                     out["surface_estimate"], out["estimate_confidence"], out["sand_risk"], out["reason"]),
                )
                written += 1
                risk_counts[out["sand_risk"]] = risk_counts.get(out["sand_risk"], 0) + 1

    return {
        "status": "OK",
        "route_id": base["route_id"],
        "route_base_id": bid,
        "route_version_key": vkey,
        "context_rows": written,
        "sand_risk_counts": risk_counts,
    }


def _main(argv: list[str] | None = None) -> int:
    import json
    parser = argparse.ArgumentParser(description="Write route_surface_context (untagged-segment inference).")
    parser.add_argument("--route-id", dest="route_id")
    parser.add_argument("--route-base-id", dest="route_base_id", type=int)
    args = parser.parse_args(argv)
    print(json.dumps(ensure_route_surface_context(route_id=args.route_id, route_base_id=args.route_base_id),
                     ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
