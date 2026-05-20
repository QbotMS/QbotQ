#!/usr/bin/env python3
"""
email_reply_processor.py — przetwarza odpowiedzi na raporty jazdy.
Zapisuje w tle:
  - komentarz wellness → Intervals.icu
  - gear_usage        → garaż Q (save_gear / save_component / save_memory)
  - equipment_note    → garaż Q (save_gear / save_component / save_memory)

Cron (dodaj po ride_report):
*/30 * * * * cd /opt/qbot/app && .venv/bin/python email_reply_processor.py >> /opt/qbot/app/logs/email_reply.log 2>&1
"""

import sys, json, imaplib, email, re
from datetime import datetime
from pathlib import Path
from email.header import decode_header
import httpx
import qbot_config as cfg
from qbot_garage_mapper import classify_gear_text
from qgpt_client import qgpt_json
from qbot_mcp_client import mcp_call as _shared_mcp_call

ATHLETE_ID    = cfg.INTERVALS_ATHLETE_ID
API_KEY       = cfg.INTERVALS_API_KEY
GMAIL_USER    = cfg.GMAIL_USER
GMAIL_PASS    = cfg.GMAIL_APP_PASSWORD

ICU_HDR = cfg.intervals_headers()

PROCESSED_FILE = Path("/opt/qbot/app/data/processed_replies.json")
FAILED_REPLIES_FILE = Path("/opt/qbot/app/data/email_failed_replies.json")
PROCESSED_FILE.parent.mkdir(exist_ok=True)

# ── Deduplikacja ──────────────────────────────────────────────────────────────

def already_processed(msg_id: str) -> bool:
    try:
        return msg_id in json.loads(PROCESSED_FILE.read_text())
    except:
        return False

def mark_processed(msg_id: str, info: dict):
    try:
        data = json.loads(PROCESSED_FILE.read_text()) if PROCESSED_FILE.exists() else {}
    except:
        data = {}
    data[msg_id] = {"ts": datetime.now().isoformat(), **info}
    if len(data) > 300:
        for k in sorted(data.keys())[:len(data) - 300]:
            del data[k]
    PROCESSED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def mark_failed_reply(msg_id: str, info: dict):
    try:
        data = json.loads(FAILED_REPLIES_FILE.read_text(encoding="utf-8")) if FAILED_REPLIES_FILE.exists() else []
    except Exception:
        data = []
    data.append({"ts": datetime.now().isoformat(), "message_id": msg_id, **info})
    FAILED_REPLIES_FILE.write_text(json.dumps(data[-200:], ensure_ascii=False, indent=2), encoding="utf-8")

# ── MCP / API ─────────────────────────────────────────────────────────────────

def mcp_call(tool: str, args: dict | None = None):
    return _shared_mcp_call(
        tool,
        args,
        client_name="email-reply-processor",
        logger=lambda msg: print(f"   {msg}"),
    )

def icu_save_wellness_comment_UNUSED(ride_date: str, comment: str):
    """Dołącza komentarz do istniejącego wellness w Intervals.icu (nie nadpisuje innych pól)."""
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness/{ride_date}"
    try:
        existing      = httpx.get(url, headers=ICU_HDR, timeout=15).json()
        prev_comment  = (existing.get("comment") or "").strip()
    except:
        prev_comment  = ""
    new_comment = f"{prev_comment}\n📧 {comment}".strip() if prev_comment else f"📧 {comment}"
    r = httpx.put(url,
                  headers={**ICU_HDR, "Content-Type": "application/json"},
                  json={"comment": new_comment}, timeout=15)
    r.raise_for_status()

# ── QGPT parsers ──────────────────────────────────────────────────────────────

