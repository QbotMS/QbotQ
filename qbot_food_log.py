#!/usr/bin/env python3
"""Jedzenie spoza diety + wiadomosc dnia (2026-10-12). Dok.: docs/BROKUL.md

Telegram (telegram_reply_processor): kazdy wolny tekst i kazde zdjecie = jedzenie.
  1) surowa tresc ZAWSZE najpierw do qbot_v2.food_entries (nic nie ginie, idempotencja po tg_message_id),
  2) dzien: 'wczoraj', 'przedwczoraj', dzien tygodnia, DD.MM; domyslnie dzis, 00:00-03:59 = poprzedni dzien,
  3) katalog Michala (food_catalog) -> 'jak zwykle' bez AI, gdy ta sama porcja potwierdzona >= 2 razy,
  4) inaczej AI (Anthropic) szacuje kcal + pelne makra; gdy porcja niejasna -> pytanie przyciskami,
  5) potwierdzenie z numerem i data + [mniej][OK][wiecej][dzien wczesniej][usun].
Wiadomosc dnia (20:00): Brokul (zjadlem / nie / lodowka), lodowka, wpisy poza dieta, szybkie przyciski,
suma dnia z intake_*, stan zamkniecia dnia (pod pas Jedzenia).
Przyciski: fd:<akcja>:<id>[:<n>] (wpisy), qk:<RRRRMMDD>:<kod> (szybkie), br:... (Brokul -> qbot_brokul_meals).
"""
from __future__ import annotations

import base64
import json
import re
import time
import sys
import unicodedata
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/opt/qbot/app")

TZ = ZoneInfo("Europe/Warsaw")
DNI = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
SOURCE = "telegram"
# szybkie przyciski: (etykieta, kcal, B, W, T) - zgrubne, kalibracja waga wyrownuje blad
QUICK = {
    "snack": ("Przekąska", 250, 6, 30, 12),
    "sweet": ("Słodycze", 350, 4, 45, 17),
    "out_s": ("Posiłek na mieście (mały)", 600, 25, 60, 28),
    "out_m": ("Posiłek na mieście (średni)", 900, 35, 90, 42),
    "out_l": ("Posiłek na mieście (duży)", 1300, 50, 130, 62),
    # dni bez diety: posilki S/M/L (B ~20%, W ~45%, T ~35% energii)
    "bf_s": ("Śniadanie (małe)", 350, 18, 39, 14), "bf_m": ("Śniadanie (średnie)", 550, 28, 62, 21),
    "bf_l": ("Śniadanie (duże)", 800, 40, 90, 31),
    "ln_s": ("Obiad (mały)", 600, 30, 68, 23), "ln_m": ("Obiad (średni)", 900, 45, 101, 35),
    "ln_l": ("Obiad (duży)", 1300, 65, 146, 51),
    "dn_s": ("Kolacja (mała)", 450, 23, 51, 18), "dn_m": ("Kolacja (średnia)", 700, 35, 79, 27),
    "dn_l": ("Kolacja (duża)", 1000, 50, 113, 39),
}
SCALE_STEP = 0.25
CATALOG_AUTO_N = 2

_WD = [("poniedzia", 0), ("wtor", 1), ("środ", 2), ("srod", 2), ("czwart", 3), ("piąt", 4), ("piat", 4),
       ("sobot", 5), ("niedziel", 6)]
_DATE_WORDS = re.compile(
    r"\b(dzi[śs](iaj)?|wczoraj|przedwczoraj|rano|wieczorem|po po[łl]udniu|w nocy|"
    r"w\s+)?(poniedzia\w*|wtor\w*|[śs]rod\w*|czwart\w*|pi[ąa]t\w*|sobot\w*|niedziel\w*)\b|"
    r"\b(dzi[śs](iaj)?|wczoraj|przedwczoraj)\b|\b\d{1,2}\.\d{2}(\.\d{2,4})?\b", re.I)


