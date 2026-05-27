#!/usr/bin/env python3
"""QCal CLI — Calendar Events, Reminders, Dispatcher, Rules."""

import argparse, json, os, sys
from datetime import date, datetime, timedelta

sys.path.insert(0, "/opt/qbot/app")


def _rd(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in ("today","dzisiaj","dziś"): return date.today().isoformat()
    if raw in ("tomorrow","jutro"): return (date.today() + timedelta(days=1)).isoformat()
    if raw in ("yesterday","wczoraj"): return (date.today() - timedelta(days=1)).isoformat()
    m = re.search(r"^\+(\d+)d$", raw, re.I); 
    if m: return (date.today() + timedelta(days=int(m.group(1)))).isoformat()
    try: date.fromisoformat(raw); return raw
    except ValueError: return date.today().isoformat()

import re


def _db():
    import psycopg; from psycopg.rows import dict_row
    return psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)


# ── Events ──

def cmd_event_add(args):
    c = _db(); cur = c.cursor()
    cur.execute("""INSERT INTO calendar_events (date_start,date_end,time_start,event_type,title,description,status,source,affects_training,affects_nutrition) VALUES (%s,%s,%s,%s,%s,%s,'planned','manual',%s,%s) RETURNING id""",
        (_rd(args.date), _rd(args.date_end) if args.date_end else None, args.time or None, args.type, args.title, args.description, args.affects_training, args.affects_nutrition))
    eid = cur.fetchone()["id"]; c.commit(); c.close()
    print(f"✓ Event id={eid} — {args.title} ({_rd(args.date)})"); return 0

def cmd_event_list(args):
    c = _db(); cur = c.cursor()
    df = _rd(args.date_from) if args.date_from else date.today().isoformat()
    dt = _rd(args.date_to) if args.date_to else (date.today() + timedelta(days=7)).isoformat()
    cur.execute("SELECT * FROM calendar_events WHERE date_start BETWEEN %s AND %s ORDER BY date_start, time_start", (df, dt))
    rows = cur.fetchall(); c.close()
    if not rows: print("No events."); return 0
    print(f"Events ({len(rows)}):")
    for r in rows:
        t = r.get("time_start","") or ""; ts = str(t)[:5] if t else ""
        print(f"  [{r['id']}] {r['date_start']} {ts} {r['event_type']}: {r['title']} ({r['status']})")
    return 0

def cmd_event_show(args):
    c = _db(); cur = c.cursor(); cur.execute("SELECT * FROM calendar_events WHERE id=%s",(args.id,)); r = cur.fetchone(); c.close()
    if not r: print("Not found."); return 1
    print(json.dumps(dict(r), indent=2, ensure_ascii=False, default=str)); return 0

def cmd_event_cancel(args):
    c = _db(); cur = c.cursor(); cur.execute("UPDATE calendar_events SET status='cancelled', updated_at=now() WHERE id=%s",(args.id,)); c.commit(); c.close()
    print(f"✓ Event {args.id} cancelled."); return 0

def cmd_event_delete(args):
    c = _db(); cur = c.cursor();
    if not args.yes:
        r = input(f"Delete event {args.id}? [t/N] ").strip().lower()
        if r not in ("t","y"): print("Cancelled."); c.close(); return 0
    cur.execute("DELETE FROM calendar_events WHERE id=%s",(args.id,)); c.commit(); c.close()
    print(f"✓ Event {args.id} deleted."); return 0


# ── Reminders ──

def cmd_reminder_add(args):
    c = _db(); cur = c.cursor()
    due = None
    if args.time:
        try: due = f"{_rd(args.date)} {args.time}:00+02:00"
        except: pass
    cur.execute("""INSERT INTO reminders (date,time,timezone,title,message,reminder_type,status,priority,recurrence_rule,channel,requires_confirmation,metadata_json,due_at)
        VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s::timestamptz) RETURNING id""",
        (_rd(args.date), args.time or None, "Europe/Warsaw", args.title, args.message or "", args.type or "custom", args.priority or "normal", args.recurrence or None, args.channel or "cli", args.requires_confirmation or False, None, due))
    rid = cur.fetchone()["id"]; c.commit(); c.close()
    print(f"✓ Reminder id={rid} — {args.title} on {_rd(args.date)} {args.time or ''}"); return 0

