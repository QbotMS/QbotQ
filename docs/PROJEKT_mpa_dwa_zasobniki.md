# ModelQ — projekt: ksztalt MPA z osobnym czlonem nerwowo-miesniowym

Data: 2026-07-26. Status: **PROJEKT DO ZATWIERDZENIA, nie wdrozony.**
Kontekst: `DECISIONS.md` 2026-07-26 (ustalenie 5 — slepa sciezka `extract.py`).

---

## 1. Co jest zle dzisiaj

`fitmodel/modelq2/mpa.py` liczy dostepna moc jedna linijka:

```
MPA = TP + (PP - TP) * (Wbal / W')
```

Dwa punkty brzegowe sa bezsporne: pelny bak -> MPA=PP, pusty -> MPA=TP.
Miedzy nimi poprowadzono **prosta** — to zalozenie, nie wynik dopasowania.
Nic w kodzie nie kalibruje tego ksztaltu na danych Michala.

**Gdzie sie lamie.** Model zaklada, ze moc sprintu spada proporcjonalnie do
opróznienia baku beztlenowego. Sprint 5-sekundowy ciagnie jednak glownie
z fosfokreatyny i ukladu nerwowo-miesniowego — to inny zasobnik, odbudowywany
w minuty spokojnej jazdy, niezaleznie od ksiegowania W'.

**Dowod (jazda 2026-07-04, 11:59:46):**
- model dawal dostepne **563 W** (Wbal na 42%)
- realnie pojechane **745 W**
- zeby wzor to wytlumaczyl, Wbal musialby byc pelny w 66%

Solver domykajacy taka roznice jedyna wolna galka (HIE) rozdyma bak do
**35-67 kJ** przy sensownych 13-22 kJ. Stad slepa sciezka `extract.py`.

**Uwaga: sam Wbal jest DOBRY.** Model Skiby z dynamicznym tau zgadza sie
z Karoo do 0,49 pp. Wadliwa jest wylacznie liniowa nakladka Wbal -> MPA.

---

## 2. Proponowany ksztalt — dwa zasobniki

```
MPA = TP + A_wprime * (Wbal / W') + A_pcr * (PCrbal / PCr)

warunek brzegowy:  A_wprime + A_pcr = PP - TP
```

- **W'** — zasobnik beztlenowy mleczanowy. Pojemnosc W', regeneracja jak dzis
  (Skiba, tau = 546*exp(-0.01*(TP-P)) + 316). Odpowiada za wysilki od ~30 s wzwyz.
- **PCr** — zasobnik fosfokreatynowy. Pojemnosc rzedu **3-5 kJ**, regeneracja
  SZYBKA (tau ~20-40 s). Odpowiada za sprinty 1-15 s.

Sprawdzenie na przypadku z 4.07 (Wbal 42%, PCr odbudowany po spokojnej jezdzie):
przy PP-TP = 768 W i podziale A_pcr = 0,7 -> MPA = 245,5 + 230*0,42 + 538*1,0
= **880 W** >= 745 W. Przebicie znika bez ruszania HIE.

---

## 3. Dane do kalibracji (wyciagniete 2026-07-26, rok wstecz)

Koperta mocy vs obecny model 2-param `Signature.power_for_duration`:

| okno | rekord | model 2p | roznica | praca nad TP |
|-----:|-------:|---------:|--------:|-------------:|
| 1 s | 2131 | 1002 | +1129 | 1,9 kJ |
| 2 s | 1247 | 990 | +257 | 2,0 kJ |
| 5 s | 1161 | 955 | +206 | 4,6 kJ |
| 10 s | 800 | 902 | -102 | 5,5 kJ |
| 20 s | 623 | 811 | -188 | 7,5 kJ |
| 30 s | 563 | 737 | -174 | 9,5 kJ |
| 60 s | 417 | 585 | -168 | 10,3 kJ |
| 120 s | 367 | 440 | -73 | 14,6 kJ |
| 300 s | 280 | 325 | -45 | 10,3 kJ |
| 600 s | 266 | 285 | -19 | 12,3 kJ |
| 1200 s | 248 | 265 | -17 | 3,0 kJ |
| 1800 s | 232 | 259 | -27 | **-24,3 kJ** |
| 3600 s | 214 | 252 | -38 | **-113,4 kJ** |

