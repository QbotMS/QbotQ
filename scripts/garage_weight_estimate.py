"""garage_weight_estimate.py - estymator wagi rzeczy w Garazu.

PO CO: do oszacowania masy bagazu wyprawowego nie potrzeba wagi co do grama,
ale potrzeba JAKIEJS liczby dla kazdej rzeczy. Wagi zwazone (weight_g) sa
nienaruszalne - estymaty ida do osobnej kolumny weight_est_g.

JAK: dwa etapy.
  1. TABELA BAZOWA - typowa masa dla kategorii (rozmiar M/L), korygowana
     mnoznikami za material (merino ciezsze) i sezon (zimowe ciezsze).
     Jawna, audytowalna, dziala bez sieci i bez LLM.
  2. DOPRECYZOWANIE LLM - model czyta nazwe i opis (np. "ultralight",
     "Polartec Alpha", "3L rain shell") i koryguje. Wynik jest PRZYCINANY
     do widelek wokol bazy, zeby zadna halucynacja nie weszla do danych.

Uruchomienie:
    python3 scripts/garage_weight_estimate.py [limit] [--no-llm]
Skrypt jest wznawialny - liczy tylko rzeczy bez weight_g i bez weight_est_g.
"""
import json
import re
import sqlite3
import sys

# skrypt bywa uruchamiany z katalogu scripts/ - modulu qgpt_client szukamy w app/
sys.path.insert(0, "/opt/qbot/app")

DB = "/opt/qbot/app/data/garage.db"

# --- tabela bazowa: typowa masa w gramach dla rozmiaru M/L ---
BAZA_GEAR = {
    "Base Layer Top": 130, "Base Layer Bottom": 130,
    "Jersey": 145, "T-Shirt": 130, "Jersey Long Sleeve": 200,
    "Bottoms / Bibs": 210, "Mid Layer Bottom": 220,
    "Vest / Gilet": 120, "Jacket / Shell": 300,
    "Warmers": 95, "Gloves": 65, "Headwear": 40, "Neckwear": 35,
    "Socks": 60, "Overshoes": 130, "Shoes": 800, "Helmet": 320,
    "Glasses": 30, "Accessories": 120,
}
BAZA_EQUIP = {
    "Torby bikepackingowe": 350, "Bagazniki i mocowania": 500,
    "Elektronika": 200, "Nawigacja i swiatla": 130,
    "Narzedzia i serwis": 250, "Kuchnia": 300, "Spanie": 800,
    "Higiena": 120, "Apteczka": 200, "Dokumenty": 80, "Inne": 200,
}
BAZA_COMP = {
    "frame": 1100, "fork": 600, "headset": 100, "stem": 130, "handlebar": 280,
    "aero bars": 500, "seatpost": 250, "saddle": 260, "wheels": 1600,
    "tires": 500, "cassette": 350, "chain": 260, "crankset": 650,
    "drivetrain": 400, "brakes": 400, "pedals": 320, "bottom bracket": 90,
    "electronics": 150, "rack": 500, "mudguards": 300, "bottle cages": 40,
    "spare parts": 200, "other": 200,
}

MNOZ_MATERIAL = {"merino": 1.25, "merino blend": 1.15, "techniczna": 1.0, "inna": 1.0}
MNOZ_SEZON = {"zima": 1.30, "lato": 0.85}          # tylko gdy jeden sezon
MNOZ_ROZMIAR = {"XS": 0.85, "S": 0.92, "M": 1.0, "L": 1.08, "XL": 1.16, "XXL": 1.24}

WIDELKI = (0.45, 2.5)     # dozwolony przedzial korekty LLM wzgledem bazy


def _baza(tabela, kategoria):
    if tabela == "gear":
        return BAZA_GEAR.get(kategoria, 150)
    if tabela == "equipment":
        return BAZA_EQUIP.get(kategoria, 200)
    return BAZA_COMP.get(kategoria, 250)


def szacuj_tabelarycznie(tabela, row):
    """Etap 1: baza kategorii + mnozniki. Zwraca (gramy, opis_podstawy)."""
    kat = row["category"] or ""
    w = float(_baza(tabela, kat))
    opis = ["baza %s=%dg" % (kat or "?", w)]

    if tabela == "gear":
        fab = (row["fabric"] or "").lower()
        if fab in MNOZ_MATERIAL and MNOZ_MATERIAL[fab] != 1.0:
            w *= MNOZ_MATERIAL[fab]
            opis.append("%s x%.2f" % (fab, MNOZ_MATERIAL[fab]))
        sez = [s for s in (row["season"] or "").split(",") if s]
        if len(sez) == 1 and sez[0] in MNOZ_SEZON:
            w *= MNOZ_SEZON[sez[0]]
            opis.append("%s x%.2f" % (sez[0], MNOZ_SEZON[sez[0]]))
        rozm = (row["size"] or "").strip().upper()
        if rozm in MNOZ_ROZMIAR and MNOZ_ROZMIAR[rozm] != 1.0:
            w *= MNOZ_ROZMIAR[rozm]
            opis.append("rozm. %s x%.2f" % (rozm, MNOZ_ROZMIAR[rozm]))
    return int(round(w)), " | ".join(opis)