def cmd_reminder_list(args):
    c = _db(); cur = c.cursor()
    if args.date_from and args.date_to:
        cur.execute("SELECT * FROM reminders WHERE date BETWEEN %s AND %s ORDER BY date,time", (_rd(args.date_from), _rd(args.date_to)))
    elif args.date:
        cur.execute("SELECT * FROM reminders WHERE date=%s ORDER BY time", (_rd(args.date),))
    else:
        cur.execute("SELECT * FROM reminders ORDER BY date,time LIMIT 50")
    rows = cur.fetchall(); c.close()
    if not rows: print("No reminders."); return 0
    print(f"Reminders ({len(rows)}):")
    for r in rows:
        t = str(r.get("time","") or "")[:5]
        print(f"  [{r['id']}] {r['date']} {t} {r['reminder_type']}: {r['title']} ({r['status']})")
    return 0

def cmd_reminder_done(args):
    c = _db(); cur = c.cursor()
    cur.execute("UPDATE reminders SET status='done', sent_at=now(), updated_at=now() WHERE id=%s",(args.id,)); c.commit(); c.close()
    print(f"✓ Reminder {args.id} → done"); return 0

def cmd_reminder_cancel(args):
    c = _db(); cur = c.cursor()
    cur.execute("UPDATE reminders SET status='cancelled', updated_at=now() WHERE id=%s",(args.id,)); c.commit(); c.close()
    print(f"✓ Reminder {args.id} cancelled."); return 0

def cmd_reminder_snooze(args):
    c = _db(); cur = c.cursor()
    until = datetime.now() + timedelta(minutes=args.minutes)
    cur.execute("UPDATE reminders SET status='snoozed', snoozed_until=%s, updated_at=now() WHERE id=%s",(until, args.id)); c.commit(); c.close()
    print(f"✓ Reminder {args.id} snoozed until {until.strftime('%H:%M')}"); return 0


# ── Dispatcher ──

def cmd_reminders_dispatch(args):
    c = _db(); cur = c.cursor()
    now = datetime.now()
    cur.execute("""SELECT * FROM reminders WHERE status='pending' AND (due_at IS NULL OR due_at <= %s) AND (send_after IS NULL OR send_after <= %s) ORDER BY priority DESC, due_at""",
        (now, now))
    pending = cur.fetchall()
    cur.execute("SELECT channel, enabled FROM reminder_channels WHERE enabled=true")
    channels = {r["channel"] for r in cur.fetchall()}
    c.close()

    if not pending: print("No pending reminders."); return 0

    sent, skipped = 0, 0
    for r in pending:
        ch = r.get("channel","cli")
        if ch not in channels:
            skipped += 1; continue

        title = r.get("title","?")
        msg = r.get("message") or title

        if args.dry_run:
            print(f"[DRY-RUN] Would send: {title} via {ch} — {msg[:80]}")
            sent += 1
        else:
            try:
                if ch == "telegram":
                    from qbot_qcal_telegram import send_message
                    send_message(msg)
                else:
                    print(f"[CLI] {r['date']} {r.get('time','')} {title}: {msg}")
                # Log
                c2 = _db(); cur2 = c2.cursor()
                cur2.execute("INSERT INTO reminder_delivery_log (reminder_id, channel, status) VALUES (%s,%s,'sent')",(r["id"],ch))
                cur2.execute("UPDATE reminders SET status='sent', sent_at=now(), updated_at=now() WHERE id=%s",(r["id"],))
                c2.commit(); c2.close()
                sent += 1
            except Exception as e:
                c2 = _db(); cur2 = c2.cursor()
                cur2.execute("INSERT INTO reminder_delivery_log (reminder_id, channel, status, error) VALUES (%s,%s,'failed',%s)",(r["id"],ch,str(e)[:200]))
                c2.commit(); c2.close()
                skipped += 1
                print(f"  FAILED: {title} — {e}")

    if args.dry_run:
        print(f"\n[Dry-run] Would send {sent}, skip {skipped}.")
    else:
        print(f"Sent {sent}, skipped {skipped}.")
    return 0


