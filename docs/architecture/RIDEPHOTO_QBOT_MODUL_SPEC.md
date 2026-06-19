# RidePhoto — moduł QBot (spec poprawiona)

Wersja: 1.1 · 2026-06-12
Zastępuje: RidePhotoAI_podsumowanie.md (koncepcja standalone iOS — odrzucona)

> Status: projekt zaakceptowany, parkowany. Wracamy do implementacji po
> podpięciu Claude do Desktop Commander (SSH na olga181). Decyzje UI niżej
> ustalone: docelowo galeria HTML, iOS opcjonalnie w przyszłości.

---

## 0. Kluczowa zmiana architektoniczna

Oryginalny dokument zakładał aplikację iOS z własnym indeksem. Odwracamy:

```text
iPhone (Shortcuts / później appka)
  → wysyła: metadane zdjęć + downscale JPEG
QBot serwer (olga181)
  → matching do etapu/jazdy (FIT track + planning_facts)
  → AI (Albert/Gemini): tagi, score, opis, delete_candidate
  → DB: qbot_v2.ride_photo*
  → intenty: zapytania, selekcja, draft Instagram
Apple Photos
  → pozostaje jedyną biblioteką oryginałów (bez zmian, bez edycji)
```

Serwer nigdy nie trzyma oryginałów — tylko downscale (max 1600px, EXIF
wycięty poza datą/GPS) + metadane.

**Wycięte z oryginalnej koncepcji:**
- nieniszczące edycje PHContentEditingOutput/PHAdjustmentData (sekcje 8–11)
  — wymaga pełnej natywnej appki; PHAdjustmentData nadpisuje (nie komponuje)
  wcześniejsze edycje użytkownika z Photos.app; out of scope,
- własny pipeline korekt obrazu — korekty tylko jako eksportowe kopie
  tymczasowe pod publikację (Pillow: ekspozycja/kontrast/crop),
- Instagram Graph API (MVP 5) — share sheet wystarcza, API wymaga konta
  Business/Creator + App Review.

---

## 1. Ingest — Skrót iOS (MVP, bez appki)

Skrót "QBot: zdjęcia z jazdy":
1. Wybór zdjęć (picker) lub "zdjęcia z dziś".
2. Dla każdego: pobierz datę, GPS, zmniejsz do 1600px JPEG q80.
3. POST na nowy endpoint `/mcp/action` → `ridephoto_ingest`:

```json
{
  "action": "ridephoto_ingest",
  "args": {
    "photos": [
      {
        "asset_local_id": "ABC-123/L0/001",
        "captured_at": "2026-06-10T14:32:11+02:00",
        "lat": 43.4521, "lon": 11.1234,
        "sha256": "…",
        "content_b64": "…(JPEG 1600px)…"
      }
    ],
    "project_hint": "tuscany_2026"
  }
}
```

Uwagi:
- `captured_at` zawsze z offsetem; serwer normalizuje do UTC
  (FIT-y są w UTC — bez tego matching się rozjeżdża).
- `sha256` liczony z wysyłanego JPEG — klucz deduplikacji i klucz stabilny
  zamiast `asset_local_id` (localIdentifier jest niestabilny między
  urządzeniami i po resync iCloud).
- Zapis pliku: `/opt/qbot/artifacts/projects/{project_id}/photos/{sha256}.jpg`
  (ścieżka `projects/` — znany working write path; `wip/` ma permission denied).
- Limit batcha: 10 zdjęć / request (timeout Cloudflare), Skrót pętluje.

---

## 2. Schemat DB (`qbot_v2`)

