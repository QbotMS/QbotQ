# AERO / Centrum CdA — pełny opis do audytu

Stan na 19.10.2026. Autor: sesja Claude „claude-aero” (18–19.10.2026), na decyzjach Michała.
Cel dokumentu: jedno miejsce z całą logiką, algorytmami, parametrami, testami, ustaleniami, decyzjami i znanymi
problemami tematu AERO (opór powietrza i toczenia) w QBot oraz powiązanych zmian (strażnik miernika).
Źródło prawdy to kod — tu są odwołania do plików/funkcji. Liczby z testów są z dnia testu (dane się zmieniają).

---

## 0. Słownik (prosto)

| Pojęcie | Znaczenie |
|---|---|
| CdA | „opór sylwetki”: powierzchnia czołowa × współczynnik oporu [m²]. Większe = więcej W na powietrze. |
| Crr | współczynnik oporu toczenia (opony + nawierzchnia). Moc toczenia = m·g·Crr·v. |
| ρ (rho) | gęstość powietrza [kg/m³] = p / (287,05 · (T + 273,15)), p w Pa. |
| Moc na powietrze | ½ · ρ · CdA · v_pow² · v (v_pow = prędkość względem powietrza, z wiatrem). |
| Odcinek / okno | 30-sekundowy fragment jazdy (krok 10 s) spełniający filtry (płasko, równo, prosto). |
| Kotwica | wartość ZAŁOŻONA (nie liczona), od której liczy się resztę — tu Crr asfaltu. |
| Kanon | jedno źródło wartości CdA/Crr/masy dla całego QBota (`fitmodel.cda.canon`). |
| XSS | obciążenie treningowe (ModelQ). „Planowane XSS” = obciążenie trasy liczone przed jazdą. |
| Pole AERO | pole QExt2 na Karoo liczące opór na żywo (osobny projekt; tu tylko sprawdzian). |

---

## 1. Cel i decyzje Michała (chronologicznie)

| Data | Decyzja | Gdzie zapisane |
|---|---|---|
| 18.10 | Jedno miejsce na aero: **„Centrum CdA” jako zakładka w Formie**, niepowiązane z pojedynczą jazdą (pojedyncza jazda za bardzo zaszumiona). Raport jazdy co najwyżej 1 linijka. | DECISIONS 18.10, TODO [AERO-CDA] |
| 18.10 | Najpierw sprawdzić mierniki mocy (Michał: wzrost formy możliwy; Favero nie używany w tygodniu 12–18.10; Quarq przełożony z Grizla na Graila 14.10; Quarq ma automatyczne zero). | DECISIONS 18.10 (jeden strażnik) |
| 18.10 | Brak czujników w FIT → nie zgadywać miernika. Temperatury nie używać jako automatycznej wymówki („może jechałem mocniej / lepszy dzień”). | j.w. |
| 18.10 | **Jeden strażnik** wiarygodności mocy (było 5 bytów) — stary `power_meter_guard` usunięty. | DECISIONS 18.10 „Jeden strażnik … etap A” |
| 18.10 | Etap B (3 dalsze zmiany strażnika) — po sprawdzeniu DECISIONS **odrzucony** (wszystkie 3 zasady mają powód). | DECISIONS 18.10 |
| 18.10 | „Zrób to produkcyjnie — będę tam oceniał” (Centrum CdA na produkcji, nie tylko makieta). | DECISIONS „Centrum CdA v1” |
| 18.10 | „Rób oba”: liczony Crr + zapis/sprawdzian pola AERO z FIT. | DECISIONS „Centrum CdA v2” |
| 18.10 | Przepięcie innych miejsc na kanon: raport jazdy TAK; obciążenie tras TAK z jawnym współczynnikiem zmienności (test); ocena podjazdów i kontrola miernika — dopiero po teście (test wypadł na niekorzyść → zostają). | DECISIONS „Kanon”, „XSS tras”, „podjazdy” |
| 19.10 | **Cel pola AERO = optymalizacja oporu, na który Michał ma wpływ (pozycja)**, żeby jeździć efektywniej. Pole NIE miało mierzyć zmiany asfalt→szuter. Wartość „droga” na żywo bez sensu, jeśli szuter kosztuje zawsze podobnie. | tylko ta rozmowa + ten plik |
| 19.10 | Testy na trasach **MyBIOM** (najczęściej jeżdżone), Grail vs Grizl; uwzględnić jazdy zimowe. | ten plik, rozdz. 9 |

---

## 2. Architektura — co gdzie jest