Kalibracja PCr: z okien 1-15 s (praca nad TP ~2-5 kJ) i z tempa odbudowy
miedzy powtarzanymi sprintami w tej samej jezdzie (mamy 1 Hz w `activity_record`).

---

## 4. DWA PROBLEMY POWAZNIEJSZE, ktore wyszly przy okazji

### 4a. TP jest wyzsze niz najlepsza godzina Michala w calym roku

TP = **245,5 W**, a najlepsze realne wyniki z 365 dni to
**1800 s = 232 W** i **3600 s = 214 W**. Praca nad progiem w tych oknach jest
UJEMNA (-24 kJ, -113 kJ). Prog, ktorego nie da sie utrzymac przez pol godziny,
nie jest progiem.

Dwie mozliwosci, obie do sprawdzenia:
1. TP jest zawyzone (pochodzi z kotwic przepisanych z Xerta, patrz 4c),
2. Michal po prostu nigdy nie jedzie maksymalnie przez 30-60 min (gravel/turystyka),
   wiec rekordy sa submaksymalne i nie sa dowodem przeciw TP.

**BLAD W PIERWSZEJ WERSJI TEGO DOKUMENTU (poprawione 2026-07-26).**
Bylo tu napisane, ze sprawy nie da sie rozstrzygnac bez celowego wysilku
20-30 min na maksa. To sprzeczne z ZALOZENIEM FUNDAMENTALNYM projektu:
ModelQ ma wyznaczac forme z NORMALNEJ jazdy, bez testow maksymalnych.
Model, ktory kaze uzytkownikowi zrobic sobie test FTP, jest zbedny.

**Rozstrzygniecie BEZ testu — dwie niezalezne metody, obie z juz posiadanych danych.**

