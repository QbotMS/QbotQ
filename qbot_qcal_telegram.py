#!/usr/bin/env python3
"""QBot Telegram Conversational Gateway — qbot.query + context memory + confirm flow."""

import hashlib, json, os, sys, re
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, "/opt/qbot/app")

# ── Auth ──

def _token() -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _allowed() -> set[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or ""
    return {s.strip() for s in raw.split(",") if s.strip()}

def is_authorized(chat_id: str) -> bool:
    return str(chat_id).strip() in _allowed()
# ── Telegram API ──

def send_message(chat_id: str, text: str) -> dict:
    token = _token()
    if not token: return {"ok": False, "error": "no token"}
    import httpx
    r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4096], "parse_mode": "Markdown"}, timeout=10)
    try: return r.json()
    except: return {"ok": False, "error": r.text[:100]}

def status() -> dict:
    token = _token(); allowed = _allowed()
    configured = bool(token and allowed)
    try:
        import httpx; me = {}
        if token: me = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5).json().get("result", {})
    except: me = {}
    return {"configured": configured, "bot_name": me.get("first_name","?"), "bot_username": me.get("username","?"), "allowed_chats": len(allowed)}

def poll_once() -> list[dict]:
    token = _token()
    if not token: return []
    import httpx
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 10, "timeout": 5}, timeout=10)
    return r.json().get("result",[]) if r.status_code == 200 else []


# ── DB helpers ──

def _db():
    import psycopg; from psycopg.rows import dict_row
    return psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)

def _conv_get(chat_id: str) -> dict | None:
    try:
        c = _db(); cur = c.cursor()
        cur.execute("SELECT * FROM telegram_conversations WHERE chat_id=%s", (str(chat_id),))
        r = cur.fetchone(); c.close()
        return dict(r) if r else None
    except: return None

def _conv_upsert(chat_id: str, **fields):
    try:
        c = _db(); cur = c.cursor()
        conv = _conv_get(chat_id)
        if conv:
            sets = ", ".join(f"{k}=%s" for k in fields)
            vals = list(fields.values()) + [chat_id]
            cur.execute(f"UPDATE telegram_conversations SET {sets}, updated_at=now() WHERE chat_id=%s", vals)
        else:
            fields["chat_id"] = chat_id
            keys = ", ".join(fields.keys()); placeholders = ", ".join(["%s"]*len(fields))
            cur.execute(f"INSERT INTO telegram_conversations ({keys}) VALUES ({placeholders})", list(fields.values()))
        c.commit(); c.close()
    except: pass

def _turn_add(chat_id: str, direction: str, text: str = "", intent: str = "", response_json: dict = None):
    try:
        c = _db(); cur = c.cursor()
        cur.execute("INSERT INTO telegram_conversation_turns (chat_id, direction, message_text, intent, qbot_response_json) VALUES (%s,%s,%s,%s,%s)",
            (str(chat_id), direction, text[:1000], intent, json.dumps(response_json, default=str) if response_json else None))
        c.commit(); c.close()
    except: pass

def _pending_create(chat_id: str, action_type: str, payload: dict, preview: str, idem_key: str = "") -> int | None:
    try:
        c = _db(); cur = c.cursor()
        expires = datetime.now() + timedelta(minutes=15)
        cur.execute("""INSERT INTO telegram_pending_actions (chat_id, action_type, status, payload_json, preview_text, idempotency_key, expires_at)
            VALUES (%s,%s,'pending',%s,%s,%s,%s) RETURNING id""",
            (str(chat_id), action_type, json.dumps(payload, default=str), preview, idem_key, expires))
        pid = cur.fetchone()["id"]; c.commit(); c.close()
        _conv_upsert(chat_id, state="awaiting_confirmation", pending_action_id=pid)
        return pid
    except Exception as e: return None

