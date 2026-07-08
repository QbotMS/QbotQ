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
