#!/usr/bin/env python3
"""Diety od Brokula - jadlospis -> QBot (2026-10-12). Dok.: docs/BROKUL.md

Przeplyw:
  tick (cron */15)  -> co 3 h import menu z panelu (5 dni x posilki) do qbot_v2.brokul_meals,
                       miedzy importami lekki odczyt panelu (podtrzymanie sesji),
                    -> o 20:00 Telegram: lista dzisiejszych posilkow z przyciskami,
                    -> sesja wygasla -> jedna wiadomosc z linkiem /brokul-dostep.
  przycisk ✅       -> posilek trafia do bilansu (intake_logs + intake_items, source='brokul').
  przycisk ❌       -> pominiety; jesli byl w bilansie, wpis znika. Ponowne klikniecie
                       aktualnego stanu = cofniecie (wraca do 'pending').
Do bilansu NIC nie wchodzi bez ✅ (decyzja Michala 12.10.2026).
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/opt/qbot/app")
import psycopg
from psycopg.rows import dict_row

import qbot_brokul as B

TZ = ZoneInfo("Europe/Warsaw")
IMPORT_EVERY_S = 3 * 3600
KEEPALIVE_EVERY_S = 20 * 60
NOTIFY_HOUR = 20
ACCESS_URL = "https://albert.cytr.us/brokul-dostep"
SOURCE = "brokul"
# przyblizona pora posilku (do eaten_at); dokladna godzina nie jest znana
MEAL_TIMES = {
    "śniadanie": dtime(7, 30), "ii śniadanie": dtime(10, 30), "przedtreningowy": dtime(13, 30),
    "potreningowy": dtime(16, 30), "obiad": dtime(14, 0), "podwieczorek": dtime(16, 30),
    "kolacja": dtime(19, 30),
}
_DNI = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]

# znaczniki ikon przy wartosciach (stabilne) + zapas po etykiecie
_ICON_KEY = {
    "macros-fat": "fat_g", "macros-saturated_acids": "sat_fat_g",
    "macros-carbohydrates": "carbs_g", "macros-sugar": "sugars_g",
    "macros-protein": "protein_g", "macros-salt": "salt_g",
}
_LABEL_KEY = [
    ("kwasy", "sat_fat_g"), ("tłuszcz", "fat_g"), ("cukr", "sugars_g"),
    ("węglowodan", "carbs_g"), ("białk", "protein_g"), ("sól", "salt_g"),
]


def _log(msg: str) -> None:
    print("[%s] %s" % (datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def _conn():
    import os
    kw = dict(host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
              user=os.getenv("PGUSER", "qbot"), dbname=os.getenv("PGDATABASE", "qbot"),
              row_factory=dict_row, connect_timeout=5)
    if os.getenv("PGPASSWORD"):
        kw["password"] = os.getenv("PGPASSWORD")
    return psycopg.connect(**kw)


# ======================================================================= parser
def _num(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    return float(m.group().replace(",", ".")) if m else None


def _clean(t: str) -> str:
    t = t.replace("\ufeff", "").replace("\u200b", "")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:)\]])", r"\1", t)
    t = re.sub(r"([(\[])\s+", r"\1", t)
    return t


def parse_menu(html: str, menu_item_id: str | None = None) -> list[dict]:
    """HTML strony /customer/diets/menu/item/<id>/ -> lista posilkow."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for dd in soup.select("div.meals[data-day]"):
        day = dd.get("data-day") or ""
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", day):
            continue
        order = 0
        for card in dd.find_all("div", recursive=False):
            h3 = card.find("h3")
            if not h3:
                continue
            order += 1
            meal = {"day": day, "meal_type": _clean(h3.get_text(" ")), "meal_order": order,
                    "menu_item_id": menu_item_id, "name": None, "kcal": None, "kj": None,
                    "fat_g": None, "sat_fat_g": None, "carbs_g": None, "sugars_g": None,
                    "protein_g": None, "salt_g": None, "ingredients": None, "allergen_notice": None}
            for p in card.find_all("p"):
                t = _clean(p.get_text(" "))
                if t and not t.lower().startswith("wartości"):
                    meal["name"] = t
                    break
            for li in card.find_all("li"):
                strongs = [_clean(s.get_text(" ")) for s in li.find_all("strong")]
                use = li.find("use")
                icon = (use.get("href") or use.get("xlink:href") or "").rsplit("#", 1)[-1] if use else ""
                label = _clean(li.get_text(" ")).lower()
                if icon == "macros-energy_value" or "energ" in label:
                    for s in strongs:
                        if "kcal" in s.lower():
                            meal["kcal"] = _num(s)
                        elif "kj" in s.lower():
                            meal["kj"] = _num(s)
                    continue
                key = _ICON_KEY.get(icon)
                if not key:
                    for frag, k in _LABEL_KEY:
                        if frag in label:
                            key = k
                            break
                if key and strongs and meal.get(key) is None:
                    meal[key] = _num(strongs[-1])
            text = _clean(card.get_text(" "))
            m = re.search(r"Składniki:\s*(.*?)(?=\s*Z uwagi na|\s*~\s*\d|$)", text, re.S)
            if m:
                meal["ingredients"] = m.group(1).strip() or None
            m = re.search(r"(Z uwagi na .*?\.)(?=\s*~|\s*$)", text, re.S)
            if m:
                meal["allergen_notice"] = m.group(1).strip()
            out.append(meal)
    return out


