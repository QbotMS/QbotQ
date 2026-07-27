"""qbot_gear_scrape.py - zaciaganie danych rzeczy ze strony produktu (serwis Garaz).

DWIE WARSTWY (trwale, niezalezne od konkretnego sklepu):
  W1. Dane strukturalne: JSON-LD schema.org/Product + OpenGraph + <title>.
      Szybkie i precyzyjne, ale wiele sklepow ma je puste/niepelne.
  W2. LLM czyta TEKST STRONY i wyciaga pola. Dziala niezaleznie od ukladu sklepu,
      wiec nowy sklep NIE wymaga nowej latki. Czesto wyciaga te WAGE z opisu.

Scalanie: W1 ma pierwszenstwo (twarde dane), W2 uzupelnia luki.
Kazde pole dostaje ZRODLO (provenance): 'struktura' | 'llm' | 'domena'.
Zasada: brak danych => null. Nie zgadujemy po cichu.
NIE renderuje JavaScriptu - strony ladowane dynamicznie dadza mniej.
"""
import json
import re
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; QBotGear/1.0; +https://albert.cytr.us)"
MAX_BYTES = 3_000_000
LLM_TEXT_CHARS = 9000
# Ponizej tego progu uznajemy strone za renderowana JavaScriptem i doczytujemy
# ja prawdziwa przegladarka (Playwright). Regula generyczna, nie per-sklep.
THIN_TEXT_CHARS = 2500

FIELDS = ("category", "brand", "model", "color", "price", "currency", "sku", "ean",
          "weight_g", "image")


def fetch_html(url, timeout=12):
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "pl,en;q=0.8"},
                     timeout=timeout, stream=True)
    r.raise_for_status()
    data = b""
    for chunk in r.iter_content(8192):
        data += chunk
        if len(data) > MAX_BYTES:
            break
    enc = r.encoding or "utf-8"
    return data.decode(enc, "replace"), str(r.url)


