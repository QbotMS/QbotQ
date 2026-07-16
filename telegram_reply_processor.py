#!/usr/bin/env python3
"""
telegram_reply_processor.py — odbiera wiadomości z Telegrama i przetwarza je:
  - wellness_comment  → save_wellness (Intervals.icu)
  - gear_observations → save_gear / save_component / save_memory (garaż Q)
  - brak danych       → fallback chat z QGPT

Cron: */2 * * * * cd /opt/qbot/app && .venv/bin/python telegram_reply_processor.py >> logs/telegram_reply_cron.log 2>&1
"""
import sys, json, re, httpx
from datetime import date, datetime, timedelta
from pathlib import Path
import qbot_config as cfg
from qbot_garage_mapper import classify_gear_text
from qgpt_client import qgpt_chat, qgpt_json
from qbot_mcp_client import mcp_call as _shared_mcp_call

TOKEN         = cfg.TELEGRAM_TOKEN
CHAT_ID       = str(cfg.TELEGRAM_CHAT_ID)

STATE_FILE        = Path("/opt/qbot/app/data/telegram_state.json")
CHAT_HISTORY_FILE = Path("/opt/qbot/app/data/telegram_chat_history.json")
FAILED_MESSAGES_FILE = Path("/opt/qbot/app/data/telegram_failed_messages.json")
STATE_FILE.parent.mkdir(exist_ok=True)

LOG_FILE = Path("/opt/qbot/app/logs/telegram_reply.log")
LOG_FILE.parent.mkdir(exist_ok=True)

CHAT_MAX_HISTORY = 30  # ostatnie N wiadomości w historii

TG_BASE = f"https://api.telegram.org/bot{TOKEN}"

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")

