#!/usr/bin/env python3
"""QBot Planning Memory CLI — detect, add, list, reconcile planning facts."""
import argparse, json, os, sys
from datetime import date

sys.path.insert(0, "/opt/qbot/app")


def _rd(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in ("today", "dzisiaj", "dziś"):
        return date.today().isoformat()
    if raw in ("tomorrow", "jutro"):
        return (date.today() + timedelta(days=1)).isoformat()
    from datetime import timedelta
    try:
        return date.fromisoformat(raw).isoformat()
    except (ValueError, TypeError):
        return date.today().isoformat()


def cmd_detect(args):
    from qbot_planning_memory import detect_planning_facts
    drafts = detect_planning_facts(args.text)
    if not drafts:
        print("Nie wykryto faktów planistycznych.")
        return
    print(f"Wykryto {len(drafts)} faktów planistycznych:")
    for d in drafts:
        print(f"  type={d['fact_type']} date={d['date']} title={d['title']}")
        print(f"    confidence={d['confidence']}")
        print(f"    fact_json={json.dumps(d.get('fact_json',{}), ensure_ascii=False, default=str)}")
    print()
    print("(nie zapisano – dodaj --yes aby zapisać)")


def cmd_add(args):
    from qbot_planning_memory import save_planning_fact
    fd = _rd(args.date)
    fjson = {}
    if args.json:
        try:
            fjson = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(f"Błąd parsowania --json: {e}")
            return 1
    draft = {
        "fact_type": args.type,
        "date": fd,
        "title": args.title,
        "confidence": args.confidence,
        "fact_json": fjson,
    }
    if args.valid_until:
        draft["valid_until"] = args.valid_until

    result = save_planning_fact(draft, channel="cli", confirm=args.yes)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


def cmd_list(args):
    from qbot_planning_memory import list_planning_facts
    fd = _rd(args.date) if args.date else None
    facts = list_planning_facts(fact_date=fd, status=args.status)
    if not facts:
        print("Brak faktów planistycznych.")
        return
    print(f"Znaleziono {len(facts)} faktów planistycznych:")
    for f in facts:
        fj = f.get("fact_json", {})
        if isinstance(fj, str):
            try:
                fj = json.loads(fj)
            except (json.JSONDecodeError, TypeError):
                fj = {}
        fj_preview = json.dumps(fj, ensure_ascii=False, default=str)[:200] if fj else "{}"
        print(f"  [{f['id']}] {f['date']} | {f['fact_type']:30s} | {f['status']:15s} | {f['title'][:50]}")
        print(f"        confidence={f['confidence']} json={fj_preview}")


def cmd_reconcile(args):
    from qbot_planning_memory import reconcile_plans
    fd = _rd(args.date)
    results = reconcile_plans(fd, dry_run=args.dry_run)
    print(f"Reconciliacja dla {fd}:")
    for r in results:
        print(f"  type={r.get('reconciliation_type','?')}")
        print(f"  summary={r.get('summary','')}")
        details = r.get("details_json", {})
        if details:
            print(f"  details={json.dumps(details, ensure_ascii=False, default=str)}")
        print()


def main():
    parser = argparse.ArgumentParser(description="QBot Planning Memory CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    det = sub.add_parser("detect")
    det.add_argument("text", nargs="?", default="", help="Query text to analyze")
    det.add_argument("--text", dest="text_alt", help="Alternative text input")

    add = sub.add_parser("add")
    add.add_argument("--date", default="today")
    add.add_argument("--type", required=True, help="fact_type: planned_training, rest_day, nutrition_plan_assumption, custom")
    add.add_argument("--title", required=True)
    add.add_argument("--json", default="{}", help="JSON fact payload")
    add.add_argument("--confidence", default="medium", choices=["low", "medium", "high"])
    add.add_argument("--valid-until")
    add.add_argument("--yes", action="store_true", help="Confirm save")

    lst = sub.add_parser("list")
    lst.add_argument("--date")
    lst.add_argument("--status")

    rec = sub.add_parser("reconcile")
    rec.add_argument("--date", default="today")
    rec.add_argument("--dry-run", action="store_true", default=True)
    rec.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    args = parser.parse_args()

    if args.cmd == "detect":
        text = args.text or args.text_alt or ""
        if not text:
            print("Podaj tekst do analizy.")
            return 1
        cmd_detect(args)
    elif args.cmd == "add":
        return cmd_add(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "reconcile":
        cmd_reconcile(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
