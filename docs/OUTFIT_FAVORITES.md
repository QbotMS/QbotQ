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
