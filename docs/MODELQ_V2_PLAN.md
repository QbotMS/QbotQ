# ModelQ v2 — projekt implementacji (papier przed kodem)

> Powstaje PO: MODELQ_V2_XERT_SPEC.md (logika Xerta) + decyzji "od nowa, obok, bez dziedziczenia".
> Ten plik = projekt STRUKTURY MQ2 do zatwierdzenia przed pisaniem kodu.
> Status: SZKIC do akceptacji Michala (2026-07-08).

## Dowody wykonalnosci (zrobione 2026-07-08, skrypty testowe, nic nie zapisane)
Test MPA od zera na jezdzie 6.07 (Xert: 1 max effort 00:19):
- [OK] Mechanika MPA liczy sie tick-po-ticku z activity_record 1Hz, z poprawnym CP (cp_v3),
  BEZ starego kodu. Wzor Filar 1 dziala.
- [OK] Wykrywanie przebic jako ZDARZENIA (ciagle fragmenty), nie sekundy. Przy W'=20kJ/PP=1000
  -> 7 zdarzen; przy W'=8 -> 38 zdarzen. Trend potwierdza self-correction: nizsze W' = wiecej
  falszywych przebic.
- [WNIOSEK] W' i przebicia sprzezone. Ekstrakcja sygnatury = iteruj (TP,W',PP) az zdarzen ~0-1.
  To rdzen Filaru 2+3. Wykonalne.
- [DO DOPRACOWANIA w implementacji] dokladny prog przebicia (margin, min. czas trwania,
  filtr artefaktow 1s). 7 zdarzen -> trzeba zejsc do ~1 dopasowaniem sygnatury + filtrem.

## Struktura pakietu: fitmodel/modelq2/
Kazdy modul = jeden filar. Zero importow ze starego fitmodel (poza wspoldzielonym _db_connect).

    modelq2/
      __init__.py
      signature.py     # Filar 0: klasa Signature(TP, HIE, PP) + walidacja, serializacja
      mpa.py           # Filar 1: replay MPA tick-po-ticku z 1Hz. CZYSTY, bez cf-oddychania.
                       #   wejscie: rows[(ts,power)], Signature -> szereg MPA + min_wbal + Wbal(t)
      breakthrough.py  # Filar 2: wykrywanie zdarzen przebicia (nie sekund) + filtr artefaktow
      extract.py       # Filar 2+3: ekstrakcja sygnatury z jazdy (iteruj az zdarzen ~0-1)
      xss.py           # Filar 4: XSS Low/High/Peak z work-allocation, spojne z MPA. JEDEN silnik.
      training_load.py # Filar 5: 3 osobne TL (Low/High/Peak) + Recovery Load + Form
      decay.py         # Filar 3: predykcja sygnatury z TL + zanik (jak cp_v3, ale 3 parametry)
      progression.py   # spina: dzien-po-dniu sygnatura z przebic + decay + dryf, trickle-down
      io.py            # odczyt activity_record (read-only), zapis do modelq2_* (izolowane)

## Tabele (izolowane, prefiks modelq2_)
    qbot_v2.modelq2_signature      # dzienna sygnatura
      day PK, tp_w, hie_kj, pp_w,
      source (breakthrough|decay|seed), bt_medal (0-3), confidence,
      tl_low, tl_high, tl_peak, rl_low, rl_high, rl_peak,
      form_low, form_high, form_peak, updated_at
    qbot_v2.modelq2_ride           # per jazda
      external_id PK, ride_date, min_wbal_pct, bt_events, max_exceed_w,
      xss_low, xss_high, xss_peak, xss_total,
      sig_tp_before, sig_tp_after, ... (co zmienilo przebicie)