_SYS = (
    "Szacujesz mase sprzetu i odziezy rowerowej w GRAMACH. Dostajesz liste rzeczy, "
    "a przy kazdej wartosc bazowa wyliczona z kategorii. Twoim zadaniem jest ja SKORYGOWAC "
    "na podstawie nazwy i opisu: slowa typu ultralight/cienka/mesh obnizaja mase, "
    "a Polartec Alpha, Primaloft, puch, 3L membrana, zimowy, ocieplany - podwyzszaja. "
    "Jesli nazwa nic nie wnosi, zwroc wartosc bazowa. "
    "FORMAT: obiekt JSON, gdzie KLUCZEM jest NUMER id (jako tekst), a wartoscia liczba gramow. "
    "Przyklad dla pozycji 12 i 34: {\"12\": 165, \"34\": 320}. "
    "Nie uzywaj slowa 'id' jako klucza. Zwroc WYLACZNIE ten JSON, bez markdown. "
    "Podaj wpis dla KAZDEGO id z listy."
)


def dopracuj_llm(pozycje, conn):
    """Etap 2: korekta LLM, przycinana do widelek wokol bazy."""
    from qgpt_client import qgpt_text
    linie = []
    for p in pozycje:
        linie.append("id=%s | %s | %s %s | baza=%dg | opis: %s" % (
            p["id"], p["category"] or "?", p["brand"] or "", p["model"] or "",
            p["baza"], (p["notes"] or "")[:130].replace("\n", " ")))
    raw = qgpt_text("Skoryguj mase tych rzeczy:\n\n" + "\n".join(linie),
                    system=_SYS, max_tokens=900, temperature=0)
    raw = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except Exception:
        return {}
    dozwolone = {p["id"]: p for p in pozycje}
    wynik = {}
    for k, v in d.items():
        try:
            gid = int(str(k).strip())
        except ValueError:
            continue
        p = dozwolone.get(gid)
        if not p:
            continue                       # tylko id z tej partii
        try:
            g = int(round(float(str(v).replace(",", "."))))
        except (TypeError, ValueError):
            continue
        lo = int(p["baza"] * WIDELKI[0])
        hi = int(p["baza"] * WIDELKI[1])
        przyciety = max(lo, min(hi, g))    # halucynacja nie przejdzie
        wynik[gid] = (przyciety, przyciety != g)
    return wynik


def przelicz(tabela, limit=200, uzyj_llm=True):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    kolumny = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % tabela)]
    pola = ["id", "category", "brand", "model", "notes"]
    for extra in ("fabric", "season", "size"):
        if extra in kolumny:
            pola.append(extra)
    sel = ", ".join(pola)
    rows = conn.execute(
        "SELECT %s FROM %s WHERE active=1 AND weight_g IS NULL AND weight_est_g IS NULL "
        "ORDER BY id LIMIT ?" % (sel, tabela), (limit,)).fetchall()
    if not rows:
        conn.close()
        return {"tabela": tabela, "do_zrobienia": 0}

    pozycje = []
    for r in rows:
        d = {k: (r[k] if k in r.keys() else None) for k in
             ("id", "category", "brand", "model", "notes", "fabric", "season", "size")}
        g, opis = szacuj_tabelarycznie(tabela, d)
        d["baza"], d["opis"] = g, opis
        pozycje.append(d)

    korekty = {}
    if uzyj_llm:
        for i in range(0, len(pozycje), 20):
            try:
                korekty.update(dopracuj_llm(pozycje[i:i + 20], conn))
            except Exception as e:
                print("  LLM partia %d: %s" % (i // 20 + 1, str(e)[:90]))

    n_tab = n_llm = n_przyc = 0
    for p in pozycje:
        if p["id"] in korekty:
            g, przyciety = korekty[p["id"]]
            src = "llm"
            note = p["opis"] + (" | LLM %dg" % g) + (" (przyciete do widelek)" if przyciety else "")
            n_llm += 1
            n_przyc += 1 if przyciety else 0
        else:
            g, src, note = p["baza"], "tabela", p["opis"]
            n_tab += 1
        conn.execute("UPDATE %s SET weight_est_g=?, weight_est_src=?, weight_est_note=? "
                     "WHERE id=? AND weight_g IS NULL" % tabela, (g, src, note, p["id"]))
    conn.commit()

    suma = conn.execute(
        "SELECT sum(COALESCE(weight_g, weight_est_g)) FROM %s WHERE active=1" % tabela).fetchone()[0]
    brak = conn.execute(
        "SELECT count(*) FROM %s WHERE active=1 AND weight_g IS NULL AND weight_est_g IS NULL"
        % tabela).fetchone()[0]
    conn.close()
    return {"tabela": tabela, "policzone": len(pozycje), "z_tabeli": n_tab, "z_llm": n_llm,
            "przyciete": n_przyc, "bez_wagi_po": brak, "suma_g_calej_tabeli": suma}


if __name__ == "__main__":
    limit = 200
    uzyj_llm = "--no-llm" not in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            limit = int(a)
    for t in ("gear", "equipment", "components"):
        print(json.dumps(przelicz(t, limit, uzyj_llm), ensure_ascii=False))
