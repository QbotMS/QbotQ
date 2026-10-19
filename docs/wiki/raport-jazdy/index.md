---
tytul: Raport jazdy
dzial: raport-jazdy
typ: przeglad
opis: Pokazuje, jak czytać raport wykonanej jazdy i prowadzi do jego poszczególnych części.
tagi: [raport, jazda, mapa, wykres, aktywność]
synonimy: [raport jazdy, ride report, podsumowanie jazdy, analiza aktywnosci]
skroty: [NP, IF, W′bal, XSS]
gdzie_widac: [Raport jazdy, Strava]
liczby: []
zalezy_od: [plik-fit, np-if, wprime-bal]
wplywa_na: [analiza-jazdy, analiza-ai, opis-strava]
zrodla_kodu: [qbot3/rides/ride_report_builder.py, build_w1, save_report, qbot3/rides/ride_report_w2.py, build_w2, qbot_v2.ride_report_data, qbot3/rides/ride_report_facts.py, web_public/raport-jazdy.html, web_public/raport-jazdy2-dane.js]
aktualizacja: 19.10.2026
---

# Raport jazdy

Raport jazdy pokazuje, co zarejestrowało urządzenie, jak wyglądał wysiłek na trasie i które dodatkowe informacje udało się dołączyć. Główna część ekranu łączy mapę z wykresem; panel po lewej podaje podsumowanie, a pionowy pasek ikon otwiera szczegóły.

![Raport jazdy z 18.10.2026: mapa, podsumowanie i wykres wysiłku](../img/ekrany/raport-jazdy.png)

Na zrzucie jest jazda z Marek z 18.10.2026. W lewym panelu widać dystans 53,9 km, czas 2:26, prędkość 22,1 km/h, moc 154 W, próg 241 W i obciążenie. Werdykt jest pod kartą z danymi. Kolorowy ślad na mapie pokazuje wybraną warstwę „strefa mocy”. Dolny wykres ma wspólną oś odległości: przyciski nad nim pozwalają włączać serie, a po prawej wybiera się warstwy i korelację. Dokładne znaczenie obciążenia i mocy opisują [NP i IF](np-if.md) oraz [W′bal](wprime-bal.md).

## Droga od jazdy do ekranu

