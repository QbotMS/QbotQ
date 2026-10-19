# AERO / CdA — AUDYT I HANDOFF DO DALSZEJ SESJI

Data: 2026-10-19
Zakres: QBot + QExt2
Status: audyt założeń i bieżącej implementacji zakończony na poziomie wystarczającym do projektowania v3. Kod nie był zmieniany w tej sesji.

## 1. Cel

Celem nie jest dalsze strojenie istniejących progów AERO, tylko zbudowanie możliwie najlepiej działającego modułu:

- QExt2: wykrywanie zmian oporu aerodynamicznego / pozycji podczas jazdy,
- QBot: estymacja CdA i porównania między jazdami,
- wspólny kanon danych fizycznych i parametrów,
- jawna ocena jakości/pewności wyniku,
- odporność na wiatr, nawierzchnię, stan drogi, błąd nachylenia i zmiany prędkości.

Kluczowa konkluzja audytu:

> Obecne AERO v2 w QExt2 jest w praktyce detektorem zmiany NIEWYJAŚNIONEGO OPORU, a nie wiarygodnym detektorem zmiany pozycji aerodynamicznej.

To oznacza, że nie należy dalej poprawiać go wyłącznie przez zmianę długości okien, STEP_MIN czy filtrów steady. Potrzebna jest przebudowa modelu fizycznego.

---

## 2. Przejrzane elementy

### QBot
- `/opt/qbot/app/docs/AERO_CDA.md`
- `/opt/qbot/app/docs/TODO.md` sekcja `[AERO-CDA]`
- `/opt/qbot/app/fitmodel/cda.py`
- `/opt/qbot/app/scripts/_tmp_aero_model.py`
- `/opt/qbot/app/qbot3/rides/activity_devices.py`
- baza `qbot_v2.ride_cda`
- baza `qbot_v2.qext2_aero_record`
- dane `activity_record`, `activity_device`, `ride_report_data`
- Garage: rowery / masa / komponenty

### QExt2
- `docs/AERO.md`
- `app/src/main/kotlin/com/qext2/primary/engine/AeroEstimator.kt`
- `RideDataAggregator.kt`
- `SurfaceProfileCache.kt`
- infrastruktura testowa i replay repo QExt2
- historia commitów AERO v1/v2

---

## 3. Najważniejsze rozbieżności QBot ↔ QExt2

### 3.1 Masa

QExt2 AERO używa obecnie:

`masa = bodyWeight + 9 kg`

QBot CdA używa:

`masa = bodyWeight + EXTRA_KG`

W dokumentacji/ustaleniach Centrum CdA przewija się +14 kg jako masa systemowa używana dla modelu aero/rolling.

To musi zostać ujednolicone. Masa ma wpływ na:
- toczenie,
- grawitację,
- zmianę energii kinetycznej,
- pośrednio wyliczone CdA.

Docelowo: jedno źródło prawdy z QBot, najlepiej masa systemowa per rower/konfiguracja.

### 3.2 Crr

QExt2 AERO v2: stałe `Crr = 0.007`.

QBot: Crr per kategoria nawierzchni z kanonu, z kotwicą asfaltu `0.0055` i resztą estymowaną z danych historycznych.

Skala błędu jest duża. Dla systemu ok. 115 kg przy 30 km/h:

- `ΔCrr = 0.001` ≈ 9–10 W,
- asfalt 0.0055 vs stałe 0.007 ≈ ~14 W różnicy,
- cięższa nawierzchnia np. okolice 0.011 vs 0.007 ≈ ~38 W.

Wniosek: zmiana nawierzchni może bez problemu wyglądać jak duża zmiana aero przy obecnym modelu QExt2.

### 3.3 Wiatr

QExt2 AERO v2 nie używa wiatru w równaniu siły aerodynamicznej. Używa go tylko do decyzji o resecie kierunku.

Jednocześnie QExt2 już posiada:
- prędkość wiatru,
- kierunek wiatru,
- heading,
- freshness/cache,
- aktualną pozycję na trasie.

Brak wiatru w AERO nie wynika z braku danych, tylko z obecnego założenia algorytmu.

