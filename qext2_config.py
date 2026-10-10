"""QExt2 (Karoo) - ustawienia komunikatow i kolorow pol KOKPIT 2, edytowane w QBot SETUP > QExt2.

Etap 1 (2026-10-10): DEFAULTS = dokladny opis obecnego zachowania QExt2 (wyciagniety z kodu:
RouteMessageEngine.kt, Kokpit2.kt, EtaEngine.steepDescentAhead); widok tylko do odczytu.
Etap 2: zapis zmian w qbot_v2.app_settings (klucz KEY) - nadpisania nakladane na DEFAULTS.
Etap 3: QExt2 pobiera wynik view()['config'] razem z /ride-readiness i stosuje.
Dok.: docs/QEXT2_CONFIG.md
"""
import copy
import json

KEY = "qext2_config"
VERSION = 1

LEVELS = {"info": "informacja (ciemne tło)", "warn": "ostrzeżenie (żółte tło)", "crit": "krytyczny (bordowe tło)"}

# kolejnosc listy = obecna precedencja (wyzej = wazniejszy, wypiera nizsze z paska)
MESSAGES = [
    {"id": "hub", "name": "Komunikat z centrali (QBot / ActiveMessageHub)", "level": "by_severity",
     "level_note": "wg ważności nadawcy: krytyczny = bordowe, ostrzeżenie = żółte", "on": True,
     "when": "zawsze, gdy centrala wysłała komunikat; przykrywa wszystkie pozostałe", "params": {}},
    {"id": "wprime", "name": "W′ – rezerwa", "level": "crit", "on": True,
     "when": "stan rezerwy W′ z modelu podjazdów (BOMBA / ODBUDOWA / TRZYMASZ / PRZEPAŁ); trzymany na ekranie bez rotacji",
     "params": {}},
    {"id": "rain_now", "name": "Deszcz teraz", "level": "warn", "on": True, "when": "pada ≥ próg (mm/h)",
     "params": {"min_mmh": {"v": 0.1, "unit": "mm/h", "label": "próg opadu"}}},
    {"id": "storm", "name": "Burza nadchodzi", "level": "warn", "on": True, "when": "burza w prognozie po trasie w ciągu N min",
     "params": {"lead_min": {"v": 60, "unit": "min", "label": "wyprzedzenie"}}},
    {"id": "snow", "name": "Śnieg nadchodzi", "level": "warn", "on": True, "when": "śnieg w prognozie po trasie w ciągu N min",
     "params": {"lead_min": {"v": 30, "unit": "min", "label": "wyprzedzenie"}}},
    {"id": "rain_soon", "name": "Deszcz nadchodzi", "level": "warn", "on": True,
     "when": "deszcz w prognozie po trasie w ciągu N min i z prawdopodobieństwem ≥ P",
     "params": {"lead_min": {"v": 30, "unit": "min", "label": "wyprzedzenie"}, "min_prob": {"v": 40, "unit": "%", "label": "min. prawdopodobieństwo"}}},
    {"id": "fuel", "name": "Jedzenie (bilans węglowodanów)", "level": "warn", "on": True, "when": "bilans węglowodanów ≤ próg",
     "params": {"alert_g": {"v": -30, "unit": "g", "label": "próg bilansu"}}},
    {"id": "dusk_after", "name": "Meta po zmroku", "level": "warn", "on": True, "when": "przewidywana meta (ETA) po zmroku", "params": {}},
    {"id": "dusk_soon", "name": "Do zmroku", "level": "warn", "on": True, "when": "do zmroku zostało ≤ N min",
     "params": {"warn_min": {"v": 45, "unit": "min", "label": "ostrzeżenie przed zmrokiem"}}},
    {"id": "descent", "name": "Stromy zjazd", "level": "crit", "on": True,
     "when": "na trasie w promieniu R km odcinek o nachyleniu ≤ próg (z nawierzchnią, gdy nie asfalt)",
     "params": {"threshold_pct": {"v": -6, "unit": "%", "label": "próg nachylenia"}, "near_km": {"v": 3.0, "unit": "km", "label": "zasięg zapowiedzi"}}},
    {"id": "climb", "name": "Podjazd", "level": "info", "on": True,
     "when": "najbliższy podjazd Karoo w promieniu R km; dalej – jako komunikat domyślny, gdy nic bliżej",
     "params": {"near_km": {"v": 3.0, "unit": "km", "label": "zasięg zapowiedzi"}}},
    {"id": "surface", "name": "Zmiana nawierzchni", "level": "info", "on": True,
     "when": "najbliższa zmiana nawierzchni (z QBota) w promieniu R km; dalej – jako komunikat domyślny",
     "params": {"near_km": {"v": 3.0, "unit": "km", "label": "zasięg zapowiedzi"}}},
    {"id": "poi", "name": "Punkty: woda / sklep / jedzenie", "level": "info", "on": True,
     "when": "najbliższy punkt z QBota w promieniu R km; woda najpierw, zamknięte dziś pomijane",
     "params": {"near_km": {"v": 2.0, "unit": "km", "label": "zasięg"}, "skip_closed": {"v": True, "unit": "", "label": "pomijaj zamknięte"}}},
]