def parse_daily_reply_with_qgpt(reply_text: str, report_date: str) -> dict:
    prompt = f"""Przeanalizuj odpowiedź zawodnika na codzienny raport Q z dnia {report_date}.

Odpowiedź:
\"\"\"
{reply_text[:2000]}
\"\"\"

Zwróć TYLKO poprawny JSON, bez żadnego tekstu przed ani po, bez backtick'ów:

{{
  "wellness_comment": "ogólne samopoczucie, energia, nastrój, jakość snu subiektywnie — null jeśli brak",
  "training_done": "co faktycznie zrobił: typ, czas, intensywność — null jeśli brak lub nie wspomina",
  "supplements": [
    {{"name": "nazwa suplementu", "action": "wzial|odstawil|zmienil", "note": "szczegóły lub null"}}
  ],
  "schedule": [
    {{"type": "praca|podroz|stres|wydarzenie|inne", "note": "szczegóły"}}
  ],
  "nutrition": "zmiany w diecie, post, specjalne odżywianie — null jeśli brak",
  "health": "dolegliwości, ból, choroba, urazy — null jeśli brak",
  "gear_notes": [
    {{"item": "element sprzętu", "note": "spostrzeżenie"}}
  ],
  "calendar_events": [
    "krótki tytuł wpisu do kalendarza, np. Trening Z2 1h, Delegacja Wrocław, Rest day"
  ]
}}

Zasady:
- wellness_comment: subiektywne odczucia, NIE fakty mierzalne
- training_done: tylko jeśli mówi co już ZA SOBĄ ma (zrobił) — null jeśli planuje
- calendar_events: KAŻDA wzmianka o planie na dziś lub jutro — trening, delegacja, rest day, wydarzenie, cokolwiek; krótkie tytuły; pusta lista jeśli brak
- supplements: każda wzmianka o lekach, suplementach, kawie, alkoholu jeśli kontekst zdrowotny
- schedule: wszystko co wpływa na trening — praca, podróż, stres, brak czasu
- puste listy [] lub null gdy danych brak"""

    return qgpt_json(prompt, max_tokens=800)

def parse_reply_with_qgpt(reply_text: str, ride_date: str, activity_name: str) -> dict:
    prompt = f"""Przeanalizuj odpowiedź zawodnika na raport jazdy z dnia {ride_date} ({activity_name}).

Odpowiedź:
\"\"\"
{reply_text[:2000]}
\"\"\"

Zwróć TYLKO poprawny JSON, bez żadnego tekstu przed ani po, bez backtick'ów:

{{
  "wellness_comment": "subiektywne odczucia po jeździe: nogi, zmęczenie, samopoczucie ogólne — null jeśli brak",
  "gear_used": [
    {{"name": "nazwa elementu odzieży jak wymienił zawodnik", "opinion": "opinia lub null"}}
  ],
  "equipment_notes": [
    {{"item": "element roweru lub komponentu", "note": "spostrzeżenie"}}
  ]
}}

Zasady:
- wellness_comment: tylko subiektywne odczucia, NIE fakty o jeździe (dystans, moc itp.)
- gear_used: KAŻDA wzmianka o odzieży lub wyposażeniu osobistym (kask, koszulka, spodenki, skarpety, rękawice, buty, kurtka, kamizelka, czapka, komin itp.)
- equipment_notes: tylko rower i komponenty (łańcuch, opony, hamulce, siodło, pedały itp.)
- puste listy [] lub null gdy danych brak"""

    return qgpt_json(prompt, max_tokens=800)

# ── Email helpers ─────────────────────────────────────────────────────────────

def decode_str(s: str) -> str:
    parts = decode_header(s or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)

