"""Uwagi do AI przy doborze ubioru (Analiza trasy -> Sprzet -> "Uwagi do AI").

Decyzje Michala 2026-10-10:
- uwaga (wolny tekst, np. "dobral rekawiczki czarne, lepiej pasuja zielone") POPRAWIA OD RAZU biezacy zestaw
  (tylko wskazane rzeczy, reszta zostaje; bez autokorekty silnika) i zapisuje nowa wersje propozycji,
- AI proponuje WNIOSEK NA PRZYSZLOSC (zasada ogolna); zapis dopiero po zatwierdzeniu przez Michala,
- zatwierdzone wnioski (qbot_v2.outfit_lessons, active) ida do KAZDEGO doboru ubioru jako reguly z priorytetem
  (qbot_web.report_outfit_build -> rules), nowy wniosek moze zastapic stare (sprzeczne / dublujace),
- rzecz wybrana zgodnie z wnioskiem ma w 'dlaczego' slowo "uwag" -> autokorekta kolorow silnika jej nie cofa.
Dok.: docs/OUTFIT_FAVORITES.md (sekcja Uwagi do AI)
"""
from __future__ import annotations

import datetime as _dt
import json

from qbot3.routes import outfit_advisor as OA
from qbot3.routes import outfit_fav as F

MAX_LESSONS = 40


# ---------------- wnioski ----------------
def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.outfit_lessons (id bigserial PRIMARY KEY, "
                 "created_at timestamptz NOT NULL DEFAULT now(), route_id text, ride_date date, uwaga text, "
                 "wniosek text NOT NULL, active boolean NOT NULL DEFAULT true, replaced_by bigint)")


def _r(r, keys):
    return dict(r) if isinstance(r, dict) else dict(zip(keys, r))


def lessons(conn) -> list:
    ensure(conn)
    rows = conn.execute("SELECT id, wniosek, created_at FROM qbot_v2.outfit_lessons WHERE active ORDER BY created_at DESC LIMIT %s",
                        (MAX_LESSONS,)).fetchall()
    conn.commit()
    out = []
    for x in rows:
        x = _r(x, ("id", "wniosek", "created_at"))
        out.append({"id": int(x["id"]), "wniosek": x["wniosek"], "created_at": str(x["created_at"])})
    return out


def as_rules(conn) -> list:
    """Wnioski w formacie regul dla promptu doboru (pierwsze = najwazniejsze)."""
    try:
        ls = lessons(conn)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []
    return [{"temat": "WNIOSEK Z UWAG MICHALA - priorytet nad innymi regulami; rzecz wybrana z jego powodu: w 'dlaczego' napisz 'zgodnie z Twoja uwaga'",
             "tresc": x["wniosek"]} for x in ls]


def save_lesson(conn, tresc, zastepuje=None, route_id=None, ride_date=None, uwaga=None) -> dict:
    ensure(conn)
    t = (tresc or "").strip()[:400]
    if not t:
        raise ValueError("pusty wniosek")
    r = conn.execute("INSERT INTO qbot_v2.outfit_lessons (route_id, ride_date, uwaga, wniosek) VALUES (%s,%s,%s,%s) RETURNING id",
                     (route_id, ride_date, (uwaga or "")[:1000], t)).fetchone()
    nid = int(r["id"] if isinstance(r, dict) else r[0])
    ids = []
    for x in zastepuje or []:
        try:
            ids.append(int(x))
        except Exception:
            pass
    if ids:
        conn.execute("UPDATE qbot_v2.outfit_lessons SET active=false, replaced_by=%s WHERE id = ANY(%s) AND active", (nid, ids))
    conn.commit()
    return {"id": nid, "wniosek": t}


def delete_lesson(conn, lid) -> bool:
    ensure(conn)
    conn.execute("UPDATE qbot_v2.outfit_lessons SET active=false WHERE id=%s", (int(lid),))
    conn.commit()
    return True


