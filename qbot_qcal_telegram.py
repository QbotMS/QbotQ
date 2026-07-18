#!/usr/bin/env python3
"""QBot Telegram Conversational Gateway — qbot.query + context memory + confirm flow."""

import hashlib, json, os, sys, re
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, "/opt/qbot/app")

# ── Auth ──

def _token() -> str: return os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
def _allowed() -> set[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or ""
    return {s.strip() for s in raw.split(",") if s.strip()}

def is_authorized(chat_id: str) -> bool:
    return str(chat_id).strip() in _allowed()

_ALLOWED_ACTIONS = {"confirm_route_analysis"}  # kalendarz qcal_* usuniety 2026-07-16; nutrition_log_add usuniete 2026-07-05
_CONFIRM_WORDS = {"tak", "yes", "ok", "potwierdzam", "zapisz", "dodaj", "confirm", "/confirm", "/yes", "t", "y"}
_DECLINE_WORDS = {"nie", "no", "anuluj", "cancel", "/cancel", "/no", "n"}
_CONFIRM_NUMERIC_RE = re.compile(r"^\s*#?\s*(\d+)\s+(.+?)\s*$", re.IGNORECASE)

def _clean_preview(answer: str) -> str:
    for suffix in [
        "\n\nZapis wymaga potwierdzenia przez writer nutrition_log_add.",
        "\n\nZapis wymaga potwierdzenia przez writer qcal_reminder_add.",
        "\n\nZapis wymaga potwierdzenia przez writer qcal_event_add.",
        "\nZapis wymaga potwierdzenia przez writer nutrition_log_add.",
        "\nZapis wymaga potwierdzenia przez writer qcal_reminder_add.",
        "\nZapis wymaga potwierdzenia przez writer qcal_event_add.",
        "\nZapis wymaga potwierdzenia.",
        "\nZapis wymaga potwierdzenia",
    ]:
        if answer.rstrip().endswith(suffix):
            return answer.rstrip()[:-len(suffix)].rstrip()
    return answer.rstrip()


def _telegram_result_text(result: dict) -> str:
    answer = str(result.get("answer", "") or "").strip()
    status = str(result.get("status", "") or "").lower()
    limitations = result.get("limitations", [])
    first_limitation = limitations[0] if isinstance(limitations, list) and limitations else "nieznany błąd"

    if not answer and status == "error":
        return f"⚠️ Albert nie mógł odpowiedzieć: {first_limitation}"
    if not answer:
        return ""
    if status == "draft":
        return answer + "\n\n_(zapis wymaga potwierdzenia — wywołaj qbot.action_execute)_"
    return answer


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _route_confirm_log_path(route_id: str) -> str:
    base_dir = os.getenv("QBOT_ROUTE_CONFIRM_LOG_DIR") or "/opt/qbot/artifacts/logs"
    log_dir = os.path.join(base_dir, "rwgps_confirmations")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"rwgps_precompute_{route_id}_telegram_confirm.log")

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

