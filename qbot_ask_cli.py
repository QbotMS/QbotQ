#!/usr/bin/env python3
"""qbot ask — unified decision CLI / operator workflow.

Uses existing:
- qbot_query_router.query() for read queries + action_draft + planning_fact_drafts
- qbot_capabilities.CAPABILITIES for capability registry
- qbot_nutrition_db.meal_log_create / daily_summary_compute for nutrition writes
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Allowed action types ────────────────────────────────────────────────

ALLOWED_ACTION_TYPES = {"nutrition_log_add"}


# ── Safety check ─────────────────────────────────────────────────────────

def evaluate_action_safety(action_draft: dict) -> dict:
    """Evaluate whether an action_draft is safe to execute.

    Returns:
        dict with safe_to_execute, reason, missing_fields, action_type, writer_capability
    """
    if not action_draft:
        return {
            "safe_to_execute": False,
            "reason": "No action draft provided.",
            "missing_fields": [],
            "action_type": None,
            "writer_capability": None,
        }

    action_type = action_draft.get("action_type", "")
    writer_cap = action_draft.get("writer_capability", "")
    payload = action_draft.get("payload", {}) or {}
    idem_key = action_draft.get("idempotency_key", "")

    if action_type not in ALLOWED_ACTION_TYPES:
        return {
            "safe_to_execute": False,
            "reason": f"Action type '{action_type}' is not in the allowlist.",
            "missing_fields": [],
            "action_type": action_type,
            "writer_capability": writer_cap,
        }

    required: list[str] = []
    if action_type == "nutrition_log_add":
        required = ["date", "kcal_total"]
        if not payload.get("meal_name") and not payload.get("raw_text"):
            required.append("meal_name_or_raw_text")

    missing = [f for f in required if not payload.get(f)]

    if not idem_key:
        missing.append("idempotency_key")

    requires_confirm = action_draft.get("requires_confirm", True)

    if missing:
        return {
            "safe_to_execute": False,
            "reason": "Missing required fields.",
            "missing_fields": missing,
            "action_type": action_type,
            "writer_capability": writer_cap,
        }

    if requires_confirm is not False:
        return {
            "safe_to_execute": True,
            "reason": "All required fields present, action is safe to execute.",
            "missing_fields": [],
            "action_type": action_type,
            "writer_capability": writer_cap,
        }

    return {
        "safe_to_execute": False,
        "reason": "requires_confirm is False — skipping.",
        "missing_fields": [],
        "action_type": action_type,
        "writer_capability": writer_cap,
    }


# ── Execution ────────────────────────────────────────────────────────────

def _exec_nutrition_log(payload: dict, idem_key: str) -> dict:
    from qbot_nutrition_db import meal_log_create, daily_summary_compute

    day = payload.get("date") or __import__("datetime").date.today().isoformat()
    meal_name = payload.get("meal_name") or payload.get("raw_text", "").strip() or "posiłek"
    kcal = payload.get("kcal_total") or 0
    prot = payload.get("protein_g") or 0
    carbs = payload.get("carbs_g") or 0
    fat = payload.get("fat_g") or 0
    fiber = payload.get("fiber_g")
    sodium = payload.get("sodium_mg")
    source = payload.get("source", "manual")
    conf = payload.get("confidence", "medium")

    context = json.dumps({"source": source, "confidence": conf, "idempotency_key": idem_key}, ensure_ascii=False)
    item = {
        "food_name": meal_name,
        "amount": 1,
        "unit": "porcja",
        "kcal": kcal,
        "carbs_g": carbs,
        "protein_g": prot,
        "fat_g": fat,
    }
    if fiber is not None:
        item["fiber_g"] = fiber
    if sodium is not None:
        item["sodium_mg"] = sodium

    meal = meal_log_create(
        meal_type="meal",
        note=meal_name,
        context=context,
        eaten_at=f"{day}T12:00:00",
        items=[item],
    )

    summary = daily_summary_compute(day)

    return {
        "status": "ok",
        "record": {"id": meal.get("id"), "meal_name": meal_name, "kcal": kcal, "date": day},
        "summary": summary,
    }


def execute_action(action_draft: dict) -> dict:
    """Execute an action_draft. Returns execution result dict."""
    action_type = action_draft.get("action_type", "")
    payload = action_draft.get("payload", {}) or {}
    idem_key = action_draft.get("idempotency_key", "")

    if action_type == "nutrition_log_add":
        return _exec_nutrition_log(payload, idem_key)
    else:
        return {"status": "error", "error": f"Unknown action_type: {action_type}"}


# ── Query ────────────────────────────────────────────────────────────────

def run_query(question: str) -> dict:
    """Run qbot query and return the result with safeguards."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qbot_query_router import query
    result = query(question=question, mode='read_only', scope='all')
    return result


# ── Ambiguity detection ─────────────────────────────────────────────────