# ---------------- poprawka biezacego zestawu ----------------
def _set_view(z, by):
    def it(i, where):
        g = by.get(int(i.get("id", -1))) or {}
        return {"id": i.get("id"), "nazwa": i.get("nazwa") or g.get("nazwa"), "warstwa": i.get("warstwa") or g.get("warstwa"),
                "kolor": i.get("kolor") or g.get("kolor"), "gdzie": where}
    return [it(i, "na_sobie") for i in z.get("rzeczy") or []] + [it(i, "kieszen") for i in z.get("do_kieszeni") or []]


def _prompt(p, by, uwaga, ls):
    zs = p.get("zestawy") or []
    cur = [{"zestaw": "A" if i == 0 else "B", "nazwa": z.get("nazwa"), "rzeczy": _set_view(z, by)} for i, z in enumerate(zs)]
    garaz = [{"id": g["id"], "nazwa": g["nazwa"], "warstwa": g["warstwa"], "kolor": g.get("kolor")} for g in by.values()
             if not g.get("nie_do_jazdy")]
    return ("Michal zglasza uwage do zaproponowanego ubioru na jazde. Zrob DWIE rzeczy:\n"
            "1) poprawke biezacych zestawow: zmien TYLKO to, czego dotyczy uwaga (reszta bez zmian); nowe rzeczy WYLACZNIE z listy 'garaz' (id);"
            " jedna rzecz na warstwe na sobie; jesli uwaga nie wskazuje zestawu, a pasuje do obu - zmien w obu;\n"
            "2) wniosek na przyszlosc: JEDNO zdanie, zasada ogolna (nie o tej jednej jezdzie), ktora pomoze lepiej dobierac ubior"
            " (np. 'Do zielonej gory dobieraj zielone rekawiczki zamiast czarnych'); jesli uwaga jest czysto jednorazowa - null."
            " Jesli wniosek jest sprzeczny albo dubluje ktorys z 'wnioski_dotad' - podaj ich id w 'zastepuje'.\n"
            "Piszesz po polsku Z POLSKIMI ZNAKAMI (a, e, l z ogonkami itd.), na TY.\n\n"
            "uwaga: " + json.dumps(uwaga, ensure_ascii=False)
            + "\n\nzestawy (biezace): " + json.dumps(cur, ensure_ascii=False)
            + "\n\nwnioski_dotad: " + json.dumps([{"id": x["id"], "wniosek": x["wniosek"]} for x in ls], ensure_ascii=False)
            + "\n\ngaraz: " + json.dumps(garaz, ensure_ascii=False)
            + '\n\nZwroc TYLKO JSON: {"zmiany": [{"zestaw": "A" lub "B", "usun_id": id lub null, "dodaj_id": id lub null,'
              ' "gdzie": "na_sobie" lub "kieszen", "dlaczego": "1 zdanie (dla nowej rzeczy), zaczynasz od: Zgodnie z Twoja uwaga"}],'
              ' "odpowiedz": "1-2 zdania: co zmieniles (albo czemu nic)",'
              ' "wniosek": {"tresc": "zdanie albo null", "zastepuje": [id]}}')


def _nm(it):
    k = (it.get("kolor") or "").strip()
    return "%s%s" % (it.get("nazwa") or it.get("id"), " (%s)" % k.lower() if k else "")


