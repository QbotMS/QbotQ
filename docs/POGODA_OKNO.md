# POGODA — Okno jazdy (krok 2)

> Stan: 2026-10-14. Logika: `qbot_pogoda_okno.py`, API `/api/pogoda/okno?lat=&lon=[&id=|&dzien=&start=&dur=]`, panel ◷ na `pogoda.html`.

Pytanie: „przesunąć jazdę czy moknąć?”. Jazda z kalendarza Trenera (`trainer_session`, rower, plan, 3 dni) albo zadana ręcznie.
- **Kandydaci startu:** co 30 min w oknach Trenera na rower (`qbot_trener_engine.day_info` → `win['rower']`), bez kolizji z zajętościami
  i innymi sesjami dnia (bez sesji pominiętych); zawsze + godzina z planu; dziś tylko od teraz + 10 min.
- **Pogoda:** `qbot_pogoda.conditions_point` (modele wg sprawdzalności), szansa opadu z zespołu ICON-EU-EPS (Open-Meteo Ensemble,
  odsetek wariantów ≥ 0,2 mm/h), najbliższa godzina z radaru (`nowcast_point`, udział ≥ 0,5 → mm/h radaru), wschód/zachód (Open-Meteo daily).
- **Progi = Trener** (`P(ov,'wx.*')`: wiatr 8, porywy 13 m/s, szansa 40%, chłód, upał) — obie części QBota mówią jednym głosem.
- **Ocena 0–100** = 100 − 10 × kara: deszcz × 3, szansa, porywy ponad próg, oblodzenie 3, mgła 1,5, błoto 1, zmrok min/20, chłód/upał.
- Werdykt: „Lepiej przesunąć: HH:MM” gdy najlepszy start > plan + 10 pkt; karty Plan / Wcześniej / Później; siatka startów (klik = przelicz).
- Bez nowych wiadomości Telegram (zasada Michała).

## Gdzie jechać / weekend (krok 3, 2026-10-14)
`qbot_pogoda_map.ocena_dnia(dzien, a_h, b_h)` — ocena 0–100 każdego piksela 6 km w oknie godzin Trenera na rower (weekend 08–19):
kara = 0,08·wiatr + 0,04·|temp−16| (komfort, rozróżnia remisy) + opad[mm]·1,5 + max(0, wiatr−5) + max(0, poryw−12)·0,4 + max(0, 4−temp)·0,35
+ max(0, tmax−28)·0,5. PNG + JSON w katalogu przebiegu. Rejony: co ≥ 60 km, nazwa = najbliższa miejscowość ≥ 2000 mieszk. (GeoNames PL,
duże miasta po polsku), punkty > 15 km od miejscowości pomijane, sortowanie (ocena, odległość). Mapa modelu do +120 h, `pola_<krok>.npz`.
API `/api/pogoda/weekend?dzien=&lat=&lon=`, `/api/pogoda/weekend/{key}.png`. Uwaga: katalogi `pogoda_model` muszą należeć do qbot
(serwis zapisuje oceny dni) — ręczne przebudowy jako root psuły zapis (14.10). Szansa z zespołu tylko do +60 h, dalej mapa opadu.

### Limit odległości i zasięg pogody (2026-10-14, prośba Michała)
Panel ★: limit 50/100/150/250 km / bez limitu od pozycji prognozy (domyślnie 100, localStorage `qpogoda_wkkm`); `PM.rejony()` wybiera
miejsca tylko w promieniu (odstęp = limit/4, 20–60 km). Na mapie: przerywany okrąg limitu, etykiety „n. Nazwa · ocena” i **okrąg zasięgu
pogody** = odległość do najbliższego piksela z oceną < max(65, ocena − 8) (max 80 km) — jak daleko od punktu warunki są podobne.
Pola oceny zapisywane w `ocena_<dzien>_<okno>.npz`. API `/api/pogoda/weekend?...&km=`.
