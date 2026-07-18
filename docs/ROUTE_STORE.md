# QBot — Route store: wersjonowanie, retencja, czyszczenie i narzędzia Alberta

_Utworzono 2026-07-01. Dokumentuje zmiany z sesji „route store cleanup/repair + narzędzia tras Alberta". Żywy system wygrywa — weryfikuj na kodzie._

## 1. Po co to jest
Trasa (RWGPS) może być wielokrotnie modyfikowana i wielokrotnie przeliczana. Ten obszar pilnuje, żeby:
- każda wersja geometrii trasy miała własny, spójny zestaw danych,
- stare wersje nie puchły w nieskończoność (retencja),
- dało się bezpiecznie skasować całą trasę (czyszczenie),
- Albert mógł na życzenie użytkownika wypisać / przeliczyć / skasować trasę.

Zasada nadrzędna: **trasę zawsze można ponownie pobrać z RWGPS**, dlatego kasowanie przez czat jest dozwolone (z zabezpieczeniem).

## 2. Model danych (skrót)
- `route_artifacts` — jeden wiersz na trasę (plik GPX ma STAŁĄ nazwę `rwgps_<id>.gpx`, upsert po `artifact_path`).
- `route_base` — jeden wiersz na `route_version_key` (upsert po `route_id + route_version_key`). Nowy klucz = NOWY wiersz bazowy. Przy zapisie nowej AKTYWNEJ wersji poprzednie wersje tego `route_id` są dezaktywowane (`status='disabled'`) — dokładnie JEDNA `active` na `route_id` (patrz 2a). Czytelnicy i tak biorą najnowszą po `route_modified_at`.
- `route_version_key` — odcisk (sha256) geometrii (sha256+dystans+track_points), liczony w `qbot3/routes/route_base_store` / `qbot_route_tools`.
- Warstwy child kasowane kaskadowo z `route_base`: `route_axis_segments`, `route_climb_events`, `route_elevation_samples`, `route_landcover_layer`, `route_poi_layer`, `route_attraction_run` + `route_attraction_layer`, `route_shade_layer`, `route_surface_layer`, `route_analysis_run`, `route_precompute_jobs`.
- Warstwy child kasowane kaskadowo z `route_artifacts`: `route_frames`, `route_frame_weather`, `route_parse_results`, `route_surface_profiles` → `route_surface_segments`.
- `ride_frames.route_artifact_id` = ON DELETE SET NULL (przejazdy zostają, tylko odpięte).
- Surówka eksportu RWGPS: tabela `qbot_v2.artifacts` (`idempotency_key` typu `rwgps_export:<id>:<fmt>:<data>`).

## 2a. Jedna aktywna wersja na trasę (2026-07-03)
Klucz konfliktu upsertu to `(route_id, route_version_key)`, więc każda nowa geometria to NOWY
wiersz `route_base`. Wcześniej stary wiersz zostawał `status='active'` → narastały 2–3 „aktywne”
wersje tej samej trasy.

Poprawka (`route_base_store._upsert_route_base`, commit `e334cb7`): po zapisie nowej wersji,
w TEJ SAMEJ transakcji (`ensure_route_base` → `conn.transaction()`):
`UPDATE qbot_v2.route_base SET status='disabled' WHERE route_id=%s AND route_base_id<>%s AND status='active'`.
Dzięki temu jest dokładnie JEDNA `active` na `route_id`.

- Dozwolone statusy (CHECK `route_base_status_chk`): `active`, `stale`, `disabled`, `failed`.
  Dla wygaszonej-ale-poprawnej starej wersji użyto `disabled` (nie `stale` — `stale` = zły parse,
  patrz `route_status` w writerze: `active` gdy `looks_valid`, inaczej `stale`).
- `route_base.status` NIE jest źródłem wyboru wersji: raport/geometria/nawierzchnia biorą wersję po
  `route_id` + `ORDER BY route_modified_at DESC`; `_fetch_active_route_version` działa na `route_artifacts`.
  Dlatego dezaktywacja starych jest bezpieczna (nic jej nie czyta do selekcji).
- Jednorazowe sprzątnięcie istniejących dubli wykonane (najnowsza per `route_id` zostaje `active`,
  starsze → `disabled`): 55864231 3→1, 55798129 2→1, 55918401 2→1.

## 3. Wersjonowanie pliku GPX (archiwizacja)
`tools/rwgps/client.py` → `_archive_previous_gpx_version()` (wołane tuż przed nadpisaniem pliku):
- aktywny plik ZAWSZE ma stałą nazwę `rwgps_<id>.gpx` (wszystkie ~9 miejsc czytających go działa bez zmian),
- gdy treść GPX się ZMIENIŁA, poprzednia wersja jest archiwizowana jako `rwgps_<id>_<sha10>.gpx`,
- brak zmiany albo plik inny niż GPX → nic nie archiwizuje.

Decyzja: wybrano „stała nazwa aktywnego + archiwum starych + przeliczanie starszej = promote+recompute" zamiast zmieniania nazw po sha (to dotknęłoby ~9 żywych plików, w tym narzędzia Alberta — zbyt ryzykowne).