def _apply(p, zmiany, by):
    """Deterministyczne nalozenie zmian AI. Zwraca liste opisow (pusta = nic nie zmieniono)."""
    done = []
    zs = p.get("zestawy") or []
    for ch in zmiany if isinstance(zmiany, list) else []:
        if not isinstance(ch, dict):
            continue
        zi = 0 if str(ch.get("zestaw") or "A").upper().startswith("A") else 1
        if zi >= len(zs):
            continue
        z = zs[zi]
        z.setdefault("rzeczy", []); z.setdefault("do_kieszeni", [])
        try:
            rm = int(ch["usun_id"]) if ch.get("usun_id") is not None else None
        except Exception:
            rm = None
        try:
            ad = int(ch["dodaj_id"]) if ch.get("dodaj_id") is not None else None
        except Exception:
            ad = None
        if ad is not None and ad not in by:
            continue
        tag = "A" if zi == 0 else "B"
        slot_on = None
        if rm is not None:
            for key in ("rzeczy", "do_kieszeni"):
                for i, it in enumerate(z[key]):
                    if int(it.get("id", -1)) == rm:
                        z[key].pop(i)
                        slot_on = key
                        done.append("%s: usuni\u0119to %s" % (tag, _nm(it)))
                        break
                if slot_on:
                    break
        if ad is None:
            continue
        g = by[ad]
        key = "do_kieszeni" if (ch.get("gdzie") == "kieszen" or (slot_on == "do_kieszeni" and ch.get("gdzie") != "na_sobie")) else "rzeczy"
        z["rzeczy"] = [i for i in z["rzeczy"] if int(i.get("id", -1)) != ad]
        z["do_kieszeni"] = [i for i in z["do_kieszeni"] if int(i.get("id", -1)) != ad]
        if key == "rzeczy":
            for i, it in enumerate(z["rzeczy"]):
                if (it.get("warstwa") or (by.get(int(it.get("id", -1))) or {}).get("warstwa")) == g["warstwa"]:
                    done.append("%s: zamiast %s" % (tag, _nm(it)))
                    z["rzeczy"].pop(i)
                    break
        new = {"id": g["id"], "nazwa": g["nazwa"], "kategoria": g["kategoria"], "warstwa": g["warstwa"], "kolor": g.get("kolor"),
               "dlaczego": (ch.get("dlaczego") or "Zgodnie z Twoja uwaga.").strip(), "zamienniki": [], "z_uwagi": True}
        z[key].append(new)
        done.append("%s: dodano %s" % (tag, _nm(g)))
    for z in zs:
        z["rzeczy"].sort(key=lambda x: OA.LAYER_KEYS.index(x["warstwa"]) if x.get("warstwa") in OA.LAYER_KEYS else 99)
        z["kolory"] = OA._kolory(z["rzeczy"])
    return done


def apply_note(conn, route_id, ride_date, uwaga) -> dict:
    from qgpt_client import qgpt_json
    u = (uwaga or "").strip()[:1000]
    if not u:
        return {"ok": False, "blad": "pusta uwaga"}
    row = conn.execute("SELECT proposal, start_time, long_stops, long_stop_min FROM qbot_v2.route_outfit WHERE route_id=%s AND ride_date=%s "
                       "ORDER BY created_at DESC LIMIT 1", (route_id, ride_date)).fetchone()
    conn.commit()
    if not row:
        return {"ok": False, "blad": "brak propozycji ubioru dla tego planu - najpierw dobierz ubior"}
    row = _r(row, ("proposal", "start_time", "long_stops", "long_stop_min"))
    p = row["proposal"] if not isinstance(row["proposal"], str) else json.loads(row["proposal"])
    by = {g["id"]: g for g in F.gear_list()}
    ls = lessons(conn)
    try:
        o = qgpt_json(_prompt(p, by, u, ls), system="Doradca ubioru rowerowego QBota. Tylko JSON.", max_tokens=2000, temperature=0.3)
    except Exception as e:  # noqa
        return {"ok": False, "blad": "AI: %s" % str(e)[:120]}
    if not isinstance(o, dict):
        return {"ok": False, "blad": "zla odpowiedz AI"}
    done = _apply(p, o.get("zmiany"), by)
    odp = (o.get("odpowiedz") or "").strip()
    p.setdefault("uwagi_historia", []).append({"uwaga": u, "odpowiedz": odp, "zmiany": done,
                                               "kiedy": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")})
    p["created_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    if done:
        OA.save(conn, route_id, ride_date, row["start_time"], row["long_stops"], row["long_stop_min"], p)
    p["plan"] = {"start": row["start_time"], "long_stops": row["long_stops"], "long_stop_min": row["long_stop_min"]}
    w = o.get("wniosek") if isinstance(o.get("wniosek"), dict) else {}
    t = (w.get("tresc") or "").strip() if isinstance(w.get("tresc"), str) else ""
    zast = []
    lmap = {x["id"]: x for x in ls}
    for x in w.get("zastepuje") or []:
        try:
            if int(x) in lmap:
                zast.append(lmap[int(x)])
        except Exception:
            pass
    return {"ok": True, "proposal": p, "odpowiedz": odp, "zmiany": done,
            "wniosek_propozycja": {"tresc": t, "zastepuje": zast} if t and t.lower() != "null" else None}
