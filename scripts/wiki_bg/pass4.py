#!/usr/bin/env python3
"""WIKI-QBOT -- przebieg 4 (18.10.2026): produkcyjna strona /wiki.html wg zaakceptowanej makiety (kanwa Design
"Wiki QBot — makieta"). Czeka na koniec przebiegu 3, buduje indeks (scripts/wiki_bg/build_index.py -> /wiki-dane/),
potem codex pisze WYLACZNIE wiki.html, wiki.js, wiki.css w /opt/qbot/web/public. Menu (nav.js) NIE jest ruszane.
Status: /opt/qbot/artifacts/wiki_bg/status4.json. Telegram na koniec."""
from __future__ import annotations
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner as R

R.STATUS = f"{R.OUT}/status4.json"
PUB = "/opt/qbot/web/public"
ALLOWED = {"wiki.html", "wiki.js", "wiki.css"}
STAGE = "/opt/qbot/artifacts/wiki_web"  # piaskownica codexa nie moze pisac w web/public (bwrap/.git) -> budowa tu, kopia przez runner

SPEC = f"""Budujesz PRODUKCYJNA strone wiki serwisu QBot Lab. Katalog roboczy: {STAGE} -- tu tworzysz WYLACZNIE wiki.html, wiki.js, wiki.css; po Twojej pracy skrypt skopiuje je do {PUB}
(statyczne pliki serwisu, serwowane przez qbot-web za logowaniem jako /wiki.html). Pliki serwisu czytasz z {PUB}. NIE ruszasz zadnego innego pliku (nav.js, ui2*.css, inne strony -- tylko czytasz).
Nie restartujesz uslug. Nie piszesz do bazy.

DANE (gotowe, tylko odczyt przez fetch): /wiki-dane/_indeks.json (pola: zbudowano, hasla[{{p, tytul, dzial, typ, opis, tagi[], synonimy[], skroty[], gdzie_widac[],
liczby[], zalezy_od[], wplywa_na[], naglowki[], tekst}}]) oraz pliki /wiki-dane/<p> (markdown z blokiem front matter --- ... --- na gorze, ktory trzeba odciac)
i obrazy /wiki-dane/img/... (linki w md sa wzgledne do pliku md). Zajrzyj do {R.APP}/docs/wiki/ i {R.APP}/scripts/wiki_bg/build_index.py, zeby poznac format.

WZORZEC WYGLADU: istniejace strony serwisu -- przeczytaj forma.html, ui2.css, ui2-tokens.css, nav.js, tabs.css, theme.css w {PUB}. Strona MUSI:
- podlaczyc /ui2-tokens.css (jedyne zrodlo kolorow; zero kolorow wpisanych na sztywno -- tylko zmienne var(--bg) itd.), /nav.css + /nav.js (lewe menu serwisu
  jak na innych stronach, przelacznik dzien/noc klasa html.theme-dark, klucz localStorage qtheme) -- tak samo jak forma.html;
- dzialac w trybie dziennym i NOCNYM oraz na iPhonie (390 px): na telefonie drzewko dzialow chowa sie pod przycisk, spis "Na tej stronie" staje sie poziomym paskiem.
- Biblioteki tylko jesli niezbedne: markdown -> marked (pinned, z cdn.jsdelivr.net), diagramy -> mermaid (pinned) z motywem dopasowanym do dzien/noc.
  Sprawdz, czy serwis ma juz te pliki lokalnie w {PUB}/vendor -- jesli tak, uzyj lokalnych.

WIDOKI (jedna strona, routing przez ?p=<sciezka hasla> i ?q=<szukane>; przyciski wstecz przegladarki dzialaja -- history.pushState):
1. START (brak p): naglowek "Jak dziala QBot -- po ludzku" + zdanie; DUZE pole wyszukiwania; "Czesto szukane" (4 chipy: hasla z typem liczba/algorytm
   z dzialow modelq/forma/raport-jazdy/trasy); INTERAKTYWNA MAPA SERWISU: trzy pasy od lewej -- ZRODLA DANYCH / SILNIKI QBOTA / GDZIE TO WIDZISZ --
   kafelki-przyciski; klikniecie kafelka podswietla powiazane (reszta przygaszona do 30%), pod mapa panel: kategoria, nazwa, opis 1-2 zdania,
   "Korzysta z:", "Zasila:", przycisk "Otworz dzial". Strzalki tylko najwazniejsze (np. ModelQ->Raport, ModelQ->Forma, Forma->Trener, Pogoda->Analiza trasy,
   Pogoda->Garaz + dwie duze strzalki miedzy pasami). Silniki = dzialy wiki; powiazania silnik<->silnik licz z pol zalezy_od/wplywa_na w indeksie (zagreguj po dziale),
   zrodla i kanaly wyjscia opisz w malej tablicy w wiki.js (z komentarzem skad pochodzi -- mapa-serwisu.md). Mapa ma sie przewijac poziomo na telefonie.
   Dalej: siatka DZIALOW (12 kafelkow: nazwa, liczba hasel z indeksu, opis 1 zdanie z <dzial>/index.md), trzy karty: Mapa serwisu (mapa-serwisu.md),
   Zaleznosci (zaleznosci.md), Slowniczek (slowniczek.md); "Ostatnio zmienione" (5 hasel wg pola aktualizacja).
2. HASLO (?p=...): lewa kolumna drzewko dzialow (biezacy dzial rozwiniety, biezace haslo podswietlone), srodek tresc, prawa kolumna "Na tej stronie" (z naglowkow ##,
   podswietla aktualna sekcje przy przewijaniu). Nad trescia: okruszki (Wiki > Dzial > Haslo), tytul, opis, chipy: typ, aktualizacja, "Inne nazwy:" (synonimy).
   Tresc z markdown; bloki mermaid renderowane; obrazy z poprawionymi sciezkami, klikalne (powiekszenie w nakladce); linki .md -> nawigacja wewnatrz wiki;
   sekcje "Wplywa na"/"Zalezy od" -- dodatkowo na dole dwie karty z linkami z metaznacznikow; "Zrodla" zwiniete (<details>).
   Numerowane listy w sekcji "Jak liczone" wystylizuj jako kroki (kolko z numerem). Cytaty "> DO SPRAWDZENIA" jako zolta ramka.
3. WYSZUKIWARKA: pole w naglowku kazdego widoku + skrot klawisza "/". Wyniki na zywo pod polem (lista: tytul, dzial, typ, opis, oraz "Pasuje do: <synonim>"
   gdy trafienie nie w tytule). Ranking: tytul 10, synonimy/skroty/tagi 8, opis 4, naglowki 2, tekst 1; kazde slowo zapytania musi trafic; bez polskich znakow
   i wielkosci liter (normalize NFD, l/ł). Filtr dzialow chipami. Enter = pierwszy wynik. ?q= w adresie.
4. STRONA GLOWNA ma <title>Wiki — QBot Lab</title>, favicon jak inne strony.

JAKOSC: czysty, czytelny kod (komentarze po polsku, krotkie), dostepnosc (prawdziwe <button>/<a>/<input> z <label>), kontrast w obu motywach, brak bledow w konsoli.
Daty w formacie DD.MM.RRRR. Na koniec w ostatniej odpowiedzi podaj krotko: co zrobiono, czego nie zrobiono, znane braki (trafi do P4_strona.last.txt).
Jesli mozesz -- sprawdz strone: {R.PY} {R.APP}/scripts/dev_fetch.py /wiki.html --head  (moze nie dzialac w piaskownicy -- wtedy pomin)."""