[W1 i W2 raportu jazdy](../slowniczek.md#w1-i-w2-raportu-jazdy) oznaczają część liczbową i opcjonalny komentarz sztucznej inteligencji (AI; [słowniczek](../slowniczek.md#ai-sztuczna-inteligencja)). Brak komentarza nie usuwa mapy ani pomiarów. GPS (system określania położenia; [słowniczek](../slowniczek.md#gps)) pozwala połączyć ślad z wykresem.

```mermaid
flowchart LR
  FIT[Zapis z urządzenia] --> Fakt[Pomiary jazdy]
  MQ[Próg i dane ModelQ] --> Raport[Zestaw faktów]
  GPS[Pozycja i ślad] --> Raport
  Fakt --> Raport
  Raport --> Mapa[Mapa i wykres]
  Raport --> Karty[Karty szczegółów]
  Raport --> AI[Analiza AI]
  AI --> Panel[Panel analizy]
  Raport --> Strava[Opis Strava]
```

## Co widzisz na ekranie

| Na ekranie | Co to mówi | Hasło |
|---|---|---|
| Dystans, czas, prędkość, moc | Podstawowe podsumowanie jazdy | [Analiza jazdy](analiza-jazdy.md) |
| Wysokość i przewyższenie | Profil wysokości w czasie jazdy oraz suma podejść | [Przewyższenie](przewyzszenie.md) |
| Tętno i próg tętna | Zarejestrowane tętno; próg służy do czytania stref, jeśli jest dostępny | [Plik FIT](plik-fit.md) |
| Próg i procent zapasu | NP (moc znormalizowana; [słowniczek](../slowniczek.md#np)) oraz IF (stosunek NP do progu; [słowniczek](../slowniczek.md#if)) porównują wysiłek z progiem | [NP i IF](np-if.md), [W′bal](wprime-bal.md) |
| Zapas i jego przebieg | Wartość minimalna albo seria w czasie; źródło może się różnić | [W′bal](wprime-bal.md) |
| Praca i tempo jej wydatkowania | Energia wykonanej pracy oraz średnia na godzinę | [Analiza jazdy](analiza-jazdy.md), [Plik FIT](plik-fit.md) |
| Kadencja i biegi | Obrót pedałów oraz przełożenie, gdy pomiary są dostępne | [Plik FIT](plik-fit.md) |
| Temperatura i wiatr | Warunki zapisane lub dołączone do jazdy; wiatr może być wyliczony względem kierunku śladu | [Analiza jazdy](analiza-jazdy.md) |
| Kolorowy ślad i wybór „warstwy” | Miejsce jazdy i wybrana informacja rysowana na śladzie | [Analiza jazdy](analiza-jazdy.md) |
| Dolny wykres i kolorowe przyciski | Pomiary wzdłuż trasy; widoczne serie można włączać i wyłączać | [Plik FIT](plik-fit.md) |
| Werdykt | Krótka synteza planu, wysiłku i kontekstu | [Analiza AI](analiza-ai.md) |
| Ikony po prawej stronie panelu | Dodatkowe karty, m.in. moc, tętno, pogoda, sprzęt | [Analiza jazdy](analiza-jazdy.md) |
| „Z kim jechałem” oraz „Ubiór / rower” | Dane towarzyszy oraz sprzęt przypisany do aktywności | [Analiza jazdy](analiza-jazdy.md) |
| Prędkość, kadencja, temperatura, rozwinięcie, momenty | Przyciski serii wykresu; włączają i wyłączają dostępne przebiegi | [Plik FIT](plik-fit.md) |
| Przewyższenie | Suma podejść przypisana do wykonanej jazdy | [Przewyższenie](przewyzszenie.md) |
| Nawierzchnia | Udział rozpoznanych typów podłoża | [Nawierzchnia jazdy](nawierzchnia-jazdy.md) |
| Porównanie planu z jazdą | Pokazuje się, gdy uda się dopasować zapisany plan | [Plan a wykonanie](plan-wykonanie.md) |
| Tekst opublikowany przy aktywności | Krótszy opis z wybranych faktów raportu | [Opis Strava](opis-strava.md) |

Lista kart i ich kolejność zależą od danych wybranej jazdy; strona dodaje część z nich warunkowo. Zrzut pokazuje układ przykładowej aktywności, nie gwarantowaną listę dla każdej jazdy.

## Jak korzystać

Najpierw sprawdź datę i nazwę jazdy w lewym górnym rogu. Następnie wybierz serię na wykresie i porównaj jej przebieg z mapą. Jeśli interesuje Cię fragment, kliknij wykres lub ślad; panel odcinka pokazuje statystyki zaznaczonego zakresu. Wartości z jazdy mogą pochodzić z różnych źródeł, dlatego czytaj także podpis pod kartą.

Przykład z 18.10.2026: ekran pokazuje moc średnią 154 W, NP 175 W i próg TP 241 W. IF jest zapisane jako 0,72. Dzielenie liczb widocznych na ekranie daje 0,73, ponieważ waty są zaokrąglone. Prędkość ruchu to 22,1 km/h, a średnia liczona z całego czasu to 20,0 km/h; drugi wynik uwzględnia postoje.

## Jak czytać źródła danych

Przy kartach raport podaje, skąd pochodzi liczba. „FIT” oznacza zapis z urządzenia. „ModelQ” oznacza wartość modelu dla danego dnia. „Karoo” lub „QExt2” wskazuje pomiar dołączony przez urządzenie. Gdy źródło jest opisane jako szacunek albo wnioskowanie, traktuj je jako mniej bezpośrednie niż zapis czujnika.

Raport z 18.10.2026 pokazuje, dlaczego warto czytać źródło: próg 241 W pochodzi z ModelQ, a moc średnia 154 W, NP 175 W i moc maksymalna 671 W pochodzą z zapisu jazdy. Nie są to pomiary z jednego źródła.

## Kiedy wrócić do szczegółów

- Gdy NP jest wyraźnie wyższe od średniej mocy, sprawdź wykres i [NP oraz IF](np-if.md), aby znaleźć mocniejsze fragmenty.
- Gdy zapas wysiłku mocno spada, sprawdź jego przebieg i źródło w [haśle W′bal](wprime-bal.md).
- Gdy mapa pokazuje nawierzchnię, pamiętaj, że jej udział jest szacunkiem i może mieć niepełne pokrycie. Wyjaśnia to [nawierzchnia jazdy](nawierzchnia-jazdy.md).
- Gdy obok jazdy pojawia się plan, sprawdź jego nazwę. Dopasowanie może się nie udać albo wskazać bliski plan; opisuje to [plan a wykonanie](plan-wykonanie.md).
- Gdy werdykt zawiera interpretację, porównaj ją z kartami i wykresem. [Analiza AI](analiza-ai.md) nie zastępuje zarejestrowanych liczb.

> Pełny zestaw kart zależy od danych aktywności. Kod strony tworzy część sekcji warunkowo, więc nie ma jednej stałej listy kart obecnych przy każdej jeździe.

<details>
<summary>Wzór</summary>

Średnia prędkość całkowita = dystans ÷ cały czas. Średnia w ruchu pomija sekundy poniżej progu postoju. Dla ekranu z 18.10 dystans 53,9 km podzielony przez 2,69 h daje około 20,0 km/h; podzielony przez 2,44 h daje około 22,1 km/h.

</details>

19.10.2026: ekran raportu ma sześć sekcji: Ciało i forma, Wysiłek, Moc, Prędkość, Paliwo oraz Technika. Generator dołącza między innymi spalone węglowodany, jedzenie zapisane w Dzienniku oraz porównanie tętna spoczynkowego z 60 dniami. W części „W czym jechałem” podaje też fakty o jedzeniu na rowerze.

## Powiązane hasła

- [Analiza jazdy](analiza-jazdy.md)
- [Plik FIT](plik-fit.md)
- [NP i IF](np-if.md)
- [W′bal](wprime-bal.md)
- [Nawierzchnia jazdy](nawierzchnia-jazdy.md)
- [Plan a wykonanie](plan-wykonanie.md)
- [Analiza AI](analiza-ai.md)
- [Opis Strava](opis-strava.md)

## Wpływa na / Zależy od

- Wpływa na: widok raportu, karty i wykres jazdy; wybrane fakty mogą być użyte w analizie AI i opisie Strava.
- Zależy od: pomiarów aktywności, śladu GPS, zapisanych danych ModelQ oraz dostępności opcjonalnych analiz.

```mermaid
flowchart LR
 A[Wybór jazdy] --> B[Podsumowanie i wykres]
 B --> C[Sprawdź źródło liczby]
 C --> D[Karta szczegółów]
 C --> E[Mapa i odcinek]
 B --> F[Opcjonalny komentarz AI]
```

## Zrodla

- `/opt/qbot/app/qbot3/rides/ride_report_builder.py` — `build_w1`, `save_report`, sekcje `load`, `trace`, `surface`, `plan_vs_actual`.
- `/opt/qbot/app/qbot3/rides/ride_report_w2.py` — `build_w2`.
- `/opt/qbot/web/public/raport-jazdy.html` — układ raportu i karty.
- `/opt/qbot/web/public/raport-jazdy2-ws.js` — mapa, serie wykresu, warstwy i wybór odcinka.
- `/opt/qbot/web/public/raport-jazdy3-rail.js` — pasek ikon i panele.
- `qbot_v2.ride_report_data` — zapisany raport W1/W2.
