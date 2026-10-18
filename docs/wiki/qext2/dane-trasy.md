---
tytul: Dane trasy przekazywane Karoo
dzial: qext2
typ: algorytm
opis: QBot przekazuje Karoo nawierzchnię, punkty na trasie, plan czasu i typową relację mocy do tętna.
tagi: [trasa, nawierzchnia, punkty, czas, ef]
synonimy: [dane trasy, trasa na karoo, points, route profile]
skroty: [EF, NP, IF]
gdzie_widac: [Karoo, QExt2]
liczby: [500 m, 300 pozycji, 1 km, 1 h, 90 dni, 60 min, 10 km/h, 0,60–0,80, 5 jazd]
zalezy_od: [trasy/punkty-na-trasie]
wplywa_na: []
zrodla_kodu: [qbot_api.py /api/surface/by-name /api/poi/by-name /api/plan/by-name /api/ef/typical _qext2_plan_route, qext2_config.py, qext2_deploy/app/src/main/kotlin/com/qext2/primary/surface/SurfaceProfileCache.kt, qext2_deploy/app/src/main/kotlin/com/qext2/primary/statsv2/PlanProfile.kt, qext2_deploy/app/src/main/kotlin/com/qext2/primary/statsv2/RideWindows.kt]
aktualizacja: 18.10.2026
---

# Dane trasy przekazywane Karoo

## Co to jest

Podczas jazdy QExt2 może pobrać z QBota kilka uzupełniających danych dla zaplanowanej trasy: nawierzchnię odcinkami, punkty z wodą i jedzeniem oraz profil przewidywanego czasu jazdy. Osobno pobiera też typową relację mocy do tętna używaną w widoku statystyk. To cztery różne odpowiedzi; brak jednej nie oznacza, że pozostałe nie działają.

## Po co

Karoo może dzięki temu pokazać, co zbliża się na trasie, gdzie można uzupełnić wodę albo ile czasu ruchu i postojów model zakłada na kolejnych kilometrach. Typowa relacja mocy do tętna jest punktem porównania dla bieżącego wysiłku. Dane te QBot przygotowuje wcześniej lub na żądanie, a QExt2 wyświetla na liczniku.

## Skąd dane

- **Nawierzchnia:** najnowszy gotowy profil nawierzchni przypisany do rozpoznanej trasy.
- **Punkty logistyczne:** aktywne punkty wody, sklepy i miejsca z jedzeniem. QBot ogranicza wynik do punktów leżących najwyżej 500 m od trasy i zwraca maksymalnie 300 pozycji.
- **Plan czasu:** model QBota tworzy profil co około 1 km. Dla każdego punktu rozdziela przewidywany czas ruchu i postoje. Wynik używa trybu normalnego, jest przechowywany w pamięci podręcznej do godziny, a Karoo może ponowić pobranie po błędzie.
- **Typowe EF:** mediana NP podzielonej przez średnie tętno w odpowiednio dobranych jazdach. Do zestawu wchodzą jazdy z ostatnich 90 dni, co najmniej 60 minut, ze średnią prędkością powyżej 10 km/h i intensywnością IF od 0,60 do 0,80. Przy mniej niż 5 jazdach QBot zwraca brak typowej wartości.

EF (współczynnik efektywności, NP podzielone przez średnie tętno) i IF (intensywność względem progu) są wyjaśnione w [słowniczku](../slowniczek.md). Nazwy i kategorie punktów logistycznych wyjaśnia też hasło [punkty na trasie](../trasy/punkty-na-trasie.md).

## Jak liczone

1. Karoo prosi o dane dla nazwy bieżącej trasy. QBot próbuje dopasować nazwę do zapisanej trasy.
2. Dla nawierzchni QBot pobiera najnowszy gotowy profil i łączy sąsiadujące odcinki o tej samej klasie.
3. Dla punktów QBot wybiera aktywne punkty logistyczne do 500 m od trasy, porządkuje je po kilometrze trasy i ogranicza odpowiedź do 300 pozycji. Karoo pokazuje najbliższy przydatny punkt; przy wyborze preferuje wodę i może pominąć miejsce zamknięte danego dnia.
4. Dla planu czasu QBot zwraca próbki mniej więcej co 1 km, osobno dla ruchu i postojów. Karoo porównuje później te wartości z przebiegiem bieżącej jazdy.
5. Dla typowego EF QBot liczy medianę z jazd spełniających filtry. Jeżeli jest ich mniej niż 5, nie przedstawia typowej wartości.

Weryfikacja kodu potwierdziła zakresy i filtry, ale nie pobrano w tej sesji odpowiedzi z aktywnego Karoo ani przykładowej listy punktów konkretnej trasy. Odczyt bazy z 16.10.2026 potwierdza jazdę z 4 026 próbkami QExt2, ale to przykład danych FIT po jeździe, nie profil trasy ani wyliczenie typowego EF.

