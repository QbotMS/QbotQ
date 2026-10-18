---
tytul: Pola QExt2 w pliku FIT
dzial: qext2
typ: algorytm
opis: Po jeździe QBot odczytuje wybrane pomiary QExt2 z pliku aktywności i zapisuje ich podsumowanie.
tagi: [fit, qext2, wprime, wiatr, aero, podsumowanie]
synonimy: [fit qext2, dane z karoo, rezerwa z karoo, w prime balans, wiatr qext2]
skroty: [FIT, W′bal, CP, RSRV, W′, XSS]
gdzie_widac: [Historia jazdy, Raport jazdy]
liczby: [4 026 próbek, 40%, 83%, 238 W, 8 743 próbki, 2,4 m/s, 11,4%, 8 819 próbek AERO, 95 W]
zalezy_od: []
wplywa_na: [raport-jazdy/wprime-bal]
zrodla_kodu: [fitmodel/fit_ingest.py _QEXT2_FIELDS parse_fit_qext2_records summarize_qext2 ensure_qext2_table upsert_qext2_ride, fitmodel/qext2_aero.py store, fitmodel/modelq2/mpa.py, qext2_deploy/docs/KONTRAKT_DANYCH.md, qbot_v2.fitmodel_qext2_ride, qbot_v2.qext2_aero_record, qbot_v2.modelq2_ride]
aktualizacja: 18.10.2026
---

# Pola QExt2 w pliku FIT

## Co to jest