```
FIT (Karoo) --fit_ingest--> activity_record (1 Hz), activity_device, fitmodel_qext2_ride, qext2_aero_record (pole AERO)
raport jazdy (ride_report_builder) --> ride_report_data.w1_json.trace (km, surface_cat), weather (pressure_hpa, precip)
                                   \-> energy (podział energii)  <-- cda.canon()
daily_job krok 'cda' --> cda.run() --> ride_cda (jazda), cda_crr (nawierzchnia), cda_xss_calib (co 7 dni)
/api/forma/cda --> cda.summary() --> forma-cda.js (Forma > Centrum CdA)
route_xss_phys._estimate_route_xss_phys --> cda.route_physics_params() (kanon + współczynnik zmienności)
```

### Pliki

| Plik | Rola |
|---|---|
| `fitmodel/cda.py` | Całe liczenie CdA/Crr, kanon (`canon`, `route_physics_params`), kalibracja XSS (`calibrate_xss`), dane strony (`summary`), sprawdzian pola AERO (`_aero_checks`). |
| `fitmodel/qext2_aero.py` | Zapis 4 pól AERO z FIT (`store`, `backfill`) i sprawdzian jednej jazdy (`ride_check`). |
| `fitmodel/fit_ingest.py` | `_QEXT2_FIELDS` + 4 pola AERO; po `upsert_qext2_ride` woła `qext2_aero.store` (no-op gdy brak pól). |
| `fitmodel/daily_job.py` | Kroki `p_at_hr` i `cda` (w obu przebiegach joba). |
| `qbot_web.py` | Endpoint `GET /api/forma/cda` (używa `fitmodel.api._db_connect`, kursor krotkowy). |
| `web/public/forma.html` | Zakładka `data-t="cda"`, sekcja `#p-cda`, skrypt `forma-cda.js?v=3`. |
| `web/public/forma-cda.js` | Render strony (karty rowerów, tabela Crr, kalibracja XSS, porównania, sprawdzian pola, wykres, jakość danych). |
| `qbot3/rides/ride_report_builder.py` | `_energy(recs, ride_key, day)` — podział energii z kanonu; progi substratu od TP. |
| `qbot3/routes/route_xss_phys.py` | `_estimate_route_xss_phys(..., factor=None, legacy=False)` — XSS tras z kanonu × współczynnik. |
| `fitmodel/p_at_hr.py` | „Moc przy tym samym tętnie” jako wskaźnik formy (zastąpił stary strażnik). |
| `fitmodel/telegram_notify.py` | Wspólne wysyłanie Telegrama (przeniesione ze starego strażnika). |
| `archive/fitmodel_power_meter_guard.20261018.py` | Stary strażnik (wycofany). |

### Tabele (schemat `qbot_v2`)

| Tabela | Klucz | Kolumny | Kto pisze |
|---|---|---|---|
| `ride_cda` | external_id | ride_date, bike, meter_key, n_windows, dir_spread, wind_ms, wind_from_deg, cda, cda_se, explained_pct, rho, status (OK/POMINIETA), reason, computed_at | `cda.run` |
| `cda_crr` | cat (1–4) | crr, n_windows, n_rides, source (kotwica/liczony/za mało danych), computed_at | `cda.run` |
| `cda_xss_calib` | computed_at | factor, n_rides, err_new_pct, err_old_pct, half_new_pct, half_old_pct | `cda.calibrate_xss` |
| `qext2_aero_record` | (external_id, ts) | state, dw_w, cda, ref_cda (1 Hz) | `qext2_aero.store` |
| `ride_p_at_hr` | external_id | ride_date, p_at_hr_w, meter_key, temp_c, computed_at | `p_at_hr.run` |
| `power_meter_guard` | — | historia starego strażnika; **nic jej już nie czyta** | — |

Czytane: `activity_record`, `activity_device`, `ride_report_data` (trace, weather), `fitmodel_daily` (waga),
`fitmodel_ride_quarantine`, `load_guard`, `modelq2_ride` (XSS, sygnatura), `training_sessions`, Garaż `data/garage.db`
(`ride_gear_log`, `gear`, `components`).

---

## 3. Centrum CdA — algorytm (`fitmodel/cda.py`)

### 3.1 Które jazdy
- `training_sessions`: `date >= CDA_SINCE` (**2026-06-16** — od tej daty są raporty jazd z nawierzchnią), `avg_power_w IS NOT NULL`, `distance_m > 10000`.
- Pominięcie (status POMINIETA, `reason`), kolejność sprawdzania (`_excluded`):
  1. kwarantanna aktywna (`fitmodel_ride_quarantine.released IS NULL`) → „kwarantanna miernika”;
  2. dzień w `fitmodel.lthr.METER_BAD` (01.07–25.08.2026) → „zły okres miernika”;
  3. `load_guard.ratio` poza `[load_guard.LO, load_guard.HI]` → „moc i tętno się rozjeżdżają” (dotyczy też krótkich jazd);
  4. brak `trace` w raporcie → „brak raportu jazdy (nawierzchnia)”;
  5. mniej niż `MIN_WIN = 12` odcinków → „za mało płaskich, równych odcinków”;
  6. wynik CdA poza 0,15–0,9 → „wynik poza zakresem fizycznym”.

