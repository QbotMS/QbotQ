# QExt2 – ustawienia komunikatów i kolorów pól (QBot SETUP > QExt2)

Cel: wszystkie komunikaty paska KOKPIT 2 (pole „QExt2 KOKPIT 2 nav”) i reguły kolorowania pól Karoo w jednym miejscu,
z możliwością zmiany progów, poziomów (tło), włączania/wyłączania i kolejności (precedencji).

## Etapy
1. **(2026-10-10, gotowe)** Podgląd obecnych reguł – tylko odczyt. Reguły wyciągnięte z kodu QExt2 (build 292):
   `RouteMessageEngine.kt` (kandydaci, progi `RAIN_SOON_MIN=30`, `FUEL_ALERT_G=-30`, `DUSK_WARN_MIN=45`, `NEAR_KM=3`, `POI_NEAR_KM=2`,
   burza 60 min, deszcz ≥40%), `RouteMessageRotator` (20 s / 8 s / 5 s), `EtaEngine.steepDescentAhead` (−6%, 3 km),
   `Kokpit2.kt` (poziomy tła: krytyczny W′/zjazd/HUB-krytyczny, ostrzeżenie deszcz/jedzenie/zmrok/HUB; kolory pól).
2. **(2026-10-10, gotowe)** Edycja i zapis: `POST /api/setup/qext2` (body w postaci `compact()`; `{"reset":true}` = domyślne) →
   `qbot_v2.app_settings` klucz `qext2_config`. `effective()` nakłada zapis na DEFAULTS i pomija nieznane id/klucze/opcje
   (walidacja: typ jak wartość domyślna, poziom z LEVELS, komunikat z centrali zawsze pierwszy i zawsze włączony).
   Front: ▲▼ kolejność, włącz/wyłącz, poziom (tło), progi, reguła koloru; pomarańczowa ramka = inna niż domyślna.
   `for_karoo(cur)` = gotowa postać dla Karoo (etap 3).
3. **(2026-10-10, gotowe)** `/ride-readiness` (qbot-api) zwraca `qext2Config` = `for_karoo()`. QExt2 (build ≥ 293):
   `QExt2PrimaryExtension` zapisuje go (`AthleteDataStore.saveQext2Config`) i ładuje do `kokpit/Kokpit2Config.kt`.
   Stosowane w: `RouteMessageEngine.candidates` (wł/wył, progi, kolejność `sortByOrder`), `RouteMessageRotator` (rotacja),
   `Kokpit2NavRenderer.drawMsg` (poziom tła), `Kokpit2InstRenderer` (moc/W′/tętno/prędkość), `Kokpit2NavRenderer` (wiatr, manewr, ETA),
   `RideDataAggregator.getSteepDescentAhead` (próg i zasięg zjazdu). Zmiany docierają przy pobraniu formy dnia (start QExt2 / ponowienia);
   w SETUP na Karoo linia „Komunikaty i kolory z QBota: <data zapisu | domyślne>”, w ride_log `QEXT2_CONFIG updated=…`.

## Pliki
- `qext2_config.py` – DEFAULTS (MESSAGES w kolejności precedencji, ROTATION, COLORS z opcjami), `view(cur)`.
- `qbot_web.py` – `GET /api/setup/qext2` (restart qbot-web po zmianie).
- `/opt/qbot/web/public/setup.html` – zakładka „QExt2 (Karoo)” (`q2Load` / `q2Render`), poza repo (kopia: scripts/web_mirror.py).

## Zasada
Zmiana reguły w kodzie QExt2 = zaktualizuj DEFAULTS w `qext2_config.py` (inaczej podgląd kłamie).