Podczas jazdy QExt2 zapisuje w pliku FIT (formacie pliku aktywności; [słowniczek](../slowniczek.md#fit)) dodatkowe pomiary. QBot odczytuje znane pola i zapisuje podsumowanie dla całej jazdy.

## Po co

Podsumowanie zachowuje informacje o rezerwie W′bal ([pozostałym zapasie](../modelq/wprime-bal.md)), mocy i wybranych wskaźnikach QExt2. Można je później porównać z innymi obliczeniami jazdy.

## Skąd dane

Źródłem jest plik FIT (format zapisu aktywności, opisany w [słowniczku](../slowniczek.md#fit)) dostarczony do QBota. Program odczytuje między innymi przebieg W′bal, pole [CP](../slowniczek.md#cp), pojemność [W′](../modelq/hie.md), gotowość, rezerwę [RSRV](../slowniczek.md#rsrv), punkty obciążenia [XSS](../slowniczek.md#xss) i pola [AERO](../slowniczek.md#aero). Zna także numer wersji zapisu, pięciosekundową moc znormalizowaną i pola kontroli wiatru. Od 18.10.2026 zapisuje też próbki AERO w osobnym archiwum. Ten zapis AERO nie jest częścią skrótu jazdy opisanego niżej.

## Jak liczone

QBot nie odtwarza tu każdej wartości z algorytmu QExt2. Dla większości pól odczytuje próbki z pliku i tworzy skrót jazdy: minimum, wartość końcową, liczbę próbek, czas pierwszego zejścia W′bal do zera, medianę gotowości oraz wybrane podsumowania wiatru. Pola AERO są wyjątkiem: QBot zachowuje ich próbki osobno, a nie tylko skrót. Starszy opis wymiany z 17.10.2026 mówi, że serwer jeszcze ich nie odczytuje. Bieżący kod i zapis z 18.10.2026 potwierdzają, że ten opis jest już nieaktualny.

Przykład z bazy: jazda z 16.10.2026 (`24745225177`) miała 4 026 próbek; minimalny [W′bal](../modelq/wprime-bal.md) wyniósł 40%, końcowy 83%, a końcowa wartość pola [CP](../slowniczek.md#cp) QExt2 238 W. CP to historyczna nazwa techniczna pola QExt2; [TP](../modelq/tp.md) jest nazwą progu w ModelQ. W jeździe z 18.10.2026 zapisano 8 743 próbki kontroli wiatru; mediana wyniosła 2,4 m/s, a udział czasu pod wiatr 11,4%.

![Porównanie minimalnej i końcowej rezerwy W′bal w dwóch zapisanych jazdach](../img/qext2-wbal-przyklady.svg)

Na wykresie wartości z 16.10.2026 to 40% minimum i 83% na końcu. Dla 18.10.2026 są to 59% i 89%. Słupki pokazują tylko dwie liczby z każdego podsumowania, nie przebieg rezerwy w czasie.

Porównanie minimum QExt2 i ModelQ dla trzech wspólnych jazd pokazuje różnice między niezależnymi obliczeniami. Na przykład 11.10.2026 QExt2 zapisał 0%, a ModelQ wyliczył 6,3%. Pole QExt2 zapisuje procent jako liczbę całkowitą, a wynik ModelQ ma jedno miejsce po przecinku. Różnica 6,3 punktu w tej jeździe nie wynika z samego sposobu wyświetlenia.

![Minimum W′bal z QExt2 i ModelQ dla trzech jazd](../img/qext2-wbal-porownanie-202610.svg)

Próbki AERO z 18.10.2026: w bazie jest 8 819 próbek. W chwili 09:57:05 pole zapisało stan „pewny”, zmianę +95 W oraz bieżący współczynnik oporu 0,795 i odniesienie 0,470. To są wartości przepisane z FIT; QBot nie wyliczył ich sam. Wartość mocy jest szacunkiem pola, a nie pomiarem miernika.

```mermaid
flowchart LR
  Ride[Jazda na Karoo] --> FIT[Plik FIT z polami QExt2]
  FIT --> Odczyt[QBot odczytuje pomiary]
  Odczyt --> Fields[W′bal, CP, W′, gotowość, RSRV, XSS]
  Odczyt --> Summary[Minima, wartości końcowe, zdarzenia]
  Summary --> Table[Podsumowanie jazdy w historii QBota]
  Odczyt --> Aero[Próbki AERO zapisane osobno]
  Table --> Analysis[Analiza jazdy może użyć wybranych danych]
```

## Gdzie to widać

W QBocie wartości są zapisane w podsumowaniu jazdy. Zwykły użytkownik widzi je tylko tam, gdzie dana analiza jawnie korzysta z danych QExt2.

## Jak czytać

Najniższy procent W′bal to najniższa zapisana rezerwa podczas jazdy, a wartość końcowa jest ostatnią dostępną próbką. Pole CP z pliku QExt2 nie należy automatycznie utożsamiać z bieżącym progiem TP QBota.

## Decyzje i historia

Nazwy pól uzgadnia projekt QExt2 i QBot. Nie każde pole zapisane przez nową wersję QExt2 jest już odczytywane i zachowywane przez QBot.

## Ograniczenia i pułapki

- Starszy plik FIT bez pól QExt2 nie zawiera danych do tego podsumowania.
- Niektóre rekordy mają schemat 1, inne schemat 2; porównania wymagają uwzględnienia schematu.
- Pola AERO QBot zapisuje w osobnym archiwum próbek. Nie dopisuje ich do skrótu w historii jazdy, dlatego brak wartości AERO na tym ekranie nie oznacza braku próbek.
- Historia QBota przechowuje również podsumowanie kontroli wiatru, ale nie każda jazda ma te dane. Przykład z 18.10.2026 potwierdza zapis dla nowej jazdy.

## Jak czytać zapis na przykładzie

1. Po jeździe QBot odczytuje tylko próbki, w których występuje co najmniej jedno rozpoznane pole QExt2.
2. Dla jazdy z 16.10.2026 znaleziono 4 026 takich próbek. Wartość minimalna W′bal wyniosła 40%, a końcowa 83%.
3. Dla jazdy z 18.10.2026 zapis kontroli wiatru obejmował 8 743 próbki. Mediana prędkości przyjętego wiatru wyniosła 2,4 m/s; 11,4% próbek wskazywało wiatr w twarz.
4. Podsumowanie zachowuje wybrane wartości krańcowe lub mediany. Nie jest szeregiem wszystkich sekund i nie pozwala narysować pełnego przebiegu W′bal. Osobne archiwum AERO z 18.10.2026 zawiera 8 819 próbek; o 09:57:05 odnotowało stan pewny i +95 W.

Liczby te są prawdziwymi odczytami zapisanych jazd i dotyczą dwóch różnych dni. Nie należy z nich wyciągać wniosku, że wiatr był stały przez całą jazdę albo że każda jazda ma próbki kontroli wiatru.

> DO SPRAWDZENIA: kod potwierdza zapis próbek AERO po przetworzeniu FIT, ale nie zapisuje w tym rekordzie nazwy usługi, która dostarczyła konkretny plik. Nie potwierdzono każdej ścieżki dostarczenia FIT.

## Czego to podsumowanie nie mówi

Wartość końcowa jest ostatnią dostępną próbką w pliku, a niekoniecznie pomiarem wykonanym dokładnie w chwili zatrzymania. Minimum mówi o najniższym zapisanym wyniku, nie o czasie jego trwania. Mediana wiatru opisuje środkową wartość wśród odczytanych próbek, nie średnią prędkość na całej trasie. Analiza szczegółowa może więc potrzebować oryginalnych próbek jazdy.

## Wpływa na

- Analizę W′bal, jeśli korzysta z zapisanych zdarzeń z FIT QExt2.
- Możliwość porównywania wyników QExt2 z wynikami obliczanymi przez QBot.

## Zależy od

- Pliku FIT zawierającego pola QExt2.
- Zgodności nazw pól po stronie QExt2 i programu odczytującego QBota.

## Powiązane hasła

- [QExt2 i Karoo](index.md)
- [Przepływ danych podczas jazdy](przeplyw-jazdy.md)
- [W′bal w raporcie](../raport-jazdy/wprime-bal.md)
- [W′bal](../modelq/wprime-bal.md)

## Zrodla

- `/opt/qbot/app/fitmodel/fit_ingest.py` — `_QEXT2_FIELDS`, `parse_fit_qext2_records`, `summarize_qext2`, `ensure_qext2_table`, `upsert_qext2_ride`.
- `/opt/qbot/qext2_deploy/docs/KONTRAKT_DANYCH.md` — nazwy i wersje pól FIT, stan 17.10.2026; jego informacja o braku odczytu AERO jest nieaktualna względem bieżącego kodu QBota.
- `qbot_v2.fitmodel_qext2_ride` — jazda `24745225177`, 16.10.2026.
- `/opt/qbot/app/fitmodel/qext2_aero.py` — osobny zapis próbek AERO.
- `/opt/qbot/app/fitmodel/modelq2/mpa.py` — niezależne wyliczenie przebiegu ModelQ.
- `qbot_v2.qext2_aero_record` — jazda `24766557671`, 18.10.2026; próbka z 09:57:05.
- `qbot_v2.modelq2_ride` — porównania minimów W′bal dla jazd z 11, 16 i 18.10.2026.