def snapshot() -> dict:
    out = {}
    for f in os.listdir(PUB):
        p = os.path.join(PUB, f)
        if os.path.isfile(p) and f not in ALLOWED:
            out[f] = os.path.getmtime(p)
    return out


def main() -> int:
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    t_wait = time.time()
    while time.time() - t_wait < 60 * 60:  # czekaj na przebieg 3 (max 60 min)
        try:
            if json.load(open(f"{R.OUT}/status3.json")).get("done"):
                break
        except Exception:
            pass
        time.sleep(30)
    R.worklock()
    R.log("PASS4 START")
    r = subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/build_index.py"], capture_output=True, text=True, timeout=300, cwd=R.APP)
    st["stages"]["indeks"] = {"status": "OK" if r.returncode == 0 else f"BLAD {r.returncode}", "info": (r.stdout or r.stderr)[-200:]}
    R.save_status(st)
    before = snapshot()
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    os.makedirs(STAGE, exist_ok=True)
    cmd = ["codex", "exec", "--skip-git-repo-check", "-C", STAGE, "-o", f"{R.OUT}/P4_strona.last.txt",
           "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
           "--", SPEC]
    t0 = time.time()
    with open(f"{R.OUT}/P4_strona.log", "w") as lf:
        try:
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                timeout=90 * 60, env=env, cwd=STAGE).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    import shutil
    for f in ALLOWED:
        if os.path.exists(os.path.join(STAGE, f)):
            shutil.copy2(os.path.join(STAGE, f), os.path.join(PUB, f))
    after = snapshot()
    changed = sorted(f for f in after if before.get(f) != after[f])
    made = sorted(f for f in ALLOWED if os.path.exists(os.path.join(PUB, f)))
    st["stages"]["strona"] = {"status": "OK" if rc == 0 else f"BLAD {rc}", "min": round((time.time() - t0) / 60),
                              "pliki": made, "UWAGA_zmienione_inne": changed}
    st.update({"done": True, "end": R.now()})
    R.save_status(st)
    subprocess.run([R.PY, f"{R.APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=R.APP, capture_output=True, timeout=30)
    msg = (f"📘 WIKI QBot — strona /wiki.html: {'gotowa' if rc == 0 and len(made) == 3 else 'NIE POWSTALA (rc ' + str(rc) + ', plikow ' + str(len(made)) + ')'} ({R.now()}).\n"
           f"Pliki: {', '.join(made) or 'brak'}" + (f"\n⚠️ Zmienione inne pliki: {', '.join(changed)}" if changed else "") +
           "\nhttps://albert.cytr.us/wiki.html — przed wpięciem do menu sprawdzę ją na żywo.")
    R.tg(msg)
    R.log("PASS4 KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"PASS4 AWARIA {e!r}")
        R.tg(f"⚠️ WIKI QBot przebieg 4: awaria {e!r}"[:400])
        raise
