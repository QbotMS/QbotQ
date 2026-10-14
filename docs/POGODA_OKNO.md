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