```sql
CREATE TABLE qbot_v2.ride_photo (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sha256          text UNIQUE NOT NULL,
    asset_local_id  text,
    project_id      text,                 -- np. 'tuscany_2026'
    stage_no        int,                  -- etap, NULL = nieprzypisane
    activity_ref    text,                 -- FIT filename / Garmin activity id
    captured_at_utc timestamptz NOT NULL,
    lat             double precision,
    lon             double precision,
    dist_to_track_m double precision,     -- NULL gdy brak GPS
    km_along_route  double precision,
    match_method    text NOT NULL,        -- 'time_gps'|'time_only'|'day_bbox'|'manual'
    confidence      real NOT NULL,        -- 0..1
    file_path       text NOT NULL,
    created_at      timestamptz DEFAULT now()
);

CREATE TABLE qbot_v2.ride_photo_ai (
    photo_id        uuid PRIMARY KEY REFERENCES qbot_v2.ride_photo(id),
    caption         text,
    tags            text[],
    quality_score   real,
    phash           text,                 -- imagehash, deduplikacja serii
    duplicate_group uuid,
    status          text DEFAULT 'KEEP',  -- KEEP|HIGHLIGHT|DELETE_CANDIDATE|DUPLICATE|PRIVATE
    status_reason   text,
    selected_insta  boolean DEFAULT false,
    analyzed_at     timestamptz
);
```

Bez tabeli `Ride` — jazdy już istnieją (FIT/Garmin/planning_facts).
`stage_no` + `project_id` wiąże zdjęcie z istniejącą strukturą etapów.

---

## 3. Matching (serwer, deterministyczny)

Kolejność prób, pierwsza pasująca wygrywa:

1. **time_gps** (confidence 0.95): `captured_at_utc` w oknie jazdy ±30 min
   ORAZ odległość do **faktycznego śladu FIT** < 500 m.
   Ślad FIT, nie planowana trasa RWGPS — plan i wykonanie się różnią
   (case E07: 74 km plan vs 57.6 km nowa trasa).
2. **day_bbox** (0.7): zdjęcie poza oknem jazdy, ale w dniu etapu
   i w bbox trasy dnia + bufor 5 km. Łapie kolacje, noclegi, zwiedzanie
   po zjeździe — w bikepackingu to większość "dobrych" zdjęć.
3. **time_only** (0.5): brak GPS w EXIF, czas w oknie jazdy ±30 min.
4. **manual** (1.0): przez `ridephoto_assign` (akcja GPT).

Implementacja: `tools/ride_photos.py`; odległość do śladu — istniejący
kod z `rwgps_route_profile_sample.py` (parsowanie GPX/FIT już jest).
Ślad FIT: `/opt/qbot/app/outgoing/michal/hammerhead_originals/`.

---

## 4. Pipeline AI (Albert / Gemini)

Po ingest, asynchronicznie lub na żądanie (`ridephoto_analyze`):

1. **pHash** (`imagehash`, bez AI): grupowanie serii/duplikatów —
   w grupie tylko najostrzejsze idzie do AI, reszta = DUPLICATE.
2. **Gemini 2.5 Flash** (przez istniejący `albert.py`,
   `tool_choice='required'`), jeden call na zdjęcie, prompt zwraca JSON:
   `{caption, tags[], quality_score, status, status_reason}`.
   Tagi ze słownika zamkniętego: gravel, rower, widok, jedzenie, nocleg,
   podjazd, nawierzchnia, awaria, dokument, selfie, ludzie, przypadkowe.
3. **DELETE_CANDIDATE** heurystyki przed AI (taniej): blur (variance of
   Laplacian, OpenCV/Pillow), histogram (zbyt ciemne/przepalone).
4. **PRIVATE**: tagi twarz/dokument/ekran → status PRIVATE,
   wykluczone z draftów Instagram domyślnie.

Prywatność: do Gemini idzie tylko downscale bez EXIF; zdjęcia PRIVATE
nie idą do AI ponownie po oznaczeniu.

---

## 5. Akcje (action_execute)

Nowe wpisy — **w OBU allowlistach** (`qbot_mcp_adapter.py`
ORAZ `qbot3/adapters/mcp_adapter.py`, listy canonical + LLM-first):

