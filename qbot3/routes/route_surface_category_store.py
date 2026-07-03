"""Kanoniczny kategoryzator nawierzchni (5 kategorii) -> route_surface_layer.surface_meta_json.

Przebieg DB->DB (BEZ Overpass). Czyta route_surface_layer (surface / tracktype /
highway / smoothness / classification_source z surface_meta_json) + route_surface_context
(WorldCover: sand_risk, surface_estimate, dominant_pl, reason) i dopisuje per odcinek:
  surface_category (1-5, int), surface_category_label (str), surface_category_reason (str).

Model (docs/DECISIONS.md 2026-07-03):
  1 twarda szybka    asphalt, concrete, paving_stones
  2 dobry gravel     compacted, fine_gravel; tracktype grade1-2
  3 zwykly gravel    gravel, dirt, ground, cobblestone; tracktype grade3
  4 trudna/wolna     grass, mixed; tracktype grade4
  5 ryzyko/niepewne  sand, mud, rocky, stony, unknown; tracktype grade5;
                     goly track/path bez tagu; kontekst piach/nieprzejezdnosc

Kolejnosc bazy: inferred_tracktype(grade) -> tagged_surface(tabela) -> goly(=5).
Kontekst (tylko dla golych): las/pole/grunt -> zlagodzenie do 4; piach/nieprzej. -> 5.
  UWAGA: wnioskowany sand_risk (SREDNIE/WNIOSK./...) NIE podbija do 5 (bez falszywej
  pewnosci); do 5 podbija tylko tag surface=sand lub sand_risk=WYSOKIE.
Degrader smoothness (po bazie+kontekscie, dziala TEZ na tagged surface):
  horrible/very_horrible/impassable -> 5
  bad/very_bad: utwardzone(kat.1) -> 4; grunt(kat.2-4) -> min(4, +1 oczko)

Flagi (bicycle/access/mtb) — Faza 2 (silnik nie zapisuje jeszcze tych tagow), tu nieobecne.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

LABELS = {1: "twarda szybka", 2: "dobry gravel", 3: "zwykly gravel",
          4: "trudna/wolna", 5: "ryzyko/niepewne"}

_GRADE_CAT = {"grade1": 2, "grade2": 2, "grade3": 3, "grade4": 4, "grade5": 5}
_SURF_CAT = {
    "asphalt": 1, "concrete": 1, "paving_stones": 1,
    "compacted": 2, "fine_gravel": 2,
    "gravel": 3, "dirt": 3, "ground": 3, "cobblestone": 3,
    "grass": 4, "mixed": 4,
    "sand": 5, "mud": 5, "rocky": 5, "stony": 5,
}
_BAD_SM = {"bad", "very_bad"}
_TERRIBLE_SM = {"horrible", "very_horrible", "impassable"}


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


def _base_category(surface: str | None, tracktype: str | None,
                   highway: str | None, cls: str | None) -> tuple[int, str, str]:
    tt = str(tracktype or "").strip().lower()
    hw = str(highway or "").strip().lower()
    s = str(surface or "").strip().lower()
    # a) tracktype-driven (wierniej niz label pochodny grade4->dirt itd.)
    if cls == "inferred_tracktype" and tt in _GRADE_CAT:
        return _GRADE_CAT[tt], f"tracktype {tt}", "tracktype"
    # b) jawny tag surface
    if cls == "tagged_surface":
        if s in _SURF_CAT:
            return _SURF_CAT[s], f"tag surface={s}", "tagged"
        return 5, f"tag surface={s or '?'} poza skala", "tagged"
    # awaryjnie: track z grade mimo innego cls
    if hw == "track" and tt in _GRADE_CAT:
        return _GRADE_CAT[tt], f"track tracktype {tt}", "tracktype"
    # c) wnioskowane z typu drogi (inferred_highway):
    #    utwardzona z klasy drogi -> tabela (NIE goly);
    #    track/path bez tagu (ground/dirt/unknown) -> goly = czerwona flaga
    if s in ("asphalt", "concrete", "paving_stones"):
        return _SURF_CAT[s], f"wnioskowane z typu drogi ({hw or '?'}) -> utwardzona", "inferred_paved"
    if s == "mixed":
        return 4, f"wnioskowane: {hw or 'droga'} zwykle utwardzona, slaby stan", "inferred_paved"
    return 5, "goly odcinek bez tagu OSM", "bare"


def _apply_context(cat: int, base_source: str, ctx: dict | None) -> tuple[int, str]:
    if not ctx:
        return cat, ""
    sand = str(ctx.get("sand_risk") or "").strip().upper()
    est = str(ctx.get("surface_estimate") or "").strip().lower()
    dom = str(ctx.get("dominant_pl") or "").strip().lower()
    strong_sand = (sand == "WYSOKIE") or ("piach" in est) or ("sand" in est)
    impass = ("nieprzej" in est) or ("impass" in est)
    land_like = (any(k in est for k in ("grunt", "polna", "szuter", "ubit", "utwardz", "droga"))
                 or any(k in dom for k in ("las", "pole", "traw", "upraw", "lak", "łak")))
    if base_source == "bare":
        if strong_sand or impass:
            return 5, "piach/nieprzejezdnosc: " + (est or "kontekst")
        if land_like:
            r = f"goly; WorldCover: {dom or est or 'teren'} -> przejezdna polna"
            if sand and sand not in ("NISKIE", "WYSOKIE"):
                r += f" (sand_risk={sand}, wnioskowane)"
            return 4, r
        return cat, "goly, kontekst niejednoznaczny -> ostroznie"
    # nie-goly: tylko twarde ryzyko piachu podbija nieutwardzone
    if strong_sand and cat >= 3:
        return 5, "otwarty teren + wysokie ryzyko piachu"
    return cat, ""


def _apply_smoothness(cat: int, smoothness: str | None) -> tuple[int, str]:
    sm = str(smoothness or "").strip().lower()
    if not sm:
        return cat, ""
    if sm in _TERRIBLE_SM:
        return 5, f"smoothness={sm} -> nieprzejezdne/ryzyko"
    if sm in _BAD_SM:
        if cat == 1:
            return 4, f"smoothness={sm} na utwardzonej -> rozbita, wolna"
        new = min(4, cat + 1)
        if new != cat:
            return new, f"smoothness={sm} -> -1 oczko"
        return cat, f"smoothness={sm}"
    return cat, ""


def compute_category(*, surface: str | None, tracktype: str | None, highway: str | None,
                     classification_source: str | None, smoothness: str | None,
                     ctx: dict | None) -> tuple[int, str, str]:
    """Zwraca (kategoria 1-5, label, reason)."""
    cat, reason, src = _base_category(surface, tracktype, highway, classification_source)
    cat, r_ctx = _apply_context(cat, src, ctx)
    cat, r_sm = _apply_smoothness(cat, smoothness)
    parts = [p for p in (reason, r_ctx, r_sm) if p]
    return cat, LABELS[cat], "; ".join(parts)


def _ctx_at_km(ctx_rows: list[dict], km_mid: float) -> dict | None:
    for c in ctx_rows:
        try:
            if float(c["km_from"]) <= km_mid < float(c["km_to"]):
                return c
        except (TypeError, ValueError, KeyError):
            continue
    return None


def _route_base_id(conn, *, route_id: str | None, route_base_id: int | None) -> int:
    if route_base_id is not None:
        return int(route_base_id)
    row = conn.execute(
        "SELECT route_base_id FROM qbot_v2.route_base WHERE route_id=%s "
        "ORDER BY updated_at DESC, route_base_id DESC LIMIT 1", (str(route_id),)).fetchone()
    if not row:
        raise LookupError(f"No route_base for route_id={route_id!r}")
    return int(row["route_base_id"])


def ensure_route_surface_category(*, route_id: str | int | None = None,
                                  route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")
    with _db_conn() as conn:
        rbid = _route_base_id(conn, route_id=(str(route_id) if route_id is not None else None),
                              route_base_id=route_base_id)
        seg_rows = conn.execute(
            "SELECT route_surface_layer_id, segment_index, surface, highway, tracktype, "
            "surface_meta_json FROM qbot_v2.route_surface_layer "
            "WHERE route_base_id=%s ORDER BY segment_index", (rbid,)).fetchall()
        ctx_rows = conn.execute(
            "SELECT km_from, km_to, dominant_pl, surface_estimate, sand_risk, reason "
            "FROM qbot_v2.route_surface_context WHERE route_base_id=%s ORDER BY km_from",
            (rbid,)).fetchall()
        ctx_rows = [dict(c) for c in ctx_rows]

        histogram = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        updated = 0
        with conn.transaction():
            for r in seg_rows:
                meta = dict(r["surface_meta_json"] or {})
                surface = r["surface"] or meta.get("surface_refined") or meta.get("surface_raw")
                cls = meta.get("classification_source")
                smoothness = meta.get("smoothness")
                try:
                    km_mid = (float(meta.get("km_from")) + float(meta.get("km_to"))) / 2.0
                except (TypeError, ValueError):
                    km_mid = None
                ctx = _ctx_at_km(ctx_rows, km_mid) if km_mid is not None else None
                cat, label, reason = compute_category(
                    surface=surface, tracktype=r["tracktype"], highway=r["highway"],
                    classification_source=cls, smoothness=smoothness, ctx=ctx)
                meta["surface_category"] = cat
                meta["surface_category_label"] = label
                meta["surface_category_reason"] = reason
                conn.execute(
                    "UPDATE qbot_v2.route_surface_layer SET surface_meta_json=%s::jsonb, "
                    "updated_at=now() WHERE route_surface_layer_id=%s",
                    (json.dumps(meta, ensure_ascii=False), r["route_surface_layer_id"]))
                histogram[cat] += 1
                updated += 1
    return {
        "status": "OK",
        "route_base_id": rbid,
        "category_rows": updated,
        "histogram": {LABELS[k]: v for k, v in histogram.items()},
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute+store surface_category (1-5) into route_surface_layer.")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--route-id", dest="route_id")
    g.add_argument("--route-base-id", dest="route_base_id", type=int)
    args = parser.parse_args(argv)
    res = ensure_route_surface_category(route_id=args.route_id, route_base_id=args.route_base_id)
    print(json.dumps(res, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