def meal_ok(m: dict) -> bool:
    """Regula QBota: kazdy wpis jedzenia z kcal i pelnymi makrami."""
    return bool(m.get("name")) and all(m.get(k) is not None for k in ("kcal", "protein_g", "carbs_g", "fat_g"))


# ======================================================================= baza
_FIELDS = ("name", "kcal", "kj", "fat_g", "sat_fat_g", "carbs_g", "sugars_g", "protein_g",
           "salt_g", "ingredients", "allergen_notice", "menu_item_id", "meal_order")


def upsert_meals(meals: list[dict]) -> dict:
    """Nowe -> insert. Istniejace 'pending' -> aktualizacja. Potwierdzonych nie ruszamy."""
    res = {"new": 0, "updated": 0, "kept_decided": 0, "invalid": 0}
    with _conn() as c:
        for m in meals:
            if not meal_ok(m):
                res["invalid"] += 1
                _log("POMINIETO niepelny posilek %s %s" % (m.get("day"), m.get("meal_type")))
                continue
            row = c.execute("SELECT id, status FROM qbot_v2.brokul_meals WHERE day=%s AND meal_type=%s",
                            (m["day"], m["meal_type"])).fetchone()
            vals = [m.get(f) for f in _FIELDS]
            if not row:
                c.execute("INSERT INTO qbot_v2.brokul_meals (day, meal_type, %s) VALUES (%%s, %%s, %s)"
                          % (", ".join(_FIELDS), ", ".join(["%s"] * len(_FIELDS))),
                          [m["day"], m["meal_type"]] + vals)
                res["new"] += 1
            elif row["status"] == "pending":
                c.execute("UPDATE qbot_v2.brokul_meals SET %s, fetched_at=now(), updated_at=now() WHERE id=%%s"
                          % ", ".join("%s=%%s" % f for f in _FIELDS), vals + [row["id"]])
                res["updated"] += 1
            else:
                res["kept_decided"] += 1
        c.commit()
    return res


def import_menu() -> dict:
    """Panel -> numery menu -> kazde menu -> parser -> baza. Rzuca B.SessionExpired."""
    ids = B.menu_ids(B.fetch("/customer/diets/"))
    if not ids:
        raise RuntimeError("w panelu nie ma linku do menu (/customer/diets/menu/item/<id>/)")
    meals = []
    for mid in ids:
        meals += parse_menu(B.fetch("/customer/diets/menu/item/%s/" % mid), mid)
    if not meals:
        raise RuntimeError("menu pobrane, ale parser nie znalazl posilkow - zmienila sie strona?")
    res = upsert_meals(meals)
    res["menu_ids"] = ids
    res["days"] = sorted({m["day"] for m in meals})
    B._state_update(last_import=time.strftime("%Y-%m-%d %H:%M:%S"), last_import_ts=time.time(),
                    last_import_result={k: v for k, v in res.items() if k != "days"})
    return res


def day_meals(day: date | str) -> list[dict]:
    with _conn() as c:
        return c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE day=%s ORDER BY meal_order, id",
                         (str(day),)).fetchall()


def _slug(meal_type: str) -> str:
    t = meal_type.lower()
    for a, b in (("ś", "s"), ("ó", "o"), ("ł", "l"), ("ą", "a"), ("ę", "e"), ("ż", "z"), ("ź", "z"), ("ć", "c"), ("ń", "n")):
        t = t.replace(a, b)
    return "brokul_" + re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _remove_intake(c, log_id) -> None:
    if log_id:
        c.execute("DELETE FROM qbot_v2.intake_items WHERE intake_log_id=%s", (log_id,))
        c.execute("DELETE FROM qbot_v2.intake_logs WHERE id=%s", (log_id,))


