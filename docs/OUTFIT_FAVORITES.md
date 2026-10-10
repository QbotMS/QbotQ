# Faworyci ubioru (Analiza trasy -> Sprzet)

Wdrozone 2026-10-10 (decyzje Michala tego dnia).

## Co to jest
W panelu **Sprzet** Analizy trasy, w naglowku obok tytulu, jest przycisk **"★ Faworyci"** (z licznikiem).
Otwiera okno z dwiema kolumnami: **Rodzaj** (kategoria rzeczy z Garazu) | **Rzecz** (rzeczy tej kategorii, ptaszki).
Na gorze okna lista wybranych (× usuwa), ostrzezenie gdy dwie rzeczy sa z tej samej warstwy.
Faworyci sa przypisani do **trasy + daty planu** (ubior jest na dzien, w ktory planowana jest trasa).

## Dobor ubioru
- **Bez faworytow** - jak dotad: `qbot3/routes/outfit_advisor.advise` (zestaw spokojniejszy + szybszy).
- **Z faworytami** - `qbot3/routes/outfit_fav.advise_fav`:
  - **Zestaw A "Z Twoimi faworytami"**: zawiera KAZDY faworyt (na sobie albo w kieszeni; dwa z tej samej warstwy -> jeden do kieszeni).
    Faworyt spoza kandydatow silnika (np. poza zakresem temperatur) jest dokladany na sile. AI wybiera tempo A.
  - **"Jak rozumiem Twoj wybor"** (`zrozumienie`): 1-2 zdania, czemu pewnie wybrales te rzeczy (nowa rzecz do sprawdzenia, kolor, cieplej/luzniej niz prognoza...).
  - `faworyci_uwagi`: ostrzezenie, gdy faworyt slabo pasuje do warunkow - faworyt ZOSTAJE.
  - **Zestaw B "Propozycja AI"**: osobne wywolanie AI, ktore NIE widzi faworytow; **tempo B = tempo A**.
  - Kontrole i autokorekta silnika dzialaja na oba zestawy; autokorekta A jest cofana, gdy wyrzucilaby faworyta.
- Czas: dwa wywolania AI po kolei (~20-40 s).

## Dane i API
- Tabela `qbot_v2.route_outfit_fav (route_id, ride_date, gear_ids jsonb, updated_at)`, PK (route_id, ride_date); max 12 rzeczy.
- `GET /api/report/outfit/gear` - rzeczy z Garazu z warstwa ubioru (`nie_do_jazdy` = wykluczone audytem/ankieta).
- `GET /api/report/outfit/fav?route_id&date` -> `{ids}`; `POST /api/report/outfit/fav {route_id, date, ids}`.
- `POST /api/report/outfit` sam wybiera tryb (sa faworyci -> advise_fav). Propozycja z faworytami ma `tryb: "faworyci"`,
  `faworyci`, `zrozumienie`, `faworyci_uwagi`, zestawy z `rola: "faworyci" | "ai"`, rzeczy-faworyty z `faworyt: true`.
  Zapis jak dotad w `qbot_v2.route_outfit`.

## Front (statyki poza repo, kopia w web_public/)
- `raport-trasy2-plan.js` - blok Sprzet (przycisk, okno, render A/B, gwiazdki, ostrzezenie "faworyci zmienili sie").
- `raport-trasy2.js` - `document.body.dataset.mk` = aktywna sekcja (przycisk Faworyci widoczny tylko w Sprzecie).
- `raport-trasy2.css` - style `.mkw-fav*`, `.mkw-ov`, `.mkw-box`.

## Testy
`tests/test_outfit_fav.py` (bez AI: lista rzeczy, wymuszenie faworyta, walidacja jednego zestawu, prompt B).

# Uwagi do AI (2026-10-10)

Przycisk **"Uwagi do AI"** obok "Dobierz ponownie" (panel Sprzet). Okno: pole na uwage (np. "czarne rekawiczki -> lepiej zielone",
"zamien kamizelke w A"), lista **"Czego AI sie nauczylo"** z x (zapomnij).

Decyzje Michala:
- uwaga **poprawia od razu biezacy zestaw** - tylko wskazane rzeczy, reszta bez zmian, nowe rzeczy z calego Garazu;
  bez autokorekty silnika; zapis nowej wersji w `qbot_v2.route_outfit` (+ `uwagi_historia`, rzeczy `z_uwagi: true` = znak ✎),
- AI proponuje **wniosek na przyszlosc** (jedna zasada ogolna, albo brak gdy uwaga jednorazowa); **zapis dopiero po
  zatwierdzeniu** (mozna poprawic tekst); wniosek moze **zastapic** stare (sprzeczne/dublujace) - stare `active=false, replaced_by`.
- zatwierdzone wnioski (max 40 najnowszych) ida do **kazdego doboru** (z faworytami i bez) na poczatku `reguly_ubioru`
  z dopiskiem "priorytet nad innymi regulami" (`outfit_notes.as_rules` w `report_outfit_build`).
- rzecz wybrana zgodnie z wnioskiem: AI pisze w 'dlaczego' "zgodnie z Twoja uwaga" -> **autokorekta kolorow i podpowiedz
  kolorow silnika jej nie ruszaja** (`outfit_advisor._autofix` / `_checks`, warunek "uwag" w dlaczego).

Kod: `qbot3/routes/outfit_notes.py`. Tabela `qbot_v2.outfit_lessons (id, created_at, route_id, ride_date, uwaga, wniosek, active, replaced_by)`.
API: `POST /api/report/outfit/note {route_id, date, uwaga}` -> `{proposal, odpowiedz, zmiany, wniosek_propozycja}`;
`GET /api/report/outfit/lessons`; `POST /api/report/outfit/lessons {tresc, zastepuje, route_id, date, uwaga}` albo `{usun: id}`.
Test: `tests/test_outfit_notes.py` (bez AI). E2E 2026-10-10 na kopii propozycji: czarne MAAP Alt_Road -> zielone, ~3 s.