def _pending_execute(chat_id: str, action_id: int, dry_run: bool = False) -> dict:
    try:
        c = _db(); cur = c.cursor()
        cur.execute("SELECT * FROM telegram_pending_actions WHERE id=%s AND chat_id=%s AND status='pending'", (action_id, str(chat_id)))
        pa = cur.fetchone()
        if not pa: c.close(); return {"status":"not_found"}
        if pa["expires_at"] and pa["expires_at"] < datetime.now():
            cur.execute("UPDATE telegram_pending_actions SET status='expired', updated_at=now() WHERE id=%s",(action_id,))
            c.commit(); c.close(); _conv_upsert(chat_id, state="idle", pending_action_id=None)
            return {"status":"expired"}

        atype = pa["action_type"]
        payload = pa["payload_json"] if isinstance(pa["payload_json"], dict) else json.loads(pa["payload_json"]) if pa["payload_json"] else {}

        if dry_run:
            cur.execute("UPDATE telegram_pending_actions SET status='executed', updated_at=now() WHERE id=%s",(action_id,))
            c.commit(); c.close()
            return {"status":"dry_run_only", "action_type": atype, "payload_fields": list(payload.keys())}

        # Execute the writer
        result = _execute_writer(atype, payload, pa.get("idempotency_key",""))
        cur.execute("UPDATE telegram_pending_actions SET status=%s, updated_at=now() WHERE id=%s", ("executed" if result.get("status") in ("OK","ok") else "failed", action_id))
        c.commit(); c.close()
        _conv_upsert(chat_id, state="idle", pending_action_id=None)
        return result
    except Exception as e: return {"status":"error","error":str(e)[:200]}

def _pending_decline(chat_id: str, action_id: int) -> dict:
    try:
        c = _db(); cur = c.cursor()
        cur.execute("UPDATE telegram_pending_actions SET status='declined', updated_at=now() WHERE id=%s AND chat_id=%s AND status='pending'", (action_id, str(chat_id)))
        c.commit(); c.close()
        _conv_upsert(chat_id, state="idle", pending_action_id=None)
        return {"status":"declined"}
    except: return {"status":"error"}

def _execute_writer(atype: str, payload: dict, idem_key: str) -> dict:
    """Execute a local writer — same as MCP handlers."""
    try:
        if atype == "nutrition_log_add":
            from qbot_mcp_adapter import _handle_nutrition_add
            return _handle_nutrition_add({**payload, "idempotency_key": idem_key, "confirm": True})
        elif atype == "qcal_reminder_add":
            from qbot_mcp_adapter import _handle_qcal_reminder_add
            return _handle_qcal_reminder_add({**payload, "idempotency_key": idem_key, "confirm": True})
        elif atype == "qcal_reminder_done":
            from qbot_mcp_adapter import _handle_qcal_reminder_done
            return _handle_qcal_reminder_done({**payload, "confirm": True})
        elif atype == "qcal_reminder_cancel":
            from qbot_mcp_adapter import _handle_qcal_reminder_cancel
            return _handle_qcal_reminder_cancel({**payload, "confirm": True})
        elif atype == "qcal_event_add":
            from qbot_mcp_adapter import _handle_qcal_event_add
            return _handle_qcal_event_add({**payload, "idempotency_key": idem_key, "confirm": True})
        elif atype == "qcal_event_cancel":
            from qbot_mcp_adapter import _handle_qcal_event_cancel
            return _handle_qcal_event_cancel({**payload, "confirm": True})
        return {"status": "unknown_action_type", "action_type": atype}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── Main handler ──

