---
tytul: Cele treningowe
dzial: trener
typ: strona
opis: Cele treningowe określają priorytety i terminy, które Trener może uwzględnić w planie sezonu.
tagi: [cele, trening, priorytet, wyprawa, termin]
synonimy: [cel treningowy, cel A, wyprawa, goal, start]
skroty: []
gdzie_widac: [Trening, Cele, Kalendarz]
liczby: [data, godziny]
zalezy_od: [trener/sezon, trener/trasy, trener/kalendarz]
wplywa_na: [trener/sezon, trener/plan-tygodnia, trener/kalendarz]
zrodla_kodu: [qbot_trener_engine.py season_weeks, qbot_trener_api.py, qbot_v2.trainer_goal]
aktualizacja: 18.10.2026
---

# Cele treningowe

Cele mówią Trenerowi, na co przygotowujesz się w danym terminie. Mogą dotyczyć wyprawy, długiej jazdy lub innego celu. Priorytet A może przesunąć etapy sezonu, aby zostało miejsce na przygotowanie, lżejszy okres przed celem i odpoczynek po nim.

## Po co

Wpisz cel z datą oraz realnym zakresem. Jeśli to wyjazd rowerowy, przypnij trasę albo wydarzenie kalendarza, jeżeli jest dostępne. Dzięki temu plan może uwzględnić konkretną jazdę. Nie traktuj samego wpisania nazwy celu jako rezerwacji całego czasu w kalendarzu.

## Jak działa

1. W zakładce Cele wybierasz rok i dodajesz pozycję. Na ekranie możesz określić rodzaj, nazwę, daty i ważność.
2. Odczyt celów z bazy 18.10.2026 pokazuje m.in. wyprawę „Wyprawa po złoto”: 13.09.2027–22.09.2027, 10 dni, 650 km, 15 000 m przewyższenia, priorytet A. Wpis jest aktywny. To cel zapisany przez właściciela, a nie automatycznie potwierdzony plan jazd.
3. Silnik bierze pod uwagę cele wyprawowe o priorytecie A przy wyznaczaniu końca bazy oraz tygodni przygotowania i regeneracji.
4. Odczyt tej samej listy zawiera też cele priorytetu B: m.in. wyprawę „Preludium sezonu” 26.03.2027–28.03.2027 na 250 km i 1 500 m. Silnik sezonu uwzględnia cele A przy wyznaczaniu bloków wokół wypraw; wpisy B nadal pozostają w celach i ich statusach.
5. Cel z przypisaną trasą może być widoczny jako trening rowerowy w Kalendarzu. Szczegóły opisuje [Trasa jako trening](trasy.md).

```mermaid
flowchart TD
  Wpis[Cel i termin] --> Priorytet[Rodzaj i ważność]
  Trasa[Trasa lub wydarzenie] --> Powiazanie[Powiązanie z Kalendarzem]
  Priorytet --> Sezon[Wyznaczenie faz sezonu]
  Powiazanie --> Jazda[Planowana jazda]
  Sezon --> Plan[Godziny i sesje tygodnia]
  Jazda --> Plan
  Plan --> Widok[Kalendarz Treningu]
```

![Widok tygodnia z etykietą sezonu i celem 5 godzin](../img/ekrany/trening.png)

Na pokazanym tygodniu wartość „Cel z Sezonu” to 5 h. To przykład celu objętości tygodnia, nie cel sportowy z zakładki Cele. Zakładka Cele przechowuje wydarzenia i priorytety, a kafel Kalendarza pokazuje tygodniową liczbę godzin wynikającą z fazy.

## Jak czytać

Cel A jest istotnym punktem sezonu, ale nie gwarantuje konkretnej liczby godzin ani wyniku sportowego. Cel sezonu w kafelku tygodnia to planowana objętość tygodnia. Jeśli termin się zmienił, zaktualizuj go; nie zakładaj, że sam trening zostanie przesunięty razem z wydarzeniem.

Na ekranie Cele możesz przełączyć rok, aby oddzielić stare wydarzenia od przyszłych. Po zmianie priorytetu sprawdź ponownie zakładkę Plan, ponieważ cel A jest wejściem do układania faz. Przy celu z trasą zweryfikuj również datę i liczbę dni w Kalendarzu. Zrzut października pokazuje tygodniowy cel sezonu 5 h, ale nie listę celów. Powyższe przykłady pochodzą z odczytu bazy z 18.10.2026.

## Ograniczenia

Cel może nie zawierać kompletnej trasy lub informacji o dostępności. W takiej sytuacji plan korzysta tylko z danych, które ma. Odczyt z 18.10.2026 potwierdził aktywne cele, ale nie dowodzi, że przypięto do nich trasy ani że terminy nadal odpowiadają zamiarom właściciela. Zrzut dostarczony do tego hasła nie pokazuje zakładki Cele.

Jeśli widzisz w Kalendarzu nazwę wyprawy, ale nie widzisz oczekiwanej jazdy, otwórz wpis i sprawdź, czy powiązano go z trasą oraz wskazano odpowiednie dni. Zmiana terminu celu może zmienić fazy i plan kolejnych tygodni; sprawdź plan po zapisaniu.

## Wpływa na / Zależy od

Cele priorytetu A wpływają na fazy sezonu; cele z przypisaną trasą mogą wpływać na plan dnia. Szczegóły sezonu, tras i terminów są opisane osobno.

## Powiązane hasła

- [Sezon](sezon.md)
- [Plan tygodnia](plan-tygodnia.md)
- [Trasy w treningu](trasy.md)
- [Kalendarz](kalendarz.md)

## Zrodla

- `/opt/qbot/web/public/trener.js` — `rGoals`, formularz celów i pobieranie podsumowania trasy.
- `qbot_trener_engine.py` — `season_bounds`, `season_weeks`, `build_context`.
- `qbot_v2.trainer_goal` — zapis celów i ich priorytetu.
- `docs/TRENER.md` — reguły celów, sezonu i edytora.
