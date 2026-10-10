# QExt2 – ustawienia komunikatów i kolorów pól (QBot SETUP > QExt2)

Cel: wszystkie komunikaty paska KOKPIT 2 (pole „QExt2 KOKPIT 2 nav”) i reguły kolorowania pól Karoo w jednym miejscu,
z możliwością zmiany progów, poziomów (tło), włączania/wyłączania i kolejności (precedencji).

## Etapy
1. **(2026-10-10, gotowe)** Podgląd obecnych reguł – tylko odczyt. Reguły wyciągnięte z kodu QExt2 (build 292):
   `RouteMessageEngine.kt` (kandydaci, progi `RAIN_SOON_MIN=30`, `FUEL_ALERT_G=-30`, `DUSK_WARN_MIN=45`, `NEAR_KM=3`, `POI_NEAR_KM=2`,
   burza 60 min, deszcz ≥40%), `RouteMessageRotator` (20 s / 8 s / 5 s), `EtaEngine.steepDescentAhead` (−6%, 3 km),
   `Kokpit2.kt` (poziomy tła: krytyczny W′/zjazd/HUB-krytyczny, ostrzeżenie deszcz/jedzenie/zmrok/HUB; kolory pól).
2. Edycja i zapis: `POST /api/setup/qext2` → `qbot_v2.app_settings` klucz `qext2_config` (nadpisania na DEFAULTS).
3. QExt2 pobiera konfigurację razem z `/ride-readiness` (start + co 30 min) i stosuje; domyślne = obecne zachowanie.

## Pliki
- `qext2_config.py` – DEFAULTS (MESSAGES w kolejności precedencji, ROTATION, COLORS z opcjami), `view(cur)`.
- `qbot_web.py` – `GET /api/setup/qext2` (restart qbot-web po zmianie).
- `/opt/qbot/web/public/setup.html` – zakładka „QExt2 (Karoo)” (`q2Load` / `q2Render`), poza repo (kopia: scripts/web_mirror.py).

## Zasada
Zmiana reguły w kodzie QExt2 = zaktualizuj DEFAULTS w `qext2_config.py` (inaczej podgląd kłamie).