ORDER_NOTE = ("Zjazd, podjazd i nawierzchnia w zasięgu są między sobą układane wg odległości (najbliższy pierwszy); "
              "bez trasy pokazywane są tylko komunikaty od W′ do zmroku.")

ROTATION = {
    "urgent_solo_s": {"v": 20, "unit": "s", "label": "pilny (deszcz, jedzenie, zmrok) sam na ekranie"},
    "rotate_s": {"v": 8, "unit": "s", "label": "potem na zmianę z kolejnymi co"},
    "min_hold_s": {"v": 5, "unit": "s", "label": "minimalny czas komunikatu na ekranie"},
}

# kolory pol: tylko tam, gdzie sa realne alternatywy; "v" = obecne zachowanie
COLORS = [
    {"id": "power", "field": "Moc (dolne pole)", "v": "pacing",
     "options": {"pacing": "wg tempa (PacingEngine): biała < 85% pułapu, zielona 85–100%, czerwona > pułapu > 10 s, tło alarmu > 30 s",
                 "zones": "wg stref CP (Z1–Z6, jak cyfra przy piorunie)"}},
    {"id": "wbal", "field": "W′ % (dolne pole)", "v": "trend",
     "options": {"trend": "wg trendu: zielony rośnie, czerwony spada, biały stały",
                 "level": "wg poziomu: biały > 50%, żółty 20–50%, czerwony < 20%"}},
    {"id": "hr", "field": "Tętno (dolne pole)", "v": "zone",
     "options": {"zone": "strefa (Z1–Z5); Z4 żółta, Z5 czerwona; serce wg dryfu tętna", "bpm": "uderzenia/min (te same kolory)"}},
    {"id": "speed", "field": "Prędkość (dolne pole)", "v": "yellow",
     "options": {"yellow": "zawsze żółta (#F2C230) – odróżnia się od mocy", "white": "biała"}},
    {"id": "wind", "field": "Strzałka wiatru (górne pole)", "v": "headtail",
     "options": {"headtail": "czerwona – w twarz, zielona – w plecy, biała – boczny/słaby", "white": "zawsze biała"},
     "params": {"min_mps": {"v": 3, "unit": "m/s", "label": "próg siły"}, "share": {"v": 70, "unit": "%", "label": "udział składowej czołowej"}}},
    {"id": "turn", "field": "Znak manewru (górne pole)", "v": "sharp_warn",
     "options": {"sharp_warn": "żółty: ostro, nawrót, rondo z zawróceniem; reszta biała", "white": "zawsze biały"}},
    {"id": "eta", "field": "ETA (górne pole)", "v": "deadline",
     "options": {"deadline": "wg zapasu do zmroku: czerwona po zmroku, żółta ≤ Y min, zielona ≥ G min, biała pomiędzy"},
     "params": {"green_min": {"v": 30, "unit": "min", "label": "zielona od zapasu"}, "yellow_min": {"v": 10, "unit": "min", "label": "żółta do zapasu"}}},
]


