# Jeden silnik pogodowy QBota — spis i plan (E0, 2026-10-14)

**Decyzja Michała (14.10.2026): jeden silnik pogodowy dla wszystkich modułów.**

## Stan wyjściowy — 6 równoległych ścieżek
| Ścieżka | Pliki | Źródło / wybór modelu | Mocne strony |
|---|---|---|---|
| Pogoda (punkt) | `qbot_pogoda*.py`, `qbot_radar*.py`, `qbot_eps_verif.py` | Open-Meteo, **model wg sprawdzalności (IMGW)** per parametr × doba; zespół ICON-EU-EPS; radar OPERA; mapy ICON-EU (DWD) | radar + ostrzeżenia, szansa z 40 wariantów, warunki drogi (lód, mgła, błoto, rosa), charakter dnia (CAPE/LI), weryfikacja |
| Silnik METEO tras (Analiza trasy, Planer) | `qbot3/routes/route_meteo_engine.py`, `route_weather_models.py`, `route_utci.py`, `ride_thermal.py`, `qbot_wbgt_tools.py`, `route_shade_*`, `route_climate.py`, `outfit_*` | Open-Meteo; **model = najdrobniejsza siatka sięgająca daty** + 6 modeli i rozrzut ECMWF ENS; ERA5 dla dat poza prognozą | UTCI (wiatr efektywny z pędem), „na rowerze” (kalibracja Karoo), WBGT Liljegren z cieniem (WorldCover), burze NO-GO, wiatr vs kierunek + osłona terenu, słońce/UV, klimat ERA5 |
| Trener | `qbot_trener_engine.py` (forecast, wx_bad), `qbot_trener_weather.py`, `qbot_trener_stats.py` | Open-Meteo (własne pobieranie) | okna jazdy, poranna korekta planu, progi z historii |
| Powiadomienia | `qbot_notif.live_weather` | Open-Meteo | — |
| Raport poranny / stare narzędzia | `event_morning_report.py`, `qbot_integration_tools.py`, `qbot_legacy_parity_tools.py`, `qbot_telegram_tools.py`, narzędzie Alberta `weather_forecast` | **OpenWeatherMap** | — |
| Planer: tabela modeli | `qbot_web.api_planer_pogoda`, `_pogoda_*` | przez silnik METEO tras | ocena zgodności modeli (Albert) |

## Znalezione i naprawione w E0
- **Godziny wartości „z poprzedniej godziny”** (Open-Meteo: opad, szansa opadu, porywy = przedział T−1..T):
  - silnik tras interpolował liniowo między pełnymi godzinami → opad ok. **30 min za wcześnie** (przejazd 14:30 dostawał pół deszczu z 13–14);
    teraz interpolacja po środkach przedziałów (T−30 min) dla opadu, szansy opadu i porywów;
  - Pogoda: opad poprawiony wcześniej (b8ba5d4), porywy teraz też z T+1 dla godziny T..T+1.
  - Do sprawdzenia w E4: Trener (`forecast`, `window_wx`), `live_weather`.

## Plan
- **E1** — wydzielenie rdzenia (`qbot_wx`): pobieranie + cache + poprawne godziny + radar + zespół + ERA5; Pogoda pierwsza na rdzeniu.
- **E2** — silnik tras czyta dane z rdzenia (fizyka bez zmian); test zgodności stary/nowy na zapisanych trasach.
- **E3** — wspólna fizyka odczucia: UTCI + „na rowerze” + WBGT (lato) także dla punktu (Pogoda, Okno jazdy); warunki drogi i charakter dnia
  także dla tras. Jedna reguła wyboru modelu: sprawdzalność, a gdzie jej brak (zagranica, daleko w przód) — najdrobniejsza siatka + rozrzut.
- **E4** — Trener, powiadomienia, raport poranny, Albert na rdzeniu; usunięcie OpenWeatherMap.
