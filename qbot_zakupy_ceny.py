"""Garaz > Zakupy, ETAP 3 (2026-10-13): szukanie najnizszej ceny dla pozycji z listy.

Decyzja Michala: najskuteczniej = nie tylko Ceneo (nie ma wszystkich sklepow). Kazda oferta SPRAWDZONA.
Zrodla (rownolegle w workerze scripts/zakupy_ceny_worker.py, uruchamianym przyciskiem; ok. 30-60 s):
  1) AI z wyszukiwarka (Anthropic web_search): sklepy wysylajace do Polski, ten sam produkt/wariant, linki do stron produktu.
     Kazdy link otwieramy (zwykle pobranie, a dla stron skryptowych przegladarka) i czytamy cene ze strony
     (dane strukturalne produktu). Cena AI NIE jest brana na wiare.
  2) Ceneo (przegladarka - zwykle pobranie dostaje strone-zapore): wyniki wyszukiwania -> pasujace produkty ->
     oferty sklepow ze strony produktu Ceneo (ceny pokazywane przez Ceneo = aktualne, link do produktu w Ceneo).
  3) Link z pozycji (Twoj sklep) - tez sprawdzany, zeby bylo z czym porownac.
Zgodnosc produktu: nazwa strony musi zawierac wiekszosc slow z nazwy pozycji (liczby, np. 12 rz./126 ogniw, MUSZA sie zgadzac)
albo zgadza sie EAN. Inaczej oferta odpada ("inny wariant").
Status oferty: ok (cena sprawdzona) / blocked (sklep blokuje QBota, np. Allegro 403 - pokazywane osobno, z cena wg AI,
wyraznie oznaczone jako niesprawdzone) / reszta odpada (brak ceny, inny produkt, blad).
Waluty obce -> PLN po kursie NBP (tabela A). Ceny bez kosztu dostawy (sklepy podaja go roznie).
Wynik: tabela shop_offers (historia przebiegow), stan na shop_items (price_search_*), Dzwonek "Ceny: ...".
Dok.: docs/ZAKUPY.md. Testy: tests/test_zakupy_ceny.py.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, quote_plus

sys.path.insert(0, "/opt/qbot/app")

UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) "
              "Version/17.0 Safari/605.1.15")
AI_MAX_SEARCHES = 5
AI_MAX_OFFERS = 10
CENEO_PRODUCTS = 2
KEEP_OK = 5
KEEP_BLOCKED = 3
MATCH_MIN = 0.6

OFFERS_DDL = """
CREATE TABLE IF NOT EXISTS shop_offers (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL,
    run_at    TEXT NOT NULL,
    shop      TEXT,
    title     TEXT,
    price     REAL,
    currency  TEXT,
    price_pln REAL,
    url       TEXT,
    source    TEXT,
    status    TEXT NOT NULL,
    note      TEXT
);
CREATE INDEX IF NOT EXISTS idx_shop_offers_item ON shop_offers(item_id, run_at);
"""
ITEM_COLS = [("price_search_at", "TEXT"), ("price_search_status", "TEXT"), ("price_search_note", "TEXT")]


def _log(msg):
    print("[%s] ceny: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


# ======================================================================= czyste funkcje (testowane)
def _fold(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("ł", "l"))
    return "".join(ch for ch in t if not unicodedata.combining(ch))


_STOP = {"i", "z", "w", "na", "do", "dla", "the", "and", "with", "of", "for", "nowy", "new", "oryginalny", "sklep",
         "cena", "kup", "rz", "rzed", "rzedow", "rzedowy", "speed", "sp", "szt", "pcs", "x"}


def tokens(t: str) -> list[str]:
    """Slowa znaczace: litery/cyfry, bez stop-slow; laczy np. 'cn-m8100' -> 'cn', 'm8100' i 'cnm8100'."""
    f = _fold(t)
    out = []
    for w in re.findall(r"[a-z0-9]+(?:[-./][a-z0-9]+)*", f):
        parts = [p for p in re.split(r"[-./]", w) if p]
        for p in parts + ([w.replace("-", "").replace(".", "").replace("/", "")] if len(parts) > 1 else []):
            if p not in _STOP and (len(p) >= 2 or p.isdigit()):
                out.append(p)
    return list(dict.fromkeys(out))


_UNITS = {"kaps", "kapsulek", "kapsulki", "tabl", "tabletek", "tabletki", "szt", "sztuk", "ml", "mg", "g", "kg", "l",
          "ogniw", "ogniwa", "link", "links", "par", "pary", "porcji", "cm", "mm", "rozmiar", "size", "kolor", "color"}


def match_score(item_name: str, brand: str | None, page_name: str) -> float:
    """Udzial slow z nazwy pozycji obecnych w nazwie strony. Liczba z pozycji, ktorej brak na stronie = 0 (inny wariant).
    Rdzen nazwy (bez marki, jednostek i liczb) musi sie zgadzac co najmniej w polowie - inaczej 0
    (np. 'Olimp Magnez 90 kaps.' vs 'Olimp Witamina C 90 kaps.')."""
    want = tokens(" ".join(x for x in (brand, item_name) if x))
    if not want:
        return 0.0
    have = set(tokens(page_name))
    joined = "".join(sorted(have))
    bt = set(tokens(brand or ""))

    spaced = " ".join(sorted(have))

    def has(w):
        if w.isdigit():   # '12' pasuje do '12rz', ale nie do '126'
            return re.search(r"(?<!\d)%s(?!\d)" % w, spaced) is not None
        return w in have or (len(w) >= 4 and w in joined)

    for w in want:
        if w.isdigit() and not has(w):
            return 0.0
    core = [w for w in want if w not in bt and w not in _UNITS and not w.isdigit()]
    if core and sum(1 for w in core if has(w)) / len(core) < 0.5:
        return 0.0
    return sum(1 for w in want if has(w)) / len(want)


def same_product(item: dict, page: dict) -> tuple[bool, str]:
    """page = {name, ean}. EAN zgodny = ten sam; EAN rozny = inny; inaczej po slowach."""
    ie, pe = re.sub(r"\D", "", str(item.get("ean") or "")), re.sub(r"\D", "", str(page.get("ean") or ""))
    if ie and pe:
        return (ie == pe), ("EAN zgodny" if ie == pe else "inny EAN")
    sc = match_score(item.get("name") or "", item.get("brand"), page.get("name") or "")
    return sc >= MATCH_MIN, "zgodność nazwy %d%%" % round(sc * 100)


def parse_price(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = str(v).replace("\xa0", " ").strip()
    m = re.search(r"\d[\d .,]*", s)
    if not m:
        return None
    n = m.group().strip().replace(" ", "")
    if "," in n and "." in n:
        n = n.replace(".", "").replace(",", ".") if n.rfind(",") > n.rfind(".") else n.replace(",", "")
    elif "," in n:
        n = n.replace(",", ".") if len(n.split(",")[-1]) <= 2 else n.replace(",", "")
    elif n.count(".") > 1 or (n.count(".") == 1 and len(n.split(".")[-1]) == 3):
        n = n.replace(".", "")
    try:
        x = float(n)
    except ValueError:
        return None
    return x if x > 0 else None


def domain(url: str) -> str:
    h = (urlparse(url or "").hostname or "").lower()
    return re.sub(r"^(www|m|sklep|shop)\.", "", h)


def ai_offers_from_text(txt: str) -> list[dict]:
    """JSON z odpowiedzi AI (moze byc w ```json```) -> lista {shop, url, price, currency, name}."""
    a, b = txt.find("["), txt.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        arr = json.loads(txt[a:b + 1])
    except ValueError:
        return []
    out = []
    for o in arr if isinstance(arr, list) else []:
        if not isinstance(o, dict):
            continue
        u = str(o.get("url") or "").strip()
        if not re.match(r"^https?://", u):
            continue
        out.append({"shop": str(o.get("shop") or domain(u))[:80], "url": u[:1000], "price": parse_price(o.get("price")),
                    "currency": (str(o.get("currency") or "PLN").upper()[:5]).replace("ZŁ", "PLN").replace("ZL", "PLN"),
                    "name": str(o.get("name") or "")[:200]})
    return out[:AI_MAX_OFFERS]


def shop_key(o: dict) -> str:
    """Sklep = domena (Ceneo podaje domene sklepu, AI i link - z adresu)."""
    d = (o.get("shop") or "") if o.get("source") == "ceneo" else domain(o.get("url") or "")
    return re.sub(r"^(www|m|sklep|shop)\.", "", _fold(d).strip())


def pick(offers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Najtansza oferta na sklep; zwraca (ok posortowane - max KEEP_OK, blocked bez sklepow z 'ok' - max KEEP_BLOCKED)."""
    ok: dict = {}
    bl: dict = {}
    for o in offers:
        if o.get("price_pln") is None:
            continue
        tgt = ok if o["status"] == "ok" else bl if o["status"] == "blocked" else None
        if tgt is None:
            continue
        k = shop_key(o)
        if k not in tgt or o["price_pln"] < tgt[k]["price_pln"]:
            tgt[k] = o
    oks = sorted(ok.values(), key=lambda o: o["price_pln"])
    bls = sorted([o for k, o in bl.items() if k not in ok], key=lambda o: o["price_pln"])
    return oks[:KEEP_OK], bls[:KEEP_BLOCKED]