**Metoda 1: kotwica z drogi dla TP (analogiczna do tej, ktora juz dziala dla W').**
Gdy Wbal spada do zera, bak beztlenowy jest pusty i cala moc pochodzi z toru
tlenowego. Jesli w tym stanie zawodnik JEDZIE DALEJ przez >=60 s na mocy X,
a Wbal nie schodzi glebiej — to znaczy, ze X miesci sie w progu, czyli **TP >= X**.
Maksymalne takie X w oknie czasowym daje DOLNE OGRANICZENIE TP z normalnej jazdy.
To dokladnie ten sam mechanizm, ktory dzis zasila `wprime_source`
("kotwica z drogi: Wbal=0% na jezdzie 2026-07-22 (51s)").
Material gotowy: 4 jazdy z Wbal=0 w ostatnich 45 dniach (20.06, 4.07, 6.07, 12.07).

**Metoda 2: dryf tetna przy dopasowanej mocy (juz zaimplementowana w QExt2).**
Dlugi odcinek na stalej mocy P bez ucieczki tetna => P jest ponizej progu.
Najwyzsze P z niedryfujacym tetnem to drugie, niezalezne dolne ograniczenie TP.

Jesli obie metody wskaza sufit wyraznie ponizej 245,5 W — TP jest zawyzone
i wiadomo o ile. Zero dodatkowych jazd, zero testow.

### 4b. `mmp_1_w = 2131 W` to artefakt

2131 W na 1 s przy 100 kg to wynik z poziomu swiatowego sprintu torowego.
PP sygnatury = 1014 W. Rekord 1 s jest ponad dwukrotnie wyzszy — to szpilka
mocomierza, nie wysilek. **Do odfiltrowania przed kalibracja PCr**, inaczej
zatruje caly krotki koniec. Podobnie podejrzane 2 s = 1247 W.

### 4c. Kotwice z Xerta

`modelq2_anchor` to wartosci przepisane z Xerta. Cala sygnatura MQ2, a wiec
i TP z punktu 4a, stoi na benchmarku, ktory wg wlasnej zasady projektu nie
powinien byc inputem. Do rozstrzygniecia osobno.

---

## 4d. POTWIERDZENIE Z DANYCH (2026-07-27) -- pojemnosc PCr zmierzona

Test: przeliczenie wszystkich wyplukan z roku przy W' PRZYBITYM na 24 kJ
(wartosc zmierzona z drogi). Cel: rozdzielic "bak za maly" od "prog za niski",
co przy W' zmiennym bylo niemozliwe.

**Wynik: z 11 jazd z niedomiarem 4 znikaja calkowicie** (18.03, 31.05, 5.06, 4.07).
W tym najwazniejsza -- 2026-06-05, niedomiar 4.6 kJ utrzymany przez **61 s** --
znika do zera. To jedyne dlugie zdarzenie w calym zbiorze.

**Resztka na 7 jazdach ma jedna wspolna ceche: WSZYSTKIE <=30 s.**

    data        resztka   czas   moc
    2026-03-03   3.9 kJ    22s   417 W
    2026-06-20   3.4 kJ    28s   372 W
    2026-07-06   2.0 kJ    14s   390 W
    2026-03-22   1.1 kJ    10s   355 W
    2026-03-10   0.3 kJ     6s   303 W
    2025-12-27   0.3 kJ     7s   294 W
    2026-03-11   0.0 kJ     1s   290 W

**WNIOSEK 1 -- TP sie broni.** Gdyby prog byl zanizony, przekroczenia siedzialyby
w DLUGICH wysilkach (prog dotyczy tego, co da sie utrzymac). Zostaly wylacznie
zrywy kilkunastosekundowe. Zarzut, ze 244 W jest zawyzone, upada.
UWAGA: to NIE jest dowod poprawnosci TP -- ograniczenia OD GORY nadal nie ma
i bez wysilku do granicy nie bedzie. Brak przeciwdowodu != dowod.

**WNIOSEK 2 -- W' = 24 kJ potwierdzone druga, niezalezna droga.** Kasuje wszystkie
niedomiary w wysilkach dluzszych niz 30 s.

**WNIOSEK 3 -- POJEMNOSC PCr ZMIERZONA: ~4 kJ.** Sekcja 2 tego dokumentu zakladala
"rzedu 3-5 kJ" na wyczucie. Dane: 0.3-3.9 kJ, maksimum 3.9 kJ. Zalozenie trafione,
teraz jest to liczba z jazd Michala, a nie z podrecznika.

    PCr_CAPACITY_KJ ~= 4.0    (z maksimum resztki; dolne ograniczenie)

Podzial A_pcr / A_wprime nadal do kalibracji -- resztka mowi o POJEMNOSCI
zasobnika, nie o tym, jaka czesc (PP - TP) z niego pochodzi.

## 5. Kolejnosc prac (propozycja)

1. **Odfiltrowac szpilki** z krotkiego konca (1-2 s) — warunek wstepny czegokolwiek.
2. **Rozstrzygnac 4a BEZ testu** — zaimplementowac kotwice z drogi dla TP
   (max moc utrzymana >=60 s przy Wbal=0) + odczyt z dryfu tetna przy dopasowanej
   mocy. Obie metody na juz posiadanych jazdach. ZADNYCH testow maksymalnych.
3. **Skalibrowac PCr** (pojemnosc, tau, podzial A_pcr/A_wprime) na oknach 1-15 s
   i na odbudowie miedzy sprintami z `activity_record`.
4. **Wdrozyc dwuzasobnikowe MPA** w `mpa.py` za flaga, rownolegle ze starym.
5. **Przewalidowac** na 4 jazdach z przebiciami (20.06, 4.07, 6.07, 12.07):
   czy przebicia znikaja bez rozdymania HIE.
6. Dopiero wtedy **`extract.py`** — przebicia -> HIE.

**Nie zaczynac od kroku 6.** Na obecnym ksztalcie MPA da bzdury, co juz
udowodniono liczbowo.

---

## 6. Czego ten projekt NIE rozwiazuje

Przebicia trwaja <=69 s, wiec nawet po naprawie ksztaltu beda wyznaczac
**HIE, nie TP**. TP pozostanie na dryfie od kotwicy. Punkt 4a jest wazniejszy
dla LTP niz cala ta przebudowa: LTP = TP - HIE/400, a to TP odpowiadalo za
14,6 W ostatniego rozjazdu, nie HIE.

**ZASADA NADRZEDNA TEGO PROJEKTU (i calego ModelQ): zadnych testow maksymalnych.**
Forma ma wynikac z jazd, ktore i tak sa robione. Kazda propozycja zaczynajaca sie
od "niech uzytkownik zrobi test" jest z definicji bledna — to znak, ze model
nie potrafi tego, po co powstal. Jesli danych brakuje, wlasciwa odpowiedz to
uczciwe null + zakres + confidence, a nie zadanie od uzytkownika wysilku.