def fetch_rendered(url, timeout_ms=25000):
    """Pobiera strone z wykonaniem JavaScriptu (Playwright/Chromium)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            pg = br.new_page(user_agent=UA, locale="pl-PL",
                             viewport={"width": 1280, "height": 1600})
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                pg.wait_for_load_state("networkidle", timeout=9000)
            except Exception:
                pass
            pg.wait_for_timeout(600)
            return pg.content(), pg.url
        finally:
            br.close()


def _strf(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = next((x for x in v if x), None)
    if isinstance(v, dict):
        v = v.get("name") or v.get("@value") or v.get("url")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _iter_jsonld(soup):
    out = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = (tag.string or tag.get_text() or "").strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", txt))
            except Exception:
                continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
                continue
            if not isinstance(d, dict):
                continue
            if isinstance(d.get("@graph"), list):
                stack.extend(d["@graph"])
            out.append(d)
    return out


def _is_product(d):
    t = d.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "product" for x in t)
    return str(t).lower() == "product"


def _brand_from_host(base_url):
    host = (urlparse(base_url).hostname or "").lower()
    host = re.sub(r"^www\.", "", host)
    parts = host.split(".")
    if not parts or not parts[0]:
        return None
    label = parts[0]
    return label[:1].upper() + label[1:]


def _num(v):
    if v in (None, ""):
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(v).replace(" ", ""))
    return m.group(0).replace(",", ".") if m else None


# ---------------- W1: dane strukturalne ----------------

def parse_structured(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    res = {k: None for k in FIELDS}
    res["images"] = []

    prod = None
    for d in _iter_jsonld(soup):
        if _is_product(d):
            prod = d
            break
    if prod:
        res["model"] = _strf(prod.get("name"))
        b = prod.get("brand")
        res["brand"] = _strf(b.get("name") if isinstance(b, dict) else b)
        res["color"] = _strf(prod.get("color"))
        res["sku"] = _strf(prod.get("sku") or prod.get("mpn"))
        res["ean"] = _strf(prod.get("gtin13") or prod.get("gtin") or prod.get("gtin8")
                           or prod.get("gtin12") or prod.get("gtin14"))
        img = prod.get("image")
        if isinstance(img, str):
            res["images"] = [img]
        elif isinstance(img, list):
            res["images"] = [x for x in img if isinstance(x, str) and x]
        res["image"] = res["images"][0] if res.get("images") else None
        offers = prod.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict):
            res["price"] = _num(offers.get("price") or offers.get("lowPrice"))
            res["currency"] = _strf(offers.get("priceCurrency"))
        w = prod.get("weight")
        if isinstance(w, dict):
            wv, wu = _num(w.get("value")), (_strf(w.get("unitCode") or w.get("unitText")) or "").lower()
            if wv:
                try:
                    res["weight_g"] = int(round(float(wv) * (1000 if wu in ("kg", "kgm") else 1)))
                except ValueError:
                    pass

    def meta(prop, attr="property"):
        t = soup.find("meta", attrs={attr: prop})
        return _strf(t.get("content")) if t and t.get("content") else None

    og_title = meta("og:title")
    og_image = meta("og:image")
    if og_image:
        if og_image not in res["images"]:
            res["images"].insert(0, og_image)
        res["image"] = og_image
    if not res["model"]:
        res["model"] = og_title or _strf(soup.title.string if soup.title else None)
    if not res["price"]:
        res["price"] = _num(meta("product:price:amount") or meta("og:price:amount"))
    if not res["currency"]:
        res["currency"] = meta("product:price:currency") or meta("og:price:currency")
    if not res["color"] and og_title:
        head = re.split(r"\s*[»|]\s*", og_title)[0]
        if "," in head:
            cand = head.rsplit(",", 1)[-1].strip()
            if 0 < len(cand) <= 40:
                res["color"] = cand
    if res["image"]:
        res["image"] = urljoin(base_url, res["image"])
    res["images"] = [urljoin(base_url, u) for u in res.get("images") or []]
    return res, soup


# ---------------- W2: LLM czyta tekst strony ----------------

def page_text(soup, limit=LLM_TEXT_CHARS):
    for bad in soup(["script", "style", "noscript", "svg", "iframe", "footer", "nav"]):
        bad.decompose()
    txt = soup.get_text(" ", strip=True)
    txt = re.sub(r"\s{2,}", " ", txt)
    return txt[:limit]


_LLM_SYSTEM = (
    "Jestes precyzyjnym ekstraktorem danych produktowych ze stron sklepow rowerowych. "
    "Dostajesz TEKST strony produktu. Zwracasz WYLACZNIE obiekt JSON, bez markdown, bez komentarza. "
    "Klucze: category, brand, model, color, price, currency, sku, ean, weight_g. "
    "category = dopasuj produkt do JEDNEJ z dozwolonych kategorii podanych w zapytaniu; "
    "przepisz ja DOKLADNIE tak jak podano. Jesli produkt nie pasuje do zadnej - null. "
    "brand = producent odziezy/sprzetu (NIE nazwa sklepu). "
    "model = nazwa produktu bez marki i bez koloru. "
    "price = sama liczba; currency = kod waluty (PLN/EUR/USD/GBP...). "
    "weight_g = masa produktu w GRAMACH jako liczba calkowita (przelicz z kg jesli trzeba); "
    "jesli podano mase dla konkretnego rozmiaru, wez ja. "
    "KRYTYCZNE: jesli czegos NIE MA wprost w tekscie - wpisz null. NIE ZGADUJ, nie szacuj, "
    "nie uzupelniaj z wiedzy wlasnej o marce. Lepiej null niz zmyslona wartosc."
)


def llm_extract(text, url, categories=None):
    from qgpt_client import qgpt_text
    cats = [c for c in (categories or []) if c]
    cat_block = ("\n\nDOZWOLONE KATEGORIE (wybierz dokladnie jedna albo null):\n- "
                 + "\n- ".join(cats)) if cats else ""
    prompt = ("Adres strony: %s\n\nTEKST STRONY:\n%s%s\n\n"
              "Zwroc JSON z polami: category, brand, model, color, price, currency, sku, ean, weight_g."
              % (url, text, cat_block))
    raw = qgpt_text(prompt, system=_LLM_SYSTEM, max_tokens=400, temperature=0)
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except Exception:
        return {}
    out = {}
    cat = d.get("category")
    if cat and cats:
        cl = str(cat).strip().lower()
        for c in cats:
            if c.lower() == cl:
                out["category"] = c
                break
    for k in ("brand", "model", "color", "sku", "ean", "currency"):
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip() and str(v).strip().lower() != "null":
            out[k] = str(v).strip()[:200]
    p = _num(d.get("price"))
    if p:
        out["price"] = p
    w = d.get("weight_g")
    try:
        if w not in (None, "", "null"):
            wi = int(round(float(str(w).replace(",", "."))))
            if 1 <= wi <= 20000:
                out["weight_g"] = wi
    except (TypeError, ValueError):
        pass
    return out


# ---------------- scalanie ----------------

# ---------------- wybor zdjecia: TYLKO PRODUKT, bez modela ----------------

IMG_MAX_CHECK = 4
IMG_MIN_PX = 200


def _fetch_image(url, timeout=8, max_bytes=4_000_000):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, stream=True)
    r.raise_for_status()
    raw = b""
    for ch in r.iter_content(8192):
        raw += ch
        if len(raw) > max_bytes:
            break
    return raw


def _thumb_b64(raw, px=320):
    import io, base64
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if min(im.size) < IMG_MIN_PX:
        return None, im.size
    im.thumbnail((px, px))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return base64.b64encode(b.getvalue()).decode(), im.size


def pick_product_image(urls):
    """Z listy zdjec wybiera packshot: sam produkt, bez modela/scenerii.
    Ocena przez model widzacy obrazy. Zwraca (url, powod)."""
    from concurrent.futures import ThreadPoolExecutor
    todo = list(urls or [])[:IMG_MAX_CHECK]

    def _one(u):
        try:
            b64, _size = _thumb_b64(_fetch_image(u))
            return (u, b64) if b64 else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=5) as ex:
        cands = [x for x in ex.map(_one, todo) if x]
    if not cands:
        return (urls[0] if urls else None), "brak kandydatow do oceny"
    if len(cands) == 1:
        return cands[0][0], "jedno zdjecie"
    content = [{"type": "text", "text":
                "Ktore z tych zdjec pokazuje WYLACZNIE sam produkt (packshot na jednolitym tle, "
                "bez czlowieka, bez modela, bez scenerii)? Zdjecia sa ponumerowane od 1. "
                "Odpowiedz SAMA LICZBA. Jesli zadne nie jest packshotem, odpowiedz 0."}]
    for i, (_u, b64) in enumerate(cands, 1):
        content.append({"type": "text", "text": "Zdjecie %d:" % i})
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + b64}})
    try:
        from qgpt_client import qgpt_chat
        out = qgpt_chat([{"role": "user", "content": content}], max_tokens=10, temperature=0)
        n = int(re.search(r"\d+", (out or "")).group(0))
    except Exception as e:
        return cands[0][0], "ocena niedostepna (%s)" % str(e)[:60]
    if 1 <= n <= len(cands):
        return cands[n - 1][0], "packshot wybrany z %d zdjec" % len(cands)
    return cands[0][0], "brak packshotu wsrod %d zdjec - pierwsze z galerii" % len(cands)


def scrape(url, use_llm=True, categories=None, render=False, pick_image=True):
    """render=True wlacza doczytanie przegladarka (wolne ~30-45 s) - do batcha,
    nie do interaktywnego klikniecia."""
    html, final = fetch_html(url)
    s1, soup = parse_structured(html, final)
    text = page_text(soup)

    # Strona renderowana JavaScriptem => statyczny HTML jest pusty w tresci.
    # Doczytujemy przegladarka i uzupelniamy luki. Regula ogolna, nie per-sklep.
    rendered = False
    render_error = None
    js_page = len(text) < THIN_TEXT_CHARS
    if render and js_page:
        try:
            html2, final2 = fetch_rendered(url)
            s2, soup2 = parse_structured(html2, final2)
            text2 = page_text(soup2)
            if len(text2) > len(text):
                rendered = True
                text = text2
                final = final2 or final
                for k in FIELDS:
                    if s1.get(k) in (None, "") and s2.get(k) not in (None, ""):
                        s1[k] = s2[k]
                if not s1.get("images") and s2.get("images"):
                    s1["images"] = s2["images"]
        except Exception as e:
            render_error = str(e)[:200]

    fields = {k: s1.get(k) for k in FIELDS}
    src = {k: ("struktura" if fields.get(k) not in (None, "") else None) for k in FIELDS}

    llm = {}
    llm_error = None
    if use_llm:
        try:
            llm = llm_extract(text, final, categories)
        except Exception as e:
            llm_error = str(e)[:200]
    for k, v in llm.items():
        if k in FIELDS and fields.get(k) in (None, ""):
            fields[k] = v
            src[k] = "llm"

    if not fields.get("brand"):
        fields["brand"] = _brand_from_host(final)
        src["brand"] = "domena" if fields["brand"] else None

    if fields.get("brand") and fields.get("model"):
        b = fields["brand"].lower()
        if fields["model"].lower().startswith(b + " "):
            fields["model"] = fields["model"][len(b):].strip()

    images = s1.get("images") or ([fields["image"]] if fields.get("image") else [])
    image_note = None
    if pick_image and len(images) > 1:
        best, image_note = pick_product_image(images)
        if best:
            fields["image"] = best
            src["image"] = "packshot"

    return {"url": final, "fields": fields, "sources": src,
            "images": images, "image_note": image_note,
            "llm_used": bool(llm), "llm_error": llm_error,
            "rendered": rendered, "render_error": render_error,
            "js_page": js_page, "text_len": len(text)}
