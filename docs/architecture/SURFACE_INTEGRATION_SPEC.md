# Nawierzchnia trasy — spec wdrożenia
## QBot + QExt2

*Wersja 1.0 · 2026-06-18*

---

## Cel

Pokazywać w QExt2 nawierzchnię trasy (asfalt / gravel / luźna) w czasie jazdy:
- bieżący segment pod kołem (live advisory: kadencja, moc, pacing),
- lookahead: ile asfaltu / szutru zostało do końca etapu,
- nawierzchnia podjazdów (strategia: asfaltowy vs gravel = inny pacing),
- mnożnik węglowodanów i płynów (~1.05–1.10 na gravelу, ~1.10–1.20 luźna).

---

## Architektura

```
RWGPS (nowa trasa)
  │  webhook → created/updated
  ▼
QBot (olga181)
  │  async pipeline nawierzchni w tle
  │  próbkowanie co ~80–100 m (Overpass, around:20m)
  │  wynik: [{km_start, km_end, surface}] per trasa
  ▼
QBot REST endpoint /surface/{route_id}
  │  prefetch przy załadowaniu danych atlety
  ▼
QExt2 (Karoo)
  │  cache lokalny, klucz = hash polyline bieżącej trasy
  │  lookup w pamięci podczas jazdy (zero kosztu bateryjnego)
  │  fallback → stream RouteGraph surfacetype (jeśli zainstalowany)
  ▼
Pola / advisory:
  - bieżąca nawierzchnia (live)
  - km asfaltu / szutru do końca
  - mnożnik carbsGPerH / fluidLPerH
  - advisory pacing (DEFENSYWNA na gravelowym podjeździe)
```

---

## Decyzje projektowe

| Kwestia | Decyzja | Uzasadnienie |
|---|---|---|
| Źródło primary | QBot prefetch | Dane własne, offline w trakcie jazdy, niezależne od innych appek |
| Źródło fallback | RouteGraph stream `surfacetype` | Już zainstalowany do wizualizacji, zero dodatkowego kosztu |
| Próbkowanie | co 80–100 m | Spójne z RouteGraph (80 m), łapie odcinki >80 m |
| Metoda Overpass | `around:20` per punkt | Dokładne — najbliższa droga do punktu GPS, nie bbox prostokąta |
| Walidacja cache | hash polyline trasy | Deterministyczny, zmiana trasy = natychmiastowe czyszczenie |
| Wpływ na W' | brak | Mierzona moc (Quarq) już zawiera opory nawierzchni — mnożnik = double-count |
| Wpływ na węgle/płyny | mnożnik ~1.05–1.20 | Metaboliczny narzut nie-napędowy (stabilizacja, wibracje) poza mocą |
| Wpływ na W' advisory | przesunięcie progu trybu | DEFENSYWNA/NORMALNA na podstawie nawierzchni + gradientu (warstwa display) |

---

## TODO

### QBot — backend

#### B1. Przepisanie pipeline nawierzchni (Overpass)
- [ ] Zastąpić metodę bbox → `around:20,lat,lon` per punkt
- [ ] Batchowanie: kilka punktów w jednym zapytaniu Overpass (`union`)
- [ ] Próbkowanie co 80–100 m (wzorem RouteGraph)
- [ ] Scal kolejne punkty z identyczną nawierzchnią → segmenty `{km_start, km_end, surface}`
- [ ] Wynik: `paved / gravel / loose` (3 klasy, spójne z RouteGraph)
- [ ] Test porównawczy z RouteGraph na etapie E03 / E05 Toskanii

#### B2. REST endpoint dla QExt2
- [ ] `GET /api/surface/{route_id}` → `[{km_start, km_end, surface}]`
- [ ] Autoryzacja: ten sam Bearer co `/mcp/`
- [ ] Cache w DB (`route_surface_segments`) — nie przeliczaj przy każdym fetchu
- [ ] Odpowiedź gdy brak danych: `{status: "not_ready", eta_sec: N}` (async w toku)

#### B3. Webhook RWGPS
- [ ] Endpoint `POST /rwgps-webhook/` w qbot-api
- [ ] Odpowiedź `200 OK` natychmiast (wymóg RWGPS: <1 s)
- [ ] Async: dla `action=created/updated` + `item_type=route` → odpal pipeline nawierzchni w tle
- [ ] Weryfikacja podpisu HMAC (nagłówek `x-rwgps-signature`)
- [ ] Konfiguracja w RWGPS: API client settings → webhook URL → typy: route created/updated
- [ ] Test: stwórz trasę testową w RWGPS → sprawdź czy pojawia się profil nawierzchni

#### B4. Prefetch w athlete-data
- [ ] Przy fetchu danych atlety (już robi QExt2 przy starcie) → dorzuć profile nawierzchni dla wszystkich etapów aktywnego projektu
- [ ] Format: `{route_id: [{km_start, km_end, surface}]}` per etap
- [ ] Endpoint: rozszerzyć istniejący `/api/athlete` lub osobny `/api/surface/prefetch?project_id=X`