### 3.2 Rower i miernik (`bike_and_meter`)
- `activity_device`: urządzenie `device_type='34'` i `manufacturer='sram'` (AXS) → `AXS_BIKE = {27856: "Grail", 10625: "Grizl"}`, inny numer → `"AXS <nr>"`.
- Brak AXS, ale jest `bike_power` → **Monster**. Brak czujników (FIT po restarcie Karoo) → `None` („nieznany”).
- Miernik: `ant:<ant_device_number>` albo `sn:<serial>` pierwszego `bike_power`.
- Uwaga: celowo NIE `qbot3.rides.activity_devices.bike_for_ride` (mapa `bike_sensor` była nieaktualna po przełożeniu Quarqa).

### 3.3 Odcinki (`windows`)
Dane: `activity_record` (sec, power_w, speed_mps, distance_m, altitude_m, cadence_rpm, temperature_c, lat, lon, ts).
Okno = 31 próbek (30 s), krok 10 s. Odrzucane, gdy:
- jakakolwiek brakująca wartość mocy/prędkości/dystansu/wysokości/lat;
- `min(moc) < 60 W` lub `CV mocy > 0,25` (odch. std / średnia);
- `śr. prędkość < VMIN = 4,0 m/s` (14,4 km/h) lub `min prędkość < VMIN − 1`;
- brak kadencji lub `min(kadencja) < 50`;
- dystans okna `< 80 m`;
- `|nachylenie| > 2 %` (nachylenie = Δwysokość / dystans okna);
- zmiana kursu między połówkami okna `> 35°`;
- nawierzchnia (z `trace.surface_cat` w punkcie środka okna, po km) **nie w {1,2,3,4}** (5 = ryzyko/niepewna i nieznana — pomijane).

Dla okna liczone (kolumny macierzy W):
- `v = dystans / 30`; `T` = średnia temperatura okna (brak → 12 °C); `p` = ciśnienie z raportu `weather.pressure_hpa.value` (brak → 1013 hPa);
- `ρ = p·100 / (287,05·(T+273,15))`;
- masa `m = waga dnia (fitmodel_daily, ostatnia ≤ dzień jazdy) + EXTRA_KG` (`fitmodel.meter_physics.EXTRA_KG = 14 kg`; brak wagi → 100 kg);
- `kin = ½·m·(v_koniec² − v_start²) / 30`;
- `Pa0 = śr.moc · 0,976 − m·g·v·nachylenie − kin` (0,976 = sprawność napędu, g = 9,81);
- `xr = m·g·v` (mnożnik Crr), kurs `h` (start→koniec), kategoria `cat`, czas startu/końca okna (epoch).

### 3.4 Dopasowanie jednej jazdy (`fit_ride`)
- `Pa = Pa0 − xr · Crr[cat]` (moc na powietrze przy danym Crr).
- Siatka wiatru: siła `0…7 m/s` co 0,25 × kierunek `0…350°` co 10° (1 044 kombinacje, numpy).
- `v_pow = v + s·cos(θ − h)`, `X = ½·ρ·v_pow·|v_pow|·v`.
- `CdA = (X·Pa) / (X·X)` (najmniejsze kwadraty bez wyrazu wolnego), wybór kombinacji o najmniejszym SSE.
- Błąd: `se = √(SSE / (n−1) / ΣX²)`.
- `explained_pct = 100·(1 − SSE / SSE0)`, SSE0 = dopasowanie bez wiatru.
- `dir_spread = 1 − |Σ wektorów kursu| / n` (0 = jeden kierunek → wiatr słabo wyznaczony).

### 3.5 Wspólne liczenie Crr (`joint_fit`) — v2
- Start: `CRR_START = {1: 0,0055, 2: 0,0085, 3: 0,012, 4: 0,018}`.
- **Kotwica: Crr kat. 1 (twarda szybka / asfalt) = `CRR_ANCHOR = 0,0055` — nie liczony.**
- Pętla (max 20): (a) dla każdej jazdy `fit_ride` przy bieżących Crr; (b) dla kat. 2–4 z ≥ `CRR_MIN_WIN = 150` odcinkami:
  `Crr_k = Σ(r · xr) / Σ(xr²)`, `r = Pa0 − CdA_jazdy · X_jazdy` po oknach kat. k ze wszystkich jazd; przycięcie do [0,002; 0,05];
  (c) stop, gdy maks. względna zmiana Crr < 0,2 %.
- Kategorie z < 150 odcinków zostają na starcie („za mało danych”).
- **Dlaczego kotwica:** bez niej (test T2) Crr rósł, a CdA malało bez końca — prędkości odcinków za mało różne, żeby rozdzielić v (toczenie) i v³ (powietrze).