# PELNE ZESTAWIENIE KOLOROW KOKPIT 2 (tylko odczyt; zrodlo: Kokpit2.kt, RideDataAggregator.unifiedPowerColors,
# RouteMessageEngine). Pozycje z "cfg" zaleza od wyboru w sekcji Kolory pol (wyswietlane wg obecnego ustawienia).
PALETTE = [
  {"group": "Dolne pole (instr)", "items": [
    {"el": "Belka trasy", "rules": [["#2E7BFF", "przejechane"], ["#F2F4F7", "przed tobą: asfalt"], ["#FFB300", "przed tobą: szuter"],
                                     ["#FF2A2A", "przed tobą: trudne / sypkie"], ["#FF3DF5", "długie postoje"],
                                     ["#39FF14", "twoja pozycja (koło z czarną obwódką)"], ["#465366", "tło belki / brak trasy"]]},
    {"el": "Moc (liczba)", "cfg": "power", "rules": [["#CBD5E1", "brak profilu tempa / brak mocy / dane > 5 s"], ["#FFFFFF", "< 85% pułapu tempa"],
        ["#4ADE80", "85–100% pułapu (w celu)"], ["#FFFFFF", "nad pułapem do 10 s (zryw tolerowany)"], ["#FF5252", "nad pułapem > 10 s"],
        ["#FF5252", "nad pułapem > 30 s: czerwone TŁO pod cyframi, cyfry czarne (gaśnie po 5 s poniżej)"]]},
    {"el": "Piorun + numer strefy", "rules": [["#9AA3AE", "Z1 (< 55% CP)"], ["#6FA8FF", "Z2 (55–75%)"], ["#22C55E", "Z3 (75–90%)"],
        ["#EAB308", "Z4 (90–105%)"], ["#F97316", "Z5 (105–120%)"], ["#EF4444", "Z6 (> 120%)"], ["#9AA5B1", "brak mocy / CP"]]},
    {"el": "Prędkość (liczba)", "cfg": "speed", "rules": [["#F2C230", "zawsze żółta"], ["#9AA3AE", "brak danych"]]},
    {"el": "W′ %", "cfg": "wbal", "rules": [["#4ADE80", "trend: rośnie"], ["#FF8C8C", "trend: spada"], ["#FFFFFF", "trend: stały"],
        ["#9AA3AE", "brak danych"]]},
    {"el": "Tętno", "cfg": "hr", "rules": [["#FFFFFF", "Z1–Z3"], ["#FACC15", "Z4"], ["#FF8C8C", "Z5"], ["#9AA3AE", "brak danych"]]},
    {"el": "Serce przy tętnie", "rules": [["#FFFFFF", "bez dryfu"], ["#FB923C", "dryf tętna – umiarkowany"], ["#FF8C8C", "dryf tętna – duży"]]},
    {"el": "NP 5 – podpis", "rules": [["#4ADE80", "NP 5 min rośnie"], ["#FF8C8C", "spada"], ["#C9D2DC", "stała"]]},
    {"el": "⌀ – symbol średniej prędkości", "rules": [["#4ADE80", "średnia rośnie"], ["#FF8C8C", "spada"], ["#C9D2DC", "stała"]]},
    {"el": "Kadencja, NP 5, ⌀ (liczby)", "rules": [["#FFFFFF", "wartość"], ["#9AA3AE", "brak danych"]]},
    {"el": "Bieg", "rules": [["#AEB8C4", "blat (szary – rzadko się zmienia)"], ["#FFFFFF", "koronka"], ["#9AA5B1", "znak ×"]]},
    {"el": "Podpisy i jednostki (KAD, BIEG, W′%, V km/h, W)", "rules": [["#9AA5B1", "szare"]]},
  ]},
  {"group": "Górne pole (nav)", "items": [
    {"el": "Pasek komunikatów – tło", "rules": [["#1E2731", "informacja (tekst biały)"], ["#FFC21A", "ostrzeżenie (tekst czarny)"],
        ["#8B0A1A", "krytyczny (tekst biały)"], ["#FB923C", "napis DEMO (czarny na żółtym tle)"]]},
    {"el": "Temperatura", "rules": [["#FFFFFF", "wartość"], ["#AEB8C4", "termometr"], ["#9AA3AE", "brak danych"]]},
    {"el": "Pogoda / opad", "rules": [["#60A5FA", "deszcz (kropla, %, mm)"], ["#BFDBFE", "śnieg"], ["#FF8C8C", "burza (błyskawica i %)"],
        ["#FACC15", "słońce"], ["#E5E7EB", "chmura przy częściowym zachmurzeniu"], ["#9AA5B1", "pochmurno, mgła"]]},
    {"el": "Manewr (ikona i dystans)", "cfg": "turn", "rules": [["#FFFFFF", "zwykłe: lewo/prawo, lekko, prosto, rondo"],
        ["#FFC21A", "ostro, nawrót, rondo z zawróceniem"], ["#9AA5B1", "jednostka m / km"]]},
    {"el": "Nachylenie – trójkąt (wysokość rośnie z nachyleniem)", "rules": [["#3B4BA8", "≤ −8%"], ["#5B9BE0", "−8 … −5%"], ["#2DD4BF", "−5 … −2%"],
        ["#9AA5B1", "−2 … 1%"], ["#86EFAC", "1 … 2%"], ["#22C55E", "2 … 5%"], ["#EAB308", "5 … 8%"], ["#FDBA74", "8 … 11%"],
        ["#F97316", "11 … 14%"], ["#EF4444", "14 … 20%"], ["#A855F7", "≥ 20%"]]},
    {"el": "Nachylenie – liczba", "rules": [["#FFFFFF", "wartość"], ["#9AA5B1", "znak %"]]},
    {"el": "DST, DTD", "rules": [["#FFFFFF", "wartości"], ["#AEB8C4", "pionowe podpisy"]]},
    {"el": "ETA", "cfg": "eta", "rules": [["#FF8C8C", "meta po zmroku"], ["#FACC15", "zapas do zmroku ≤ próg żółty"],
        ["#4ADE80", "zapas ≥ próg zielony"], ["#FFFFFF", "pomiędzy / bez zmroku"]]},
    {"el": "Wiatr – strzałka (kierunek względem jazdy)", "cfg": "wind", "rules": [["#FF8C8C", "w twarz (składowa czołowa ≥ próg)"],
        ["#4ADE80", "w plecy"], ["#FFFFFF", "boczny / słaby"]]},
    {"el": "Wiatr – liczba i m/s", "rules": [["#FFFFFF", "wartość"], ["#AEB8C4", "m / s"]]},
  ]},
]