# ======================================================================= kursy NBP
_FX: dict = {}


def to_pln(price, cur) -> float | None:
    if price is None:
        return None
    cur = (cur or "PLN").upper()
    if cur in ("PLN", "ZŁ", "ZL"):
        return round(price, 2)
    if cur not in _FX:
        try:
            import httpx
            r = httpx.get("https://api.nbp.pl/api/exchangerates/rates/a/%s/?format=json" % cur.lower(), timeout=8)
            _FX[cur] = float(r.json()["rates"][0]["mid"]) if r.status_code == 200 else None
        except Exception:
            _FX[cur] = None
    k = _FX.get(cur)
    return round(price * k, 2) if k else None


# ======================================================================= zrodlo 1: AI z wyszukiwarka
_AI_PROMPT = """Szukasz w internecie NAJTAŃSZYCH ofert dokładnie tego produktu dla klienta w Polsce.
Produkt: {name}
Marka: {brand}
{extra}
Zasady:
- Tylko sklepy internetowe, które wysyłają do Polski (polskie i zagraniczne). Bez porównywarek (Ceneo, Skąpiec, idealo), bez aukcji z licytacją.
- DOKŁADNIE ten sam produkt i wariant (rozmiar, długość, liczba sztuk/kapsułek, kolor jeśli ma znaczenie). Inny wariant pomiń.
- Link do STRONY TEGO PRODUKTU w sklepie (nie do wyszukiwarki ani kategorii).
- Cena aktualna z tej strony (bez kosztu dostawy).
- Do {n} ofert, od najtańszej.
Odpowiedz WYŁĄCZNIE tablicą JSON, bez komentarza:
[{{"shop": "nazwa sklepu", "url": "https://...", "price": 0.0, "currency": "PLN", "name": "nazwa produktu na stronie"}}]"""