def _log(msg: str) -> None:
    print("[%s] food: %s" % (datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def _conn():
    from qbot_brokul_meals import _conn as c
    return c()


# ======================================================================= czyste funkcje
def parse_day(text: str, now: datetime) -> date:
    """Dzien wpisu z tekstu. Domyslnie dzis; 00:00-03:59 = poprzedni dzien."""
    t = (text or "").lower()
    today = now.date()
    m = re.search(r"\b(\d{1,2})\.(\d{2})(?:\.(\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            cand = date(y, mo, d)
            if not m.group(3) and cand > today:
                cand = date(y - 1, mo, d)
            if cand <= today:
                return cand
        except ValueError:
            pass
    if re.search(r"\bprzedwczoraj\b", t):
        return today - timedelta(days=2)
    if re.search(r"\bwczoraj\b", t):
        return today - timedelta(days=1)
    if re.search(r"\bdzi[śs](iaj)?\b", t):
        return today
    for stem, wd in _WD:
        if re.search(r"\b" + stem, t):
            back = (today.weekday() - wd) % 7
            return today - timedelta(days=back)
    if now.hour < 4:
        return today - timedelta(days=1)
    return today


def norm_phrase(text: str) -> str:
    t = _DATE_WORDS.sub(" ", (text or "").lower())
    t = unicodedata.normalize("NFKD", t.replace("ł", "l"))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def clean_items(items) -> list[dict] | None:
    """Kazda pozycja z nazwa, kcal i pelnymi makrami (regula QBota) - inaczej None."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            return None
        x = {"name": str(it.get("name") or "").strip()[:120], "portion": str(it.get("portion") or "").strip()[:60],
             "kcal": _f(it.get("kcal")), "protein_g": _f(it.get("protein_g")),
             "carbs_g": _f(it.get("carbs_g")), "fat_g": _f(it.get("fat_g")),
             "conf": {"pewne": "pewne", "średnie": "średnie", "srednie": "średnie"}.get(str(it.get("conf") or "").strip().lower(), "zgrubne"),
             "src": str(it.get("src") or "").strip()[:40],
             "short": _fit_short(str(it.get("short") or "").strip())}
        if not x["name"] or any(x[k] is None or x[k] < 0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")):
            return None
        out.append(x)
    return out or None


def totals(items: list[dict], scale: float = 1.0) -> dict:
    return {k: round(sum((i.get(k) or 0) for i in items) * scale, 1) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}


def _fmt(v) -> str:
    return "%.0f" % v if v is not None else "?"


def _esc(t) -> str:
    import html as _h
    return _h.escape(str(t or ""), quote=False)


def _fit_short(s: str, n: int = 24) -> str:
    """Skrot do n znakow bez ciecia ilosci w polowie (17.10: 'Konjac wolow.+warzywa 30' z '... 300 g')."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    m = re.search(r"\s(~?[\d.,]+\s?(?:g|ml|kg|l|szt\.?)|×\s?\d+)$", s)
    if m and len(m.group(0)) < n - 4:
        q = m.group(0); return s[:m.start()][:n - len(q) - 1].rstrip() + "…" + q
    return s[:n - 1].rstrip() + "…"


def _short(it: dict) -> str:
    sh = (it.get("short") or "").strip()
    if not sh:
        nm, po = it["name"], (it.get("portion") or "")
        sh = nm if len(nm) <= 22 else nm[:21].rstrip() + "…"
        if po and len(sh) + len(po) <= 21:
            sh += " " + po
    return _fit_short(sh)


def receipt_text(e: dict) -> str:
    """HTML: naglowek z suma, makra, tabela 'kcal | pozycja' w bloku stalej szerokosci, legenda."""
    d = e["day"]
    sc = e.get("scale") or 1
    items = e["items"] or []
    t = totals(items, sc)
    head = "✅ <b>#%d · %s %s · %s kcal</b>" % (e["id"], DNI[d.weekday()], d.strftime("%d.%m"), _fmt(t["kcal"]))
    sub = "B %s · W %s · T %s g" % (_fmt(t["protein_g"]), _fmt(t["carbs_g"]), _fmt(t["fat_g"]))
    if abs(sc - 1) > 1e-6:
        sub += " · ×%.2f" % sc
    if e.get("_from_catalog"):
        sub += " · jak zwykle"
    mk = {"pewne": " ", "średnie": "~", "zgrubne": "?"}
    rows = ["%4s%s %s" % (_fmt((it["kcal"] or 0) * sc), mk.get(it.get("conf"), " "), _short(it)) for it in items]
    out = [head, sub, "<pre>" + _esc("\n".join(rows)) + "</pre>"]
    marks = {it.get("conf") for it in items}
    leg = []
    if "zgrubne" in marks:
        leg.append("? zgrubnie")
    if "średnie" in marks:
        leg.append("~ średnio")
    if leg or len(items) > 1:
        out.append("<i>%sPopraw: odpowiedz na tę wiadomość, np. „makaron ok. 600 g”.</i>" % ((" · ".join(leg) + ". ") if leg else ""))
    return "\n".join(out)


def receipt_kb(eid: int) -> dict:
    return {"inline_keyboard": [
        [{"text": "➖ mniej", "callback_data": "fd:m:%d" % eid}, {"text": "✔ OK", "callback_data": "fd:k:%d" % eid},
         {"text": "➕ więcej", "callback_data": "fd:p:%d" % eid}],
        [{"text": "← dzień wcześniej", "callback_data": "fd:b:%d" % eid}, {"text": "🗑 usuń", "callback_data": "fd:x:%d" % eid}]]}


# ======================================================================= AI
_PROMPT = """Szacujesz wartości odżywcze jedzenia/napojów, które użytkownik (dorosły mężczyzna w Polsce) zjadł.
Zwracasz WYŁĄCZNIE JSON, bez komentarza:
{"not_food": false, "ambiguous": false, "time": null, "items": [{"name": "...", "portion": "...", "kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "conf": "pewne|średnie|zgrubne", "src": "...", "short": "..."}], "question": null, "options": null}
Zasady:
- Pomiń słowa o czasie ("wczoraj", "w sobotę", "rano", daty) - opisują kiedy, nie co.
- "time": godzina jedzenia "HH:MM", TYLKO gdy użytkownik ją podał (np. "11:10", "o 21", "o 21:30"); inaczej null.
- "short": nazwa RAZEM z ilością, max 22 znaki (np. "Racuchy ×6", "Makaron Kojak ~400 g", "Chrupki HiProt. 60 g").
- Każda pozycja: krótka polska nazwa, porcja słowami (np. "cała ~30 cm", "2 szt.", "0,5 l"), kcal i PEŁNE makra (liczby).
- ZAWSZE odpowiadasz samym JSON-em. Nigdy tabel, list, pytań ani komentarzy tekstem.
- Gdy w wiadomości jest WIĘCEJ NIŻ JEDNA pozycja -> NIGDY nie pytaj ("ambiguous": false): dla każdej przyjmij typową porcję
  i opisz ją wprost w "portion" (np. "porcja ~350 g", "kawałek ~100 g", "całe opakowanie 70 g").
- Gdy ilość podana -> użyj jej. Typowe pojedyncze sztuki (pączek, banan, baton, jabłko, piwo 0,5 l, kawa) -> przyjmij 1 typową sztukę bez pytania.
- Gdy jest JEDNA pozycja, ilości NIE podano, a realne porcje różnią się ponad 2x (pizza, ciasto, makaron, frytki, lody, sałatka, zupa, chipsy...) ->
  "ambiguous": true, "question": krótko np. "Pizza – ile?", "options": 3-4 warianty [{"label": "1 kawałek", "items": [...pełne pozycje dla tego wariantu, z wszystkimi produktami z wiadomości...]}],
  label max 18 znaków; wtedy "items": null.
- Sieciówki (McDonald's, KFC, Żabka, Starbucks) i produkty paczkowane -> wartości producenta, jeśli je znasz.
- Zdjęcie: szacuj widoczną porcję; etykieta z tabelą wartości -> przepisz ją i przelicz na zjedzoną ilość.
- KILKA zdjęć = JEDEN wpis (jeden posiłek): wypisz pozycje ze WSZYSTKICH zdjęć w jednej liście, nigdy nie pytaj
  ("ambiguous": false). Ten sam produkt widoczny na kilku zdjęciach (np. przód opakowania i etykieta) licz RAZ.
- Nie jedzenie i nie napój -> {"not_food": true}.
- HISTORIA (jeśli podana) to wcześniejsze wpisy TEGO użytkownika. Gdy pozycja to ten sam produkt/danie -> użyj jego
  wartości i wielkości porcji (przelicz, jeśli ilość inna); wtedy "src": "historia DD.MM", "conf": "pewne".
- "conf": "pewne" = historia, etykieta ze zdjęcia albo dokładnie znana wartość producenta przy podanej ilości;
  "średnie" = znany produkt, ale ilość lub wariant zgadywane; "zgrubne" = porcja i skład zgadywane (dania domowe, restauracje).
  Nie zawyżaj pewności.
- BAZA PRODUKTÓW (Open Food Facts, wartości na 100 g; wyniki wyszukiwania bywają nietrafione) -> użyj TYLKO, gdy to na pewno
  ten sam produkt (marka i nazwa się zgadzają); przelicz na zjedzoną ilość; "src": "Open Food Facts". "src": krótko skąd wartości (np. "historia 27.06", "etykieta", "wartości producenta", "szacunek").
"""


def _ai_json(system: str, content: list) -> dict:
    """Anthropic -> obiekt JSON. Bez JSON-a jedna prosba o poprawke. Rzuca przy bledzie."""
    import httpx
    import qbot_config as cfg
    from qgpt_client import parse_json_text
    msgs = [{"role": "user", "content": content}]
    for _ in range(2):
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"content-type": "application/json", "x-api-key": cfg.ANTHROPIC_API_KEY,
                                "anthropic-version": "2023-06-01"},
                       json={"model": cfg.ANTHROPIC_MODEL, "max_tokens": 4000, "temperature": 0, "system": system,
                             "messages": msgs},
                       timeout=90)
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        a, b = txt.find("{"), txt.rfind("}")
        try:
            j = parse_json_text(txt[a:b + 1]) if 0 <= a < b else None
        except ValueError:
            j = None
        if isinstance(j, dict):
            return j
        msgs = msgs + [{"role": "assistant", "content": txt or "?"},
                       {"role": "user", "content": "To nie jest JSON. Odpowiedz WYŁĄCZNIE JSON-em wg schematu, bez pytań."}]
    raise ValueError("AI: brak JSON w odpowiedzi")


_STOP = {"porcja", "porcji", "kawalek", "kawalki", "kawalkow", "sztuk", "sztuki", "srednie", "srednich", "duza", "duzy",
         "duze", "mala", "maly", "male", "jedna", "jeden", "okolo", "troche", "jakies", "biedronki", "biedronka", "lidla",
         "lidl", "zabki", "zabka", "oraz", "potem", "rano", "wieczorem"}


def _toks(t: str) -> set[str]:
    return {w[:5] for w in norm_phrase(t).split() if len(w) >= 4 and not w.isdigit() and w not in _STOP}


def history_refs(text: str, limit: int = 8) -> list[dict]:
    """Wczesniejsze wpisy Michala podobne do tekstu (bez Brokula i szacunkow presetu) - punkt odniesienia dla AI."""
    q = _toks(text or "")
    if not q:
        return []
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT ON (lower(i.food_name)) l.date, i.food_name, i.kcal, i.protein_g, i.carbs_g, i.fat_g "
            "FROM qbot_v2.intake_items i JOIN qbot_v2.intake_logs l ON l.id=i.intake_log_id "
            "WHERE COALESCE(l.source,'') <> 'brokul' AND COALESCE(l.source,'') NOT ILIKE '%%preset%%' "
            "AND COALESCE(l.meal_type,'') <> 'quick' AND i.kcal IS NOT NULL AND i.kcal > 0 "
            "AND i.food_name NOT LIKE 'Posiłek na mieście%%' AND i.food_name NOT IN ('Przekąska','Słodycze') "
            "ORDER BY lower(i.food_name), l.date DESC").fetchall()
    scored = []
    for r in rows:
        hit = len(q & _toks(r["food_name"]))
        if hit:
            scored.append((hit, r["date"], r))
    scored.sort(key=lambda x: (-x[0], -x[1].toordinal()))
    out = []
    for hit, d, r in scored[:limit]:
        out.append({"date": r["date"].strftime("%d.%m"), "name": r["food_name"], "kcal": r["kcal"],
                    "protein_g": r["protein_g"], "carbs_g": r["carbs_g"], "fat_g": r["fat_g"]})
    return out