```python
"ridephoto_ingest",    # batch metadane+JPEG
"ridephoto_analyze",   # uruchom AI dla projektu/etapu
"ridephoto_assign",    # ręczne przypisanie sha256→etap
"ridephoto_status",    # zmiana statusu (KEEP/DELETE_CANDIDATE/…)
"ridephoto_insta_draft"  # generuj draft wpisu dla etapu
```

Po zmianie schematu Custom GPT: Bearer token resetuje się — wpisać ręcznie.

---

## 6. Intenty (`INTENT_KEYWORDS`)

Frazy wielowyrazowe PRZED krótkimi; sprawdzić `_resolve_intent(q)`
lokalnie przed patchem; dodać early-exit guard w `_detect_domains()`
żeby "zdjęcia etap X" nie wpadało w `multi_intent`:

```python
# PRZED ogólnymi keywordami trip/etap:
(["zdjęcia etap", "zdjęcia z etapu", "fotki etap"], "ridephoto_list"),
(["najlepsze zdjęcia", "highlighty zdjęć"], "ridephoto_best"),
(["zdjęcia do usunięcia", "słabe zdjęcia"], "ridephoto_delete_candidates"),
(["wpis insta", "wpis na instagram", "draft instagram"], "ridephoto_insta"),
```

Regex etapu: istniejący wzorzec z odmianą
`\b(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)\b`.

Odpowiedzi tekstowe są warstwą MVP (GPT nie renderuje miniatur z serwera),
ale **docelowy UI to galeria HTML** — bez niej nie ma sensownego wejścia
w przeglądanie zdjęć, selekcję i draft Instagram. Tekst zostaje jako szybki
interfejs zapytań, HTML jest interfejsem pracy ze zdjęciami.

Tekstowo (MVP):
"Etap 3: 14 zdjęć (12 time_gps, 2 day_bbox) · 3 HIGHLIGHT ·
2 DELETE_CANDIDATE (blur) · 1 grupa duplikatów (4 szt.)".

Galeria HTML (docelowo, od MVP 4):
- generowana do `/opt/qbot/artifacts/projects/{project}/photos/index.html`,
  serwowana przez istniejący publiczny serwis (port 20181 / Cloudflare),
  za tokenem w URL,
- przepływ: lista etapów → miniatury etapu → podgląd → selekcja
  (HIGHLIGHT / DELETE_CANDIDATE) → ekran "draft Instagram",
- miniatury z downscale na serwerze (już mamy 1600px, generujemy 400px),
- akcje selekcji wołają `/mcp/action` (`ridephoto_status`,
  `ridephoto_insta_draft`) — HTML jako cienki frontend nad istniejącymi
  akcjami, bez osobnego backendu,
- statyczny HTML + minimalny JS (fetch do `/mcp/action`); bez frameworka.

**iOS (przyszłość, opcjonalnie):** natywna appka PhotoKit tylko jeśli Skrót
zacznie uwierać przy ingest. Rola appki = kontroler QBota (auto-sync zdjęć,
wygodniejszy ingest), a nie osobny mózg — matching i AI zostają na serwerze.

---

## 7. Draft Instagram

`ridephoto_insta_draft etap=6`:
1. Zdjęcia: HIGHLIGHT z etapu, max 8, bez PRIVATE, sort km_along_route.
2. Metryki z `planning_facts` + Garmin (dystans, przewyższenie, nawierzchnia).
3. Gemini składa tekst (format jak w oryginalnej sekcji 13).
4. Wynik: tekst + lista sha256 → użytkownik publikuje przez share sheet.

**Uwaga:** sam generator tekstu (bez zdjęć) nie wymaga niczego z tego
modułu — dane już są w planning_facts. Można wdrożyć od razu jako
samodzielny intent.

---

## 8. Kolejność MVP (zrewidowana)

