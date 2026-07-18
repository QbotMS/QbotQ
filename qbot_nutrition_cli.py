#!/usr/bin/env python3
"""QBot Nutrition CLI — ad hoc meal logging and daily summary.

Usage:
  qbot nutrition meal add     --date 2026-05-27 --name "..." --kcal 720 ...
  qbot nutrition meal list    --date 2026-05-27
  qbot nutrition meal delete  --id 42 [--yes]
  qbot nutrition summary show --date 2026-05-27

Flags:
  --dry-run        Preview without writing
  --yes            Confirm without prompt (required for llm_estimate source)
  --source         llm_estimate | manual | qbot (default: manual)
  --confidence     low | medium | high (for llm_estimate)
  --notes          Free-text notes
  --assumptions    JSON string of LLM assumptions (optional)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

sys.path.insert(0, "/opt/qbot/app")


def _load_deps():
    from qbot_nutrition_db import (
        meal_log_create,
        meal_log_delete,
        meal_log_list,
        daily_summary_compute,
        daily_summary_get,
    )
    return meal_log_create, meal_log_delete, meal_log_list, daily_summary_compute, daily_summary_get


VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_SOURCES = {"llm_estimate", "manual", "qbot"}


def _resolve_date(raw: str) -> str:
    """Resolve 'today'/'yesterday' keywords to ISO date."""
    raw = raw.strip().lower()
    if raw in ("today", "dzisiaj", "dziś"):
        return date.today().isoformat()
    if raw in ("yesterday", "wczoraj"):
        return (date.today() - __import__("datetime").timedelta(days=1)).isoformat()
    try:
        date.fromisoformat(raw)
        return raw
    except ValueError:
        return date.today().isoformat()


def cmd_meal_add(args: argparse.Namespace) -> int:
    meal_log_create, _, _, daily_summary_compute, _ = _load_deps()

    source = args.source or "manual"
    if source not in VALID_SOURCES:
        print(f"ERROR: source must be one of {sorted(VALID_SOURCES)}")
        return 1

    confidence = args.confidence or "medium"
    if confidence not in VALID_CONFIDENCE:
        print(f"ERROR: confidence must be one of {sorted(VALID_CONFIDENCE)}")
        return 1

    if args.kcal is None or args.kcal < 0:
        print("ERROR: --kcal required and must be >= 0")
        return 1

    macros = {
        "carbs_g": args.carbs or 0,
        "protein_g": args.protein or 0,
        "fat_g": args.fat or 0,
        "fiber_g": args.fiber or 0,
    }
    for k, v in macros.items():
        if v < 0:
            print(f"ERROR: --{k.replace('_g','')} must be >= 0")
            return 1

    day = _resolve_date(args.date or date.today().isoformat())
    try:
        date.fromisoformat(day)
    except ValueError:
        print(f"ERROR: invalid date format: {day} (use YYYY-MM-DD)")
        return 1

    assumptions = None
    if args.assumptions:
        try:
            assumptions = json.loads(args.assumptions)
        except json.JSONDecodeError:
            print("ERROR: --assumptions must be valid JSON")
            return 1

    context = json.dumps({
        "source": source,
        "confidence": confidence,
        "assumptions": assumptions,
    }, ensure_ascii=False)

    item = {
        "food_name": args.name or "posiłek",
        "amount": 1,
        "unit": "porcja",
        "kcal": args.kcal,
        "carbs_g": args.carbs or 0,
        "protein_g": args.protein or 0,
        "fat_g": args.fat or 0,
        "fiber_g": args.fiber or 0,
        "sodium_mg": args.sodium or 0,
    }

    # ── Dry-run ──
    if args.dry_run:
        print("[DRY-RUN] Would create meal log:")
        print(f"  date:    {day}")
        print(f"  name:    {args.name}")
        print(f"  source:  {source}")
        print(f"  conf:    {confidence}")
        print(f"  kcal:    {args.kcal}")
        for k, v in macros.items():
            if v:
                print(f"  {k.replace('_g','')}:     {v}")
        if args.fiber:
            print(f"  fiber:   {args.fiber}")
        if args.sodium:
            print(f"  sodium:  {args.sodium} mg")
        if args.notes:
            print(f"  notes:   {args.notes}")
        if assumptions:
            print(f"  assumptions: {json.dumps(assumptions, ensure_ascii=False)[:200]}")
        print("\nRun with --yes to confirm.")
        return 0

    # ── LLM estimate confirmation ──
    if source == "llm_estimate" and not args.yes:
        print(f"⚠  source=llm_estimate (confidence={confidence}). Potwierdź.")
        print(f"   Posiłek: {args.name} — {args.kcal} kcal")
        resp = input("   Zapisać? [t/N] ").strip().lower()
        if resp not in ("t", "y", "yes", "tak"):
            print("Anulowano.")
            return 0

    # ── Save ──
    meal = meal_log_create(
        meal_type="meal",
        note=args.notes,
        context=context,
        eaten_at=f"{day}T12:00:00",
        items=[item],
    )

    meal_id = meal.get("id")
    print(f"✓ Posiłek zapisany: id={meal_id}")

    # Recompute summary
    summary = daily_summary_compute(day)
    print(f"  Dzienny bilans ({day}):")
    print(f"    kcal={summary.get('kcal_total',0):.0f}  "
          f"C={summary.get('carbs_total',0):.0f}g  "
          f"P={summary.get('protein_total',0):.0f}g  "
          f"F={summary.get('fat_total',0):.0f}g  "
          f"fiber={summary.get('fiber_total',0):.0f}g  "
          f"fluids={summary.get('fluids_total',0):.0f}ml")
    return 0


def cmd_meal_list(args: argparse.Namespace) -> int:
    _, _, meal_log_list, _, _ = _load_deps()
    day = _resolve_date(args.date or date.today().isoformat())
    meals = meal_log_list(date_str=day, limit=args.limit or 50)

    if not meals:
        print(f"Brak posiłków dla {day}.")
        return 0

    print(f"Posiłki {day} ({len(meals)}):")
    for m in meals:
        ctx = {}
        try:
            if m.get("context"):
                ctx = json.loads(m["context"])
        except (json.JSONDecodeError, TypeError):
            pass
        source = ctx.get("source", "?")
        conf = ctx.get("confidence", "")
        items = m.get("items", [])
        kcal_sum = sum(i.get("kcal", 0) or 0 for i in items)
        names = [i.get("food_name", "?") for i in items]
        tag = ""
        if source == "llm_estimate":
            tag = f" [LLM {conf}]"
        print(f"  id={m['id']}  {m['eaten_at'][:10]}  {kcal_sum:.0f} kcal  "
              f"{', '.join(names[:3])}{tag}")


def cmd_meal_delete(args: argparse.Namespace) -> int:
    _, meal_log_delete, _, daily_summary_compute, _ = _load_deps()
    meal_id = args.id

    if not args.yes and not args.dry_run:
        resp = input(f"Usunąć posiłek id={meal_id}? [t/N] ").strip().lower()
        if resp not in ("t", "y", "yes", "tak"):
            print("Anulowano.")
            return 0

    if args.dry_run:
        from qbot_nutrition_db import get_meal_log
        meal = get_meal_log(meal_id)
        if meal:
            print(f"[DRY-RUN] Would delete meal id={meal_id}: {meal.get('eaten_at','')[:10]}")
        else:
            print(f"[DRY-RUN] Meal id={meal_id} not found.")
        return 0

    deleted = meal_log_delete(meal_id)
    if deleted:
        date_str = deleted.get("eaten_at", "")[:10]
        daily_summary_compute(date_str)
        print(f"✓ Usunięto posiłek id={meal_id}. Podsumowanie {date_str} przeliczone.")
    else:
        print(f"✗ Posiłek id={meal_id} nie istnieje.")
        return 1
    return 0


def cmd_summary_show(args: argparse.Namespace) -> int:
    _, _, _, daily_summary_compute, daily_summary_get = _load_deps()
    day = _resolve_date(args.date or date.today().isoformat())

    if args.recompute:
        s = daily_summary_compute(day)
        print(f"  (przeliczone z bazy)")
    else:
        s = daily_summary_get(day)
        if not s:
            s = daily_summary_compute(day)
            print(f"  (przeliczone — brak cache)")
        else:
            print(f"  (z cache, computed_at={s.get('computed_at','?')[:19]})")

    print(f"  Dzienny bilans ({day}):")
    print(f"    kcal_total      {s.get('kcal_total',0):.0f}")
    print(f"    carbs_total     {s.get('carbs_total',0):.0f} g")
    print(f"    protein_total   {s.get('protein_total',0):.0f} g")
    print(f"    fat_total       {s.get('fat_total',0):.0f} g")
    print(f"    fiber_total     {s.get('fiber_total',0):.0f} g")
    print(f"    sodium_total    {s.get('sodium_total',0):.0f} mg")
    print(f"    fluids_total    {s.get('fluids_total',0):.0f} ml")
    return 0


def _nut_db():
    import os, psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
    )


def cmd_catalog_audit(args: argparse.Namespace) -> int:
    c = _nut_db()
    print("=== Catalog Audit ===")
    rows = c.execute("SELECT source, COUNT(*) AS cnt FROM food_items GROUP BY source ORDER BY cnt DESC").fetchall()
    print(f"food_items by source:")
    for r in rows:
        print(f"  {r['source']!r}: {r['cnt']}")
    rows = c.execute("SELECT id, name, source, verified FROM food_items WHERE verified=false ORDER BY id").fetchall()
    print(f"\nunverified:")
    if rows:
        for r in rows:
            linked = c.execute("SELECT COUNT(*) AS c FROM meal_log_items WHERE food_item_id=%s", (r['id'],)).fetchone()['c']
            print(f"  id={r['id']} name={r['name']!r} source={r['source']!r} verified={r['verified']} linked={linked}")
    else:
        print("  (none)")
    rows = c.execute("SELECT source, COUNT(*) AS cnt FROM meal_templates GROUP BY source ORDER BY cnt DESC").fetchall()
    print(f"\nmeal_templates by source:")
    for r in rows:
        print(f"  {r['source']!r}: {r['cnt']}")
    rows = c.execute("SELECT COUNT(*) AS total FROM meal_log_items").fetchone()
    linked = c.execute("SELECT COUNT(*) AS c FROM meal_log_items WHERE food_item_id IS NULL").fetchone()
    print(f"\nmeal_log_items: {rows['total']} total, {linked['c']} unlinked (food_item_id IS NULL)")
    if args.verbose:
        rows = c.execute("""
            SELECT food_name, COUNT(*) AS cnt, ROUND(AVG(kcal)) AS avg_kcal
            FROM meal_log_items WHERE food_item_id IS NULL AND food_name IS NOT NULL
            GROUP BY food_name ORDER BY cnt DESC
        """).fetchall()
        print(f"\ncandidate groups ({len(rows)}):")
        for r in rows:
            print(f"  {r['food_name']!r}: {r['cnt']}x, ~{r['avg_kcal']} kcal")
    c.close()
    return 0


def cmd_catalog_cleanup(args: argparse.Namespace) -> int:
    c = _nut_db()
    test_ids = c.execute(
        "SELECT id, name, source, verified FROM food_items WHERE name ILIKE 'test%' AND source='qbot' AND verified=false ORDER BY id"
    ).fetchall()

    if not test_ids:
        print("No test products found.")
        c.close()
        return 0

    can_delete = []
    for r in test_ids:
        linked = c.execute("SELECT COUNT(*) AS cnt FROM meal_log_items WHERE food_item_id=%s", (r['id'],)).fetchone()['cnt']
        can_delete.append((r, linked))

    print("Products to clean up:")
    total = 0
    for r, linked in can_delete:
        status = "CAN DELETE" if linked == 0 else f"IN USE ({linked} links)"
        print(f"  id={r['id']} name={r['name']!r} source={r['source']!r} verified={r['verified']} → {status}")
        if linked == 0:
            total += 1

    if not total:
        print("\nNo products can be safely deleted (all have links).")
        c.close()
        return 0

    if args.dry_run:
        print(f"\n[DRY-RUN] Would delete {total} product(s). Use --yes to execute.")
        c.close()
        return 0

    if not args.yes:
        print(f"\nUse --yes to delete {total} product(s).")
        c.close()
        return 1

    # Execute
    deleted = []
    for r, linked in can_delete:
        if linked == 0:
            c.execute("DELETE FROM food_items WHERE id=%s", (r['id'],))
            deleted.append(r['name'])

    c.commit()
    c.close()
    print(f"\n✓ Deleted {len(deleted)} product(s): {', '.join(deleted)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QBot Nutrition CLI — ad hoc meal logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── meal add ──
    p_add = sub.add_parser("meal-add", aliases=["meal_add", "meal", "add"],
                           help="Dodaj posiłek")
    p_add.add_argument("--date", default=date.today().isoformat())
    p_add.add_argument("--name", default="posiłek", help="Nazwa posiłku")
    p_add.add_argument("--kcal", type=float, required=True, help="Kalorie (kcal)")
    p_add.add_argument("--carbs", type=float, default=0, help="Węglowodany (g)")
    p_add.add_argument("--protein", type=float, default=0, help="Białko (g)")
    p_add.add_argument("--fat", type=float, default=0, help="Tłuszcz (g)")
    p_add.add_argument("--fiber", type=float, default=0, help="Błonnik (g)")
    p_add.add_argument("--sodium", type=float, default=0, help="Sód (mg)")
    p_add.add_argument("--source", choices=sorted(VALID_SOURCES), default="manual")
    p_add.add_argument("--confidence", choices=sorted(VALID_CONFIDENCE), default=None)
    p_add.add_argument("--notes")
    p_add.add_argument("--assumptions", help="JSON string of LLM assumptions")
    p_add.add_argument("--dry-run", action="store_true", help="Preview only")
    p_add.add_argument("--yes", action="store_true", help="Skip confirmation")

    # ── meal list ──
    p_list = sub.add_parser("meal-list", aliases=["meal_list", "list"],
                            help="Lista posiłków dla daty")
    p_list.add_argument("--date", default=date.today().isoformat())
    p_list.add_argument("--limit", type=int, default=50)

    # ── meal delete ──
    p_del = sub.add_parser("meal-delete", aliases=["meal_delete", "delete"],
                           help="Usuń posiłek po ID")
    p_del.add_argument("--id", type=int, required=True, help="Meal ID")
    p_del.add_argument("--yes", action="store_true", help="Skip confirmation")
    p_del.add_argument("--dry-run", action="store_true")

    # ── summary show ──
    p_sum = sub.add_parser("summary-show", aliases=["summary_show", "summary"],
                           help="Dzienne podsumowanie")
    p_sum.add_argument("--date", default=date.today().isoformat())
    p_sum.add_argument("--recompute", action="store_true", help="Wymuś przeliczenie")

    # ── template add ──
    p_ta = sub.add_parser("template-add", aliases=["template_add", "tadd"],
                          help="Dodaj szablon posiłku")
    p_ta.add_argument("--name", required=True)
    p_ta.add_argument("--serving-label", default="porcja")
    p_ta.add_argument("--kcal", type=float, required=True)
    p_ta.add_argument("--carbs", type=float, default=0)
    p_ta.add_argument("--protein", type=float, default=0)
    p_ta.add_argument("--fat", type=float, default=0)
    p_ta.add_argument("--fiber", type=float, default=0)
    p_ta.add_argument("--sodium", type=float, default=0)
    p_ta.add_argument("--source", default="manual_cronometer_migration")
    p_ta.add_argument("--confidence", choices=sorted(VALID_CONFIDENCE), default="high")
    p_ta.add_argument("--notes")
    p_ta.add_argument("--assumptions")
    p_ta.add_argument("--dry-run", action="store_true")

    # ── template list ──
    p_tl = sub.add_parser("template-list", aliases=["template_list", "tlist"],
                          help="Lista szablonów")
    p_tl.add_argument("--limit", type=int, default=50)

    # ── template show ──
    p_ts = sub.add_parser("template-show", aliases=["template_show", "tshow"],
                          help="Pokaż szablon")
    p_ts.add_argument("--name", required=True)

    # ── template delete ──
    p_td = sub.add_parser("template-delete", aliases=["template_delete", "tdel"],
                          help="Usuń szablon")
    p_td.add_argument("--name", required=True)
    p_td.add_argument("--yes", action="store_true")

    # ── template import ──
    p_ti = sub.add_parser("template-import", aliases=["template_import", "timport"],
                          help="Import szablonów z JSON")
    p_ti.add_argument("--file", required=True)
    p_ti.add_argument("--dry-run", action="store_true")
    p_ti.add_argument("--yes", action="store_true")

    # ── meal add-from-template ──
    p_mt = sub.add_parser("meal-add-from-template",
                          aliases=["meal_from_template", "maddt"],
                          help="Dodaj posiłek z szablonu")
    p_mt.add_argument("--template", required=True)
    p_mt.add_argument("--date", default=date.today().isoformat())
    p_mt.add_argument("--dry-run", action="store_true")
    p_mt.add_argument("--yes", action="store_true")

    # ── plan-day ──
    p_pd = sub.add_parser("plan-day", aliases=["plan_day", "plan"],
                          help="Zaplanuj jadłospis na dzień")
    p_pd.add_argument("--date", default=date.today().isoformat())
    p_pd.add_argument("--goal", choices=["deficit","maintenance","fueling","recovery"], default="deficit")
    p_pd.add_argument("--day-type", dest="day_type",
                      choices=["rest","light_training","normal_training","long_ride","hard_training","recovery"],
                      default="rest")
    p_pd.add_argument("--planned-ride-km", type=float)
    p_pd.add_argument("--target-kcal", type=float)
    p_pd.add_argument("--meals-count", type=int, default=3)
    p_pd.add_argument("--available-foods")
    p_pd.add_argument("--use-templates", action="store_true")
    p_pd.add_argument("--save-draft", action="store_true")
    p_pd.add_argument("--dry-run", action="store_true")
    p_pd.add_argument("--yes", action="store_true")

    # ── plan-show ──
    p_ps = sub.add_parser("plan-show", aliases=["plan_show", "pshow"],
                          help="Pokaż plan")
    p_ps.add_argument("--id", type=int)
    p_ps.add_argument("--date")

    # ── plan-list ──
    p_pl = sub.add_parser("plan-list", aliases=["plan_list", "plist"],
                          help="Lista planów")
    p_pl.add_argument("--date")
    p_pl.add_argument("--status")
    p_pl.add_argument("--limit", type=int, default=20)

    # ── plan-accept / plan-apply / plan-delete ──
    p_pa = sub.add_parser("plan-accept", aliases=["plan_accept", "paccept"],
                          help="Zaakceptuj plan (status → accepted)")
    p_pa.add_argument("--id", type=int, required=True)
    p_pa.add_argument("--yes", action="store_true")

    p_pap = sub.add_parser("plan-apply", aliases=["plan_apply", "papply"],
                           help="Zastosuj plan — dodaj posiłki do dziennego spożycia")
    p_pap.add_argument("--id", type=int, required=True)
    p_pap.add_argument("--yes", action="store_true")

    p_pdel = sub.add_parser("plan-delete", aliases=["plan_delete", "pdel"],
                            help="Usuń/anuluj plan")
    p_pdel.add_argument("--id", type=int, required=True)
    p_pdel.add_argument("--yes", action="store_true")

    # ── MCP log preview / add ──
    plp = sub.add_parser("log-preview", aliases=["log_preview"],
                         help="Podgląd posiłku przed zapisem (MCP compatible)")
    plp.add_argument("--date", default=date.today().isoformat())
    plp.add_argument("--meal-name")
    plp.add_argument("--raw-text", dest="raw_text")
    plp.add_argument("--kcal", type=float)
    plp.add_argument("--protein", "--protein-g", type=float, dest="protein")
    plp.add_argument("--carbs", "--carbs-g", type=float, dest="carbs")
    plp.add_argument("--fat", "--fat-g", type=float, dest="fat")
    plp.add_argument("--fluids", "--fluids-ml", type=float, dest="fluids")
    plp.add_argument("--source", default="chatgpt_mcp")
    plp.add_argument("--confidence", default="medium")

    pla = sub.add_parser("log-add", aliases=["log_add"],
                         help="Zapisz posiłek do nutrition DB (wymaga --yes i --idempotency-key)")
    pla.add_argument("--date", default=date.today().isoformat())
    pla.add_argument("--meal-name")
    pla.add_argument("--raw-text", dest="raw_text")
    pla.add_argument("--kcal", type=float)
    pla.add_argument("--protein", "--protein-g", type=float, dest="protein")
    pla.add_argument("--carbs", "--carbs-g", type=float, dest="carbs")
    pla.add_argument("--fat", "--fat-g", type=float, dest="fat")
    pla.add_argument("--fluids", "--fluids-ml", type=float, dest="fluids")
    pla.add_argument("--source", default="chatgpt_mcp")
    pla.add_argument("--confidence", default="medium")
    pla.add_argument("--idempotency-key", required=True)
    pla.add_argument("--yes", action="store_true")

    # ── catalog-audit ──
    p_ca = sub.add_parser("catalog-audit", aliases=["catalog_audit", "caudit"],
                          help="Audyt katalogu produktów")
    p_ca.add_argument("--verbose", action="store_true", help="Pokaż szczegóły")

    # ── catalog-cleanup ──
    p_cc = sub.add_parser("catalog-cleanup", aliases=["catalog_cleanup", "cclean"],
                          help="Usuń testowe produkty z katalogu")
    p_cc.add_argument("--dry-run", action="store_true", help="Tylko pokaż, nie usuwaj")
    p_cc.add_argument("--yes", action="store_true", help="Wykonaj cleanup")

    args = parser.parse_args()

    if args.command in ("meal-add", "meal_add", "meal", "add"):
        return cmd_meal_add(args)
    elif args.command in ("meal-list", "meal_list", "list"):
        return cmd_meal_list(args)
    elif args.command in ("meal-delete", "meal_delete", "delete"):
        return cmd_meal_delete(args)
    elif args.command in ("summary-show", "summary_show", "summary"):
        return cmd_summary_show(args)
    elif args.command in ("template-add", "template_add", "tadd"):
        return cmd_template_add(args)
    elif args.command in ("template-list", "template_list", "tlist"):
        return cmd_template_list(args)
    elif args.command in ("template-show", "template_show", "tshow"):
        return cmd_template_show(args)
    elif args.command in ("template-delete", "template_delete", "tdel"):
        return cmd_template_delete(args)
    elif args.command in ("template-import", "template_import", "timport"):
        return cmd_template_import(args)
    elif args.command in ("meal-add-from-template", "meal_from_template", "maddt"):
        return cmd_meal_add_from_template(args)
    elif args.command in ("plan-day", "plan_day", "plan"):
        return cmd_plan_day(args)
    elif args.command in ("plan-show", "plan_show", "pshow"):
        return cmd_plan_show(args)
    elif args.command in ("plan-list", "plan_list", "plist"):
        return cmd_plan_list(args)
    elif args.command in ("plan-accept", "plan_accept", "paccept"):
        return cmd_plan_accept(args)
    elif args.command in ("plan-apply", "plan_apply", "papply"):
        return cmd_plan_apply(args)
    elif args.command in ("plan-delete", "plan_delete", "pdel"):
        return cmd_plan_delete(args)
    elif args.command in ("log-preview", "log_preview"):
        return cmd_log_preview(args)
    elif args.command in ("log-add", "log_add"):
        return cmd_log_add(args)
    elif args.command in ("catalog-audit", "catalog_audit", "caudit"):
        return cmd_catalog_audit(args)
    elif args.command in ("catalog-cleanup", "catalog_cleanup", "cclean"):
        return cmd_catalog_cleanup(args)
    else:
        parser.print_help()
        return 1


# ── Template command implementations ────────────────────────────────────────

def cmd_template_add(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import template_create, template_get_by_name

    existing = template_get_by_name(args.name)
    if existing and not args.dry_run:
        print(f"⚠ Szablon '{args.name}' już istnieje (id={existing['id']}). Użyj template-delete najpierw.")
        return 1

    assumptions = None
    if args.assumptions:
        try:
            assumptions = json.loads(args.assumptions)
        except json.JSONDecodeError:
            print("ERROR: --assumptions must be valid JSON")
            return 1

    if args.dry_run:
        print(f"[DRY-RUN] Would create template: {args.name}")
        print(f"  {args.kcal} kcal, C={args.carbs} P={args.protein} F={args.fat}")
        return 0

    tmpl = template_create(
        name=args.name,
        serving_label=args.serving_label,
        kcal=args.kcal,
        carbs_g=args.carbs,
        protein_g=args.protein,
        fat_g=args.fat,
        fiber_g=args.fiber,
        sodium_mg=args.sodium,
        source=args.source,
        confidence=args.confidence,
        notes=args.notes,
        assumptions_json=assumptions,
    )
    print(f"✓ Szablon zapisany: id={tmpl['id']} {tmpl['name']}")
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import template_list
    templates = template_list(limit=args.limit or 50)
    if not templates:
        print("Brak szablonów.")
        return 0
    print(f"Szablony ({len(templates)}):")
    for t in templates:
        print(f"  [{t['id']}] {t['name']} — {t['kcal']:.0f} kcal "
              f"C={t['carbs_g']:.0f} P={t['protein_g']:.0f} F={t['fat_g']:.0f} "
              f"src={t['source']} conf={t['confidence']}")
    return 0


def cmd_template_show(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import template_get_by_name
    t = template_get_by_name(args.name)
    if not t:
        print(f"Szablon '{args.name}' nie znaleziony.")
        return 1
    print(f"  name:           {t['name']}")
    print(f"  serving_label:  {t['serving_label']}")
    print(f"  kcal:           {t['kcal']:.0f}")
    print(f"  carbs_g:        {t['carbs_g']:.0f}")
    print(f"  protein_g:      {t['protein_g']:.0f}")
    print(f"  fat_g:          {t['fat_g']:.0f}")
    print(f"  fiber_g:        {t['fiber_g']:.0f}")
    print(f"  sodium_mg:      {t['sodium_mg']:.0f}")
    print(f"  source:         {t['source']}")
    print(f"  confidence:     {t['confidence']}")
    print(f"  notes:          {t['notes'] or '-'}")
    if t.get('assumptions_json'):
        a = t['assumptions_json']
        if isinstance(a, str):
            a = json.loads(a)
        print(f"  assumptions:    {json.dumps(a, ensure_ascii=False)[:200]}")
    print(f"  created_at:     {t['created_at'][:19]}")
    return 0


def cmd_template_delete(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import template_get_by_name, template_delete
    t = template_get_by_name(args.name)
    if not t:
        print(f"Szablon '{args.name}' nie znaleziony.")
        return 1
    if not args.yes:
        resp = input(f"Usunąć szablon '{args.name}' (id={t['id']})? [t/N] ").strip().lower()
        if resp not in ("t", "y", "yes", "tak"):
            print("Anulowano.")
            return 0
    template_delete(t["id"])
    print(f"✓ Usunięto szablon '{args.name}'.")
    return 0


def cmd_template_import(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import template_import_batch
    try:
        with open(args.file) as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: cannot read {args.file}: {e}")
        return 1

    if not isinstance(data, list):
        print("ERROR: JSON must be a list of templates")
        return 1

    dry = args.dry_run
    if not dry and not args.yes:
        print(f"Zaimportować {len(data)} szablonów z {args.file}?")
        resp = input("[t/N] ").strip().lower()
        if resp not in ("t", "y", "yes", "tak"):
            print("Anulowano.")
            return 0

    result = template_import_batch(data, dry_run=dry)
    if dry:
        print(f"[DRY-RUN] Would process {len(result['preview'])} templates:")
        for p in result['preview']:
            print(f"  {p['name']} → {p['action']}")
    else:
        print(f"✓ Import: {result['created']} created, {result['updated']} updated, {result['skipped']} skipped")
    return 0


def cmd_meal_add_from_template(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import (template_get_by_name, meal_log_create,
                                    daily_summary_compute)

    tmpl = template_get_by_name(args.template)
    if not tmpl:
        print(f"Szablon '{args.template}' nie znaleziony. Lista: qbot nutrition template-list")
        return 1

    day = _resolve_date(args.date or date.today().isoformat())

    kcal = tmpl["kcal"]
    item = {
        "food_name": tmpl["name"],
        "amount": 1,
        "unit": tmpl.get("serving_label", "porcja"),
        "kcal": kcal,
        "carbs_g": tmpl["carbs_g"],
        "protein_g": tmpl["protein_g"],
        "fat_g": tmpl["fat_g"],
        "fiber_g": tmpl.get("fiber_g", 0),
        "sodium_mg": tmpl.get("sodium_mg", 0),
    }

    context = json.dumps({
        "source": "template",
        "template_id": tmpl["id"],
        "template_name": tmpl["name"],
        "confidence": tmpl.get("confidence", "high"),
    }, ensure_ascii=False)

    if args.dry_run:
        print(f"[DRY-RUN] Would add meal from template '{tmpl['name']}' on {day}")
        print(f"  {kcal:.0f} kcal, {item['carbs_g']:.0f}g C, {item['protein_g']:.0f}g P, {item['fat_g']:.0f}g F")
        return 0

    if not args.yes:
        print(f"Dodać '{tmpl['name']}' ({kcal:.0f} kcal) na {day}?")
        resp = input("[t/N] ").strip().lower()
        if resp not in ("t", "y", "yes", "tak"):
            print("Anulowano.")
            return 0

    meal_log_create(
        meal_type="meal",
        context=context,
        note=f"from template: {args.template}",
        eaten_at=f"{day}T12:00:00",
        items=[item],
    )
    s = daily_summary_compute(day)
    print(f"✓ Dodano z szablonu '{args.template}'. Bilans dnia {day}:")
    print(f"  kcal={s.get('kcal_total',0):.0f} C={s.get('carbs_total',0):.0f}g "
          f"P={s.get('protein_total',0):.0f}g F={s.get('fat_total',0):.0f}g")
    return 0


# ── Plan command implementations ─────────────────────────────────────────────

def _plan_from_args(args) -> dict:
    from qbot_nutrition_planner import plan_day, _get_templates_from_db, _get_already_logged
    day = _resolve_date(args.date or date.today().isoformat())
    templates = _get_templates_from_db() if args.use_templates else []
    av = [f.strip() for f in args.available_foods.split(",") if f.strip()] if args.available_foods else None
    already = _get_already_logged(day) if not args.dry_run else 0
    return plan_day(
        goal=args.goal, day_type=args.day_type, date_str=day,
        planned_ride_km=args.planned_ride_km, target_kcal=args.target_kcal,
        meals_count=args.meals_count or 3, available_foods=av,
        use_templates=bool(templates) and args.use_templates, templates=templates,
        already_logged_kcal=already,
    )


def cmd_plan_day(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    day = _resolve_date(args.date or date.today().isoformat())
    meals = plan.get("meals", [])

    print(f"Plan dnia {day}")
    print(f"  goal:     {plan['goal']} | day_type: {plan['day_type']}")
    print(f"  TDEE:     {plan['estimated_total_expenditure']:.0f} kcal (conf={plan['confidence']})")
    print(f"  deficit:  {plan['target_deficit_kcal']:.0f} kcal")
    print(f"  intake:   {plan['target_intake_kcal']:.0f} kcal")
    if plan.get("already_logged_kcal", 0) > 0:
        print(f"  eaten:    {plan['already_logged_kcal']:.0f} kcal")
    print(f"  remaining:{plan['remaining_kcal']:.0f} kcal")
    print(f"  macros:   P={plan['target_protein_g']:.0f}g C={plan['target_carbs_g']:.0f}g F={plan['target_fat_g']:.0f}g")
    print(f"  posiłków: {len(meals)}")
    for i, m in enumerate(meals):
        print(f"    {i+1}. {m.get('meal_name','?')} — {m.get('kcal',0):.0f} kcal "
              f"P={m.get('protein_g',0):.0f}g C={m.get('carbs_g',0):.0f}g F={m.get('fat_g',0):.0f}g")
    if plan.get("warnings_json"):
        w = plan["warnings_json"]
        if isinstance(w, list):
            for wm in w:
                print(f"  ⚠ {wm}")
    print(f"\n  {plan.get('note','To jest plan/draft.')}")

    if args.dry_run or not args.save_draft:
        if not args.save_draft:
            print("  (--save-draft nie podano — plan nie zapisany)")
        return 0

    if not args.yes:
        resp = input("Zapisać draft planu do bazy? [t/N] ").strip().lower()
        if resp not in ("t","y","yes","tak"):
            print("Anulowano."); return 0

    from qbot_nutrition_db import plan_create
    p = plan_create(date_str=day, goal=plan["goal"], day_type=plan["day_type"],
        planned_ride_km=plan.get("planned_ride_km"),
        estimated_total_expenditure=plan["estimated_total_expenditure"],
        target_deficit_kcal=plan["target_deficit_kcal"],
        target_intake_kcal=plan["target_intake_kcal"],
        target_protein_g=plan.get("target_protein_g"),
        target_carbs_g=plan.get("target_carbs_g"),
        target_fat_g=plan.get("target_fat_g"),
        planned_meals_count=args.meals_count or 3,
        available_foods=args.available_foods,
        used_templates=bool(plan.get("used_templates")),
        confidence=plan.get("confidence","medium"),
        assumptions_json=plan.get("assumptions_json"),
        warnings_json=plan.get("warnings_json") if isinstance(plan.get("warnings_json"), list) else None,
        meals=meals)
    print(f"✓ Draft zapisany: plan_id={p['id']}")
    return 0


def cmd_plan_show(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import plan_get, plan_list
    plan = None
    if args.id:
        plan = plan_get(args.id)
    elif args.date:
        plans = plan_list(date_str=_resolve_date(args.date), limit=1)
        if plans:
            plan = plan_get(plans[0]["id"])
    if not plan:
        print("Plan nie znaleziony.")
        return 1
    meals = plan.get("meals", [])
    print(f"Plan id={plan['id']}  date={plan['date']}  status={plan['status']}")
    print(f"  goal={plan['goal']} day_type={plan['day_type']}")
    print(f"  TDEE={plan.get('estimated_total_expenditure','?')} kcal")
    print(f"  intake={plan.get('target_intake_kcal','?')} deficit={plan.get('target_deficit_kcal','?')}")
    print(f"  macros: P={plan.get('target_protein_g','?')}g C={plan.get('target_carbs_g','?')}g F={plan.get('target_fat_g','?')}g")
    print(f"  confidence={plan.get('confidence','?')} source={plan.get('source','?')}")
    if meals:
        print(f"  meals ({len(meals)}):")
        for m in meals:
            print(f"    {m['meal_order']}. {m['meal_name']} — {m.get('kcal',0):.0f} kcal")
    return 0


def cmd_plan_list(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import plan_list
    plans = plan_list(date_str=_resolve_date(args.date) if args.date else None,
                      status=args.status, limit=args.limit or 20)
    if not plans:
        print("Brak planów.")
        return 0
    print(f"Plany ({len(plans)}):")
    for p in plans:
        print(f"  id={p['id']} {p['date']} status={p['status']} "
              f"goal={p['goal']} intake={p.get('target_intake_kcal','?'):.0f} kcal")
    return 0


def cmd_plan_accept(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import plan_get, plan_update_status
    plan = plan_get(args.id)
    if not plan:
        print(f"Plan id={args.id} nie znaleziony."); return 1
    if not args.yes:
        resp = input(f"Zaakceptować plan id={args.id} ({plan['date']})? [t/N] ").strip().lower()
        if resp not in ("t","y","yes","tak"): print("Anulowano."); return 0
    plan_update_status(args.id, "accepted")
    print(f"✓ Plan id={args.id} zaakceptowany.")
    return 0


def cmd_plan_apply(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import plan_get, plan_apply
    plan = plan_get(args.id)
    if not plan:
        print(f"Plan id={args.id} nie znaleziony."); return 1
    meals = plan.get("meals", [])
    total = sum(m.get("kcal", 0) or 0 for m in meals)
    print(f"Plan id={args.id}: {len(meals)} posiłków, {total:.0f} kcal łącznie.")
    if not args.yes:
        resp = input(f"UWAGA: dodać {len(meals)} posiłków do dziennego spożycia? [t/N] ").strip().lower()
        if resp not in ("t","y","yes","tak"): print("Anulowano."); return 0
    result = plan_apply(args.id)
    if result.get("status") == "ok":
        p = result.get("plan", {})
        print(f"✓ Plan id={args.id} zastosowany — posiłki dodane do spożycia ({p.get('date','')}).")
    else:
        print(f"✗ Błąd: {result.get('error','')}")
        return 1
    return 0


def cmd_plan_delete(args: argparse.Namespace) -> int:
    from qbot_nutrition_db import plan_get, plan_delete
    plan = plan_get(args.id)
    if not plan:
        print(f"Plan id={args.id} nie znaleziony."); return 1
    if not args.yes:
        resp = input(f"Usunąć plan id={args.id} ({plan['date']}, {plan['status']})? [t/N] ").strip().lower()
        if resp not in ("t","y","yes","tak"): print("Anulowano."); return 0
    plan_delete(args.id)
    print(f"✓ Plan id={args.id} usunięty.")
    return 0


# ── MCP nutrition log commands ──────────────────────────────────────────────

def cmd_log_preview(args: argparse.Namespace) -> int:
    """Preview meal before saving — no DB writes."""
    import hashlib, json
    from datetime import date as dt_date

    day = _resolve_date(args.date or dt_date.today().isoformat())
    raw = args.raw_text or ""
    meal_name = args.meal_name or (raw[:60] if raw else "posiłek")
    kcal = args.kcal or 0
    prot = args.protein or 0
    carbs = args.carbs or 0
    fat = args.fat or 0
    fluids = args.fluids or 0
    source = args.source or "chatgpt_mcp"
    conf = args.confidence or "medium"

    payload = f"{day}|{meal_name}|{kcal}|{prot}|{carbs}|{fat}"
    idem_key = hashlib.sha256(payload.encode()).hexdigest()[:16]

    draft = {
        "date": day, "meal_name": meal_name, "raw_text": raw,
        "kcal_total": kcal, "protein_g": prot, "carbs_g": carbs, "fat_g": fat,
        "fluids_ml": fluids, "source": source, "confidence": conf,
    }
    print("[PREVIEW] Draft meal — nic nie zapisano.")
    print(json.dumps(draft, indent=2, ensure_ascii=False))
    print(f"\nIdempotency key: {idem_key}")
    print("Aby zapisać: qbot nutrition log-add --idempotency-key " + idem_key + " --yes")
    return 0


def cmd_log_add(args: argparse.Namespace) -> int:
    """Save meal to nutrition DB. Requires --yes and --idempotency-key."""
    import json
    from qbot_nutrition_db import meal_log_create, daily_summary_compute, _conn as nut_conn

    if not args.yes:
        print("ERROR: --yes required to save.")
        return 1

    idem_key = args.idempotency_key or ""
    if not idem_key:
        print("ERROR: --idempotency-key required. Use qbot nutrition log-preview to generate one.")
        return 1

    # Check idempotency
    try:
        c = nut_conn()
        cur = c.cursor()
        cur.execute("SELECT 1 FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
        if cur.fetchone():
            c.close()
            print(f"⚠ DUPLICATE: idempotency_key '{idem_key}' already exists. Meal already saved.")
            return 0
        c.close()
    except Exception:
        pass

    day = _resolve_date(args.date or date.today().isoformat())
    meal_name = args.meal_name or "posiłek"
    kcal = args.kcal or 0
    prot = args.protein or 0
    carbs = args.carbs or 0
    fat = args.fat or 0
    fluids = args.fluids or 0
    source = args.source or "chatgpt_mcp"
    conf = args.confidence or "medium"
    raw_text = args.raw_text or ""
    idem_key = args.idempotency_key or ""

    context = json.dumps({"source": source, "confidence": conf, "raw_text": raw_text, "idempotency_key": idem_key})
    item = {"food_name": meal_name, "amount": 1, "unit": "porcja", "kcal": kcal,
            "carbs_g": carbs, "protein_g": prot, "fat_g": fat}

    try:
        meal = meal_log_create(meal_type="meal", note=f"MCP: {meal_name}", context=context, eaten_at=f"{day}T12:00:00", items=[item])
        summary = daily_summary_compute(day)

        # Audit
        try:
            c2 = nut_conn()
            cur2 = c2.cursor()
            cur2.execute(
                "INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (idem_key, meal.get("id"), day, source, raw_text, json.dumps({"meal_name": meal_name, "kcal": kcal}, default=str), json.dumps({"meal_id": meal.get("id")}, default=str)))
            c2.commit(); c2.close()
        except Exception:
            pass


        print(f"✓ Saved: id={meal.get('id')} — {meal_name} ({kcal:.0f} kcal)")
        print(f"  Daily summary ({day}): kcal_total={summary.get('kcal_total',0):.0f}, P={summary.get('protein_total',0):.0f}g, C={summary.get('carbs_total',0):.0f}g, F={summary.get('fat_total',0):.0f}g")
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