def detect_ambiguity(question: str, result: dict) -> str | None:
    """Detect if the query is ambiguous. Returns None if OK, or an explanation."""
    intents = result.get("intents_detected", [])
    action_draft = result.get("action_draft")
    answer = (result.get("answer") or "").strip()

    if action_draft:
        safety = evaluate_action_safety(action_draft)
        if not safety["safe_to_execute"]:
            missing = safety.get("missing_fields", [])
            if missing:
                hints = []
                action_type = action_draft.get("action_type", "")
                if "kcal_total" in missing and "meal_name_or_raw_text" in missing:
                    hints.append("Jaka porcja / kcal / makra?")
                if "date" in missing:
                    hints.append("Na kiedy?")
                if "title" in missing:
                    hints.append("Jaki tytuł?")
                if "meal_name_or_raw_text" in missing:
                    hints.append("Co dokładnie zapisać (nazwa posiłku lub opis)?")
                if "idempotency_key" in missing:
                    hints.append("Brak klucza idempotency — wygeneruję automatycznie.")
                if hints:
                    return " | ".join(hints)
    return None


# ── Formatting ───────────────────────────────────────────────────────────

def _fmt_safety(safety: dict) -> str:
    lines = [f"  safe_to_execute={safety['safe_to_execute']}"]
    if safety.get("reason"):
        lines.append(f"  reason: {safety['reason']}")
    if safety.get("missing_fields"):
        lines.append(f"  missing_fields: {', '.join(safety['missing_fields'])}")
    if safety.get("action_type"):
        lines.append(f"  action_type: {safety['action_type']}")
    if safety.get("writer_capability"):
        lines.append(f"  writer_capability: {safety['writer_capability']}")
    return "\n".join(lines)


def format_default(result: dict, action_draft: dict | None, pf_drafts: list[dict],
                   safety: dict | None) -> str:
    parts = []
    ans = (result.get("answer") or "").strip()
    if ans:
        parts.append(ans)
    if action_draft:
        ad = action_draft
        parts.append(f"\n[DRAFT] {ad.get('action_type','?')}")
        parts.append(f"  idempotency_key: {ad.get('idempotency_key','?')}")
        parts.append(f"  Do wykonania użyj --yes albo potwierdź przez kanał.")
    if pf_drafts:
        parts.append(f"\n[PLANNING] Wykryto {len(pf_drafts)} fakt(y/ów) planistycznych:")
        for d in pf_drafts:
            parts.append(f"  - {d.get('title','?')} ({d.get('confidence','?')})")
        parts.append(f"  Planning facts nie są zapisywane przez ask --yes w tym etapie.")
    if safety and not safety.get("safe_to_execute"):
        parts.append(f"\n[SAFETY] Bezpieczeństwo: NIE — {safety.get('reason','?')}")
    return "\n".join(parts)


def format_dry_run(result: dict, action_draft: dict | None, pf_drafts: list[dict],
                   safety: dict | None) -> str:
    parts = []
    ans = (result.get("answer") or "").strip()
    if ans:
        parts.append(ans)
    if action_draft:
        ad = action_draft
        parts.append(f"\n[DRY-RUN] action_draft:")
        parts.append(f"  action_type: {ad.get('action_type','?')}")
        parts.append(f"  writer_capability: {ad.get('writer_capability','?')}")
        parts.append(f"  idempotency_key: {ad.get('idempotency_key','?')}")
        payload = ad.get("payload", {}) or {}
        for k, v in payload.items():
            parts.append(f"  {k}: {v!r}")
        if safety:
            parts.append(f"\n[SAFETY]")
            parts.append(_fmt_safety(safety))
            if safety.get("safe_to_execute"):
                parts.append(f"\n  Do wykonania: qbot ask ... --yes")
            else:
                parts.append(f"\n  Nie można wykonać.")
    if pf_drafts:
        parts.append(f"\n[PLANNING] {len(pf_drafts)} fakt(y/ów):")
        for d in pf_drafts:
            parts.append(f"  - {d.get('title','?')} ({d.get('confidence','?')})")
    return "\n".join(parts)


def format_explain(result: dict, action_draft: dict | None, pf_drafts: list[dict],
                   safety: dict | None, ambiguity: str | None) -> str:
    parts = []
    parts.append("=== qbot ask explain ===")
    intents = result.get("intents_detected", [])
    parts.append(f"intents/domains: {intents}")
    parts.append(f"answer: {(result.get('answer') or '')[:200]}")
    if action_draft:
        ad = action_draft
        parts.append(f"\naction_type: {ad.get('action_type','?')}")
        parts.append(f"writer_capability: {ad.get('writer_capability','?')}")
        parts.append(f"idempotency_key: {ad.get('idempotency_key','?')}")
        payload = ad.get("payload", {}) or {}
        for k, v in payload.items():
            parts.append(f"  {k}: {v!r}")
        if safety:
            parts.append(f"\nsafety:")
            parts.append(_fmt_safety(safety))
    else:
        parts.append(f"\naction_draft: brak")
    if pf_drafts:
        parts.append(f"\nplanning_fact_drafts: {len(pf_drafts)} fact(s)")
        for d in pf_drafts:
            parts.append(f"  {d.get('fact_type','?')}: {d.get('title','?')} ({d.get('confidence','?')})")
            fj = d.get("fact_json", {})
            if fj:
                parts.append(f"    {json.dumps(fj, ensure_ascii=False)}")
        parts.append(f"\n  Planning facts nie są zapisywane przez ask --yes w tym etapie.")
    if ambiguity:
        parts.append(f"\nambiguity: {ambiguity}")
    return "\n".join(parts)


