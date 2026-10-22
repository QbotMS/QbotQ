"""QExt2 -- wazne wiadomosci (RSS) w pasku komunikatow KOKPIT. Dok.: docs/QEXT2_WIADOMOSCI.md

Decyzje Michala 22.10.2026 (sesja news-2210):
- kanaly RSS odpytywane co 2 min (warunkowo: ETag / If-Modified-Since), zrodla z SETUP (tabela news_source),
- jedno zrodlo wystarczy, filtruje AI: ocena 1-5 + ikona + skrot <= 32 znaki PO POLSKU (tlumaczenie),
- prog AI wg waznosci kanalu: wysoka >= 3, normalna >= 4, niska = 5, wylaczony = nie pobierany;
  waznosc czasowa (news_source_period, od-do) nadpisuje zwykla w swoim okresie,
- okres aktywnosci zrodla: stale albo od-do,
- bez dziennego limitu; na Karoo tylko wiadomosci opublikowane PO STARCIE jazdy, kazda grupa (te same wiadomosci
  z roznych zrodel) wyslana w jezdzie najwyzej raz,
- kanal do Karoo: pole `news` w odpowiedzi na sygnal jazdy (mcp_server._qext2_ping), bez nowego lacza.
Petla: qbot_web (watek qbot-news) -> tick() co TICK_S.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
TICK_S = 120
TEXT_MAX = 40   # 22.10: 32 bylo za malo na konkret z nazwiskiem (przyklady Michala maja 34-38); zmiesci sie -> symulator
ASSESS_MAX_AGE_H = 2      # starszych naglowkow AI nie ocenia (np. pierwsze pobranie kanalu) -- i tak nie poszlyby na Karoo
DEDUP_WINDOW_H = 6        # z iloma godzinami wstecz AI porownuje duble
BATCH = 20                # naglowkow w jednym wywolaniu AI
PER_PING = 5              # najwyzej tyle wpisow w jednej odpowiedzi na sygnal jazdy (reszta w nastepnym)
LOCK_KEY = 2210220001     # pg_try_advisory_lock -- jedna petla naraz
UA = "Mozilla/5.0 (QBot news; +https://qbot.cytr.us)"

# 22.10.2026 (akceptacja Michala): surowszy start -- wysoka >= 4, normalna = 5, niska = 5. PREMIA: ocena o 1 nizsza od progu
# przechodzi, gdy te sama wiadomosc podadza co najmniej 2 rozne redakcje (bez czekania dla wiadomosci nad progiem);
# kanal o waznosci niskiej premii nie ma (tylko 5).
IMPORTANCE = {"wysoka": 4, "normalna": 5, "niska": 5}   # waznosc kanalu -> prog oceny AI
PREMIA = {"wysoka", "normalna"}
PREMIA_WAIT_H = 6        # tyle godzin wiadomosc z ocena tuz pod progiem czeka na druga redakcje
IMP_RANK = {"wysoka": 0, "normalna": 1, "niska": 2}

DEFAULT_SOURCES = [
    ("Polsat News · Polska", "https://www.polsatnews.pl/rss/polska.xml", "pl"),
    ("Polsat News · Świat", "https://www.polsatnews.pl/rss/swiat.xml", "world"),
    ("RMF24 · Polska", "https://www.rmf24.pl/fakty/polska/feed", "pl"),
    ("RMF24 · Świat", "https://www.rmf24.pl/fakty/swiat/feed", "world"),
    ("Interia Fakty", "https://fakty.interia.pl/feed", "auto"),
    ("Deutsche Welle PL", "https://rss.dw.com/xml/rss-pol-all", "world"),
    ("Euronews PL", "https://pl.euronews.com/rss", "world"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "world"),
    ("Bankier", "https://www.bankier.pl/rss/wiadomosci.xml", "auto"),   # mieszany (kraj + swiat)
    ("Reuters (Google News)", "https://news.google.com/rss/search?q=when:24h+site:reuters.com&ceid=US:en&hl=en-US&gl=US", "world"),   # Reuters nie ma juz publicznego RSS
    # 22.10.2026: kanaly lokalne Warszawa (ikona local = 📍, osobna miara: co zmienia jazde po miescie), prosba Michala
    ("RMF24 · Warszawa", "https://www.rmf24.pl/regiony/warszawa/feed", "local"),
    ("Warszawa w Pigułce", "https://warszawawpigulce.pl/feed/", "local"),
    ("Miejski Reporter", "https://www.miejskireporter.pl/feed/", "local"),
    ("Google News · Warszawa", "https://news.google.com/rss/search?q=Warszawa+when:1d&hl=pl&gl=PL&ceid=PL:pl", "local"),
    # 22.10.2026: kanaly rowerowe (ikona bike = osobna miara: premiery gravel/osprzet/liczniki), wybor Michala
    ("Gravel Cyclist", "https://www.gravelcyclist.com/feed/", "bike"),
    ("Bikerumor", "https://bikerumor.com/feed/", "bike"),
    ("Bikepacking.com", "https://bikepacking.com/feed/", "bike"),
    ("The Radavist", "https://theradavist.com/feed/", "bike"),
    ("BikeRadar (Google News)", "https://news.google.com/rss/search?q=when:24h+site:bikeradar.com&ceid=GB:en&hl=en-GB&gl=GB", "bike"),
    ("Cyclingnews", "https://www.cyclingnews.com/feeds.xml", "bike"),
    ("Escape Collective", "https://escapecollective.com/feed/", "bike"),
]

DDL = [
    """CREATE TABLE IF NOT EXISTS qbot_v2.news_source (id serial PRIMARY KEY, name text NOT NULL, url text NOT NULL UNIQUE,
       icon text NOT NULL DEFAULT 'world', importance text NOT NULL DEFAULT 'normalna', active_from date, active_to date,
       sort int NOT NULL DEFAULT 100, etag text, last_modified text, last_ok_at timestamptz, last_error text,
       last_error_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.news_source_period (id serial PRIMARY KEY,
       source_id int NOT NULL REFERENCES qbot_v2.news_source(id) ON DELETE CASCADE,
       date_from date NOT NULL, date_to date NOT NULL, importance text NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.news_item (id bigserial PRIMARY KEY,
       source_id int NOT NULL REFERENCES qbot_v2.news_source(id) ON DELETE CASCADE, guid text NOT NULL,
       title text NOT NULL, summary text, link text, published_at timestamptz NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(),
       status text NOT NULL DEFAULT 'nowy', group_id bigint, score int, icon text, text_pl text, reason text, threshold int,
       assessed_at timestamptz, UNIQUE (source_id, guid))""",
    "CREATE INDEX IF NOT EXISTS news_item_pub_idx ON qbot_v2.news_item (published_at)",
    "ALTER TABLE qbot_v2.news_item ADD COLUMN IF NOT EXISTS user_vote smallint",   # 22.10: ocena Michala +1 / -1
    "ALTER TABLE qbot_v2.news_item ADD COLUMN IF NOT EXISTS voted_at timestamptz",
    """CREATE TABLE IF NOT EXISTS qbot_v2.news_sent (ride_id bigint NOT NULL, group_id bigint NOT NULL, item_id bigint NOT NULL,
       sent_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (ride_id, group_id))""",
]


# ------------------------------------------------------------------ czyste funkcje (testy: tests/test_qbot_news.py)
def threshold(importance: str) -> int | None:
    """Prog oceny AI dla waznosci kanalu; None = kanal wylaczony."""
    return IMPORTANCE.get(importance)


def effective_importance(base: str, periods: list[dict], day: dt.date) -> str:
    """Waznosc kanalu w danym dniu: waznosc czasowa (okres od-do obejmujacy dzien) wygrywa ze zwykla."""
    for p in periods:
        if p["date_from"] <= day <= p["date_to"]:
            return p["importance"]
    return base


def source_active(src: dict, day: dt.date) -> bool:
    """Zrodlo pobierane: nie wylaczone i dzien w okresie aktywnosci (puste od/do = stale)."""
    if src.get("importance") == "wylaczony":
        return False
    if src.get("active_from") and day < src["active_from"]:
        return False
    if src.get("active_to") and day > src["active_to"]:
        return False
    return True


def trim_text(s: str, n: int = TEXT_MAX) -> str:
    """Skrot do paska: jedna linia, <= n znakow; za dlugi -> obciecie na granicy slowa + wielokropek."""
    s = re.sub(r"\s+", " ", (s or "")).strip().strip('"„”').strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut[n // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-–") + "…"


def outlet(url: str) -> str:
    """Redakcja z adresu kanalu (Polsat PL i Polsat Swiat = jedna redakcja; Google News site:X = X)."""
    import urllib.parse as up
    u = up.urlparse(url or "")
    host = (u.hostname or "").lower()
    if host == "news.google.com":
        m = re.search(r"site:([a-z0-9.-]+)", up.unquote(u.query or ""))
        if m:
            host = m.group(1)
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "edu"):   # bbci.co.uk, x.com.pl
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def clean_text(text: str, icon: str | None) -> str:
    """Bezpiecznik formy (22.10): ikona flagi juz mowi 'Polska' -- przedrostek 'Polska:' wycinany."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if icon == "pl":
        t = re.sub(r"^(Polska|PL|W Polsce)\s*[:,–-]\s*", "", t, flags=re.I)
        t = t[:1].upper() + t[1:]
    return t


def is_fact(text: str) -> bool:
    """Bezpiecznik zasady 'tylko fakty' (22.10.2026): skrot-pytanie albo zagadka nie idzie na Karoo."""
    t = (text or "").strip()
    return bool(t) and "?" not in t and not t.lower().startswith(("kto ", "co ", "czy ", "dlaczego ", "jak ", "ile "))


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _when(it, ns) -> dt.datetime | None:
    for tag in ("pubDate", "{http://purl.org/dc/elements/1.1/}date", ns + "published", ns + "updated"):
        v = it.findtext(tag)
        if not v:
            continue
        v = v.strip()
        try:
            d = parsedate_to_datetime(v)
        except Exception:
            try:
                d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d
    return None


def parse_feed(raw: bytes) -> list[dict]:
    """RSS 2.0 / Atom -> [{guid, title, summary, link, published}] (bez daty publikacji -- pomijane)."""
    root = ET.fromstring(raw)
    atom = "{http://www.w3.org/2005/Atom}"
    out = []
    items = root.findall(".//item")
    is_atom = not items
    if is_atom:
        items = root.findall(".//" + atom + "entry")
    for it in items:
        if is_atom:
            title = it.findtext(atom + "title") or ""
            ln = it.find(atom + "link")
            link = ln.get("href") if ln is not None else ""
            summary = it.findtext(atom + "summary") or it.findtext(atom + "content") or ""
            guid = it.findtext(atom + "id") or link
        else:
            title = it.findtext("title") or ""
            link = it.findtext("link") or ""
            summary = it.findtext("description") or ""
            guid = it.findtext("guid") or link
        title = _strip_html(title)
        when = _when(it, atom)
        if not title or when is None:
            continue
        guid = (guid or "").strip() or hashlib.sha1(title.encode("utf-8")).hexdigest()
        out.append({"guid": guid[:500], "title": title[:400], "summary": _strip_html(summary)[:400],
                    "link": (link or "").strip()[:1000], "published": when})
    return out


def order_key(row: dict) -> tuple:
    """Kolejnosc wysylki na Karoo: waznosc kanalu (wysoka pierwsza), potem ocena AI, potem czas publikacji."""
    return (IMP_RANK.get(row.get("eff_importance"), 1), -(row.get("score") or 0), row["published_at"])


# ------------------------------------------------------------------ baza
def ensure(cur) -> None:
    for q in DDL:
        cur.execute(q)
    cur.execute("SELECT count(*) AS n FROM qbot_v2.news_source")
    if (cur.fetchone() or {}).get("n", 0) == 0:
        for i, (name, url, icon) in enumerate(DEFAULT_SOURCES):
            cur.execute("INSERT INTO qbot_v2.news_source (name, url, icon, sort) VALUES (%s,%s,%s,%s) ON CONFLICT (url) DO NOTHING",
                        (name, url, icon, (i + 1) * 10))


def _periods(cur) -> dict[int, list[dict]]:
    cur.execute("SELECT source_id, date_from, date_to, importance FROM qbot_v2.news_source_period ORDER BY date_from")
    out: dict[int, list[dict]] = {}
    for r in cur.fetchall():
        out.setdefault(r["source_id"], []).append(r)
    return out


# ------------------------------------------------------------------ pobieranie
def _fetch_one(src: dict) -> dict:
    req = urllib.request.Request(src["url"], headers={"User-Agent": UA})
    if src.get("etag"):
        req.add_header("If-None-Match", src["etag"])
    if src.get("last_modified"):
        req.add_header("If-Modified-Since", src["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(5_000_000)
            return {"id": src["id"], "ok": True, "items": parse_feed(raw),
                    "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {"id": src["id"], "ok": True, "items": [], "not_modified": True}
        return {"id": src["id"], "ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"id": src["id"], "ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}


def test_url(url: str) -> dict:
    """Sprawdzenie kanalu przy dodawaniu w SETUP: dziala? + 2 ostatnie naglowki."""
    r = _fetch_one({"id": 0, "url": url})
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}
    its = sorted(r["items"], key=lambda x: x["published"], reverse=True)
    if not its:
        return {"ok": False, "error": "kanał bez wiadomości z datą"}
    return {"ok": True, "count": len(its),
            "last": [{"title": i["title"], "published": i["published"].astimezone(TZ).strftime("%d.%m %H:%M")} for i in its[:2]]}


def fetch(cur, now: dt.datetime) -> dict:
    """Pobiera aktywne kanaly rownolegle, zapisuje nowe naglowki. Zwraca podsumowanie."""
    cur.execute("SELECT * FROM qbot_v2.news_source ORDER BY sort, id")
    srcs = [s for s in cur.fetchall() if source_active(s, now.astimezone(TZ).date())]
    nowe = bledy = 0
    if not srcs:
        return {"zrodel": 0, "nowe": 0, "bledy": 0}
    with cf.ThreadPoolExecutor(max_workers=min(12, len(srcs))) as ex:
        res = list(ex.map(_fetch_one, srcs))
    for r in res:
        if not r["ok"]:
            bledy += 1
            cur.execute("UPDATE qbot_v2.news_source SET last_error=%s, last_error_at=%s WHERE id=%s", (r["error"], now, r["id"]))
            continue
        cur.execute("UPDATE qbot_v2.news_source SET last_ok_at=%s, last_error=NULL, etag=COALESCE(%s, etag), "
                    "last_modified=COALESCE(%s, last_modified) WHERE id=%s",
                    (now, r.get("etag"), r.get("last_modified"), r["id"]))
        for it in r["items"]:
            if it["published"] > now + dt.timedelta(minutes=10):   # data z przyszlosci -> czas pobrania
                it["published"] = now
            stary = now - it["published"] > dt.timedelta(hours=ASSESS_MAX_AGE_H)
            cur.execute("INSERT INTO qbot_v2.news_item (source_id, guid, title, summary, link, published_at, fetched_at, status) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_id, guid) DO NOTHING",
                        (r["id"], it["guid"], it["title"], it["summary"], it["link"], it["published"], now,
                         "stary" if stary else "nowy"))
            nowe += cur.rowcount or 0
    return {"zrodel": len(srcs), "nowe": nowe, "bledy": bledy}


# ------------------------------------------------------------------ AI: ocena + tlumaczenie + skrot + duble
SYS = (
    # 22.10.2026 (decyzja Michala): kryterium = "czy to zmienia sytuacje albo wiedze kolarza mieszkajacego w Polsce".
    # Lista kategorii wybrana przez Michala; wszystko spoza niej <= 2, nawet gdy powazne (tlo wojny, katastrofy za granica).
    "Jestes redaktorem dyzurnym dla kolarza mieszkajacego w Polsce. W trakcie jazdy widzi na liczniku jedna linijke. "
    "Pytanie kluczowe: CZY TA WIADOMOSC ZMIENIA JEGO SYTUACJE ALBO WIEDZE O TYM, CO DZIEJE SIE W POLSCE I NA SWIECIE? "
    "Jesli nie zmienia - nie przeszkadzaj mu.\n"
    "Ocene 4-5 moga dostac WYLACZNIE te kategorie (wybral je uzytkownik):\n"
    " POLSKA: (a) atak lub realne zagrozenie dla Polski: drony/rakiety nad Polska, sabotaz z ofiarami, alarm RCB, ewakuacje; "
    "(b) duze decyzje panstwa: rzad, Sejm, prezydent - ustawa lub weto o duzym znaczeniu, dymisja premiera/ministra, wybory, "
    "stan wyjatkowy; (c) wielkie wydarzenia: smierc waznej osoby publicznej, katastrofa w Polsce z wieloma ofiarami, "
    "rozstrzygniecie glosnej sprawy w Polsce (zatrzymanie glosnego poszukiwanego, wazny wyrok).\n"
    # 22.10 z ocen Michala (👍): bezpieczenstwo regionu tez zmienia jego wiedze
    " BEZPIECZENSTWO REGIONU: (h) Rosja wobec Polski i Europy: grozby uzycia broni jadrowej, szpiedzy i sabotazysci "
    "zatrzymani w Polsce lub kraju sasiednim, masowe niepokoje (protesty, zamieszki) w kraju sasiednim.\n"
    " SWIAT: (d) przelom: poczatek lub koniec wojny, rozejm, traktat pokojowy; (e) atak na kraj NATO lub UE; "
    "(f) wydarzenie, o ktorym mowi caly swiat: nowy papiez, smierc przywodcy swiatowego, zamach na glowe panstwa, "
    "katastrofa o skali tysiecy ofiar.\n"
    " ROWER: (i) sprawy rowerzystow w Polsce - przepisy, budowa i zasady tras rowerowych, zmiany w ruchu drogowym dotyczace "
    "rowerow (takze projekty i konsultacje rzadowe - to zmienia jego wiedze).\n"
    " ZRODLA LOKALNE (rodzaj='lokalne', ikona 'local', Warszawa): INNA MIARA - co zmienia sytuacje kogos, kto jezdzi "
    "po Warszawie rowerem. 4-5 = zamkniete ulice, mosty, sciezki rowerowe, duze remonty i objazdy, zmiany w ruchu, blokady "
    "miasta (demonstracje, maratony, wizyty), powazne zdarzenie z zagrozeniem (pozar, ewakuacja, oblawa policji, wypadek "
    "blokujacy trase), alerty pogodowe i smogowe, nowe trasy rowerowe i zmiany Veturilo, wazne decyzje miasta. 1-2 = kultura, "
    "gastronomia, przepisy kulinarne, drobny kryminal, ciekawostki, poradniki, nekrologi lokalne. Ikona zawsze 'local'. "
    "Tekst: miejsce + co, np. 'Most Lazienkowski zamkniety do niedzieli', 'Kasprzaka: frezowanie, objazdy od piatku'.\n"
    " ZRODLA ROWEROWE (rodzaj='rower', ikona 'bike'): INNA MIARA. 4-5 = premiera nowego roweru gravel znanej marki, "
    "nowa grupa osprzetu (SRAM, Shimano, Campagnolo), nowy licznik Hammerhead / Garmin / Wahoo, nowy sprzet do bikepackingu "
    "znanej marki. 1-2 = recenzje, testy, poradniki, listy prezentowe, filmy, relacje z wypraw, wyscigi i wyniki, tresci "
    "sponsorowane, promocje. Ikona zawsze 'bike'. Tekst: marka + model + co nowego, np. 'Garmin Edge 1060: sterowanie glosem', "
    "'SRAM: nowa grupa gravel XPLR'.\n"
    " KULTURA I SPORT: (g) rozstrzygniecie glosnej sprawy, o ktorej mowia wszyscy (np. wybrano nowego aktora Bonda, "
    "polski zloty medal olimpijski, Nobel dla Polaka).\n"
    "Wszystko inne -> ocena 1-2, NAWET GDY POWAZNE: kolejne ataki i ofiary w trwajacej wojnie (tlo), katastrofy i pogoda za "
    "granica, ewakuacje firm, epidemie poza Europa, gospodarka i rynki, ceny, zwykle sledztwa i kryminal, polityczne przepychanki, "
    "sondaze, zapowiedzi, plotki, celebryci, ciekawostki.\n"
    "Dla zrodel lokalnych z innego kraju (kraj_zrodla = kod kraju) dodatkowo 4-5 dla tego, co zmienia sytuacje kogos, kto "
    "jedzie tam rowerem: strajki transportu, zamkniete drogi, pozary, erupcje, alerty pogodowe.\n"
    "5 = kategoria a-i i wydarzenie bez watpienia przelomowe; 4 = kategoria a-i; 3 = blisko, ale nie zmienia sytuacji.\n"
    "ZASADA: na licznik ida tylko FAKTY. Gdy temat jest wazny, a tytul to pytanie lub przyneta, oceniaj TEMAT i przepisz go "
    "na fakt z tytulu lub opisu (np. 'Putin uzyje broni atomowej? Komentarz Zelenskiego' -> 'Zelenski o grozbie atomowej "
    "Putina'). Ocena 1 i powod 'przyneta, brak faktu' tylko wtedy, gdy nie da sie powiedziec, co sie stalo.\n"
    "Jesli podano 'przyklady_uzytkownika' - to jego wlasne oceny wczesniejszych wiadomosci (wazne / niewazne). "
    "Trzymaj sie ich miary: podobne sprawy oceniaj tak samo.\n"
    "Dla kazdego naglowka zwroc:\n"
    "- ocena 1-5 jak wyzej;\n"
    "- ikona: 'pl' gdy wiadomosc dotyczy Polski, 'world' gdy swiata; dla zrodel z kodem kraju zwroc ten kod;\n"
    "- tekst: skrot PO POLSKU (tlumacz z kazdego jezyka), najwyzej 40 znakow ze spacjami. KONKRETNIE: kto (nazwisko, partia, "
    "instytucja) i co dokladnie zrobil; uzyj nazwisk i nazw z tytulu i opisu. NIGDY nie zaczynaj od 'Polska:' - ikona flagi "
    "juz to mowi. Dla wiadomosci ze swiata podaj na poczatku kraj lub miejsce (ikona to tylko kula ziemska). "
    "Wzorce uzytkownika: 'Nowe zasady budowy tras rowerowych' (nie 'Polska: nowe zasady tras'), "
    "'PiS: wniosek o odwolanie Kierwinskiego' (nie 'PiS: odwolanie ministra'), 'Sikorski rzucil wyzwanie Mentzenowi' "
    "(nie 'Polska: Mentzen na szkoleniu'), 'Francja: powodz, 4 ofiary', 'Sejm uchwalil budzet 2027'. "
    "Zdanie oznajmujace, bez pytajnika, emocji, cudzyslowow, wykrzyknikow i nazwy redakcji;\n"
    "- dubel: klucz wczesniejszej wiadomosci (z listy 'wczesniejsze' albo innej z tej samej paczki) o TYM SAMYM "
    "wydarzeniu, inaczej null;\n"
    "- powod: 3-8 slow po polsku: kategoria (a-i) albo dlaczego nie zmienia sytuacji.\n"
    "Zwroc WYLACZNIE JSON: {\"wyniki\":[{\"k\":\"...\",\"ocena\":1,\"ikona\":\"pl\",\"tekst\":\"...\",\"dubel\":null,\"powod\":\"...\"}]}"
)


def _llm_json(prompt: str) -> dict:
    import qgpt_client as Q
    return Q.qgpt_json(prompt, system=SYS, max_tokens=2500, temperature=0)


SYS_SHORT = (
    "Skracasz polskie komunikaty do jednej linijki licznika rowerowego. Kazdy tekst przepisz tak, by mial NAJWYZEJ 36 znakow "
    "lacznie ze spacjami (policz znaki!). Zostaw nazwiska i konkret (kto i co zrobil), bez 'Polska:' na poczatku; dla swiata "
    "kraj na poczatku (np. 'Francja: powodz, 4 ofiary'). Zachowaj sam fakt, po polsku, bez cudzyslowow i wykrzyknikow; mozesz pominac "
    "szczegoly i liczby drugorzedne, uzyc skrotow (UE, USA, PE, MSZ). Zwroc WYLACZNIE JSON {\"k\": \"tekst\", ...} z tymi samymi kluczami."
)


def shorten(texts: dict[str, str], rounds: int = 2) -> dict[str, str]:
    """Teksty dluzsze niz TEXT_MAX -> AI przepisuje krocej (do 2 rund); co dalej za dlugie, obcina trim_text."""
    import qgpt_client as Q
    out = dict(texts)
    for _ in range(rounds):
        todo = {k: v for k, v in out.items() if len(v.strip()) > TEXT_MAX}
        if not todo:
            break
        r = Q.qgpt_json(json.dumps(todo, ensure_ascii=False), system=SYS_SHORT, max_tokens=1200, temperature=0)
        for k, v in (r or {}).items():
            if k in out and isinstance(v, str) and v.strip():
                out[k] = re.sub(r"\s+", " ", v).strip()
    return out


VOTE_EXAMPLES = 40   # ile ostatnich ocen Michala idzie do instrukcji AI jako przyklady


def examples(cur, n: int = VOTE_EXAMPLES) -> list[dict]:
    """Ostatnie oceny Michala (podglad SETUP: 👍/👎) jako przyklady dla AI -- uczy QBota jego miary waznosci."""
    cur.execute("""SELECT title, text_pl, user_vote FROM qbot_v2.news_item WHERE user_vote IS NOT NULL
                   ORDER BY voted_at DESC NULLS LAST LIMIT %s""", (n,))
    return [{"tytul": r["title"][:160], "skrot": r["text_pl"], "uzytkownik": "wazne" if r["user_vote"] > 0 else "niewazne"}
            for r in cur.fetchall()]


def vote(cur, item_id: int, v: int, now: dt.datetime | None = None) -> dict:
    """Ocena Michala dla naglowka: +1 wazne, -1 niewazne, 0 = cofnij. Dotyczy calej grupy dubli."""
    now = now or dt.datetime.now(TZ)
    v = 1 if v > 0 else (-1 if v < 0 else None)
    cur.execute("UPDATE qbot_v2.news_item SET user_vote=%s, voted_at=%s WHERE id=%s RETURNING id", (v, now if v else None, item_id))
    return {"status": "OK" if cur.fetchone() else "BRAK", "id": item_id, "vote": v}


def assess(cur, now: dt.datetime, llm=_llm_json, short=shorten) -> dict:
    """Ocena nowych naglowkow paczkami (jedno wywolanie AI na paczke). Ustawia status, ocene, ikone, skrot, grupe."""
    cur.execute("""SELECT i.id, i.title, i.summary, s.name, s.icon FROM qbot_v2.news_item i
                   JOIN qbot_v2.news_source s ON s.id=i.source_id WHERE i.status='nowy' ORDER BY i.published_at LIMIT %s""",
                (BATCH * 3,))
    todo = cur.fetchall()
    if not todo:
        return {"ocenione": 0}
    cur.execute("""SELECT id, group_id, text_pl FROM qbot_v2.news_item
                   WHERE assessed_at >= %s AND text_pl IS NOT NULL AND status <> 'blad' ORDER BY assessed_at DESC LIMIT 80""",
                (now - dt.timedelta(hours=DEDUP_WINDOW_H),))
    earlier = cur.fetchall()
    group_of = {f"g{e['id']}": e["group_id"] or e["id"] for e in earlier}
    votes = examples(cur)
    periods = _periods(cur)
    cur.execute("SELECT id, importance FROM qbot_v2.news_source")
    base_imp = {r["id"]: r["importance"] for r in cur.fetchall()}
    cur.execute("SELECT id, source_id FROM qbot_v2.news_item WHERE id = ANY(%s)", ([t["id"] for t in todo],))
    src_of = {r["id"]: r["source_id"] for r in cur.fetchall()}
    day = now.astimezone(TZ).date()
    done = 0
    for b in range(0, len(todo), BATCH):
        part = todo[b:b + BATCH]
        payload = {
            "przyklady_uzytkownika": votes,
            "wczesniejsze": [{"k": f"g{e['id']}", "tekst": e["text_pl"]} for e in earlier[:60]],
            "nowe": [{"k": f"n{t['id']}", "zrodlo": t["name"],
                      "kraj_zrodla": (t["icon"] if t["icon"] not in ("pl", "world", "auto", "bike", "local") else None),
                      "rodzaj": ("rower" if t["icon"] == "bike" else "lokalne" if t["icon"] == "local" else "wiadomosci"),
                      "tytul": t["title"], "opis": (t["summary"] or "")[:300]} for t in part],
        }
        try:
            out = llm(json.dumps(payload, ensure_ascii=False))
            res = {str(x.get("k")): x for x in (out.get("wyniki") or []) if isinstance(x, dict)}
        except Exception as e:  # noqa: BLE001
            for t in part:
                cur.execute("UPDATE qbot_v2.news_item SET status='blad', reason=%s, assessed_at=%s WHERE id=%s",
                            (f"AI: {type(e).__name__}"[:200], now, t["id"]))
            continue
        longs = {k: str(v.get("tekst") or "") for k, v in res.items() if len(str(v.get("tekst") or "").strip()) > TEXT_MAX}
        if longs:   # 22.10: AI czesto przekracza 32 znaki -- dodatkowe skracanie zamiast obcinania w pol slowa
            try:
                for k, v in short(longs).items():
                    res[k]["tekst"] = v
            except Exception:  # noqa: BLE001
                pass
        for t in part:
            x = res.get(f"n{t['id']}")
            if not x:
                cur.execute("UPDATE qbot_v2.news_item SET status='blad', reason='AI pominelo naglowek', assessed_at=%s WHERE id=%s",
                            (now, t["id"]))
                continue
            try:
                score = max(1, min(5, int(x.get("ocena"))))
            except Exception:
                score = 1
            icon = t["icon"] if t["icon"] not in ("auto",) else (x.get("ikona") if x.get("ikona") in ("pl", "world") else "world")
            if t["icon"] == "world" and x.get("ikona") == "pl":
                icon = "pl"   # kanal swiatowy, ale wiadomosc o Polsce
            text = trim_text(clean_text(x.get("tekst") or t["title"], icon))
            dub = x.get("dubel")
            gid = group_of.get(str(dub)) if dub else None
            if gid is None and dub and str(dub).startswith("n"):
                try:
                    gid = group_of.get(str(dub)) or int(str(dub)[1:])
                except Exception:
                    gid = None
            gid = gid or t["id"]
            imp = effective_importance(base_imp.get(src_of[t["id"]], "normalna"), periods.get(src_of[t["id"]], []), day)
            thr = threshold(imp) or 6
            if score >= thr:
                status = "przeszlo"
            elif score == thr - 1 and imp in PREMIA:
                status = "czeka"   # na druga redakcje (promote)
            else:
                status = "odrzucone"
            if status in ("przeszlo", "czeka") and not is_fact(text):
                status, x["powod"] = "odrzucone", "pytanie/przyneta zamiast faktu"
            cur.execute("""UPDATE qbot_v2.news_item SET status=%s, score=%s, icon=%s, text_pl=%s, reason=%s, threshold=%s,
                           group_id=%s, assessed_at=%s WHERE id=%s""",
                        (status, score, icon, text, str(x.get("powod") or "")[:200], thr, gid, now, t["id"]))
            group_of[f"n{t['id']}"] = gid
            group_of[f"g{t['id']}"] = gid
            done += 1
    return {"ocenione": done}


def promote(cur, now: dt.datetime) -> dict:
    """Premia 2 redakcji: wiadomosc 'czeka' przechodzi, gdy w jej grupie (duble) sa naglowki z >= 2 roznych redakcji;
    po PREMIA_WAIT_H bez potwierdzenia -> odrzucone."""
    cur.execute("SELECT id, COALESCE(group_id, id) AS gid, assessed_at FROM qbot_v2.news_item WHERE status='czeka'")
    up = down = 0
    for w in cur.fetchall():
        cur.execute("""SELECT DISTINCT s.url FROM qbot_v2.news_item i JOIN qbot_v2.news_source s ON s.id=i.source_id
                       WHERE COALESCE(i.group_id, i.id)=%s AND i.assessed_at IS NOT NULL""", (w["gid"],))
        red = {outlet(r["url"]) for r in cur.fetchall()}
        if len(red) >= 2:
            cur.execute("UPDATE qbot_v2.news_item SET status='przeszlo', reason=COALESCE(reason,'') || %s WHERE id=%s",
                        (" · potwierdzone: " + ", ".join(sorted(red))[:120], w["id"]))
            up += 1
        elif w["assessed_at"] and now - w["assessed_at"] > dt.timedelta(hours=PREMIA_WAIT_H):
            cur.execute("UPDATE qbot_v2.news_item SET status='odrzucone', reason=COALESCE(reason,'') || %s WHERE id=%s",
                        (" · brak 2. redakcji", w["id"]))
            down += 1
    return {"premia": up, "bez_potwierdzenia": down}


def tick(conn, now: dt.datetime | None = None) -> dict:
    """Jeden obieg petli: pobranie + ocena. Advisory lock -- dwa procesy nie robia tego naraz."""
    now = now or dt.datetime.now(TZ)
    cur = conn.cursor()
    ensure(cur)
    conn.commit()
    cur.execute("SELECT pg_try_advisory_lock(%s) AS ok", (LOCK_KEY,))
    if not (cur.fetchone() or {}).get("ok"):
        return {"status": "ZAJETE"}
    try:
        f = fetch(cur, now)
        conn.commit()
        a = assess(cur, now)
        conn.commit()
        pr = promote(cur, now)
        conn.commit()
        return {"status": "OK", **f, **a, **pr}
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()


# ------------------------------------------------------------------ dla Karoo
def for_ride(cur, ride_id: int, now: dt.datetime | None = None) -> list[dict]:
    """Wpisy do pola `news` odpowiedzi na sygnal jazdy: opublikowane po starcie jazdy, ktore przeszly prog, grupa jeszcze
    niewyslana w tej jezdzie. Oznacza je jako wyslane. Najwyzej PER_PING (reszta przy nastepnym sygnale)."""
    now = now or dt.datetime.now(TZ)
    ensure(cur)
    cur.execute("SELECT started_at FROM qbot_v2.karoo_live WHERE id=%s", (ride_id,))
    r = cur.fetchone()
    if not r:
        return []
    cur.execute("""SELECT DISTINCT ON (COALESCE(i.group_id, i.id)) i.id, COALESCE(i.group_id, i.id) AS gid, i.icon, i.text_pl,
                          i.score, i.published_at, i.source_id, s.importance
                   FROM qbot_v2.news_item i JOIN qbot_v2.news_source s ON s.id=i.source_id
                   WHERE i.status='przeszlo' AND i.published_at >= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.news_sent n WHERE n.ride_id=%s AND n.group_id=COALESCE(i.group_id, i.id))
                   ORDER BY COALESCE(i.group_id, i.id), i.published_at""", (r["started_at"], ride_id))
    rows = cur.fetchall()
    if not rows:
        return []
    periods = _periods(cur)
    day = now.astimezone(TZ).date()
    for x in rows:
        x["eff_importance"] = effective_importance(x["importance"], periods.get(x["source_id"], []), day)
    rows.sort(key=order_key)
    out = []
    for x in rows[:PER_PING]:
        cur.execute("INSERT INTO qbot_v2.news_sent (ride_id, group_id, item_id, sent_at) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT DO NOTHING", (ride_id, x["gid"], x["id"], now))
        out.append({"id": f"n{x['id']}", "icon": x["icon"] or "world", "text": x["text_pl"], "importance": x["score"],
                    "published": x["published_at"].astimezone(TZ).strftime("%H:%M")})
    return out


def cleanup(cur, now: dt.datetime, keep_days: int = 14) -> int:
    """Kasuje naglowki starsze niz keep_days (podglad w SETUP pokazuje ostatnie dni)."""
    cur.execute("DELETE FROM qbot_v2.news_item WHERE fetched_at < %s", (now - dt.timedelta(days=keep_days),))
    n = cur.rowcount or 0
    cur.execute("DELETE FROM qbot_v2.news_sent WHERE sent_at < %s", (now - dt.timedelta(days=keep_days),))
    return n


# ------------------------------------------------------------------ podglad dla SETUP > QExt2 > Wiadomosci
def _f(d):
    return d.astimezone(TZ).strftime("%d.%m %H:%M") if d else None


def view(cur, hours: int = 24, now: dt.datetime | None = None) -> dict:
    """Dane strony SETUP > QExt2 > Wiadomosci: zrodla (waznosc, prog, okresy, stan kanalu) i naglowki z ostatnich `hours` h
    z ocena AI, powodem, dublami i informacja, czy i kiedy poszly na Karoo. Naglowki 'stary' tylko w liczniku."""
    now = now or dt.datetime.now(TZ)
    day = now.astimezone(TZ).date()
    periods = _periods(cur)
    cur.execute("SELECT * FROM qbot_v2.news_source ORDER BY sort, id")
    sources = []
    for s in cur.fetchall():
        per = periods.get(s["id"], [])
        eff = effective_importance(s["importance"], per, day)
        sources.append({
            "id": s["id"], "name": s["name"], "url": s["url"], "icon": s["icon"], "outlet": outlet(s["url"]),
            "importance": s["importance"], "importance_now": eff, "threshold": threshold(eff),
            "premia": eff in PREMIA, "active_now": source_active(s, day),
            "active_from": s["active_from"].strftime("%d.%m.%Y") if s["active_from"] else None,
            "active_to": s["active_to"].strftime("%d.%m.%Y") if s["active_to"] else None,
            "periods": [{"od": p["date_from"].strftime("%d.%m.%Y"), "do": p["date_to"].strftime("%d.%m.%Y"),
                         "importance": p["importance"]} for p in per],
            "last_ok": _f(s["last_ok_at"]), "last_error": s["last_error"], "last_error_at": _f(s["last_error_at"])})
    since = now - dt.timedelta(hours=hours)
    cur.execute("SELECT status, count(*) AS n FROM qbot_v2.news_item WHERE fetched_at >= %s GROUP BY status", (since,))
    counts = {r["status"]: r["n"] for r in cur.fetchall()}
    cur.execute("""SELECT i.id, COALESCE(i.group_id, i.id) AS gid, i.status, i.score, i.threshold, i.icon, i.text_pl, i.reason,
                          i.title, i.link, i.published_at, s.name AS source, i.user_vote,
                          (SELECT min(n.sent_at) FROM qbot_v2.news_sent n WHERE n.group_id=COALESCE(i.group_id, i.id)) AS sent_at
                   FROM qbot_v2.news_item i JOIN qbot_v2.news_source s ON s.id=i.source_id
                   WHERE i.published_at >= %s AND i.status <> 'stary'
                   ORDER BY i.published_at DESC LIMIT 400""", (since,))
    items = [{"id": r["id"], "gid": r["gid"], "dubel": r["gid"] != r["id"], "status": r["status"], "score": r["score"],
              "threshold": r["threshold"], "icon": r["icon"], "text": r["text_pl"], "reason": r["reason"], "title": r["title"],
              "link": r["link"], "published": _f(r["published_at"]), "source": r["source"], "sent": _f(r["sent_at"]),
              "vote": r["user_vote"]}
             for r in cur.fetchall()]
    cur.execute("SELECT count(*) AS n FROM qbot_v2.news_item WHERE user_vote IS NOT NULL")
    nvotes = cur.fetchone()["n"]
    return {"status": "OK", "now": _f(now), "hours": hours, "tick_s": TICK_S, "text_max": TEXT_MAX,
            "votes": nvotes, "vote_examples": VOTE_EXAMPLES,
            "importance_thresholds": IMPORTANCE, "premia": sorted(PREMIA), "premia_wait_h": PREMIA_WAIT_H,
            "sources": sources, "counts": counts, "items": items}