def search_ai(item: dict) -> tuple[list[dict], str]:
    import httpx
    import qbot_config as cfg
    extra = []
    if item.get("ean"):
        extra.append("EAN: %s" % item["ean"])
    if item.get("sku"):
        extra.append("Kod producenta/SKU: %s" % item["sku"])
    if item.get("url"):
        extra.append("Przykładowa strona produktu (dla identyfikacji): %s" % item["url"])
    prompt = _AI_PROMPT.format(name=item["name"], brand=item.get("brand") or "-", extra="\n".join(extra), n=AI_MAX_OFFERS)
    r = httpx.post("https://api.anthropic.com/v1/messages",
                   headers={"content-type": "application/json", "x-api-key": cfg.ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01"},
                   json={"model": cfg.ANTHROPIC_MODEL, "max_tokens": 3000, "temperature": 0,
                         "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": AI_MAX_SEARCHES,
                                    "user_location": {"type": "approximate", "country": "PL", "city": "Warsaw",
                                                      "timezone": "Europe/Warsaw"}}],
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=150)
    r.raise_for_status()
    j = r.json()
    txt = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
    u = j.get("usage") or {}
    note = "AI: %s wyszukiwań" % ((u.get("server_tool_use") or {}).get("web_search_requests", "?"))
    return ai_offers_from_text(txt), note


