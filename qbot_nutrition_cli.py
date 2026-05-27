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

    day = args.date or date.today().isoformat()
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
    day = args.date or date.today().isoformat()
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
    day = args.date or date.today().isoformat()

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

    args = parser.parse_args()

    if args.command in ("meal-add", "meal_add", "meal", "add"):
        return cmd_meal_add(args)
    elif args.command in ("meal-list", "meal_list", "list"):
        return cmd_meal_list(args)
    elif args.command in ("meal-delete", "meal_delete", "delete"):
        return cmd_meal_delete(args)
    elif args.command in ("summary-show", "summary_show", "summary"):
        return cmd_summary_show(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