## 4. Retencja wersji
`qbot3/routes/route_versions.py`:
- `list_all_routes()` — lista tras w bazie,
- `list_route_versions(route_id)` — wersje danej trasy,
- `prune_route_versions(route_id, keep=3, confirm=False)` — zostawia 3 najnowsze wersje `route_base` (kaskada) + 3 najnowsze pliki archiwalne; aktywny plik nigdy nie kasowany; domyślnie dry-run.

CLI: `scripts/route_versions_cli.py` (lista wszystkich / jednej, `--prune --keep N --confirm`).

Auto-retencja: `qbot3/routes/route_precompute_orchestrator.py` — po udanym precompute woła `prune_route_versions(route_id, keep=3, confirm=True)` w try/except; wynik dołączany jako `retention` do zwrotki. To jeden punkt styku (obejmuje ścieżkę Telegram-yes i Albert).

## 5. Czyszczenie całej trasy (purge)
`scripts/route_store_purge.py` → `purge_route(route_id, confirm=False)`:
- **dwustopniowo**: `confirm=False` (domyślnie) = podgląd (DRY_RUN, liczy co zniknie, nic nie kasuje); `confirm=True` = realne skasowanie,
- kasuje `route_base` + `route_artifacts` (kaskady) + surówkę (`artifacts` po `idempotency_key LIKE 'rwgps_export:<id>:%'`) + pliki na dysku pod `/opt/qbot/artifacts`,
- NOOP gdy trasy nie ma.

Kanał admin/DEV: narzędzie `dev_route_store_purge` w `/root/qbot-dev-mcp/server.py` (POZA repo aplikacji; wymaga restartu `qbot-dev-mcp`).

## 6. Narzędzia Alberta (czat)
Rejestr: `qbot3/tool_registry.py`; prompt: `qbot3/llm/albert.py` (twarda reguła: zmiana narzędzia = aktualizacja promptu w tym samym kroku).
- `route_list` (odczyt) — wypisuje trasy w bazie / stan wersji.
- `route_recompute` (write) — przeliczenie AKTYWNEJ wersji (woła `ensure_route_precompute`). Starsza wersja = najpierw promote+recompute (odłożone).
- `route_attractions` (write) — włącza/wyłącza osobną kanoniczną warstwę atrakcji. Wikipedia/Wikidane są pierwszym sitem, a Google lokalizuje i wspiera ranking kandydatów przechodzących wspólną bramkę semantyczną. Wynik publikuje się atomowo i tylko przy gęstości co najmniej 10 kandydatów/100 km. Operacja nie przelicza `route_poi_layer`, więc nie rusza sklepów, jedzenia ani wody. Analiza Trasy i Planer czytają ten sam opublikowany ranking; bez migracji lub pełnego wyniku działają na starym źródle.
- `route_delete` (write, **dwustopniowo**) — bez `confirm` zwraca PODGLĄD; realne kasowanie dopiero po `confirm=true` (po wyraźnej zgodzie użytkownika). Prompt wymusza: najpierw podgląd, pytanie, potem kasowanie.

## 7. Trzy warstwy bezpieczeństwa zapisów (otwarte WĄSKO dla tras)
System celowo blokuje zapisy/kasowanie z czatu na trzech poziomach. Dla operacji na trasach otwarto je wąsko; masowe kasowanie i inne destrukcje dalej zablokowane.
1. **Strażnik destrukcji** — `qbot3/agent_runtime.py` `_is_destructive_query` + wyjątek `_looks_like_route_delete_request` (pojedyncza trasa przechodzi do Alberta; „skasuj wszystkie trasy" / mass-delete BLOKOWANE; wzorzec analogiczny do nutrition-delete).
2. **Whitelista realnych zapisów** — `qbot3/agent_runtime.py` `_execute_single_tool` i `_execute_real_write_tool`: dopisane `route_recompute`, `route_delete` (ścieżka generyczna jak `rwgps_route_import_gpx` / `route_poi_analyze`). Bez tego zapis kończył się nieszkodliwym „draft".
3. **Allowlista walidatora** — `qbot3/safety.py` `_ACTION_ALLOWLIST` (przez `_LEGACY_EXTRA_ACTIONS`): dopisane `route_recompute`, `route_delete`. Bez tego `validate()` odrzucał je jako „not in allowlist".

Zabezpieczenie kasowania trzyma dwustopniowy `route_delete` (podgląd → confirm).

## 8. Weryfikacja na żywo (2026-07-01)
- `route_list`: „pokaż wszystkie trasy" → Albert zwrócił 34 trasy.
- `route_delete` (dwustopniowo): „skasuj trasę 55798129" → Albert pokazał pełny podgląd (baza 1, oś 1423, wysokości 1424, warstwy, plik) i poprosił o „tak/kasuj"; NIC nie skasowane.
- `route_recompute`: wykonuje się realnie (nie „draft").

## 9. Pliki
- `scripts/route_store_purge.py` (nowy), `scripts/route_versions_cli.py` (nowy), `qbot3/routes/route_versions.py` (nowy).
- `tools/rwgps/client.py`, `qbot3/routes/route_precompute_orchestrator.py`, `qbot3/tool_registry.py`, `qbot3/llm/albert.py`, `qbot3/agent_runtime.py`, `qbot3/safety.py`.
- Poza repo: `/root/qbot-dev-mcp/server.py` (`dev_route_store_purge`).