### 3.6 Zapis
`run()` liczy WSZYSTKIE jazdy od CDA_SINCE przy każdym wywołaniu (ok. 5 s), upsert `ride_cda` i `cda_crr`, potem
`calibrate_xss` (co 7 dni). daily_job woła `run(conn, lookback_days=7)` — parametr ignorowany (pełne przeliczenie).

### 3.7 Kanon roweru (strona i `canon`)
- Jazdy OK roweru z ostatnich `CANON_DAYS = 120` dni.
- **Mediana ważona** CdA, waga = `1 / max(se, 0,01)²`.
- „typowo” = kwartyle 25–75 % (nieważone).
- Status: `n < 3` → „za mało danych”; `n ≥ 8` i `(Q75 − Q25) / mediana ≤ 0,15` → „pewne”; inaczej „niepewne”.

### 3.8 Porównania (strój, koła, rower)
- Garaż: `ride_gear_log` (sloty `CMP_SLOTS = Kurtka, Kamizelka, Koszulka / bluza, Nakrycie głowy, Komin i chusta, Nogawki, wheels`).
  Warstwy pod spodem (termika) **wyłączone** — dawały pozorne „pewne” z pory roku (−0,09 CdA przy 3 vs 3 jazdach).
- Dla rzeczy: rower = ten, na którym rzecz była najczęściej; jazdy Z rzeczą vs jazdy BEZ niej (tylko jazdy z wpisem stroju, ten rower).
- Wynik dopiero od `CMP_MIN = 5` jazd po każdej stronie. `d = średnia_z − średnia_bez`, `se = √(var_z/n_z + var_bez/n_bez)`.
  „pewne” gdy `|d| > 2·se` **i** min(n) ≥ `CMP_SURE = 8`; „możliwe” gdy `|d| > se`; inaczej „bez różnicy”.
- Rower vs rower: wszystkie jazdy OK (bez okna 120 dni), te same progi.
- Na stronie wat przy prędkości v: `ΔP = ½ · 1,2 · ΔCdA · v³` (bez wiatru; 25/30/35 km/h).

### 3.9 Kanon dla reszty QBota
- `canon(external_id=None, day=None)` → `{cda, cda_src, crr{1..4}, crr_unknown, mass}`:
  CdA tej jazdy (ride_cda OK) → mediana ważona roweru jazdy (120 dni) → mediana ważona wszystkich → 0,42.
  `crr_unknown` = średnia kat. 2–4. `mass` = waga dnia + 14 kg. Własne połączenie DB.
- `route_physics_params()` (pamięć 10 min) → `cda` (wszystkie rowery), `crr_paved` = kat. 1, `crr_unpaved` = średnia kat. 2–4,
  `crr_unknown` = (asfalt + szuter)/2, `extra_kg` = 14, `factor` = ostatni z `cda_xss_calib` (brak → `XSS_FACTOR_DEFAULT = 1,17`).

---

## 4. Użycie kanonu w QBot

### 4.1 Raport jazdy — `ride_report_builder._energy(recs, ride_key, day)`
- Na rekord (1 Hz): powietrze `½·1,2·CdA·v³`, toczenie `Crr[r["scat"]]·m·g·v` (brak kategorii → `crr_unknown`), wznoszenie `m·g·Δh` (tylko w górę), kinetyka (tylko przyrost).
- CdA/Crr/masa z `cda.canon(ride_key, day)`; zapas przy błędzie: stałe `CDA = 0,42`, `CRR = 0,010`, masa 108 kg.
- Źródło w tagu: `"Centrum CdA: ta jazda"` / `"rower Grail"` / …
- Substrat (udział węgli): progi `0,55·TP` i `0,75·TP`, **TP z `modelq2_ride.sig_tp_w` tej jazdy** (zapas: ostatnie TP; ostatni zapas 253) — było 253 na sztywno.
  **Ta zmiana nie jest w commicie na 19.10 rano.**
- Stare raporty zmienią podział energii dopiero przy przebudowie (świadomie nie przebudowywane — mała wartość, długi proces).

### 4.2 Obciążenie planowanych tras — `route_xss_phys._estimate_route_xss_phys`
- Segment 50 m: prędkość z modelu `segment_speed_kmh(nachylenie, asfalt/szuter, tryb)`, wiatr klimatologiczny (opcjonalnie, z azymutu),
  `P = (m·g·v·nachylenie + m·g·Crr·v + ½·1,2·CdA·v_pow·|v_pow|·v) / 0,97`, zjazd → 0, sekunda po sekundzie → `compute_xss`.
- Od 18.10: CdA/Crr z `route_physics_params`, **masa = waga (podana przez wołającego) + 14 kg**, wynik **× współczynnik zmienności**.
- `legacy=True` = stare stałe (CdA 0,4; Crr asfalt 0,010 / szuter 0,018 / nieznana 0,014; masa = sama waga; bez współczynnika) — tylko do porównań.
- Wołający: `qbot_web.py` (`_route_physics_xss` w analizie trasy, planer etapów) — przekazują **samą wagę zawodnika**.
- Zapisane analizy tras zmieniają się dopiero przy ponownym przeliczeniu trasy.

