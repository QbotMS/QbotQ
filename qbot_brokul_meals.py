#!/usr/bin/env python3
"""Diety od Brokula - jadlospis -> QBot. Dok.: docs/BROKUL.md

Ten modul: dane Brokula (menu, harmonogram dostaw, statusy posilkow, lodowka) + tick crona.
Wiadomosc dnia (20:00), logowanie jedzenia spoza diety i przyciski szybkie: qbot_food_log.py.

Statusy posilku (brokul_meals.status):
  pending    - brak decyzji
  eaten      - zjedzony w dniu eaten_day (zwykle = day; z lodowki = pozniejszy dzien) -> wpis w intake_*
  skipped    - nie zjedzony (pominiety)
  fridge     - 'zjem pozniej' (lodowka); wraca w kolejnych dniach w wiadomosci dnia
  discarded  - z lodowki wyrzucony
  cancelled  - dzien odwolany/przeniesiony w panelu (nie ma go w harmonogramie dostaw)
Do bilansu wchodzi WYLACZNIE 'eaten' (decyzja Michala 12.10.2026).
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
END_REMIND_DAYS = 2
ACCESS_URL = "https://albert.cytr.us/brokul-dostep"
SOURCE = "brokul"
MEAL_TIMES = {
    "śniadanie": dtime(7, 30), "ii śniadanie": dtime(10, 30), "przedtreningowy": dtime(13, 30),
    "potreningowy": dtime(16, 30), "obiad": dtime(14, 0), "podwieczorek": dtime(16, 30),
    "kolacja": dtime(19, 30),
}
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


def parse_delivery_days(html: str) -> list[str]:
    """Strona /customer/diets/day/order_item_id/<id>/ -> daty dostaw (ISO)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    main = soup.find("main") or soup
    out = set()
    for d, m, y in re.findall(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", main.get_text("\n")):
        try:
            out.add(date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            pass
    return sorted(out)


def meal_ok(m: dict) -> bool:
    """Regula QBota: kazdy wpis jedzenia z kcal i pelnymi makrami."""
    return bool(m.get("name")) and all(m.get(k) is not None for k in ("kcal", "protein_g", "carbs_g", "fat_g"))


# ======================================================================= baza
_FIELDS = ("name", "kcal", "kj", "fat_g", "sat_fat_g", "carbs_g", "sugars_g", "protein_g",
           "salt_g", "ingredients", "allergen_notice", "menu_item_id", "meal_order")


def upsert_meals(meals: list[dict]) -> dict:
    """Nowe -> insert. Istniejace 'pending'/'cancelled' -> aktualizacja (cancelled wraca do pending). Reszty nie ruszamy."""
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
            elif row["status"] in ("pending", "cancelled"):
                c.execute("UPDATE qbot_v2.brokul_meals SET %s, status='pending', fetched_at=now(), updated_at=now() WHERE id=%%s"
                          % ", ".join("%s=%%s" % f for f in _FIELDS), vals + [row["id"]])
                res["updated"] += 1
            else:
                res["kept_decided"] += 1
        c.commit()
    return res


def sync_delivery(order_item_id: str, days: list[str]) -> dict:
    """Zapis harmonogramu + odwolane dni: posilki 'pending' z dni zamowienia, ktorych nie ma w harmonogramie."""
    if not days:
        return {"days": 0, "cancelled": 0}
    with _conn() as c:
        c.execute("DELETE FROM qbot_v2.brokul_delivery_days WHERE order_item_id=%s", (order_item_id,))
        for d in days:
            c.execute("INSERT INTO qbot_v2.brokul_delivery_days (day, order_item_id) VALUES (%s,%s)", (d, order_item_id))
        n = c.execute("UPDATE qbot_v2.brokul_meals SET status='cancelled', updated_at=now() "
                      "WHERE menu_item_id=%s AND status='pending' AND NOT (day = ANY(%s::date[]))",
                      (order_item_id, days)).rowcount
        c.commit()
    return {"days": len(days), "cancelled": n}


def import_menu() -> dict:
    """Panel -> numery menu -> harmonogram dostaw + menu -> baza. Rzuca B.SessionExpired."""
    ids = B.menu_ids(B.fetch("/customer/diets/"))
    if not ids:
        raise RuntimeError("w panelu nie ma linku do menu (/customer/diets/menu/item/<id>/)")
    meals, deliv = [], {}
    for mid in ids:
        meals += parse_menu(B.fetch("/customer/diets/menu/item/%s/" % mid), mid)
        try:
            deliv[mid] = parse_delivery_days(B.fetch("/customer/diets/day/order_item_id/%s/" % mid))
        except B.SessionExpired:
            raise
        except Exception as e:
            _log("harmonogram %s: blad %s" % (mid, e))
    if not meals:
        raise RuntimeError("menu pobrane, ale parser nie znalazl posilkow - zmienila sie strona?")
    res = upsert_meals(meals)
    for mid, days in deliv.items():
        res["delivery_" + mid] = sync_delivery(mid, days)
    res["menu_ids"] = ids
    res["days"] = sorted({m["day"] for m in meals})
    B._state_update(last_import=time.strftime("%Y-%m-%d %H:%M:%S"), last_import_ts=time.time(),
                    last_import_result={k: v for k, v in res.items() if k != "days"})
    return res


def day_meals(day: date | str) -> list[dict]:
    """Posilki DOSTARCZONE danego dnia (bez odwolanych)."""
    with _conn() as c:
        return c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE day=%s AND status<>'cancelled' "
                         "ORDER BY meal_order, id", (str(day),)).fetchall()


def fridge_for(day: date | str) -> list[dict]:
    """Lodowka widoczna w dniu 'day': odlozone wczesniej + zjedzone/wyrzucone z lodowki tego dnia."""
    with _conn() as c:
        return c.execute(
            "SELECT * FROM qbot_v2.brokul_meals WHERE day < %s AND ("
            " (status='fridge') OR (status='eaten' AND eaten_day=%s AND eaten_day<>day)"
            " OR (status='discarded' AND decided_at::date=%s)) ORDER BY day, meal_order",
            (str(day), str(day), str(day))).fetchall()


def delivery_end() -> date | None:
    with _conn() as c:
        r = c.execute("SELECT max(day) d FROM qbot_v2.brokul_delivery_days").fetchone()
    return r["d"] if r else None


def _slug(meal_type: str) -> str:
    t = meal_type.lower()
    for a, b in (("ś", "s"), ("ó", "o"), ("ł", "l"), ("ą", "a"), ("ę", "e"), ("ż", "z"), ("ź", "z"), ("ć", "c"), ("ń", "n")):
        t = t.replace(a, b)
    return "brokul_" + re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def remove_intake(c, log_id) -> None:
    if log_id:
        c.execute("DELETE FROM qbot_v2.intake_items WHERE intake_log_id=%s", (log_id,))
        c.execute("DELETE FROM qbot_v2.intake_logs WHERE id=%s", (log_id,))


def drop_preset(c, day) -> None:
    """Realny wpis zastepuje szacunek z presetu tego dnia (inaczej podwojne liczenie)."""
    for o in c.execute("SELECT id FROM qbot_v2.intake_logs WHERE date=%s AND source ILIKE '%%preset%%'", (day,)).fetchall():
        remove_intake(c, o["id"])


def set_status(meal_id: int, status: str, eaten_day: date | None = None) -> dict:
    """eaten -> wpis do bilansu w dniu eaten_day (domyslnie dzien dostawy); kazdy inny status -> wpis usuniety."""
    assert status in ("eaten", "skipped", "pending", "fridge", "discarded")
    with _conn() as c:
        m = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE id=%s FOR UPDATE", (meal_id,)).fetchone()
        if not m:
            raise KeyError("brak posilku %s" % meal_id)
        log_id = m["intake_log_id"]
        ed = eaten_day or m["day"]
        if log_id and (status != "eaten" or m["eaten_day"] != ed):
            remove_intake(c, log_id)
            log_id = None
        if status == "eaten" and not log_id:
            t = MEAL_TIMES.get(m["meal_type"].lower(), dtime(12, 0)) if ed == m["day"] else dtime(13, 0)
            c.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (ed,))
            drop_preset(c, ed)
            note = "Brokuł: %s" % m["meal_type"] + ("" if ed == m["day"] else " (z lodówki, dostawa %s)" % m["day"].strftime("%d.%m"))
            log_id = c.execute(
                "INSERT INTO qbot_v2.intake_logs (date, eaten_at, meal_type, note, source, quality_status) "
                "VALUES (%s, %s, %s, %s, %s, 'imported') RETURNING id",
                (ed, datetime.combine(ed, t, tzinfo=TZ), _slug(m["meal_type"]), note, SOURCE)).fetchone()["id"]
            c.execute(
                "INSERT INTO qbot_v2.intake_items (intake_log_id, food_name, amount, unit, kcal, protein_g, "
                "carbs_g, fat_g, fiber_g, sodium_mg, source) VALUES (%s,%s,1,'porcja',%s,%s,%s,%s,NULL,%s,%s)",
                (log_id, m["name"], m["kcal"], m["protein_g"], m["carbs_g"], m["fat_g"],
                 round(m["salt_g"] * 400, 1) if m["salt_g"] is not None else None, SOURCE))
        c.execute("UPDATE qbot_v2.brokul_meals SET status=%s, intake_log_id=%s, eaten_day=%s, decided_at=%s, updated_at=now() "
                  "WHERE id=%s", (status, log_id, ed if status == "eaten" else None,
                                  None if status == "pending" else datetime.now(TZ), meal_id))
        c.commit()
        return {"id": meal_id, "day": m["day"], "status": status, "eaten_day": ed if status == "eaten" else None}


