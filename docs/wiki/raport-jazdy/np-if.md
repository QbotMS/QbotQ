---
tytul: NP i IF
dzial: raport-jazdy
typ: liczba
opis: Pokazuje moc znormalizowaną i jej stosunek do progu użytego przez raport.
tagi: [np, if, moc, próg, intensywność]
synonimy: [np, if, normalized power, intensity factor, moc znormalizowana]
skroty: [NP, IF, TP]
gdzie_widac: [Raport jazdy, Analiza AI]
liczby: []
zalezy_od: [plik-fit, ../modelq/tp, index]
wplywa_na: [index, analiza-ai]
zrodla_kodu: [qbot3/rides/ride_report_builder.py, _np, _load, qbot_v2.fitmodel_daily]
aktualizacja: 18.10.2026
---

# NP i IF

## Co to jest

NP (moc znormalizowana; [słowniczek](../slowniczek.md#np)) uwzględnia mocne fragmenty jazdy silniej niż zwykła średnia. IF (stosunek NP do progu; [słowniczek](../slowniczek.md#if)) pokazuje, jak NP wypada względem progu użytego w raporcie.

## Po co

Pomaga porównać równą jazdę z jazdą zawierającą mocne fragmenty. Nie zastępuje wykresu ani opisu całego wysiłku.

## Skad dane

Moc pochodzi z zapisu aktywności. Próg pochodzi z ModelQ. W tym haśle używam określenia TP (próg mocy; [słowniczek](../slowniczek.md#tp)).

## Jak liczone krok po kroku

1. Zapis jazdy z 18.10.2026 ma średnią moc 154 W i NP (moc znormalizowaną; [słowniczek](../slowniczek.md#np)) 175 W.
2. Próg TP (próg mocy; [słowniczek](../slowniczek.md#tp)) wynosi 241 W.
3. Dla 18.10.2026 niezaokrąglone wartości wynoszą NP 174,505 W i TP 240,700 W. Iloraz to 0,72499, a więc IF (stosunek NP do progu; [słowniczek](../slowniczek.md#if)) 0,72. Na ekranie widać już zaokrąglone 175 W i 241 W; ich dzielenie daje inną setną.
4. Oznaczenie ModelQ przy progu wskazuje jego pochodzenie; raport przedstawia ten próg jako TP.

![Kafle mocy i wykres z widoku raportu](../img/ekrany/raport-jazdy.png)

Porównanie trzech wartości z raportu: [wykres mocy i progu z 18.10.2026](../img/raport-jazdy-moc-20261018.svg). Długość słupka pokazuje liczbę watów, nie czas trwania wysiłku.

## Gdzie to widać

W karcie mocy raportu oraz w wykresie, gdy seria mocy jest włączona.

## Jak czytać

IF około 0,72 opisuje intensywność całej jazdy względem progu użytego w raporcie. Nie jest oceną, czy jazda była „dobra” ani zaleceniem treningowym. Gdy IF jest wyższe, a jazda długa, sprawdź również czas, przebieg mocy i zapas wysiłku. Dwie jazdy o tym samym IF mogą mieć inne zrywy i inne przerwy.

W praktyce porównuj wskaźnik między jazdami tylko wtedy, gdy progi są zbliżone i dane są kompletne. Jeśli próg zmienił się między dniami, identyczna moc NP może dać inny IF. Sam IF nie pokazuje, czy moc była równa: do tego służy przebieg na wykresie.

Sprawdź też czas aktywności. Ten sam wskaźnik przy krótkiej i długiej jeździe nie oznacza takiej samej ilości wykonanej pracy. Dystans, czas, przebieg tętna i zapas wysiłku uzupełniają obraz, ale nie zmieniają definicji IF.

Wykres w zrzucie ma przełączane serie. Włącz moc i tętno, a potem wskaż odcinek na mapie: łatwiej zobaczyć, czy wyższy wysiłek przypadał na podjazd, trudne podłoże czy przyspieszenie. Raport nie wyświetla tu kolorowych progów IF; kolory śladu odpowiadają wybranej warstwie mapy.

<details>
<summary>Wzór</summary>

NP to czwarty pierwiastek ze średniej czwartej potęgi średnich mocy z 30 sekund. IF = NP ÷ TP. Wzory są skrótem obliczenia; wynik z ekranu może różnić się o 0,01 od rachunku na pełnych, zaokrąglonych watach.

</details>

Różnica 0,72 wobec rachunku z 175 W i 241 W została wyjaśniona: dokładny próg wynosi 240,7 W, a NP odtworzona z próbek 174,505 W. Nie jest to błąd serwisu.

## Powiazane hasla

- [Raport jazdy](index.md)
- [Plik FIT](plik-fit.md)
- [Analiza jazdy](analiza-jazdy.md)
- [W′bal](../modelq/wprime-bal.md)
- [TP](../modelq/tp.md)

## Wplywa na / Zalezy od

- Wpływa na: podsumowanie mocy w raporcie oraz wybrane fakty przekazywane do analizy AI.
- Zależy od: próbek mocy z jazdy i progu ModelQ dostępnego dla dnia jazdy.

## Zrodla

- `/opt/qbot/app/qbot3/rides/ride_report_builder.py` — `_np`, `_load`, `_modelq_form`.
- `qbot_v2.fitmodel_daily` — dzienny próg ModelQ.
- `qbot_v2.ride_report_data` — zapisane `load.np_w`, `load.if` i próg.