### 4.3 Kalibracja współczynnika — `cda.calibrate_xss(conn, force=False)`
- Raz na `XSS_CALIB_DAYS = 7` dni (w `run`).
- Jazdy: `ride_cda.status = 'OK'` ∩ `modelq2_ride.xss_source = 'power'`, `xss_total > 0`.
- Ślad jazdy → segmenty 50 m (dystans, nachylenie, nawierzchnia: kat. 1 → asfalt, 2–5 → szuter, brak → nieznana, środek lat/lon).
- Sygnatura jazdy `Signature.from_kj(sig_tp_w, sig_hie_kj, sig_pp_w)` z `modelq2_ride`.
- `new = _estimate_route_xss_phys(seg, sig, waga, "normalny", None, factor=1.0)`, `old = … legacy=True`.
- `factor = mediana(XSS_rzecz / new)`; błędy = mediana `|rzecz − f·new| / rzecz` i `|rzecz − old| / rzecz`;
  „połowa/połowa”: współczynnik z jazd parzystych, błąd na nieparzystych. Min. 10 jazd.

### 4.4 Gdzie kanonu NIE użyto (świadomie)
| Miejsce | Stałe | Dlaczego zostaje |
|---|---|---|
| `qbot3/routes/climb_score.py` (ocena podjazdów, `power_req`) | CdA 0,4; Crr kat. 1–5: 0,006 / 0,010 / 0,014 / 0,020 / 0,028 (domyślnie 0,010); rower 14 kg | Test T4: kanon gorszy na podjazdach. |
| `fitmodel/meter_physics.py` (kontrola miernika na podjazdach) | CdA 0,45; Crr 0,009; EXTRA_KG 14 | j.w.; kanon zaniżałby moc wymaganą → zawyżał wskaźnik miernika (próg bezpiecznika CP 1,15). |

---

## 5. Pole AERO z Karoo (QExt2) — w QBot tylko sprawdzian

### 5.1 Pole w QExt2 (repo QExt2, `engine/AeroEstimator.kt`, `docs/AERO.md`, od 0.4.1 z 17.10)
- Stałe: sprawność 0,976; **Crr 0,007 stały**; masa = waga + **9 kg**; VMIN 5 m/s; moc ≥ 60 W; |nachylenie| ≤ 4 %; |przysp.| ≤ 0,4 m/s²;
  kadencja ≥ 50; równość: 20 próbek, kadencja ±8, moc ±20 %; „teraz” 30 s, odniesienie 60 s przed; zmiana musi trwać 5 s;
  próg zgłoszenia zmiany 0,10 CdA; reset po 30 s nierównej jazdy; reset po zmianie kursu > 35° tylko przy wietrze ≥ 3 m/s.
- `Pa = moc_3s·0,976 − m·g·v·(nachylenie + 0,007) − m·v·a`; **wiatr nie wchodzi do prędkości powietrza** (tylko do resetu).
- Zapis do FIT co 1 s: `qext2_aero_state` (0 brak warunków / 1 zbiera / 2 pewny), `qext2_aero_dw_w`, `qext2_aero_cda`, `qext2_aero_ref_cda`.

### 5.2 Zapis w QBot (`fitmodel/qext2_aero.py`)
- `fit_ingest.parse_fit_qext2_records` czyta 4 pola; `store()` kasuje i wstawia rekordy jazdy do `qext2_aero_record`.
- **Czas zapisywany jak w `activity_record`: naiwny UTC** (baza traktuje go jak lokalny). Sprawdzone 18.10: `activity_record` 08:24+02 przy starcie 10:24 lokalnie — przy czasie „poprawnym” wychodziło 2 h przesunięcia.
- Wczytane: jazda 24766557671 (18.10), 8 819 s. Parsowanie FIT ~7–12 s/plik.

### 5.3 Sprawdzian (`qext2_aero.ride_check`, `cda._aero_checks`)
- % czasu w stanach 0/1/2.
- „Zmiana pokazana przez pole” = początek okresu z |dW| ≥ 1 W w stanie 1–2 (lub nowe odniesienie w trakcie). dW = 0 przy ref = cda to budowanie poziomu, nie zmiana.
- CdA pola = mediana `qext2_aero_cda` (stan 1–2, 0,1–1,5) vs CdA QBota tej jazdy.
- Zgodność = korelacja Pearsona między CdA odcinka QBota (`Pa / X` z dopasowania jazdy) a medianą CdA pola w tym oknie (≥ 10 próbek), min. 8 odcinków.
- Wynik 18.10: pewne 42,7 % / zbiera 27,5 % / brak 29,7 %; 6 zmian (km 30,4–32,2); CdA pola 0,626 vs QBot 0,511; zgodność r = 0,14 (168 odcinków).
- **Zastrzeżenie (19.10):** porównanie częściowo nieuczciwe — QBot odejmuje nawierzchnię i wiatr, pole nie. Do przerobienia po zmianie definicji pola (rozdz. 11).