# ======================================================================= Telegram: przyciski Brokula
def handle_callback(cq, tg_answer_callback, tg_send_plain, tg_edit_markup, chat_id_allowed):
    """br:<akcja>:<id>|<RRRRMMDD>[:<dzien wiadomosci RRRRMMDD>]
       e zjadlem / s nie zjadlem / p cofnij / f do lodowki / d zjadlem z lodowki (w dniu wiadomosci)
       w wyrzucone / a wszystkie pozostale zjedzone / z wszystkie pozostale do lodowki."""
    import qbot_food_log as F
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    if chat != str(chat_id_allowed):
        tg_answer_callback(cq.get("id"), "Brak dostepu")
        return
    parts = data.split(":")
    act, arg = (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else "")
    mday = datetime.strptime(parts[3], "%Y%m%d").date() if len(parts) > 3 else None
    try:
        if act in ("e", "s", "p", "f", "d", "w"):
            st = {"e": "eaten", "s": "skipped", "p": "pending", "f": "fridge", "d": "eaten", "w": "discarded"}[act]
            r = set_status(int(arg), st, eaten_day=mday if act == "d" else None)
            day = mday or r["day"]
            tg_answer_callback(cq.get("id"), {"e": "Zapisane w bilansie", "s": "Nie zjedzone", "p": "Cofnięte",
                                              "f": "Do lodówki", "d": "Zjedzone dziś", "w": "Wyrzucone"}[act])
        elif act in ("a", "z"):
            day = datetime.strptime(arg, "%Y%m%d").date()
            n = 0
            for m in day_meals(day):
                if m["status"] == "pending":
                    set_status(m["id"], "eaten" if act == "a" else "fridge")
                    n += 1
            tg_answer_callback(cq.get("id"), ("Zjedzone: %d" if act == "a" else "Do lodówki: %d") % n)
        else:
            tg_answer_callback(cq.get("id"))
            return
    except Exception as e:
        tg_answer_callback(cq.get("id"), "Błąd zapisu")
        tg_send_plain("⚠️ Brokuł: nie udało się zapisać (%s)." % type(e).__name__)
        raise
    F.refresh_day(day, chat_id=chat, message_id=msg.get("message_id"))