def defaults():
    return {"version": VERSION, "messages": copy.deepcopy(MESSAGES), "rotation": copy.deepcopy(ROTATION), "colors": copy.deepcopy(COLORS)}


def _ensure(cur):
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def stored(cur):
    """Zapisane nadpisania (etap 2) albo None."""
    _ensure(cur)
    cur.execute("SELECT value, updated_at FROM qbot_v2.app_settings WHERE key=%s", (KEY,))
    r = cur.fetchone()
    if not r:
        return None, None
    v = r[0] if not isinstance(r, dict) else r["value"]
    ts = r[1] if not isinstance(r, dict) else r["updated_at"]
    if isinstance(v, str):
        v = json.loads(v)
    return v, ts


def _coerce(default, v):
    """Wartosc z formularza w typie wartosci domyslnej (bool/int/float); None = odrzuc."""
    try:
        if isinstance(default, bool):
            return bool(v)
        f = float(v)
        if f != f or abs(f) > 100000:
            return None
        return int(round(f)) if isinstance(default, int) else round(f, 2)
    except Exception:
        return None


def effective(st):
    """DEFAULTS z nalozonymi zapisanymi zmianami. Nieznane id/klucze/opcje sa pomijane."""
    cfg = defaults()
    if not isinstance(st, dict):
        return cfg
    mo = st.get("messages") or {}
    items = {m["id"]: m for m in cfg["messages"]}
    for mid, ov in (mo.get("items") or {}).items():
        m = items.get(mid)
        if not m or not isinstance(ov, dict):
            continue
        if "on" in ov:
            m["on"] = bool(ov["on"])
        if m["level"] != "by_severity" and ov.get("level") in LEVELS:
            m["level"] = ov["level"]
        for k, v in (ov.get("params") or {}).items():
            if k in m["params"]:
                c = _coerce(m["params"][k]["v"], v)
                if c is not None:
                    m["params"][k]["v"] = c
    order = [i for i in (mo.get("order") or []) if i in items and i != "hub"]
    order += [i for i in items if i not in order and i != "hub"]
    cfg["messages"] = [items["hub"]] + [items[i] for i in order]   # komunikat z centrali zawsze pierwszy
    for k, v in (st.get("rotation") or {}).items():
        if k in cfg["rotation"]:
            c = _coerce(cfg["rotation"][k]["v"], v)
            if c is not None and c >= 1:
                cfg["rotation"][k]["v"] = c
    cols = {f["id"]: f for f in cfg["colors"]}
    for fid, ov in (st.get("colors") or {}).items():
        f = cols.get(fid)
        if not f or not isinstance(ov, dict):
            continue
        if ov.get("v") in f["options"]:
            f["v"] = ov["v"]
        for k, v in (ov.get("params") or {}).items():
            if k in (f.get("params") or {}):
                c = _coerce(f["params"][k]["v"], v)
                if c is not None:
                    f["params"][k]["v"] = c
    return cfg


