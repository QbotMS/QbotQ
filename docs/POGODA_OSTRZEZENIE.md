# POGODA — ostrzeżenie o deszczu w czasie jazdy

> Stan: 2026-10-14. Kod: `qbot_pogoda_alert.py`. Powód: 14.10 start 14:30, ulewa 14:50–15:15; radar przewidział ją już o 14:10–14:30
> („ok. 15:00”), ale trzeba było zajrzeć na stronę.

**Decyzje Michała:** tylko ostrzeżenie o DESZCZU; na stronie (dzwonek w menu + pasek na Pogodzie) i w Telegramie; dla CAŁEJ długości
jazdy; QExt2 (Karoo) na razie bez zmian — integracja później, osobno.

- **Jazdy:** Trener (`trainer_session`, rower, plan), pilnowanie od 60 min przed startem do końca. Punkt: dom (`qbot_pogoda.home`).
- **Część jazdy w zasięgu radaru** (60 min, wg sprawdzalności radaru): prognoza radaru → „🌧 Radar: deszcz u Ciebie ok. HH:MM
  (za X min), siła (do N mm/h), potrwa ok. Y min”. Siła: < 1 słaby, < 4 umiarkowany, < 10 silny, ≥ 10 mm/h ulewa.
- **Dalsza część jazdy:** szansa z zespołu ICON-EU-EPS ≥ 40% → „🌦 Prognoza: X% szans … Radar na razie nic nie widzi”.
  Pilnowanie trwa co 5 min, więc kolejne odcinki jazdy wchodzą w zasięg radaru.
- **Bez zasypywania:** max 3 wiadomości na jazdę; radar — kolejna tylko dla nowego epizodu albo przesunięcia godziny > 15 min;
  prognoza — raz, zanim radar coś zobaczy. Logika w czystej funkcji `decide()` (testy w skrypcie wdrożeniowym).
- **Dzwonek:** źródło „Radar: deszcz w czasie jazdy” (klucz `radar:<id jazdy>`), wyłączenie w ustawieniach powiadomień wyłącza też
  Telegram. Pozycja zamyka się po końcu jazdy.
- Wywołanie: pętla radaru w qbot-web (każda nowa klatka). Stan: `qbot_v2.pogoda_alert`. API `/api/pogoda/ostrzezenie`.