| # | Zakres | Zależności |
|---|--------|-----------|
| 0 | `instagram_draft` tekstowy (bez zdjęć) | nic — planning_facts już są |
| 1 | DB + `ridephoto_ingest` + Skrót iOS + matching | FIT parser (jest) |
| 2 | pHash + heurystyki blur/histogram + intenty list/delete_candidates | MVP 1 |
| 3 | Gemini: tagi/caption/score + `ridephoto_best` | MVP 2 |
| 4 | Galeria HTML (lista→miniatury→podgląd→selekcja) + `ridephoto_insta_draft` ze zdjęciami | MVP 3 |
| — | Natywna appka iOS (PhotoKit, auto-sync, kontroler QBota) | tylko jeśli Skrót uwiera |
| — | Nieniszczące edycje w Photos | wycięte |
| — | Instagram Graph API | wycięte |

## 9. Smoke test MVP 1

```bash
# po deploy + systemctl restart qbot-api
curl -s -X POST https://qbot.cytr.us/mcp/action -H "Authorization: Bearer $TOK" \
  -d '{"action":"ridephoto_ingest","args":{"photos":[{...1 zdjęcie testowe z Toskanii...}]}}'
# oczekiwane: stage_no przypisany, match_method='time_gps', plik na dysku
psql: SELECT stage_no, match_method, confidence FROM qbot_v2.ride_photo;
```

---

## 10. UI HTML — koncepcja

Cel: minimalny interfejs do obsługi całego modułu z przeglądarki (iPhone/iPad/
desktop). Bez frameworka, bez build-stepu, bez osobnego backendu. Statyczny
HTML + waniliowy JS, który woła istniejące endpointy QBota. Generowany na
serwer, serwowany przez publiczny serwis (port 20181 / Cloudflare) za tokenem.

### 10.1 Zasada

```text
Przeglądarka (HTML+JS)
   │  GET  /ridephoto/{project}/?t={token}   → strona (statyczny HTML)
   │  GET  /ridephoto/{project}/data.json    → stan (etapy, zdjęcia, statusy)
   │  GET  /ridephoto/thumb/{sha256}.jpg      → miniatura 400px
   │  GET  /ridephoto/photo/{sha256}.jpg      → podgląd 1600px
   │  POST /mcp/action                         → akcje (status, draft)
   ▼
QBot (te same akcje co GPT — UI nie dostaje własnego API)
```

UI nigdy nie ma własnej logiki biznesowej — każde kliknięcie to wywołanie
istniejącej akcji `action_execute`. To samo źródło prawdy co GPT.

### 10.2 Strony (jeden plik, widoki przełączane w JS)

```text
[1] Lista etapów
    - kafelki: etap, miniatura okładki, licznik zdjęć,
      badge HIGHLIGHT / DELETE_CANDIDATE
    - klik → widok [2]

[2] Galeria etapu
    - siatka miniatur (lazy-load), badge statusu na rogu
    - filtr: wszystkie | highlighty | do usunięcia | duplikaty
    - klik miniatury → widok [3]

[3] Podgląd zdjęcia
    - duży obraz (1600px), pod nim: tagi, quality_score, match_method,
      km_along_route, caption
    - przyciski statusu: ★ HIGHLIGHT · ✓ KEEP · 🗑 DELETE_CANDIDATE · 🔒 PRIVATE
    - klik = POST ridephoto_status, optymistyczny update + refetch

[4] Draft Instagram (per etap)
    - wybrane HIGHLIGHT (drag do zmiany kolejności karuzeli)
    - wygenerowany tekst + hashtagi (edytowalne pole)
    - przycisk "Generuj" → POST ridephoto_insta_draft
    - przycisk "Kopiuj" / "Pobierz zdjęcia" (share sheet po stronie iOS)
```

### 10.3 Kontrakt danych (`data.json`)

Generowany przez `ridephoto_ui_data` (read-only akcja) albo statycznie przy
każdej zmianie statusu. Jeden payload zasila wszystkie widoki:

