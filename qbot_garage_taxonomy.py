"""Taksonomia odziezy rowerowej w Garazu (decyzja Michala 2026-09-24).

Kategorie opisuja RODZAJ rzeczy; czesc ciala (gora/dol) i dlugosc (rekawa/nogawki) sa PARAMETRAMI rzeczy
(gear.g_body, gear.g_len). Z kategorii + parametrow wynika:
  - slot w "W czym jechalem" (slot_of)          - np. Kurtki i kamizelki bez rekawow -> "Kamizelka"
  - warstwa w doradcy ubioru (LAYER_OF_SLOT)
  - Ocena rzeczy z Ankiety ocen (ocena)         - wagi per kategoria, Dopasowanie stale 30%.
Jedno zrodlo prawdy: qbot_web (Garaz, panel jazdy, pakowanie), outfit_advisor, qbot_garage_audit_api.
"""
from __future__ import annotations

TERMIKA = "Termika"
KOSZ_KOL = "Koszulki i bluzy kolarskie"
KOSZ_TECH = "Koszulki i bluzy techniczne"
KURTKI = "Kurtki i kamizelki"
DESZCZ = "Odzie\u017c deszczowa"
Z_WKL = "Spodnie i spodenki z wk\u0142adk\u0105"
BEZ_WKL = "Spodnie i spodenki bez wk\u0142adki"
WARMERS = "R\u0119kawki i nogawki"
RIDING_OTHER = ["R\u0119kawiczki", "Nakrycie g\u0142owy", "Komin i chusta", "Skarpety", "Ochraniacze na buty", "Buty",
                "Kask", "Okulary", "Akcesoria"]
RIDING_CATS = [TERMIKA, KOSZ_KOL, KOSZ_TECH, KURTKI, DESZCZ, Z_WKL, BEZ_WKL, WARMERS] + RIDING_OTHER

BODY = {"gora": "g\u00f3ra", "dol": "d\u00f3\u0142"}
LEN = {"bez": "bez r\u0119kaw\u00f3w", "krotki": "kr\u00f3tki", "34": "3/4", "dlugi": "d\u0142ugi"}
# warstwowanie gornych rzeczy (preferencja, nie zakaz) i styl (2026-09-25)
LAYERING = {"chetnie": "ch\u0119tnie", "potrzeba": "w razie potrzeby", "nie": "nie"}
STYLE = {"kolarski": "kolarski", "outdoor": "outdoorowy"}
# kategorie, w ktorych parametry maja sens (reszta: brak)
PARAM_CATS = {TERMIKA: ("body", "len"), KOSZ_KOL: ("len", "layer", "style"), KOSZ_TECH: ("len", "layer", "style"),
              KURTKI: ("len", "style"), DESZCZ: ("body", "len", "style"), Z_WKL: ("len",), BEZ_WKL: ("len",), WARMERS: ("body", "len")}
DEFAULT_BODY = {KOSZ_KOL: "gora", KOSZ_TECH: "gora", KURTKI: "gora", Z_WKL: "dol", BEZ_WKL: "dol"}

# stare nazwy kategorii -> nowe (dla zapisanych list pakowania, starych danych, importow)
OLD2NEW = {
    "Bielizna termoaktywna \u2014 g\u00f3ra": TERMIKA, "Bielizna termoaktywna \u2014 d\u00f3\u0142": TERMIKA,
    "Spodnie termiczne": TERMIKA,
    "Koszulka kr\u00f3tki r\u0119kaw": KOSZ_KOL, "Koszulka d\u0142ugi r\u0119kaw": KOSZ_KOL, "Koszulka techniczna": KOSZ_TECH,
    "Kurtka": KURTKI, "Kamizelka": KURTKI,
    "Spodenki z wk\u0142adk\u0105": Z_WKL, "Spodnie rowerowe (bez wk\u0142adki)": BEZ_WKL,
}

SLOTS = ["Termika \u2014 g\u00f3ra", "Termika \u2014 d\u00f3\u0142", "Koszulka / bluza", "Kamizelka", "Kurtka",
         "Deszczowa \u2014 g\u00f3ra", "Deszczowa \u2014 d\u00f3\u0142", "Z wk\u0142adk\u0105", "Bez wk\u0142adki",
         "R\u0119kawki", "Nogawki"] + RIDING_OTHER