---

## 6. Strażnik miernika mocy (zmiany 18.10)

- Przed: 5 bytów oceniających moc — stary strażnik P@HR (`power_meter_guard`, od 28.09 bez Telegrama, fałszywe ALERT-y), `load_guard` (aktywny, pyta na Telegramie), `meter_phys` (fizyka na podjazdach, bezpiecznik w `cp_breakthrough`), kwarantanna, `lthr.METER_BAD`.
- Po (etap A): stary strażnik usunięty; **`load_guard` + kwarantanna = jedyny sędzia**.
  - `p_at_hr.py`: mediana mocy z sekund z tętnem 115–134, kadencją ≥ 40, prędkością ≥ 3 m/s, mocą > 0; min. 600 s takich sekund (inaczej NULL); bez progów i werdyktów. Przeniesione 155 wartości ze starej tabeli. `season.py` czyta `ride_p_at_hr` (wykres „Wydolność” ciągły); usunięte `guard_alert_days` (season + prompt analizy w `qbot_web.py`).
  - `telegram_notify.send` — wspólna funkcja (6 modułów importowało ją ze starego strażnika).
- Etap B (odrzucony, z powodami w DECISIONS): `meter_phys < 1,15` w `cp_breakthrough` zostaje (fałszywa kotwica 11.08: miernik +25 %); uwaga o chłodzie w pytaniu `load_guard` zostaje (zgodna z `hr_xss_calib`: 1,018 + 0,0054·(T−15), n = 160 → przy ~4 °C kilka % niżej, w rozrzucie ±11 %); `METER_BAD` zostaje (świadomie szerszy od kwarantanny; obciążenie z mocy zostaje).
- `meter_phys` pod Warszawą od września bez wyników (płasko, < 5 okien podjazdowych) — **to nie awaria**.

---

## 7. Testy i wyniki (wszystkie skrypty były tymczasowe `scripts/_tmp_*.py`, samousuwające — tu metoda do odtworzenia)

### T1. Mierniki na Grailu (18.10)
- Metoda: stosunek NP / średnie tętno z całej jazdy, Grail, kolejne tygodnie.
- Favero 01–11.10 (6 jazd): 1,21–1,48, śr. 1,33. Quarq 14–18.10 (3 jazdy): 1,27–1,43, śr. 1,34. → **brak dowodu, że Quarq zawyża.**
- Stary strażnik: rozrzut P@HR tego samego miernika ±12 % (150–192 W) przy progu 8 % → test za mało czuły.
- 14.10: FIT bez czujników, strażnik zgadł Favero (zapas z biegów AXS), a był Quarq; spadek temp. w jeździe 10,7 → 6,3 °C;
  P@HR ćwiartki 151 / 186 / 178 / 198 W; Michał: 20 min deszczu → schłodzenie, niższe tętno.
- `load_guard` dla października: OK / KRÓTKA (bez alarmów).

### T2. Rozdzielanie CdA i Crr (18.10, 25 jazd, 2 357 okien od 4 m/s; kat. 1: 1 266, 2: 480, 3: 314, 4: 297)
- Bez kotwicy: 8 iteracji — Crr kat. 1 0,0060 → 0,0079 (rośnie), CdA Grail 0,430 → 0,370 (maleje) → **brak zbieżności**.
- Z kotwicą asfaltu 0,0045 / 0,0055 / 0,0065: różnica gravelu (kat. 2–4) vs asfalt stabilnie **+0,0050…+0,0056** niezależnie od kotwicy;
  CdA Grail 0,458 / 0,430 / 0,401, Grizl 0,435 / 0,403 / 0,373 → ±0,001 Crr ≈ ∓0,03 CdA. Poziom CdA zależy od kotwicy, porównania nie.
- Produkcja 18.10: Crr kat. 1–4 = 0,0055 / 0,0105 / 0,0109 / 0,0106; 27 jazd OK; Grail 0,430, Grizl 0,402 (pewne), Monster 0,601.

