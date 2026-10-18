---
tytul: Koła i opony
dzial: garaz
typ: pojecie
opis: Garaż zapisuje zestawy kół, ich opony oraz to, w którym rowerze są obecnie zamontowane.
tagi: [kola, opony, rower, montaz, szerokosc]
synonimy: [opony rowerowe, wheelset, tires, kola gravelowe, opona przod tyl]
skroty: []
gdzie_widac: [Garaż, Analiza trasy]
liczby: [16 opon, 6 opon zamontowanych, 45 mm, 50 mm, 55 mm]
zalezy_od: [rowery-komponenty]
wplywa_na: [wybor-roweru, ../pogoda/ubior]
zrodla_kodu: [docs/GARAZ.md, qbot3/garage_wheels.py, qbot3/routes/gear_kit.py]
aktualizacja: 18.10.2026
---

# Koła i opony

## Co to jest

W Garażu koło to osobny zestaw, który można przypisać do roweru. Opona jest przypisana do zestawu oraz do przodu albo tyłu. Dzięki temu rekomendacja roweru może opisać opony faktycznie zapisane przy jego kołach.

## Po co

Przed jazdą sprawdź, czy zapisane koła i opony odpowiadają temu, co jest fizycznie założone. Przy zmianie opon popraw wpisy w Garażu. Jeśli koło zostało przełożone, sprawdź jego przypisanie do roweru; nazwa roweru i szerokość opony pomagają ocenić, czy propozycja na trasę ma sens.

## Skąd dane

W odczycie tylko do odczytu z 18.10.2026 było 16 wpisów opon. Sześć miało stan „zamontowana”: para na Grailu, para przy drugim zestawie Zipp bez wskazanego roweru oraz para na Monsterze. Pozostałe dziesięć było poza aktualnym montażem. Taki stan bazy opisuje zapis, nie czujnik mierzący oponę.

## Jak liczone

1. Wpisz koło jako część roweru albo pozostaw je na półce jako zapas. Przykładowy aktywny zapis to zestaw Zipp 303 S XPLR przypisany do Graila.
2. Przypisz oponę do zestawu i oznacz przód lub tył. W odczycie z 18.10.2026 zestaw Graila miał z przodu Schwalbe G-One Pro RX 50 mm, a z tyłu G-One Pro R 50 mm.
3. Przy kolejnym zestawie opony mogą mieć inne rozmiary. Zipp 303 S „Zestaw #2” miał zapisane G-One Pro RS: 50 mm z przodu i 45 mm z tyłu. Sam wpis nie wskazywał aktualnego roweru.
4. Monster miał parę Continental RaceKing TanWall 55 mm, z przodu i z tyłu. Odczyt 18.10.2026 łączył tę parę z zestawem Alexrims w Monsterze.
5. Przy wyborze roweru na trasę system pokazuje zapisane przy nim opony. Nie oblicza z tych danych ciśnienia; brak danych o obręczy lub masie nie jest zastępowany zgadywaną wartością.

```mermaid
flowchart LR
  Kolo[Zestaw kół] --> Rower[Rower albo półka]
  Opona[Wpis opony] --> Miejsce[Przód lub tył]
  Miejsce --> Zestaw[Opona przypisana do koła]
  Zestaw --> Podglad[Opony zapisane przy rowerze]
  Rower --> Podglad
  Podglad --> Trasa[Opis sprzętu na trasę]
  Zmiana[Przekładka z czujnikiem prędkości] --> Historia[Historia montażu]
  Historia --> Rower
```

## Gdzie to widać

Koła i opony są w zakładce Garażu poświęconej kołom. W karcie Sprzęt Analizy trasy widać opony przypisane do proponowanego roweru. Do orientacji po głównej stronie służy [zrzut Garażu](../img/ekrany/garaz.png): pokazuje karty rowerów i tabelę części, ale nie otwartą zakładkę kół. Lista zrzutów jest w [indeksie ekranów](../img/ekrany/indeks.md).

## Jak czytać

„Zamontowana” oznacza stan zapisany w Garażu. „W garażu” oznacza, że wpis nie jest obecnie przypisany do przodu ani tyłu koła. Szerokość w milimetrach pochodzi z wpisu opony. Jeżeli wpis koła nie ma roweru, rekomendacja nie powinna przedstawiać go jako wyposażenia konkretnego roweru.

## Decyzje i historia

Każde miejsce opony jest oddzielne: przód i tył mogą różnić się modelem lub szerokością. Jedno miejsce na kole jest przeznaczone dla jednej części danego rodzaju; zapis nowej części na zajętym miejscu odsyła poprzednią do zapasu. Historia przekładek pomaga zachować kolejność zmian.

## Ograniczenia i pułapki

- Baza nie potwierdza, czy fizycznie wykonano zmianę, jeśli nie ma późniejszego wpisu lub odczytu rozpoznanego czujnika prędkości.
- Na 18.10.2026 drugi zestaw Zipp miał aktywne opony, ale jego wpis nie wskazywał przypisanego roweru. To ograniczenie danych, nie potwierdzony błąd serwisu.
- Sama szerokość nie wystarcza do obliczenia ciśnienia.
- Zmiana statusu opony nie musi oznaczać zmiany wpisu samego koła.

## Wpływa na / Zależy od

**Wpływa na:** listę opon w propozycji roweru na trasę i opis wyposażenia.

**Zależy od:** przypisania koła do roweru, opony do koła oraz pozycji przód/tył.

## Powiązane hasła

- [Rowery i komponenty](rowery-komponenty.md)
- [Wybór roweru do trasy](wybor-roweru.md)
- [Sprzęt w Garażu](sprzet.md)
- [Dobór ubioru](doradca-ubioru.md)

## Zrodla

- `/opt/qbot/app/docs/GARAZ.md` — opony i przypisanie do kół.
- `/opt/qbot/app/qbot3/garage_wheels.py` — historia montażu i reakcja na czujnik prędkości.
- `/opt/qbot/app/qbot3/routes/gear_kit.py` — odczyt opon przy rowerze do rekomendacji.
- Odczyt `garage.db` z 18.10.2026 — 16 opon, bieżące przypisania i szerokości.
- `img/ekrany/garaz.png`, `img/ekrany/indeks.md` — zrzut i wykaz ekranów.
