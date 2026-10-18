---
tytul: Pogoda w QExt2
dzial: pogoda
typ: polaczenie
opis: "Opisuje pogodę z trasy, którą QBOT przekazuje urządzeniu QExt2."
tagi: ["pogoda", "qext2", "karoo", "trasa", "radar"]
synonimy: ["pogoda karoo", "qext2 pogoda", "pogoda na liczniku", "weather on route", "dane meteo karoo"]
skroty: ["QExt2", "Karoo", "ETA", "OPERA"]
gdzie_widac: ["QExt2", "Karoo"]
liczby: ["kilometr trasy", "wiatr m/s", "porywy m/s", "horyzont min"]
zalezy_od: ["pogoda/pogoda-na-trasie", "pogoda/radar", "pogoda/wiatr", "pogoda/ostrzezenia"]
wplywa_na: ["qext2/index"]
zrodla_kodu: ["qbot_api.py _qext2_weather_route _qext2_radar_overlay _qext2_live_loop", "qbot3/routes/route_meteo_engine.py", "docs/POGODA_OSTRZEZENIE.md"]
aktualizacja: 18.10.2026
---

# Pogoda w QExt2

## Co to jest

QExt2 może otrzymać z QBota pogodę dla bieżącej trasy od aktualnego kilometra do jej końca. QBOT liczy ją tym samym silnikiem meteo trasowym, który jest używany w analizie trasy.

## Po co

Podczas jazdy pozwala pokazać prognozowane warunki na dalszych odcinkach bez czekania na oddzielne obliczenie po stronie urządzenia.

## Skąd dane

QBot rozpoznaje trasę przekazaną w trybie jazdy i wybiera kolejne punkty od bieżącego kilometra. Korzysta z prognozy Open-Meteo, przebiegu trasy i przewidywanego czasu dotarcia. Dla odcinków w najbliższych 120 minutach opad z modelu może zostać zastąpiony krótką prognozą przesunięcia ostatniego obrazu [OPERA](../slowniczek.md#opera).

## Jak liczone

1. QExt2 przekazuje identyfikator trasy i bieżący kilometr w trybie jazdy.
2. QBOT uruchamia silnik bazowo, aby oszacować czas dotarcia do aktualnego miejsca, a następnie liczy ponownie z dopasowaną godziną startu.
3. Z dalszej części trasy wybiera najwyżej 250 punktów, z kilometrem i minutami do przejazdu.
4. Do punktów dodaje odczuwalną temperaturę, opad, jego prawdopodobieństwo, wiatr czołowy/tylny i porywy.
5. Dla punktów do 120 minut może użyć radaru zamiast prognozy opadu. Wynik jest buforowany przez 10 minut; automat odświeżający tryb jazdy sprawdza stan co minutę i odświeża pogodę co 15 minut.

Wartości dla pojedynczej jazdy nie zostały odczytane z bazy w tym etapie, dlatego nie podaję przykładowych liczb dla trasy.

```mermaid
flowchart LR
  Karoo[Pozycja i trasa] --> API[API QBot]
  API --> ETA[Ustal kilometraż i ETA]
  ETA --> Silnik[Silnik meteo trasy]
  Silnik --> Punkty[Prognoza kolejnych punktów]
  Radar[OPERA do 120 minut] --> Punkty
  Punkty --> Dane[Temperatura, opad i wiatr]
  Dane --> QExt[QExt2 / Karoo]
```

## Gdzie to widać

Dane są częścią połączenia QBota z QExt2. Dokładny ekran urządzenia i sposób prezentacji każdego pola wymagają osobnego potwierdzenia.

> DO SPRAWDZENIA: Potwierdzić na urządzeniu QExt2, jak wyświetlane są składowa wiatru, porywy, szansa opadu i informacja o źródle opadu.

## Jak czytać

Składowa wzdłużna wiatru jest wyrażona w m/s: wartość dodatnia oznacza wiatr czołowy, ujemna — wiatr w plecy. Porywy także są w m/s. Czas przy punkcie oznacza liczbę minut do przewidywanego przejazdu. Informacja o pochodzeniu opadu rozróżnia radar i prognozę modelową.

## Decyzje i historia

Wpis projektu z 16.10.2026 opisuje tryb jazdy, odświeżanie co 15 minut i użycie radaru do 120 minut; bieżąca implementacja potwierdza te elementy. Pogoda nie wyznacza rozpiski mocy: jej właścicielem pozostaje QExt2/Karoo.

## Ograniczenia i pułapki

Brak rozpoznanej trasy lub danych segmentowych zwraca odpowiedź o błędzie. Radar jest stosowany tylko, gdy dostępna jest świeża klatka; poza krótkim horyzontem pozostaje model. Odczyt opiera się na implementacji API — nie potwierdza aktualnego ekranu urządzenia.

## Wpływa na

Prognozę dalszej części trasy przekazywaną z QBota do QExt2.

## Zależy od

Nazwy i przebiegu trasy, aktualnego kilometra, przewidywanego czasu przejazdu, prognozy i dostępności radaru.

## Powiązane hasła

- [Pogoda na trasie](pogoda-na-trasie.md)
- [Radar](radar.md)
- [Wiatr](wiatr.md)
- [QExt2](../qext2/index.md)

## Zrodla

- `/opt/qbot/app/qbot_api.py` — `_qext2_weather_route`, `_qext2_radar_overlay`, `_qext2_live_loop`.
- `/opt/qbot/app/qbot3/routes/route_meteo_engine.py` — prognoza segmentowa.
- `/opt/qbot/app/docs/CONTEXT.md` — wpis 16.10.2026 o pogodzie QExt2.
- `/opt/qbot/app/docs/POGODA_OSTRZEZENIE.md` — powiązany sygnał jazdy i ostrzeżenie radarowe.