# ── Stan offsetu ──────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except:
        return {"last_update_id": 0}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def save_failed_message(update_id: int, text: str, error: Exception):
    try:
        data = json.loads(FAILED_MESSAGES_FILE.read_text(encoding="utf-8")) if FAILED_MESSAGES_FILE.exists() else []
    except Exception:
        data = []
    data.append({
        "ts": datetime.now().isoformat(),
        "update_id": update_id,
        "text": text,
        "error": str(error)[:1000],
    })
    FAILED_MESSAGES_FILE.write_text(
        json.dumps(data[-200:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ── MCP ───────────────────────────────────────────────────────────────────────

def mcp_call(tool, args=None):
    return _shared_mcp_call(
        tool, args, client_name="telegram-reply-processor", logger=log
    )

# ── Telegram API ──────────────────────────────────────────────────────────────

def tg_get_updates(offset: int) -> list:
    r = httpx.get(f"{TG_BASE}/getUpdates",
                  params={"offset": offset, "timeout": 5, "limit": 50},
                  timeout=20)
    r.raise_for_status()
    return r.json().get("result", [])

def tg_send(text: str):
    r = httpx.post(f"{TG_BASE}/sendMessage",
                   json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
                   timeout=10)
    r.raise_for_status()

# ── Chat z QGPT (fallback) ────────────────────────────────────────────────────

def load_chat_history() -> list:
    try:
        return json.loads(CHAT_HISTORY_FILE.read_text())
    except:
        return []

def save_chat_history(history: list):
    CHAT_HISTORY_FILE.write_text(
        json.dumps(history[-CHAT_MAX_HISTORY:], ensure_ascii=False, indent=2)
    )

def chat_with_qgpt(text: str) -> str:
    today = date.today()
    system = (
        f"Jesteś asystentem Michała — kolarza używającego systemu Q-bot do śledzenia "
        f"wellness, treningów, sprzętu i planowania wyjazdów. "
        f"Dzisiaj jest {today.strftime('%A, %d %B %Y')} ({today.isoformat()}). "
        f"Odpowiadasz po polsku, zwięźle i konkretnie. "
        f"Jeśli pytanie dotyczy danych (wellness, HRV, aktywności, sprzęt, trasy) — "
        f"odpowiedz na podstawie kontekstu rozmowy lub poproś o doprecyzowanie."
    )

    history = load_chat_history()
    history.append({"role": "user", "content": text})

    reply = qgpt_chat(history, system=system, max_tokens=1024)
    history.append({"role": "assistant", "content": reply})
    save_chat_history(history)
    return reply

# ── QGPT parser ───────────────────────────────────────────────────────────────

def parse_with_qgpt(text: str) -> dict:
    today = date.today()
    weekdays_pl = {
        "poniedziałek": 0, "wtorek": 1, "środa": 2, "czwartek": 3,
        "piątek": 4, "sobota": 5, "niedziela": 6,
    }

    prompt = f"""Dzisiaj jest {today.isoformat()} ({today.strftime('%A')}).
Przeanalizuj wiadomość od kolarza i zwróć TYLKO poprawny JSON, bez żadnego tekstu przed ani po, bez backtick'ów:

{{
  "target_date": "YYYY-MM-DD",
  "wellness_comment": "subiektywne samopoczucie, energia, ból, sen, nastrój — null jeśli brak",
  "gear_observations": ["obserwacja o sprzęcie lub odzieży 1", "obserwacja 2"],
  "activity_context": "krótki opis aktywności jeśli wspomniana — null jeśli brak",
  "calendar_events": ["tytuł wpisu do kalendarza np. Rest day, Delegacja, Trening Z2 1h"],
  "cancel_planned_workouts": true
}}

Zasady:
- target_date: rozumiej "dziś"→{today.isoformat()}, "wczoraj"→{(today-timedelta(days=1)).isoformat()}, dni tygodnia → ostatni miniony taki dzień; domyślnie dziś
- wellness_comment: TYLKO subiektywne odczucia, nie fakty mierzalne; null jeśli wiadomość nie dotyczy samopoczucia
- gear_observations: każda wzmianka o rowerze, komponentach, odzieży, bucie, kasku itp. — osobny element listy; pusta lista jeśli brak
- activity_context: krótki slug np. "Trening Z2 60min" lub "Commute do pracy" — null jeśli brak aktywności
- calendar_events: każde zdarzenie warte wpisania w kalendarz — "Rest day", "Delegacja Wrocław", planowany trening itp.; pusta lista jeśli brak
- cancel_planned_workouts: true TYLKO gdy wprost mówi że odpuszcza/rezygnuje z treningu lub to rest day; false w pozostałych przypadkach

Wiadomość:
\"\"\"{text[:1500]}\"\"\"
"""

    return qgpt_json(prompt, max_tokens=400)

# ── Przetwarzanie wiadomości ──────────────────────────────────────────────────

def process_message(text: str):
    log(f"📨 Treść: {text[:120].strip()}")

    parsed = parse_with_qgpt(text)
    log(f"🤖 QGPT: {json.dumps(parsed, ensure_ascii=False)}")

    target_date   = parsed.get("target_date", date.today().isoformat())
    wellness      = parsed.get("wellness_comment")
    gear_obs      = parsed.get("gear_observations") or []
    activity_ctx  = parsed.get("activity_context") or "ogolne"
    cal_events    = parsed.get("calendar_events") or []
    cancel_plans  = parsed.get("cancel_planned_workouts", False)
    saved         = []

    # 1. Wellness → Intervals.icu
    if wellness:
        result = mcp_call("save_wellness", {"date": target_date, "comments": wellness})
        if result:
            log(f"   ✅ Wellness [{target_date}]: {wellness[:80]}")
            saved.append("wellness")
        else:
            log(f"   ⚠️  Wellness: błąd zapisu")

    # 2. Gear → save_gear / save_component / save_memory
    if gear_obs:
        hhmm  = datetime.now().strftime("%H%M")
        slug  = re.sub(r'[^a-z0-9]+', '_', activity_ctx.lower())[:30]
        topic = f"gear_usage:{target_date}:{slug}:{hhmm}"
        saved_count = 0
        for o in gear_obs:
            action = classify_gear_text(o)
            if action.tool == "save_memory":
                payload = action.payload or {"topic": topic, "content": f"• {o}\nŹródło: Telegram"}
            else:
                payload = {**action.payload, "active": 1}
            result = mcp_call(action.tool, payload)
            if result:
                log(f"   ✅ Gear [{action.label}]: {o}")
                saved.append(action.label)
                saved_count += 1
            else:
                log(f"   ⚠️  Gear: błąd zapisu -> {o}")
        if saved_count:
            saved.append(f"gear({saved_count})")

    # 3. Kasuj zaplanowane treningi jeśli rest day / rezygnacja
    if cancel_plans:
        events_raw = mcp_call("get_events", {"oldest": target_date, "newest": target_date})
        events = events_raw if isinstance(events_raw, list) else []
        removed = 0
        for ev in events:
            if ev.get("category") in ("WORKOUT", "NOTE") and ev.get("id"):
                result = mcp_call("delete_event", {"event_id": ev["id"]})
                if result:
                    log(f"   🗑  Usunięto z kalendarza: {ev.get('name')} [{ev['id']}]")
                    removed += 1
        if removed:
            saved.append(f"usunięto {removed} plan(y)")

    # 4. Wpisy kalendarza → Intervals.icu
    for title in cal_events:
        if not title:
            continue
        result = mcp_call("create_event", {"date": target_date, "title": title})
        if result:
            log(f"   ✅ Kalendarz: {title}")
            saved.append(f"event:{title}")
        else:
            log(f"   ⚠️  Kalendarz: błąd dla '{title}'")

    summary = ", ".join(saved) if saved else "brak danych do zapisu"
    log(f"   ✅ Zapisano: {summary}")
    return summary

# ── Main ──────────────────────────────────────────────────────────────────────

def tg_send_plain(text):
    try:
        httpx.post(f"{TG_BASE}/sendMessage", json={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as _e:
        log(f"   tg_send_plain blad: {_e}")


def tg_answer_callback(cq_id, text=""):
    try:
        httpx.post(f"{TG_BASE}/answerCallbackQuery", json={"callback_query_id": cq_id, "text": text}, timeout=10)
    except Exception:
        pass


def tg_edit_markup(chat_id, message_id):
    try:
        httpx.post(f"{TG_BASE}/editMessageReplyMarkup",
                   json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
                   timeout=10)
    except Exception:
        pass


def _spawn_komoot_analyze_worker(tour_id, atrakcje=False):
    """Odpala analize trasy Komoot w odlaczonym procesie (nie blokuje crona)."""
    import subprocess, sys
    args = [sys.executable, "/opt/qbot/app/scripts/komoot_analyze_worker.py", str(tour_id)]
    if atrakcje:
        args.append("--atrakcje")
    logf = open("/opt/qbot/logs/komoot_analyze_" + str(tour_id) + ".log", "ab")
    subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT,
                     cwd="/opt/qbot/app", start_new_session=True)


def handle_komoot_callback(cq):
    data = cq.get("data") or ""
    cq_id = cq.get("id")
    m = cq.get("message") or {}
    chat_id = str((m.get("chat") or {}).get("id", ""))
    message_id = m.get("message_id")
    if chat_id != CHAT_ID:
        tg_answer_callback(cq_id, "Brak dostepu")
        return
    if not data.startswith("kmt:"):
        tg_answer_callback(cq_id)
        return
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tour_id = parts[2] if len(parts) > 2 else ""
    import komoot_watch
    _clear = True
    if action == "y":
        tg_answer_callback(cq_id, "Analizuje...")
        tg_send_plain("\U0001F504 Przyjeto. Uruchamiam analize trasy #" + tour_id + " w tle - chwile to potrwa, przysle wynik.")
        _spawn_komoot_analyze_worker(tour_id, atrakcje=False)
    elif action == "ya":
        tg_answer_callback(cq_id, "Analizuje + atrakcje...")
        tg_send_plain("\U0001F504 Przyjeto. Uruchamiam analize trasy #" + tour_id + " (+atrakcje) w tle - chwile to potrwa, przysle wynik.")
        _spawn_komoot_analyze_worker(tour_id, atrakcje=True)
    elif action == "n":
        tg_answer_callback(cq_id, "Pominieto")
        try:
            komoot_watch.skip_tour(tour_id)
        except Exception as e:
            log(f"   skip_tour blad: {e}")
        tg_send_plain("\u274c Pominieto trase #" + tour_id + ".")
    else:
        tg_answer_callback(cq_id)
    if message_id and _clear:
        tg_edit_markup(chat_id, message_id)


def main():
    log("🔍 Sprawdzam Telegram...")

    state  = load_state()
    offset = state.get("last_update_id", 0) + 1

    try:
        updates = tg_get_updates(offset)
    except Exception as e:
        log(f"❌ getUpdates błąd: {e}")
        sys.exit(1)

    if not updates:
        log("ℹ️  Brak nowych wiadomości.")
        return

    log(f"📬 Znaleziono {len(updates)} update(ów).")

    for upd in updates:
        update_id = upd.get("update_id", 0)

        cq = upd.get("callback_query")
        if cq:
            state["last_update_id"] = update_id
            save_state(state)
            try:
                handle_komoot_callback(cq)
            except Exception as e:
                log(f"   callback blad: {e}")
            continue

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            state["last_update_id"] = update_id
            save_state(state)
            continue

        chat_id  = str(msg.get("chat", {}).get("id", ""))
        text     = msg.get("text", "").strip()

        # Bezpieczeństwo — tylko nasz chat
        if chat_id != CHAT_ID:
            log(f"🚫 Unauthorized chat_id={chat_id} — ignoruję")
            state["last_update_id"] = update_id
            save_state(state)
            continue

        # Pomijaj puste i komendy
        if not text:
            log("   ⏭  Pusta wiadomość — pomijam")
            state["last_update_id"] = update_id
            save_state(state)
            continue
        if text.startswith("/"):
            log(f"   ⏭  Komenda {text.split()[0]} — pomijam")
            state["last_update_id"] = update_id
            save_state(state)
            continue

        try:
            summary = process_message(text)
            if summary == "brak danych do zapisu":
                log("💬 Fallback → chat z QGPT")
                reply = chat_with_qgpt(text)
                log(f"   🤖 Odpowiedź: {reply[:120]}")
                tg_send(reply)
                state["last_update_id"] = update_id
                save_state(state)
            else:
                state["last_update_id"] = update_id
                save_state(state)
                tg_send(f"✅ Zapisano: {summary}")
        except Exception as e:
            log(f"   ❌ Błąd przetwarzania: {e}")
            save_failed_message(update_id, text, e)
            try:
                tg_send(f"⚠️ Błąd: {e}")
            except Exception as send_exc:
                log(f"   ❌ Nie udało się wysłać informacji o błędzie: {send_exc}")

    log("✅ Zakończono.")

if __name__ == "__main__":
    main()
