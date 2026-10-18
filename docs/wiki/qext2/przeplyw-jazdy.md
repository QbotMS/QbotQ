---
tytul: Przepływ danych podczas jazdy
dzial: qext2
typ: algorytm
opis: Pokazuje drogę danych między QBotem, Karoo i plikiem z zapisem jazdy.
tagi: [qext2, przeplyw, karoo, fit]
synonimy: [jak qbot laczy sie z karoo, dane podczas jazdy, synchronizacja hammerhead]
skroty: [FIT, ETA, W′bal]
gdzie_widac: [Karoo, QExt2, Hammerhead, Historia jazdy]
liczby: [10 min, 30 min, 4 026 próbek, 40%, 83%, 8 743 próbki, 2,4 m/s, 11,4%]
zalezy_od: [qext2/kokpit2, qext2/dane-trasy, qext2/pogoda-info]
wplywa_na: [qext2/pola-fit, raport-jazdy/index]
zrodla_kodu: [mcp_server.py ride_readiness _qext2_ping, qbot_api.py /api/weather/by-name _qext2_live_loop, fitmodel/fit_ingest.py parse_fit_qext2_records summarize_qext2 upsert_qext2_ride, qbot_v2.fitmodel_qext2_ride, qext2_deploy/docs/KONTRAKT_DANYCH.md]
aktualizacja: 18.10.2026
---

# Przepływ danych podczas jazdy

## Co to jest

