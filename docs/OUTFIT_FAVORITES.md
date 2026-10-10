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