def get_body(msg) -> str:
    """Wyciąga plain text z wiadomości (fallback: strip HTML)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                raw = part.get_payload(decode=True)
                return raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                raw = part.get_payload(decode=True)
                txt = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", txt)
    raw = msg.get_payload(decode=True)
    return raw.decode(msg.get_content_charset() or "utf-8", errors="replace") if raw else ""

def strip_quoted(body: str) -> str:
    """Usuwa cytowany oryginał — zostawia tylko nową treść."""
    clean = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^(On |W dniu |--\s*$|_{5,})", stripped):
            break
        if stripped.startswith(">"):
            break
        clean.append(line)
    return "\n".join(clean).strip()

def parse_date_from_subject(subject: str) -> str:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", subject)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return datetime.now().strftime("%Y-%m-%d")

def parse_activity_from_subject(subject: str) -> str:
    m = re.search(r"Raport jazdy\s*[—–\-]\s*(.+?)\s*[·•]\s*\d", subject)
    return m.group(1).strip() if m else "Jazda"

def parse_date_from_daily_subject(subject: str) -> str:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", subject)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return datetime.now().strftime("%Y-%m-%d")

# ── Procesor odpowiedzi na raport dzienny ─────────────────────────────────────

def process_daily_replies(mail):
    _, data = mail.search(None, 'UNSEEN SUBJECT "raport"')
    nums = [n for n in data[0].split() if n]
    if not nums:
        return
    # Filtruj tylko wiadomości dotyczące Q-raport (nie Raport jazdy)
    daily_nums = []
    for n in nums:
        _, md = mail.fetch(n, "(RFC822)")
        msg_tmp = email.message_from_bytes(md[0][1])
        subj_tmp = decode_str(msg_tmp.get("Subject", "")).lower()
        if "q-raport" in subj_tmp or ("raport" in subj_tmp and "jazdy" not in subj_tmp):
            daily_nums.append(n)
    nums = daily_nums
    if not nums:
        return

    print(f"📨 Znaleziono {len(nums)} odpowiedzi na raport dzienny.")

    for num in nums:
        _, msg_data = mail.fetch(num, "(RFC822)")
        msg     = email.message_from_bytes(msg_data[0][1])
        subject = decode_str(msg.get("Subject", ""))
        msg_id  = msg.get("Message-ID", str(num))

        is_reply = bool(msg.get("In-Reply-To")) or subject.lower().startswith(("re:", "odp:", "aw:", "sv:"))
        if not is_reply:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        if already_processed(msg_id):
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        reply_text = strip_quoted(get_body(msg))
        if len(reply_text) < 5:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        report_date = parse_date_from_daily_subject(subject)
        print(f"\n🔍 Q-raport dzienny ({report_date})")
        print(f"   Treść: {reply_text[:120].strip()}...")

        try:
            parsed = parse_daily_reply_with_qgpt(reply_text, report_date)
        except Exception as e:
            print(f"   ❌ QGPT błąd: {e}")
            mark_failed_reply(msg_id, {
                "type": "daily",
                "subject": subject,
                "report_date": report_date,
                "body": reply_text[:4000],
                "error": str(e)[:1000],
            })
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        saved = []

        # 1. Wellness + trening → Intervals.icu
        parts = [p for p in [parsed.get("wellness_comment"), parsed.get("training_done")] if p]
        if parts:
            comment = " | ".join(parts)
            try:
                mcp_call("save_wellness", {"date": report_date, "comments": comment})
                print(f"   ✅ Wellness: {comment[:80]}")
                saved.append("wellness")
            except Exception as e:
                print(f"   ⚠️  Wellness błąd: {e}")

        # 2. Suplementy → memory
        for sup in parsed.get("supplements") or []:
            content = json.dumps({"date": report_date, "name": sup["name"],
                                  "action": sup.get("action"), "note": sup.get("note")},
                                 ensure_ascii=False)
            topic = f"supplement:{report_date}:{sup['name'][:30]}"
            if mcp_call("save_memory", {"topic": topic, "content": content}):
                print(f"   ✅ Suplement: {sup['name']} ({sup.get('action')})")
                saved.append(f"supplement:{sup['name']}")

        # 3. Harmonogram / kontekst → memory
        schedule = parsed.get("schedule") or []
        if schedule:
            content = json.dumps({"date": report_date, "events": schedule}, ensure_ascii=False)
            if mcp_call("save_memory", {"topic": f"schedule:{report_date}", "content": content}):
                for ev in schedule:
                    print(f"   ✅ Harmonogram: {ev.get('type')} — {ev.get('note','')[:60]}")
                    saved.append(f"schedule:{ev.get('type')}")

        # 4. Odżywianie → memory
        if parsed.get("nutrition"):
            content = json.dumps({"date": report_date, "note": parsed["nutrition"]}, ensure_ascii=False)
            if mcp_call("save_memory", {"topic": f"nutrition_note:{report_date}", "content": content}):
                print(f"   ✅ Dieta: {parsed['nutrition'][:60]}")
                saved.append("nutrition")

        # 5. Zdrowie → memory
        if parsed.get("health"):
            content = json.dumps({"date": report_date, "note": parsed["health"]}, ensure_ascii=False)
            if mcp_call("save_memory", {"topic": f"health:{report_date}", "content": content}):
                print(f"   ✅ Zdrowie: {parsed['health'][:60]}")
                saved.append("health")

        # 6. Sprzęt → save_gear / save_component / memory
        for note in parsed.get("gear_notes") or []:
            text = f"{note['item']}: {note['note']}"
            action = classify_gear_text(text)
            if action.tool == "save_memory":
                payload = action.payload or {"topic": f"equipment_note:{report_date}", "content": json.dumps({
                    "date": report_date,
                    "item": note["item"],
                    "note": note["note"]
                }, ensure_ascii=False)}
            else:
                payload = {**action.payload, "active": 1}
            if mcp_call(action.tool, payload):
                print(f"   ✅ Sprzęt [{action.label}]: {note['item']} — {note['note']}")
                saved.append(action.label)

        # 7. Wpisy kalendarza → Intervals.icu
        for title in parsed.get("calendar_events") or []:
            if not title:
                continue
            result = mcp_call("create_event", {"date": report_date, "title": title})
            if result:
                print(f"   ✅ Intervals: {title}")
                saved.append(f"event:{title}")
            else:
                print(f"   ⚠️  Nie udało się dodać: {title}")

        mail.store(num, "+FLAGS", "\\Seen")
        mark_processed(msg_id, {"report_date": report_date, "saved": saved})
        print(f"   ✅ Zapisano: {', '.join(saved) or 'brak danych do zapisu'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def process_replies():
    print(f"📬 Sprawdzam odpowiedzi [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("INBOX")
    except Exception as e:
        print(f"❌ IMAP błąd: {e}")
        sys.exit(1)

    _, data = mail.search(None, 'UNSEEN SUBJECT "Raport jazdy"')
    nums = data[0].split()
    # Fallback: szukaj też bez emoji (subject może być encoded)
    if not nums:
        _, data2 = mail.search(None, 'UNSEEN SUBJECT "raport jazdy"')
        nums = data2[0].split()

    if not nums:
        print("ℹ️  Brak odpowiedzi na raporty jazdy.")
    else:
        print(f"📨 Znaleziono {len(nums)} odpowiedzi na raport jazdy.")

    for num in nums:
        _, msg_data = mail.fetch(num, "(RFC822)")
        msg     = email.message_from_bytes(msg_data[0][1])
        subject = decode_str(msg.get("Subject", ""))
        msg_id  = msg.get("Message-ID", str(num))

        # Pomiń oryginalne raporty wysłane przez skrypt (nie są odpowiedziami)
        is_reply = bool(msg.get("In-Reply-To")) or subject.lower().startswith(("re:", "odp:", "aw:", "sv:"))
        if not is_reply:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        if already_processed(msg_id):
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        reply_text = strip_quoted(get_body(msg))
        if len(reply_text) < 5:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        ride_date     = parse_date_from_subject(subject)
        activity_name = parse_activity_from_subject(subject)

        print(f"\n🔍 {activity_name} ({ride_date})")
        print(f"   Treść: {reply_text[:120].strip()}...")

        try:
            parsed = parse_reply_with_qgpt(reply_text, ride_date, activity_name)
        except Exception as e:
            print(f"   ❌ QGPT błąd: {e}")
            mark_failed_reply(msg_id, {
                "type": "ride",
                "subject": subject,
                "ride_date": ride_date,
                "activity": activity_name,
                "body": reply_text[:4000],
                "error": str(e)[:1000],
            })
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        saved = []

        # 1. Wellness → Intervals.icu
        if parsed.get("wellness_comment"):
            try:
                mcp_call("save_wellness", {"date": ride_date, "comments": parsed["wellness_comment"]})
                print(f"   ✅ Wellness: {parsed['wellness_comment'][:80]}")
                saved.append("wellness")
            except Exception as e:
                print(f"   ⚠️  Wellness błąd: {e}")

        # 2. Gear usage → save_gear / save_component / memory
        gear_list = parsed.get("gear_used") or []
        if gear_list:
            topic = f"gear_usage:{ride_date}:{activity_name[:30]}"
            saved_count = 0
            for g in gear_list:
                text = f"{g['name']}: {g.get('opinion') or ''}".strip(": ")
                action = classify_gear_text(text)
                if action.tool == "save_memory":
                    payload = action.payload or {"topic": topic, "content": json.dumps({
                        "date": ride_date,
                        "activity": activity_name,
                        "item": g["name"],
                        "opinion": g.get("opinion")
                    }, ensure_ascii=False)}
                else:
                    payload = {**action.payload, "active": 1}
                if mcp_call(action.tool, payload):
                    print(f"   ✅ Gear [{action.label}]: {g['name']}" + (f" — {g['opinion']}" if g.get("opinion") else ""))
                    saved.append(action.label)
                    saved_count += 1
            if saved_count:
                saved.append(f"gear({saved_count})")

        # 3. Equipment notes → save_gear / save_component / memory
        for note in parsed.get("equipment_notes") or []:
            text = f"{note['item']}: {note['note']}"
            action = classify_gear_text(text)
            if action.tool == "save_memory":
                payload = action.payload or {"topic": f"equipment_note:{ride_date}", "content": json.dumps({
                    "date": ride_date,
                    "activity": activity_name,
                    "item": note["item"],
                    "note": note["note"]
                }, ensure_ascii=False)}
            else:
                payload = {**action.payload, "active": 1}
            if mcp_call(action.tool, payload):
                print(f"   ✅ Sprzęt [{action.label}]: {note['item']} — {note['note']}")
                saved.append(action.label)

        mail.store(num, "+FLAGS", "\\Seen")
        mark_processed(msg_id, {
            "ride_date": ride_date,
            "activity": activity_name,
            "saved": saved
        })
        print(f"   ✅ Zapisano: {', '.join(saved) or 'brak danych do zapisu'}")

    process_daily_replies(mail)

    mail.logout()
    print("\n✅ Zakończono.")

if __name__ == "__main__":
    process_replies()