To wymiana danych między QBotem, Karoo z QExt2 i serwisem Hammerhead. QBot przekazuje dane potrzebne na ekranie, a po jeździe odczytuje pomiary zapisane w pliku FIT (formacie pliku aktywności; [słowniczek](../slowniczek.md#fit)).

## Po co

Dzięki temu Karoo może pokazać informacje o gotowości, trasie, pogodzie i ustawieniach, a QBot może później uwzględnić część pomiarów QExt2 w historii jazdy.

## Skąd dane

Karoo pobiera z QBota dane gotowości i ustawienia. Szczegóły trasy, pogody i planu pobiera osobno, gdy są potrzebne. Podczas jazdy może wysłać pozycję, nazwę trasy, kilometr trasy i szacowany czas przyjazdu. Harmonogram systemu uruchamia synchronizację Hammerhead→Garmin co 10 minut; osobny lekki odczyt nowych FIT działa co 30 minut. Sam wpis harmonogramu nie potwierdza dokładnego opóźnienia konkretnego pliku.

## Jak liczone

1. Karoo pobiera gotowość oraz konfigurację kokpitu z QBota.
2. Gdy potrzebuje szczegółów trasy, pyta osobne usługi QBotu: między innymi o nawierzchnię, punkty, plan czasu i pogodę.
3. W trybie jazdy QBot przyjmuje sygnał położenia oraz postępu. Zapisuje aktualną trasę i kilometr.
4. Po otrzymaniu FIT QBot szuka pól QExt2 w próbkach jazdy. Liczy z nich skrót dla całej jazdy i zapisuje go w historii.

Przykład z bazy: jazda z 16.10.2026, o numerze `24745225177`, miała 4 026 próbek QExt2. Minimalna rezerwa W′bal ([pozostały zapas](../modelq/wprime-bal.md)) wyniosła 40%, a końcowa 83%. To wartości odczytane z pliku jazdy, nie prognoza QBotu.

```mermaid
flowchart TD
  Start[Start QExt2] --> Readiness[Pobranie gotowości i ustawień]
  Readiness --> Ekran[Dane widoczne na Karoo]
  Ekran -->|pozycja, trasa, km, ETA| Ping[QBot zapisuje stan jazdy]
  Ping --> Info[QBot przygotowuje pogodę na trasę]
  Ekran --> Koniec[Koniec jazdy]
  Koniec --> FIT[Plik FIT przez Hammerhead]
  FIT --> Parse[QBot odczytuje pola QExt2]
  Parse --> Sum[Podsumowanie jednej jazdy]
  Sum --> DB[Podsumowanie w historii QBota]
```

## Gdzie to widać

Na Karoo dane widać w polach QExt2. W QBocie podsumowanie jest częścią historii jazdy; dalsza analiza zależy od tego, czy korzysta z konkretnego pola.

## Jak czytać

Brak podsumowania QExt2 nie oznacza braku samej jazdy. Starszy plik może nie zawierać pól QExt2; wtedy program odczytujący pomija tę część bez błędu całego importu.

## Decyzje i historia

QBot utrzymuje własny odczyt i zapis podsumowania pól QExt2. QExt2 jest osobnym projektem, więc jego ekran i obliczenia nie są częścią kodu QBota.

## Ograniczenia i pułapki

- Wpisy w tabeli są podsumowaniem. Nie są pełnym zapisem każdej próbki.
- W zapisie mogą występować różne wersje pól FIT. QBot zachowuje numer wersji; brak numeru traktuje jako wersję 1.
- Bieżąca baza ma miejsce na podsumowanie kontroli wiatru, a przykład z 18.10.2026 potwierdza zapis. Nie odczytano dziennika synchronizacji aktywnego konta, więc rzeczywistego czasu dostarczenia pliku nie da się tu podać.

## Przykład odbioru po jeździe

1. Jazda z 16.10.2026 została zapisana w QBot pod identyfikatorem `24745225177`.
2. Jej podsumowanie zawiera 4 026 próbek QExt2, minimum W′bal równe 40% i wartość końcową 83%.
3. Inna jazda, z 18.10.2026, zawiera 8 743 próbki kontroli wiatru; środkowy odczyt wynosi 2,4 m/s, a udział próbek pod wiatr 11,4%.
4. Te zapisy potwierdzają, że QBot odebrał i podsumował przykładowe pliki. Nie pokazują, ile minut po zakończeniu jazdy pliki dotarły do serwera.

Synchronizacja Hammerhead i importer FIT mają w kodzie harmonogramy co 10 i 30 minut. To interwały uruchamiania zadań, nie gwarantowany czas pojawienia się konkretnego pliku. Nie mogę więc wyliczyć dokładnego opóźnienia na podstawie samego podsumowania.

> DO SPRAWDZENIA: znaczniki czasu zakończenia jazdy, pojawienia się pliku i zapisu podsumowania dla jednego aktywnego konta.

## Po czym poznać niepełny przepływ

- Jeśli jazda jest w historii, ale brakuje danych QExt2, plik może nie zawierać obsługiwanych pól albo importer mógł ich nie rozpoznać.
- Jeśli podsumowanie istnieje, ale nie ma próbek wiatru, może to być starszy plik lub jazda bez tych pól.
- Brak sygnału postępu jazdy nie oznacza automatycznie utraty FIT. Sygnał na żywo służy między innymi do kontekstu pogody; odbiór pliku po jeździe jest osobną drogą.

## Wpływa na

- [Pola FIT QExt2](pola-fit.md) — opisują szczegółowo wartości z pliku.
- [Raport jazdy](../raport-jazdy/index.md) — może korzystać z odtworzonego albo zapisanego W′bal.

## Zależy od

- Dostępności usług QBota oraz internetu.
- Poprawnego pliku FIT i obecności w nim pól QExt2.

## Powiązane hasła

- [QExt2 i Karoo](index.md)
- [KOKPIT 2 i ustawienia](kokpit2.md)
- [Pogoda INFO](pogoda-info.md)
- [Pola FIT QExt2](pola-fit.md)

## Zrodla

- `/opt/qbot/app/mcp_server.py` — `ride_readiness`, `_qext2_ping`.
- `/opt/qbot/app/qbot_api.py` — `/api/weather/by-name`, `_qext2_live_loop`.
- `/opt/qbot/app/fitmodel/fit_ingest.py` — `parse_fit_qext2_records`, `summarize_qext2`, `upsert_qext2_ride`.
- `qbot_v2.fitmodel_qext2_ride` — przykład jazdy z 16.10.2026.
- `/opt/qbot/qext2_deploy/docs/KONTRAKT_DANYCH.md` — uzgodnione nazwy pól FIT.