def estimate(text: str | None, image: tuple[bytes, str] | None = None, refs: list | None = None,
             off: list | None = None) -> dict:
    """AI -> {'not_food'|'ambiguous', items|options, question}. Rzuca przy bledzie."""
    content = []
    imgs = image if isinstance(image, list) else ([image] if image else [])   # 18.10: album = kilka zdjec
    for im in imgs:
        content.append({"type": "image", "source": {"type": "base64", "media_type": im[1],
                                                    "data": base64.b64encode(im[0]).decode()}})
    msg = ("Wiadomość użytkownika (%d zdjęć – jeden wpis): " % len(imgs) if len(imgs) > 1 else "Wiadomość użytkownika: ") + \
        (text or ("(same zdjęcia)" if len(imgs) > 1 else "(samo zdjęcie)"))
    if refs:
        msg += "\n\nHISTORIA użytkownika (podobne wcześniejsze wpisy):\n" + "\n".join(
            "- %s | %s | %s kcal, B %s, W %s, T %s" % (r["date"], r["name"], r["kcal"], r["protein_g"], r["carbs_g"], r["fat_g"])
            for r in refs)
    if off:
        msg += "\n\nBAZA PRODUKTÓW (Open Food Facts, na 100 g):\n" + "\n".join(
            "- [%s] %s | %s | %s | %s kcal, B %s, W %s, T %s" % (o["q"], o["name"], o["brands"], o["quantity"] or "?",
                                                               o["kcal"], o["p"], o["c"], o["f"]) for o in off)
    content.append({"type": "text", "text": msg})
    j = _ai_json(_PROMPT, content)
    if j.get("not_food"):
        return {"not_food": True}
    if j.get("ambiguous") and j.get("options"):
        opts = []
        for o in j["options"][:4]:
            it = clean_items((o or {}).get("items"))
            if it:
                opts.append({"label": str(o.get("label") or "?")[:24], "items": it})
        if len(opts) >= 2:
            return {"ambiguous": True, "question": str(j.get("question") or "Ile?")[:80], "options": opts, "time": _hhmm(j.get("time"))}
    it = clean_items(j.get("items"))
    if not it:
        raise ValueError("AI: brak pelnych wartosci (kcal + makra)")
    return {"items": it, "time": _hhmm(j.get("time"))}