def _turn_add(chat_id: str, direction: str, text: str = "", intent: str = "", response_json: dict = None, action_id: int | None = None):
    try:
        c = _db(); cur = c.cursor()
        cur.execute(
            """
            INSERT INTO telegram_conversation_turns
                (chat_id, direction, message_text, intent, qbot_response_json, action_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (str(chat_id), direction, text[:1000], intent, json.dumps(response_json, default=str) if response_json else None, action_id),
        )
        row = cur.fetchone()
        c.commit(); c.close()
        return int(row["id"]) if row and row.get("id") is not None else None
    except: pass
    return None


def _pending_active_rows(chat_id: str) -> list[dict[str, Any]]:
    try:
        c = _db(); cur = c.cursor()
        cur.execute(
            """
            SELECT id, chat_id, action_type, status, payload_json, preview_text, idempotency_key, expires_at, created_at, updated_at
            FROM telegram_pending_actions
            WHERE chat_id=%s AND status='pending'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY id ASC
            """,
            (str(chat_id),),
        )
        rows = [dict(row) for row in cur.fetchall()]
        c.close()
        return rows
    except:
        return []


def _pending_get(chat_id: str, action_id: int) -> dict[str, Any] | None:
    try:
        c = _db(); cur = c.cursor()
        cur.execute(
            """
            SELECT id, chat_id, action_type, status, payload_json, preview_text, idempotency_key, expires_at, created_at, updated_at
            FROM telegram_pending_actions
            WHERE id=%s AND chat_id=%s
            LIMIT 1
            """,
            (int(action_id), str(chat_id)),
        )
        row = cur.fetchone()
        c.close()
        return dict(row) if row else None
    except:
        return None


def _refresh_pending_expires_at(chat_id: str, action_id: int, expires_minutes: int = 30) -> dict[str, Any]:
    try:
        c = _db(); cur = c.cursor()
        expires = datetime.now() + timedelta(minutes=expires_minutes)
        cur.execute(
            """
            UPDATE telegram_pending_actions
            SET expires_at=%s,
                status=CASE WHEN status='expired' THEN 'pending' ELSE status END,
                updated_at=now()
            WHERE id=%s AND chat_id=%s AND status IN ('pending', 'expired')
            RETURNING id, expires_at
            """,
            (expires, int(action_id), str(chat_id)),
        )
        row = cur.fetchone()
        c.commit(); c.close()
        if not row:
            return {"status": "not_found"}
        return {"status": "ok", "id": row["id"], "expires_at": row["expires_at"], "expires_minutes": expires_minutes}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def _parse_confirmation_reply(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _CONFIRM_NUMERIC_RE.match(raw)
    if m:
        action_id = int(m.group(1))
        decision_word = m.group(2).strip().split()[0].lower() if m.group(2).strip() else ""
        if decision_word in _CONFIRM_WORDS:
            return {"action_id": action_id, "decision": "yes", "explicit": True}
        if decision_word in _DECLINE_WORDS:
            return {"action_id": action_id, "decision": "no", "explicit": True}
        return {"action_id": action_id, "decision": None, "explicit": True}
    low = raw.lower()
    if low in _CONFIRM_WORDS:
        return {"action_id": None, "decision": "yes", "explicit": False}
    if low in _DECLINE_WORDS:
        return {"action_id": None, "decision": "no", "explicit": False}
    return {"action_id": None, "decision": None, "explicit": False}


def upsert_pending_action(
    *,
    chat_id: str,
    action_type: str,
    payload: dict,
    preview: str,
    idem_key: str = "",
    expires_minutes: int = 15,
) -> dict[str, Any]:
    try:
        c = _db(); cur = c.cursor()
        lock_key = f"{str(chat_id)}:{action_type}:{idem_key}" if idem_key else f"{str(chat_id)}:{action_type}:{preview[:64]}"
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
        if idem_key:
            cur.execute(
                """
                SELECT id, status
                FROM telegram_pending_actions
                WHERE chat_id=%s AND action_type=%s AND idempotency_key=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(chat_id), action_type, idem_key),
            )
            existing = cur.fetchone()
            if existing:
                pid = existing["id"]
                status = existing.get("status", "")
                if status == "pending":
                    _conv_upsert(chat_id, state="awaiting_confirmation", pending_action_id=pid)
                c.commit(); c.close()
                return {"status": "existing", "created": False, "pending_action_id": pid, "action_status": status}

        expires = datetime.now() + timedelta(minutes=expires_minutes)
        cur.execute(
            """INSERT INTO telegram_pending_actions (chat_id, action_type, status, payload_json, preview_text, idempotency_key, expires_at)
            VALUES (%s,%s,'pending',%s,%s,%s,%s) RETURNING id""",
            (str(chat_id), action_type, json.dumps(payload, default=str), preview, idem_key, expires),
        )
        pid = cur.fetchone()["id"]
        _conv_upsert(chat_id, state="awaiting_confirmation", pending_action_id=pid)
        c.commit(); c.close()
        return {"status": "pending", "created": True, "pending_action_id": pid, "action_status": "pending"}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)[:200], "created": False, "pending_action_id": None}

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
    except Exception as e:
        import traceback; traceback.print_exc()
        return None