### T3. XSS planowanych tras (18.10)
- A. Rzeczywista prędkość odcinka, masa +14 kg w obu: stare stałe rzecz/plan 0,88 (plan zawyża), kanon 1,12; błąd stare ~14 %, kanon × wsp. ~6,7 %.
- B. Prędkość z modelu (jak planer), masa +14 kg w obu: stare 0,916, błąd 10,7 %; kanon × 1,174: 4,6 %; połowa/połowa 3,7 % vs 8,3 %.
- **C. Produkcja (`calibrate_xss`, stary model z samą wagą jak w produkcji): współczynnik 1,2133; błąd 5,1 % vs 5,4 %; połowa/połowa 4,5 % vs 5,4 % (27 jazd).**
- **Korekta:** liczby z A/B przedstawione Michałowi jako „10,7 % → 4,6 %” były błędne (stary model liczony z masą, której produkcja nie podaje). Rzeczywista poprawa mała; zysk = spójność (jedno źródło, masa roweru, jawny współczynnik zamiast ukrytego w zawyżonym Crr).

### T4. Ocena podjazdów (18.10)
- `ride_climb_efforts` od 16.06, bez kwarantanny i pchania, ≥ 60 s, moc > 50 W: **n = 9**.
- Moc wymagana przy RZECZYWISTEJ prędkości podjazdu vs zmierzona × 0,97.
- Stare: plan/rzecz 0,887, błąd 11,3 %; kanon: 0,859, 14,1 %. Asfalt/dobry: 8,4 vs 9,3 %; szuter 3–5: 15,4 vs 20,1 %.
- Wniosek: Crr kanonu pochodzi z płaskich, szybkich odcinków; na wolnym, luźnym podjeździe realny opór wyższy → nie przepinać; powtórzyć przy ≥ 30 podjazdach.

### T5. MyBIOM — opór drogi wg roweru i nawierzchni (19.10)
- Jazdy MyBIOM (nazwy na Stravie ~„biom”; `qbot_strava_publish.kind_model`): Grail 08.10, 14.10; Grizl 26.08, 27.08, 28.08, 01.09, 08.09; Monster 11.09, 18.09, 22.09.
- Odcinki jak w 3.3, ale od 2,5 m/s, moc ≥ 40 W, CV ≤ 0,3, dystans ≥ 60 m, wszystkie kategorie.
  Efektywny Crr odcinka = `(Pa0 − ½·ρ·CdA_roweru·v_pow·|v_pow|·v) / (m·g·v)`, CdA roweru = mediana z Centrum CdA (Grail 0,430 / Grizl 0,403 / Monster 0,573), wiatr z `ride_cda`.
- Mediany Crr: asfalt 0,0054 / 0,0054 / 0,0047 (Grail/Grizl/Monster); dobry gravel 0,0107 / 0,0091 / 0,0102; zwykły 0,0118 / 0,0113 / 0,0113;
  trudna/wolna 0,0104 / 0,0103 / 0,0115; ryzyko 0,0113 / 0,0103 / 0,0094.
- **Wolnych odcinków (< 14 km/h) brak** — w Puszczy nawet „trudna” jest przejezdna szybko.
- Te same miejsca (kafelek ~150 m): Grail−Monster −0,0010 (29 miejsc), Grizl−Monster −0,0006 (41), Grail−Grizl +0,0009 (44) → opony różnią się minimalnie.
- Rozrzut między miejscami (78 kafelków, nieutwardzone): 10 % 0,0073 | 50 % 0,0101 | 90 % 0,0117 | max 0,0162 → przy 25 km/h ok. **35 W** między łatwym a trudnym fragmentem tego samego „szutru”. Kategorie z mapy tego nie rozróżniają.

### T6. MyBIOM — stan drogi w różnych dniach (19.10)
- Mapa miejsc z 9 letnich jazd z raportem (200 kafelków, 79 z medianą letnią z ≥ 3 odcinków). Dla każdej jazdy MyBIOM (też starych bez raportu):
  kategoria z mapy, wiatr dopasowany przy CdA roweru, różnica efektywnego Crr od mediany letniej TEGO SAMEGO miejsca, w W przy 20 km/h (m = 115 kg).
- Wyniki: 25.01.2025 (8 °C) +1 W; **13.02.2025 (4 °C) +13 W**; 16.04.2025 +1 W; **18.05.2026 (15 °C) +10 W**; 23.05.2026 +1 W;
  **14.10.2026 (deszcz, 8 °C) +16 W**; jazdy letnie (kontrola, w próbie) −3…+5 W, Grail 08.10 −10 W.
- 23.04.2025: za mało odcinków na znanych miejscach. Stare jazdy: AXS bez numeru → rower przyjęty „Grizl?”; 14.10 to Grail (FIT bez czujników).
- Wniosek: **stan drogi zmienia się z dnia na dzień o +10–16 W przy 20 km/h** (~+20–25 % oporu szutru); nie każdy zimowy dzień gorszy (25.01 jak lato — możliwe zmarznięte podłoże, niepotwierdzone).
- Skutek: ciężka droga zawyża CdA jazdy w Centrum CdA (14.10: 0,51–0,55 zamiast ~0,43).