---

### QExt2 — Karoo

#### E1. Cache nawierzchni
- [ ] `SurfaceProfileCache` — mapa `polylineHash → List<SurfaceSegment>`
- [ ] `data class SurfaceSegment(val kmStart: Float, val kmEnd: Float, val surface: SurfaceType)`
- [ ] `enum SurfaceType { PAVED, GRAVEL, LOOSE }`
- [ ] Klucz = `hash(routePolyline)` z `OnNavigationState`
- [ ] Czyszczenie przy każdej zmianie polyline (nowa trasa = nowe dane)
- [ ] Persystencja: `SharedPreferences` lub `AtomicReference` w pamięci (restart appki = refetch)

#### E2. Fetch z QBota przy załadowaniu trasy
- [ ] Hook: `OnNavigationState → NavigatingRoute` → nowa polyline → fetch
- [ ] Mapowanie: nazwa trasy z `NavigationState` → route_id (RWGPS jako wspólne źródło)
- [ ] Fetch `GET /api/surface/{route_id}` — asynchroniczny, nie blokuje jazdy
- [ ] Obsługa `not_ready`: retry po 30 s (max 3 razy)
- [ ] Po fetchu: zapisz do cache, wyczyść stary

#### E3. Fallback na RouteGraph
- [ ] Subskrypcja `TYPE_EXT::karoo-routegraph::surfacetype` (miękka — tylko jeśli zainstalowany)
- [ ] Gdy brak danych QBota w cache → użyj wartości z RouteGraph stream
- [ ] `0.0=paved, 1.0=gravel, 2.0=loose` → mapowanie na `SurfaceType`
- [ ] Logowanie: skąd pochodzi bieżąca wartość (QBot / RouteGraph / brak)

#### E4. Lookup podczas jazdy
- [ ] `fun currentSurface(kmAlongRoute: Float): SurfaceType` — binarny lookup w cache
- [ ] Wołany z istniejącej pętli (co ~1 s, razem z carbsGPerH i innymi)
- [ ] `fun remainingByType(kmAlongRoute: Float): Map<SurfaceType, Float>` — ile km każdego typu do końca

#### E5. Mnożnik węglowodanów i płynów
- [ ] `fun surfaceMultiplier(surface: SurfaceType): Float` → `PAVED=1.0, GRAVEL=1.08, LOOSE=1.15`
- [ ] Wpiąć w `fuelProducer.tick(carbs * multiplier, fluid * multiplier, isMoving)`
- [ ] Tylko gdy `hasRoute=true` (już bramkowane)
- [ ] Wartości mnożników jako stałe w `AthleteDataStore` (edytowalne w SETUP opcjonalnie)

#### E6. Advisory pacing per nawierzchnia
- [ ] Wpiąć `currentSurface()` do `ClimbPacingProducer`
- [ ] Na gravelowym podjeździe: próg trybu DEFENSYWNA obniżony o 5–10 W vs asfaltowy
- [ ] Komunikat advisory (ActiveMessage): „GRAVEL — wygładź moc, siedź"
- [ ] Tylko na podjeździe (gradient > 3%) i powierzchnia = GRAVEL/LOOSE

#### E7. Pole „ile szutru zostało"
- [ ] Nowe pole danych w QExt2: `SurfaceAheadDataType`
- [ ] Wyświetla: `ASF 23km · GRV 18km` (do końca etapu)
- [ ] Alternatywnie: procent szutru pozostałego
- [ ] Widoczne tylko gdy `hasRoute=true` i dane nawierzchni załadowane

---

## Kolejność wdrożenia

```
1. B1 (przepisanie Overpass)          ← fundament, reszta zależy
2. B2 (endpoint REST)                 ← QExt2 może zacząć fetchować
3. E1 + E2 (cache + fetch w QExt2)   ← integracja end-to-end
4. E3 (fallback RouteGraph)           ← odporność
5. E5 (mnożnik węgli/płynów)         ← pierwsza realna wartość dla kolarza
6. B3 (webhook RWGPS)                 ← automatyzacja przed jazdą
7. B4 (prefetch w athlete-data)       ← offline na Karoo
8. E6 (advisory pacing)               ← zaawansowane
9. E7 (pole szutru ahead)             ← zaawansowane
```

---

## Uwagi

- W' depletion: **bez mnożnika nawierzchni** — Quarq mierzy realną moc, opory nawierzchni już w niej są. Mnożnik nawierzchni na W' = double-count (lekcja z build-104).
- Mnożniki węglowodanów (E5) to proxy metabolicznego narzutu poza mocą (stabilizacja, wibracje) — małe wartości celowo.
- RouteGraph pozostaje primary do wizualizacji profilu trasy — QExt2 nie duplikuje tej funkcji.
- Webhook RWGPS nie ma retry (B3) — odpowiedź QBota musi być <1 s, processing async.
