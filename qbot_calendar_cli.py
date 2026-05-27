#!/usr/bin/env python3
"""QBot Calendar CLI — day, event, reminder, snapshot, import-history."""

import argparse
import json
import sys
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")


def _rd(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in ("today", "dzisiaj", "dziś"): return date.today().isoformat()
    if raw in ("yesterday", "wczoraj"): return (date.today() - timedelta(days=1)).isoformat()
    try: date.fromisoformat(raw); return raw
    except ValueError: return date.today().isoformat()


# ── Commands ──

def cmd_day_show(args):
    from qbot_calendar_core import get_snapshot, build_snapshot
    d = _rd(args.date)
    snap = get_snapshot(d) if not args.rebuild else None
    if not snap:
        snap = build_snapshot(d)
    if args.json:
        print(json.dumps(snap, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Day: {d}")
        cs = snap.get("completeness_score") or snap.get("_completeness_score") or 0
        print(f"  completeness: {cs*100:.0f}%")
        for section in ["nutrition", "meals", "training", "sleep", "health_events",
                        "health_risk_notes", "supplements", "goals", "calendar_events",
                        "reminders", "nutrition_plans"]:
            val = snap.get(section)
            if isinstance(val, list):
                print(f"  {section}: {len(val)} entries")
            elif isinstance(val, dict):
                print(f"  {section}: available")
            elif val is None:
                pass
        if snap.get("_missing_tables"):
            print(f"  missing_tables: {', '.join(snap['_missing_tables'][:8])}")
    return 0


def cmd_day_rebuild(args):
    from qbot_calendar_core import rebuild_range, build_snapshot
    if args.date_from and args.date_to:
        r = rebuild_range(_rd(args.date_from), _rd(args.date_to))
        print(f"Rebuilt {r['rebuilt']} days ({r['range']})")
        if r.get("errors"):
            for e in r["errors"]:
                print(f"  ERROR: {e}")
    else:
        build_snapshot(_rd(args.date))
        print(f"Snapshot rebuilt for {_rd(args.date)}")
    return 0


def cmd_day_list(args):
    from qbot_calendar_core import day_list, get_snapshot
    days = day_list(_rd(args.date_from), _rd(args.date_to or date.today().isoformat()))
    for d in days:
        snap = get_snapshot(d["date"])
        score = snap["completeness_score"] if snap else 0
        print(f"  {d['date']} type={d.get('day_type','?')} completeness={score*100:.0f}%")
    return 0


def cmd_event_add(args):
    from qbot_calendar_core import event_create
    ev = event_create(date_start=_rd(args.date_start), title=args.title,
                      event_type=args.event_type, description=args.description,
                      affects_training=args.affects_training,
                      affects_nutrition=args.affects_nutrition,
                      affects_health=args.affects_health)
    print(f"✓ Event: id={ev['id']} — {ev['title']}")
    return 0


def cmd_event_list(args):
    from qbot_calendar_core import event_list
    events = event_list(date_from=_rd(args.date_from) if args.date_from else None,
                        date_to=_rd(args.date_to) if args.date_to else None)
    if not events: print("No events."); return 0
    for ev in events:
        print(f"  [{ev['id']}] {ev['date_start']} {ev['event_type']}: {ev['title']} ({ev['status']})")
    return 0


def cmd_event_show(args):
    from qbot_calendar_core import event_get
    ev = event_get(args.id)
    if not ev: print("Not found."); return 1
    print(json.dumps(ev, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_event_delete(args):
    from qbot_calendar_core import event_delete
    if not args.yes:
        r = input(f"Delete event {args.id}? [t/N] ").strip().lower()
        if r not in ("t","y"): print("Cancelled."); return 0
    event_delete(args.id); print(f"✓ Event {args.id} deleted."); return 0


def cmd_reminder_add(args):
    from qbot_calendar_core import reminder_create
    r = reminder_create(date_str=_rd(args.date), title=args.title,
                        time_str=args.time, reminder_type=args.reminder_type,
                        message=args.message, channel=args.channel)
    print(f"✓ Reminder: id={r['id']} — {r['title']} {r['date']} {r.get('time','')}")
    return 0


def cmd_reminder_list(args):
    from qbot_calendar_core import reminder_list
    items = reminder_list(date_str=_rd(args.date) if args.date else None)
    if not items: print("No reminders."); return 0
    for r in items:
        print(f"  [{r['id']}] {r['date']} {r.get('time','')} {r['reminder_type']}: {r['title']} ({r['status']})")
    return 0


def cmd_reminder_done(args):
    from qbot_calendar_core import reminder_update_status
    reminder_update_status(args.id, "done"); print(f"✓ Reminder {args.id} → done"); return 0


def cmd_reminder_cancel(args):
    from qbot_calendar_core import reminder_update_status
    reminder_update_status(args.id, "cancelled"); print(f"✓ Reminder {args.id} → cancelled"); return 0


def cmd_import_history(args):
    from qbot_calendar_core import import_history_audit
    result = import_history_audit(source=args.source, date_from=_rd(args.date_from),
                                  date_to=_rd(args.date_to or date.today().isoformat()))
    print(f"Import audit: source={result['source']} range={result['date_from']} → {result['date_to']}")
    for t, info in sorted(result["tables"].items()):
        if info.get("exists"):
            in_range = info.get("rows_in_range")
            in_range_s = f" (in range: {in_range})" if in_range is not None else ""
            print(f"  ✓ {t}: {info['total_rows']} rows{in_range_s}")
        else:
            print(f"  ✗ {t}: MISSING")
    print(f"\n{result.get('note','')}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="QBot Calendar CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ds = sub.add_parser("day-show")
    ds.add_argument("--date", default=date.today().isoformat())
    ds.add_argument("--json", action="store_true")
    ds.add_argument("--rebuild", action="store_true")

    dr = sub.add_parser("day-rebuild")
    dr.add_argument("--date", default=date.today().isoformat())
    dr.add_argument("--date-from", dest="date_from")
    dr.add_argument("--date-to", dest="date_to")

    dl = sub.add_parser("day-list")
    dl.add_argument("--date-from", required=True)
    dl.add_argument("--date-to")

    ea = sub.add_parser("event-add")
    ea.add_argument("--date-start", required=True)
    ea.add_argument("--title", required=True)
    ea.add_argument("--type", dest="event_type", default="note")
    ea.add_argument("--description")
    ea.add_argument("--affects-training", dest="affects_training", action="store_true")
    ea.add_argument("--affects-nutrition", dest="affects_nutrition", action="store_true")
    ea.add_argument("--affects-health", dest="affects_health", action="store_true")
    ea.add_argument("--yes", action="store_true")

    el = sub.add_parser("event-list")
    el.add_argument("--from", dest="date_from")
    el.add_argument("--to", dest="date_to")

    es = sub.add_parser("event-show"); es.add_argument("--id", type=int, required=True)

    ed = sub.add_parser("event-delete")
    ed.add_argument("--id", type=int, required=True); ed.add_argument("--yes", action="store_true")

    ra = sub.add_parser("reminder-add")
    ra.add_argument("--date", required=True); ra.add_argument("--title", required=True)
    ra.add_argument("--time"); ra.add_argument("--type", dest="reminder_type", default="custom")
    ra.add_argument("--message"); ra.add_argument("--channel", default="cli")
    ra.add_argument("--yes", action="store_true")

    rl = sub.add_parser("reminder-list"); rl.add_argument("--date")

    rd2 = sub.add_parser("reminder-done")
    rd2.add_argument("--id", type=int, required=True); rd2.add_argument("--yes", action="store_true")

    rc = sub.add_parser("reminder-cancel")
    rc.add_argument("--id", type=int, required=True); rc.add_argument("--yes", action="store_true")

    ih = sub.add_parser("import-history")
    ih.add_argument("--source", default="all")
    ih.add_argument("--date-from", default="2025-01-01")
    ih.add_argument("--date-to")

    args = parser.parse_args()
    cmds = {
        "day-show": lambda: cmd_day_show(args), "day-rebuild": lambda: cmd_day_rebuild(args),
        "day-list": lambda: cmd_day_list(args),
        "event-add": lambda: cmd_event_add(args), "event-list": lambda: cmd_event_list(args),
        "event-show": lambda: cmd_event_show(args), "event-delete": lambda: cmd_event_delete(args),
        "reminder-add": lambda: cmd_reminder_add(args), "reminder-list": lambda: cmd_reminder_list(args),
        "reminder-done": lambda: cmd_reminder_done(args), "reminder-cancel": lambda: cmd_reminder_cancel(args),
        "import-history": lambda: cmd_import_history(args),
    }
    fn = cmds.get(args.cmd)
    if fn: return fn()
    parser.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