### T7. Inne sprawdzenia
- Nawierzchnia w raportach (krok 1 [AERO-CDA]): 56/56 raportów schema 3 z nawierzchnią (naprawa 16.10: wspólny plik GPX → Permission denied).
- Repo KarooBBrakers (zewnętrzne, hamulce): nic do przeniesienia; pomysł na później — wykrywanie nawierzchni z drgań akcelerometru Karoo.
- Strona Centrum CdA: Playwright 1440 px i 390 px — bez błędów JS, bez przewijania w bok, dymki działają (18.10).

---

## 8. Stan danych (18–19.10)
- Jazdy od 16.06 z mocą > 10 km: 56; użyte 27, pominięte 29 (głównie kwarantanna i zły okres miernika).
- Wpisy „W czym jechałem”: 10 jazd (koła 1) → porównania stroju prawie wszystkie „za mało danych”.
- Monster: 1 jazda użyta (niepewne).
- Pole AERO w bazie: 1 jazda (18.10).

---

## 9. Znane problemy, ryzyka, ograniczenia
1. **Kotwica Crr asfaltu (0,0055) jest założeniem** — od niej zależy poziom CdA (±0,03 na ±0,001), nie porównania.
2. **Kategorie nawierzchni z mapy (OSM) są zgrubne** i nie znają stanu drogi (mokro, śnieg, piach). T5/T6: różnice między miejscami (~35 W) i dniami (+10–16 W) są większe niż między kategoriami.
3. **Stan drogi wpływa na CdA jazdy** (mokra droga udaje gorszą pozycję) — brak korekty (otwarte).
4. **Pogoda w raporcie nie wykryła deszczu 14.10** (flaga „mokro” fałszywa) — do sprawdzenia.
5. Wiatr z jazdy: jazda w jednym kierunku (`dir_spread` < 0,3) → słabo wyznaczony; siatka max 7 m/s.
6. Crr z płaskich szybkich odcinków nie przenosi się na wolne podjazdy (T4).
7. FIT bez czujników → rower „nieznany” (jazda liczona, ale bez przypisania roweru do kanonu).
8. Porównania stroju to poszlaki (zwykłe jazdy różnią się wieloma rzeczami naraz).
9. Restart qbot-api 18.10 zerwał połączenie DEV MCP — usługi aktywne; nie zweryfikowano, czy qbot-api wczytał nowy `route_xss_phys` (używa go głównie qbot-web).
10. Test w T3 C i T4 to mediany na 27 / 9 próbkach.

---

## 10. Commity (repo /opt/qbot/app)
| Commit | Treść |
|---|---|
| c8a33a7, 7c7dd7f | (16–17.10, inna sesja) nawierzchnia w raportach, koła/opony w „W czym jechałem” |
| c139837 | TODO: krok 1 ZROBIONE + decyzje Centrum CdA |
| 479c164 | Jeden strażnik miernika (etap A) |
| 1499600 | Centrum CdA v1 |
| 1184727 | Centrum CdA v2: Crr z jazd, pole AERO z FIT + sprawdzian |
| bd153ad | Kanon (`cda.canon`), raport jazdy: podział energii z kanonu |
| dfb26d1 | XSS tras z kanonu + współczynnik zmienności |
| — (niezacommitowane 19.10) | `ride_report_builder.py`: progi substratu od TP |
Dokumentacja: `docs/DECISIONS.md` (wpisy 18.10), `docs/TODO.md` ([AERO-CDA] kroki 1–8), ten plik.

---

## 11. Otwarte (do decyzji Michała)
1. **„Stan drogi” w QBot:** na powtarzanych trasach liczyć różnicę oporu od typowego w tych samych miejscach (metoda T6) i korygować CdA jazdy; pokazać w Centrum CdA / raporcie („droga ciężka: +15 W”).
2. **Pole AERO (QExt2, osobna sesja)** — propozycja po 19.10: jedna liczba POZYCJA (W), z odjętym wiatrem (karoo-headwind na żywo) i drogą (asfalt/szuter z trasy QBota co 50 m; bez trasy = asfalt); masa +14 kg; na szutrze oznaczenie „niska pewność” (T5/T6: droga zmienia się o ±15–20 W, tyle co pozycja). QBot musiałby wysłać: kanon CdA/Crr/masa + nawierzchnię trasy (np. obok `/api/plan/by-name`).
3. **Sprawdzian pola AERO** przerobić pod nową definicję (porównanie „pozycji” z odjętą drogą i wiatrem).
4. **Deszcz 14.10 niewykryty** przez pogodę QBota — diagnoza.
5. Powtórzyć T4 (podjazdy) przy ≥ 30 podjazdach; ewentualnie osobny Crr dla wolnych odcinków.
6. Krok 6 [AERO-CDA]: porównania na wspólnych odcinkach (metoda kafelków z T5/T6 jest gotowym zalążkiem).
7. Wykrywanie nawierzchni z drgań akcelerometru Karoo (pomysł, niezbadany).