> DO SPRAWDZENIA: przykład z bazy dla wszystkich czterech odpowiedzi trasowych oraz typowego EF, wraz z nazwą trasy i datą obliczenia.

```mermaid
flowchart TD
  Nazwa[Nazwa trasy z Karoo] --> Dopasowanie[QBot rozpoznaje trasę]
  Dopasowanie --> Nawierzchnia[Profil nawierzchni]
  Dopasowanie --> Punkty[Woda, sklepy i jedzenie]
  Dopasowanie --> Czas[Profil ruchu i postojów]
  Jazdy[Jazdy z ostatnich 90 dni] --> EF[Typowe EF]
  Nawierzchnia --> K[Kokpit lub ekran statystyk]
  Punkty --> K
  Czas --> K
  EF --> K
  Brak[Dopasowania lub danych] --> Pusta[Brak wyniku dla danej grupy]
```

<details>
<summary>Wzór</summary>

Typowe EF = mediana z wartości NP / średnie tętno dla jazd spełniających filtry. Mediana wybiera środkowy wynik po uporządkowaniu jazd, więc pojedyncza bardzo wysoka lub niska wartość ma mniejszy wpływ niż przy zwykłej średniej.

</details>

## Gdzie to widać

Nawierzchnia i punkty mogą pojawić się w pasku nawigacyjnym KOKPIT 2. Profil czasu jest używany w widoku statystyk QExt2, a typowe EF jest pobierane przez rozszerzenie dla porównania wysiłku. Dostępny zrzut WIKI przedstawia stronę SETUP QBota, nie ekran jazdy Karoo.

![Zakładka QExt2 w SETUP QBota; dane trasy są pokazywane na Karoo, a nie w tym zrzucie](../img/ekrany/setup.png)

## Jak czytać

- Brak profilu nawierzchni oznacza, że QBot nie ma gotowego profilu dla rozpoznanej trasy; nie oznacza automatycznie braku samej trasy.
- Punktów może nie być, jeśli nie znaleziono trasy albo żaden aktywny punkt nie spełnia kryteriów odległości i kategorii.
- Plan czasu rozdziela ruch i postoje. Nie jest obietnicą dokładnej godziny przyjazdu.
- Typowe EF to punkt odniesienia z wcześniejszych jazd, a nie ocena zdrowia ani prognoza mocy.

## Ograniczenia

- Dopasowanie odbywa się po nazwie trasy, która może być niejednoznaczna.
- Profil nawierzchni i lista punktów zależą od aktualnych danych trasowych.
- Typowe EF nie filtruje po rowerze, ponieważ dane źródłowe jazd nie mają w tej ścieżce sprawdzonego powiązania z rowerem.
- > DO SPRAWDZENIA: dokładny ekran, na którym aktywna wersja QExt2 prezentuje plan czasu i typowe EF.

## Wpływa na / Zależy od

- Dane nawierzchni i punktów wpływają na podpowiedzi nawigacyjne.
- Profil czasu wpływa na porównanie planowanego czasu z ruchem i postojami w trakcie jazdy.
- Typowe EF jest osobnym tłem porównawczym w statystykach; nie zmienia obliczeń ModelQ w QBocie.
- Wszystkie odpowiedzi zależą od poprawnego rozpoznania trasy lub dostępności wystarczającej liczby jazd.

## Powiązane hasła

- [QExt2 i Karoo](index.md)
- [Przepływ jazdy](przeplyw-jazdy.md)
- [Komunikaty KOKPIT 2](komunikaty.md)
- [Punkty na trasie](../trasy/punkty-na-trasie.md)
- [Czas przejazdu](../trasy/czas-przejazdu.md)
- [Słowniczek](../slowniczek.md)

## Zrodla

- `/opt/qbot/app/qbot_api.py` — `/api/surface/by-name`, `/api/poi/by-name`, `/api/plan/by-name`, `/api/ef/typical`, `_qext2_plan_route`.
- `/opt/qbot/app/qext2_config.py` — komunikat nawierzchni i punktów, domyślne zasięgi.
- `/opt/qbot/qext2_deploy/app/src/main/kotlin/com/qext2/primary/surface/SurfaceProfileCache.kt` — pobranie nawierzchni i punktów.
- `/opt/qbot/qext2_deploy/app/src/main/kotlin/com/qext2/primary/statsv2/PlanProfile.kt` — profil czasu.
- `/opt/qbot/qext2_deploy/app/src/main/kotlin/com/qext2/primary/statsv2/RideWindows.kt` — typowe EF.