def compact(cfg):
    """Postac do zapisu / dla Karoo: same wartosci (bez opisow)."""
    return {
        "version": VERSION,
        "messages": {"order": [m["id"] for m in cfg["messages"]],
                     "items": {m["id"]: {"on": m["on"], "level": m["level"], "params": {k: p["v"] for k, p in m["params"].items()}}
                               for m in cfg["messages"]}},
        "rotation": {k: p["v"] for k, p in cfg["rotation"].items()},
        "colors": {f["id"]: {"v": f["v"], "params": {k: p["v"] for k, p in (f.get("params") or {}).items()}} for f in cfg["colors"]},
    }


def save(cur, body):
    """Zapis zmian z SETUP (body w postaci compact). Zwraca efektywna konfiguracje."""
    cfg = effective(body)
    _ensure(cur)
    cur.execute("INSERT INTO qbot_v2.app_settings (key, value, updated_at) VALUES (%s, %s::jsonb, now()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()", (KEY, json.dumps(compact(cfg))))
    return cfg


def reset(cur):
    _ensure(cur)
    cur.execute("DELETE FROM qbot_v2.app_settings WHERE key=%s", (KEY,))


def for_karoo(cur):
    """Konfiguracja dla QExt2 (etap 3): wartosci + znacznik wersji zapisu."""
    st, ts = stored(cur)
    out = compact(effective(st))
    out["updated_at"] = ts.isoformat() if ts else None
    return out


def view(cur):
    """Widok dla SETUP > QExt2: obecne reguly (domyslne + zapisane zmiany) i wartosci domyslne do porownania."""
    st, ts = stored(cur)
    return {"config": effective(st), "defaults": compact(defaults()), "levels": LEVELS, "order_note": ORDER_NOTE, "palette": PALETTE,
            "stored": bool(st), "updated_at": ts.isoformat() if ts else None,
            "editable": True, "source": "QExt2 build 292 (KOKPIT 2) – reguły odczytane z kodu"}
