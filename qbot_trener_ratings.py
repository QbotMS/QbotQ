"""TRENER - oceny planu przez uzytkownika (1-5 + komentarz) i ich uzycie przez Trenera.

Tabela qbot_v2.trainer_rating (sql/trainer_v6.sql), klucz (username, day, sport) - przetrwa przeliczenie tygodnia
(sesje auto dostaja nowe id). Uzycie ocen:
  * sila: exercise_prefs() -> srednia ocen kazdego cwiczenia (z kopii zestawu przy ocenie); qbot_trener_workouts.details
    pomija cwiczenia ze srednia <= 2 (wstawia inny wariant z tej samej grupy, najlepiej oceniony);
  * wszystkie sporty: recent_for_ai() -> ostatnie oceny z komentarzami dla weryfikacji AI (qbot_trener_review) i Alberta.
Zestaw z preferencjami liczymy TYLKO dla przyszlych sesji w stanie plan - miniona/zrobiona sesja pokazuje to, co bylo.
Testy: tests/test_trener_ratings.py.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

MAX_NOTE = 300
SPORT_NAMES = {"rower": "rower", "sila": "siła", "wiosl": "wioślarz", "joga": "joga"}


class BadRating(ValueError):
    pass


def clean_rating(b) -> dict:
    """Walidacja wejscia POST /rating. rating 0 = usun ocene."""
    if not isinstance(b, dict):
        raise BadRating("body: oczekiwano obiektu")
    try:
        sid = int(b.get("session_id"))
    except (TypeError, ValueError):
        raise BadRating("session_id: wymagane")
    try:
        r = int(b.get("rating"))
    except (TypeError, ValueError):
        raise BadRating("rating: liczba 0-5")
    if r < 0 or r > 5:
        raise BadRating("rating: liczba 0-5")
    note = b.get("note")
    note = str(note).strip()[:MAX_NOTE] if note not in (None, "") else None
    return {"session_id": sid, "rating": r, "note": note or None}


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


def exercise_prefs(c, user: str, days: int = 365) -> dict:
    """{nazwa cwiczenia: srednia ocena} z ocenionych sesji silowych (ostatni rok)."""
    c.execute("SELECT rating, exercises FROM qbot_v2.trainer_rating WHERE username=%s AND sport='sila' "
              "AND exercises IS NOT NULL AND day >= %s", (user, date.today() - timedelta(days=days)))
    acc: dict = {}
    for row in c.fetchall():
        ex = row["exercises"]
        if isinstance(ex, str):
            try:
                ex = json.loads(ex)
            except ValueError:
                ex = []
        for e in ex or []:
            n = (e or {}).get("name")
            if n:
                acc.setdefault(n, []).append(int(row["rating"]))
    return {n: round(sum(v) / len(v), 2) for n, v in acc.items()}


def details_for(c, user: str, s: dict, phase, prefs: dict | None = None) -> dict:
    """Szczegoly sesji; dla przyszlej sesji 'plan' z uwzglednieniem ocen cwiczen."""
    import qbot_trener_workouts as TW
    n = TW.strength_index(c, user, s) if s["sport"] == "sila" else 0
    use = s["sport"] == "sila" and s.get("status") == "plan" and _d(s["day"]) >= date.today()
    if use and prefs is None:
        prefs = exercise_prefs(c, user)
    return TW.details(s["sport"], phase, s["dur_min"], bool(s.get("cut")), n, prefs=(prefs if use else None))


def for_range(c, user: str, d0, d1) -> dict:
    """{(RRRR-MM-DD, sport): {rating, note}} dla tygodnia."""
    c.execute("SELECT day, sport, rating, note FROM qbot_v2.trainer_rating WHERE username=%s AND day BETWEEN %s AND %s",
              (user, d0, d1))
    return {(str(r["day"])[:10], r["sport"]): {"rating": int(r["rating"]), "note": r["note"]} for r in c.fetchall()}


def _mirror(s: dict, note) -> None:
    """2026-09-29: tresc notatki -> sygnal organizmu -> wpis samopoczucia w Kalendarzu (fitmodel/body_notes.py, w tle).
    Ocena gwiazdkami to ocena planu - NIE jest przenoszona."""
    try:
        from fitmodel.body_notes import sync_async
        sync_async(s["day"], s["sport"], note, s.get("name"))
    except Exception as e:
        print("trener ocena: kopia do Kalendarza nieudana:", e)


def save(c, user: str, b: dict, phase=None) -> dict:
    """Zapis/usuniecie oceny sesji (upsert po dniu i sporcie) + kopia zestawu cwiczen z chwili oceny."""
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s", (b["session_id"], user))
    s = c.fetchone()
    if not s:
        raise BadRating("nie ma takiej sesji")
    s = dict(s)
    if b["rating"] == 0:
        c.execute("DELETE FROM qbot_v2.trainer_rating WHERE username=%s AND day=%s AND sport=%s", (user, s["day"], s["sport"]))
        _mirror(s, None)
        return {"ok": True, "deleted": True}
    title, ex = s.get("name"), None
    if s["sport"] in ("sila", "wiosl", "joga"):
        try:
            det = details_for(c, user, s, phase)
            title = det.get("title") or title
            if s["sport"] == "sila":
                ex = [{"group": e.get("group"), "name": e.get("name")} for e in det.get("exercises") or []]
        except Exception as e:  # zestaw pomocniczy - ocena ma sie zapisac i bez niego
            print("trener ocena: brak zestawu:", e)
    c.execute(
        "INSERT INTO qbot_v2.trainer_rating (username, day, sport, session_id, rating, note, title, exercises) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (username, day, sport) DO UPDATE SET "
        "session_id=EXCLUDED.session_id, rating=EXCLUDED.rating, note=EXCLUDED.note, title=EXCLUDED.title, "
        "exercises=COALESCE(EXCLUDED.exercises, qbot_v2.trainer_rating.exercises), updated_at=now()",
        (user, s["day"], s["sport"], s["id"], b["rating"], b["note"], title,
         json.dumps(ex, ensure_ascii=False) if ex is not None else None))
    _mirror(s, b.get("note"))
    return {"ok": True, "day": str(s["day"])[:10], "sport": s["sport"], "rating": b["rating"], "note": b["note"]}


def recent_for_ai(c, user: str, before, days: int = 120, limit: int = 20) -> list:
    """Ostatnie oceny (najnowsze pierwsze) w zwartej formie dla AI/Alberta."""
    b = _d(before)
    c.execute("SELECT day, sport, rating, note, title FROM qbot_v2.trainer_rating WHERE username=%s AND day BETWEEN %s AND %s "
              "ORDER BY day DESC LIMIT %s", (user, b - timedelta(days=days), b + timedelta(days=13), limit))
    return [{"data": str(r["day"])[:10], "sport": SPORT_NAMES.get(r["sport"], r["sport"]), "ocena": int(r["rating"]),
             "sesja": r["title"], "komentarz": r["note"]} for r in c.fetchall()]


def text_recent(items: list) -> str:
    if not items:
        return ""
    out = ["Twoje oceny planu (1–5, najnowsze):"]
    for it in items[:8]:
        out.append(f"- {it['data']} {it['sport']}: {it['ocena']}/5" + (f" — {it['komentarz']}" if it.get("komentarz") else ""))
    return "\n".join(out)
