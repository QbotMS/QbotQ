# Xert

## Co to jest

Xert jest zewnętrznym punktem porównania dla ModelQ. Zabezpieczenia w kodzie zabraniają używania go jako podstawy parametrów QBota.

## Po co

Pomaga przenieść dane między usługą a QBotem i sprawdzić, czy przepływ działa.

## Skąd dane

Zewnętrzne dane Xert zapisane jako migawki profilu lub w tabeli porównawczej ModelQ.

## Jak liczone

Kod ma osobne moduły importu i porównania. Testy zabezpieczające ograniczają miejsca, które mogą czytać dane Xert; wynik ModelQ pozostaje niezależny.

```mermaid
flowchart LR
  A[Usługa zewnętrzna] --> B[QBot lub automat]
  B --> C[Zapis / wynik]
  C --> D[Strona albo powiadomienie]
```

Nie odczytano aktualnego rekordu porównawczego Xert. Ograniczenie roli Xert potwierdza kod testów i dokumentacja projektu.

## Gdzie to widać

SETUP > Połączenia zawiera ramki Stravy, Komoot i Hammerhead/Karoo. Wybrane stany integracji pokazuje SETUP > Połączenia > Status. Szczegóły danego przepływu podano powyżej.

## Jak czytać

Status opisuje świeżość i powodzenie pracy automatu, a nie gwarantuje kompletności wszystkich danych u dostawcy. Brak osobnego checku nie przesądza o braku integracji.

## Decyzje i historia

Nie odczytano aktualnego rekordu porównawczego Xert. Ograniczenie roli Xert potwierdza kod testów i dokumentacja projektu.

## Ograniczenia i pułapki

Nie zakładaj, że każda pozycja oznacza bieżący, poprawny import. Częstotliwości wymagają potwierdzenia w aktywnym harmonogramie.

## Wpływa na

- [Połączenia i dane](index.md)
- [Status i automaty](../system/automaty.md)

## Zależy od

- Dostępu do wskazanej usługi oraz uruchomienia automatu.
- Zapisów w tabelach/plikach wymienionych poniżej.

## Powiązane hasła

- [Garmin](garmin.md)
- [Harmonogram importów](harmonogram-importow.md)
- [Raport jazdy](../raport-jazdy/index.md)

## Zrodla

- `qbot3/connectors/import_xert_profile_snapshot.py`; `fitmodel/xert_bench.py`; `fitmodel/xert_daily_bench.py`; `tests/test_no_xert_basis.py`; `tests/test_xert_isolation.py`
- `qbot_v2.xert_profile_snapshots`; `qbot_v2.modelq2_xert_bench`