# ── Rules ──

def cmd_rules_list(args):
    c = _db(); cur = c.cursor()
    cur.execute("SELECT * FROM reminder_rules ORDER BY id")
    rows = cur.fetchall(); c.close()
    if not rows: print("No rules."); return 0
    for r in rows:
        print(f"  [{r['id']}] {r['name']} ({r['rule_type']}) enabled={r['enabled']}")
    return 0

def cmd_rules_enable(args):
    c = _db(); cur = c.cursor(); v = not args.disable
    cur.execute("UPDATE reminder_rules SET enabled=%s, updated_at=now() WHERE id=%s",(v, args.id)); c.commit(); c.close()
    print(f"✓ Rule {args.id} → enabled={v}"); return 0

def cmd_rules_run(args):
    """Run enabled rules, generate reminder drafts."""
    c = _db(); cur = c.cursor()
    cur.execute("SELECT * FROM reminder_rules WHERE enabled=true")
    rules = cur.fetchall(); c.close()

    drafts = 0
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")

    for rule in rules:
        rtype = rule["rule_type"]
        if rtype == "missing_nutrition" and now >= "21:00":
            try:
                c2 = _db(); cur2 = c2.cursor()
                cur2.execute("SELECT kcal_total FROM nutrition_daily_summary WHERE date=%s",(today,))
                nut = cur2.fetchone(); c2.close()
                if not nut or (nut.get("kcal_total",0) or 0) < 100:
                    msg = "Brak wpisanego żywienia za dziś. Uzupełnić?"
                    action = rule.get("action_json",{})
                    if isinstance(action, str): action = json.loads(action)
                    ch = action.get("channel","cli")
                    if not args.dry_run:
                        c3 = _db(); cur3 = c3.cursor()
                        cur3.execute("""INSERT INTO reminders (date,title,message,reminder_type,status,priority,channel) VALUES (%s,%s,%s,'missing_nutrition','pending','normal',%s) RETURNING id""",
                            (today, "Missing nutrition", msg, ch))
                        c3.commit(); c3.close()
                    print(f"[{'DRY-RUN' if args.dry_run else 'CREATED'}] {msg}")
                    drafts += 1
            except: pass

    if not drafts: print("No rule drafts generated.")
    else: print(f"\nTotal: {drafts} drafts.")
    return 0


# ── Synced events (Intervals) ──

