#!/usr/bin/env python3
"""B5 — kalkulator ciśnień opon (QBot).

Model hybrydowy (decyzja zamknięta, patrz CURRENT.md / MASTER HANDOFF) — NIE zmieniać:
- opona <=42 mm  -> Berto:  P[psi] = 600*L/W^2 + 0.75*W - 25
  (L = obciążenie koła w funtach [lb], W = szerokość opony w mm)
- opona >=42 mm  -> Heine (surface-aware): baza z REALNEGO kalkulatora Rene Herse
  (siatka soft/firm wg szerokość x waga łączna, pobrana 2026-06-22), korekta wg
  nawierzchni + łagodny rozkład przód/tył.

ŹRÓDŁO OPON (TASK 1.1 — dynamiczne z garażu, NIE hardkodowane):
Narzędzie czyta WSZYSTKIE aktywne zestawy kół z garage.db
(components, category='wheels', active=1) i dla każdego ustala AKTUALNIE zamontowaną
oponę (nazwa marka+model + szerokość w mm) wg kolejności fallbacków:
  (a) components.spec — format strukturalny key=value (KONWENCJA, patrz niżej);
  (b) components.notes — sparsuj zamontowaną oponę z sekcji "zamontowane (przód i tył)",
      IGNORUJĄC sekcję części zamiennych/zapasowych (po markerze "CZĘŚCI ZAMIENNE"/"zapas");
  (c) parametr widthN_mm (N = numer zestawu wg kolejności id) — nadpisuje;
  (d) brak — wyraźnie "BRAK DANYCH — podaj szerokość".

KONWENCJA ZAPISU AKTUALNEJ OPONY (jeden wpis aktualizuje kalkulator):
  components.spec = "tire=<marka model>; width_mm=<zmierzona szerokość w mm>"
  np.  tire=Schwalbe Thunder Burt 2.1; width_mm=54
  - width_mm = szerokość ZMIERZONA na danej obręczy (preferowana nad nominalną).
  - Gdy spec puste, czytane jest z notes (oponę montowaną wpisuj jako
    "Opony: <marka model> <rozmiar> (przód i tył)"; zapasowe po linii "--- CZĘŚCI ZAMIENNE").
PRZELICZANIE SZEROKOŚCI NA mm (gdy brak width_mm w spec):
  - ETRTO "700x45" / "...x45mm"  -> 45 mm (liczba po 'x');
  - jawne "NN mm"                -> NN mm;
  - cale "2.1\""/"2.1"           -> round(2.1 * 25.4) mm = ~53 mm (NOMINALNE, mniej pewne —
    zaleca się wpisać zmierzoną szerokość do components.spec width_mm).

Pozostałe wejścia:
- waga zawodnika: qbot_v2.body_measurements (najnowszy weight_kg) lub param weight_kg
- masa roweru: garage.db bikes.weight_kg (NULL -> 10.0 kg domyślnie, oznaczone) lub bike_weight_kg
- nawierzchnia: param surface (asfalt/szuter_gladki/szuter_luzny/techniczny); brak -> wszystkie
- rozkład masy: 40/60 (przód/tył)
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

_APP_ROOT = Path("/opt/qbot/app")
_GARAGE_DB = str(_APP_ROOT / "data" / "garage.db")
_PSI_PER_BAR = 14.5038
_DEFAULT_BIKE_KG = 10.0
_INCH_MM = 25.4

# ── REALNA siatka Rene Herse (soft_bar, firm_bar) -> {width_mm: {weight_kg: (soft, firm)}}
# Pobrana 2026-06-22 (Claude in Chrome) z kalkulatora Rene Herse. Waga = rider+bike łącznie. NIE zmieniać.
_RH_GRID = {
    42: {100: (2.6, 3.3), 110: (2.9, 3.5), 113: (2.9, 3.6), 120: (3.1, 3.8)},
    45: {90: (2.2, 2.8), 100: (2.5, 3.1), 110: (2.7, 3.3), 113: (2.8, 3.4), 120: (2.9, 3.6), 130: (3.1, 3.9)},
    48: {100: (2.3, 2.9), 110: (2.5, 3.1), 113: (2.6, 3.2), 120: (2.7, 3.4)},
    50: {90: (2.0, 2.5), 100: (2.2, 2.7), 110: (2.4, 3.0), 113: (2.5, 3.0), 120: (2.6, 3.2), 130: (2.8, 3.5)},
    52: {100: (2.1, 2.6), 110: (2.3, 2.8), 113: (2.4, 2.9), 120: (2.5, 3.1)},
    54: {90: (1.9, 2.3), 100: (2.0, 2.5), 110: (2.2, 2.7), 113: (2.3, 2.8), 120: (2.4, 2.9), 130: (2.6, 3.1)},
    55: {100: (2.0, 2.5), 110: (2.2, 2.7), 113: (2.2, 2.7), 120: (2.3, 2.9)},
}

# Korekta wg nawierzchni: mnożnik na RH-soft dla koła TYLNEGO (skalibrowane do walidacji 54 mm). NIE zmieniać.
_SURFACE = [
    ("asfalt", 1.00, "asfalt / gładki bruk"),
    ("szuter_gladki", 0.95, "gładki szuter / hardpack"),
    ("szuter_luzny", 0.87, "luźny szuter / żwir"),
    ("techniczny", 0.83, "techniczny / kamienisty / błoto"),
]
_FRONT_FACTOR = 0.90  # przód lżejszy (40/60); łagodna korekta — RH odradza mocno niższy przód


# ── Połączenia z bazą (robust, wzorzec jak tools/rwgps/route_brief.py _db_connect) ──
def _load_env_local() -> None:
    p = _APP_ROOT / ".env.local"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


def _pg_conn():
    """Połączenie do appowego PostgreSQL (qbot_v2/public). Ładuje .env.local jak route_brief."""
    _load_env_local()
    try:
        import psycopg
        from psycopg.rows import dict_row
        kwargs = dict(host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                      dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                      row_factory=dict_row, connect_timeout=5)
        pw = os.getenv("PGPASSWORD")
        if pw:
            kwargs["password"] = pw
        return psycopg.connect(**kwargs)
    except Exception:
        return None


def _garage_conn():
    return sqlite3.connect(_GARAGE_DB)


# ── Model liczenia (NIE zmieniać) ──
def _interp(d: dict, x: float):
    ks = sorted(d.keys())
    if x <= ks[0]:
        return d[ks[0]]
    if x >= ks[-1]:
        return d[ks[-1]]
    lo = max(k for k in ks if k <= x)
    hi = min(k for k in ks if k >= x)
    if lo == hi:
        return d[lo]
    t = (x - lo) / (hi - lo)
    a, b = d[lo], d[hi]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _rh_lookup(width_mm: float, weight_kg: float):
    ws = sorted(_RH_GRID.keys())
    w = min(max(width_mm, ws[0]), ws[-1])
    lo = max(x for x in ws if x <= w)
    hi = min(x for x in ws if x >= w)
    s_lo, f_lo = _interp(_RH_GRID[lo], weight_kg)
    if hi == lo:
        return s_lo, f_lo
    s_hi, f_hi = _interp(_RH_GRID[hi], weight_kg)
    t = (w - lo) / (hi - lo)
    return (s_lo + (s_hi - s_lo) * t, f_lo + (f_hi - f_lo) * t)


def _psi(bar: float) -> int:
    return round(bar * _PSI_PER_BAR)


def _berto_psi(load_kg: float, width_mm: float) -> float:
    L = load_kg * 2.20462
    return 600.0 * L / (width_mm ** 2) + 0.75 * width_mm - 25.0


# ── Odczyt wagi ──
def _athlete_weight():
    conn = _pg_conn()
    if conn is None:
        return None, None
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT weight_kg, date FROM qbot_v2.body_measurements "
                "WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1")
            r = cur.fetchone()
            if r:
                return float(r["weight_kg"]), str(r["date"])
    except Exception:
        pass
    return None, None


def _bike_weight():
    try:
        c = _garage_conn()
        row = c.execute("SELECT weight_kg FROM bikes WHERE active=1 ORDER BY id LIMIT 1").fetchone()
        c.close()
        if row and row[0] is not None:
            return float(row[0]), False
    except Exception:
        pass
    return _DEFAULT_BIKE_KG, True


# ── Parsowanie opony / szerokości ──
_ETRTO_RE = re.compile(r"(?:700|650|29|27\.5|28|26)\s*[x×]\s*(\d{2})\s*c?\s*mm?", re.I)
_MM_RE = re.compile(r"(\d{2}(?:\.\d)?)\s*mm", re.I)
_INCH_RE = re.compile(r"(\d\.\d{1,2})")
_SPARE_MARKERS = ("części zamienne", "czesci zamienne", "zapas", "zamienne")


def _width_from_text(t: str):
    """Zwraca (width_mm, źródło) z fragmentu opisującego oponę. Kolejność: ETRTO -> mm -> cale(nom)."""
    if not t:
        return None, None
    m = _ETRTO_RE.search(t)
    if m:
        return float(m.group(1)), "ETRTO"
    m = _MM_RE.search(t)
    if m:
        return float(m.group(1)), "mm"
    m = _INCH_RE.search(t)
    if m:
        val = float(m.group(1))
        if 1.3 <= val <= 3.2:  # zakres rozsądnych cali opon
            return round(val * _INCH_MM), "cal(nom)"
    return None, None


def _clean_tire_name(name: str) -> str:
    name = re.sub(r"\s*(?:700|650|29|27\.5|28|26)\s*[x×]\s*\d{2}\s*c?\s*mm?\b", "", name, flags=re.I)
    name = re.sub(r"\s*\d{2}(?:\.\d)?\s*mm\b", "", name, flags=re.I)
    return name.strip(" .,-")


def _parse_spec(spec: str):
    """KONWENCJA: 'tire=...; width_mm=NN'. Zwraca (tire_name|None, width_mm|None)."""
    if not spec or not spec.strip():
        return None, None
    d = {}
    for part in spec.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.strip().lower()] = v.strip()
    name = d.get("tire") or d.get("opona")
    wmm = None
    if d.get("width_mm"):
        try:
            wmm = float(re.findall(r"[\d.]+", d["width_mm"])[0])
        except Exception:
            wmm = None
    if not d:  # spec nie w formacie key=value — spróbuj wyłuskać szerokość wprost
        wmm, _ = _width_from_text(spec)
    return name, wmm


def _parse_width_mm(spec: str, notes: str, param):
    """Zwraca (front_mm|None, rear_mm|None) z param/spec/notes."""
    if param is not None:
        try:
            w = float(re.findall(r"[\d.]+", str(param))[0])
            return w, w
        except Exception:
            return None, None

    d = {}
    if spec and spec.strip():
        for part in spec.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                d[k.strip().lower()] = v.strip()

        def _num(key: str):
            val = d.get(key)
            if not val:
                return None
            m = re.search(r"[\d.]+", val)
            return float(m.group(0)) if m else None

        front = _num("width_front_mm")
        rear = _num("width_rear_mm")
        if front is not None and rear is not None:
            return front, rear

        w = _num("width_mm")
        if w is not None:
            return w, w

        if not d:
            w, _ = _width_from_text(spec)
            if w is not None:
                return w, w

    _, width, _ = _parse_notes_tire(notes)
    if width is not None:
        return width, width
    return None, None


def _mounted_section(notes: str) -> str:
    """Zwraca fragment notes opisujący ZAMONTOWANE opony (ucina przy markerze zapasów)."""
    if not notes:
        return ""
    low = notes.lower()
    cut = len(notes)
    for marker in _SPARE_MARKERS:
        i = low.find(marker)
        if i != -1:
            cut = min(cut, i)
    return notes[:cut]


def _parse_notes_tire(notes: str):
    """Z sekcji zamontowanej wyłuskuje (tire_name|None, width_mm|None, źródło|None)."""
    sec = _mounted_section(notes)
    if not sec:
        return None, None, None
    m = re.search(r"opon\w*\s*:?\s*([^(\n]+)", sec, re.I)
    if not m:
        return None, None, None
    raw = re.split(r"\.\s", m.group(1), 1)[0].strip()
    width, wsrc = _width_from_text(raw)
    return _clean_tire_name(raw) or raw.strip(), width, wsrc


def _read_wheelsets(overrides: dict[int, float]) -> list[dict]:
    """Wszystkie aktywne zestawy kół z garażu + ustalona aktualna opona per zestaw."""
    rows = []
    try:
        c = _garage_conn()
        rows = c.execute(
            "SELECT id, brand, model, spec, notes, weight_g FROM components "
            "WHERE category='wheels' AND active=1 ORDER BY id").fetchall()
        c.close()
    except Exception:
        rows = []
    sets = []
    for idx, (cid, brand, model, spec, notes, weight_g) in enumerate(rows, start=1):
        name_spec, _ = _parse_spec(spec)
        tire_name, width, wsrc = None, None, None
        front_mm, rear_mm = _parse_width_mm(spec, notes, None)
        if front_mm is not None and rear_mm is not None:
            width = (front_mm, rear_mm)
            wsrc = "spec" if spec and "width_" in spec.lower() else "notes"
        ov = overrides.get(idx)
        if ov is not None:
            width = (float(ov), float(ov))
            wsrc = f"parametr width{idx}_mm"
        if not tire_name and name_spec:
            tire_name = name_spec
        label = f"{brand} {model}".strip() if brand else (model or f"Zestaw #{idx}")
        wheelset_kg = float(weight_g) / 1000.0 if weight_g is not None else None
        sets.append({
            "idx": idx,
            "label": label,
            "tire": tire_name,
            "width": width,
            "wsrc": wsrc,
            "wheelset_kg": wheelset_kg,
        })
    return sets


def _wheelset_block(ws: dict, rider_kg, bike_kg, extra_kg, front_frac, rear_frac, surface):
    out = [f"### {ws['label']}"]
    tire = ws.get("tire") or "nieznana"
    width = ws.get("width")
    if not width or width[0] is None or width[1] is None:
        out.append(f"Opona: {tire} — **BRAK DANYCH o szerokości**. "
                   f"Podaj parametr width{ws['idx']}_mm albo uzupełnij components.spec "
                   f"(np. 'tire={tire}; width_mm=NN').")
        return "\n".join(out)
    front_mm, rear_mm = width
    if front_mm == rear_mm:
        out.append(f"Opona (z garażu): {tire} · {front_mm:.0f}mm (źródło: {ws.get('wsrc') or '?'}).")
    else:
        out.append(f"Opona (z garażu): {tire} · {front_mm:.0f}/{rear_mm:.0f} mm (przód/tył, źródło: {ws.get('wsrc') or '?'}).")
    if ws.get("wsrc", "").startswith("notes/cal"):
        out.append("_(szerokość z cali = nominalna; dla precyzji wpisz zmierzoną do components.spec width_mm)_")

    bike_kg = bike_kg + float(ws.get("wheelset_kg") or 0.0)
    combined_kg = rider_kg + bike_kg + extra_kg

    def _base_bar(side_width: float, load_kg: float):
        if side_width <= 42:
            return _berto_psi(load_kg, side_width) / _PSI_PER_BAR, "Berto"
        soft, firm = _rh_lookup(side_width, combined_kg)
        return soft, "Heine"

    rear_base, rear_model = _base_bar(rear_mm, combined_kg * rear_frac)
    front_base, front_model = _base_bar(front_mm, combined_kg * front_frac)

    if front_mm == rear_mm and rear_model == "Heine":
        out.append(f"Model: Heine (surface-aware, baza Rene Herse @ {combined_kg:.0f} kg łącznie). Punkt startowy.")
        soft, firm = _rh_lookup(rear_mm, combined_kg)
        out.append(f"Referencja RH (cały rower, jedna wartość): soft {soft:.1f} bar / firm {firm:.1f} bar.")
    elif rear_model == "Heine" or front_model == "Heine":
        out.append(f"Model: Heine (surface-aware, baza Rene Herse @ {combined_kg:.0f} kg łącznie). Punkt startowy.")
        rear_soft, rear_firm = _rh_lookup(rear_mm, combined_kg)
        front_soft, front_firm = _rh_lookup(front_mm, combined_kg)
        out.append(f"Referencja RH tył: soft {rear_soft:.1f} bar / firm {rear_firm:.1f} bar.")
        out.append(f"Referencja RH przód: soft {front_soft:.1f} bar / firm {front_firm:.1f} bar.")
    else:
        out.append("Model: Berto (opona ≤42 mm). Punkt startowy:")

    buckets = _SURFACE
    if surface:
        buckets = [b for b in _SURFACE if b[0] == surface] or _SURFACE
    for key, mult, desc in buckets:
        rear = rear_base * mult if rear_model == "Heine" else rear_base
        front = front_base * mult * _FRONT_FACTOR if front_model == "Heine" else front_base
        out.append(f"- {desc}: przód {front:.1f} bar ({_psi(front)} psi) · tył {rear:.1f} bar ({_psi(rear)} psi)")
    return "\n".join(out)


def _tool_qbot_tire_pressure(args: dict | None = None) -> dict[str, Any]:
    a = args or {}
    weight = a.get("weight_kg")
    wsrc, wdate = "parametr", None
    if weight is None:
        weight, wdate = _athlete_weight()
        wsrc = "qbot_v2.body_measurements"
    if weight is None:
        return {"status": "DATA_MISSING",
                "error": "Brak wagi zawodnika (body_measurements puste i brak parametru weight_kg)."}
    weight = float(weight)

    bike = a.get("bike_weight_kg")
    bike_default = False
    if bike is None:
        bike, bike_default = _bike_weight()
    bike = float(bike)
    extra = float(a.get("extra_load_kg", 0) or 0)
    combined = weight + bike + extra

    dist = a.get("weight_distribution") or [40, 60]
    front_frac, rear_frac = dist[0] / 100.0, dist[1] / 100.0

    overrides = {}
    if a.get("width1_mm") is not None:
        overrides[1] = a.get("width1_mm")
    if a.get("width2_mm") is not None:
        overrides[2] = a.get("width2_mm")
    surface = a.get("surface")

    wheelsets = _read_wheelsets(overrides)
    if not wheelsets:
        return {"status": "DATA_MISSING",
                "error": "Brak aktywnych zestawów kół w garage.db (components category='wheels' active=1)."}

    head = [
        "## Ciśnienie opon — punkt startowy (B5)",
        f"Waga zawodnika: {weight:.2f} kg ({wsrc}{', ' + wdate if wdate else ''}).",
        f"Masa roweru: {bike:.1f} kg ({'DOMYŚLNA — bikes.weight_kg puste, do przeważenia' if bike_default else 'garage.db'})."
        + (f" + ładunek {extra:.1f} kg." if extra else ""),
        f"Masa roweru: {bike:.1f} kg. Rozkład przód/tył: {dist[0]}/{dist[1]}. Masa łączna z kołami widoczna per zestaw.",
        f"Zestawy kół z garażu: {len(wheelsets)}.",
        "",
    ]
    blocks = [_wheelset_block(ws, weight, bike, extra, front_frac, rear_frac, surface) for ws in wheelsets]

    notes = (
        "Wartości to PUNKT STARTOWY — dostroić do odczucia i terenu. "
        "Opony i szerokości czytane DYNAMICZNIE z garażu (components: spec → notes → parametr widthN_mm → BRAK). "
        "Aby zaktualizować oponę jednym wpisem: components.spec = 'tire=<marka model>; width_mm=<zmierzona mm>'. "
        "Baza Heine = realny kalkulator Rene Herse (2026-06-22); korekta nawierzchni i przód/tył skalibrowana terenowo (54 mm). "
        "Masa roweru domyślna 10 kg gdy brak w garażu."
    )
    analysis = "\n".join(head) + "\n\n".join(blocks) + "\n\n_" + notes + "_"
    return {"status": "OK", "analysis": analysis, "notes": notes}