def _notify_expired() -> None:
    st = B.state()
    if st.get("expired_notified"):
        return
    import qbot_food_log as F
    F.tg_send("🥦 Brokuł: sesja wygasła, menu się nie pobiera.\n"
              "Zaloguj się na dietyodbrokula.pl i wklej nowe ciasteczka:\n" + ACCESS_URL)
    B._state_update(expired_notified=time.strftime("%Y-%m-%d %H:%M:%S"))


def _remind_end(now: datetime) -> None:
    """Rano (7:00-9:59), gdy do konca zamowienia zostaly <= 2 dni dostaw - raz na koniec zamowienia."""
    end = delivery_end()
    if not end or not (7 <= now.hour < 10):
        return
    left = (end - now.date()).days
    if left < 0 or left > END_REMIND_DAYS:
        return
    key = "end_reminded_%s" % end.isoformat()
    if B.state().get(key):
        return
    import qbot_food_log as F
    F.tg_send("🥦 Dieta Brokuła kończy się %s (%s). Przedłużone? Jeśli tak, QBot sam zobaczy nowe zamówienie."
              % (end.strftime("%d.%m"), F.DNI[end.weekday()]))
    B._state_update(**{key: time.strftime("%Y-%m-%d %H:%M:%S")})


# ======================================================================= tick
def tick(now: datetime | None = None) -> None:
    import qbot_food_log as F
    now = now or datetime.now(TZ)
    st = B.state()
    if B.SESSION_FILE.exists():
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
    # 2026-10-12: koniec diety -> linia w porannej wiadomosci (qbot_food_plan.morning_digest), bez osobnej wysylki
    try:  # 2026-10-12: zalecenia AI tygodnia (Jedzenie -> Analiza) - same, w niedziele od 21:00, raz na tydzien, bez wiadomosci
        if now.weekday() == 6 and now.hour >= 21:
            import qbot_food_api as FA
            FA.week_ai(now.date(), force=False)
    except Exception as e:
        _log("AI tygodnia: %s" % e)
    try:
        n = F.retry_pending()
        if n:
            _log("dokonczono wpisow jedzenia: %d" % n)
    except Exception as e:
        _log("retry jedzenia: %s" % e)
    try:
        import qbot_food_plan as FP
        for l in FP.tick(now):
            _log(l)
    except Exception as e:
        _log("plan jedzenia: %s" % e)
    if now.hour >= NOTIFY_HOUR:
        try:
            if F.send_day(now.date()):
                _log("wyslano wiadomosc dnia %s" % now.date())
        except Exception as e:
            _log("blad wysylki Telegram: %s" % e)


if __name__ == "__main__":
    tick()