QBot fituje wiatr z jazdy. Obecny model jest wzdłużny (składowa względem headingu), a nie pełnym modelem wektorowego apparent wind/yaw.

Dla QExt2 v3 wiatr musi wejść bezpośrednio do modelu. Dla QBot v3 należy rozważyć prior z prognozy zamiast całkowicie wolnego fitu.

### 3.4 Nachylenie

W QExt2 zmienna nazywa się `filteredGradeRef`, ale obecny update ma współczynnik 1.0:

`filtered = old + 1.0 * (raw - old)`

czyli realnie nie ma filtrowania.

To jest problem krytyczny dla CdA, bo nawet mały bias grade może zostać zamieniony na opór aero.

Wniosek: v3 powinno liczyć bilans energetycznie po oknie, a nie opierać się na chwilowym bilansie 1 Hz z surowym grade.

---

## 4. Realna jazda 18.10 — ważne rozróżnienie v1 vs v2

Jazda 18.10 rano zawiera pola AERO z QExt2 v1.

Commit AERO v2:

`da7d0a9062a05cdca80d7a9411487fd4c385bb57`

powstał dopiero 18.10 o 12:24 UTC, czyli po jeździe.

W związku z tym:

- brak reakcji AERO na odcinku ok. km 10–12,
- surowe wartości CdA z FIT,
- duży skok +95 W,

są obserwacjami v1, nie v2.

Dokumentacja QExt2 mówi, że v2 było jedynie symulowane/replayowane na FIT z 18.10. Nie ma jeszcze walidacji v2 na prawdziwej jeździe z urządzenia.

To trzeba zachować jako ważne ograniczenie: nie wolno uznać v2 za zweryfikowane terenowo.

### Dane z v1 / jazdy 18.10

W `qext2_aero_record` występowały fizycznie absurdalne chwilowe wartości CdA (zakres około -2.8 do +4.1; mediana około 0.63). To pokazuje, że bieżący model przepuszcza niewyjaśniony błąd fizyki do samego CdA, a logika poziomów tylko częściowo go maskuje.

Dla QBot tej samej jazdy:
- CdA około 0.511,
- fitted wind około 0.75 m/s,
- prognozowany wiatr około 2.0 m/s.

W szerszym zbiorze fitted wind bywa istotnie niższy od prognozy; mediana relacji fitted/forecast z analizowanego zbioru była około 0.31. To może wynikać z ekspozycji przy ziemi/lesie, ale też pokazuje degenerację `CdA ↔ wiatr ↔ Crr` i przemawia za użyciem prioru.

---

## 5. Stan drogi — nie wolno wrzucać go do CdA

Z dokumentacji T6 w `AERO_CDA.md`:

- stan tej samej drogi może zmieniać opór o około +10–16 W przy 20 km/h,
- ciężka/mokra droga potrafi zawyżyć wyliczone CdA jazdy,
- różnice między miejscami i dniami potrafią być większe niż różnice między samymi kategoriami nawierzchni.

Docelowy model:

`Crr_effective = Crr_surface + ΔCrr_road_state`

Road-state powinien być modelowany osobno, najlepiej z matched segments / historycznego baseline tego samego miejsca.

---

## 6. Rekomendowana architektura v3

### 6.1 QExt2: AERO/POZYCJA v3

QExt2 nie powinno próbować pokazywać absolutnego CdA jako głównej wartości live.

Docelowy wynik:

`POZYCJA -8 W`

czyli różnica oporu względem lokalnego baseline po odjęciu:
- toczenia,
- wiatru,
- nachylenia,
- zmian energii kinetycznej.

Do tego confidence:
- wysoka,
- średnia,
- niska,
- brak wyniku.

W złych warunkach lepiej pokazać `—` niż fałszywie precyzyjne waty.

### 6.2 Model energetyczny po oknie

Zamiast chwilowego CdA 1 Hz:

`Σ(P*eta*dt) = E_aero + E_roll + ΔE_kin + ΔE_pot`

Po przekształceniu estymować efekt aero z całego okna 20–60 s.

