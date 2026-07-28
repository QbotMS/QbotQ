"""garage_enrich.py - nocne uzupelnianie Garazu z otwartych zrodel.

CO ROBI dla kazdej rzeczy bez zdjecia/adresu:
  1. jesli ma zapisany url - pobiera te strone;
     jesli nie ma - SZUKA w sieci po "marka model" i bierze do 3 kandydatow,
  2. LLM POTWIERDZA, ze strona opisuje dokladnie ten produkt (inaczej odrzuca),
  3. uzupelnia WYLACZNIE PUSTE pola: url, sku, ean, kolor, cena (tylko PLN),
  4. pobiera zdjecie produktu (packshot) jesli rzecz go nie ma.

CZEGO NIE ROBI:
  - nie nadpisuje niczego, co juz jest w bazie,
  - nie bierze wagi z marketplace'ow (tam to zwykle masa przesylki),
  - nie zgaduje: brak potwierdzenia = pomijamy i zapisujemy powod w raporcie.

Uruchomienie:  python3 scripts/garage_enrich.py [--limit N] [--table gear|equipment|components]
Wznawialny: przetwarza tylko rzeczy bez zdjecia.
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/scripts")

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

import qbot_gear_scrape as scr

DB = "/opt/qbot/app/data/garage.db"
IMG_DIR = "/opt/qbot/web/public/gear"
RAPORT = "/opt/qbot/app/docs/audit/garage_enrich_%s.md" % time.strftime("%Y-%m-%d")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
PREFIX = {"gear": "", "equipment": "eq", "components": "cmp"}
# tam waga to zwykle masa przesylki z opakowaniem - nie ufamy
MARKETPLACE = ("amazon.", "allegro.", "ebay.", "aliexpress.", "temu.", "olx.")
PRZERWA = 5.0          # sekundy miedzy zapytaniami do sieci


def log(txt):
    os.makedirs(os.path.dirname(RAPORT), exist_ok=True)
    with open(RAPORT, "a", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt, flush=True)


def szukaj(q, n=3):
    """Wyszukiwarka bez klucza API. Zwraca liste adresow."""
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": q},
                          headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.select("a.result__a"):
        h = a.get("href") or ""
        if "uddg=" in h:
            try:
                h = unquote(parse_qs(urlparse(h).query)["uddg"][0])
            except Exception:
                pass
        if h.startswith("http") and "duckduckgo.com" not in h:
            out.append(h)
        if len(out) >= n:
            break
    return out


SMIECI = re.compile(r'(zestaw|wersja|glowny|szybszy|modul|rozmiar)', re.I)


def czysc_zapytanie(marka, model):
    """Nazwy modeli w bazie bywaja opisowe, np.
    'Zipp 303 S XPLR - Zestaw #1 (glowny gravel)' albo 'Canyon CP0047 - mostek 80mm'.
    Do wyszukiwarki zostawiamy sam produkt: ucinamy po myslniku i wyrzucamy nawiasy."""
    m = model or ''
    m = re.sub(r'\([^)]*\)', ' ', m)              # tresc w nawiasach
    m = re.split(r'\s+[-\u2013\u2014]\s+', m)[0]      # wszystko po myslniku/pauzie
    m = re.sub(r'#\d+', ' ', m)
    m = re.sub(r'\s{2,}', ' ', m).strip(' -,;')
    if not m or SMIECI.search(m):
        m = re.sub(r'\s{2,}', ' ', re.sub(r'[-\u2013\u2014#()]', ' ', model or '')).strip()
    return ('%s %s' % (marka or '', m)).strip()


_SYS_WERYF = (
    "Sprawdzasz, czy strona sklepu dotyczy szukanego produktu. Dostajesz nazwe szukana "
    "(marka + model, czesto skrocona lub zapisana po polsku) oraz dane ze strony. "
    "Odpowiadasz jednym slowem. TAK gdy to ten sam produkt LUB ta sama rodzina produktu "
    "u tego samego producenta - inny kolor, rozmiar, rocznik czy nieco inna nazwa handlowa "
    "sa w porzadku. NIE gdy to inny producent, wyraznie inny typ rzeczy, strona kategorii, "
    "artykul redakcyjny bez produktu albo strona nieproduktowa. "
    "Nazwa szukana bywa niepelna - nie wymagaj doslownej zgodnosci."
)


def potwierdz(marka, model, pola, url):
    from qgpt_client import qgpt_text
    opis = "marka=%s | model=%s | kategoria=%s" % (
        pola.get("brand"), pola.get("model"), pola.get("category"))
    pyt = ("SZUKAMY: %s %s\nSTRONA (%s): %s\n\nCzy to ten sam produkt?"
           % (marka or "", model or "", urlparse(url).netloc, opis))
    try:
        odp = qgpt_text(pyt, system=_SYS_WERYF, max_tokens=5, temperature=0)
    except Exception:
        return False
    return (odp or "").strip().upper().startswith("TAK")


def zapisz_zdjecie(tabela, gid, url_obrazu):
    pref = PREFIX[tabela]
    r = requests.get(url_obrazu, headers={"User-Agent": UA}, timeout=20, stream=True)
    r.raise_for_status()
    raw = b""
    for ch in r.iter_content(8192):
        raw += ch
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("obraz za duzy")
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    os.makedirs(IMG_DIR, exist_ok=True)
    baza = "%s%d" % (pref, gid)
    full = im.copy(); full.thumbnail((1600, 1600))
    th = im.copy(); th.thumbnail((240, 240))
    full.save(os.path.join(IMG_DIR, "%s.jpg" % baza), "JPEG", quality=85)
    th.save(os.path.join(IMG_DIR, "%s_thumb.jpg" % baza), "JPEG", quality=82)
    v = int(time.time())
    return "/gear/%s.jpg?v=%d" % (baza, v), "/gear/%s_thumb.jpg?v=%d" % (baza, v)


def przetworz(conn, tabela, row, kategorie):
    gid = row["id"]
    marka, model = row["brand"], row["model"]
    nazwa = " ".join([x for x in (marka, model) if x]) or ("#%d" % gid)
    kandydaci = []
    if row["url"]:
        kandydaci = [row["url"]]
    else:
        zapytanie = czysc_zapytanie(marka, model)
        kandydaci = szukaj(zapytanie)
        time.sleep(PRZERWA)
        if not kandydaci:                      # pusto = mozliwy limit wyszukiwarki
            time.sleep(20)
            kandydaci = szukaj(zapytanie)
            time.sleep(PRZERWA)
    if not kandydaci:
        return {"id": gid, "nazwa": nazwa, "wynik": "brak wynikow wyszukiwania"}

    for url in kandydaci:
        try:
            d = scr.scrape(url, categories=kategorie, pick_image=True)
        except Exception as e:
            continue
        pola = d.get("fields") or {}
        if not row["url"] and not potwierdz(marka, czysc_zapytanie("", model), pola, url):
            continue

        zmiany, host = [], urlparse(url).netloc.lower()
        def ustaw(kol, wart, etykieta):
            if wart in (None, "") or row[kol] not in (None, ""):
                return
            conn.execute("UPDATE %s SET %s=? WHERE id=?" % (tabela, kol), (wart, gid))
            zmiany.append(etykieta)

        ustaw("url", d.get("url") or url, "url")
        if "sku" in row.keys():
            ustaw("sku", pola.get("sku"), "sku")
        if "ean" in row.keys():
            ustaw("ean", pola.get("ean"), "ean")
        if "color" in row.keys():
            ustaw("color", pola.get("color"), "kolor")
            # Kolor uproszczony (color_q) - to WLASNIE JEGO pokazuje kolumna "Kolor"
            # w tabeli Garazu. Bez tego rzecz ma kolor w bazie, ale w tabeli widac
            # pusto az do recznego wejscia w edycje i zapisania.
            if "color_q" in row.keys() and not row["color_q"]:
                _r = conn.execute("SELECT color FROM %s WHERE id=?" % tabela, (gid,)).fetchone()
                _txt = _r[0] if _r else None
                if _txt:
                    try:
                        from qbot_web import _color_q as _do_color_q
                        _q = _do_color_q(_txt)
                    except Exception:
                        _q = None
                    if _q:
                        conn.execute("UPDATE %s SET color_q=? WHERE id=?" % tabela, (_q, gid))
                        zmiany.append("kolor uproszczony %s" % _q)
        cur = (pola.get("currency") or "").upper()
        if "purchase_price" in row.keys() and cur in ("", "PLN") and pola.get("price"):
            ustaw("purchase_price", pola.get("price"), "cena")
        # waga tylko ze zrodel, gdzie to masa produktu, nie przesylki
        if pola.get("weight_g") and row["weight_g"] is None and not any(m in host for m in MARKETPLACE):
            conn.execute("UPDATE %s SET weight_g=?, weight_src='web' WHERE id=? AND weight_g IS NULL"
                         % tabela, (pola["weight_g"], gid))
            zmiany.append("WAGA %dg" % pola["weight_g"])

        if not row["photo"] and pola.get("image"):
            try:
                p, t = zapisz_zdjecie(tabela, gid, pola["image"])
                conn.execute("UPDATE %s SET photo=?, thumb=? WHERE id=?" % tabela, (p, t, gid))
                zmiany.append("zdjecie")
            except Exception as e:
                zmiany.append("zdjecie NIEUDANE (%s)" % str(e)[:40])
        conn.commit()
        time.sleep(PRZERWA)
        return {"id": gid, "nazwa": nazwa, "wynik": ", ".join(zmiany) or "nic nowego",
                "zrodlo": host}
    return {"id": gid, "nazwa": nazwa, "wynik": "zaden kandydat nie zostal potwierdzony"}


def main():
    limit = 500
    tabele = ["gear", "equipment", "components"]
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if a == "--table" and i + 1 < len(sys.argv):
            tabele = [sys.argv[i + 1]]

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    kat_gear = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM gear WHERE category IS NOT NULL")]
    kat_eq = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM equipment WHERE category IS NOT NULL")]

    log("\n# Run wzbogacania Garazu - %s" % time.strftime("%Y-%m-%d %H:%M"))
    start = time.time()
    for tabela in tabele:
        kategorie = kat_gear if tabela == "gear" else (kat_eq if tabela == "equipment" else [])
        rows = conn.execute(
            "SELECT * FROM %s WHERE active=1 AND (photo IS NULL OR photo='') "
            "ORDER BY id LIMIT ?" % tabela, (limit,)).fetchall()
        log("\n## %s - do przetworzenia: %d" % (tabela, len(rows)))
        ok = 0
        for n, row in enumerate(rows, 1):
            try:
                w = przetworz(conn, tabela, row, kategorie)
            except Exception as e:
                w = {"id": row["id"], "nazwa": row["model"], "wynik": "BLAD %s" % str(e)[:70]}
            if "zdjecie" in w["wynik"] or "WAGA" in w["wynik"]:
                ok += 1
            log("- [%d/%d] %s -> %s%s" % (n, len(rows), w["nazwa"], w["wynik"],
                                          (" (%s)" % w.get("zrodlo")) if w.get("zrodlo") else ""))
        log("\n**%s: uzupelniono istotnie %d z %d**" % (tabela, ok, len(rows)))
    log("\nCzas calosci: %.1f min" % ((time.time() - start) / 60.0))
    conn.close()


if __name__ == "__main__":
    main()
