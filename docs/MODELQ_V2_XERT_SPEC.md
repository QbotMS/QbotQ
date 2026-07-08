# ModelQ v2 — kompletna specyfikacja logiki Xert (dokument zrodlowy)

> Cel: odtworzyc CALA logike Xerta (nie wybierac pojedynczych klockow), zrozumiec ja,
> a POTEM zaprojektowac ModelQ v2 jako spersonalizowana wersje. Xert = uniwersalny,
> ModelQ v2 = tuningowany do fizjologii Michala. Xert trzymany jako benchmark na czas
> kalibracji, docelowo wypiety.
>
> Zasada: NIE robic kotwic z danych Xert (proteza "tu i teraz" -> rozjazd za tydzien).
> Odtworzyc algorytm, ktory z tych samych danych 1Hz (activity_record) wyliczy to samo.
>
> Status: SZKIC W BUDOWIE (2026-07-08). Zrodla cytowane inline.

---

## Filar 0 — Sygnatura (Fitness Signature)

Trzy parametry opisuja cala krzywa mocy zawodnika:
- **TP (Threshold Power)** — najwyzsza moc utrzymywana dlugo bez narastania zmeczenia.
  Odpowiednik CP/FTP. Xert liczy ja z maksymalnych wysilkow ze WSZYSTKICH aktywnosci,
  adaptuje w czasie, bez testu.
- **HIE (High Intensity Energy)** — energia dostepna POWYZEJ TP (kJ). Odpowiednik W'/FRC.
  "Jak dlugo i jak mocno mozesz jechac nad TP." Michal/Xert: ~20-23 kJ.
- **PP (Peak Power)** — maksymalna moc chwilowa (1 s), sprint. Michal/Xert: ~1000-1030 W.

Krzywa mocy = wizualna reprezentacja sygnatury:
- gora-lewo = PP (1 s), dol-prawo = TP (asymptota), obszar miedzy = HIE.
- Punkty na krzywej = "points-of-failure" dla wysilkow fresh-to-failure (od swiezosci do odmowy).

Kalkulator sygnatury Xert: wystarcza 3 pary (czas, moc) maksymalnych wysilkow + 1 dodatkowy
punkt. (zrodlo: baronbiosys "Your Fitness Signature")

---

## Filar 1 — MPA (Maximal Power Available), sekunda-po-sekundzie

RDZEN CALEGO MODELU. MPA = ile mocy masz dostepne W TEJ SEKUNDZIE, z uwzglednieniem zmeczenia.

Zasady jakosciowe (zrodla: baronbiosys "Maximal Power Available", "Understanding MPA",
PezCycling 2017 "MPA Modelling"):
- Na starcie (swiezy): **MPA = PP**.
- Jazda **powyzej TP**: MPA SPADA (zmeczenie). Im wyzej nad TP, tym szybszy spadek.
- Jazda **ponizej TP**: MPA ROSNIE (regeneracja). Im nizej pod TP, tym szybsza regeneracja.
- **Punkt-odmowy / max wysilek**: gdy moc = MPA (dotkniecie). To jest "breakthrough".
- MPA nie moze byc przekroczone przez rzeczywista moc -> jesli jest, sygnatura zle
  oszacowana i wymaga remodelowania (self-correcting).
- HIE limituje jak szybko MPA moze byc wyczerpane; wartosc HIE wyznacza MPA w czasie
  rzeczywistym. Gdy HIE zuzyte nad progiem -> MPA spada ku TP; gdy HIE odbudowane pod
  progiem -> MPA wraca ku PP. (zrodlo: baronbiosys "High Intensity Energy")

### DOKLADNA MATEMATYKA (zlozona z literatury naukowej, na ktorej Xert bazuje)

Xert NIE publikuje wprost swoich rownan, ale MPA jest matematycznie rownowazne modelowi
W'bal (Skiba/Morton) "odwroconemu do gory nogami": MPA = TP + (dostepne W' teraz)/czas.
Gdy W'bal pelne -> MPA = PP; gdy W'bal = 0 -> MPA = TP.