LAYER_OF_SLOT = {
    "Termika \u2014 g\u00f3ra": "baza_gora", "Termika \u2014 d\u00f3\u0142": "baza_dol", "Koszulka / bluza": "koszulka",
    "Kamizelka": "kamizelka", "Kurtka": "kurtka", "Deszczowa \u2014 g\u00f3ra": "deszcz_gora",
    "Deszczowa \u2014 d\u00f3\u0142": "deszcz_dol", "Z wk\u0142adk\u0105": "spodenki", "Bez wk\u0142adki": "spodnie",
    "R\u0119kawki": "rekawki", "Nogawki": "nogawki", "R\u0119kawiczki": "rekawiczki", "Nakrycie g\u0142owy": "glowa",
    "Komin i chusta": "szyja", "Skarpety": "skarpety", "Buty": "buty", "Ochraniacze na buty": "ochraniacze",
}
# stare sloty "W czym jechalem" -> nowe (gdy nie da sie wyliczyc z rzeczy)
OLD_SLOT = {"Bielizna termoaktywna \u2014 g\u00f3ra": "Termika \u2014 g\u00f3ra",
            "Bielizna termoaktywna \u2014 d\u00f3\u0142": "Termika \u2014 d\u00f3\u0142",
            "Spodnie termiczne": "Termika \u2014 d\u00f3\u0142", "Koszulka kr\u00f3tki r\u0119kaw": "Koszulka / bluza",
            "Koszulka d\u0142ugi r\u0119kaw": "Koszulka / bluza", "Koszulka techniczna": "Koszulka / bluza",
            "Kamizelka": "Kamizelka", "Kurtka": "Kurtka", "Spodenki z wk\u0142adk\u0105": "Z wk\u0142adk\u0105",
            "Spodnie rowerowe (bez wk\u0142adki)": "Bez wk\u0142adki"}


def body_of(cat, body):
    return body or DEFAULT_BODY.get(cat)


def slot_of(cat, body=None, length=None):
    """Slot 'W czym jechalem' dla rzeczy (kategoria + parametry)."""
    b = body_of(cat, body)
    if cat == TERMIKA:
        return "Termika \u2014 d\u00f3\u0142" if b == "dol" else "Termika \u2014 g\u00f3ra"
    if cat in (KOSZ_KOL, KOSZ_TECH):
        return "Koszulka / bluza"
    if cat == KURTKI:
        return "Kamizelka" if length == "bez" else "Kurtka"
    if cat == DESZCZ:
        return "Deszczowa \u2014 d\u00f3\u0142" if b == "dol" else "Deszczowa \u2014 g\u00f3ra"
    if cat == Z_WKL:
        return "Z wk\u0142adk\u0105"
    if cat == BEZ_WKL:
        return "Bez wk\u0142adki"
    if cat == WARMERS:
        return "Nogawki" if b == "dol" else "R\u0119kawki"
    if cat in RIDING_OTHER:
        return cat
    return None


