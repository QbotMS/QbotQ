# Planer Wypraw — atrakcje i dzienne trasy QBot

_Aktualizacja: 2026-07-18. Stan produkcyjny po wdrożeniu wspólnego mechanizmu atrakcji i eksportu wyprawy na dni._

## 1. Cel i preferencje

Planer przygotowuje jedną długą trasę, dzieli ją na dni, a każdy dzień trafia później osobno do Analizy Trasy. Wyszukiwanie atrakcji ma być wykonane raz dla całej wyprawy, nie osobno dla każdego dnia.

Założenia kalibracji:

- około 10–15 kandydatów na 100 km do decyzji TAK/NIE;
- około 2–3 rekomendacji na 100 km;
- wyjątkowe miejsca do około 2 km od śladu mogą wejść do selektora;
- preferowane są zamki, pałace, historyczne miasta i rynki, fortyfikacje, zabytki techniki, skanseny i widoczne pozostałości archeologiczne;
- muzea i przyroda mają niższy priorytet;
- zwykłe kościoły, kapliczki, pomniki, zoo i parki rozrywki są odrzucane;
- obiekt sakralny przechodzi tylko jako wyjątkowy zabytek;
- postój nie może wymagać ponad 60 minut;
- podobne kategorie nie są sztucznie urozmaicane — kilka dobrych zamków lub pałaców jest dozwolone;
- każdy kandydat występuje tylko raz po deduplikacji.

Kalibrację przeprowadzono na Oppelner Gravelzug. Feedback wykazał potrzebę mocnego uwzględniania historycznych miast, m.in. Grodkowa, Prudnika, Tułowic, Kamieńca Ząbkowickiego i Nysy, oraz obniżenia oceny grodzisk bez widocznych pozostałości.

## 2. Jedno kanoniczne źródło atrakcji

Planer Wypraw i Analiza Trasy czytają ten sam opublikowany wynik z tabel `qbot_v2.route_attraction_run` i `qbot_v2.route_attraction_layer` przez `qbot3/routes/route_attraction_store.py`.

Ranking znajduje się w `qbot3/routes/route_attraction_engine.py`. Aktualna wersja: `route_attractions_v2.1`. Wikipedia, Wikidata i OSM tworzą bramkę semantyczną. Google jest dodatkowym dowodem jakości i lokalizacji, ale sam nie decyduje, czy miejsce jest atrakcją.

Publikacja jest atomowa. Niepełny lub zbyt ubogi wynik nie zastępuje poprzedniej publikacji. Minimalna bramka to 10 kandydatów na 100 km, cel rankingu to 12 kandydatów i 2,5 rekomendacji na 100 km.

Warstwa przechowuje nazwę, kategorię, kilometr, odległość od śladu, wynik i jego składowe, czas postoju, opis, zdjęcie, link źródłowy, dopasowaną ocenę Google i flagę rekomendacji.

## 3. Najważniejsze reguły rankingu

Najwyższe wagi bazowe mają historyczne miasta oraz zamki i pałace. Wysoko oceniane są fortyfikacje i zabytki techniki. Muzea oraz przyroda mają niskie wagi.

Archeologia ma dwa przypadki:

- ruiny, wieża, wały, mury lub rekonstrukcja dostają premię;
- sam wpis o grodzisku bez elementu do zobaczenia dostaje silną karę.

Odległość jest karana progresywnie. Kandydat oddalony ponad 800 m przechodzi tylko przy wysokiej wartości bazowej. Granica źródłowego wyszukiwania pozostaje do około 2 km.

Rekomendacje są rozkładane wzdłuż trasy mechanizmem MMR. Lista TAK/NIE nie karze dwóch pobliskich dobrych miejsc, bo ma stanowić szerszą wspólną bazę wyboru.

## 4. Podział wyprawy i Dodaj do QBot

Endpoint: `POST /api/planer/dodaj-do-qbot`.

Body:

```json
{
  "route_id": "<id trasy nadrzędnej>",
  "cuts": [40.0, 85.5]
}
```

Implementacja: `qbot3/routes/planer_stage_export.py`.

Po kliknięciu „Dodaj wszystkie dni do QBot (N GPX)” system:

1. waliduje 1–12 dni, minimum 1 km na dzień;
2. generuje deterministyczny `split_key`;
3. tworzy osobny identyfikator i GPX każdego dnia;
4. rejestruje GPX w kanonicznym route store;
5. zapisuje relację dziecko–rodzic w `qbot_v2.route_stage_lineage`;
6. dziedziczy wycinek nawierzchni i POI logistycznych;
7. zapisuje zakończone joby, dzięki czemu odcinki są dostępne w Analizie Trasy.

GPX trafiają do `/opt/qbot/artifacts/exports/rwgps/rwgps_<child_route_id>.gpx`. Identyfikator ma format `planer-<hash rodzica>-<hash podziału>-dNN`.

## 5. Dziedziczenie bez ponownych zapytań

Dzienna trasa jest wycinkiem geometrii, a nie nowym źródłem atrakcji. `get_route_attractions()` rozpoznaje lineage, czyta publikację rodzica w zakresie `parent_km_from..parent_km_to` i przelicza kilometr względem początku dnia.

Skutki:

- Wikipedia, Wikidata i Google są pytane raz dla całej wyprawy;
- każdy dzień widzi atrakcje tylko ze swojego zakresu;
- eksport raportuje `external_attraction_requests: 0`;
- dodanie daty i pogody nie uruchamia ponownego wyszukiwania atrakcji.

Sklepy, jedzenie, woda i pozostała logistyka pozostają osobną warstwą `route_poi_layer`. Są dziedziczone jako wycinek rodzica, ale nie są mieszane z kanoniczną warstwą atrakcji.

## 6. Sprzątanie zmienionych podziałów

Zmiana liczby dni lub punktów podziału tworzy nowy zestaw. Sprzątanie poprzedniego podziału zaczyna się dopiero po poprawnym utworzeniu i zapisaniu całego nowego zestawu.

Kasowane są wyłącznie rekordy wskazane przez lineage dla tego samego rodzica, z innym `split_key`, źródłem artefaktu `planer` i identyfikatorem zgodnym ze ścisłym formatem dziennej trasy.

Kolejność bezpieczeństwa:

1. pełne utworzenie nowego zestawu;
2. transakcyjne usunięcie starego lineage, `route_base`, artefaktów i warstw zależnych;
3. po zatwierdzeniu transakcji usunięcie dokładnych GPX, bez globów i kasowania katalogów.

Błąd usunięcia pliku nie unieważnia nowego podziału i trafia do `cleanup_warnings`. Brak pliku jest informacyjny. Identyczny podział jest idempotentny. Trasy ręczne, rodzic i trasy niezwiązane są poza zakresem sprzątania.

## 7. WEB i pliki

Statyki są poza repozytorium aplikacji:

- `/opt/qbot/web/public/planer-wyprawy-render.js`, cache `v27`;
- `/opt/qbot/web/public/planer-wyprawy.html`.

Najważniejsze pliki repozytorium:

- `sql/route_attraction_store_v1.sql`;
- `sql/route_stage_lineage_v1.sql`;
- `scripts/apply_route_stage_lineage_v1.py`;
- `qbot3/routes/route_attraction_engine.py`;
- `qbot3/routes/route_attraction_sources.py`;
- `qbot3/routes/route_attraction_store.py`;
- `qbot3/routes/planer_stage_export.py`;
- `qbot_web.py`;
- testy `test_route_attraction_engine.py`, `test_route_attraction_store.py`, `test_planer_stage_export.py`.

## 8. Weryfikacja

Stan produkcyjny:

- migracja `route_stage_lineage_v1` zastosowana;
- `qbot-web` aktywny;
- Planer serwuje frontend `v27`;
- lista gotowych tras filtruje aktywne `route_base`;
- testy nie tworzyły sztucznych tras produkcyjnych.

Testy związane z mechanizmem:

- Planer i sprzątanie: 15/15;
- silnik atrakcji: 8/8;
- wspólny store/reader atrakcji: 11/11.

Pełny pytest zebrał 456 testów. Powyższe zestawy przeszły w całości; pełny projekt nadal ma wcześniejsze, niezwiązane błędy kolektorów, raportów i testów Google POI.

Commity sesji: `f577e34`, `692b029`, `c972a5a`, `74e31d2`, `d4238e3`.

## 9. Granice i dalsze kroki

- Pierwsze realne kliknięcie użytkownika jest testem integracyjnym pełnego zapisu; produkcji nie zanieczyszczano trasami testowymi.
- Należy monitorować `cleanup_warnings`.
- Commity są w produkcyjnym repozytorium; synchronizacja z `origin/main` wymaga osobnego `git push origin main`.