def _parse_followup_dates(text: str):
    """Parse 'od 4 maja do 26' → ('2026-05-04','2026-05-26')."""
    from datetime import date as dt_date
    today = dt_date.today()
    months = {"stycznia":1,"lutego":2,"marca":3,"kwietnia":4,"maja":5,"czerwca":6,
              "lipca":7,"sierpnia":8,"września":9,"października":10,"listopada":11,"grudnia":12}
    m = re.search(r"od\s+(\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)\s+do\s+(\d{1,2})", text)
    if m:
        day1, mon, day2 = int(m.group(1)), m.group(2), int(m.group(3))
        mo = months.get(mon, today.month)
        return f"{today.year}-{mo:02d}-{day1:02d}", f"{today.year}-{mo:02d}-{day2:02d}"
    m = re.search(r"od\s+(\d{4}-\d{2}-\d{2})\s+do\s+(\d{4}-\d{2}-\d{2})", text)
    if m: return m.group(1), m.group(2)
    m = re.search(r"od\s+(\d{4}-\d{2}-\d{2})", text)
    if m: return m.group(1), None
    return None, None


def handle_message(chat_id: str, text: str, dry_run: bool = True) -> dict:
    """Route Telegram message through qbot.query + context memory + confirm flow."""
    if not is_authorized(str(chat_id)):
        _turn_add(chat_id, "system", text="[unauthorized]", intent="unauthorized")
        return {"response": "Unauthorized. No data returned.", "authorized": False, "status": "blocked"}

    conv = _conv_get(chat_id)
    tl = text.strip().lower()
    state = (conv or {}).get("state", "idle")
    pending_id = (conv or {}).get("pending_action_id")

    # ── Confirmation commands ──
    if tl in ("tak","yes","ok","potwierdzam","zapisz","dodaj","confirm","/confirm","/yes"):
        if pending_id:
            if dry_run:
                _turn_add(chat_id, "inbound", text, intent="confirm_dryrun")
                pa_info = ""
                try:
                    c2 = _db(); cur2 = c2.cursor()
                    cur2.execute("SELECT action_type, preview_text FROM telegram_pending_actions WHERE id=%s",(pending_id,))
                    pa = cur2.fetchone()
                    if pa: pa_info = f" (akcja: {pa.get('action_type','?')} — {pa.get('preview_text','')[:100]})"
                    c2.close()
                except: pass
                msg = f"[DRY-RUN] Pending action nie została wykonana — tryb dry-run.{pa_info} Uruchom bez --dry-run aby zapisać."
                _turn_add(chat_id, "outbound", text=msg, intent="confirm_dryrun_result")
                return {"response": msg, "status": "ok", "dry_run": True}
            result = _pending_execute(chat_id, pending_id, dry_run=False)
            _turn_add(chat_id, "inbound", text, intent="confirm")
            st = result.get("status","?")
            msg = "✓ Wykonano." if st in ("OK","ok") else f"Błąd: {result.get('error',result.get('status','?'))}"
            _turn_add(chat_id, "outbound", text=msg, intent="confirm_result")
            return {"response": msg, "status": "ok", "executed": True, "action_result": result}
        else:
            return {"response": "Brak pending action do potwierdzenia.", "status": "idle"}

    if tl in ("nie","no","anuluj","cancel","/cancel","/no"):
        if pending_id:
            _pending_decline(chat_id, pending_id)
            _turn_add(chat_id, "inbound", text, intent="decline")
            msg = "Anulowano."
            _turn_add(chat_id, "outbound", text=msg, intent="decline_result")
            return {"response": msg, "status": "ok"}

    # ── Simple slash commands ──
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd == "/today": return _today_response(chat_id)
        if cmd == "/reminders": return _reminders_response(chat_id)
        if cmd in ("/help","/start"): return {"response": "QBot Telegram:\n/today /reminders /status\nPisz naturalnie np. 'pokaż bilans za ostatnie 7 dni'"}
        if cmd == "/status":
            return {"response": f"QBot v1 — {date.today().isoformat()}"}

    # ── Natural language via qbot.query ──
    context = {}
    if conv:
        ctx = conv.get("context_json") or {}
        if isinstance(ctx, str):
            try: ctx = json.loads(ctx)
            except: ctx = {}
        if conv.get("last_intent"): context["last_intent"] = conv["last_intent"]
        for k in ("last_date_from","last_date_to","last_domains"):
            if ctx.get(k): context[k] = ctx[k]

    # ── Follow-up detection ──
    # If user types a short message with date references and there's a prior intent,
    # reconstruct the query with prior intent + new date range.
    prior_intent = (conv or {}).get("last_intent","")
    prior_ctx = (conv or {}).get("context_json") or {}
    if isinstance(prior_ctx, str):
        try: prior_ctx = json.loads(prior_ctx)
        except: prior_ctx = {}

    is_followup = (
        tl and len(tl) < 60 and not tl.startswith("/") and
        prior_intent and re.search(r"^\s*a\s+|^\s*od\s+\d|^\s*dla\s+dat|^\s*zmien.*zakres|^\s*pokaż\s+ten\s+sam", tl)
    )
    if is_followup:
        # Extract date range from the follow-up text and build a proper range query
        date_text = tl
        # Try to extract "od X do Y" pattern and construct proper ISO dates
        df_val, dt_val = _parse_followup_dates(date_text)
        if df_val and prior_ctx.get("last_query"):
            prior_query = prior_ctx["last_query"]
            # Replace date part or construct new query
            m = re.search(r"(od\s+\d{4}-\d{2}-\d{2}|ostatn\S+\s+\d+\s+\S+)", prior_query)
            if m:
                new_date = f"od {df_val} do {dt_val}" if dt_val else f"od {df_val}"
                text = prior_query[:m.start()] + new_date + prior_query[m.end():]
            else:
                text = f"{prior_query} od {df_val}" + (f" do {dt_val}" if dt_val else "")

    try:
        from qbot_query_router import query as qbot_query
        result = qbot_query(question=text, mode="read_only", scope="all", context=json.dumps(context))

        intent = result.get("intents_detected",[])
        answer = result.get("answer","")
        tables = result.get("tables",[])

        # Detect if user's intent suggests a write action
        write_hint = _detect_write_intent(tl, answer, result)

        if write_hint:
            preview = write_hint.get("preview","")
            idem = hashlib.sha256(f"{chat_id}|{write_hint.get('action_type')}|{datetime.now().isoformat()}".encode()).hexdigest()[:16]
            if not dry_run:
                pid = _pending_create(chat_id, write_hint["action_type"], write_hint.get("payload",{}), preview, idem)
                response = f"{preview}\nPotwierdzić? Odpowiedz: tak / nie."
                _turn_add(chat_id, "inbound", text, intent="write_draft")
                _turn_add(chat_id, "outbound", text=response, intent="write_draft")
            else:
                # In dry-run, still create a dummy pending action for testing
                pid = _pending_create(chat_id, write_hint["action_type"], write_hint.get("payload",{}), preview, idem)
                response = _format_answer(answer, tables)
                response += f"\n\n[DRY-RUN] Proponowana akcja: {preview}\nPending action utworzona (test). 'tak' pokaże co zostało zrobione, ale nic nie zapisze."
                _turn_add(chat_id, "inbound", text, intent="write_draft")
                _turn_add(chat_id, "outbound", text=response, intent="write_draft")
        else:
            response = _format_answer(answer, tables)
            _turn_add(chat_id, "inbound", text, intent=str(intent)[:100])
            _turn_add(chat_id, "outbound", text=response, intent="query_response")

        _conv_upsert(chat_id, state="idle" if not write_hint else "awaiting_confirmation",
                     last_intent=str(intent)[:100],
                     last_response_summary=answer[:300],
                     context_json=json.dumps({
                         "last_date_from": result.get("date_resolution",{}).get("date_from",""),
                         "last_date_to": result.get("date_resolution",{}).get("date_to",""),
                         "last_domains": intent,
                         "last_query": text,
                     }))

        return {"response": response, "status": "ok", "read_only": True, "intents": intent}
    except Exception as e:
        return {"response": f"Błąd: {str(e)[:200]}", "status": "error"}


