from __future__ import annotations

"""Notatki po jednostce -> sygnal organizmu -> Kalendarz (2026-09-29).

Ocena gwiazdkami w TRENERZE = ocena PLANU (nie samopoczucia) - nie jest tu uzywana.
Tresc notatki bywa jednak sygnalem o organizmie ("ciezkie nogi", "nie mam sily"). extract_signal() odczytuje z niej
TYLKO stan organizmu (-2..+2); dyskomfort sprzetowy (siodlo, dretwienie rak, ubranie) przy oznakach slabosci traktuje
jako OBJAW zmeczenia (slabnacy tulow -> ciezar na siodlo i rece), a nie wine sprzetu. Opinie o planie sa pomijane.
sync_trener_note() zapisuje wynik jako wpis Kalendarza kind='feel' (source='trener', source_ref=trener:<dzien>:<sport>),
title zaczyna sie od "📝 " (TRENER nie dubluje go jako kafelka). Wpis Kalendarza wchodzi do stanu ciala jak kazdy
wpis samopoczucia (fitmodel/real_load.py, feel != 0). Kalendarz -> TRENER: TRENER juz pokazuje wpisy Kalendarza.
"""

import json
import re
import threading

TITLE_MARK = "📝 "

_SYSTEM = (
    "Czytasz krotka notatke kolarza amatora po jednostce treningowej. Oceniasz WYLACZNIE, co mowi o STANIE ORGANIZMU "
    "(zmeczenie / swiezosc). Zasady: 'ciezkie nogi', 'brak sily', 'nie mam sily', 'zajechany', 'oslabiony', 'bol miesni' = "
    "zmeczenie; 'lekko', 'moc', 'swietnie', 'swiezy', 'noga podaje' = swiezosc. Dyskomfort sprzetowy (siodlo, dretwienie rak, "
    "ubranie) przy oznakach slabosci traktuj jako objaw zmeczenia (slabnacy tulow przerzuca ciezar na siodlo i rece), a bez "
    "takich oznak - pomin. Opinie o planie treningowym pomijaj. feel: -2 wyraznie zmeczony, -1 zmeczony, 0 brak sygnalu, "
    "+1 swiezy, +2 wyraznie swiezy. Zwroc WYLACZNIE JSON: {\"feel\": int, \"summary\": \"max 8 slow po polsku\", "
    "\"quote\": \"kluczowy fragment notatki\"}."
)

_NEG = [(r"nie mam si[lł]|brak si[lł]|bez si[lł]|zajechan|wyczerpan|padam|trup", -2),
        (r"ci[eę][zż]kie nogi|zm[eę]czon|os[lł]abion|s[lł]ab[oy]|ci[eę][zż]ko|b[oó]l mi[eę]", -1)]
_POS = [(r"[sś]wietnie|rewelac|moc jest|noga podaje|[sś]wie[zż]y|lekko", 1)]


def rules_signal(text: str) -> dict:
    t = (text or "").lower()
    for pat, v in _NEG:
        m = re.search(pat, t)
        if m:
            return {"feel": v, "summary": "zmęczenie z notatki", "quote": m.group(0), "method": "reguly"}
    for pat, v in _POS:
        m = re.search(pat, t)
        if m:
            return {"feel": v, "summary": "świeżość z notatki", "quote": m.group(0), "method": "reguly"}
    return {"feel": 0, "summary": "", "quote": "", "method": "reguly"}


def extract_signal(text: str) -> dict:
    """AI (qgpt), zapas: reguly slownikowe. Zwraca feel -2..2, summary, quote, method."""
    if not (text or "").strip():
        return {"feel": 0, "summary": "", "quote": "", "method": "brak"}
    try:
        from qgpt_client import qgpt_text
        raw = qgpt_text(text.strip(), system=_SYSTEM, max_tokens=800, temperature=0.0)
        i = (raw or "").find("{")
        obj, _ = json.JSONDecoder().raw_decode(raw[i:])
        fv = int(obj.get("feel", 0))
        return {"feel": max(-2, min(2, fv)), "summary": str(obj.get("summary") or "")[:80],
                "quote": str(obj.get("quote") or "")[:160], "method": "ai"}
    except Exception:
        return rules_signal(text)


def _ensure_cols(cur):
    cur.execute("ALTER TABLE qbot_v2.calendar_entry ADD COLUMN IF NOT EXISTS source TEXT, ADD COLUMN IF NOT EXISTS source_ref TEXT")


def sync_trener_note(conn, day, sport: str, note: str | None, session_name: str | None = None) -> dict:
    """Upsert/usuniecie wpisu Kalendarza z notatki TRENERA + przeliczenie gotowosci/stanu ciala tego dnia."""
    cur = conn.cursor()
    _ensure_cols(cur)
    ref = "trener:%s:%s" % (str(day)[:10], sport)
    cur.execute("DELETE FROM qbot_v2.calendar_entry WHERE source='trener' AND source_ref=%s", (ref,))
    sig = extract_signal(note or "")
    if (note or "").strip():
        title = TITLE_MARK + (sig["summary"] or ("notatka: " + (session_name or sport)))
        cur.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, feel, title, note, source, source_ref) "
                    "VALUES (%s,'feel',%s,%s,%s,'trener',%s)",
                    (str(day)[:10], sig["feel"], title[:120], (note or "").strip()[:1000], ref))
    conn.commit()
    try:
        from fitmodel.readiness import recalc_subjective_days
        recalc_subjective_days(conn, [(str(day)[:10], None)])
    except Exception as exc:
        sig["recalc_error"] = str(exc)
    return dict(sig, ref=ref)


def sync_async(day, sport: str, note: str | None, session_name: str | None = None) -> None:
    """Z requestu TRENERA: w tle (AI trwa kilka sekund), wlasne polaczenie - zapis oceny nie czeka."""
    def _run():
        try:
            import time
            time.sleep(1.5)          # transakcja zapisu oceny zdazy sie zatwierdzic
            from fitmodel.ftp_resolver import _db_connect
            c = _db_connect()
            try:
                r = sync_trener_note(c, day, sport, note, session_name)
                print("[body_notes] %s %s -> feel %s (%s)" % (day, sport, r.get("feel"), r.get("method")), flush=True)
            finally:
                c.close()
        except Exception as exc:
            print("[body_notes] BLAD %s: %s" % (day, exc), flush=True)
    threading.Thread(target=_run, daemon=True).start()
