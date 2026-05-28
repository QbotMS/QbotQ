#!/usr/bin/env python3
"""Check template alias map for collisions.

Usage:
  cd /opt/qbot/app && python3 scripts/check_template_aliases.py

Shows all auto-generated and explicit aliases, highlighting ambiguous ones.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Mock DB-less mode: seed _get_meal_templates_cache with data from cronometer_templates.json
_SEED_TEMPLATES = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "cronometer_templates.json").read_text()
)

# Assign sequential IDs (1-based). NOTE: real DB may differ; "_build_template_aliases"
# will use whatever IDs are returned by _get_meal_templates_cache().
_SEED_WITH_IDS = [
    {**tmpl, "id": idx + 1, "assumptions_json": None}
    for idx, tmpl in enumerate(_SEED_TEMPLATES)
]

# Replace the real cache with our seed data (safe in test mode)
import qbot_query_router as qr

# Monkey-patch the lru_cache
orig_cache = qr._get_meal_templates_cache
qr._get_meal_templates_cache.cache_clear()
qr._get_meal_templates_cache = lambda: tuple(_SEED_WITH_IDS)  # type: ignore

# Also clear module-level _TEMPLATE_ALIASES so _build_template_aliases runs fresh
qr._TEMPLATE_ALIASES.clear()


def main():
    print("=" * 72)
    print("TEMPLATE ALIAS CHECK — 7 seed templates")
    print("=" * 72)

    # Show source templates
    print(f"\n{'─' * 72}")
    print("Source templates (from cronometer_templates.json + sequential IDs):")
    print(f"{'─' * 72}")
    print(f"{'ID':>3} | {'Name':<40} | {'kcal':>6} | {'P':>5} | {'C':>5} | {'F':>5}")
    print(f"{'─' * 72}")
    for tmpl in _SEED_WITH_IDS:
        print(f"{tmpl['id']:>3} | {tmpl['name']:<40} | {tmpl['kcal']:>6} | "
              f"{tmpl['protein_g']:>5} | {tmpl['carbs_g']:>5} | {tmpl['fat_g']:>5}")
    print(f"{'─' * 72}")

    # Build aliases
    aliases = qr._build_template_aliases()
    print(f"\n{'─' * 72}")
    print(f"Alias map: {len(aliases)} entries")
    print(f"{'─' * 72}")

    # Group by ambiguity
    certain = {k: v for k, v in aliases.items() if len(v) == 1}
    ambiguous = {k: v for k, v in aliases.items() if len(v) > 1}

    # Name lookup
    name_by_id = {t["id"]: t["name"] for t in _SEED_WITH_IDS}

    if certain:
        print(f"\nCertain aliases ({len(certain)}):")
        for key in sorted(certain.keys()):
            tid = certain[key][0]
            name = name_by_id.get(tid, "?")
            print(f"  {key:<45} → [ID={tid}] {name}")

    if ambiguous:
        print(f"\n⚠  AMBIGUOUS ALIASES ({len(ambiguous)}):")
        for key in sorted(ambiguous.keys()):
            tids = ambiguous[key]
            names = "; ".join(f"{name_by_id.get(tid, '?')} (ID={tid})" for tid in tids)
            print(f"  {key:<45} → {len(tids)} matches: {names}")

    # Summary
    print(f"\n{'─' * 72}")
    print(f"Summary:")
    print(f"  Total aliases:    {len(aliases)}")
    print(f"  Certain:          {len(certain)}")
    print(f"  Ambiguous:        {len(ambiguous)}")
    ambiguous_tids = set()
    for tids in ambiguous.values():
        ambiguous_tids.update(tids)
    print(f"  Templates with ambiguous alias: {len(ambiguous_tids)}")
    if ambiguous_tids:
        for tid in sorted(ambiguous_tids):
            print(f"    - ID={tid} {name_by_id.get(tid, '?')}")

    # Test specific known queries
    print(f"\n{'─' * 72}")
    print("Known query resolution tests:")
    print(f"{'─' * 72}")
    test_queries = [
        "dieta od Brokuła",
        "co to jest dieta od Brokuła w mojej bazie?",
        "Brokuł",
        "Brokuł sport 2000",
        "Białko owsiane",
        "Białko",
        "wiejski HP",
        "nieznany posiłek XYZ",
    ]
    for q in test_queries:
        result = qr._alias_match_template(q)
        if result is None:
            print(f"  {q:<50} → NO MATCH")
        elif result.get("ambiguous"):
            tids = [c["template_id"] for c in result.get("candidates", [])]
            names = [c["template_name"] for c in result.get("candidates", [])]
            print(f"  {q:<50} → AMBIGUOUS: {tids} {names}")
        else:
            print(f"  {q:<50} → MATCH: ID={result['template_id']} {result['template_name']}")


if __name__ == "__main__":
    main()