def build_json(result: dict, action_draft: dict | None, pf_drafts: list[dict],
               safety: dict | None, execution_result: dict | None,
               ambiguity: str | None) -> dict:
    j = {
        "answer": result.get("answer", ""),
        "status": result.get("status"),
        "intents_detected": result.get("intents_detected"),
        "action_draft": action_draft,
        "planning_fact_drafts": pf_drafts,
        "safety": safety,
        "execution_result": execution_result,
        "ambiguity": ambiguity,
    }
    return j


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="qbot ask — unified decision CLI / operator workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Tryby:\n"
            "  domyślny: pokazuje odpowiedź + drafty (jeśli istnieją), nie zapisuje\n"
            "  --dry-run: pokazuje co zostałoby wykonane, nie zapisuje\n"
            "  --yes: wykonuje tylko jednoznaczny action_draft z allowlisty\n"
            "  --explain: szczegółowe informacje o intencji, safety, draftach\n"
            "  --json: zwraca JSON\n"
        ),
    )
    parser.add_argument("text", nargs="+", help="Zapytanie")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż, nie zapisuj")
    parser.add_argument("--yes", action="store_true", help="Wykonaj action_draft jeśli bezpieczny")
    parser.add_argument("--explain", action="store_true", help="Szczegółowe info")
    parser.add_argument("--json", action="store_true", help="Wyjście JSON")

    args = parser.parse_args()
    question = " ".join(args.text).strip()

    # ── Run query ──
    result = run_query(question)
    action_draft = result.get("action_draft")
    pf_drafts = result.get("planning_fact_drafts", [])

    # ── Safety check ──
    safety = evaluate_action_safety(action_draft) if action_draft else None

    # ── Ambiguity ──
    ambiguity = detect_ambiguity(question, result)

    # ── Execution (--yes only) ──
    execution_result = None
    if args.yes and action_draft and safety and safety["safe_to_execute"]:
        from qbot_nutrition_db import _conn as nut_conn
        idem_key = action_draft.get("idempotency_key", "")
        # Check idempotency
        try:
            c = nut_conn()
            cur = c.cursor()
            cur.execute("SELECT 1 FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
            if cur.fetchone():
                print(f"[IDEMPOTENCY] Key '{idem_key}' already used — duplicate, skipping.")
                c.close()
                execution_result = {"status": "duplicate", "error": "idempotency_key already used"}
                action_draft = None
            else:
                c.close()
        except Exception:
            pass
        if action_draft:
            execution_result = execute_action(action_draft)
            # Audit
            try:
                c2 = nut_conn()
                cur2 = c2.cursor()
                cur2.execute(
                    "INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (idem_key, execution_result.get("record", {}).get("id"), result.get("date_resolution", {}).get("date", ""),
                     "ask_cli", question, json.dumps(action_draft.get("payload", {}), default=str),
                     json.dumps(execution_result, default=str)),
                )
                c2.commit()
                c2.close()
            except Exception:
                pass
            action_draft = None  # mark as consumed
    elif args.yes:
        if not action_draft:
            print("No action draft to execute. Read-only query.")
            return 0
        if safety and not safety["safe_to_execute"]:
            print(f"Cannot execute: {safety['reason']}")
            if safety.get("missing_fields"):
                print(f"Missing: {', '.join(safety['missing_fields'])}")
            return 1

    # ── Output ──
    if args.json:
        j = build_json(result, action_draft, pf_drafts, safety, execution_result, ambiguity)
        print(json.dumps(j, indent=2, ensure_ascii=False, default=str))
    elif args.explain:
        print(format_explain(result, action_draft, pf_drafts, safety, ambiguity))
    elif args.dry_run:
        print(format_dry_run(result, action_draft, pf_drafts, safety))
    elif args.yes and execution_result:
        rec = execution_result.get("record", {})
        print(f"✓ Wykonano: {rec}")
        summary = execution_result.get("summary", {})
        if summary:
            kcal = summary.get("kcal_total", 0)
            prot = summary.get("protein_total", 0)
            carbs = summary.get("carbs_total", 0)
            fat = summary.get("fat_total", 0)
            print(f"  Dzienny bilans: kcal={kcal:.0f} B={prot:.0f}g W={carbs:.0f}g T={fat:.0f}g")
    else:
        print(format_default(result, action_draft, pf_drafts, safety))

    return 0


if __name__ == "__main__":
    sys.exit(main())