def _detect_write_intent(tl: str, answer: str, result: dict) -> dict | None:
    """Detect if user wants to write/create/set/cancel."""
    intents = result.get("intents_detected",[])
    if re.search(r"przypomnij\s+mi|dodaj\s+(przypomnienie|wydarzenie|event|posiłek|do\s+j)|zapisz|stwórz|utwórz", tl):
        if re.search(r"przypomnij|przypomnienie", tl):
            return {"action_type": "qcal_reminder_add", "preview": "Przygotowano draft przypomnienia.", "payload": {}}
        if re.search(r"posiłek|jedzenie|spożycie|dodaj do", tl):
            return {"action_type": "nutrition_log_add", "preview": "Przygotowano draft posiłku.", "payload": {}}
    if re.search(r"oznacz\s+(przypomnienie|reminder).*jako\s+(zrobione|done)", tl):
        m = re.search(r"(\d+)", tl)
        rid = int(m.group(1)) if m else 0
        return {"action_type": "qcal_reminder_done", "preview": f"Oznaczyć reminder {rid} jako done?", "payload": {"reminder_id": rid}}
    if re.search(r"(odwołaj|anuluj|usuń|skasuj)\s+(przypomnienie|reminder|wydarzenie|event)", tl):
        return {"action_type": "qcal_reminder_cancel", "preview": "Anulować?", "payload": {}}
    return None