def _pending_execute(chat_id: str, action_id: int, dry_run: bool = False) -> dict:
    try:
        c = _db(); cur = c.cursor()
        cur.execute("SELECT * FROM telegram_pending_actions WHERE id=%s AND chat_id=%s AND status='pending'", (action_id, str(chat_id)))
        pa = cur.fetchone()
        if not pa: c.close(); return {"status":"not_found"}
        if pa["expires_at"] and pa["expires_at"] < datetime.now(tz=pa["expires_at"].tzinfo):
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
        result = _execute_writer(atype, payload, pa.get("idempotency_key",""), chat_id=str(chat_id), action_id=action_id)
        if not isinstance(result, dict):
            result = {
                "status": "error",
                "error": "writer returned no result",
                "action_type": atype,
            }
        launch_audit_id = result.get("launch_audit_id")
        if atype == "confirm_route_analysis":
            result_status = "executed" if result.get("status") in ("OK", "ok") and launch_audit_id else "failed"
            if result.get("status") in ("OK", "ok") and not launch_audit_id:
                result = {
                    "status": "error",
                    "error": "missing durable launch audit for route precompute confirmation",
                    "action_type": atype,
                }
        else:
            result_status = "executed" if result.get("status") in ("OK","ok") else "failed"
        cur.execute("UPDATE telegram_pending_actions SET status=%s, updated_at=now() WHERE id=%s", (result_status, action_id))
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


def _handle_pending_confirmation(chat_id: str, text: str, dry_run: bool = False) -> dict | None:
    parsed = _parse_confirmation_reply(text)
    decision = parsed.get("decision")
    if decision not in ("yes", "no"):
        return None

    explicit_action_id = parsed.get("action_id")
    active_rows = _pending_active_rows(chat_id)
    target_row: dict[str, Any] | None = None

    if explicit_action_id is not None:
        for row in active_rows:
            if int(row.get("id") or 0) == int(explicit_action_id):
                target_row = row
                break
        if target_row is None:
            existing = _pending_get(chat_id, int(explicit_action_id))
            if not existing:
                return {"response": f"Nie widzę aktywnej prośby #{explicit_action_id} dla tego czatu.", "status": "idle"}
            if existing.get("status") != "pending":
                return {"response": f"Prośba #{explicit_action_id} nie jest już aktywna.", "status": "idle"}
            target_row = existing
    else:
        if len(active_rows) == 1:
            target_row = active_rows[0]
        elif len(active_rows) > 1:
            return {"response": "Masz kilka aktywnych próśb. Odpowiedz numerem, np. 18 TAK.", "status": "ok", "needs_number": True}
        else:
            return {"response": "Nie mam aktywnej akcji do potwierdzenia.", "status": "idle"}

    if not target_row:
        return {"response": "Nie mam aktywnej akcji do potwierdzenia.", "status": "idle"}

    expires_at = target_row.get("expires_at")
    if expires_at and expires_at < datetime.now(tz=expires_at.tzinfo):
        try:
            _pending_decline(chat_id, int(target_row["id"]))
        except:
            pass
        return {"response": f"Prośba #{target_row['id']} wygasła. Wyślij prośbę jeszcze raz.", "status": "ok", "expired": True}

    action_id = int(target_row["id"])
    action_type = str(target_row.get("action_type") or "")

    if dry_run:
        _turn_add(chat_id, "inbound", text, intent="confirm_dryrun", action_id=action_id)
        msg = f"[DRY-RUN] Wykonałbym #{action_id} {action_type}. Uruchom bez --dry-run aby zapisać."
        _turn_add(chat_id, "outbound", text=msg, intent="confirm_dryrun_result", action_id=action_id)
        return {"response": msg, "status": "ok", "dry_run": True}

    if decision == "no":
        _pending_decline(chat_id, action_id)
        _turn_add(chat_id, "inbound", text, intent="decline", action_id=action_id)
        msg = f"#{action_id} anulowano."
        _turn_add(chat_id, "outbound", text=msg, intent="decline_result", action_id=action_id)
        return {"response": msg, "status": "ok", "declined": True, "action_id": action_id, "action_type": action_type}

    result = _pending_execute(chat_id, action_id, dry_run=False)
    _turn_add(chat_id, "inbound", text, intent="confirm", action_id=action_id)
    st = result.get("status", "?")
    if st in ("OK", "ok"):
        if action_type == "confirm_route_analysis":
            msg = f"✓ Uruchomiłem analizę #{action_id}. Wynik zapisuję w DB i logach."
        else:
            msg = f"✓ Wykonano #{action_id}."
    elif st == "expired":
        msg = f"Prośba #{action_id} wygasła. Wyślij prośbę jeszcze raz."
    else:
        msg = f"Błąd przy #{action_id}: {result.get('error', result.get('status', '?'))}"
    _turn_add(chat_id, "outbound", text=msg, intent="confirm_result", action_id=action_id)
    return {"response": msg, "status": "ok", "executed": st in ("OK", "ok"), "action_id": action_id, "action_type": action_type, "action_result": result}