# ======================================================================= weryfikacja strony sklepu
def _fetch_plain(url: str):
    import requests
    r = requests.get(url, headers={"User-Agent": UA_BROWSER, "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
                                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                     timeout=12)
    if r.status_code >= 400:
        raise _HttpErr(r.status_code)
    return r.text[:3_000_000], r.url


def _fetch_browser(url: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            pg = br.new_page(user_agent=UA_BROWSER, locale="pl-PL", viewport={"width": 1280, "height": 1600})
            resp = pg.goto(url, wait_until="domcontentloaded", timeout=20000)
            try:
                pg.wait_for_load_state("networkidle", timeout=7000)
            except Exception:
                pass
            if resp is not None and resp.status >= 400:
                raise _HttpErr(resp.status)
            return pg.content(), pg.url
        finally:
            br.close()


class _HttpErr(Exception):
    def __init__(self, code):
        super().__init__("HTTP %s" % code)
        self.code = code


def read_page(url: str, render: bool = False) -> dict:
    """{name, price, currency, ean, status: ok|noprice|blocked|error, note}. Bez AI - dane strukturalne strony.
    Pobranie jak zwykla przegladarka (render=True: prawdziwa przegladarka z JavaScriptem)."""
    import qbot_gear_scrape as S
    try:
        html, final = (_fetch_browser if render else _fetch_plain)(url)
    except _HttpErr as e:
        if e.code in (401, 403, 429, 503):
            return {"status": "blocked", "note": "sklep blokuje QBota (%s)" % e.code}
        return {"status": "error", "note": str(e)}
    except Exception as e:
        return {"status": "error", "note": "%s: %s" % (type(e).__name__, str(e)[:100])}
    try:
        s, soup = S.parse_structured(html, final)
    except Exception as e:
        return {"status": "error", "note": "parser: %s" % str(e)[:80]}
    title = ""
    try:
        og = soup.find("meta", attrs={"property": "og:title"})
        title = (og.get("content") if og else "") or (soup.title.get_text(" ") if soup.title else "")
    except Exception:
        pass
    name = " ".join(x for x in (s.get("brand"), s.get("model")) if x) or title
    if title and _fold(title) not in _fold(name):
        name = name + " | " + title
    price = parse_price(s.get("price"))
    if price is None:
        # zapas: cena z meta (product:price:amount / og:price:amount / itemprop=price)
        try:
            for prop in ("product:price:amount", "og:price:amount"):
                m = soup.find("meta", attrs={"property": prop})
                if m and parse_price(m.get("content")):
                    price = parse_price(m.get("content"))
                    cm = soup.find("meta", attrs={"property": prop.replace("amount", "currency")})
                    if cm and not s.get("currency"):
                        s["currency"] = cm.get("content")
                    break
            if price is None:
                m = soup.find(attrs={"itemprop": "price"})
                if m is not None:
                    price = parse_price(m.get("content") or m.get_text(" "))
        except Exception:
            pass
    return {"status": "ok" if price else "noprice", "name": name[:300], "price": price,
            "currency": (s.get("currency") or "PLN").upper(), "ean": s.get("ean"), "url": final or url,
            "note": None if price else "brak ceny w danych strony"}


def verify(item: dict, o: dict) -> dict:
    p = read_page(o["url"])
    if p["status"] != "ok":
        p2 = read_page(o["url"], render=True)   # blokada albo strona skryptowa -> prawdziwa przegladarka
        if p2["status"] == "ok" or p["status"] != "blocked":
            p = p2
    out = dict(o, source=o.get("source") or "ai")
    if p["status"] == "blocked":
        r = dict(out, status="blocked", price_pln=to_pln(o.get("price"), o.get("currency")),
                 note=p["note"] + "; cena wg AI, niesprawdzona")
    elif p["status"] != "ok":
        r = dict(out, status="drop", price_pln=None, note=p.get("note") or "brak ceny na stronie")
    else:
        same, why = same_product(item, p)
        if not same:
            r = dict(out, status="drop", title=p.get("name"), price_pln=None, note="inny produkt/wariant (%s): %s" % (why, (p.get("name") or "")[:80]))
        else:
            r = dict(out, status="ok", title=p.get("name"), price=p["price"], currency=p["currency"], url=p.get("url") or o["url"],
                     price_pln=to_pln(p["price"], p["currency"]), note="cena sprawdzona na stronie (%s)" % why)
    _log("  %-7s %-22s %s | %s" % (r["status"], domain(o["url"])[:22], r.get("price_pln"), (r.get("note") or "")[:110]))
    return r


# ======================================================================= zrodlo 2: Ceneo (przegladarka)
def search_ceneo(item: dict) -> tuple[list[dict], str]:
    from playwright.sync_api import sync_playwright
    q = " ".join(x for x in (item.get("brand"), item["name"]) if x)
    if item.get("brand") and _fold(item["name"]).startswith(_fold(item["brand"])):
        q = item["name"]
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        try:
            pg = br.new_page(locale="pl-PL", user_agent=UA_BROWSER)
            pg.goto("https://www.ceneo.pl/;szukaj-" + quote_plus(q[:120]), wait_until="domcontentloaded", timeout=25000)
            pg.wait_for_timeout(4500)
            rows = pg.evaluate("""()=>[...document.querySelectorAll('.cat-prod-row[data-productid]')].map(r=>({
                id:r.dataset.productid, name:r.dataset.productname||'', price:r.dataset.productminprice,
                placement:r.dataset.placementId||''}))""")
            cands = []
            for r in rows:
                if "top30" in r["placement"] or "promotion" in r["placement"]:
                    continue
                sc = match_score(item["name"], item.get("brand"), r["name"])
                if sc >= MATCH_MIN:
                    cands.append((sc, r))
            cands.sort(key=lambda x: (-x[0], parse_price(x[1]["price"]) or 1e9))
            for sc, r in cands[:CENEO_PRODUCTS]:
                purl = "https://www.ceneo.pl/%s" % r["id"]
                pg.goto(purl, wait_until="domcontentloaded", timeout=25000)
                pg.wait_for_timeout(3500)
                offs = pg.evaluate("""()=>[...document.querySelectorAll('.js_productOfferGroupItem[data-shopurl]')]
                    .filter(o=>!o.classList.contains('js_recom'))
                    .map(o=>({shop:o.dataset.shopurl, price:o.dataset.price, name:o.dataset.productname||''}))""")
                for o in offs:
                    pr = parse_price(o["price"])
                    if not pr or not o["shop"] or o["shop"] == "red":
                        continue
                    out.append({"shop": o["shop"], "url": purl, "price": pr, "currency": "PLN", "price_pln": pr,
                                "title": r["name"], "source": "ceneo", "status": "ok",
                                "note": "cena z Ceneo (zgodność nazwy %d%%)" % round(sc * 100)})
        finally:
            br.close()
    return out, "Ceneo: %d ofert" % len(out)


# ======================================================================= przebieg dla pozycji
def run(item: dict) -> dict:
    """Pelny przebieg: zrodla rownolegle, weryfikacja ofert AI, wybor. Bez bazy (zapis w save_run)."""
    t0 = time.time()
    notes, offers = [], []
    own = None
    if item.get("url"):
        own = read_page(item["url"])
        if own.get("status") != "ok":
            own2 = read_page(item["url"], render=True)
            if own2.get("status") == "ok" or own.get("status") != "blocked":
                own = own2
        if own.get("status") == "ok":
            item = dict(item, ean=item.get("ean") or own.get("ean"))
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_ai = ex.submit(search_ai, item)
        f_cn = ex.submit(search_ceneo, item)
        try:
            ai, n = f_ai.result(timeout=170)
            notes.append(n + ", ofert %d" % len(ai))
        except Exception as e:
            ai = []
            notes.append("AI: błąd %s" % type(e).__name__)
        ai = [o for o in ai if domain(o["url"]) not in ("ceneo.pl", "skapiec.pl", "idealo.pl", "idealo.de")]
        with ThreadPoolExecutor(max_workers=4) as vx:   # do 4 przegladarek naraz (pamiec VPS)
            offers += list(vx.map(lambda o: verify(item, o), ai))
        try:
            cn, n = f_cn.result(timeout=120)
            offers += cn
            notes.append(n)
        except Exception as e:
            notes.append("Ceneo: błąd %s" % type(e).__name__)
    if own and own.get("status") == "ok":
        offers.append({"shop": domain(own["url"]), "url": own["url"], "price": own["price"], "currency": own["currency"],
                       "price_pln": to_pln(own["price"], own["currency"]), "title": own.get("name"), "source": "link",
                       "status": "ok", "note": "Twój link (cena sprawdzona)"})
    elif own:
        notes.append("Twój link: %s" % (own.get("note") or own.get("status")))
    ok, bl = pick(offers)
    dropped = sum(1 for o in offers if o["status"] == "drop")
    notes.append("odrzucone: %d" % dropped)
    return {"ok": ok, "blocked": bl, "dropped": dropped, "note": " · ".join(notes), "secs": round(time.time() - t0)}


# ======================================================================= baza
def ensure(c) -> None:
    c.executescript(OFFERS_DDL)
    have = {r[1] for r in c.execute("PRAGMA table_info(shop_items)")}
    for col, typ in ITEM_COLS:
        if col not in have:
            c.execute("ALTER TABLE shop_items ADD COLUMN %s %s" % (col, typ))


def save_run(c, item_id: int, res: dict, run_at: str) -> None:
    for o in res["ok"] + res["blocked"]:
        c.execute("INSERT INTO shop_offers (item_id, run_at, shop, title, price, currency, price_pln, url, source, status, note) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (item_id, run_at, o.get("shop"), (o.get("title") or o.get("name") or "")[:300], o.get("price"),
                   o.get("currency"), o.get("price_pln"), o.get("url"), o.get("source"), o["status"], (o.get("note") or "")[:300]))


def latest_offers(c, item_id: int) -> dict:
    r = c.execute("SELECT max(run_at) FROM shop_offers WHERE item_id=?", (item_id,)).fetchone()
    if not r or not r[0]:
        return {"run_at": None, "ok": [], "blocked": [], "history": []}
    rows = [dict(x) for x in c.execute("SELECT shop, title, price, currency, price_pln, url, source, status, note "
                                       "FROM shop_offers WHERE item_id=? AND run_at=? ORDER BY price_pln", (item_id, r[0]))]
    hist = [{"run_at": h[0], "min_pln": h[1], "shop": h[2]} for h in c.execute(
        "SELECT run_at, min(price_pln), shop FROM shop_offers WHERE item_id=? AND status='ok' GROUP BY run_at ORDER BY run_at",
        (item_id,))]
    return {"run_at": r[0], "ok": [x for x in rows if x["status"] == "ok"],
            "blocked": [x for x in rows if x["status"] == "blocked"], "history": hist}


def summary(res: dict) -> str:
    if res["ok"]:
        b = res["ok"][0]
        return "najtaniej %s zł w %s (%d sprawdzonych ofert)" % (
            ("%.2f" % b["price_pln"]).replace(".", ",").replace(",00", ""), b.get("shop"), len(res["ok"]))
    return "nie znalazłem sprawdzonych ofert" + (" (%d niesprawdzonych)" % len(res["blocked"]) if res["blocked"] else "")