# ---------------- Ankieta ocen v2 (skala -2..+2, None = n/d) ----------------
SURVEY = [  # (kolumna, etykieta, opis -2 / 0 / +2)
    ("s_breath", "Oddychalno\u015b\u0107", "parzy, mokro / przeci\u0119tnie / \u015bwietnie wentyluje"),
    ("s_dry", "Szybkoschni\u0119cie", "d\u0142ugo mokra / przeci\u0119tnie / schnie w trakcie jazdy"),
    ("s_wind", "Wiatroszczelno\u015b\u0107", "przewiewa / cz\u0119\u015bciowo / nie przepuszcza"),
    ("s_water", "Wodoodporno\u015b\u0107", "przemaka od razu / wytrzymuje m\u017cawk\u0119 / sucho w ulewie"),
    ("s_pack", "Pakowno\u015b\u0107", "nie da si\u0119 schowa\u0107 / mie\u015bci si\u0119 w torbie / do kieszeni koszulki"),
    ("s_insul", "Izolacja", "gruba, a zimno lub wych\u0142adza / przeci\u0119tnie / grzeje \u015bwietnie jak na swoj\u0105 grubo\u015b\u0107"
                            " (n/d: rzecz nie ma grza\u0107)"),
    ("s_comfort", "Komfort", "wykonanie przeszkadza (wk\u0142adka, szwy, chwyt) / OK / nie czu\u0107 jej"),
    ("s_cond", "Stan techniczny", "zniszczona lub z wad\u0105 (np. trwa\u0142e plamy) / \u015blady u\u017cycia / jak nowa"),
    ("s_fit", "Dopasowanie", "rozmiar: nie do jazdy / niedopasowane, ale da si\u0119 je\u017adzi\u0107 / le\u017cy idealnie"),
]
SURVEY_COLS = [c for c, _, _ in SURVEY]
FIT_W = 30   # Dopasowanie: stala waga w kazdej kategorii (obowiazkowe)
COND_W = 10  # Stan techniczny: stala waga w kazdej kategorii
REST_W = 100 - FIT_W - COND_W
# wagi kryteriow kategorii (proporcje, suma 70 -> skalowane do REST_W); brak klucza = nie wchodzi do Oceny
WEIGHTS = {
    KOSZ_KOL: {"s_breath": 20, "s_dry": 15, "s_wind": 5, "s_pack": 5, "s_comfort": 15, "s_insul": 10},
    KOSZ_TECH: {"s_breath": 25, "s_dry": 15, "s_pack": 5, "s_comfort": 15, "s_insul": 10},
    TERMIKA: {"s_breath": 25, "s_dry": 15, "s_comfort": 15, "s_insul": 15},
    Z_WKL: {"s_breath": 10, "s_dry": 10, "s_comfort": 40, "s_insul": 10},
    BEZ_WKL: {"s_breath": 15, "s_dry": 10, "s_wind": 15, "s_water": 5, "s_pack": 5, "s_comfort": 10, "s_insul": 10},
    KURTKI: {"s_breath": 15, "s_dry": 5, "s_wind": 20, "s_water": 5, "s_pack": 10, "s_comfort": 5, "s_insul": 10},
    DESZCZ: {"s_breath": 15, "s_wind": 5, "s_water": 30, "s_pack": 10, "s_comfort": 5, "s_insul": 5},
    WARMERS: {"s_breath": 10, "s_dry": 10, "s_pack": 15, "s_comfort": 25, "s_insul": 10},
    "R\u0119kawiczki": {"s_breath": 10, "s_dry": 5, "s_wind": 10, "s_water": 10, "s_comfort": 25, "s_insul": 10},
    "Skarpety": {"s_breath": 15, "s_dry": 10, "s_comfort": 35, "s_insul": 10},
    "Buty": {"s_breath": 10, "s_water": 20, "s_comfort": 30, "s_insul": 10},
    "Ochraniacze na buty": {"s_wind": 15, "s_water": 30, "s_pack": 5, "s_comfort": 10, "s_insul": 10},
    "Nakrycie g\u0142owy": {"s_breath": 20, "s_dry": 15, "s_wind": 15, "s_pack": 5, "s_comfort": 5, "s_insul": 10},
    "Komin i chusta": {"s_breath": 20, "s_dry": 15, "s_wind": 15, "s_pack": 10, "s_insul": 10},
}
DEFAULT_W = {"s_breath": 20, "s_dry": 15, "s_comfort": 35}


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _weights(cat):
    """Wagi efektywne (%): Dopasowanie 30 i Stan 10 stale, reszta kategorii przeskalowana do 60."""
    w = WEIGHTS.get(cat, DEFAULT_W)
    tot = float(sum(w.values())) or 1.0
    d = {k: REST_W * v / tot for k, v in w.items()}
    d["s_fit"] = float(FIT_W)
    d["s_cond"] = float(COND_W)
    return d


def ocena(cat, vals: dict):
    """Ocena rzeczy 0..5 z ankiety (-2..+2). None = brak Dopasowania.
    Dopasowanie < 0 -> 0. Inaczej: srednia wazona odpowiedzi (n/d pominiete, ich waga rozklada sie na reszte);
    wynik 3 + srednia (0 -> 3, +2 -> 5, -2 -> 1)."""
    fit = _num(vals.get("s_fit"))
    if fit is None:
        return None
    if fit < 0:
        return 0.0
    parts = [(ww, _num(vals.get(k))) for k, ww in _weights(cat).items()]
    parts = [(ww, v) for ww, v in parts if v is not None]
    tot = sum(ww for ww, _ in parts)
    avg = sum(ww * v for ww, v in parts) / tot if tot else fit
    return round(max(1.0, min(5.0, 3.0 + avg)), 1)


def weights_for(cat):
    return {k: int(round(v)) for k, v in _weights(cat).items()}


# Pole "Stan" rzeczy (gear.condition) wynika ze Stanu technicznego z ankiety (decyzja 2026-09-25).
# "Retired" to decyzja o wycofaniu - ankieta go nie nadpisuje.
def condition_from(s_cond, current=None):
    if s_cond is None or current == "Retired":
        return None
    v = int(s_cond)
    return "New" if v >= 2 else ("Good" if v >= 0 else "Worn")
