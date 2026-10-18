#!/usr/bin/env python3
"""WIKI-QBOT -- przebieg 3 (18.10.2026): zrzuty w trybie nocnym + metaznaczniki hasel + indeks wyszukiwania.
Status: /opt/qbot/artifacts/wiki_bg/status3.json. Na koniec jedna wiadomosc Telegram."""
from __future__ import annotations
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner as R
import pass2 as P

R.STATUS = f"{R.OUT}/status3.json"

FM = """METAZNACZNIKI (front matter) -- na samej gorze KAZDEGO hasla (poza plikami zaczynajacymi sie od "_"), dokladnie w tym ukladzie:
---
tytul: <tytul jak w naglowku #>
dzial: <modelq|forma|raport-jazdy|trener|trasy|pogoda|zdrowie|garaz|qext2|albert|polaczenia|system|ogolne>
typ: <liczba|algorytm|strona|zakladka|automat|polaczenie|pojecie|przeglad>
opis: <jedno zdanie prostym jezykiem, do wynikow wyszukiwania>
tagi: [3-8 slow kluczowych, male litery]
synonimy: [jak Michal moze to nazwac/wpisac w wyszukiwarke: potoczne nazwy, angielskie odpowiedniki, stare nazwy, literowki bez polskich znakow]
skroty: [skroty uzywane w serwisie, np. TSB, W'bal]
gdzie_widac: [nazwy stron/zakladek/kanalow: np. Forma, Trening, Telegram, Karoo]
liczby: [liczby/wskazniki opisane w hasle, z jednostka]
zalezy_od: [sciezki hasel, np. modelq/tp]
wplywa_na: [sciezki hasel]
zrodla_kodu: [pliki/funkcje/tabele]
aktualizacja: <DD.MM.RRRR z polecenia date>
---
Zasady: wartosci list w jednej linii w nawiasach [ ], bez dwukropkow wewnatrz wartosci, sciezki hasel bez .md. Zalezy_od/wplywa_na spojne z sekcjami
w tresci hasla i z zaleznosci.md. Synonimy to najwazniejsze pole dla wyszukiwarki -- badz hojny (np. dla TSB: swiezosc, forma dnia, zmeczenie, balans treningowy, form)."""

STAGES3 = [("M0_szablon", """ETAP M0: dopisz blok METAZNACZNIKOW (wzor ponizej) na gore _szablon.md z krotkim objasnieniem pol, oraz do README.md, mapa-serwisu.md,
zaleznosci.md, slowniczek.md (dzial: ogolne). Sprawdz, ze odnosniki do zrzutow img/ekrany/ w calym wiki wskazuja istniejace pliki (zrzuty zostaly
wlasnie przegenerowane w trybie nocnym, nazwy plikow bez zmian; lista: img/ekrany/indeks.md) -- zepsute popraw.\n\n""" + FM)]
for slug, scope, _src in R.MODULES:
    STAGES3.append((f"M_{slug}", f"""ETAP METAZNACZNIKI -- DZIAL "{slug}" ({scope}).
Dla KAZDEGO pliku {slug}/*.md dodaj (lub popraw istniejacy) blok metaznacznikow wg wzoru. Tresci hasel NIE przepisuj -- zmieniasz tylko blok na gorze
(wyjatek: jesli zalezy_od/wplywa_na w tresci przecza zaleznosci.md, popraw tresc). Pola wypelniaj z tresci hasla i z kodu (zrodla_kodu).\n\n""" + FM))


def main() -> int:
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    R.worklock()
    R.log("PASS3 START")
    t0 = time.time()
    with open(f"{R.OUT}/screens3.log", "w") as lf:
        try:
            rc = subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/screens.py"], stdout=lf, stderr=subprocess.STDOUT,
                                timeout=40 * 60, cwd=R.APP).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    import glob
    n_png = len(glob.glob(f"{P.SHOTS}/*.png"))
    st["stages"]["zrzuty_nocne"] = {"status": "OK" if rc == 0 else f"BLAD {rc}", "png": n_png, "min": round((time.time() - t0) / 60)}
    R.save_status(st)
    fails = [] if rc == 0 else ["zrzuty_nocne"]
    base_dirty = R.dirty_outside_wiki()
    for name, prompt in STAGES3:
        R.worklock()
        st["stages"][name] = {"start": R.now(), "status": "w toku"}
        R.save_status(st)
        t0 = time.time()
        rc = P.codex2(name, prompt, None)
        res = "OK" if rc == 0 else ("LIMIT CZASU" if rc == 124 else f"BLAD {rc}")
        st["stages"][name].update({"end": R.now(), "min": round((time.time() - t0) / 60), "status": res})
        if rc != 0:
            fails.append(name)
        nd = R.dirty_outside_wiki() - base_dirty
        if nd:
            st["stages"][name]["UWAGA_zmiany_poza_wiki"] = sorted(nd)[:30]
            base_dirty |= nd
        R.save_status(st)
        R.log(f"{name}: {res}")
    r = subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/build_index.py"], capture_output=True, text=True, timeout=300, cwd=R.APP)
    idx_info = (r.stdout or r.stderr).strip()[-200:]
    st["stages"]["indeks"] = {"status": "OK" if r.returncode == 0 else f"BLAD {r.returncode}", "info": idx_info}
    st.update({"done": True, "end": R.now()})
    R.save_status(st)
    subprocess.run([R.PY, f"{R.APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=R.APP, capture_output=True, timeout=30)
    msg = (f"📘 WIKI QBot — przebieg 3 gotowy ({R.now()}): zrzuty nocne {n_png}, metaznaczniki, wyszukiwarka w podglądzie.\n"
           f"Indeks: {idx_info}" + (f"\nProblemy: {', '.join(fails)}" if fails else "") +
           "\nhttps://albert.cytr.us/wiki-podglad/index.html")
    R.tg(msg)
    R.log("PASS3 KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"PASS3 AWARIA {e!r}")
        R.tg(f"⚠️ WIKI QBot przebieg 3: awaria {e!r}"[:400])
        raise