Zysk:
- mniejsza wrażliwość na chwilowy grade,
- poprawniejsze traktowanie przyspieszeń,
- mniej szumu niż w odejmowaniu kilku dużych składników co sekundę.

### 6.3 Wiatr

Docelowo użyć pełnego wektora apparent wind:

`V_air_vector = V_bike_vector - V_wind_vector`

Minimalna sensowna wersja v3:
- moduł wektora apparent wind,
- projekcja oporu na kierunek jazdy,
- CdA na razie niezależne od yaw.

Yaw-dependent CdA można dodać później po zebraniu danych do kalibracji.

### 6.4 Crr i nawierzchnia

QExt2 powinno pobierać z QBot:
- kanoniczne Crr per typ nawierzchni,
- nawierzchnię bieżącego odcinka trasy,
- wersję parametrów.

`SurfaceProfileCache` już zapewnia profil nawierzchni z QBot i fallback RouteGraph.

Na szutrze / niepewnej nawierzchni confidence powinno być automatycznie obniżone, zwłaszcza bez korekty road-state.

### 6.5 Masa

QBot powinien dostarczać do QExt2:
- body mass,
- bike/system extra mass,
- final system mass,
- wersję/źródło.

Jedna wartość dla QBot i QExt2.

---

## 7. QBot CdA v3

QBot ma inne zadanie niż QExt2.

### QExt2
Krótki horyzont: zmiana pozycji/chwytu w tej samej jeździe.

### QBot
Długi horyzont: absolutne CdA / trend / porównania między jazdami.

Nie powinny to być identyczne algorytmy, ale powinny korzystać z tego samego kanonu parametrów fizycznych.

### 7.1 Matched segments — P1

Najważniejszy następny krok dla QBot.

Porównywać te same odcinki GPS w tym samym kierunku pomiędzy jazdami.

Dzięki temu częściowo znoszą się:
- profil,
- nawierzchnia,
- ekspozycja,
- lokalna osłona,
- charakter zakrętów.

T5/T6 w obecnej dokumentacji to dobry zalążek.

### 7.2 Wind prior — P1/P2

Zamiast:
- całkowicie wolnego fitu wiatru,
- albo twardej prognozy,

zastosować prior:

`wind ~ N(forecast * k_exposure, sigma)`

Współczynnik ekspozycji może zależeć od typu terenu/miejsca i być uczony historycznie.

### 7.3 Ride quality / confidence

Każda jazda powinna dostać jawny score oparty m.in. na:
- liczbie dobrych okien,
- spread kierunków,
- residual RMS,
- jakości wiatru,
- zmienności mocy,
- jakości grade/elevation,
- udziale nawierzchni,
- stanie miernika,
- road-state uncertainty.

Klasy np.:
- HIGH / A,
- MEDIUM / B,
- LOW / C,
- REJECT.

Kanon CdA roweru powinien ważyć jazdy wg jakości, a nie tylko formalnego `cda_se`.

### 7.4 Canonical bike detection

`fitmodel/cda.py` ma własne mapowanie roweru przez AXS/device IDs, mimo że repo ma już `qbot3.rides.activity_devices.bike_for_ride()`.

To jest niepotrzebna duplikacja i ryzyko rozjazdu.

Był już przypadek `bike=NULL` w `ride_cda` (14.10; FIT miał praktycznie tylko Tacx device_info).

Docelowo CdA powinno korzystać z jednej kanonicznej ścieżki `bike_for_ride()` + ewentualny jawny fallback/manual override.

---

## 8. Test harness — warunek przed dalszym strojeniem

QExt2 ma rozbudowaną infrastrukturę testów i replay, ale brak dedykowanego `AeroEstimatorTest` dla obecnego algorytmu AERO.

Przed strojeniem v3 należy zbudować deterministyczny harness.

Minimalne scenariusze syntetyczne:

1. stałe CdA/Crr/wiatr → wynik 0 W,
2. CdA +0.02 → wykryta strata,
3. CdA -0.03 → wykryty zysk,
4. headwind +1 m/s bez zmiany pozycji → 0 W pozycji,
5. Crr +0.002 bez zmiany pozycji → 0 W pozycji,
6. asfalt → szuter → 0 W pozycji albo confidence low,
7. grade bias +0.1% → brak pewnego wyniku / obniżony confidence,
8. przyspieszenie → poprawna kompensacja lub brak pomiaru,
9. drafting → zakłócenie / low confidence, nie „pozycja”,
10. crosswind → brak fałszywego skoku,
11. poryw wiatru → brak trwałego false positive,
12. realna zmiana pozycji + zmienny wiatr → poprawna delta.

### Replay FIT

Offline replay powinien wykonywać TEN SAM rdzeń algorytmu, który działa na Karoo.

Nie osobną implementację „podobnego” algorytmu.

To jest krytyczne, bo v2 zostało dotąd ocenione głównie przez symulację/replay na FIT z v1, a nie realny przebieg aplikacji v2.

---

## 9. Priorytety wdrożenia

### P0 — bez tego nie stroić AERO dalej

1. wspólna masa QBot/QExt2,
2. Crr z QBot zamiast stałego 0.007,
3. wiatr w równaniu QExt2,
4. poprawa grade / przejście na bilans energetyczny po oknie,
5. confidence / quality gate,
6. deterministyczne testy AERO + replay tego samego rdzenia.

### P1

7. matched segments w QBot,
8. canonical `bike_for_ride()`,
9. road-state residual,
10. jawny ride quality score,
11. kontrakt API `aero-config` QBot → QExt2.

### P2

12. probabilistyczny wind prior,
13. model ekspozycji wiatrowej per miejsce,
14. yaw/crosswind refinement,
15. uczenie road-state z większej historii.

---

## 10. Co zachować z obecnego AERO

Nie trzeba wyrzucać całej infrastruktury.

Warto zachować:
- minimalną prędkość,
- minimalną moc,
- kontrolę kadencji,
- odrzucanie dużych przyspieszeń,
- segmentację po kierunku,
- zapis pól FIT,
- integrację QBot ↔ QExt2,
- 30–60 s jako sensowny rząd wielkości okien,
- możliwość offline replay.

Do przebudowy jest głównie model fizyczny i semantyka wyniku.

---

## 11. Docelowy kontrakt między QBot i QExt2

QBot powinien udostępnić wersjonowany zestaw parametrów:

- `system_mass_kg`,
- `cda_canonical` per bike,
- `crr_by_surface`,
- uncertainty/confidence,
- model/version id,
- surface profile route,
- opcjonalnie road-state correction,
- opcjonalnie wind exposure priors.

QExt2 dodaje live:

- power,
- speed,
- heading,
- grade/elevation,
- wind vector,
- route position,
- surface,
- freshness/quality.

Wynik live:

- `delta_cda` diagnostycznie,
- `delta_w` jako główna wartość,
- confidence,
- reason/quality flags.

UI preferowane:

`POZYCJA -8 W  ●`

zamiast absolutnego `CdA 0.xxx` jako głównego live field.

---

## 12. Najważniejsza zasada projektowa

Najlepszy moduł nie jest tym, który najczęściej pokazuje liczbę.

Najlepszy moduł to taki, który:

1. potrafi rozdzielić aero od rolling/wind/grade na tyle, na ile pozwalają dane,
2. umie powiedzieć „nie da się tego teraz wiarygodnie zmierzyć”,
3. nie zamienia każdego residualu mocy na CdA,
4. ma identyczne definicje parametrów w QBot i QExt2,
5. jest walidowany tym samym kodem na syntetyce, replay i realnej jeździe.

---

## 13. Co jeszcze zostało do zrobienia po tym audycie

Nie ma brakującego elementu analizy, który blokuje projektowanie v3.

Otwarte rzeczy są już częścią wdrożenia/walidacji:

- testy syntetyczne,
- realny replay v3,
- pierwsza jazda terenowa z v3,
- kalibracja confidence/progów dopiero po poprawie fizyki,
- później matched segments / road-state / wind prior.

Następna sesja może zacząć od projektu i implementacji P0, bez ponownego audytowania starego AERO v1/v2 od zera.