def set_status(meal_id: int, status: str) -> dict:
    """'eaten' -> wpis do bilansu; 'skipped'/'pending' -> wpis (jesli byl) usuniety."""
    assert status in ("eaten", "skipped", "pending")
    with _conn() as c:
        m = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE id=%s FOR UPDATE", (meal_id,)).fetchone()
        if not m:
            raise KeyError("brak posilku %s" % meal_id)
        log_id = m["intake_log_id"]
        if status == "eaten" and not log_id:
            t = MEAL_TIMES.get(m["meal_type"].lower(), dtime(12, 0))
            eaten_at = datetime.combine(m["day"], t, tzinfo=TZ)
            c.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (m["day"],))
            # realny wpis zastepuje szacunek z presetu tego dnia (inaczej podwojne liczenie)
            for o in c.execute("SELECT id FROM qbot_v2.intake_logs WHERE date=%s AND source ILIKE '%%preset%%'",
                               (m["day"],)).fetchall():
                _remove_intake(c, o["id"])
            log_id = c.execute(
                "INSERT INTO qbot_v2.intake_logs (date, eaten_at, meal_type, note, source, quality_status) "
                "VALUES (%s, %s, %s, %s, %s, 'imported') RETURNING id",
                (m["day"], eaten_at, _slug(m["meal_type"]), "Brokuł: %s" % m["meal_type"], SOURCE)).fetchone()["id"]
            c.execute(
                "INSERT INTO qbot_v2.intake_items (intake_log_id, food_name, amount, unit, kcal, protein_g, "
                "carbs_g, fat_g, fiber_g, sodium_mg, source) VALUES (%s,%s,1,'porcja',%s,%s,%s,%s,NULL,%s,%s)",
                (log_id, m["name"], m["kcal"], m["protein_g"], m["carbs_g"], m["fat_g"],
                 round(m["salt_g"] * 400, 1) if m["salt_g"] is not None else None, SOURCE))
        elif status != "eaten" and log_id:
            _remove_intake(c, log_id)
            log_id = None
        c.execute("UPDATE qbot_v2.brokul_meals SET status=%s, intake_log_id=%s, decided_at=%s, updated_at=now() "
                  "WHERE id=%s", (status, log_id, None if status == "pending" else datetime.now(TZ), meal_id))
        c.commit()
        return {"id": meal_id, "day": m["day"], "status": status, "intake_log_id": log_id}


# ======================================================================= Telegram
def _fmt(v) -> str:
    return "%.0f" % v if v is not None else "?"


def build_message(day: date) -> tuple[str, dict | None]:
    meals = day_meals(day)
    head = "🥦 Brokuł %s (%s)" % (day.strftime("%d.%m"), _DNI[day.weekday()])
    if not meals:
        return head + "\nBrak posiłków w menu na ten dzień.", None
    icon = {"eaten": "✅", "skipped": "❌", "pending": "⏳"}
    lines = [head, "Do bilansu wchodzi tylko to, co potwierdzisz ✅.", ""]
    tot = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    kb = []
    for m in meals:
        lines.append("%s %s: %s" % (icon[m["status"]], m["meal_type"], m["name"]))
        lines.append("     %s kcal · B %s · W %s · T %s g" % (_fmt(m["kcal"]), _fmt(m["protein_g"]),
                                                            _fmt(m["carbs_g"]), _fmt(m["fat_g"])))
        if m["status"] == "eaten":
            for k in tot:
                tot[k] += m[k] or 0
        mt = m["meal_type"]
        if m["status"] == "eaten":
            row = [{"text": "✔ Zjedzone: %s" % mt, "callback_data": "br:p:%d" % m["id"]},
                   {"text": "❌ Pominąłem", "callback_data": "br:s:%d" % m["id"]}]
        elif m["status"] == "skipped":
            row = [{"text": "✅ Zjadłem", "callback_data": "br:e:%d" % m["id"]},
                   {"text": "✖ Pominięte: %s" % mt, "callback_data": "br:p:%d" % m["id"]}]
        else:
            row = [{"text": "✅ %s" % mt, "callback_data": "br:e:%d" % m["id"]},
                   {"text": "❌ Pominąłem", "callback_data": "br:s:%d" % m["id"]}]
        kb.append(row)
    if any(m["status"] == "pending" for m in meals):
        kb.append([{"text": "✅ Zjadłem wszystkie pozostałe", "callback_data": "br:a:%s" % day.strftime("%Y%m%d")}])
    lines += ["", "Zjedzone: %s kcal · B %s · W %s · T %s g" % (_fmt(tot["kcal"]), _fmt(tot["protein_g"]),
                                                               _fmt(tot["carbs_g"]), _fmt(tot["fat_g"]))]
    return "\n".join(lines), {"inline_keyboard": kb}