```json
{
  "project_id": "tuscany_2026",
  "generated_at": "2026-06-12T18:00:00Z",
  "stages": [
    {
      "stage_no": 6,
      "title": "Pienza → Monteriggioni",
      "cover_sha256": "…",
      "counts": {"total": 31, "highlight": 6, "delete": 4, "dup_groups": 2},
      "photos": [
        {
          "sha256": "…",
          "status": "HIGHLIGHT",
          "tags": ["gravel", "widok"],
          "quality_score": 0.84,
          "km_along_route": 41.2,
          "match_method": "time_gps",
          "duplicate_group": null
        }
      ]
    }
  ]
}
```

### 10.4 Bezpieczeństwo / serwowanie

- Token w query (`?t=`) — ten sam mechanizm co reszta publicznych zasobów;
  bez tokenu 403. Token per-projekt, odwoływalny.
- Zdjęcia PRIVATE: domyślnie ukryte w galerii (filtr opt-in), nigdy w okładkach
  ani w draftach IG.
- Brak zapisu do Apple Photos z UI — UI operuje wyłącznie na indeksie QBota.
  Realne usunięcie zdjęcia zostaje po stronie iPhone'a (ręcznie).
- Endpoint statyczny: HTML i JSON generowane do
  `/opt/qbot/artifacts/projects/{project}/photos/`; miniatury z cache 400px.

### 10.5 Szkielet (do MVP 4, jeden plik)

```html
<!doctype html><meta charset=utf-8><meta name=viewport
  content="width=device-width,initial-scale=1">
<title>RidePhoto · {project}</title>
<style>
  body{font:15px system-ui;margin:0;background:#111;color:#eee}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:4px;padding:4px}
  .grid img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px}
  .badge{position:absolute;top:4px;right:4px;font-size:11px;padding:1px 5px;border-radius:8px}
  .hl{background:#d9a300}.del{background:#a33}
  header{padding:10px 14px;font-weight:600;position:sticky;top:0;background:#111}
</style>
<header id=crumb>RidePhoto · {project}</header>
<div id=app></div>
<script>
const TOKEN = new URLSearchParams(location.search).get('t');
const API = '/mcp/action';
let DATA = null;

async function load(){ DATA = await (await fetch('./data.json?t='+TOKEN)).json(); renderStages(); }
function thumb(sha){ return `/ridephoto/thumb/${sha}.jpg?t=${TOKEN}`; }

function renderStages(){ /* widok [1] — kafelki etapów */ }
function renderStage(no){ /* widok [2] — siatka miniatur + filtr */ }
function renderPhoto(sha){ /* widok [3] — podgląd + przyciski statusu */ }

async function setStatus(sha, status){
  await fetch(API, {method:'POST',
    headers:{'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},
    body: JSON.stringify({action:'ridephoto_status',
      args:{sha256:sha, status}})});
  await load();                       // refetch = jedno źródło prawdy
}

async function genDraft(no){
  const r = await fetch(API, {method:'POST',
    headers:{'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},
    body: JSON.stringify({action:'ridephoto_insta_draft', args:{stage_no:no}})});
  /* pokaż tekst + hashtagi */
}
load();
</script>
```

Uwaga: token UI a Bearer GPT to dwie różne rzeczy — UI dostaje własny,
ograniczony do akcji `ridephoto_status` / `ridephoto_insta_draft` /
`ridephoto_ui_data`. Nie wystawiać pełnego Bearera GPT w przeglądarce.

### 10.6 Nowe akcje dla UI

Dodać do obu allowlist (j.w.):
```python
"ridephoto_ui_data",   # read-only, buduje data.json
"ridephoto_ui_render", # generuje statyczny index.html do katalogu projektu
```
Miniatury/podglądy: lekki route w serwisie publicznym
(`/ridephoto/thumb/{sha}.jpg`) czytający z cache na dysku — nie przez
`action_execute` (binarne, nie JSON).