## Kolejnosc budowy (kazdy krok = dowod przed nastepnym)
1. signature.py + mpa.py + test: MPA na 6.07 = jak w skrypcie wykonalnosci. (mamy dowod)
2. breakthrough.py: zdarzenia + filtr. Cel: 6.07 -> ~1 zdarzenie przy dobrej sygn.
3. extract.py: z jednej jazdy wyciagnij (TP,W',PP). Walidacja: 20.06 i 6.07 (Xert MaxEff niezerowe).
4. xss.py: Low/High/Peak. Walidacja: proporcje vs Xert CSV (6.07: 82.6/7.9/1.5).
5. training_load.py + decay.py: 3 systemy. Walidacja: dryf TP vs Xert progresja.
6. progression.py: pelny szereg 2025->dzis. Walidacja: cala krzywa TP/HIE/PP vs Xert CSV.
7. Dopiero po walidacji: podpiac konsumentow (strangler), stary usunac.

## Zasady (z decyzji architektonicznej)
- Zero kopiowania starego kodu. Stary = benchmark.
- CP wejsciowy: NIGDY ftp_est. Wlasna sygnatura MQ2 (na seed: cp_v3).
- Kazdy krok waliduje sie na danych (Xert CSV + activity_record) przed nastepnym.
- Osobny job na czas kalibracji, nie daily_job.

## Otwarte pytania do rozstrzygniecia w trakcie
- PP: ktore zrodlo? (mmp_5=822 vs mmp_1=1194 vs Xert=1000). Prawdopodobnie granica krzywej
  MPA t->0 kalibrowana do Xert, nie surowe MMP.
- tau: stale Skiba (untrained) vs personalizacja Michala. Zaczac od Skiba, kalibrowac potem.
- margin/filtr przebicia: dobrac na 6.07+20.06 tak by dac liczbe zdarzen zgodna z Xert MaxEff.


---

## KOREKTA (2026-07-08) -- MPA liniowe ZOSTAJE; przebicie = jazda nad MPA po wyczerpaniu

Badanie na 6.07 (ground truth: rider CZUL przebicie W' w sprincie ~10:30, Xert MaxEff 00:19):
- wbal dochodzi do 0 DOKLADNIE RAZ, o 10:30:45, w oknie odczutego przebicia -- niezaleznie
  od ksztaltu MPA (k w (wbal/W')^k nie zmienia KIEDY wbal=0, bo to bilans energii).
- Wczesniejszy trop "liniowe MPA zle, trzeba nieliniowe" byl PRZEDWCZESNY: ksztalt zmienia
  max_exceed tylko 232->184W, nie usuwa go. To NIE problem ksztaltu.
- Prawdziwy obraz: max_exceed (+184W) wystepuje ~10:31:55, PO wyczerpaniu W' (10:30:45).
  Czyli: po oproznieniu W' rider dalej ciagnie ~430W, a model (MPA=TP=244 przy pustym baku)
  mowi "za duzo o 184W". To jest FIZJOLOGICZNY SYGNAL PRZEBICIA: rider pojechal powyzej tego,
  co sygnatura tlumaczy -> HIE (a moze i TP/PP) sa za niskie. Zgodne z odczuciem ridera.

WNIOSEK:
- MPA liniowe (mpa.py) ZOSTAJE na tym etapie. Nie przepisujemy.
- Definicja przebicia (breakthrough.py): ciagle wyczerpanie = JEDNO zdarzenie (nie liczyc
  kazdej sekundy). Dodatkowo: exceed>0 PO wyczerpaniu W' = sygnal "podnies sygnature".
- Krok 3 (extract): podnos HIE (potem TP/PP) az moc miesci sie w MPA (exceed~0) w najmocniejszym
  wysilku. To da prawdziwe HIE z przebic (rozwiazuje 8 vs 22 od strony danych ridera, nie MMP).
- Ksztalt MPA (nieliniowy) -- ewentualnie pozniej, gdy wiecej dni z przebiciami do kalibracji.
  Na teraz brak dowodu ze potrzebny.


---

## ZMIANA KOLEJNOSCI (2026-07-08) -- forma PRZED W' (decyzja Michala: "optymalnie, nigdy na skroty")

DOWOD ze stara kolejnosc byla zla: probowano wyekstrahowac W' z pojedynczej jazdy (krok 3),
ale kalibracja tau na 2 dniach pokazala SPRZECZNOSC:
  6.07 (rider mial ZAPAS): zeby min_wbal>0 trzeba mult<=0.25
  20.06 (byl MAX effort):  zeby min_wbal~0 trzeba mult>=0.5
Zaden pojedynczy tau nie spelnia obu -> bo to NIE problem tau.

PRAWDZIWA PRZYCZYNA: 6.07 i 20.06 to DWA ROZNE STANY FORMY, nie jedna sygnatura.
Xert ma dla nich rozne sygnatury (20.06: TP=251/HIE=22.7 swiezy; 6.07: TP=244/HIE=20.5 po bloku).
Sygnatura danego dnia = funkcja FORMY (Training Load + Signature Decay), ktora zalezy od
tygodni wczesniej. Nie da sie czytac W' z jazdy w izolacji, bo bak startowy tego dnia
zalezy od historii.

NOWA KOLEJNOSC:
  5(pierwszy). training_load.py -- 3 systemy XSS Low/High/Peak -> 3 Training Loads (EWMA).
  6(drugi).    decay.py -- dzienna sygnatura podaza za forma (jak cp_v3, rozszerzone na HIE, PP).
               Efekt: dzienna baza (TP,HIE,PP) rozna 20.06 vs 6.07, zgodna z forma.
  3(trzeci).   extract.py -- DOPIERO teraz W' z przebic, wzgledem WLASCIWEGO stanu dnia.
  4.           xss.py -- rozbicie potwierdzone vs Xert CSV (Low/High/Peak per jazda).
  progression -> walidacja calej krzywej vs Xert.

Zasada bez zmian: kazdy krok waliduje sie na danych przed nastepnym. tau: NIE stale-na-sile;
wroci jako parametr do kalibracji DOPIERO gdy forma daje wlasciwa dzienna baze.


---

## USTALENIA Z DANYCH (2026-07-08) -- mechanizm formy potwierdzony na Xert snapshots

Dane xert_profile_snapshots (dzienne, 2026-05-29..07-08) DOWODZA mechanizmu "sygnatura podaza za TL":
- 20-21.06: Training Load 65->70 -> TP 248->253, HIE 21.7->23.2, PP 1009->1015 (cala sygn W GORE).
- 21.06->04.07: TL 70->60 -> TP 253->248, HIE 23.2->22.0 (sygn opada za TL, Signature Decay).
- Form (TSB) = TL - RecoveryLoad: 21.06 RL=105 -> Form=-0.49 (przemeczenie po ciezkim dniu).

WNIOSKI dla MQ2:
1. HIE NIE jest jedna liczba -- oddycha z forma (20.6<->23.2 kJ, ~3kJ zakres), jak TP.
   "Prawdziwe W'" = dzienna wartosc podazajaca za TL, zakotwiczona w przebiciach. Jak cp_v3 dla TP.
2. TP w danych: 244-253 (9W) w rytm TL. cp_v3 juz to robi dobrze -> rozszerzyc mechanizm na HIE, PP.
3. Xert eksport daje ZBIORCZY training_load (nie 3 osobne w snapshot). Mamy benchmark dla sumy TL.
   Rozbicie Low/High/Peak liczymy sami z naszego XSS; walidacja posrednia (suma ~ Xert TL).
4. Kotwica z 20.06 (swiezy, TP=253/HIE=23.2) i 6.07 (po bloku, TP=244/HIE=20.6) to DWA stany
   tej samej krzywej forma-TL, nie sprzecznosc. To rozwiazuje problem "tau nie godzi 2 dni".

PROJEKT training_load.py:
- wejscie: dzienny XSS rozbity Low/High/Peak (z xss.py -- ale najpierw uproszczenie: uzyj
  istniejacego dziennego XSS jako proxy Low, dopoki xss.py 3-system nie gotowy; H/P malutkie u Michala).
- EWMA (jak CTL): TL_sys(d) = TL_sys(d-1)*(1-1/tau_tl) + XSS_sys(d)/tau_tl. tau_tl~42 dni (jak Xert/cp_v3).
- RecoveryLoad: szybsze EWMA (tau~7). Form = TL - RL.
- wyjscie: dzienne TL_low/high/peak + RL + form. Do modelq2_signature.
PROJEKT decay.py:
- dzienna sygnatura: TP<-cp_v3 (juz dobre); HIE i PP dryfuja za swoim TL wokol kotwicy z przebic.
- na teraz (brak extract): HIE_day = HIE_anchor * (TL_high/TL_high_anchor) -- proporcja jak Xert.


---

## WALIDACJA Filaru 4+5 (2026-07-08) -- Training Load zgodny z Xert

Backfill: policzono XSS z 312 jazd 1Hz (activity_record, 2025-01-01..2026-07-06) do modelq2_ride.
Sygnatura per jazda = Xert benchmark z dnia jazdy. EWMA rozpedzona na pelnej historii.

WYNIK (nasz tl_total vs Xert training_load):
  29.05: 58.8 vs 57 | 19.06: 69.7 vs 66 | 28.06: 66.6 vs 62 | 03.07: 61.8 vs 61 | 06.07: 65.3 vs 62
  Sredni blad ~2-3 pkt na wartosciach ~60 = ~4%. Dynamika (skok 20.06 blok, opadanie) sledzi Xerta.

WNIOSEK: caly lancuch dziala -- replay MPA -> XSS Low/High/Peak -> EWMA TL daje TL zgodny z Xert,
liczony OD ZERA z wlasnych danych 1Hz. Fundament pod decay.py gotowy (wiarygodny TL do dryfu sygnatury).

Tabele: modelq2_ride (312 jazd, XSS+min_wbal per jazda), modelq2_xert_bench (759 dni benchmark).
Narzedzie: scripts/mq2_backfill.py (przeliczenie XSS porcjami po datach; uruchamiac po zmianie wag XSS).

NASTEPNE: decay.py -- dzienna sygnatura. TP<-cp_v3; HIE,PP dryfuja za swoim TL wokol kotwicy.
Potem extract.py (W' z przebic wzgledem dziennego stanu). Potem strojenie wag XSS (Peak zanizony).


---

## PRZELOM: decay.py dziala -- dzienna sygnatura rozroznia stany formy (2026-07-08)

decay.py (Filar 3+6): dzienna sygnatura dryfuje za Training Load wokol kotwicy.
Korelacje potwierdzone na 272 dniach vs Xert: TP~TL_low r=0.77, PP~TL_peak r=0.65, HIE~TL_high r=0.50.
Kotwica: 20.06 (swiezy, przebicie 00:35, Xert TP=251/HIE=22.7). TP z cp_v3 override.

WYNIK -- CEL OSIAGNIETY (rozroznienie stanow formy jedna sygnatura):
  20.06 (swiezy):   MQ2 HIE=22.7 TP=253 | Xert HIE=22.7 TP=251
  06.07 (po bloku): MQ2 HIE=20.5 TP=241 | Xert HIE=20.5 TP=244
  -> MQ2 daje ROZNE HIE dla roznych stanow, zgodnie z Xert. To rozwiazuje pierwotny problem
     "tau nie godzi 2 dni" -- bo przyczyna byla jedna sygnatura na oba; teraz kazdy dzien swoja.
Sredni blad HIE ~1.8 kJ na przekroju roku (dni blisko kotwicy ~0; dalej rosnie -> wiecej kotwic z przebic).

DO DOSTROJENIA (nie psuje rdzenia):
- PP dryfuje za mocno w dol przy niskim TL_peak (6.07 PP=948 vs Xert 1000). Clamp PP za luzny.
- Dryf od jednej kotwicy rozjezdza sie na duzych dystansach (4.05 dHIE=+4.2). Rozwiazanie: extract.py
  doda kotwice z przebic (95 dni z max_effort w benchmarku) -> wielokotwicowy dryf.

NASTEPNE: extract.py -- W' z przebic wzgledem dziennej bazy (teraz gdy baza istnieje).
Potem: strojenie (PP clamp, wagi XSS Peak), progression.py (pelny szereg), walidacja calego okna.
