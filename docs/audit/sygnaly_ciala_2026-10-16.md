# Audyt: sygnaly ciala — gdzie co sie liczy i ile razy (2026-10-16)

Zakres: wszystkie algorytmy QBota, ktore z surowych danych ciala (HRV, tetno spocz., sen, Body Battery,
samopoczucie, choroba z Kalendarza) licza liczby lub werdykty: gotowosc, zmeczenie/swiezosc, status dnia,
Trener, QExt2. Metoda: inwentarz kodu (grep po sygnalach i polach) + odczyt formul + sprawdzenie na danych.
Tylko odczyt — zadnych zmian w algorytmach w ramach audytu.

## Lancuch obliczen (kto z czego korzysta)

1. **Gotowosc dnia** `readiness_score` (fitmodel/readiness.py): HRV 40% + RHR 35% + sen 25%,
   kazdy jako z-score (mediana 3 dni vs srednia 60 dni).
2. **Gotowosc z subiektywem** `readiness_effective` = score + samopoczucie (0,15/pkt) + choroba (−0,30), limit ±0,5.
3. **Gotowosc z 3 dni** `readiness_3d` (fitmodel/day_status.py) = srednia 3 dni z `readiness_effective`.
4. **Zmeczenie faktyczne (KANON)** `atl_real` = ATL z treningow + 0,5 × B × CTL (fitmodel/real_load.py),
   B = srednia(−gotowosc_3d, tetno 7d vs mediana 60d, akumulator Body Battery) + infekcja (1,0, ogon 14 dni) + samopoczucie (0,3/pkt).
5. **Zmeczenie "plus"** `atl_plus` (fitmodel/modelq2/hidden_fatigue.py) = ATL z treningow + doplata z gotowosci
   (`readiness_score` jako mnoznik kosztu jazdy) + doplata za samopoczucie/chorobe w dni z jazda. Wariant rownolegly do kanonu.
6. **Status dnia** `day_status`: gotowosc_3d (histereza −0,4/−0,2) LUB tetno 7d > norma ruchoma+1 LUB do 14 dni po infekcji, + skok obciazenia.
7. **Trener**: "dzis wersje minimum" gdy `readiness_effective` < prog ORAZ osobno wg `day_status`.
8. **QExt2 todayFactor**: `readiness_effective` jednego dnia (qbot_api.py).

## Ile razy wchodzi kazdy sygnal do ZMECZENIA FAKTYCZNEGO (kanon)

| sygnal | droga 1 | droga 2 | razem |
|---|---|---|---|
| HRV | gotowosc_3d (40%) | — | 1× |
| sen | gotowosc_3d (25%) | — | 1× |
| **tetno spocz.** | gotowosc_3d (35%, mediana 3d) | skladnik "tetno" (srednia 7d vs mediana 60d) | **2×**, rozne okna — potrafia wskazywac przeciwnie (15–16.10) |
| **samopoczucie** | gotowosc_3d (0,15/pkt, rozmyte srednia 3 dni) | bezposrednio 0,3/pkt | **2×** |
| **choroba** | gotowosc_3d (−0,30) | bezposrednio +1,0 i ogon 14 dni | **2×** |
| Body Battery | akumulator (od 16.10) | — | 1× |
| treningi | ATL z XSS | — | 1× |

Dodatkowo: **podwojne wygladzanie** — sygnaly maja mediane 3 dni, a gotowosc_3d jeszcze srednia 3 dni
(nie podwojne liczenie, ale opoznienie reakcji ~2–3 dni).

## Werdykty (LUB, nie suma)

- **Status dnia**: tetno i choroba wchodza ponownie (przez gotowosc_3d i osobno), ale jako "LUB" — nie podbijaja liczby,
  tylko daja kilka drog do tego samego werdyktu. Akceptowalne, do opisania.
- **Trener**: dwa wyzwalacze tej samej przyczyny (prog gotowosci dnia + status dnia) — dwa komunikaty z jednego powodu
  (np. zmiana nr 216 z 14.10 z sama notatka "Status dnia: zmeczony").

## Warianty zmeczenia/swiezosci w uzyciu

- `tsb_real` (kanon, decyzja 14.10): Forma, raport z jazdy, raport trasy, prognoza formy, wykonalnosc wyprawy, Sezon, narzedzia Alberta — OK (z fallbackiem plus/raw).
- **`fitmodel/load_guard.py` czyta `tsb_plus`** — odstepstwo od kanonu.
- `atl_plus` liczony nadal (warstwa ukrytego zmeczenia) — sam zawiera gotowosc i samopoczucie; dzis nikt go nie sumuje z cialem,
  ale dwa rozne "skorygowane" zmeczenia to ryzyko pomylki.

## Wnioski (do decyzji — nic nie zmienione)

1. Cialo w zmeczeniu faktycznym: kazdy sygnal raz. Propozycja: gotowosc z 3 dni liczona z `readiness_score` (sam obiektyw:
   HRV/RHR/sen), a samopoczucie i choroba tylko bezposrednio; skladnik "tetno" usuniety.
2. `load_guard` na `tsb_real`.
3. Trener: jeden wyzwalacz "wersje minimum" (status dnia), bez osobnego progu gotowosci.
4. Test pilnujacy, ze zaden sygnal nie wchodzi do zmeczenia dwa razy.
5. `atl_plus`: zdecydowac — wygasic jako wariant (zostaje tylko kanon) albo jasno opisac jako audyt.

## WDROZONE 16.10.2026 (decyzja Michala po symulacji 01.03–16.10, 230 dni)

1. `fitmodel/real_load.py`: gotowosc w cialu = srednia 3 dni `readiness_score` (obiektyw); skladnik "tetno" usuniety;
   samopoczucie i choroba tylko bezposrednio; waga choroby ILL_W 1,0 → 1,2 (wplyw infekcji jak przed usunieciem dubla:
   symulacja — dni choroby srednio −18 przed i po). Body Battery = akumulator (wdrozone wczesniej tego dnia).
2. `fitmodel/real_load_guard.py`: 2 sygnaly ciala (gotowosc, akumulator), swiezosc porownywana z ta z samych treningow (tsb_raw).
3. `fitmodel/load_guard.py`: swiezosc kanoniczna (tsb_real) + przeliczenie zmeczenia faktycznego po korekcie jazdy.
4. Trener: jeden wyzwalacz "wersje minimum" = status dnia; prog gotowosci dnia tylko gdy statusu brak (silnik + meta API).
5. `atl_plus`/`tsb_plus`: zostaja jako warstwa audytowa (liczone, nikt nie uzywa ich jako wyniku — wszystkie odczyty to
   COALESCE(real, plus, raw)); nie usuwane, bo publish/daily_job sa na nich zbudowane.
6. Test `tests/test_real_load.py::TestKazdySygnalRaz` pilnuje: gotowosc obiektywna, brak osobnego tetna, samopoczucie i choroba raz.

Wynik na zywo: 16.10 swiezosc +15,8 (rano −41), 12.10 −12,5, 06.10 −24,8. Testy: real_load 10/10, real_load_guard 3/3,
trener_engine 36/36, load_guard 4/4.
Uwaga: srodek infekcji 15–17.09 nadal blisko zera (−3) — w chorobie bez treningow ATL z treningow spada szybko; status dnia
i tak pokazuje wtedy 'zmeczony' (osobny werdykt), a Trener ma dzien pusty + 2 dni lzej z Kalendarza.