def _chat_id() -> str:
    import qbot_config as cfg
    return str(cfg.TELEGRAM_CHAT_ID)


def send_day(day: date, force: bool = False) -> bool:
    from qbot_telegram_client import _api
    with _conn() as c:
        if not force and c.execute("SELECT 1 FROM qbot_v2.brokul_notify WHERE day=%s", (day,)).fetchone():
            return False
    if not day_meals(day):
        return False
    text, kb = build_message(day)
    chat = _chat_id()
    r = _api("sendMessage", {"chat_id": chat, "text": text, "reply_markup": kb})
    if not (r and r.get("ok")):
        raise RuntimeError("sendMessage nie powiodl sie: %s" % (r or {}).get("description"))
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.brokul_notify (day, chat_id, message_id) VALUES (%s,%s,%s) "
                  "ON CONFLICT (day) DO UPDATE SET chat_id=EXCLUDED.chat_id, message_id=EXCLUDED.message_id, sent_at=now()",
                  (day, chat, r["result"]["message_id"]))
        c.commit()
    return True


def handle_callback(cq, tg_answer_callback, tg_send_plain, tg_edit_markup, chat_id_allowed):
    """Przyciski 'br:e|s|p:<id>' i 'br:a:<YYYYMMDD>' (telegram_reply_processor)."""
    from qbot_telegram_client import _api
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    if chat != str(chat_id_allowed):
        tg_answer_callback(cq.get("id"), "Brak dostepu")
        return
    parts = data.split(":")
    act, arg = (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else "")
    try:
        if act in ("e", "s", "p"):
            r = set_status(int(arg), {"e": "eaten", "s": "skipped", "p": "pending"}[act])
            day = r["day"]
            tg_answer_callback(cq.get("id"), {"e": "Zapisane w bilansie", "s": "Pominięte",
                                              "p": "Cofnięte"}[act])
        elif act == "a":
            day = datetime.strptime(arg, "%Y%m%d").date()
            n = 0
            for m in day_meals(day):
                if m["status"] == "pending":
                    set_status(m["id"], "eaten")
                    n += 1
            tg_answer_callback(cq.get("id"), "Zapisano %d posiłków" % n)
        else:
            tg_answer_callback(cq.get("id"))
            return
    except Exception as e:
        tg_answer_callback(cq.get("id"), "Błąd zapisu")
        tg_send_plain("⚠️ Brokuł: nie udało się zapisać (%s)." % type(e).__name__)
        raise
    text, kb = build_message(day)
    _api("editMessageText", {"chat_id": chat, "message_id": msg.get("message_id"), "text": text,
                             "reply_markup": kb or {"inline_keyboard": []}})


def _notify_expired() -> None:
    st = B.state()
    if st.get("expired_notified"):
        return
    from qbot_telegram_client import _api
    _api("sendMessage", {"chat_id": _chat_id(), "disable_web_page_preview": True,
                         "text": "🥦 Brokuł: sesja wygasła, menu się nie pobiera.\n"
                                 "Zaloguj się na dietyodbrokula.pl i wklej nowe ciasteczka:\n" + ACCESS_URL})
    B._state_update(expired_notified=time.strftime("%Y-%m-%d %H:%M:%S"))


# ======================================================================= tick
def tick(now: datetime | None = None) -> None:
    now = now or datetime.now(TZ)
    st = B.state()
    session_ok = B.SESSION_FILE.exists()
    if session_ok:
        try:
            last_imp = float(st.get("last_import_ts") or 0)
            if time.time() - last_imp >= IMPORT_EVERY_S:
                res = import_menu()
                _log("import OK: %s" % res)
            else:
                last_ok = st.get("last_ok")
                age = (now.replace(tzinfo=None) - datetime.strptime(last_ok, "%Y-%m-%d %H:%M:%S")).total_seconds() if last_ok else 1e9
                if age >= KEEPALIVE_EVERY_S:
                    B.fetch("/customer/diets/")
                    _log("keepalive OK")
        except B.SessionExpired:
            _log("SESJA WYGASLA")
            _notify_expired()
        except Exception as e:
            _log("blad importu: %s: %s" % (type(e).__name__, e))
    else:
        _log("brak sesji (.brokul_session)")
    if now.hour >= NOTIFY_HOUR:
        try:
            if send_day(now.date()):
                _log("wyslano podsumowanie %s" % now.date())
        except Exception as e:
            _log("blad wysylki Telegram: %s" % e)


if __name__ == "__main__":
    tick()
