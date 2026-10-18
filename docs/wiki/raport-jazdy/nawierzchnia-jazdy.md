---
tytul: Nawierzchnia jazdy
dzial: raport-jazdy
typ: algorytm
opis: Pokazuje szacowany udział nawierzchni na śladzie wykonanej jazdy.
tagi: [nawierzchnia, asfalt, gravel, gps, raport]
synonimy: [nawierzchnia jazdy, asfalt czy gravel, surface, droga]
skroty: []
gdzie_widac: [Raport jazdy]
liczby: []
zalezy_od: [index, plik-fit]
wplywa_na: [index]
zrodla_kodu: [qbot3/rides/ride_report_builder.py, surface]
aktualizacja: 18.10.2026
---

# Nawierzchnia jazdy

## Co to jest

Raport szacuje udzial roznych rodzajow nawierzchni na podstawie sladu GPS wykonanej jazdy.

## Po co

Pozwala zobaczyc, jaka czesc sladu przypadla na asfalt, gravel lub trudniejsze odcinki.

## Skad dane

Silnik nawierzchni analizuje GPX przygotowany ze sladu GPS. Wynik ma piec klas, a kazdy raport zapisuje tez zrodlo oraz udzial odcinkow oznaczonych, wnioskowanych i nieznanych.

## Jak liczone

W raporcie z jazdy 16.10.2026 wynik wynosil: twarda szybka 80,3%, zwykly gravel 1,7%, trudna/wolna 3,5%, ryzyko/niepewne 14,5%. Udzial oznaczony wyniosl 81,2%, nieznany 6,1%, a wnioskowany 12,7%.



```mermaid
flowchart LR
 A[Ślad GPS jazdy] --> B[Przygotowanie GPX]
 B --> C[Analiza segmentów]
 C --> D[Klasy nawierzchni]
 D --> E[Udziały i jakość pokrycia]
 E --> F[Raport jazdy]
```

## Gdzie to widac

Karta nawierzchni, mapa oraz rozklad wysilku wedlug typu nawierzchni.

## Jak czytac

Procenty klas nawierzchni to udzial dystansu, a nie czasu jazdy. Czytaj razem z udzialem oznaczonym/nieznanym.

## Decyzje i historia

Kod jest podstawa tego opisu. Jezeli starsza dokumentacja opisuje inna regule, rozstrzyga aktualny kod.

## Ograniczenia i pulapki

Dokumentacja Strava grupuje klasy inaczej: asfalt, szuter i „ujeby”. To warstwa opisu publikacji i nie jest identyczna z piecioma klasami surowego raportu. Dla czesci odcinkow silnik wnioskuje klase, zamiast miec bezposredni tag.

## Wplywa na / Zalezy od

- Wplywa na: ekran raportu jazdy, a w czesci przypadkow opis publikowany na Stravie.
- Zalezy od: danych FIT, zapisanego raportu oraz danych ModelQ lub dodatkowego zrodla wskazanego przy wyniku.

## Jak czytać warstwę

1. Wybierz warstwę nawierzchni na mapie lub ikonę szczegółów. Na zrzucie głównym mapa jest ustawiona na strefę mocy, a nie nawierzchnię.
2. Raport z 16.10.2026 rozdzielił dystans na: twardą szybką 80,3%, zwykły gravel 1,7%, trudną/wolną 3,5% i ryzyko/niepewne 14,5%.
3. Te cztery udziały sumują się do 100%. Osobne 81,2% oznaczone, 12,7% wnioskowane i 6,1% nieznane opisują pewność/pochodzenie klasyfikacji, nie dodatkowe rodzaje drogi.
4. Jeśli duży fragment jest nieznany lub niepewny, traktuj podział jako niepełny opis podłoża, a nie gwarancję warunków na drodze.

![Mapa i wybór warstwy nad śladem](../img/ekrany/raport-jazdy.png)

## Powiazane hasla

- [Raport jazdy](index.md)
- [Plik FIT](plik-fit.md)
- [Analiza jazdy](analiza-jazdy.md)
- [W′bal](../modelq/wprime-bal.md)
- [TP](../modelq/tp.md)

## Zrodla

['`/opt/qbot/app/qbot3/rides/ride_report_builder.py` — `_surface_and_wind`, `_surface_wind_from_track`', '`/opt/qbot/app/tools/rwgps/route_surface_engine.py` — `analyze_route_surface`', '`qbot_v2.ride_report_data` — `surface`']