def cmd_sync_intervals(args):
    try:
        import httpx, base64, os as _os
        api_key = _os.getenv("INTERVALS_API_KEY","")
        athlete_id = _os.getenv("INTERVALS_ATHLETE_ID","")
        if not api_key or not athlete_id:
            print("Intervals credentials not configured."); return 1
        auth = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
        df = _rd(args.date_from)
        dt = _rd(args.date_to)
        resp = httpx.get(f"https://intervals.icu/api/v1/athlete/{athlete_id}/events",
            headers={"Authorization": f"Basic {auth}"}, params={"oldest": df, "newest": dt}, timeout=15)
        if resp.status_code != 200:
            print(f"API error: {resp.status_code}"); return 1
        events = resp.json()
        print(f"Intervals events ({len(events)}):")
        imported = 0
        for ev in events[:10]:
            title = ev.get("name", ev.get("title","?"))[:60]
            eid = ev.get("id","?")
            start = ev.get("start", "")[:10]
            etype = ev.get("type","planned_training")
            print(f"  {start} [{etype}] {title}")
            if not args.dry_run:
                r = execute_safe_sql
                try:
                    c = _db(); cur = c.cursor()
                    cur.execute("""INSERT INTO calendar_events (date_start,event_type,title,source,external_ref,external_source,sync_status)
                        VALUES (%s,%s,%s,'intervals',%s,'intervals','imported')
                        ON CONFLICT DO NOTHING""", (start, etype, title, str(eid)))
                    c.commit(); c.close()
                    imported += 1
                except: pass
        if args.dry_run:
            print(f"\n[Dry-run] Would import {len(events)} events from Intervals.")
        else:
            print(f"\nImported {imported} events.")
    except Exception as e:
        print(f"Error: {e}")
    return 0


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="QCal CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ea = sub.add_parser("event-add")
    ea.add_argument("--date", required=True); ea.add_argument("--date-end"); ea.add_argument("--time"); ea.add_argument("--type", default="note"); ea.add_argument("--title", required=True); ea.add_argument("--description"); ea.add_argument("--affects-training", dest="affects_training", action="store_true"); ea.add_argument("--affects-nutrition", dest="affects_nutrition", action="store_true"); ea.add_argument("--yes", action="store_true")

    el = sub.add_parser("event-list"); el.add_argument("--date-from"); el.add_argument("--date-to"); el.add_argument("--from", dest="date_from"); el.add_argument("--to", dest="date_to")
    sub.add_parser("event-show").add_argument("--id", type=int, required=True)
    ec = sub.add_parser("event-cancel"); ec.add_argument("--id", type=int, required=True); ec.add_argument("--yes", action="store_true")
    ed = sub.add_parser("event-delete"); ed.add_argument("--id", type=int, required=True); ed.add_argument("--yes", action="store_true")

    ra = sub.add_parser("reminder-add")
    ra.add_argument("--date", required=True); ra.add_argument("--time"); ra.add_argument("--type", default="custom"); ra.add_argument("--title", required=True); ra.add_argument("--message"); ra.add_argument("--channel", default="cli"); ra.add_argument("--priority", default="normal"); ra.add_argument("--recurrence"); ra.add_argument("--requires-confirmation", action="store_true"); ra.add_argument("--yes", action="store_true")

    rl = sub.add_parser("reminder-list"); rl.add_argument("--date"); rl.add_argument("--date-from"); rl.add_argument("--date-to"); rl.add_argument("--from", dest="date_from"); rl.add_argument("--to", dest="date_to")
    rd = sub.add_parser("reminder-done"); rd.add_argument("--id", type=int, required=True); rd.add_argument("--yes", action="store_true")
    rc = sub.add_parser("reminder-cancel"); rc.add_argument("--id", type=int, required=True); rc.add_argument("--yes", action="store_true")
    rs = sub.add_parser("reminder-snooze"); rs.add_argument("--id", type=int, required=True); rs.add_argument("--minutes", type=int, default=30); rs.add_argument("--yes", action="store_true")

    dd = sub.add_parser("reminders-dispatch"); dd.add_argument("--dry-run", action="store_true"); dd.add_argument("--yes", action="store_true")
    sub.add_parser("rules-list")
    re = sub.add_parser("rules-enable"); re.add_argument("--id", type=int, required=True); re.add_argument("--disable", action="store_true"); re.add_argument("--yes", action="store_true")
    rr = sub.add_parser("rules-run"); rr.add_argument("--dry-run", action="store_true"); rr.add_argument("--yes", action="store_true")

    si = sub.add_parser("sync-intervals"); si.add_argument("--date-from"); si.add_argument("--date-to"); si.add_argument("--dry-run", action="store_true"); si.add_argument("--yes", action="store_true")

    args = parser.parse_args()
    cmds = {
        "event-add": lambda: cmd_event_add(args), "event-list": lambda: cmd_event_list(args),
        "event-show": lambda: cmd_event_show(args), "event-cancel": lambda: cmd_event_cancel(args),
        "event-delete": lambda: cmd_event_delete(args),
        "reminder-add": lambda: cmd_reminder_add(args), "reminder-list": lambda: cmd_reminder_list(args),
        "reminder-done": lambda: cmd_reminder_done(args), "reminder-cancel": lambda: cmd_reminder_cancel(args),
        "reminder-snooze": lambda: cmd_reminder_snooze(args),
        "reminders-dispatch": lambda: cmd_reminders_dispatch(args),
        "rules-list": lambda: cmd_rules_list(args), "rules-enable": lambda: cmd_rules_enable(args),
        "rules-run": lambda: cmd_rules_run(args), "sync-intervals": lambda: cmd_sync_intervals(args),
    }
    fn = cmds.get(args.cmd)
    return fn() if fn else (parser.print_help(), 1)[1]


if __name__ == "__main__":
    sys.exit(main())
