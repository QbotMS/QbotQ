#!/usr/bin/env python3
"""QBot Health CLI — goals, supplements, protocols, advisor."""

import argparse
import json
import sys
from datetime import date

sys.path.insert(0, "/opt/qbot/app")


def _rd(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in ("today", "dzisiaj", "dziś"):
        return date.today().isoformat()
    if raw in ("yesterday", "wczoraj"):
        from datetime import timedelta
        return (date.today() - timedelta(days=1)).isoformat()
    try:
        date.fromisoformat(raw)
        return raw
    except ValueError:
        return date.today().isoformat()


def cmd_goal_set(args: argparse.Namespace) -> int:
    from qbot_health_db import goal_create
    g = goal_create(name=args.goal_name, goal_type=args.goal_type,
                    target_weight=args.target_weight, target_date=args.target_date,
                    next_target_weight=args.next_target_weight,
                    next_target_date=args.next_target_date,
                    priority=args.priority, notes=args.notes)
    print(f"✓ Goal created: id={g['id']} — {g['goal_name']}")
    return 0


def cmd_goal_show(args: argparse.Namespace) -> int:
    from qbot_health_db import goal_list, goal_get
    goals = goal_get(args.id) if args.id else goal_list()
    if not goals:
        print("No goals."); return 0
    if isinstance(goals, dict):
        goals = [goals]
    for g in goals:
        print(f"  [{g['id']}] {g['goal_name']} ({g['goal_type']}) status={g['status']}")
        if g.get("target_weight_kg"):
            print(f"    target: {g['target_weight_kg']} kg by {g.get('target_date','?')}")
        if g.get("next_target_weight_kg"):
            print(f"    next: {g['next_target_weight_kg']} kg by {g.get('next_target_date','?')}")
    return 0


def cmd_goal_delete(args: argparse.Namespace) -> int:
    from qbot_health_db import goal_delete
    if not args.yes:
        r = input(f"Delete goal id={args.id}? [t/N] ").strip().lower()
        if r not in ("t", "y", "yes", "tak"):
            print("Cancelled."); return 0
    goal_delete(args.id)
    print(f"✓ Goal {args.id} deleted.")
    return 0


def cmd_supplement_add(args: argparse.Namespace) -> int:
    from qbot_health_db import supp_create
    s = supp_create(name=args.name, brand=args.brand, form=args.form,
                    dose_per_unit=args.dose_per_unit, dose_unit=args.dose_unit,
                    units_total=args.units_total, units_remaining=args.units_remaining,
                    purchase_date=_rd(args.purchase_date) if args.purchase_date else None,
                    expiry_date=_rd(args.expiry_date) if args.expiry_date else None,
                    notes=args.notes)
    print(f"✓ Supplement: id={s['id']} — {s['name']} ({s['units_remaining']}/{s['units_total']} {s['form']})")
    return 0


def cmd_supplement_list(args: argparse.Namespace) -> int:
    from qbot_health_db import supp_list
    items = supp_list()
    if not items:
        print("No supplements."); return 0
    print(f"Supplements ({len(items)}):")
    for s in items:
        print(f"  [{s['id']}] {s['name']} — {s.get('units_remaining','?')}/{s.get('units_total','?')} "
              f"{s.get('form','?')} (status={s['status']})")
    return 0


def cmd_supplement_update(args: argparse.Namespace) -> int:
    from qbot_health_db import supp_update
    supp_update(args.id, units_remaining=args.units_remaining)
    print(f"✓ Supplement {args.id} updated: {args.units_remaining} remaining.")
    return 0


def cmd_supplement_delete(args: argparse.Namespace) -> int:
    from qbot_health_db import supp_delete
    if not args.yes:
        r = input(f"Delete supplement {args.id}? [t/N] ").strip().lower()
        if r not in ("t","y","yes","tak"): print("Cancelled."); return 0
    supp_delete(args.id)
    print(f"✓ Supplement {args.id} deleted.")
    return 0


def cmd_protocol_add(args: argparse.Namespace) -> int:
    from qbot_health_db import prot_create
    p = prot_create(supplement_name=args.supplement_name, dose=args.dose, dose_unit=args.dose_unit,
                    frequency=args.frequency, timing=args.timing,
                    goal=args.goal, start_date=_rd(args.start_date) if args.start_date else None,
                    notes=args.notes)
    print(f"✓ Protocol: id={p['id']} — {p['supplement_name']} {p['dose']}{p['dose_unit']} {p['frequency']}")
    return 0


def cmd_protocol_list(args: argparse.Namespace) -> int:
    from qbot_health_db import prot_list
    items = prot_list()
    if not items:
        print("No protocols."); return 0
    print(f"Protocols ({len(items)}):")
    for p in items:
        print(f"  [{p['id']}] {p['supplement_name']} — {p['dose']}{p['dose_unit']} "
              f"{p['frequency']} {p['timing']} (goal={p.get('goal','?')} status={p['status']})")
    return 0


def cmd_protocol_pause_stop(args: argparse.Namespace, status: str) -> int:
    from qbot_health_db import prot_update_status
    prot_update_status(args.id, status)
    print(f"✓ Protocol {args.id} → {status}.")
    return 0


def cmd_supplement_taken(args: argparse.Namespace) -> int:
    from qbot_health_db import intake_log
    day = _rd(args.date or date.today().isoformat())
    il = intake_log(supplement_name=args.supplement_name, date_str=day,
                    dose=args.dose, dose_unit=args.dose_unit, taken=not args.not_taken)
    print(f"✓ Logged: {il['supplement_name']} {'taken' if il['taken'] else 'skipped'} on {day}")
    # Update inventory
    try:
        from qbot_health_db import supp_list
        for s in supp_list():
            if s.get("name", "").lower() == args.supplement_name.lower() and s.get("units_remaining"):
                from qbot_health_db import supp_update
                supp_update(s["id"], units_remaining=max(0, s["units_remaining"] - 1))
                break
    except Exception:
        pass
    return 0


def cmd_intake_list(args: argparse.Namespace) -> int:
    from qbot_health_db import intake_list
    day = _rd(args.date) if args.date else None
    items = intake_list(day)
    if not items:
        print("No intake entries."); return 0
    print(f"Intake ({len(items)}):")
    for i in items:
        print(f"  [{i['id']}] {i['date']} {i.get('supplement_name','?')} "
              f"{i.get('dose','')}{i.get('dose_unit','')} {'✓' if i.get('taken') else '✗'}")
    return 0


def cmd_advisor_check(args: argparse.Namespace) -> int:
    from qbot_health_advisor import advisor_check
    r = advisor_check(int(args.period.rstrip("d")))
    print(f"Health Check ({r['date']}, {r['period_days']}d) — confidence={r['confidence']}")
    if r.get("recommendations"):
        print("Recommendations:")
        for rec in r["recommendations"]:
            print(f"  • {rec}")
    if r.get("warnings"):
        print("Warnings:")
        for w in r["warnings"]:
            print(f"  ⚠ {w}")
    if r.get("missing_fields"):
        print(f"Missing: {', '.join(r['missing_fields'][:8])}")
    return 0


def cmd_advisor_weight(args: argparse.Namespace) -> int:
    from qbot_health_advisor import _weight_advice
    r = _weight_advice()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0


def cmd_advisor_supplements(args: argparse.Namespace) -> int:
    from qbot_health_advisor import _supplement_advice, supplement_inventory_report
    inv = supplement_inventory_report()
    adv = _supplement_advice()
    print("=== Inventory ===")
    for i in inv.get("items", []):
        dl = f" (~{i['days_left_est']:.0f}d left)" if i.get('days_left_est') else ""
        print(f"  {i['name']} — {i.get('units_remaining','?')}/{i.get('dose_per_unit','?')}{i.get('dose_unit','?')} "
              f"{i.get('form','?')} {dl}")
    if inv.get("warnings"):
        for w in inv["warnings"]:
            print(f"  ⚠ {w}")
    print("\n=== Advice ===")
    for rec in adv.get("recommendations", []):
        print(f"  • {rec}")
    for w in adv.get("warnings", []):
        print(f"  ⚠ {w}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="QBot Health CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    gs = sub.add_parser("goal-set")
    gs.add_argument("--goal-name", required=True)
    gs.add_argument("--goal-type", default="weight_loss")
    gs.add_argument("--target-weight", type=float)
    gs.add_argument("--target-date")
    gs.add_argument("--next-target-weight", type=float)
    gs.add_argument("--next-target-date")
    gs.add_argument("--priority", default="balanced")
    gs.add_argument("--notes")
    gs.add_argument("--yes", action="store_true")

    sub.add_parser("goal-show")
    sub.add_parser("goal-list")

    gd = sub.add_parser("goal-delete")
    gd.add_argument("--id", type=int, required=True)
    gd.add_argument("--yes", action="store_true")

    sa = sub.add_parser("supplement-add", aliases=["supp-add"])
    sa.add_argument("--name", required=True)
    sa.add_argument("--brand")
    sa.add_argument("--form", default="capsule")
    sa.add_argument("--dose-per-unit", type=float)
    sa.add_argument("--dose-unit", default="mg")
    sa.add_argument("--units-total", type=float)
    sa.add_argument("--units-remaining", type=float)
    sa.add_argument("--purchase-date")
    sa.add_argument("--expiry-date")
    sa.add_argument("--notes")
    sa.add_argument("--yes", action="store_true")

    sub.add_parser("supplement-list", aliases=["supp-list"])

    su = sub.add_parser("supplement-update", aliases=["supp-update"])
    su.add_argument("--id", type=int, required=True)
    su.add_argument("--units-remaining", type=float)

    sd = sub.add_parser("supplement-delete", aliases=["supp-delete"])
    sd.add_argument("--id", type=int, required=True)
    sd.add_argument("--yes", action="store_true")

    pa = sub.add_parser("protocol-add")
    pa.add_argument("--supplement-name", required=True)
    pa.add_argument("--dose", type=float, default=1)
    pa.add_argument("--dose-unit", default="mg")
    pa.add_argument("--frequency", default="daily")
    pa.add_argument("--timing", default="morning")
    pa.add_argument("--goal", default="general_health")
    pa.add_argument("--start-date")
    pa.add_argument("--notes")
    pa.add_argument("--yes", action="store_true")

    sub.add_parser("protocol-list")

    pp = sub.add_parser("protocol-pause")
    pp.add_argument("--id", type=int, required=True)
    pp.add_argument("--yes", action="store_true")

    ps2 = sub.add_parser("protocol-stop")
    ps2.add_argument("--id", type=int, required=True)
    ps2.add_argument("--yes", action="store_true")

    st = sub.add_parser("supplement-taken")
    st.add_argument("--supplement-name", required=True)
    st.add_argument("--dose", type=float, default=1)
    st.add_argument("--dose-unit", default="mg")
    st.add_argument("--date", default=date.today().isoformat())
    st.add_argument("--not-taken", action="store_true")
    st.add_argument("--yes", action="store_true")

    si = sub.add_parser("supplement-intake-list")
    si.add_argument("--date")

    ac = sub.add_parser("advisor-check")
    ac.add_argument("--period", default="14d")

    sub.add_parser("advisor-weight")
    sub.add_parser("advisor-supplements", aliases=["supplements-status"])

    # ── Event commands ──
    ea = sub.add_parser("event-add")
    ea.add_argument("--type", dest="event_type", default="illness")
    ea.add_argument("--title", required=True)
    ea.add_argument("--date-start", default=date.today().isoformat())
    ea.add_argument("--date-end")
    ea.add_argument("--severity", default="mild", choices=["low","mild","moderate","high","severe"])
    ea.add_argument("--symptoms")
    ea.add_argument("--description")
    ea.add_argument("--affects-training", dest="affects_training", type=lambda x: x.lower() == "true", default=True)
    ea.add_argument("--affects-nutrition", dest="affects_nutrition", type=lambda x: x.lower() == "true", default=True)
    ea.add_argument("--yes", action="store_true")

    el = sub.add_parser("event-list")
    el.add_argument("--status", default="active")
    el.add_argument("--from", dest="date_from")
    el.add_argument("--to", dest="date_to")

    es = sub.add_parser("event-show")
    es.add_argument("--id", type=int, required=True)

    er = sub.add_parser("event-resolve")
    er.add_argument("--id", type=int, required=True)
    er.add_argument("--date-end", default=date.today().isoformat())
    er.add_argument("--yes", action="store_true")

    ed = sub.add_parser("event-delete")
    ed.add_argument("--id", type=int, required=True)
    ed.add_argument("--yes", action="store_true")

    # ── Risk commands ──
    ra = sub.add_parser("risk-add")
    ra.add_argument("--title", required=True)
    ra.add_argument("--risk-type", default="other")
    ra.add_argument("--description")
    ra.add_argument("--constraints")
    ra.add_argument("--yes", action="store_true")

    sub.add_parser("risk-list")

    rs = sub.add_parser("risk-show")
    rs.add_argument("--id", type=int, required=True)

    ru = sub.add_parser("risk-update")
    ru.add_argument("--id", type=int, required=True)
    ru.add_argument("--status", required=True)
    ru.add_argument("--yes", action="store_true")

    rd = sub.add_parser("risk-delete")
    rd.add_argument("--id", type=int, required=True)
    rd.add_argument("--yes", action="store_true")

    sub.add_parser("advisor-recovery")

    args = parser.parse_args()

    cmd_map = {
        "goal-set": lambda: cmd_goal_set(args),
        "goal-show": lambda: cmd_goal_show(argparse.Namespace(id=None)),
        "goal-list": lambda: cmd_goal_show(argparse.Namespace(id=None)),
        "goal-delete": lambda: cmd_goal_delete(args),
        "supplement-add": lambda: cmd_supplement_add(args),
        "supp-add": lambda: cmd_supplement_add(args),
        "supplement-list": lambda: cmd_supplement_list(args),
        "supp-list": lambda: cmd_supplement_list(args),
        "supplement-update": lambda: cmd_supplement_update(args),
        "supp-update": lambda: cmd_supplement_update(args),
        "supplement-delete": lambda: cmd_supplement_delete(args),
        "supp-delete": lambda: cmd_supplement_delete(args),
        "protocol-add": lambda: cmd_protocol_add(args),
        "protocol-list": lambda: cmd_protocol_list(args),
        "protocol-pause": lambda: cmd_protocol_pause_stop(args, "paused"),
        "protocol-stop": lambda: cmd_protocol_pause_stop(args, "stopped"),
        "supplement-taken": lambda: cmd_supplement_taken(args),
        "supplement-intake-list": lambda: cmd_intake_list(args),
        "advisor-check": lambda: cmd_advisor_check(args),
        "advisor-weight": lambda: cmd_advisor_weight(args),
        "advisor-supplements": lambda: cmd_advisor_supplements(args),
        "supplements-status": lambda: cmd_advisor_supplements(args),
        "event-add": lambda: cmd_event_add(args),
        "event-list": lambda: cmd_event_list(args),
        "event-show": lambda: cmd_event_show(args),
        "event-resolve": lambda: cmd_event_resolve(args),
        "event-delete": lambda: cmd_event_delete(args),
        "risk-add": lambda: cmd_risk_add(args),
        "risk-list": lambda: cmd_risk_list(args),
        "risk-show": lambda: cmd_risk_show(args),
        "risk-update": lambda: cmd_risk_update(args),
        "risk-delete": lambda: cmd_risk_delete(args),
        "advisor-recovery": lambda: cmd_recovery_check(args),
    }

    fn = cmd_map.get(args.cmd)
    if fn:
        return fn()
    parser.print_help()
    return 1


# ── Event / Risk command implementations ─────────────────────────────────────

def cmd_event_add(args: argparse.Namespace) -> int:
    from qbot_health_db import health_event_create
    import json
    symptoms = [s.strip() for s in args.symptoms.split(",") if s.strip()] if args.symptoms else None
    ev = health_event_create(
        date_start=_rd(args.date_start), title=args.title, event_type=args.event_type,
        severity=args.severity, description=args.description,
        date_end=_rd(args.date_end) if args.date_end else None, symptoms=symptoms,
        affects_training=args.affects_training, affects_nutrition=args.affects_nutrition,
    )
    print(f"✓ Event: id={ev['id']} — {ev['title']} ({ev['severity']})")
    return 0


def cmd_event_list(args: argparse.Namespace) -> int:
    from qbot_health_db import health_event_list
    events = health_event_list(status=args.status, date_from=args.date_from, date_to=args.date_to)
    if not events: print("No events."); return 0
    print(f"Events ({len(events)}):")
    for ev in events:
        sym = ev.get("symptoms_json")
        sym_s = ", ".join(sym) if isinstance(sym, list) else str(sym or "")
        print(f"  [{ev['id']}] {ev['date_start']} → {ev.get('date_end','?')} "
              f"{ev['event_type']}: {ev['title']} ({ev['severity']}) status={ev['status']}"
              + (f" — {sym_s}" if sym_s else ""))
    return 0


def cmd_event_show(args: argparse.Namespace) -> int:
    from qbot_health_db import health_event_get
    import json
    ev = health_event_get(args.id)
    if not ev: print("Not found."); return 1
    print(json.dumps(ev, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_event_resolve(args: argparse.Namespace) -> int:
    from qbot_health_db import health_event_resolve
    health_event_resolve(args.id, _rd(args.date_end))
    print(f"✓ Event {args.id} resolved."); return 0


def cmd_event_delete(args: argparse.Namespace) -> int:
    from qbot_health_db import health_event_delete
    if not args.yes:
        r = input(f"Delete event {args.id}? [t/N] ").strip().lower()
        if r not in ("t","y"): print("Cancelled."); return 0
    health_event_delete(args.id)
    print(f"✓ Event {args.id} deleted."); return 0


def cmd_risk_add(args: argparse.Namespace) -> int:
    from qbot_health_db import risk_create
    import json
    constraints = None
    if args.constraints:
        try: constraints = json.loads(args.constraints)
        except Exception: print("ERROR: --constraints must be valid JSON"); return 1
    r = risk_create(title=args.title, risk_type=args.risk_type, description=args.description, constraints=constraints)
    print(f"✓ Risk note: id={r['id']} — {r['title']}"); return 0


def cmd_risk_list(args: argparse.Namespace) -> int:
    from qbot_health_db import risk_list
    risks = risk_list()
    if not risks: print("No risk notes."); return 0
    print(f"Risk notes ({len(risks)}):")
    for r in risks: print(f"  [{r['id']}] {r['title']} ({r['risk_type']}) status={r['status']}")
    return 0


def cmd_risk_show(args: argparse.Namespace) -> int:
    from qbot_health_db import risk_get
    import json
    r = risk_get(args.id)
    if not r: print("Not found."); return 1
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_risk_update(args: argparse.Namespace) -> int:
    from qbot_health_db import risk_update_status
    risk_update_status(args.id, args.status)
    print(f"✓ Risk {args.id} → {args.status}"); return 0


def cmd_risk_delete(args: argparse.Namespace) -> int:
    from qbot_health_db import risk_delete
    if not args.yes:
        r = input(f"Delete risk {args.id}? [t/N] ").strip().lower()
        if r not in ("t","y"): print("Cancelled."); return 0
    risk_delete(args.id)
    print(f"✓ Risk {args.id} deleted."); return 0


def cmd_recovery_check(args: argparse.Namespace) -> int:
    from qbot_health_advisor import recovery_anomaly_check
    r = recovery_anomaly_check()
    print(f"Recovery check — confidence={r['confidence']}")
    if r.get("question"): print(f"  {r['question']}")
    if r.get("missing_fields"): print(f"  Missing: {', '.join(r['missing_fields'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
