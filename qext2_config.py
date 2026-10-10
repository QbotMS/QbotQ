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


def view(cur):
    """Widok dla SETUP > QExt2: obecne reguly (domyslne + ewentualne nadpisania)."""
    cfg = defaults()
    st, ts = stored(cur)
    return {"config": cfg, "levels": LEVELS, "order_note": ORDER_NOTE,
            "stored": bool(st), "updated_at": ts.isoformat() if ts else None,
            "editable": False, "source": "QExt2 build 292 (KOKPIT 2) – reguły odczytane z kodu"}
