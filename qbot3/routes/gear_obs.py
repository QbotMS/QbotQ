"""GEAR-OBS: obserwacje przy rzeczach z Garazu, zarzadzane przez AI (decyzja 2026-10-18, docs/DECISIONS.md, docs/GEAR_OBS.md).

Uwaga Michala - po jezdzie ('W czym jechalem', slot _uwagi w ride_gear_log) albo przed jazda ('Uwagi do AI' w Analizie trasy) -
AI rozbiera na OBSERWACJE przy konkretnych rzeczach: co sie stalo, aspekt, inne mozliwe przyczyny, waga. Gdy nie da sie ocenic,
AI zadaje JEDNO pytanie (odpowiedz -> ponowny rozbior). Na kazda rzecz z obserwacjami AI utrzymuje 'co wiemy' (z pewnoscia),
ktore czyta doradca ubioru (outfit_advisor.kandydaci -> pole co_wiemy). Audyt (gear.a_*) = baza i NIE jest zmieniany
automatycznie: AI moze tylko ZAPROPONOWAC zmiane (min. 2 zgodne obserwacje tego samego aspektu, nie wszystkie slabe);
zatwierdza Michal (etap 2: Garaz, etap 3: Telegram + Centrum powiadomien).

Tabele (garage.db): gear_obs_note (uwaga + kontekst + pytanie/odpowiedz + status), gear_obs (obserwacje), gear_knowledge.
Statusy uwagi: przetwarzanie -> gotowa | pytanie | bez_obserwacji | bez_rzeczy | blad.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import sys
import threading
import time

GARAGE_DB = "/opt/qbot/app/data/garage.db"
SRC_PO = "po_jezdzie"
SRC_PRZED = "przed_jazda"
WAGI = ("slaba", "srednia", "mocna")
ASPEKTY = ("woda", "cieplo", "zimno", "wiatr", "pot", "komfort", "dopasowanie", "trwalosc", "inne")
WYNIKI = ("negatywny", "pozytywny", "neutralny")
# pole audytu -> klucz slownika w qbot_garage_audit_api.OPTIONS (jedno zrodlo prawdy wartosci)
PROP_FIELDS = {"a_rain": "rain", "a_wind": "wind", "a_fit": "fit", "a_status": "st",
               "a_temp_min": None, "a_temp_max": None, "a_wet_cold": None}
PROP_MIN_OBS = 2

DDL = """
CREATE TABLE IF NOT EXISTS gear_obs_note (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, ref TEXT NOT NULL, ride_date TEXT,
  text TEXT NOT NULL, context_json TEXT, question TEXT, answer TEXT,
  status TEXT NOT NULL DEFAULT 'przetwarzanie', error TEXT,
  created_at TEXT DEFAULT (datetime('now')), processed_at TEXT);
CREATE INDEX IF NOT EXISTS gear_obs_note_ref ON gear_obs_note(source, ref);
CREATE TABLE IF NOT EXISTS gear_obs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, note_id INTEGER NOT NULL, gear_id INTEGER NOT NULL, obs_date TEXT,
  aspekt TEXT, wynik TEXT, opis TEXT, inne_przyczyny TEXT, waga TEXT,
  created_at TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS gear_obs_gear ON gear_obs(gear_id);
CREATE INDEX IF NOT EXISTS gear_obs_note_i ON gear_obs(note_id);
CREATE TABLE IF NOT EXISTS gear_knowledge (
  gear_id INTEGER PRIMARY KEY, co_wiemy TEXT, pewnosc TEXT, n_obs INTEGER,
  proposal_json TEXT, proposal_status TEXT, updated_at TEXT DEFAULT (datetime('now')));