def _format_answer(answer: str, tables: list) -> str:
    lines = [answer.strip()]
    for t in tables:
        rows = t.get("rows",[])
        if rows:
            cols = [col for col in (t.get("columns",[]) or list(rows[0].keys()))]
            max_rows = 8
            if cols:
                header = " | ".join(cols[:7])
                lines.append("\n" + header[:100])
            for r in rows[:max_rows]:
                vals = []
                for col in cols[:7]:
                    v = r.get(col)
                    if isinstance(v, list): v = ",".join(str(x)[:8] for x in v[:2])
                    if isinstance(v, str) and len(v) > 20: v = v[:18] + ".."
                    if isinstance(v, float): v = f"{v:.0f}" if abs(v) > 10 else f"{v:.1f}"
                    vals.append(str(v or "")[:14])
                lines.append(" | ".join(vals))
            if len(rows) > max_rows:
                lines.append(f"... +{len(rows)-max_rows} więcej wierszy")
    return "\n".join(lines)[:3800]


def _today_response(chat_id: str) -> dict:
    try:
        from qbot_query_router import query
        r = query(question="Pokaż wszystko co QBot wie o dzisiejszym dniu", mode="read_only", scope="all")
        return {"response": _format_answer(r.get("answer",""), r.get("tables",[])), "status": "ok"}
    except: return {"response": f"Today: {date.today().isoformat()}", "status": "ok"}

def _reminders_response(chat_id: str) -> dict:
    try:
        c = _db(); cur = c.cursor()
        cur.execute("SELECT id, title, reminder_type, time, status FROM reminders WHERE date=%s AND status='pending' ORDER BY time", (date.today().isoformat(),))
        rows = cur.fetchall(); c.close()
        if not rows: return {"response": "Brak przypomnień na dziś.", "status": "ok"}
        lines = [f"Przypomnienia ({len(rows)}):"]
        for r in rows:
            t = str(r.get("time","") or "")[:5]
            lines.append(f"[{r['id']}] {t} {r['title']} ({r['reminder_type']})")
        return {"response": "\n".join(lines), "status": "ok"}
    except: return {"response": "Nie można sprawdzić przypomnień.", "status": "error"}


# ── CLI entry points ──

def handle_update(update: dict, dry_run: bool = True) -> dict:
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")
    return handle_message(chat_id, text, dry_run=dry_run)


def handle_text_cmd(args):
    """CLI handler for handle-text command."""
    import argparse
    chat_id = args.get("chat_id","")
    text = args.get("text","")
    dry = args.get("dry_run", True)
    r = handle_message(chat_id, text, dry_run=dry)
    print(r.get("response","?"))
