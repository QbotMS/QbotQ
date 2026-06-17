# Krok 3b — status 2026-06-17

## Zrealizowane
- Commit a49e019: przelacznik QBOT_ROUTES_VIA_ALBERT + _albert_to_planner_shape (flaga OFF=default)
- Regresja offline: 5 intentow, profil/podjazdy/rwgps-recent = identyczne wyniki, POI Albert lepszy (liczniki inline), nawierzchnia drobna roznica agregacji
- .env.local: QBOT_ROUTES_VIA_ALBERT=1 (flip na prod 2026-06-17)
- Live smoke: bilans (keyword fast-path), ostatnie trasy (albert), podjazdy (albert) — wszystko OK

## Rollback
grep -n QBOT_ROUTES_VIA_ALBERT .env.local  # usun linie
systemctl restart qbot-api

## Nastepny krok
Krok 5 sprzatanie: usun core/planner.py (importy lokalne, brak crashu na usunięcie),
zaktualizuj testy patchujace plan_routes, zredukuj keyword router ~250->~20 dla domen zamknietych.