# Sprzet: rower i akcesoria (2026-10-10)

Sekcja **"Rower i akcesoria"** w panelu Sprzet (zastapila napis "Wybor Grizl / Monster Gravel pojawi sie...").
Kod: `qbot3/routes/gear_kit.py`. Panel Sprzet jest **na cala szerokosc obok menu** (przykrywa mape), czcionka tresci ~17 px,
zestawy A/B obok siebie (`.mkw-sets`).

- **Pogoda wstecz** (`past_weather`): Open-Meteo, opady godzinowe w 4 punktach trasy, okno 7 dni przed startem
  (sumy 24 h / 48 h / 72 h / 7 dni - max z punktow, ostatni deszcz) + minimalna widocznosc w czasie jazdy. Cache 30 min.
  Dla jazdy w przyszlosci godziny po "teraz" to prognoza.
- **Stan nawierzchni** (`surface_state`, progi do kalibracji na jazdach): **bloto** = >=25% nieutwardzonych i (24 h >= 8 mm
  albo 48 h >= 15 albo 7 dni >= 25 i 48 h >= 5); **mokro** = 24 h >= 3 albo 48 h >= 8 albo deszcz w czasie jazdy (>= 1 mm / >= 50%);
  **wilgotno** = 7 dni >= 10 albo 24 h >= 0,5; inaczej **sucho** (przy 7 dni < 2 mm: uwaga o sypkim piachu).
  Stan idzie tez do **doboru ubioru** (`warunki.nawierzchnia_po_opadach`, wkladane w `report_outfit_build`).
- **Rower** (AI, `choose_bike`): z Garazu bez roweru partnerki (`EXCLUDE_BIKES`); wejscie: nawierzchnia trasy asfalt/szuter/ujeby
  (kategorie 1 / 2-3 / 4-5), stan po opadach, km, przewyzszenie, czas, opony na kolach (wheel_mounts), zadania serwisowe todo.
  Wynik + drugi wybor + uwaga o oponach; zapis `qbot_v2.route_kit`. Wybierany automatycznie przy pierwszym otwarciu Sprzetu
  dla trasy+daty; "wybierz ponownie"; ostrzezenie gdy stan nawierzchni zmienil sie od wyboru.
- **Lampki** (regula w kodzie): start przed wschodem, meta po zachodzie lub < 30 min przed nim, widocznosc < 1 km -> **wymagane**
  (przod + tyl + czolowka jako zapas); widocznosc < 3 km -> **zalecane** (tyl). Lampki z Garazu (equipment, "swiatla"; bez Karoo).
- **Blotniki**: **zalecane** przy mokro / bloto; szukane w equipment/components (blotnik/fender/mudguard) - Michal je dopisze.

API: `GET /api/report/kit?route_id&date&time&long_stops&long_stop_min` (bez AI), `POST /api/report/kit` (AI wybor roweru).
Test: `tests/test_gear_kit.py` (bez AI i sieci).

## Rower: zasady Michala i reczny wybor (2026-10-10, korekta)
- `gear_kit.BIKE_RULES` (twarde, przed ocena AI): **Monster = rower na zime i naprawde ciezkie warunki** (snieg, mroz, glebokie bloto),
  NIE na zwykle trasy ok. 80 km i dluzsze; **biezace zadania serwisowe NIE wplywaja na wybor** (usuniete z wejscia AI).
- **Reczny wybor**: lista "zmien rower..." w karcie Rower -> `POST /api/report/kit/manual {route_id, date, bike_id, kontekst}`;
  zapis w `qbot_v2.route_kit` z `recznie: true` i kontekstem trasy (km, przewyzszenie, czas, nawierzchnia %, stan).
  Ostatnie 12 recznych wyborow (`manual_history`) idzie do AI jako `wybory_michala` - wzorzec na kolejne trasy.
  "zapytaj AI ponownie" nadpisuje wybor dla tej trasy+daty.
- **Blotniki per rower**: blotniki w `components` z `bike_id` (Mucky Nutz MugGuard Front/Rear -> Monster) pokazywane tylko
  dla wybranego roweru; blotniki w `equipment` (Ass Saver, SKS) - uniwersalne. Kategoria Sprzetu "Blotniki".
- 11.10 (Neverending Bug): Michal wybral Graila (zapisane jako reczny wybor).

## Zmiany danych w Garazu (garage.db, poza repo) - 2026-10-10, z czatu
- equipment 26 "Ass Saver Win Wing 2 Gravel Detour", 27 "SKS Speedrocker XL 28\"" - kategoria **Blotniki** (uniwersalne), mocowanie do uzupelnienia.
- components 73/74 "Mucky Nutz MugGuard Front/Rear" - kategoria Blotniki, **bike_id 2 (Monster)**, status zapas.
- components 75: Grizl CF SL 2025 (bike_id 1) - widelec **RockShox Rudy XPLR A1 Ultimate**, 40 mm, Sand, tlumik **Charger RaceDay 2**;
  to samo dopisane w notatce roweru (bikes.notes - te notatke czyta AI przy wyborze roweru). Sztywny widelec ma Grizl partnerki (bike_id 6).
- qbot_v2.route_kit: 11.10 (komoot-3340114493) - reczny wybor Michala: **Grail**.
- Kazda zmiana: kopia garage.db.bak.<data> przed zapisem.