def _execute_writer(atype: str, payload: dict, idem_key: str, chat_id: str | None = None, action_id: int | None = None) -> dict:
    """Execute a local writer — same as MCP handlers. Allowlist enforced."""
    if atype not in _ALLOWED_ACTIONS:
        return {"status": "not_allowed", "action_type": atype, "allowlist": sorted(_ALLOWED_ACTIONS)}
    try:
        if atype == "confirm_route_analysis":
            route_id = str(payload.get("route_id") or "").strip()
            if not route_id:
                return {"status": "error", "error": "missing route_id for route analysis confirmation"}
            # confirm_route_analysis jest ZAWSZE wykonywane jako potwierdzenie z Telegrama,
            # wiec wymuszamy telegram_confirm. Payload moze niesc trigger_source="rwgps_webhook"
            # (z fazy tworzenia pytania przez webhook) — a wtedy koncowe powiadomienie bylo
            # po cichu pomijane przez gate w route_precompute_trigger
            # ._send_route_confirmation_final_notification (trigger_source != "telegram_confirm").
            trigger_source = "telegram_confirm"
            import subprocess as _subprocess
            import sys as _sys

            log_path = _route_confirm_log_path(route_id)
            with open(log_path, "ab") as _logf:
                _subprocess.Popen(
                    [_sys.executable, "/opt/qbot/app/scripts/route_precompute_trigger.py", route_id, "--trigger-source", trigger_source],
                    stdout=_logf,
                    stderr=_subprocess.STDOUT,
                    cwd="/opt/qbot/app",
                    start_new_session=True,
                )
            launch_audit_id = None
            if chat_id and action_id is not None:
                launch_audit_id = _turn_add(
                    chat_id,
                    "system",
                    text=f"Launch precompute for #{action_id} route_id={route_id}",
                    intent="route_precompute_launch_audit",
                    response_json={
                        "status": "OK",
                        "route_id": route_id,
                        "trigger_source": trigger_source,
                        "worker_log_path": log_path,
                        "action_id": action_id,
                    },
                    action_id=action_id,
                )
            if not launch_audit_id:
                return {
                    "status": "error",
                    "error": "failed to persist route precompute launch audit",
                    "action_type": atype,
                    "route_id": route_id,
                    "worker_log_path": log_path,
                }
            return {
                "status": "OK",
                "action_type": atype,
                "route_id": route_id,
                "trigger_source": trigger_source,
                "worker_log_path": log_path,
                "launch_status": "started",
                "launch_audit_id": launch_audit_id,
            }
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

    pending_confirmation = _handle_pending_confirmation(chat_id, text, dry_run=dry_run)
    if pending_confirmation is not None:
        return pending_confirmation

    # ── Simple slash commands ──
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd in ("/help","/start"): return {"response": "QBot Telegram:\n/status\nPisz naturalnie np. 'pokaż bilans za ostatnie 7 dni'"}
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
        date_text = tl
        df_val, dt_val = _parse_followup_dates(date_text)
        if df_val and prior_ctx.get("last_query"):
            prior_query = prior_ctx["last_query"]
            m = re.search(r"(od\s+\d{4}-\d{2}-\d{2}|ostatn\S+\s+\d+\s+\S+)", prior_query)
            if m:
                new_date = f"od {df_val} do {dt_val}" if dt_val else f"od {df_val}"
                text = prior_query[:m.start()] + new_date + prior_query[m.end():]
            else:
                text = f"{prior_query} od {df_val}" + (f" do {dt_val}" if dt_val else "")

    try:
        from qbot_tools import _tool_qbot_query as qbot_query
        result = qbot_query({
            "query": text,
            "mode": "read_only",
            "scope": "all",
            "context": json.dumps(context),
        })
        if not isinstance(result, dict):
            result = {}

        intent = result.get("intents_detected",[])
        answer = str(result.get("answer", "") or "").strip()
        action_draft = result.get("action_draft")

        # ── Action draft handling ──
        # Use action_draft from qbot.query instead of separate Telegram parser.
        has_draft = bool(action_draft and action_draft.get("action_type"))
        write_hint = None
        pid = None  # pending_action_id — ustawiane przez _pending_create gdy has_draft

        if has_draft:
            atype = action_draft["action_type"]
            payload = action_draft.get("payload_json") or action_draft.get("payload") or {}
            idem_key = action_draft.get("idempotency_key", "")

            # Allowlist check
            if atype not in _ALLOWED_ACTIONS:
                response = (
                    f"Rozpoznałem akcję {atype}, ale nie znajduje się na allowliście "
                    f"dostępnych writerów: {', '.join(sorted(_ALLOWED_ACTIONS))}. "
                    f"Nie mogę jej wykonać przez Telegram."
                )
                _turn_add(chat_id, "inbound", text, intent="draft_not_allowed")
                _turn_add(chat_id, "outbound", text=response, intent="draft_not_allowed")
                _conv_upsert(chat_id, state="idle",
                             last_intent=str(intent)[:100],
                             last_response_summary=response[:300],
                             context_json=json.dumps({"last_query": text}))
                return {"response": response, "status": "blocked", "action_draft": action_draft}

            preview = _clean_preview(answer)
            pid = _pending_create(chat_id, atype, payload, preview, idem_key)

            if dry_run:
                response = f"{preview}\n\n[DRY-RUN] Akcja: {atype}. 'tak' nie wykona zapisu."
            else:
                response = f"{preview}\n\nPotwierdzić? Odpowiedz: tak / nie."
            write_hint = atype  # truthy for conv_upsert
            _turn_add(chat_id, "inbound", text, intent="write_draft")
            _turn_add(chat_id, "outbound", text=response, intent="write_draft")
        else:
            response = _telegram_result_text(result)
            if not response:
                response = "Nie mogę teraz odpowiedzieć."
            # Safety: never claim write was executed without action_execute confirm
            if result.get("plan", {}).get("is_write_intent") or result.get("orchestrator", {}).get("stage") in ("draft",):
                for fake_word in ["dodano", "zapisano", "wykonano", "utworzono"]:
                    if fake_word in response.lower()[:80]:
                        response = "Przygotowałem draft. Zapis wymaga potwierdzenia przez qbot.action_execute."
                        break
            _turn_add(chat_id, "inbound", text, intent=str(intent)[:100])
            _turn_add(chat_id, "outbound", text=response, intent="query_response")

        _conv_upsert(chat_id, state="idle" if not write_hint else "awaiting_confirmation",
                     pending_action_id=pid if write_hint else None,
                     last_intent=str(intent)[:100],
                     last_response_summary=answer[:300],
                     context_json=json.dumps({
                         "last_date_from": _mapping_or_empty(result.get("date_resolution")).get("date_from",""),
                         "last_date_to": _mapping_or_empty(result.get("date_resolution")).get("date_to",""),
                         "last_domains": intent,
                         "last_query": text,
                     }))

        return {"response": response, "status": "ok", "read_only": True, "intents": intent,
                "has_draft": has_draft}
    except Exception as e:
        return {"response": f"Błąd: {str(e)[:200]}", "status": "error"}


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
