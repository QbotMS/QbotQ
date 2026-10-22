# QExt2 — symulator pól i log zmian w QBocie

Decyzje Michała: 18.10.2026 (DECISIONS: QEXT2-SYM). Strona: Garaż → zakładka **QExt2** (`/garaz.html#qext2`, ramka `/qext2-makieta.html?embed=1`).

## Co jest na stronie
- **Trzy ekrany Karoo naraz**: KOKPIT 2 (pole nav + pole instr jedno pod drugim, mapa poglądowa pod nimi), STATS v2, INFO.
- **Scenariusze jazdy** wzdłuż lewej krawędzi — symulacja na żywo (`qext2-makieta.js`): moc → prędkość z fizyki (opory,
  nachylenie, wiatr), tętno z opóźnieniem, W′ (Skiba), NP 5, okna PRZEBIEG, TEMPO, ETA, komunikaty z wyprzedzeniem trasy.
- **Build w symulatorze**: lista buildów od startu logu (18.10.2026, commit e4d32f6); wybór przeładowuje stronę z wersją tego buildu.
- **Log zmian QExt2**: wpisy pogrupowane po dniach — godzina, build (gdy znany) lub commit, opis po polsku, stan symulatora.

## Dwie części symulatora
1. **Wygląd pól** — port 1:1 kodu QExt2 na `<canvas>`:
   - `qext2-kokpit2.js` ← `kokpit/Kokpit2.kt` (Kokpit2NavRenderer, Kokpit2InstRenderer)
   - `qext2-stats.js` ← `statsv2/StatsV2Renderer.kt` (render = STATS v2, renderInfo = INFO); czcionki `/fonts/SairaSemiCondensed-*.ttf`
2. **Dane w polach** — `qext2-makieta.js` (scenariusze jazdy). Tych danych NIE ma w kodzie QExt2 (na Karoo pochodzą z czujników,
   Karoo i QBota), więc symulator je wylicza/zmyśla. Funkcje: `navData()` (KokpitNavData), `instrData()` (KokpitInstData),
   `statsData()` (StatsV2Data), `dynItem()` (DynItem), `buildInfoWx()` (InfoWx / WxItem). Dostęp testowy: `window.__QEXT2_SIM`.
Wersje per build: `/opt/qbot/web/public/qext2-sim/<sha7>/` (qext2-kokpit2.js, qext2-stats.js, qext2-makieta.js; brak pliku → wersja
z katalogu głównego). Pliki `/qext2-*.js` w katalogu głównym = wersja startowa (ręczny port z 18.10).

## Automat (`scripts/qext2_watch.py`)
Wątek `qbot-qext2-watch` w qbot-web co 10 min uruchamia skrypt jako osobny proces (użytkownik qbot; wyłączenie `QBOT_QEXT2_WATCH=0`;
wynik każdego przebiegu: `/opt/qbot/artifacts/qext2_watch.log`).
1. Nowe commity repo `/opt/qbot/qext2_deploy` (tylko odczyt git).
2. Wpis logu: data, sha, build (tag `build-N`, gdy serwer go zna — QBot nie pobiera tagów z GitHuba; numer dochodzi później),
   pliki, opis AI po polsku (temat + fragment różnicy; zapas: temat commitu).
3. **Wygląd**: commit zmienia `Kokpit2.kt` / `StatsV2Renderer.kt` → AI przenosi różnicę Kotlina do portu JS.
4. **Nowe dane** (decyzja 18.10): commit dodaje pola do klas danych (KokpitNavData, KokpitInstData, StatsV2Data, DynItem, InfoWx,
   WxItem) → AI dopisuje je do symulacji z wartościami PRZYKŁADOWYMI (w kodzie `/* przykladowe (auto) */`; w logu lista pól).
5. Test: `node --check` + test dymny (wszystkie scenariusze, trzy ekrany) + każde nowe pole ma wartość w symulacji.
   OK → nowa wersja symulatora. Błąd → wpis „wygląd z poprzedniego buildu” + powiadomienie (dzwonek `qext2` + Telegram).
6. Zapis: `qext2-sim/builds.json` (log, najnowszy pierwszy), stan `data/qext2_watch_state.json`.

## ZMIANY PROJEKTOWANE (od 22.10.2026, sesja qext2proj-2210)
Decyzja Michała: zmiany wyglądu pól QExt2 ogląda NAJPIERW w symulatorze QBota, bez buildów testowych. Kierunek odwrotny do automatu:
projekt powstaje w JS (port pól), po akceptacji jest przenoszony do Kotlina → JEDEN build.
- **Slot**: `/opt/qbot/web/public/qext2-sim/projekt/` — kopia trzech plików JS wersji bazowej (tu się projektuje) + `projekt.json`
  (baza, tytuł, punkty `nr/pole/title/opis/status`, warianty `key/label/default/options`). Automat `qext2_watch.py` slotu NIE dotyka.
- **Strona**: `/qext2-makieta.html?b=projekt` — przełącznik u góry „Obecny build | Zmiany projektowane · N pkt” (widoczny, gdy
  projekt aktywny), panel punktów, pigułki wariantów. `&s=N` = scenariusz (zachowany przy przełączaniu obecny ↔ projekt),
  `&v=klucz:wartość,...` = warianty.
- **Warianty w kodzie projektu**: `(window.QV ? window.QV("klucz", "domyślny") : "domyślny")` — zmiana pigułki działa od razu
  (rysowanie co sekundę); zapas potrzebny, bo test dymny (node) nie ma `QV`.
- **Narzędzie** `scripts/qext2_projekt.py` (jako qbot, krótkie): `start [--base SHA7] [--title]`, `status`, `diff [plik]` (materiał
  do Kotlina), `test` (ten sam test dymny co automat), `zrzut [--b projekt|SHA7] [--s N] [--v ...]` (Playwright: błędy JS,
  czy ekrany narysowane, PNG w `/opt/qbot/artifacts/qext2-projekt/`), `zamknij [--build N]` (po buildzie: archiwum
  `qext2-sim/projekt-archiwum/<data>/`, przełącznik znika).
- **Cykl**: start → zmiany w `qext2-sim/projekt/*.js` (+ dane przykładowe w `qext2-makieta.js`) → `test` + `zrzut` → Michał ogląda
  i akceptuje punkty (status w `projekt.json`) → przeniesienie do Kotlina → build → automat dodaje build do logu → `zamknij`.

## Ograniczenia
- Wartości nowych danych są zgadnięte przez AI — pierwszy taki wpis warto przejrzeć.
- Mapa i teksty komunikatów są poglądowe.
- Skrypt odmawia uruchomienia jako root (pliki root zablokowałyby automat).
- Projekt to port JS — ostateczna czytelność (Karoo 3 ok. 2× gęstszy niż monitor) i tak do potwierdzenia na urządzeniu.