def _hhmm(v):
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(v or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


_STORES = ("lidl", "biedronk", "żabk", "zabk", "auchan", "kaufland", "carrefour", "dino", "aldi", "netto", "stokrot", "rossmann")
_STORE_RE = re.compile(r"(?i)\b(z\s+|ze\s+)?(lidla?|biedronki|biedronka|żabki|żabka|zabki|auchan|kaufland|carrefoura?|dino|aldi|netto|stokrotki|rossmanna?)\b")


def off_refs(text: str, limit: int = 6, budget_s: float = 7.0) -> list[dict]:
    """Open Food Facts dla fragmentow z marka/sklepem (search.openfoodfacts.org). Bledy i brak sieci = pusta lista."""
    import httpx
    t0 = time.time()
    frags = [f.strip(" *-•\t") for f in re.split(r"[\n,;+]+", text or "") if f.strip(" *-•\t")]
    frags = [f for f in frags if any(s in f.lower() for s in _STORES) or re.search(r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+[A-Z]|\b[A-Z]{3,}\b|\b\w+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{3,}", f)][:4]
    out = []
    for f in frags:
        if time.time() - t0 > budget_s:
            break
        q = _STORE_RE.sub(" ", f)
        q = re.sub(r"(?i)\b\d+([.,]\d+)?\s*(szt\.?|g|kg|ml|l|kawałk\w*|kostek|kostki|opak\w*)\b", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        if len(q) < 4:
            continue
        try:
            r = httpx.get("https://search.openfoodfacts.org/search",
                          params={"q": q, "page_size": 3, "fields": "product_name,brands,quantity,nutriments"},
                          headers={"User-Agent": "QBot/1.0 (osobisty asystent; albert.cytr.us)"}, timeout=3)
            hits = r.json().get("hits") or [] if r.status_code == 200 else []
        except Exception:
            hits = []
        for p in hits[:2]:
            n = p.get("nutriments") or {}
            if n.get("energy-kcal_100g") is None:
                continue
            b = p.get("brands")
            out.append({"q": f[:40], "name": p.get("product_name"), "brands": ", ".join(b) if isinstance(b, list) else b,
                        "quantity": p.get("quantity"), "kcal": n.get("energy-kcal_100g"), "p": n.get("proteins_100g"),
                        "c": n.get("carbohydrates_100g"), "f": n.get("fat_100g")})
    return out[:limit]


_FIX_PROMPT = """Poprawiasz wpis jedzenia użytkownika. Dostajesz pozycje (JSON) i poprawkę słowami.
Zwróć WYŁĄCZNIE JSON: {"items": [...pełna lista pozycji w tym samym formacie...], "zmiana": "jedno krótkie zdanie po polsku: co zmieniłeś i dlaczego kcal wzrosły, spadły albo się nie zmieniły"}.
Zmieniaj tylko pozycje, których dotyczy poprawka (ilość, wariant, wartości z etykiety; można dodać lub usunąć pozycję).
Poprawione pozycje: przelicz kcal i PEŁNE makra, "conf": "pewne" jeśli użytkownik podał konkretne liczby/ilość, "src": "poprawka".
Pozostałe pozycje przepisz bez zmian."""


def correct_items(items: list[dict], fix: str) -> list[dict]:
    return correct_items_note(items, fix)[0]


def fix_summary(before: list[dict], after: list[dict], note: str = "") -> str:
    """'kcal 435 → 435 (bez zmian) · B 27 → 27 · W 22 → 22 · T 22 → 22 g' + zdanie AI (17.10)."""
    a, b = totals(before), totals(after)
    d = b["kcal"] - a["kcal"]
    s = "kcal %s → %s (%s)" % (_fmt(a["kcal"]), _fmt(b["kcal"]), "bez zmian" if abs(d) < 1 else ("%+.0f" % d))
    s += " · B %s → %s · W %s → %s · T %s → %s g" % (_fmt(a["protein_g"]), _fmt(b["protein_g"]), _fmt(a["carbs_g"]), _fmt(b["carbs_g"]), _fmt(a["fat_g"]), _fmt(b["fat_g"]))
    return s + ("\n" + note if note else "")


def correct_items_note(items: list[dict], fix: str):
    """Poprawka -> (pozycje, zdanie AI co zmienilo)."""
    j = _ai_json(_FIX_PROMPT, [{"type": "text", "text": "POZYCJE:\n%s\n\nPOPRAWKA: %s" % (
        json.dumps(items, ensure_ascii=False), fix)}])
    it = clean_items(j.get("items"))
    if not it:
        raise ValueError("AI: poprawka bez pelnych wartosci")
    return it, str(j.get("zmiana") or "").strip()[:240]


# ======================================================================= Telegram
def _api(method: str, data: dict) -> dict:
    from qbot_telegram_client import _api as a
    return a(method, data) or {}


def _chat_id() -> str:
    import qbot_config as cfg
    return str(cfg.TELEGRAM_CHAT_ID)


def tg_send(text: str, kb: dict | None = None, reply_to: int | None = None, html: bool = False) -> int | None:
    body = {"chat_id": _chat_id(), "text": text[:4000], "disable_web_page_preview": True}
    if html:
        body["parse_mode"] = "HTML"
    if kb:
        body["reply_markup"] = kb
    if reply_to:
        body["reply_to_message_id"] = reply_to
        body["allow_sending_without_reply"] = True
    r = _api("sendMessage", body)
    return (r.get("result") or {}).get("message_id") if r.get("ok") else None


def tg_edit(message_id: int, text: str, kb: dict | None, html: bool = False) -> None:
    body = {"chat_id": _chat_id(), "message_id": message_id, "text": text[:4000],
            "disable_web_page_preview": True, "reply_markup": kb or {"inline_keyboard": []}}
    if html:
        body["parse_mode"] = "HTML"
    _api("editMessageText", body)


def _download_photo(file_id: str) -> tuple[bytes, str]:
    import httpx
    from qbot_telegram_client import _token
    r = _api("getFile", {"file_id": file_id})
    path = (r.get("result") or {}).get("file_path")
    if not path:
        raise RuntimeError("getFile: brak sciezki")
    data = httpx.get("https://api.telegram.org/file/bot%s/%s" % (_token(), path), timeout=30).content
    ext = path.rsplit(".", 1)[-1].lower()
    return data, {"png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")


# ======================================================================= wpisy
def _get(c, eid: int) -> dict | None:
    return c.execute("SELECT * FROM qbot_v2.food_entries WHERE id=%s", (eid,)).fetchone()


_BIKE_RE = re.compile(r"\b(na\s+rowerze|w\s+trakcie\s+jazdy|podczas\s+jazdy|w\s+czasie\s+jazdy)\b", re.I)


def on_bike(text) -> bool:
    """2026-10-18: wpis opisuje jedzenie/picie w trakcie jazdy rowerowej."""
    return bool(text and _BIKE_RE.search(str(text)))


def ride_mid(c, d):
    """~Srodek ostatniej jazdy rowerowej dnia d (training_sessions); brak jazdy -> None."""
    try:
        r = c.execute("SELECT started_at, duration_s FROM qbot_v2.training_sessions WHERE date=%s AND sport_type='cycling' "
                      "AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1", (d,)).fetchone()
    except Exception:
        return None
    if not r or not r["started_at"]:
        return None
    return r["started_at"] + timedelta(seconds=int((r["duration_s"] or 0) * 0.55))


def _write_intake(c, e: dict) -> int:
    from qbot_brokul_meals import remove_intake, drop_preset
    remove_intake(c, e.get("intake_log_id"))
    d = e["day"]
    sc = e["scale"] or 1
    c.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (d,))
    drop_preset(c, d)
    when = datetime.now(TZ) if d == datetime.now(TZ).date() else datetime.combine(d, dtime(13, 0), tzinfo=TZ)
    mt = "poza_dieta"
    if on_bike(e.get("raw_text")):   # 2026-10-18: zjedzone na rowerze -> typ 'na_rowerze', godzina z jazdy (raport jazdy)
        mt = "na_rowerze"
        when = ride_mid(c, d) or when
    lid = c.execute("INSERT INTO qbot_v2.intake_logs (date, eaten_at, meal_type, note, source, quality_status) "
                    "VALUES (%s,%s,%s,%s,%s,'estimated') RETURNING id",
                    (d, when, mt, "Telegram #%d: %s" % (e["id"], (e.get("raw_text") or e["kind"])[:200]), SOURCE)).fetchone()["id"]
    for it in e["items"]:
        c.execute("INSERT INTO qbot_v2.intake_items (intake_log_id, food_name, amount, unit, kcal, protein_g, carbs_g, fat_g, source) "
                  "VALUES (%s,%s,%s,'porcja',%s,%s,%s,%s,%s)",
                  (lid, (it["name"] + (" – " + it["portion"] if it.get("portion") else ""))[:200], sc,
                   round(it["kcal"] * sc, 1), round(it["protein_g"] * sc, 1), round(it["carbs_g"] * sc, 1),
                   round(it["fat_g"] * sc, 1), SOURCE))
    t = totals(e["items"], sc)
    c.execute("UPDATE qbot_v2.food_entries SET status='logged', intake_log_id=%s, kcal=%s, protein_g=%s, carbs_g=%s, fat_g=%s, "
              "updated_at=now() WHERE id=%s", (lid, t["kcal"], t["protein_g"], t["carbs_g"], t["fat_g"], e["id"]))
    return lid


def _learn(c, e: dict) -> None:
    """Katalog: ta sama fraza + ta sama porcja -> licznik; po CATALOG_AUTO_N QBot przestaje pytac."""
    if e["kind"] != "text" or not e.get("phrase_norm") or not e.get("items"):
        return
    sc = e["scale"] or 1
    items = [dict(i, kcal=round(i["kcal"] * sc, 1), protein_g=round(i["protein_g"] * sc, 1),
                  carbs_g=round(i["carbs_g"] * sc, 1), fat_g=round(i["fat_g"] * sc, 1)) for i in e["items"]]
    label = "%.0f" % totals(items)["kcal"]
    old = c.execute("SELECT label, n FROM qbot_v2.food_catalog WHERE phrase_norm=%s", (e["phrase_norm"],)).fetchone()
    n = (old["n"] + 1) if (old and old["label"] == label) else 1
    c.execute("INSERT INTO qbot_v2.food_catalog (phrase_norm, items, label, n, last_used) VALUES (%s,%s,%s,%s,now()) "
              "ON CONFLICT (phrase_norm) DO UPDATE SET items=EXCLUDED.items, label=EXCLUDED.label, n=EXCLUDED.n, last_used=now()",
              (e["phrase_norm"], json.dumps(items, ensure_ascii=False), label, n))


def create_entry(kind: str, day: date, raw_text: str | None = None, photo_file_id: str | None = None,
                 tg_message_id: int | None = None, items: list | None = None) -> int | None:
    with _conn() as c:
        r = c.execute("INSERT INTO qbot_v2.food_entries (kind, tg_message_id, raw_text, photo_file_id, day, phrase_norm, items) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tg_message_id) DO NOTHING RETURNING id",
                      (kind, tg_message_id, raw_text, photo_file_id, day,
                       norm_phrase(raw_text) if kind == "text" else None,
                       json.dumps(items, ensure_ascii=False) if items else None)).fetchone()
        c.commit()
    return r["id"] if r else None


def process_entry(eid: int, reply_to: int | None = None) -> str:
    """Szacowanie + zapis + odpowiedz. Zwraca status. Bledy -> 'failed' (wpis zostaje, wraca o 20:00)."""
    with _conn() as c:
        e = _get(c, eid)
        if not e or e["status"] not in ("new", "failed"):
            return e["status"] if e else "missing"
        c.execute("UPDATE qbot_v2.food_entries SET attempts=attempts+1 WHERE id=%s", (eid,))
        c.commit()
        try:
            res = None
            if e["kind"] == "text" and e["phrase_norm"]:
                cat = c.execute("SELECT * FROM qbot_v2.food_catalog WHERE phrase_norm=%s AND n>=%s",
                                (e["phrase_norm"], CATALOG_AUTO_N)).fetchone()
                if cat:
                    res = {"items": cat["items"], "_from_catalog": True}
            if res is None:
                imgs = [_download_photo(f) for f in photo_ids(e)]
                res = estimate(e["raw_text"], imgs or None, history_refs(e["raw_text"] or ""), off_refs(e["raw_text"] or ""))
        except Exception as ex:
            c.execute("UPDATE qbot_v2.food_entries SET status='failed', error=%s, updated_at=now() WHERE id=%s",
                      (("%s: %s" % (type(ex).__name__, ex))[:500], eid))
            c.commit()
            _log("#%d blad szacowania: %s" % (eid, ex))
            if (e["attempts"] or 0) == 0:
                tg_send("⚠️ #%d zapisane jako „%s”, ale nie udało się policzyć kcal. Spróbuję ponownie; wpis jest bezpieczny."
                        % (eid, (e["raw_text"] or "zdjęcie")[:60]), reply_to=reply_to)
            return "failed"
        if res.get("not_food"):
            c.execute("UPDATE qbot_v2.food_entries SET status='not_food', updated_at=now() WHERE id=%s", (eid,))
            c.commit()
            tg_send("🤔 #%d to chyba nie jedzenie – nic nie zapisałem. Wpisz jeszcze raz, jeśli to pomyłka." % eid,
                    {"inline_keyboard": [[{"text": "To jednak jedzenie – policz", "callback_data": "fd:r:%d" % eid}]]},
                    reply_to=reply_to)
            return "not_food"
        if res.get("ambiguous"):
            c.execute("UPDATE qbot_v2.food_entries SET status='asking', question=%s, options=%s, eaten_time=COALESCE(%s::time, eaten_time), "
                      "updated_at=now() WHERE id=%s", (res["question"], json.dumps(res["options"], ensure_ascii=False), res.get("time"), eid))
            c.commit()
            d = e["day"]
            rows, row = [], []
            for i, o in enumerate(res["options"]):
                row.append({"text": "%s · %s kcal" % (o["label"], _fmt(totals(o["items"])["kcal"])), "callback_data": "fd:o:%d:%d" % (eid, i)})
                if len(row) == 2:
                    rows.append(row); row = []
            if row:
                rows.append(row)
            rows.append([{"text": "🗑 anuluj", "callback_data": "fd:x:%d" % eid}])
            mid = tg_send("❓ #%d · %s (%s)\n%s" % (eid, d.strftime("%d.%m"), DNI[d.weekday()], res["question"]),
                          {"inline_keyboard": rows}, reply_to=reply_to)
            c.execute("UPDATE qbot_v2.food_entries SET reply_message_id=%s WHERE id=%s", (mid, eid))
            c.commit()
            return "asking"
        c.execute("UPDATE qbot_v2.food_entries SET items=%s, eaten_time=COALESCE(%s::time, eaten_time), updated_at=now() WHERE id=%s",
                  (json.dumps(res["items"], ensure_ascii=False), res.get("time"), eid))
        e = _get(c, eid)
        _write_intake(c, e)
        c.commit()
        e = _get(c, eid)
        e["_from_catalog"] = res.get("_from_catalog")
        mid = tg_send(receipt_text(e), receipt_kb(eid), reply_to=reply_to, html=True)
        c.execute("UPDATE qbot_v2.food_entries SET reply_message_id=%s WHERE id=%s", (mid, eid))
        c.commit()
    refresh_day(e["day"])
    return "logged"


def retry_pending() -> int:
    """Wpisy, ktore utknely (nowe > 2 min albo nieudane, max 4 proby) - dokoncz."""
    with _conn() as c:
        c.execute("UPDATE qbot_v2.food_entries SET status='new' WHERE status='choice' AND created_at < now() - interval '30 minutes'")   # 17.10: brak wyboru = nowy wpis
        c.commit()
        rows = c.execute("SELECT id FROM qbot_v2.food_entries WHERE status IN ('new','failed') AND attempts < 4 "
                         "AND created_at < now() - interval '2 minutes' ORDER BY id").fetchall()
    n = 0
    for r in rows:
        if process_entry(r["id"]) == "logged":
            n += 1
    return n


# ---------------------------------------------------------------- wejscie z telegram_reply_processor
def correct_entry(eid: int, fix: str, reply_to: int | None = None) -> bool:
    """Poprawka slowami do istniejacego wpisu (np. 'chrupki 60 g'). Skala wlicza sie w pozycje i wraca do 1."""
    with _conn() as c:
        e = _get(c, eid)
        if not e or e["status"] != "logged":
            return False
        sc = e["scale"] or 1
        base = [dict(i, kcal=round(i["kcal"] * sc, 1), protein_g=round(i["protein_g"] * sc, 1),
                     carbs_g=round(i["carbs_g"] * sc, 1), fat_g=round(i["fat_g"] * sc, 1)) for i in e["items"]]
        try:
            items, note = correct_items_note(base, fix)
        except Exception as ex:
            _log("#%d poprawka blad: %s" % (eid, ex))
            tg_send("⚠️ #%d: nie udało się zastosować poprawki („%s”). Wpis bez zmian." % (eid, fix[:60]), reply_to=reply_to)
            return False
        c.execute("UPDATE qbot_v2.food_entries SET items=%s, scale=1, updated_at=now() WHERE id=%s",
                  (json.dumps(items, ensure_ascii=False), eid))
        _write_intake(c, _get(c, eid))
        c.commit()
        e = _get(c, eid)
    if e["reply_message_id"]:
        tg_edit(e["reply_message_id"], receipt_text(e) + "\n✏️ poprawione: " + _esc(fix[:80]), receipt_kb(eid), html=True)
    tg_send("✏️ #%d poprawione · %s" % (eid, fix_summary(base, items, note)), reply_to=reply_to)
    refresh_day(e["day"])
    return True


def handle_text(text: str, msg: dict) -> None:
    now = datetime.now(TZ)
    rt = (msg.get("reply_to_message") or {}).get("message_id")
    if rt:
        with _conn() as c:
            r = c.execute("SELECT id FROM qbot_v2.food_entries WHERE reply_message_id=%s AND status='logged'", (rt,)).fetchone()
        if r:
            correct_entry(r["id"], text.strip()[:500], reply_to=msg.get("message_id"))
            return
    day = parse_day(text, now)
    eid = create_entry("text", day, raw_text=text.strip()[:1000], tg_message_id=msg.get("message_id"))
    if eid is None:
        _log("wiadomosc %s juz byla - pomijam" % msg.get("message_id"))
        return
    # 17.10: zwykla wiadomosc do 15 min po wpisie -> zapytaj: dopisac do niego czy nowy wpis (bez zgadywania)
    if day == now.date():
        with _conn() as c:
            last = c.execute("SELECT id, raw_text, kind, items FROM qbot_v2.food_entries WHERE status='logged' AND id<>%s "
                             "AND created_at > now() - interval '15 minutes' ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
            if last:
                c.execute("UPDATE qbot_v2.food_entries SET status='choice', updated_at=now() WHERE id=%s", (eid,))
                c.commit()
        if last:
            opis = (last["raw_text"] or ", ".join(_short(i) for i in (last["items"] or [])) or last["kind"])[:28]
            mid = tg_send("➕ Dopisać „%s” do #%d (%s), czy to osobny posiłek?" % (text.strip()[:60], last["id"], opis),
                          {"inline_keyboard": [[{"text": "✏️ Dopisz do #%d" % last["id"], "callback_data": "fd:a:%d:%d" % (eid, last["id"])},
                                                {"text": "➕ Nowy wpis", "callback_data": "fd:n:%d" % eid}]]}, reply_to=msg.get("message_id"))
            with _conn() as c:
                c.execute("UPDATE qbot_v2.food_entries SET reply_message_id=%s WHERE id=%s", (mid, eid)); c.commit()
            return
    process_entry(eid, reply_to=msg.get("message_id"))


def photo_ids(e: dict) -> list:
    """Zdjecia wpisu: lista albumu (photo_file_ids) albo pojedyncze photo_file_id."""
    ids = list(e.get("photo_file_ids") or [])
    if not ids and e.get("photo_file_id"):
        ids = [e["photo_file_id"]]
    return ids


def handle_photo(msg: dict) -> None:
    """2026-10-18: album (kilka zdjec w jednej wiadomosci Telegrama = wspolne media_group_id) -> JEDEN wpis;
    liczy go flush_albums() po petli telegram_reply_processor (wszystkie zdjecia naraz do AI).
    Pojedyncze zdjecie do 15 min po innym wpisie -> pytanie „Dopisz do #N / Nowy wpis” (jak tekst)."""
    now = datetime.now(TZ)
    cap = (msg.get("caption") or "").strip()
    photos = msg.get("photo") or []
    fid = photos[-1]["file_id"] if photos else (msg.get("document") or {}).get("file_id")
    if not fid:
        return
    mg = msg.get("media_group_id")
    if mg:
        with _conn() as c:
            e = c.execute("SELECT * FROM qbot_v2.food_entries WHERE media_group_id=%s AND status<>'deleted' ORDER BY id LIMIT 1",
                          (str(mg),)).fetchone()
            if e:
                ids = photo_ids(e)
                if fid not in ids:
                    ids.append(fid)
                    raw = " · ".join(x for x in [e["raw_text"], cap[:500]] if x) or None
                    st = "new" if e["status"] in ("logged", "failed", "not_food") else e["status"]   # spoznione zdjecie -> licz od nowa
                    c.execute("UPDATE qbot_v2.food_entries SET photo_file_ids=%s, raw_text=%s, status=%s, attempts=0, updated_at=now() "
                              "WHERE id=%s", (json.dumps(ids), raw, st, e["id"]))
                    c.commit()
                    _log("#%d album %s: +zdjecie (%d)" % (e["id"], mg, len(ids)))
                return
        eid = create_entry("photo", parse_day(cap, now), raw_text=cap[:1000] or None, photo_file_id=fid,
                           tg_message_id=msg.get("message_id"))
        if eid is not None:
            with _conn() as c:
                c.execute("UPDATE qbot_v2.food_entries SET media_group_id=%s, photo_file_ids=%s WHERE id=%s",
                          (str(mg), json.dumps([fid]), eid))
                c.commit()
        return
    eid = create_entry("photo", parse_day(cap, now), raw_text=cap[:1000] or None, photo_file_id=fid,
                       tg_message_id=msg.get("message_id"))
    if eid is None:
        return
    if _offer_append(eid, msg.get("message_id"), "zdjęcie" + (" („%s”)" % cap[:40] if cap else "")):
        return
    process_entry(eid, reply_to=msg.get("message_id"))


def _offer_append(eid: int, reply_to, label: str) -> bool:
    """Wpis z dzis do 15 min po innym -> pytanie: dopisac czy nowy (bez zgadywania). True = zapytano."""
    with _conn() as c:
        e = _get(c, eid)
        if not e or e["day"] != datetime.now(TZ).date():
            return False
        last = c.execute("SELECT id, raw_text, kind, items FROM qbot_v2.food_entries WHERE status='logged' AND id<>%s "
                         "AND created_at > now() - interval '15 minutes' ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
        if not last:
            return False
        c.execute("UPDATE qbot_v2.food_entries SET status='choice', updated_at=now() WHERE id=%s", (eid,))
        c.commit()
    opis = (last["raw_text"] or ", ".join(_short(i) for i in (last["items"] or [])) or last["kind"])[:28]
    mid = tg_send("➕ Dopisać %s do #%d (%s), czy to osobny posiłek?" % (label, last["id"], opis),
                  {"inline_keyboard": [[{"text": "✏️ Dopisz do #%d" % last["id"], "callback_data": "fd:a:%d:%d" % (eid, last["id"])},
                                        {"text": "➕ Nowy wpis", "callback_data": "fd:n:%d" % eid}]]}, reply_to=reply_to)
    with _conn() as c:
        c.execute("UPDATE qbot_v2.food_entries SET reply_message_id=%s WHERE id=%s", (mid, eid))
        c.commit()
    return True


def flush_albums() -> int:
    """Licz albumy zebrane w tym przebiegu (wolane na koncu telegram_reply_processor.main)."""
    with _conn() as c:
        rows = c.execute("SELECT id, tg_message_id FROM qbot_v2.food_entries WHERE status='new' AND media_group_id IS NOT NULL "
                         "ORDER BY id").fetchall()
    for r in rows:
        process_entry(r["id"], reply_to=r["tg_message_id"])
    return len(rows)


def _baked(e: dict) -> list:
    sc = e["scale"] or 1
    return [dict(i, kcal=round(i["kcal"] * sc, 1), protein_g=round(i["protein_g"] * sc, 1),
                 carbs_g=round(i["carbs_g"] * sc, 1), fat_g=round(i["fat_g"] * sc, 1)) for i in (e["items"] or [])]


def merge_entries(tgt: int, src: list, new_items: list | None = None, reply_to=None, note: str = "") -> bool:
    """Dolacz wpisy src (i/lub nowe pozycje) do wpisu tgt: jeden wpis, jedna suma; src -> 'deleted'."""
    from qbot_brokul_meals import remove_intake
    with _conn() as c:
        t = _get(c, tgt)
        if not t or t["status"] != "logged":
            return False
        before = _baked(t)
        items, ids, texts = list(before), photo_ids(t), [t["raw_text"]]
        for sid in src:
            s = _get(c, sid)
            if not s or sid == tgt:
                continue
            if s["status"] == "logged":
                items += _baked(s)
            ids += [f for f in photo_ids(s) if f not in ids]
            texts.append(s["raw_text"])
            remove_intake(c, s["intake_log_id"])
            c.execute("UPDATE qbot_v2.food_entries SET status='deleted', intake_log_id=NULL, error=%s, updated_at=now() WHERE id=%s",
                      ("scalone do #%d" % tgt, sid))
        items += new_items or []
        raw = " · ".join(x for x in texts if x) or None
        c.execute("UPDATE qbot_v2.food_entries SET items=%s, scale=1, photo_file_ids=%s, raw_text=%s, updated_at=now() WHERE id=%s",
                  (json.dumps(items, ensure_ascii=False), json.dumps(ids) if ids else None, raw, tgt))
        _write_intake(c, _get(c, tgt))
        c.commit()
        t = _get(c, tgt)
    if t["reply_message_id"]:
        tg_edit(t["reply_message_id"], receipt_text(t) + "\n➕ dołączone", receipt_kb(tgt), html=True)
    tg_send("➕ #%d · %s" % (tgt, fix_summary(before, items, note)), reply_to=reply_to)
    refresh_day(t["day"])
    return True


def append_photo(tgt: int, eid: int, reply_to=None) -> bool:
    """Zdjecie dopisane przyciskiem do wpisu tgt: policz samo zdjecie i dolacz jego pozycje."""
    with _conn() as c:
        e = _get(c, eid)
    try:
        res = estimate(e["raw_text"], [_download_photo(f) for f in photo_ids(e)] or None,
                       history_refs(e["raw_text"] or ""), off_refs(e["raw_text"] or ""))
    except Exception as ex:
        _log("#%d dopisanie zdjecia blad: %s" % (eid, ex))
        tg_send("⚠️ Nie udało się policzyć zdjęcia do #%d. Wyślij je jeszcze raz." % tgt, reply_to=reply_to)
        return False
    note = ""
    items = res.get("items")
    if res.get("ambiguous"):
        o = res["options"][len(res["options"]) // 2]
        items, note = o["items"], "Przyjąłem: %s (popraw odpowiedzią, jeśli inaczej)." % o["label"]
    if not items:
        tg_send("🤔 Na zdjęciu nie widzę jedzenia – #%d bez zmian." % tgt, reply_to=reply_to)
        return False
    return merge_entries(tgt, [eid], new_items=items, reply_to=reply_to, note=note)


# ---------------------------------------------------------------- przyciski
def handle_callback(cq, tg_answer_callback, tg_send_plain, tg_edit_markup, chat_id_allowed):
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    if chat != str(chat_id_allowed):
        tg_answer_callback(cq.get("id"), "Brak dostepu")
        return
    p = data.split(":")
    if p[0] == "qk":
        return _quick(cq, p, msg, tg_answer_callback)
    act, eid = p[1], int(p[2])
    days_touched = set()
    with _conn() as c:
        e = _get(c, eid)
        if not e:
            tg_answer_callback(cq.get("id"), "Nie ma takiego wpisu")
            return
        days_touched.add(e["day"])
        if act == "o" and e["status"] == "asking":
            opt = (e["options"] or [])[int(p[3])]
            c.execute("UPDATE qbot_v2.food_entries SET items=%s, scale=1 WHERE id=%s",
                      (json.dumps(opt["items"], ensure_ascii=False), eid))
            e = _get(c, eid)
            _write_intake(c, e)
            _learn(c, _get(c, eid))
            c.commit()
            tg_answer_callback(cq.get("id"), "Zapisane")
            tg_edit(msg["message_id"], receipt_text(_get(c, eid)), receipt_kb(eid), html=True)
        elif act in ("m", "p") and e["status"] == "logged":
            sc = max(0.25, round((e["scale"] or 1) + (-SCALE_STEP if act == "m" else SCALE_STEP), 2))
            c.execute("UPDATE qbot_v2.food_entries SET scale=%s WHERE id=%s", (sc, eid))
            _write_intake(c, _get(c, eid))
            c.commit()
            tg_answer_callback(cq.get("id"), "×%.2f" % sc)
            tg_edit(msg["message_id"], receipt_text(_get(c, eid)), receipt_kb(eid), html=True)
        elif act == "k" and e["status"] == "logged":
            _learn(c, e)
            c.commit()
            tg_answer_callback(cq.get("id"), "OK")
            tg_edit(msg["message_id"], receipt_text(e), None, html=True)
        elif act == "b" and e["status"] in ("logged", "asking"):
            nd = e["day"] - timedelta(days=1)
            c.execute("UPDATE qbot_v2.food_entries SET day=%s WHERE id=%s", (nd, eid))
            if e["status"] == "logged":
                _write_intake(c, _get(c, eid))
            c.commit()
            days_touched.add(nd)
            tg_answer_callback(cq.get("id"), "Przeniesione na %s" % nd.strftime("%d.%m"))
            e2 = _get(c, eid)
            tg_edit(msg["message_id"], receipt_text(e2) if e2["status"] == "logged" else _esc(msg.get("text", "")),
                    receipt_kb(eid) if e2["status"] == "logged" else msg.get("reply_markup"))
        elif act == "a" and e["status"] == "choice":   # 17.10: dopisz do wpisu p[3]
            tgt = int(p[3])
            c.execute("UPDATE qbot_v2.food_entries SET status='deleted', updated_at=now() WHERE id=%s", (eid,))
            c.commit()
            tg_answer_callback(cq.get("id"), "Dopisuję do #%d" % tgt)
            if e["kind"] == "photo":   # 18.10: zdjecie -> policz i dolacz pozycje do wpisu
                tg_edit(msg["message_id"], "✏️ zdjęcie → dopisuję do #%d" % tgt, None)
                append_photo(tgt, eid, reply_to=e["tg_message_id"])
            else:
                tg_edit(msg["message_id"], "✏️ „%s” → dopisuję do #%d" % (_esc((e["raw_text"] or "")[:60]), tgt), None)
                correct_entry(tgt, e["raw_text"] or "", reply_to=e["tg_message_id"])
        elif act == "n" and e["status"] == "choice":   # 17.10: osobny posilek
            c.execute("UPDATE qbot_v2.food_entries SET status='new', updated_at=now() WHERE id=%s", (eid,))
            c.commit()
            tg_answer_callback(cq.get("id"), "Liczę jako nowy wpis")
            tg_edit(msg["message_id"], "➕ „%s” → nowy wpis, liczę…" % _esc((e["raw_text"] or "")[:60]), None)
            process_entry(eid, reply_to=e["tg_message_id"])
        elif act == "x":
            from qbot_brokul_meals import remove_intake
            remove_intake(c, e["intake_log_id"])
            c.execute("UPDATE qbot_v2.food_entries SET status='deleted', intake_log_id=NULL, updated_at=now() WHERE id=%s", (eid,))
            c.commit()
            tg_answer_callback(cq.get("id"), "Usunięte")
            tg_edit(msg["message_id"], "🗑 #%d usunięte (%s)" % (eid, (e["raw_text"] or e["kind"])[:60]), None)
        elif act == "r" and e["status"] == "not_food":
            c.execute("UPDATE qbot_v2.food_entries SET status='new', raw_text=%s WHERE id=%s",
                      ("(to jest jedzenie/napój) " + (e["raw_text"] or ""), eid))
            c.commit()
            tg_answer_callback(cq.get("id"), "Liczę…")
            tg_edit(msg["message_id"], "↻ #%d liczę jeszcze raz…" % eid, None)
            process_entry(eid)
        else:
            tg_answer_callback(cq.get("id"))
            return
    for d in days_touched:
        refresh_day(d)


def _quick(cq, p, msg, answer) -> None:
    day = datetime.strptime(p[1], "%Y%m%d").date()
    code = p[2]
    if code == "none":
        with _conn() as c:
            r = c.execute("INSERT INTO qbot_v2.food_day (day, extras_none) VALUES (%s, true) ON CONFLICT (day) "
                          "DO UPDATE SET extras_none = NOT qbot_v2.food_day.extras_none, updated_at=now() RETURNING extras_none",
                          (day,)).fetchone()
            c.commit()
        answer(cq.get("id"), "Nic poza dietą" if r["extras_none"] else "Cofnięte")
    elif code in ("win_ok", "win_no"):
        import qbot_food_streaks as S
        r = S.set_window(day, code == "win_ok")
        answer(cq.get("id"), "Za późno – termin minął o 12:00 następnego dnia" if r == "late"
               else ("Okno dotrzymane" if code == "win_ok" else "Zapisane: okno złamane"))
    elif code in QUICK:
        lab, k, pr, cb, ft = QUICK[code]
        items = [{"name": lab, "portion": "szacunek", "kcal": k, "protein_g": pr, "carbs_g": cb, "fat_g": ft}]
        eid = create_entry("quick", day, raw_text=lab, items=items)
        with _conn() as c:
            e = _get(c, eid)
            _write_intake(c, e)
            c.commit()
            e = _get(c, eid)
        mid = tg_send(receipt_text(e), receipt_kb(eid), html=True)
        with _conn() as c:
            c.execute("UPDATE qbot_v2.food_entries SET reply_message_id=%s WHERE id=%s", (mid, eid))
            c.commit()
        answer(cq.get("id"), "Dodane – popraw ➖/➕ jeśli trzeba")
    else:
        answer(cq.get("id"))
        return
    refresh_day(day, message_id=msg.get("message_id"))


# ======================================================================= wiadomosc dnia
def day_entries(day: date) -> list[dict]:
    with _conn() as c:
        return c.execute("SELECT * FROM qbot_v2.food_entries WHERE day=%s AND status IN ('logged','asking','failed','new') "
                         "ORDER BY id", (day,)).fetchall()


def day_totals(day: date) -> dict:
    with _conn() as c:
        r = c.execute("SELECT sum(i.kcal) kcal, sum(i.protein_g) p, sum(i.carbs_g) cb, sum(i.fat_g) f "
                      "FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id WHERE l.date=%s",
                      (day,)).fetchone()
    return {"kcal": r["kcal"], "protein_g": r["p"], "carbs_g": r["cb"], "fat_g": r["f"]}


def close_state(day: date) -> dict:
    """Dzien zamkniety = Brokul bez 'pending' ORAZ (klik 'Nic poza dieta' albo >= 1 wpis poza dieta).
    Dzien bez dostawy: >= 1 wpis albo (Nic + cos z lodowki)."""
    from qbot_brokul_meals import day_meals, fridge_for
    meals = day_meals(day)
    fr = [m for m in fridge_for(day) if m["status"] == "eaten"]
    ents = [e for e in day_entries(day) if e["status"] == "logged"]
    with _conn() as c:
        fd = c.execute("SELECT * FROM qbot_v2.food_day WHERE day=%s", (day,)).fetchone()
    none = bool(fd and fd["extras_none"])
    pending = [m for m in meals if m["status"] == "pending"]
    if meals:
        closed = not pending and (none or bool(ents))
    else:
        closed = bool(ents) or (none and bool(fr))
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.food_day (day, extras_none, closed_at) VALUES (%s,%s,%s) ON CONFLICT (day) DO UPDATE "
                  "SET closed_at = CASE WHEN %s THEN COALESCE(qbot_v2.food_day.closed_at, now()) ELSE NULL END, updated_at=now()",
                  (day, none, datetime.now(TZ) if closed else None, closed))
        c.commit()
    return {"closed": closed, "pending": len(pending), "none": none, "entries": len(ents), "has_diet": bool(meals)}


def build_day(day: date) -> tuple[str, dict]:
    """Wiadomosc dnia (20:00) - ZWIEZLA (2026-10-12): naglowek z passa, posilki w 1 linii, cel, okno, stan."""
    from qbot_brokul_meals import day_meals, fridge_for
    import qbot_food_streaks as S
    meals = day_meals(day)
    fridge = fridge_for(day)
    ents = day_entries(day)
    cs = close_state(day)
    md = day.strftime("%Y%m%d")
    kb = []
    ic = {"eaten": "✅", "skipped": "❌", "pending": "⏳", "fridge": "📦", "discarded": "🗑"}
    head = "🍽 %s %s" % (DNI[day.weekday()], day.strftime("%d.%m"))
    try:
        head += " · " + S.header_line().replace(" · ", " ")
    except Exception as ex:
        _log("passa: %s" % ex)
    L = [head]
    for m in meals:
        L.append("%s %s · %s" % (ic.get(m["status"], "•"), m["meal_type"], _fmt(m["kcal"])))
        t, i = m["meal_type"], m["id"]
        if m["status"] == "pending":
            kb.append([{"text": "✅ %s" % t, "callback_data": "br:e:%d:%s" % (i, md)},
                       {"text": "❌", "callback_data": "br:s:%d:%s" % (i, md)},
                       {"text": "📦", "callback_data": "br:f:%d:%s" % (i, md)}])
        else:
            kb.append([{"text": "%s %s · cofnij" % ({"eaten": "✔", "skipped": "✖", "fridge": "📦"}.get(m["status"], ""), t),
                        "callback_data": "br:p:%d:%s" % (i, md)}])
    if sum(1 for m in meals if m["status"] == "pending") >= 2:
        kb.append([{"text": "✅ Wszystkie", "callback_data": "br:a:%s" % md},
                   {"text": "📦 Wszystkie później", "callback_data": "br:z:%s" % md}])
    for m in fridge:
        L.append("%s z lodówki: %s %s · %s" % (ic.get(m["status"], "•"), m["meal_type"], m["day"].strftime("%d.%m"), _fmt(m["kcal"])))
        t, i = "%s %s" % (m["meal_type"], m["day"].strftime("%d.%m")), m["id"]
        if m["status"] == "fridge":
            kb.append([{"text": "✅ Zjadłem: %s" % t, "callback_data": "br:d:%d:%s" % (i, md)},
                       {"text": "🗑", "callback_data": "br:w:%d:%s" % (i, md)}])
        else:
            kb.append([{"text": "%s %s · cofnij" % ("✔" if m["status"] == "eaten" else "🗑", t), "callback_data": "br:f:%d:%s" % (i, md)}])
    for e in ents:
        if e["status"] == "logged":
            desc = re.sub(r"\s+", " ", ", ".join(_short(i) for i in (e["items"] or [])) or (e["raw_text"] or e["kind"]))
            L.append("✅ #%d %s · %s" % (e["id"], desc[:38] + ("…" if len(desc) > 38 else ""), _fmt(e["kcal"])))
        else:
            L.append("⏳ #%d %s – w toku" % (e["id"], re.sub(r"\s+", " ", e["raw_text"] or "zdjęcie")[:30]))
    if meals and cs["none"] and not ents:
        L.append("✔ nic poza dietą")
    if meals:
        kb.append([{"text": ("✔ Nic poza dietą ✓" if cs["none"] else "✔ Nic poza dietą"), "callback_data": "qk:%s:none" % md},
                   {"text": "🥨", "callback_data": "qk:%s:snack" % md}, {"text": "🍫", "callback_data": "qk:%s:sweet" % md}])
        kb.append([{"text": "🍽 S", "callback_data": "qk:%s:out_s" % md}, {"text": "🍽 M", "callback_data": "qk:%s:out_m" % md},
                   {"text": "🍽 L", "callback_data": "qk:%s:out_l" % md}])
    else:
        for em, code in (("🍳", "bf"), ("🍲", "ln"), ("🌙", "dn")):
            kb.append([{"text": "%s %s" % (em, sz), "callback_data": "qk:%s:%s_%s" % (md, code, sz.lower())} for sz in ("S", "M", "L")])
        kb.append([{"text": "🥨", "callback_data": "qk:%s:snack" % md}, {"text": "🍫", "callback_data": "qk:%s:sweet" % md}])
    try:
        import qbot_food_plan as FP
        L.append(FP.evening_line(day))
    except Exception as ex:
        _log("cel dnia: %s" % ex)
    try:   # [GARMIN-DANE] Etap 5 (2026-10-14): wlasny cel snu + pora snu (fitmodel/sleep_target.py)
        from fitmodel.sleep_target import evening_line as _sleep_line
        with _conn() as c:
            L.append(_sleep_line(c, day))
    except Exception as ex:
        _log("sen: %s" % ex)
    with _conn() as c:
        ws, wd = S.window_status(c, day)
    if ws == "exempt":
        L.append("🕗 okno zwolnione (%s)" % wd)
    else:
        L.append("🕗 okno: " + {"ok": "✔", "broken": "✖" + (" " + wd if wd else ""), "pending": "potwierdź"}[ws])
        kb.append([{"text": "🕗 Dotrzymane" + (" ✓" if ws == "ok" else ""), "callback_data": "qk:%s:win_ok" % md},
                   {"text": "✖ Złamane" + (" ✓" if ws == "broken" else ""), "callback_data": "qk:%s:win_no" % md}])
    try:
        L += S.milestone_lines(day)
    except Exception:
        pass
    try:  # 2026-10-14: seria cisnienia - wieczorny pomiar (tylko dzis i gdy jeszcze nie bylo)
        import qbot_food_plan as _FP
        if day == date.today():
            with _conn() as c:
                bs = _FP.bp_series(c, day)
            if bs and not bs["evening"]:
                L.append("🩺 Wieczorny pomiar ciśnienia (dzień %d/%d) – 2 pomiary" % (bs["n"], _FP.BP_SERIES_DAYS))
    except Exception as ex:
        _log("seria cisnienia: %s" % ex)
    if cs["closed"]:
        L.append("🔒 zamknięty")
    else:
        need = (["Brokuł"] if cs["pending"] else []) + ([] if (cs["none"] or cs["entries"]) else ["dopisz jedzenie"])
        L.append("⏳ " + " · ".join(need) + ("" if ents or cs["none"] else " (tekst, zdjęcie lub przyciski" + (", 🍽 = na mieście)" if meals else ": 🍳🍲🌙 S/M/L)")))
    return "\n".join(L), {"inline_keyboard": kb}


def send_day(day: date, force: bool = False) -> bool:
    with _conn() as c:
        if not force and c.execute("SELECT 1 FROM qbot_v2.brokul_notify WHERE day=%s", (day,)).fetchone():
            return False
    text, kb = build_day(day)
    mid = tg_send(text, kb)
    if not mid:
        raise RuntimeError("sendMessage nie powiodl sie")
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.brokul_notify (day, chat_id, message_id) VALUES (%s,%s,%s) "
                  "ON CONFLICT (day) DO UPDATE SET chat_id=EXCLUDED.chat_id, message_id=EXCLUDED.message_id, sent_at=now()",
                  (day, _chat_id(), mid))
        c.commit()
    return True


def refresh_day(day: date, chat_id: str | None = None, message_id: int | None = None) -> None:
    """Odswiez wiadomosc dnia (jesli byla wyslana). Bledy pomijane - to tylko widok."""
    try:
        if not message_id:
            with _conn() as c:
                r = c.execute("SELECT message_id FROM qbot_v2.brokul_notify WHERE day=%s", (day,)).fetchone()
            if not r:
                close_state(day)
                return
            message_id = r["message_id"]
        text, kb = build_day(day)
        tg_edit(message_id, text, kb)
        import qbot_food_streaks as S
        S.check_milestones()
    except Exception as e:
        _log("refresh_day %s: %s" % (day, e))



# --------------------------------------------------------------------------- dzwonek (2026-10-13)
def notif_items(now) -> list[dict]:
    """Pozycje 'stanu na zywo' do centrum powiadomien (qbot_notif.sync_live): wczoraj do 12:00 i dzis od 19:30 -
    okno 10-20 do potwierdzenia oraz dzien do zamkniecia (Brokul / wpisy). Jedna akcja = jedno klikniecie, reszta przez link."""
    import qbot_food_streaks as S
    today = now.date()
    days = [today - timedelta(days=1)] if now.hour < 12 else []
    if now.hour * 60 + now.minute >= 19 * 60 + 30:
        days.append(today)
    out = []
    for d in days:
        if d < S.START:
            continue
        lbl = ("wczoraj " if d < today else "dziś ") + d.strftime("%d.%m")
        term = "do 12:00 " + ("dziś" if d < today else "jutro")
        url = "/zdrowie.html#dni=" + d.isoformat()
        try:
            with _conn() as c:
                ws, _ = S.window_status(c, d)
            if ws == "pending":
                out.append({"key": "live:jedzenie:okno:%s" % d.isoformat(), "kind": "jedzenie", "title": "Okno 10–20 – %s: dotrzymane?" % lbl,
                            "body": "potwierdź %s · złamane? otwórz dzień i kliknij „Złamane”" % term, "url": url,
                            "action": {"label": "Okno OK", "post": "/api/jedzenie/window", "body": {"day": d.isoformat(), "ok": True}}})
        except Exception as ex:
            _log("notif okno: %s" % ex)
        try:
            cs = close_state(d)
            if not cs["closed"]:
                need = []
                if cs["pending"]:
                    need.append("Brokuł: %d do potwierdzenia" % cs["pending"])
                if not (cs["none"] or cs["entries"]):
                    need.append("jedzenie poza dietą albo „nic poza dietą”")
                act = ({"label": "Brokuł zjedzony", "post": "/api/jedzenie/brokul/all", "body": {"day": d.isoformat(), "action": "eaten"}} if cs["pending"]
                       else ({"label": "Nic poza dietą", "post": "/api/jedzenie/none", "body": {"day": d.isoformat()}} if not (cs["none"] or cs["entries"]) else None))
                out.append({"key": "live:jedzenie:dzien:%s" % d.isoformat(), "kind": "jedzenie", "title": "Zamknij dzień – %s" % lbl,
                            "body": " · ".join(need) + " · " + term + " (passa 🔥)", "url": url, "action": act})
        except Exception as ex:
            _log("notif dzien: %s" % ex)
    return out