#### 1. Wyczerpanie i regeneracja W' (rdzen) -- Skiba W'bal, forma calkowa:
    W'bal(t) = W' - INTEGRAL_0^t [ W'exp(u) * exp(-(t-u)/tau_w) ] du
  gdzie:
    - W'      = pojemnosc nad progiem (u nas HIE), w dzulach
    - W'exp(u)= chwilowo wydatkowane W' = (P(u) - CP) gdy P>CP, inaczej 0
    - (t-u)   = czas jaki uplynal od wydatku do teraz (regeneracja)
    - tau_w   = stala czasowa ODBUDOWY W' (sekundy)

#### 2. Stala czasowa regeneracji tau (Skiba 2012, dopasowana eksperymentalnie):
    tau_w = 546 * exp(-0.01 * D_CP) + 316
  gdzie D_CP = CP - P_recovery (o ile ponizej progu regenerujesz).
  - Im GLEBIEJ ponizej progu (wieksze D_CP) -> mniejsze tau -> SZYBSZA regeneracja.
    To zgadza sie z jakosciowym opisem Xerta: "im nizej pod TP, tym szybciej MPA rosnie".
  - Stale 546, 316, 0.01 = z badan Skiba (untrained cyclists, 60s praca/30s odpoczynek).

#### 3. Wariant Skiba differential (szybszy, rownowazny, do implementacji tick-po-ticku):
  Zamiast liczyc calke wstecz co sekunde (kosztowne), forma rekurencyjna:
    gdy P > CP:  W'bal -= (P - CP) * dt                 # wyczerpanie liniowe
    gdy P <= CP: W'bal += (W' - W'bal) * (1 - exp(-dt/tau_w)) # regeneracja wykladnicza ku pelni
  (Froncioni/Skiba differential form -- powszechnie uzywany w Golden Cheetah, intervals.icu)

#### 4. MPA z W'bal (przeliczenie na moc dostepna teraz):
  MPA(t) = TP + (PP - TP) * (W'bal(t) / W')
  - swiezy (W'bal=W') -> MPA = PP
  - puste (W'bal=0)   -> MPA = TP
  UWAGA: to jest LINIOWE przyblizenie. Xert moze uzywac nieliniowego ksztaltu (PP zagina
  krotki koniec). Do WERYFIKACJI na danych: policzyc MPA obiema wersjami, porownac z
  przebiciami Xerta z CSV. [DO KALIBRACJI]

#### 5. Wykrywanie przebicia:
  Gdy realne P(t) >= MPA(t) w danej sekundzie -> punkt-odmowy (breakthrough).
  Sygnatura (TP, HIE, PP) jest wtedy remodelowana tak, by MPA nie bylo przekroczone.

### KLUCZOWE PYTANIA DO KALIBRACJI (tu ModelQ v2 sie personalizuje):
- **tau**: stale Skiba (546/316/0.01) sa dla UNTRAINED cyclists. Liversedge/badania:
  trenowani regeneruja szybciej, tau indywidualne. Michal ma juz tau dynamiczne w
  wbal_replay.py (Skiba/Bartram + readiness scaling) -- to jest DOKLADNIE miejsce
  personalizacji ModelQ v2 vs uniwersalny Xert.
- **ksztalt MPA**: liniowy vs nieliniowy (PP). Do sprawdzenia na przebiciach z CSV.
- **HIE=W'**: jesli odtworzymy MPA i przebicia, HIE wyliczy sie z przebic (nie z krzywej
  MMP!). To rozwiazuje problem "8 vs 22 kJ" -- bo przebicia MPA to inne zrodlo niz okna MMP.

### CO JUZ MAMY W KODZIE (do ponownego uzycia):
- wbal_replay.py: liczy W'bal tick-po-ticku z 1Hz, ma tau dynamiczne (Skiba/Bartram),
  3s smoothing power, readiness scaling. To jest ~80% Filaru 1.
- _peak_power (cp_wprime.py): PP z okien 1s/5s.
- fitmodel_wbal_ride: min_wbal_pct, wprime_base_kj per jazda.

---

## Filar 2 — Wykrywanie przebic (Breakthrough detection)

Zrodla: baronbiosys "How Xert Works", "Fitness Breakthroughs", "Beginners Guide".

- **Przebicie (breakthrough)** = w danej sekundzie realna moc P(t) DOTYKA/przekracza MPA(t).
  To znaczy: pojechales mocniej, niz obecna sygnatura przewiduje ze mozesz.
- **Green diamond** = najlepszy wysilek jazdy (moc najblizej MPA).
- Po przebiciu Xert przelicza sygnature (patrz Filar 3), tak by MPA=P w tym punkcie.
- **Medale** (ile z 3 parametrow WZROSLO): brazowy=1, srebrny=2, zloty=3.
- **Near-breakthrough / "fakethrough"** = bylo blisko MPA, ale nie dotknelo. Wtedy
  sygnatura moze byc lekko ZMNIEJSZONA (bo skoro probowal maksa i nie dobil -> byl slabszy
  niz model sadzil). To wazne: near-BT ciagnie sygnature W DOL, przebicie W GORE.
  Przyklad wyzwalacza near-BT: "odpuscil na szczycie podjazdu".

KLUCZ dla ModelQ: przebicie to jedyny TWARDY dowod na sygnature. Reszta czasu = predykcja
z obciazenia (Filar 3). U Michala (submaks) przebic jest MALO -> sygnatura zyje glownie
z predykcji + rzadkich przebic. Dlatego HIE=22 to prawdopodobnie stare przebicie sprzed
miesiecy, podtrzymywane przez Signature Decay (nie liczone co jazde z krzywej MMP!).

---

## Filar 3 — Aktualizacja i zanik sygnatury (Signature Decay Method)

Zrodla: baronbiosys "Fitness Improvement and Day-to-day Variation", "Xerts Magic Setting",
"Improvements to Fitness Signature Tracking", "Signature Decay Method", "Training Load & Status".

TO JEST SERCE DYNAMIKI -- i DOKLADNIE to, co recznie odtworzylismy w cp_v3 (kotwica+dryf CTL)!

### Jak Xert wyznacza sygnature w dniu aktywnosci (signature extraction):
1. **Predykcja**: przewiduje jaka sygnatura BYLA na starcie jazdy -- z Training Loads dla
   kazdego z 3 systemow (Low/High/Peak). Rosnace TL -> rosnace parametry; malejace -> malejace.
2. **Zanik (decay)**: obniza kazdy parametr wzgledem predykcji, wg wybranej metody zaniku.
3. **Porownanie**: zestawia z tym, co REALNIE pokazano na jezdzie (przebicia).
   - jest przebicie -> parametr W GORE (remodel by MPA=P).
   - brak, near-BT -> parametr moze zejsc lekko (fakethrough).

### Signature Decay Method (4 opcje; domyslna "Optimal Decay"):
- Zanik chroni przed przeszacowaniem z blednych danych (spike'i mocy, artefakty).
- NAJWAZNIEJSZE (wersja 2023): "rather than allowing signature to continually decay slowly
  from last breakthrough, your signature will decay a little, THEN FOLLOW YOUR TRAINING LOADS."
  -> czyli: troche zaniku od ostatniego przebicia, potem podaza za TL. To DOKLADNIE nasz
  model cp_v3: kotwica (przebicie) + zanik + dryf od CTL (=Training Load). POTWIERDZENIE
  ZE NASZA ARCHITEKTURA JEST ZGODNA Z XERTEM.
- Historia: stara metoda pozwalala "little room" rosnac -> nierozsadny spadek formy przy
  ciaglym treningu (ten sam blad, ktory mielismy z rolling-max okna!). Naprawili to samo co my.

### Roznice w dynamice per parametr (zrodlo: PezCycling):
- **TP** zmienia sie STOPNIOWO (gladko).
- **PP i HIE** moga SKAKAC w gore/dol (spike) -- bo zaleza od rzadkich, ostrych przebic.

### Trickle-down: gdy dochodzi nowa aktywnosc lub stara jest zmieniona, Xert przelicza
   sygnature i cala progresje do przodu (spojnosc historii).

### KLUCZ dla ModelQ v2:
- 3 OSOBNE Training Loads (Low=TP, High=HIE, Peak=PP), kazdy z wlasnym Impulse Response.
  U nas: mamy ctl_xss (jeden). ModelQ v2 potrzebuje ROZBICIA XSS na 3 systemy (Low/High/Peak)
  -> silnik buckets.py juz to liczy (i^4 progi)! Kolejny klocek juz jest.
- Kazdy parametr sygnatury dryfuje wg SWOJEGO TL. TP wolno, HIE/PP skokowo.

---

## Filar 4 — Pochodne (LTP, XSS, forma)

### LTP (Lower Threshold Power) — ZWERYFIKOWANE
Wzor odtworzony przez uzytkownika Xert (forum), potwierdzony na danych Michala:
  **LTP = TP - HIE/400**   (HIE w dzulach, t=400 s)
Weryfikacja: TP=244, HIE=20.6kJ -> 244 - 20600/400 = 192.5 W = dokladnie Xert LTP. OK.

### XSS (Xert Strain Score) -- ZEBRANE
Zrodla: baronbiosys "XSS", "Xert Strain Score", "Understanding XSS", "XSS Rate".

- **Definicja normalizacji**: 1 godzina @ TP (na swiezo) = 100 XSS. Pod zmeczeniem
  godzina @ TP moze dac WIECEJ niz 100 (bo strain liczony wzgledem MPA, nie mocy).
- **Strain danego wattu = jak blisko biezacego MPA jest ta moc.** 400 W przy MPA=1000
  = niski strain; te same 400 W przy MPA=700 (zmeczony) = wysoki strain. To odroznia XSS
  od TSS: XSS UWZGLEDNIA ZMECZENIE przez MPA. (kluczowa przewaga nad TSS/NP)
- **Rozbicie na 3 systemy** wg work allocation ratios (kazdy punkt mocy dzielony na udzial
  TP/HIE/PP):
    - XLSS (Low)  -> system TP
    - XHSS (High) -> system HIE
    - XPSS (Peak) -> system PP
  Suma pracy = praca TP + praca HIE + praca PP. Ponizej progu: tylko TP. Powyzej: TP+HIE+PP
  wg proporcji zaleznej od tego jak wysoko nad progiem.
- Ratio Low:High:Peak -> Focus & Specificity (jaki system trenowany).
- **XSSR (XSS Rate)** = intensywnosc dajaca dane XSS w godzine. Np. XSSR 200 przez 15 min
  = 50 XSS (200/(60/15)).
- Kazdy z 3 XSS -> osobny Training Load + Recovery Load -> osobny Impulse Response na
  kazdy parametr sygnatury (petla zwrotna z Filarem 3).

### CO MAMY W KODZIE:
- buckets.py: i=P/FTP, strain=i^4*(100/3600), progi Low<0.90/High 0.90-1.20/Peak>=1.20.
  To NASZ odpowiednik rozbicia XSS na 3 systemy (inna metoda niz work-allocation, ale ten
  sam cel). Do weryfikacji czy da te same proporcje co Xert Low|High|Peak.
- Nasze XSS (fitmodel): strain_rate = (P/CP_eff)*(1+beta*fatigue)*(100/3600)*dt, beta=1,
  gwarantuje 1h@CP=100. UWZGLEDNIA fatigue -- zgodne z zasada Xerta (strain wzgledem MPA).

---

## PODSUMOWANIE: co z Xerta juz mamy, czego brakuje (mapa do ModelQ v2)

| Filar | Xert | Mamy w kodzie? | Luka |
|-------|------|----------------|------|
| MPA tick | W'bal odwrocony + tau Skiba | wbal_replay.py (~80%) | przeliczyc na MPA, kalibracja tau |
| Sygnatura 3-param | TP/HIE/PP | TP=cp_v3 OK; PP=_peak_power; HIE=? | HIE z przebic (nie MMP) |
| Przebicia | P dotyka MPA | NIE (jawnie) | wykrywanie na 1Hz |
| Decay+dryf | zanik + follow TL (3 systemy) | cp_v3 robi to dla CP! | rozszerzyc na HIE, PP; 3 TL |
| XSS 3 systemy | Low/High/Peak work-alloc | buckets.py + XSS fitmodel | zweryfikowac proporcje vs Xert |
| LTP | TP - HIE/400 | wzor znany | policzyc z poprawnego HIE |

WNIOSEK: architektura cp_v3 (kotwica+zanik+dryf od obciazenia) NIE byla przypadkiem --
to jest dokladnie Signature Decay Method Xerta. Mamy wiekszosc klockow. Glowna luka:
(1) MPA z W'bal, (2) wykrywanie przebic na 1Hz, (3) HIE z przebic zamiast z MMP,
(4) rozbicie na 3 osobne Training Loads.

---

## Dane wejsciowe (mamy komplet)
- qbot_v2.activity_record: 1Hz (ts, power_w, hr_bpm, ...) dla KAZDEJ jazdy, od 2025-01-01.
  TE SAME dane co dostawal Xert. To jest warunek "te same dane -> te same wyniki".
- Michal dostarczy CSV z Xert od poczatku 2025 (progresja sygnatury + przebicia) do
  weryfikacji odtworzonego modelu.

## Sygnatura odniesienia (Xert, na dzis 2026-07-08)
- TP=244 W, HIE=20.6 kJ, PP~1000 W, LTP=192 W.
- HIE bardzo stabilne 90d: 20.5-22.7 kJ (mediana 22.1).
- PP stabilne: ~1000-1030 W.


---

## AUDYT KOMPLETNOSCI (2026-07-08) — wszystkie komponenty Xert, status pokrycia

Przeglad pelnego glosariusza Xert. [OK]=w spec, [DODANE]=uzupelnione ponizej, [POMIJAMY]=poza zakresem ModelQ.

### Rdzen (mielismy):
- [OK] Fitness Signature (TP/HIE/PP) — Filar 0
- [OK] MPA sekunda-po-sekundzie — Filar 1 (W'bal + tau Skiba)
- [OK] Breakthrough / near-BT / medale — Filar 2
- [OK] Signature Decay + predykcja z TL — Filar 3
- [OK] XSS Low/High/Peak — Filar 4
- [OK] LTP = TP - HIE/400 — Filar 4

### BRAKUJACE — uzupelnione teraz:

#### [DODANE] Focus & Specificity (charakterystyka jazdy)
- **Focus** = czas trwania LUB typ zawodnika opisujacy, JAKI system byl najbardziej cwiczony.
  "Focus Power = najwyzsza moc na dany czas, jak MMP, liczona z sygnatury." Mowi: jaki
  aspekt fitnessu byl trenowany (np. 8-min W/kg = GC Specialist).
- **Specificity Rating** = jak bardzo high-intensity strain byl SKUPIONY blisko Focus power.
  Pure (wysoki %) = skoncentrowany; Polar (niski %) = krotkie mocne + dlugie latwe, malo w Focus.
- Liczone z ratio Low:High:Peak XSS. (zrodlo: baronbiosys "Work Allocation", "Using Xert to Evaluate")
- ModelQ: mamy Low/High/Peak (buckets) -> mozemy policzyc Focus/Specificity tak samo.

#### [DODANE] Training Load + Recovery Load -> Form (petla obciazenia, 3 systemy)
KLUCZOWE brakujace ogniwo dynamiki:
- **Training Load (TL)** = wykladniczo wazona suma XSS (jak CTL), OSOBNO dla Low/High/Peak.
- **Recovery Load (RL)** = miara potrzebnej regeneracji (jak ATL), tez per system. Ukryta domyslnie.
- **Form** = bilans TL - RL (jak TSB). Kolor gwiazdek = Form; liczba gwiazdek = suma TL.
- Kazdy z 3 systemow ma WLASNY Impulse Response -> napedza dryf SWOJEGO parametru sygnatury:
    Low TL  -> dryf TP
    High TL -> dryf HIE
    Peak TL -> dryf PP
  To domyka petle z Filarem 3: "predykcja sygnatury z Training Loads" = kazdy parametr
  podaza za swoim TL. (zrodlo: baronbiosys "Training Status and Form", "XPMC", "Xert Strain Score")
- ModelQ dzis: ma JEDEN ctl_xss/atl_raw. ModelQ v2 potrzebuje TRZECH (Low/High/Peak).
  Recovery time per system: Xert pokazuje dni regeneracji osobno dla L/H/P.

#### [DODANE] Difficulty Score + XEP (Xert Equivalent Power)
- **Difficulty** = jak blisko MPA byla praca, chwila po chwili (szary obszar na wykresie).
  Rosnie gdy MPA spada blisko mocy. "Hardness" = zdolnosc wielokrotnego sciagania MPA w dol.
- **XEP (Xert Equivalent Power)** = odpowiednik NP/mocy znormalizowanej, ale liczony przez
  pryzmat sygnatury/MPA (nie 30s rolling jak NP). Uzywany do XSS.
- ModelQ: do rozwazenia jako pochodna, gdy MPA bedzie liczone.

#### [DODANE] Focus Power / krzywa mocy z sygnatury (kierunek ODWROTNY)
- Majac sygnature (TP/HIE/PP) mozna WYGENEROWAC cala krzywa mocy (Focus Power dla dowolnego t).
  To odwrotnosc ekstrakcji. Przydatne do: predykcji ETA, targetow treningowych, wizualizacji.
- ModelQ: to jest "za darmo" gdy mamy sygnature + model MPA.

#### [DODANE] Trickle-down recalculation
- Nowa/zmieniona aktywnosc -> Xert przelicza sygnature i CALA progresje do przodu.
- ModelQ v2 musi to obsluzyc: zmiana starej jazdy = przeliczenie lancucha (jak nasz backfill).

#### [DODANE] Improvement Rate / Athlete Type / Adaptive Training Advisor (XATA)
- Improvement Rate = docelowe tempo wzrostu TL (ramp rate XSS/tydzien). Off-Season..Extreme-2.
- Athlete Type = profil (GC Specialist, Sprinter, etc.) -> docelowe ratio L/H/P.
- XATA = silnik rekomendacji treningu. [POMIJAMY na teraz — to warstwa DORADCZA, nie modelujaca
  fitness. ModelQ v2 = model fitnessu; doradztwo pozniej.]

### [POMIJAMY] (peryferia, nie wplywaja na sygnature/fitness):
- HRDM (Heart Rate Derived Metrics) — TYLKO dla jazd BEZ mocy. Michal ma moc zawsze. Pomijamy.
- Fat/Carb utilization — informacyjne, nie wplywa na sygnature.
- Strava Segment / Advanced Stats — narzedzie analizy, nie model.
- Fitness Planner / Workout Designer / SMART workouts — warstwa treningowa, nie model fitnessu.

### WNIOSEK AUDYTU:
Rdzen modelu fitnessu Xert = 6 elementow, wszystkie teraz w spec:
  1. Sygnatura (TP/HIE/PP)
  2. MPA (W'bal + tau)
  3. Przebicia (P dotyka MPA)
  4. XSS -> 3 systemy (work allocation / buckets)
  5. Training/Recovery Load per system -> Form (3 Impulse Response)
  6. Signature Decay (predykcja z TL + zanik) domyka petle: TL napedza dryf sygnatury
Pochodne: LTP, Focus, Specificity, Difficulty, XEP, Focus Power — wszystkie liczone z (1)+(2)+(4)+(5).
Warstwa doradcza (XATA, Athlete Type, Improvement Rate) — POZA ModelQ v2 (model, nie trener).

DANE DO WALIDACJI (CSV Jul 8th): per jazda mamy Low/High/Peak XSS + Maximal Effort Time.
- Low/High/Peak XSS -> walidacja naszego rozbicia (buckets vs Xert work-allocation).
- Maximal Effort Time != 00:00 -> marker near-BT/BT. W danych: tylko 20.06 (00:35) i 6.07 (00:19)
  maja niezerowy -> potwierdza ze przebic jest MALO (sygnatura zyje z dryfu, nie z przebic).


---

## AUDYT POPRAWNOSCI istniejacych elementow (2026-07-08) — CZY LICZA DOBRZE

Cel: zanim ModelQ v2 uzyje istniejacych klockow, sprawdzic ze licza POPRAWNIE (blad tu
= katastrofa pozniej). Weryfikacja na zywym kodzie + danych (jazda 6.07, benchmark Xert).

### 1. W'bal / MPA (wbal_replay.py) — RDZEN
STATUS: wzor POPRAWNY, ale ZLY INPUT (CP).
- [OK] Wydatek: wbal -= (P-CP)*dt gdy P>CP. Zgodny ze Skiba.
- [OK] Regeneracja: deficit*exp(-dt/tau), tau=546*exp(-0.01*dcp)+316. Matematycznie
  rownowazne formie roznicowej dla dt=1s. Zgodne ze spec Filar 1.
- [OK] Postoje (gap>=30s): analityczna regeneracja przez dt. Poprawne.
- [OK] 3s smoothing power dla W'bal (Karoo SMOOTHED_3S). min_wbal_pct=0 na 6.07 zgadza
  sie z Xert MaxEffort 00:19 (wykryl wyczerpanie tam gdzie bylo).
- [!! BLAD KRYTYCZNY] Input CP: _fetch_daily_baseline bierze **ftp_est_w** (EF-owy, 252 na
  6.07), NIE cp_v3 (239) ani Xert TP (244). W'bal wisi na STARYM, najwyzszym progu.
  Skutek dla v2: MPA/przebicia liczone z ftp_est=252 wypadna w zlych miejscach ->
  sygnatura zle sie skalibruje. MUSI byc naprawione PRZED budowa MPA.
  Fix: baseline ma czytac wlasciwy CP (docelowo sygnatura ModelQ v2, na teraz cp_v3).
- [DO ZBADANIA] deficit0 liczony od wprime_eff_j (skalowane przez cf tick-po-ticku) --
  przy zmiennym cf target regeneracji "oddycha", mozliwy dryf. Niekrytyczne, ale sprawdzic.

### 2. XSS (wbal_replay.py) — NIEKOMPLETNY dla v2
STATUS: liczy sie, ale JEDNA liczba zamiast 3 systemow.
- [OK] Wzor: (P/CP)*(1+beta*fatigue)*(100/3600)*dt, beta=1, 1h@CP=100. Uwzglednia
  zmeczenie (fatigue z W'bal) -- zgodne z zasada Xerta (strain wzgledem MPA).
- [ROZJAZD] 6.07: nasz XSS=100.7 vs Xert total=92.0 (+9%). Do zbadania czy z CP=252
  (zawyzony CP -> inny strain) czy z metody.
- [BRAK dla v2] NIE ma rozbicia Low/High/Peak. Xert 6.07: 82.6/7.9/1.5. ModelQ v2
  wymaga 3 systemow (Filar 5: osobne TL na kazdy parametr). buckets.py to liczy osobno --
  do scalenia/uzgodnienia z XSS z wbal_replay (dzis dwa rozne silniki!).

### 3. TP / CP (cp_v3, cp_wprime) — OK po naprawach z tej sesji
- [OK] cp_v3 = 239 (Xert TP=244, delta 5). Kotwica+zanik+dryf CTL. Dobre.
- [OK] cp_modelq = 242 (Xert 244, delta 2). Okno 90d po naprawie clampu. Dobre.
- [UWAGA] ftp_est_w = 252 (EF-owy) ZAWYZONY o 8-13 W vs Xert/cp_v3. To go uzywa W'bal (bug #1).
  ftp_est to najstarsza, najmniej wiarygodna warstwa. v2 powinien go wycofac jako input.

### 4. PP / Peak Power (cp_wprime._peak_power) — ROZJAZD + nie zapisywane
- [!! nie w bazie] fitmodel_daily NIE MA kolumny peak_power_w. _peak_power liczy, ale
  wynik nigdzie nie ladzie. Dla v2 PP musi byc trwale w sygnaturze.
- [!! ROZJAZD wartosci] mmp_5_w=822 W, mmp_1_w=1194 W. Xert PP=~1000-1030.
  Ani 822 (5s) ani 1194 (1s surowe) nie rowna sie Xert 1000. Xert PP to prawdopodobnie
  NIE surowe MMP, tylko punkt krzywej mocy z modelu (ekstrapolacja do t->0 z sygnatury),
  lub 1s po odfiltrowaniu artefaktow. DO USTALENIA jak Xert liczy PP zanim uzyjemy w v2.
  (1194 na 1s bywa artefaktem miernika; 822 na 5s jest submaks). Bezpieczne: PP z krzywej
  3-param jako granica t->0, kalibrowane by ~=Xert.

### 5. CTL/ATL (training_load -> ctl_xss/atl_raw) — OK jako jeden system, BRAK 3
- [OK] ctl_xss ciagle 433 dni, dryf cp_v3 na nim dziala, banner/wykres OK.
- [BRAK dla v2] JEDEN CTL. Xert ma 3 (Low/High/Peak TL) -> osobny dryf TP/HIE/PP.
  ModelQ v2 wymaga rozbicia: XSS Low->CTL_low->dryf TP, itd.

### PODSUMOWANIE AUDYTU POPRAWNOSCI:
| element | wzor | input | kompletnosc v2 |
|---------|------|-------|----------------|
| W'bal   | OK   | ZLY CP (ftp_est 252) | rdzen ok |
| XSS     | OK   | zalezy od CP | BRAK 3 systemow |
| TP      | OK (cp_v3 239) | — | ok |
| PP      | ROZJAZD (822/1194 vs Xert 1000) | nie w bazie | ustalic metode |
| CTL     | OK   | — | BRAK 3 systemow |

NAPRAWY WYMAGANE PRZED ModelQ v2 (kolejnosc):
1. **W'bal input CP**: odpiac od ftp_est_w (252), podpiac wlasciwy CP (cp_v3 / docelowo
   sygnatura v2). BEZ TEGO MPA i przebicia beda na zlym progu. NAJPILNIEJSZE.
2. **Zunifikowac XSS**: dzis 2 silniki (wbal_replay XSS jednoliczbowy + buckets 3-system).
   v2 potrzebuje JEDNEGO XSS rozbitego na Low/High/Peak, spojnego z MPA.
3. **3 Training Loads** zamiast jednego ctl_xss.
4. **Zweryfikowac PP** = Xert PP (ktore okno).
