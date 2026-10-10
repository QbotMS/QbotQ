"""Faworyci ubioru na dzien jazdy (Analiza trasy -> Sprzet) + dobor z faworytami.

Decyzje Michala 2026-10-10:
- faworyci = rzeczy z Garazu, ktore Michal SAM chce wlozyc na jazde; przypisani do trasy + daty planu
  (Analiza trasy: ubior jest na dzien, w ktory planowana jest trasa); tabela qbot_v2.route_outfit_fav,
- gdy sa faworyci: zestaw A "Z Twoimi faworytami" (zawiera WSZYSTKIE faworyty, na sobie albo w kieszeni,
  AI dobiera reszte), zestaw B "Propozycja AI" liczony OSOBNO - AI nie widzi faworytow; tempo B = tempo A,
- AI probuje zrozumiec, czemu takie faworyty na ten dzien ("zrozumienie") i ostrzega, gdy faworyt slabo pasuje
  do warunkow (faworyt zostaje w zestawie),
- bez faworytow: dotychczasowy dobor (outfit_advisor.advise: zestaw spokojniejszy + szybszy).
Silnik (warunki, kandydaci, historia, kontrole, autokorekta) = qbot3/routes/outfit_advisor.py - bez zmian.
Dok.: docs/OUTFIT_FAVORITES.md
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import re
import time

from qbot3.routes import outfit_advisor as OA

TEMPA = ("spokojniejsza", "szybsza")


# ---------------- zapis faworytow ----------------
def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.route_outfit_fav (route_id text NOT NULL, ride_date date NOT NULL, "
                 "gear_ids jsonb NOT NULL DEFAULT '[]'::jsonb, updated_at timestamptz NOT NULL DEFAULT now(), "
                 "PRIMARY KEY (route_id, ride_date))")


def get_ids(conn, route_id, day) -> list:
    ensure(conn)
    r = conn.execute("SELECT gear_ids FROM qbot_v2.route_outfit_fav WHERE route_id=%s AND ride_date=%s",
                     (str(route_id), day)).fetchone()
    conn.commit()
    if not r:
        return []
    v = r["gear_ids"] if isinstance(r, dict) else r[0]
    v = json.loads(v) if isinstance(v, str) else (v or [])
    return [int(x) for x in v]


def set_ids(conn, route_id, day, ids) -> list:
    ensure(conn)
    clean = []
    for x in ids or []:
        try:
            i = int(x)
        except Exception:
            continue
        if i not in clean:
            clean.append(i)
    clean = clean[:12]
    conn.execute("INSERT INTO qbot_v2.route_outfit_fav (route_id, ride_date, gear_ids, updated_at) VALUES (%s,%s,%s::jsonb,now()) "
                 "ON CONFLICT (route_id, ride_date) DO UPDATE SET gear_ids=EXCLUDED.gear_ids, updated_at=now()",
                 (str(route_id), day, json.dumps(clean)))
    conn.commit()
    return clean


# ---------------- lista rzeczy do okna Faworyci ----------------
def _item_base(r):
    return {"id": int(r["id"]), "kategoria": r["category"], "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(),
            "kolor": r["color_q"] or r["color"]}


def gear_list() -> list:
    """Aktywne rzeczy z Garazu, ktore maja warstwe ubioru (bez plecakow itp.). 'nie_do_jazdy' = audyt/ankieta wyklucza."""
    out = []
    for r in OA._gear_rows():
        k = OA._layer(r)
        if not k:
            continue
        it = _item_base(r)
        it["warstwa"] = k
        if int(r["a_out"] or 0) or (r["s_fit"] is not None and int(r["s_fit"]) < 0):
            it["nie_do_jazdy"] = True
        out.append(it)
    out.sort(key=lambda x: (x["kategoria"] or "", x["nazwa"].lower(), str(x["kolor"] or "")))
    return out


def _cand_item(r, k):
    """Kandydat dla faworyta, ktorego silnik nie wybral (poza zakresem / za nisko w rankingu) - wymuszony."""
    it = _item_base(r)
    it.update({"warstwa": k, "marka": (r["brand"] or "").strip(), "ostatnio_proponowane": False, "_score": 99.0})
    rng = None
    if r["a_temp_min"] is not None and r["a_temp_max"] is not None:
        rng = (int(r["a_temp_min"]), int(r["a_temp_max"]))
    else:
        rng, _ = OA._range(r["season"], r["r_insul"], r["notes"] or "")
    it["zakres_c"] = list(rng) if rng else [-20, 40]
    it["zakres_z"] = "faworyt"
    if r["g_len"]:
        it["dlugosc"] = r["g_len"]
    if r["g_layer"]:
        it["warstwowanie"] = {"chetnie": "chetnie", "potrzeba": "w razie potrzeby (niepreferowane)", "nie": "nie - tylko sama"}.get(r["g_layer"])
    oc = {lab: r[col] for col, lab in OA._SLAB if r[col] is not None}
    if oc:
        it["ankieta"] = oc
    if r["a_status"]:
        it["audyt"] = {"status": r["a_status"]}
    return it


def _with_favs(kand, fav_ids):
    """Kopia kandydatow z dolozonymi faworytami (oznaczonymi 'faworyt': True)."""
    k2 = copy.deepcopy(kand)
    have = {it["id"]: it for v in k2.values() for it in v}
    rows = {int(r["id"]): r for r in OA._gear_rows()}
    for i in fav_ids:
        if i in have:
            have[i]["faworyt"] = True
            continue
        r = rows.get(i)
        k = OA._layer(r) if r is not None else None
        if not k:
            continue
        it = _cand_item(r, k)
        it["faworyt"] = True
        k2.setdefault(k, []).insert(0, it)
    return k2


# ---------------- walidacja jednego zestawu ----------------
def _ids_of(z, key):
    out = set()
    for it in z.get(key) or []:
        try:
            out.add(int(it.get("id")))
        except Exception:
            pass
    return out


def _valid_one(z, kand, war, tempo=None):
    """Jak outfit_advisor._valid, ale dla JEDNEGO zestawu."""
    if not isinstance(z, dict):
        return "brak zestawu"
    ids = {it["id"]: it for v in kand.values() for it in v}
    if (z.get("tempo") or "") not in TEMPA:
        return "tempo musi byc 'spokojniejsza' albo 'szybsza'"
    if tempo and z.get("tempo") != tempo:
        return "tempo zestawu musi byc '%s'" % tempo
    need = [k for k in ("buty", "skarpety", "rekawiczki") if kand.get(k)]
    dry = (OA._f((war.get("deszcz") or {}).get("max_proc"), 0.0) < 10) and not war.get("dlugie_postoje")
    on, pk = _ids_of(z, "rzeczy"), _ids_of(z, "do_kieszeni")
    if on & pk:
        return "ta sama rzecz na sobie i w kieszeni (id %s) - wybierz jedno" % ", ".join(str(i) for i in sorted(on & pk))
    miss = [k for k in need if k not in {ids[i]["warstwa"] for i in on if i in ids}]
    if miss:
        return "brak w zestawie: %s" % ", ".join(miss)
    if dry and len(pk) > 1 and not any(ids.get(i, {}).get("faworyt") for i in pk):
        return "sucha prognoza bez dlugich postojow: najwyzej 1 rzecz do kieszeni"
    if not (z.get("po_co") or "").strip():
        return "brak 'po_co' w zestawie"
    its = z.get("rzeczy") or []
    if len(its) < 4:
        return "za malo rzeczy w zestawie"
    seen = set()
    for it in its + (z.get("do_kieszeni") or []):
        try:
            i = int(it.get("id"))
        except Exception:
            return "zle id"
        if i not in ids:
            return "rzecz spoza kandydatow: %s" % i
        if it in its:
            lw = ids[i]["warstwa"]
            if lw in seen:
                return "dwie rzeczy w jednej warstwie (%s)" % lw
            seen.add(lw)
        if not (it.get("dlaczego") or "").strip():
            return "brak uzasadnienia"
    if ("spodnie" in seen or "deszcz_dol" in seen) and "spodenki" not in seen:
        return "spodnie bez wkladki bez warstwy z wkladka (liner/bibsy)"
    return None


def _missing_favs(z, fav_ids):
    have = _ids_of(z, "rzeczy") | _ids_of(z, "do_kieszeni")
    return [i for i in fav_ids if i not in have]


# ---------------- prompty ----------------
_SET_JSON = ('{"tempo": "%s", "nazwa": "krotka nazwa", "kiedy": "1 zdanie: kiedy ten zestaw",'
             ' "po_co": "%s",'
             ' "rzeczy": [{"id": liczba, "dlaczego": "1 zdanie z liczba", "zamienniki": [id, id] (opcjonalnie, 0-2, ta sama warstwa)}],'
             ' "do_kieszeni": [{"id": liczba, "dlaczego": "1 zdanie"}], "zdejmij": "co i kiedy zdjac / zalozyc (albo pusty)",'
             ' "kolory": "1 zdanie: jak zestaw uklada sie kolorystycznie",'
             ' "slaby_punkt": "1 zdanie: slaby punkt zestawu i co z nim zrobic"}')


def _base(war, kand, hist, rules):
    p = OA._prompt(war, kand, hist, rules)
    cut = p.find("\n\nZwroc JSON:")
    if cut < 0:
        raise RuntimeError("outfit_advisor._prompt: brak znacznika 'Zwroc JSON:'")
    return p[:cut]


def _prompt_fav(war, kand, hist, rules, favs):
    fv = [{"id": c["id"], "nazwa": c["nazwa"], "kategoria": c["kategoria"], "warstwa": c["warstwa"], "kolor": c.get("kolor"),
           "zestaw_uzywany_przy": OA._zakres_txt(c["zakres_c"])} for c in favs]
    return (_base(war, kand, hist, rules)
            + "\n\nfaworyci (rzeczy, ktore SAM wybrales na ten dzien - KAZDY musi byc w zestawie, na sobie albo w kieszeni; "
              "dwa faworyty z tej samej warstwy: jeden na sobie, drugi do kieszeni; reszte zestawu dobierz tak, by z nimi grala): "
            + json.dumps(fv, ensure_ascii=False)
            + '\n\nZwroc JSON: {"warunki_krotko": "1-2 zdania o przebiegu warunkow w czasie jazdy",'
              ' "z_historii": "1 zdanie: co z Twoich jazd wplynelo na dobor (albo pusty)",'
              ' "zrozumienie": "1-2 zdania na TY: jak rozumiesz, czemu wybrales te faworyty na ten dzien (np. nowa rzecz do'
              ' sprawdzenia, kolor/komplet, chcesz cieplej albo luzniej niz wynika z prognozy, ulubiona rzecz na taka trase);'
              ' ostroznie (\'pewnie chcesz...\'), z odniesieniem do warunkow i historii jazd",'
              ' "faworyci_uwagi": ["1 zdanie na faworyta, ktory slabo pasuje do warunkow: co grozi i jak to obejsc"] (pusta lista gdy pasuja),'
              ' "zestaw": ' + _SET_JSON % ("spokojniejsza albo szybsza - to, do ktorego faworyci pasuja lepiej",
                                         "1 zdanie: jak reszta zestawu gra z faworytami") + "}")


def _prompt_ai(war, kand, hist, rules, tempo):
    return (_base(war, kand, hist, rules)
            + "\n\nZwroc JSON: {\"zestaw\": " + _SET_JSON % (tempo, "1 zdanie: dlaczego te rzeczy przy tym tempie") + "}"
            + " - JEDEN zestaw na jazde w tempie '%s'." % tempo)


# ---------------- jeden zestaw: AI + kontrole + autokorekta ----------------
def _retag(msgs, tag):
    """Kontrole silnika oznaczaja jedyny zestaw jako 'A' - przepisz na wlasciwa litere."""
    if tag == "A":
        return list(msgs)
    return [s.replace("zestaw A:", "zestaw %s:" % tag).replace("automatycznie: A:", "automatycznie: %s:" % tag) for s in msgs]


def _one(conn, war, kand, hist, rules, system, prompt, tempo=None, favs=None):
    from qgpt_client import qgpt_json
    favs = favs or []
    z, err, fix, top = None, None, "", {}
    for attempt in range(2):
        try:
            top = qgpt_json(prompt + fix, system=system, max_tokens=3500, temperature=0.5)
        except Exception as e:  # noqa
            top = {}
            err = "wyjatek: " + str(e)[:120]
        z = (top or {}).get("zestaw") if isinstance(top, dict) else None
        o = {"zestawy": [z] if isinstance(z, dict) else []}
        OA._dedupe(o, war)
        err = _valid_one(z, kand, war, tempo)
        if not err and favs:
            mf = _missing_favs(z, favs)
            if mf:
                err = "brak faworytow w zestawie (id %s) - kazdy faworyt musi byc na sobie albo w kieszeni" % ", ".join(map(str, mf))
        if not err and attempt < 1:
            err = OA._style(o)
        if not err and attempt < 1:
            ch = OA._checks(o, kand, war)
            if ch:
                err = "; ".join(ch) + (" (FAWORYTOW nie usuwaj ani nie zamieniaj)" if favs else "")
        if not err:
            break
        fix = "\n\nPOPRZEDNIA ODPOWIEDZ ODRZUCONA: " + err + ". Popraw i zwroc caly JSON."
    if err:
        return None, top, err
    o = {"zestawy": [z]}
    before = copy.deepcopy(o)
    fx = OA._autofix(o, kand, war) + OA._pocket_trim(o, kand, war)
    if fx and (_missing_favs(o["zestawy"][0], favs) or _valid_one(o["zestawy"][0], kand, war, tempo)):
        o, fx = before, []          # autokorekta nie moze wyrzucic faworyta ani zepsuc zestawu
    uw = ["poprawione automatycznie: " + f for f in fx] + OA._checks(o, kand, war, final=True)
    if fx:
        note = OA._retext(o, kand, fx)
        if note:
            uw.append(note)
    z = o["zestawy"][0]
    z["_uwagi"] = uw
    return z, top, None


def _finish(z, kand, favs):
    ids = {it["id"]: it for v in kand.values() for it in v}
    for key in ("rzeczy", "do_kieszeni"):
        for it in z.get(key) or []:
            c = ids[int(it["id"])]
            it.update({"id": c["id"], "nazwa": c["nazwa"], "kategoria": c["kategoria"], "warstwa": c["warstwa"], "kolor": c["kolor"]})
            if c["id"] in favs:
                it["faworyt"] = True
            zm = []
            for j in (it.get("zamienniki") if isinstance(it.get("zamienniki"), list) else [])[:2]:
                try:
                    cj = ids.get(int(j))
                except Exception:
                    cj = None
                if cj and cj["warstwa"] == c["warstwa"] and cj["id"] != c["id"]:
                    zm.append({"id": cj["id"], "nazwa": cj["nazwa"], "kolor": cj["kolor"]})
            it["zamienniki"] = zm
    z["rzeczy"].sort(key=lambda x: OA.LAYER_KEYS.index(x["warstwa"]))
    z["kolory"] = OA._kolory(z["rzeczy"])
    return z


# ---------------- dobor z faworytami ----------------
def advise_fav(conn, data: dict, start: str, rules=None, model_name: str = "", long_stops: int = 0, long_stop_min: int = 0,
               route_id: str | None = None, ride_date: str | None = None, fav_ids=None) -> dict:
    t0 = time.perf_counter()
    fav_ids = [int(x) for x in fav_ids or []]
    war = OA.warunki(data, start, long_stops, long_stop_min)
    hist = OA.historia_jazd(conn)
    sim = OA._similar_ok(hist, war)
    if sim:
        war["podobna_jazda_ok"] = {k: v for k, v in sim.items() if not k.startswith("_")}
    kand = OA.kandydaci(war, OA.recent_ids(conn, skip=(route_id, ride_date)), liked=OA._liked(hist),
                        strong=sim["_ids"] if sim else None)
    kand_a = _with_favs(kand, fav_ids)
    by = {it["id"]: it for v in kand_a.values() for it in v}
    favs = [by[i] for i in fav_ids if i in by]
    if not favs:
        return {"ok": False, "blad": "faworyci nie sa ubiorem z Garazu (brak warstwy)"}
    fav_ok = [c["id"] for c in favs]
    system = OA._rules_text() + OA.SYS_FORMAT
    # A: z faworytami (AI wybiera tempo)
    za, top, err = _one(conn, war, kand_a, hist, rules, system, _prompt_fav(war, kand_a, hist, rules, favs), favs=fav_ok)
    if err:
        return {"ok": False, "blad": "zestaw z faworytami: " + err, "warunki": war}
    tempo = za.get("tempo")
    # B: AI bez faworytow (nie widzi ich), to samo tempo
    zb, _, err = _one(conn, war, kand, hist, rules, system, _prompt_ai(war, kand, hist, rules, tempo), tempo=tempo)
    if err:
        return {"ok": False, "blad": "propozycja AI: " + err, "warunki": war}
    uw = _retag(za.pop("_uwagi", []), "A") + _retag(zb.pop("_uwagi", []), "B")
    _finish(za, kand_a, fav_ok)
    _finish(zb, kand, set())
    za["rola"], zb["rola"] = "faworyci", "ai"
    fu = top.get("faworyci_uwagi") if isinstance(top, dict) else None
    return {"ok": True, "wersja": OA.VERSION, "tryb": "faworyci", "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "warunki": war, "warunki_krotko": top.get("warunki_krotko"), "z_historii": top.get("z_historii"),
            "zrozumienie": (top.get("zrozumienie") or "").strip(),
            "faworyci_uwagi": [s for s in (fu if isinstance(fu, list) else []) if isinstance(s, str) and s.strip()],
            "faworyci": [{"id": c["id"], "nazwa": c["nazwa"], "kolor": c.get("kolor"), "kategoria": c["kategoria"]} for c in favs],
            "zestawy": [za, zb], "kandydatow": sum(len(v) for v in kand_a.values()), "jazd_w_historii": len(hist),
            "kontrola_uwagi": uw}