"""


# ---------------- polaczenia ----------------
def _g():
    g = sqlite3.connect(GARAGE_DB, timeout=15)
    g.row_factory = sqlite3.Row
    g.executescript(DDL)
    return g


def _pg():
    if "/opt/qbot/app" not in sys.path:
        sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    return _db_connect()


def _pg_one(sql, params):
    """Jeden wiersz z Postgresa jako dict (albo None). Nigdy nie rzuca."""
    try:
        conn = _pg()
    except Exception:
        return None
    try:
        from psycopg.rows import dict_row
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _llm(prompt, max_tokens=1500):
    if "/opt/qbot/app" not in sys.path:
        sys.path.insert(0, "/opt/qbot/app")
    from qgpt_client import qgpt_json
    return qgpt_json(prompt, system="Analityk sprzetu rowerowego QBota. Tylko JSON.", max_tokens=max_tokens, temperature=0.2)


def _name(r):
    return ("%s %s" % (r["brand"] or "", r["model"] or "")).strip()


def _trim(x, n=1500):
    s = json.dumps(x, ensure_ascii=False, default=str)
    return json.loads(s) if len(s) <= n else s[:n]


# ---------------- kontekst uwagi ----------------
def ride_context(ride_key) -> dict:
    """Komplet z 'W czym jechalem' + meta + pogoda/jazda z raportu (w1). Pogoda bywa bledna (np. opad 0 mm mimo deszczu)."""
    g = _g()
    try:
        rows = g.execute("SELECT l.slot, l.gear_id, l.value, g.brand, g.model, g.category FROM ride_gear_log l "
                         "LEFT JOIN gear g ON g.id=l.gear_id WHERE l.ride_key=?", (ride_key,)).fetchall()
    finally:
        g.close()
    rzeczy, meta = [], {}
    for r in rows:
        if r["slot"].startswith("_"):
            meta[r["slot"][1:]] = r["value"]
        elif r["gear_id"] is not None:
            rzeczy.append({"id": int(r["gear_id"]), "nazwa": _name(r), "kategoria": r["category"], "slot": r["slot"]})
    w1 = _pg_one("SELECT w1_json->'weather' AS we, w1_json->'ride' AS rd, w1_json->'load' AS ld FROM qbot_v2.ride_report_data "
                 "WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (ride_key,)) or {}
    rd, ld = w1.get("rd") or {}, w1.get("ld") or {}
    ctx = {"kiedy": "po jezdzie", "data": rd.get("date"), "start": rd.get("time"), "dystans_km": rd.get("dist_km"),
           "czas_ruchu": ld.get("dur_moving_s"), "typ_jazdy": meta.get("typ"), "odczucie": meta.get("odczucie"),
           "rower": meta.get("rower"), "rzeczy": rzeczy,
           "pogoda_z_raportu": _trim(w1.get("we") or {}, 1800),
           "temp_odczuwalna_zapis": meta.get("temp_app"), "opad_zapis_mm": meta.get("precip"),
           "uwaga_o_danych": "pogoda z prognozy/modelu bywa bledna - przy sprzecznosci z uwaga Michala wierz Michalowi"}
    return {k: v for k, v in ctx.items() if v not in (None, "", [], {})}


def route_context(route_id, ride_date) -> dict:
    """Ostatnia propozycja ubioru dla planu (Analiza trasy) - rzeczy z zestawow + warunki prognozy."""
    r = _pg_one("SELECT proposal FROM qbot_v2.route_outfit WHERE route_id=%s AND ride_date=%s ORDER BY created_at DESC LIMIT 1",
                (route_id, ride_date)) or {}
    p = r.get("proposal") or {}
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = {}
    seen, rzeczy = set(), []
    for z in p.get("zestawy") or []:
        for it in (z.get("rzeczy") or []) + (z.get("do_kieszeni") or []):
            try:
                i = int(it.get("id"))
            except Exception:
                continue
            if i not in seen:
                seen.add(i)
                rzeczy.append({"id": i, "nazwa": it.get("nazwa"), "warstwa": it.get("warstwa")})
    return {"kiedy": "przed jazda (uwaga do propozycji ubioru)", "data": str(ride_date), "trasa": route_id,
            "rzeczy": rzeczy, "warunki_prognoza": _trim(p.get("warunki") or {}, 1500)}


# ---------------- rozbior uwagi ----------------
def _prompt_extract(note, ctx, no_question):
    return (
        "Michal zapisal uwage o ubiorze/sprzecie (%s). Rozbierz ja na OBSERWACJE przy konkretnych rzeczach z Garazu.\n"
        "Zasady:\n"
        "- Obserwacja = cos, co sie WYDARZYLO z konkretna rzecza (przemokla, za cieplo, wiatr przewiewal, uwiera, ciasno, sucho mimo deszczu).\n"
        "  Preferencje i polecenia (\"do zielonej czapki dawaj zielone rekawiczki\", \"na taka pogode tylko dlugie spodnie\") to NIE obserwacje"
        " - pomin je (obsluguje je inny mechanizm). Pozytywne obserwacje tez sie licza.\n"
        "- gear_id WYLACZNIE z listy kontekst.rzeczy. Gdy uwaga mowi o grupie (\"wszystko przeciekło\") - obserwacja dla kazdej rzeczy, ktorej"
        " to realnie dotyczy (np. warstwy zewnetrzne, buty, rekawiczki), z nizsza waga niz wprost nazwana rzecz.\n"
        "- inne_przyczyny: co poza sama rzecza moglo to spowodowac (sila/czas deszczu, sposob noszenia, inne warstwy, tempo) - konkretnie,"
        " krotko; null gdy brak.\n"
        "- waga: 'slaba' (niejasne, prawdopodobne inne wyjasnienie, skrajne warunki), 'srednia', 'mocna' (jasne, wprost o rzeczy).\n"
        "- Dane pogody moga sie mylic (np. opad 0 mm mimo deszczu) - przy sprzecznosci wierz Michalowi.\n"
        "%s"
        "- Piszesz po polsku Z POLSKIMI ZNAKAMI, rzeczowo.\n\n"
        "uwaga: %s\n%s"
        "kontekst: %s\n\n"
        'Zwroc TYLKO JSON: {"obserwacje": [{"gear_id": int, "aspekt": "%s", "wynik": "%s", "opis": "1 zdanie co sie stalo",'
        ' "inne_przyczyny": "..." lub null, "waga": "%s"}], "pytanie": "..." lub null}'
        % (ctx.get("kiedy", ""),
           "- pytanie: NIE zadawaj pytan (null).\n" if no_question else
           "- pytanie: JEDNO krotkie pytanie tylko gdy bez odpowiedzi nie da sie sensownie przypisac lub ocenic obserwacji"
           " (np. ktorej rzeczy dotyczy, ktoredy weszla woda); inaczej null. Zadajac pytanie i tak zapisz obserwacje,"
           " ktore juz da sie zapisac.\n",
           json.dumps(note["text"], ensure_ascii=False),
           ("pytanie_bylo: %s\nodpowiedz_Michala: %s\n" % (json.dumps(note["question"], ensure_ascii=False),
                                                         json.dumps(note["answer"], ensure_ascii=False))) if note["answer"] else "",
           json.dumps(ctx, ensure_ascii=False, default=str),
           "|".join(ASPEKTY), "|".join(WYNIKI), "|".join(WAGI)))


def process_note(note_id, no_question=False) -> dict:
    g = _g()
    try:
        n = g.execute("SELECT * FROM gear_obs_note WHERE id=?", (note_id,)).fetchone()
        if not n:
            return {"ok": False, "blad": "brak uwagi"}
        ctx = json.loads(n["context_json"] or "{}")
        old = [r["gear_id"] for r in g.execute("SELECT DISTINCT gear_id FROM gear_obs WHERE note_id=?", (note_id,))]
        allowed = {int(x["id"]) for x in ctx.get("rzeczy") or []}
        if not allowed:
            g.execute("DELETE FROM gear_obs WHERE note_id=?", (note_id,))
            g.execute("UPDATE gear_obs_note SET status='bez_rzeczy', question=NULL, processed_at=? WHERE id=?", (_now(), note_id))
            g.commit()
            touched = set(old)
        else:
            try:
                o = _llm(_prompt_extract(n, ctx, no_question or bool(n["answer"])))
            except Exception as e:  # noqa
                g.execute("UPDATE gear_obs_note SET status='blad', error=?, processed_at=? WHERE id=?", (str(e)[:300], _now(), note_id))
                g.commit()
                return {"ok": False, "blad": str(e)[:200]}
            obs = (o or {}).get("obserwacje") if isinstance(o, dict) else None
            q = (o or {}).get("pytanie") if isinstance(o, dict) else None
            q = q.strip()[:300] if isinstance(q, str) and q.strip() and not no_question and not n["answer"] else None
            g.execute("DELETE FROM gear_obs WHERE note_id=?", (note_id,))
            added = set()
            for x in obs if isinstance(obs, list) else []:
                try:
                    gid = int(x.get("gear_id"))
                except Exception:
                    continue
                if gid not in allowed:
                    continue
                g.execute("INSERT INTO gear_obs (note_id, gear_id, obs_date, aspekt, wynik, opis, inne_przyczyny, waga) VALUES (?,?,?,?,?,?,?,?)",
                          (note_id, gid, n["ride_date"], x.get("aspekt") if x.get("aspekt") in ASPEKTY else "inne",
                           x.get("wynik") if x.get("wynik") in WYNIKI else "neutralny", str(x.get("opis") or "")[:300],
                           (str(x.get("inne_przyczyny"))[:300] if x.get("inne_przyczyny") else None),
                           x.get("waga") if x.get("waga") in WAGI else "slaba"))
                added.add(gid)
            st = "pytanie" if q else ("gotowa" if added else "bez_obserwacji")
            g.execute("UPDATE gear_obs_note SET status=?, question=?, error=NULL, processed_at=? WHERE id=?", (st, q, _now(), note_id))
            g.commit()
            touched = set(old) | added
    finally:
        g.close()
    for gid in sorted(touched):
        try:
            refresh_knowledge(gid)
        except Exception as e:  # noqa
            print("gear_obs knowledge %s: %s" % (gid, e))
    _KNOW_CACHE["t"] = 0.0
    return {"ok": True, "note_id": note_id, "gear": sorted(touched)}


def _bg(note_id, no_question=False):
    t = threading.Thread(target=lambda: process_note(note_id, no_question), daemon=True, name="gear_obs_%s" % note_id)
    t.start()


def _new_note(g, source, ref, ride_date, text, ctx):
    cur = g.execute("INSERT INTO gear_obs_note (source, ref, ride_date, text, context_json, status) VALUES (?,?,?,?,?, 'przetwarzanie')",
                    (source, ref, ride_date, text, json.dumps(ctx, ensure_ascii=False, default=str)))
    return cur.lastrowid


def submit_ride_note(ride_key, background=True, no_question=False) -> dict:
    """Po zapisie 'W czym jechalem'. Ta sama tresc -> bez zmian; inna -> nowy rozbior; pusta -> obserwacje znikaja."""
    g = _g()
    try:
        r = g.execute("SELECT value FROM ride_gear_log WHERE ride_key=? AND slot='_uwagi'", (ride_key,)).fetchone()
        text = (r["value"] if r else "") or ""
        text = text.strip()[:1000]
        prev = g.execute("SELECT * FROM gear_obs_note WHERE source=? AND ref=? ORDER BY id DESC LIMIT 1", (SRC_PO, ride_key)).fetchone()
        if prev and prev["text"] == text and prev["status"] not in ("blad",):
            return {"ok": True, "note_id": prev["id"], "status": prev["status"], "question": prev["question"], "zmiana": False}
        touched = []
        if prev:
            touched = [x["gear_id"] for x in g.execute("SELECT DISTINCT gear_id FROM gear_obs WHERE note_id IN "
                                                       "(SELECT id FROM gear_obs_note WHERE source=? AND ref=?)", (SRC_PO, ride_key))]
            g.execute("DELETE FROM gear_obs WHERE note_id IN (SELECT id FROM gear_obs_note WHERE source=? AND ref=?)", (SRC_PO, ride_key))
            g.execute("DELETE FROM gear_obs_note WHERE source=? AND ref=?", (SRC_PO, ride_key))
        if not text:
            g.commit()
            for gid in touched:
                refresh_knowledge(gid)
            return {"ok": True, "note_id": None, "status": "brak_uwagi"}
        ctx = ride_context(ride_key)
        nid = _new_note(g, SRC_PO, ride_key, ctx.get("data"), text, ctx)
        g.commit()
    finally:
        g.close()
    if background:
        _bg(nid, no_question)
        return {"ok": True, "note_id": nid, "status": "przetwarzanie", "zmiana": True}
    return process_note(nid, no_question)


def submit_route_note(route_id, ride_date, text, background=True) -> dict:
    """Po 'Uwagach do AI' w Analizie trasy (obok poprawki zestawu i wniosku na przyszlosc)."""
    text = (text or "").strip()[:1000]
    if not text:
        return {"ok": True, "note_id": None, "status": "brak_uwagi"}
    ctx = route_context(route_id, ride_date)
    g = _g()
    try:
        nid = _new_note(g, SRC_PRZED, "%s|%s" % (route_id, ride_date), str(ride_date), text, ctx)
        g.commit()
    finally:
        g.close()
    if background:
        _bg(nid)
        return {"ok": True, "note_id": nid, "status": "przetwarzanie"}
    return process_note(nid)


def answer_note(note_id, answer, background=True) -> dict:
    a = (answer or "").strip()[:600]
    if not a:
        return {"ok": False, "blad": "pusta odpowiedz"}
    g = _g()
    try:
        if not g.execute("SELECT 1 FROM gear_obs_note WHERE id=?", (note_id,)).fetchone():
            return {"ok": False, "blad": "brak uwagi"}
        g.execute("UPDATE gear_obs_note SET answer=?, status='przetwarzanie' WHERE id=?", (a, note_id))
        g.commit()
    finally:
        g.close()
    if background:
        _bg(note_id)
        return {"ok": True, "note_id": note_id, "status": "przetwarzanie"}
    return process_note(note_id)


def note_status(note_id) -> dict:
    g = _g()
    try:
        n = g.execute("SELECT id, source, ref, status, question, answer, error, processed_at FROM gear_obs_note WHERE id=?", (note_id,)).fetchone()
        if not n:
            return {"ok": False, "blad": "brak uwagi"}
        obs = [dict(r) for r in g.execute("SELECT o.gear_id, o.aspekt, o.wynik, o.opis, o.inne_przyczyny, o.waga, g.brand, g.model "
                                          "FROM gear_obs o LEFT JOIN gear g ON g.id=o.gear_id WHERE o.note_id=?", (note_id,))]
        return {"ok": True, **dict(n), "obserwacje": obs}
    finally:
        g.close()


# ---------------- co wiemy ----------------
def _audit_view(r):
    keys = ("a_status", "a_fit", "a_use", "a_temp_min", "a_temp_max", "a_rain", "a_wind", "a_wet_cold", "a_role", "a_note", "a_src", "a_date")
    return {k: r[k] for k in keys if k in r.keys() and r[k] not in (None, "")}


def _allowed_values():
    try:
        if "/opt/qbot/app" not in sys.path:
            sys.path.insert(0, "/opt/qbot/app")
        from qbot_garage_audit_api import OPTIONS
    except Exception:
        OPTIONS = {}
    out = {}
    for f, k in PROP_FIELDS.items():
        if k:
            out[f] = list(OPTIONS.get(k) or [])
        elif f == "a_wet_cold":
            out[f] = [0, 1]
        else:
            out[f] = "liczba calkowita -20..40"
    return out


def _valid_prop(p, obs, allowed):
    if not isinstance(p, dict):
        return None
    f, v = p.get("pole"), p.get("na")
    if f not in PROP_FIELDS:
        return None
    al = allowed.get(f)
    if isinstance(al, list):
        if f == "a_wet_cold":
            v = 1 if v in (1, "1", True, "true") else 0
        if v not in al:
            return None
    else:
        try:
            v = max(-20, min(40, int(round(float(v)))))
        except Exception:
            return None
    asp = p.get("aspekt")
    same = [o for o in obs if (asp is None or o["aspekt"] == asp)]
    if len(same) < PROP_MIN_OBS or all(o["waga"] == "slaba" for o in same):
        return None
    return {"pole": f, "na": v, "aspekt": asp, "dlaczego": str(p.get("dlaczego") or "")[:400], "n_obs": len(same)}


def refresh_knowledge(gear_id) -> dict:
    g = _g()
    try:
        r = g.execute("SELECT * FROM gear WHERE id=?", (gear_id,)).fetchone()
        obs = [dict(x) for x in g.execute("SELECT o.*, n.source, n.text AS uwaga FROM gear_obs o JOIN gear_obs_note n ON n.id=o.note_id "
                                          "WHERE o.gear_id=? ORDER BY COALESCE(o.obs_date, o.created_at) DESC LIMIT 30", (gear_id,))]
        prev = g.execute("SELECT * FROM gear_knowledge WHERE gear_id=?", (gear_id,)).fetchone()
        if not r or not obs:
            g.execute("DELETE FROM gear_knowledge WHERE gear_id=?", (gear_id,))
            g.commit()
            return {"ok": True, "gear_id": gear_id, "co_wiemy": None}
        allowed = _allowed_values()
        item = {"id": gear_id, "nazwa": _name(r), "kategoria": r["category"], "audyt": _audit_view(r)}
        ob = [{"data": o["obs_date"], "zrodlo": o["source"], "aspekt": o["aspekt"], "wynik": o["wynik"], "opis": o["opis"],
               "inne_przyczyny": o["inne_przyczyny"], "waga": o["waga"], "uwaga_Michala": o["uwaga"]} for o in obs]
        prompt = (
            "Rzecz z Garazu Michala i jego obserwacje z jazd (od najnowszej). Napisz 'co wiemy' dla doradcy ubioru.\n"
            "Zasady:\n"
            "- co_wiemy: 1-2 zdania, praktycznie dla doboru (kiedy uwazac, z czym laczyc), z zastrzezeniami. Pojedyncza albo niejasna"
            " obserwacja to POSZLAKA - nie przekreslaj oceny z audytu, nie uogolniaj.\n"
            "- pewnosc: niska (1 obserwacja / niejasne / inne wyjasnienia) | srednia | wysoka (powtarzalny wzorzec).\n"
            "- propozycja zmiany audytu: TYLKO gdy co najmniej %d obserwacje tego samego aspektu w tym samym kierunku, bez lepszego innego"
            " wyjasnienia, i sprzeczne z audytem; inaczej null. Dozwolone pola i wartosci: %s.\n"
            "- Piszesz po polsku Z POLSKIMI ZNAKAMI.\n\n"
            "rzecz: %s\nobserwacje: %s\n\n"
            'Zwroc TYLKO JSON: {"co_wiemy": "...", "pewnosc": "niska|srednia|wysoka", "propozycja": null lub'
            ' {"pole": "...", "na": ..., "aspekt": "%s", "dlaczego": "1-2 zdania"}}'
            % (PROP_MIN_OBS, json.dumps(allowed, ensure_ascii=False), json.dumps(item, ensure_ascii=False, default=str),
               json.dumps(ob, ensure_ascii=False, default=str), "|".join(ASPEKTY)))
        o = _llm(prompt, max_tokens=800)
        if not isinstance(o, dict) or not str(o.get("co_wiemy") or "").strip():
            return {"ok": False, "blad": "zla odpowiedz AI"}
        cw = str(o["co_wiemy"]).strip()[:500]
        pw = o.get("pewnosc") if o.get("pewnosc") in ("niska", "srednia", "wysoka") else "niska"
        prop = _valid_prop(o.get("propozycja"), obs, allowed)
        pj, ps = (prev["proposal_json"], prev["proposal_status"]) if prev else (None, None)
        _new_prop = _withdrawn = False
        if prop:
            same = False
            try:
                old = json.loads(pj) if pj else None
                same = bool(old) and old.get("pole") == prop["pole"] and old.get("na") == prop["na"]
            except Exception:
                pass
            if same and ps in ("odrzucona", "zatwierdzona") and int(prev["n_obs"] or 0) >= len(obs):
                pass   # ta sama propozycja juz rozstrzygnieta i brak nowych obserwacji - nie wracamy z nia
            elif not (same and ps == "czeka"):
                pj, ps = json.dumps(prop, ensure_ascii=False), "czeka"
                _new_prop = True
        elif ps == "czeka":
            pj, ps = None, None   # wzorzec juz nie trzyma - wycofaj oczekujaca propozycje
            _withdrawn = True
        g.execute("INSERT INTO gear_knowledge (gear_id, co_wiemy, pewnosc, n_obs, proposal_json, proposal_status, updated_at) "
                  "VALUES (?,?,?,?,?,?,?) ON CONFLICT(gear_id) DO UPDATE SET co_wiemy=excluded.co_wiemy, pewnosc=excluded.pewnosc, "
                  "n_obs=excluded.n_obs, proposal_json=excluded.proposal_json, proposal_status=excluded.proposal_status, updated_at=excluded.updated_at",
                  (gear_id, cw, pw, len(obs), pj, ps, _now()))
        g.commit()
        if _new_prop:   # etap 3: Telegram + Centrum powiadomien
            _notify_prop(gear_id, _name(r), prop, r[prop["pole"]] if prop["pole"] in r.keys() else None)
        elif _withdrawn:
            _resolve_prop(gear_id)
        return {"ok": True, "gear_id": gear_id, "co_wiemy": cw, "pewnosc": pw, "propozycja": pj, "status": ps}
    finally:
        g.close()


_KNOW_CACHE = {"t": 0.0, "d": {}}


def knowledge_map() -> dict:
    """{gear_id: 'co wiemy (pewnosc ..., N obs.)'} dla doradcy ubioru. Cache 60 s."""
    if time.time() - _KNOW_CACHE["t"] < 60:
        return _KNOW_CACHE["d"]
    d = {}
    try:
        g = _g()
        try:
            for r in g.execute("SELECT gear_id, co_wiemy, pewnosc, n_obs FROM gear_knowledge WHERE co_wiemy IS NOT NULL"):
                d[int(r["gear_id"])] = "%s (pewnosc %s, obserwacji: %s)" % (r["co_wiemy"], r["pewnosc"] or "niska", r["n_obs"] or 0)
        finally:
            g.close()
    except Exception:
        d = {}
    _KNOW_CACHE.update(t=time.time(), d=d)
    return d


def backfill(since="2026-09-01") -> dict:
    """Jednorazowo: istniejace _uwagi z 'W czym jechalem' (bez pytan - to stare jazdy)."""
    g = _g()
    try:
        keys = [r["ride_key"] for r in g.execute("SELECT ride_key FROM ride_gear_log WHERE slot='_uwagi' AND COALESCE(value,'')<>'' "
                                                  "AND updated_at >= ? ORDER BY updated_at", (since,))]
    finally:
        g.close()
    out = []
    for k in keys:
        try:
            out.append((k, submit_ride_note(k, background=False, no_question=True)))
        except Exception as e:  # noqa
            out.append((k, {"ok": False, "blad": str(e)[:200]}))
    return {"n": len(keys), "wyniki": out}



# ---------------- strony (etap 2) ----------------
PROP_LABEL = {"a_rain": "Najmocniejszy sprawdzony deszcz", "a_wind": "Ochrona od wiatru", "a_fit": "Fit", "a_status": "Status",
              "a_temp_min": "Temperatura zestawu od (°C)", "a_temp_max": "Temperatura zestawu do (°C)", "a_wet_cold": "Mokra wychładza"}
VAL_TXT = {
    "a_rain": {"brak_oczekiwan": "Nie oczekuję ochrony", "nietestowany": "Nietestowana w deszczu", "mzawka_przemaka": "Mżawka — przemaka",
               "mzawka_sucho": "Mżawka — sucho", "umiarkowany_przemaka_po_czasie": "Umiarkowany — przemaka po czasie",
               "umiarkowany_sucho": "Umiarkowany — sucho", "ulewa_sucho": "Ulewa — sucho"},
    "a_wind": {"mocna": "Mocna", "umiarkowana": "Umiarkowana", "czesciowa": "Częściowa", "mala": "Mała"},
    "a_fit": {"OK": "OK", "LEKKO_CIASNA": "Lekko ciasna", "ZA_LUZNA": "Za luźna", "BLOKUJE": "Za ciasna — blokuje"},
    "a_status": {"CORE": "Rdzeń", "ROTATION": "Rotacja", "SPECIAL": "Potrzebny specjalista", "BACKUP": "Zapas",
                 "RETIRE_CANDIDATE": "Kandydat do wycofania", "FIT_BLOCKED": "Fit blokuje (za ciasna)", "OFF_BIKE": "Głównie poza rowerem",
                 "NEW": "Nowa / nietestowana"},
    "a_wet_cold": {0: "nie", 1: "tak", "0": "nie", "1": "tak"},
}


def _vtxt(f, v):
    if v is None or v == "":
        return None
    return VAL_TXT.get(f, {}).get(v, str(v))


def gear_view(gear_id) -> dict:
    g = _g()
    try:
        r = g.execute("SELECT * FROM gear WHERE id=?", (gear_id,)).fetchone()
        if not r:
            return {"ok": False, "blad": "brak rzeczy"}
        k = g.execute("SELECT * FROM gear_knowledge WHERE gear_id=?", (gear_id,)).fetchone()
        obs = [dict(x) for x in g.execute(
            "SELECT o.id, o.note_id, o.obs_date, o.aspekt, o.wynik, o.opis, o.inne_przyczyny, o.waga, n.source, n.text AS uwaga, n.answer, n.question "
            "FROM gear_obs o JOIN gear_obs_note n ON n.id=o.note_id WHERE o.gear_id=? ORDER BY COALESCE(o.obs_date, o.created_at) DESC", (gear_id,))]
        prop = None
        if k and k["proposal_json"]:
            try:
                prop = json.loads(k["proposal_json"])
                f = prop.get("pole")
                prop["etykieta"] = PROP_LABEL.get(f, f)
                prop["z_txt"] = _vtxt(f, r[f]) if f in r.keys() else None
                prop["na_txt"] = _vtxt(f, prop.get("na"))
            except Exception:
                prop = None
        return {"ok": True, "gear_id": gear_id, "nazwa": _name(r), "co_wiemy": k["co_wiemy"] if k else None,
                "pewnosc": k["pewnosc"] if k else None, "n_obs": k["n_obs"] if k else 0, "propozycja": prop,
                "proposal_status": k["proposal_status"] if k else None, "obserwacje": obs}
    finally:
        g.close()


def decide_proposal(gear_id, decision) -> dict:
    """Zatwierdz -> zmiana pola audytu (a_src + GEAR-OBS, a_date dzis); Odrzuc -> AI nie wraca z ta sama propozycja bez nowych obserwacji."""
    if decision not in ("zatwierdz", "odrzuc"):
        return {"ok": False, "blad": "decyzja: zatwierdz | odrzuc"}
    g = _g()
    try:
        k = g.execute("SELECT * FROM gear_knowledge WHERE gear_id=?", (gear_id,)).fetchone()
        if not k or k["proposal_status"] != "czeka" or not k["proposal_json"]:
            return {"ok": False, "blad": "brak propozycji czekajacej na decyzje"}
        p = json.loads(k["proposal_json"])
        f = p.get("pole")
        if decision == "zatwierdz":
            if f not in PROP_FIELDS:
                return {"ok": False, "blad": "niedozwolone pole"}
            today = _dt.date.today().isoformat()
            r = g.execute("SELECT a_src FROM gear WHERE id=?", (gear_id,)).fetchone()
            src = ((r["a_src"] if r and r["a_src"] else "") + " + GEAR-OBS " + today).strip(" +")[:120]
            g.execute("UPDATE gear SET %s=?, a_src=?, a_date=? WHERE id=?" % f, (p.get("na"), src, today, gear_id))
            st = "zatwierdzona"
        else:
            st = "odrzucona"
        g.execute("UPDATE gear_knowledge SET proposal_status=?, updated_at=? WHERE gear_id=?", (st, _now(), gear_id))
        g.commit()
    finally:
        g.close()
    _KNOW_CACHE["t"] = 0.0
    _resolve_prop(gear_id)
    return {"ok": True, "gear_id": gear_id, "status": st}



# ---------------- powiadomienia (etap 3) ----------------
GARAZ_URL = "https://albert.cytr.us/garaz.html"


def _notif_key(gear_id):
    return "gearobs:prop:%d" % int(gear_id)


def _notify_prop(gear_id, nazwa, prop, z_val) -> None:
    """Nowa propozycja zmiany oceny z audytu -> Centrum powiadomien (dzwonek, 'ubior') + Telegram. Decyzja zapada w Garazu."""
    f = prop.get("pole")
    title = "Propozycja zmiany oceny: %s" % nazwa
    body = "%s: %s → %s. %s Zdecyduj w Garażu (okno rzeczy → Obserwacje z jazd)." % (
        PROP_LABEL.get(f, f), _vtxt(f, z_val) or "—", _vtxt(f, prop.get("na")), prop.get("dlaczego") or "")
    try:
        if "/opt/qbot/app" not in sys.path:
            sys.path.insert(0, "/opt/qbot/app")
        import qbot_notif as N
        conn = _pg()
        try:
            cur = conn.cursor()
            N.push(cur, _notif_key(gear_id), "ubior", title, body, "/garaz.html")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa
        print("gear_obs notif:", e)
    try:
        import qbot_trener_notify as TN
        TN.send("👕 " + title + "\n" + body, [[{"text": "Otwórz Garaż", "url": GARAZ_URL}]])
    except Exception as e:  # noqa
        print("gear_obs telegram:", e)


def _resolve_prop(gear_id) -> None:
    try:
        if "/opt/qbot/app" not in sys.path:
            sys.path.insert(0, "/opt/qbot/app")
        import qbot_notif as N
        conn = _pg()
        try:
            cur = conn.cursor()
            N.resolve(cur, _notif_key(gear_id))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa
        print("gear_obs notif resolve:", e)
