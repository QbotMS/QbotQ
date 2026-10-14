# POGODA — ostrzeżenie o deszczu w czasie jazdy

> Stan: 2026-10-14. Kod: `qbot_pogoda_alert.py`, `qbot_karoo_live.py`, endpoint `POST /qext2/ping` w `mcp_server.py`.
> Powód: 14.10 plan Trenera 13:00, faktyczny start 14:30, ulewa 14:50–15:15; radar przewidział ją już o 14:10–14:30
> („ok. 15:00”), ale trzeba było zajrzeć na stronę, a pilnowanie wg planu objęło złe okno.

**Decyzje Michała:** tylko ostrzeżenie o DESZCZU; na stronie (dzwonek w menu + pasek na Pogodzie), w Telegramie i (etap 3) na Karoo;
dla CAŁEJ długości jazdy.

## Skąd wiadomo, że jedziesz (od 14.10 wieczór)

1. **Jazda z Karoo (pierwszeństwo).** QExt2 wysyła co ~5 min sygnał „jestem tu” (`POST /qext2/ping`, body `{"lat","lon"}`,
   token urządzenia jak `/ride-readiness`, bez tokenu 401). Pierwszy sygnał = start jazdy, brak sygnału przez 15 min = koniec
   (bez osobnych sygnałów start/stop — decyzja Michała). Zapisywana tylko OSTATNIA pozycja bieżącej jazdy (`qbot_v2.karoo_live`,
   1 wiersz na jazdę). Kasowanie: gdy QBot wczyta plik tej jazdy (`training_sessions.started_at` w oknie jazdy), awaryjnie po 24 h.
   Punkt radaru = ostatnia pozycja; jazda „otwarta” (koniec nieznany) → tylko radar, bez szansy z zespołu. Plany Trenera są wtedy
   pomijane (bez dubli). Kierunek jazdy niepotrzebny — prognoza radaru sama przesuwa opad zgodnie z jego ruchem.
2. **Zapas: plan Trenera** (`trainer_session`, rower, plan), gdy Karoo nie nadaje — pilnowanie od 60 min przed startem do końca
   jazdy, punkt: dom (`qbot_pogoda.home`). Dzięki temu ostrzeżenie może przyjść jeszcze przed wyjazdem.

## Treść i limity

- **Część jazdy w zasięgu radaru** (60 min, wg sprawdzalności radaru): „🌧 Radar: deszcz u Ciebie ok. HH:MM (za X min), siła
  (do N mm/h), potrwa ok. Y min”. Siła: < 1 słaby, < 4 umiarkowany, < 10 silny, ≥ 10 mm/h ulewa.
- **Dalsza część jazdy (tylko plan Trenera):** szansa z zespołu ICON-EU-EPS ≥ 40% → „🌦 Prognoza: X% szans … Radar na razie nic nie widzi”.
- **Bez zasypywania:** max 3 ostrzeżenia na jazdę (dzwonek); radar — kolejne tylko dla nowego epizodu albo przesunięcia godziny
  > 15 min; prognoza — raz, zanim radar coś zobaczy. **Telegram: tylko PIERWSZE ostrzeżenie na jazdę** (decyzja 14.10) — kolejne
  tylko dzwonek i Karoo.
- **Dzwonek:** źródło „Radar: deszcz w czasie jazdy” (klucz `radar:<id>` plan / `radar:k<id>` Karoo); wyłączenie w ustawieniach
  powiadomień wyłącza też Telegram. Pozycja zamyka się po końcu jazdy.

## Odpowiedź dla Karoo (etap 3: wyświetlenie w KOKPICIE)

`POST /qext2/ping` → `{"status":"OK","ride":id,"new_ride":bool,"rain":null|{...}}`. `rain` = bieżące ostrzeżenie z radaru dla tej
jazdy (dopóki epizod trwa, +5 min): `eta` (HH:MM), `za_min`, `pada`, `mmh`, `sila`, `dur_min`, `otwarte`, `short`
(np. „deszcz za 12 min · umiarkowany · ~30 min” / „pada · ulewa · jeszcze ~20 min”). Ostrzeżenie liczy pętla radaru co nową klatkę,
więc odpowiedź może się spóźniać do ~5 min względem sygnału. Ograniczenie: gdy radar „zgubi” zapowiedziany opad, ostatnie
ostrzeżenie wisi do swojego końca (eta + czas trwania).

## Technika

- Logika: czyste funkcje `decide()` (qbot_pogoda_alert) i `short()` (qbot_karoo_live), testy `tests/test_karoo_live.py`.
- Wywołanie: pętla radaru w qbot-web (każda nowa klatka). Stan: `qbot_v2.pogoda_alert` (kolumny `src` trener|karoo, `data` jsonb:
  mmh/dur/otwarte), `qbot_v2.karoo_live`. API strony `/api/pogoda/ostrzezenie` (pasek: jazda z Karoo ma pierwszeństwo).
- Zmiana `mcp_server.py` wymaga restartu usługi `q-bot`; `qbot_pogoda_alert`/`qbot_karoo_live` — restartu `qbot-web`.
