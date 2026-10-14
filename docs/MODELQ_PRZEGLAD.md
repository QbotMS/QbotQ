# ModelQ — przegląd od podstaw (MODELQ-PRZEGLAD)

Powód (Michał, 2026-10-14): „średnio raz w tygodniu do tego wracamy i ciągle jest źle”.
Zasada: najpierw inwentaryzacja i diagnoza na liczbach, potem plan do decyzji. Do czasu decyzji NIC w działającym ModelQ się nie zmienia.

## Etap 1 — inwentaryzacja (2026-10-14, tylko odczyt)

### 1. Co ModelQ podaje reszcie QBota
Tabela `qbot_v2.fitmodel_daily` (publikacja: `fitmodel/modelq2/publish.py`, krok `run_daily_v2` w daily_job):
| kolumna | znaczenie | uwaga |
|---|---|---|
| `cp_modelq_w`, `ftp_est_w` | **TP** (próg) z sygnatury MQ2 | nazwa „cp” historyczna — to NIE jest CP z krzywej moc-czas |
| `ltp_modelq_w` | LTP = EMA28(TP − HIE/400) | |
| `wprime_modelq_kj` | **HIE** (zapas na mocne wysiłki, odpowiednik W′) | |
| `pp_modelq_w` | PP (moc szczytowa) | |
| `ctl_xss`, `atl_raw/atl_plus`, `tsb_*` | forma / zmęczenie z XSS | kanon świeżości = wersja „po korekcie” (atl_real/tsb_real) |

Konsumenci (pliki czytające te pola): Karoo (`fitmodel/threshold_sync.py` → intervals.icu → Hammerhead; `mcp_server.py`), Trener
(`qbot_trener_api.py`, `qbot_trener_stats.py`), raporty jazdy i tras (`qbot3/rides/ride_report_builder.py`, `qbot3/routes/route_report_canonical.py`,
`tools/rwgps/route_brief.py`, `tools/rwgps/ride_verdict.py`), Forma/web (`qbot_web.py`, `fitmodel/api.py`), Albert (`qbot_integration_tools.py`),
oraz moduły pochodne: W′bal (`wbal_replay.py`), glikogen, kubełki XSS, LTHR, HRR, VO2max (zamrożony), dryf/upał.
**Każdy błąd TP/HIE rozlewa się na całego QBota** (strefy na Karoo, plan Trenera, XSS, świeżość, raporty).

### 2. Skąd biorą się wartości
- **5 kotwic, wszystkie przepisane z Xerta** (`qbot_v2.modelq2_anchor`, zamrożone 08.07.2026):
  27.12.2025 TP 244 / HIE 20,6 · 22.02.2026 239 / 20,2 · 29.03 245 / 22,5 · 16.05 245 / 21,3 · **20.06 251 / 22,7** (najnowsza).
- **Dzienna sygnatura = najbliższa kotwica przesunięta wzorem** (`fitmodel/modelq2/decay.py`), bez pomiaru:
  - TP = TP_kotwicy + 0,66 W × (CTL_dnia − CTL_kotwicy), ograniczone do −10 % / +12 % kotwicy,
  - HIE = HIE_kotwicy × (obciążenie intensywne dnia / w kotwicy), ograniczone do ±20 %,
  - PP idzie lekko za HIE.
- `modelq2_signature`: **652 dni, 100 % `source='decay'`** — ani jeden dzień nie pochodzi z pomiaru.
- Dziś: TP 239 = 251 + 0,66 × (58 − 76); HIE 18,2 = **dolna granica** 0,8 × 22,7 (przyklejone do ogranicznika od sierpnia).

### 3. Mechanizmy korekty i ich stan
| mechanizm | plik | stan |
|---|---|---|
| kotwica EF (z tętna/mocy, „w górę”) | `modelq2/publish.py` | **WYŁĄCZONA od 25.08** („tymczasowo do ~5.09”, nie włączona); kotwica 11.08 (+25 % miernik) usunięta 08.10 |
| przełom CP z krzywej moc-czas (2/5/10/20 min ponad krzywą modelu, z potwierdzeniem na Telegramie) | `cp_breakthrough.py` | **WŁĄCZONY od 08.10**; sprawdzono 136 jazd, **0 przełomów** (backtest: 0 w 10 mies.) |
| W′ z drogi (zdarzenia W′bal = 0) | `wprime_road.py`, `wprime_anchor.py` | działa; od 09.2026 ~18,6–18,8 kJ (zgodne z HIE 18,2) |
| przegląd progu TP | `tp_recheck.py` | uzbrojony (DECISIONS 04.10) |
| strażnicy miernika / obciążenia | `power_meter_guard.py`, `load_guard.py`, `meter_physics.py`, kwarantanna | działają |
| synchronizacja progu na Karoo | `threshold_sync.py` | działa (intervals FTP 239) |
| Xert — benchmark | `xert_daily_bench.py` | działa, ale od 08.2026 **bezużyteczny** (patrz pkt 4) |

### 4. Liczby (średnie miesięczne)
| mies. | TP | HIE kJ | LTP | CTL | Xert TP | ModelQ − Xert |
|---|---|---|---|---|---|---|
| 2025-10 | 264 | 24,7 | 202 | 75 | 259 | +5,6 |
| 2025-12 | 247 | 21,6 | 194 | 50 | 249 | −1,2 |
| 2026-02 | 241 | 21,7 | 186 | 36 | 239 | +1,5 |
| 2026-04 | 248 | 23,2 | 190 | 68 | 247 | +1,5 |
| 2026-06 | 247 | 20,6 | 195 | 70 | 248 | −0,6 |
| 2026-07 | 243 | 18,8 | 196 | 65 | 244 | −1,3 |
| **2026-08** | 249 | 18,2 | 204 | 74 | **287** | −38 |
| **2026-09** | 242 | 18,2 | 197 | 63 | **313** | −71 |
| 2026-10 | 239 | 18,2 | 193 | 58 | **308** | −70 |
Do lipca ModelQ ≈ Xert (z definicji — kotwice i kalibracja wzoru są z Xerta). Od sierpnia Xert „przebił” na danych z wadliwego miernika
(oś AHP29525, miernik/fizyka do 1,37) → Xert nie nadaje się już ani na kotwice, ani na porównanie.

### 5. Historia awarii / zmian (DECISIONS.md, od lipca)
07.07 diagnoza „absurdalnej zmienności” FTP/CP/LTP/W′ → tłumienie i zanik · 19.07 błędna kalibracja miernika (jazda 19.07) ·
26.07 podwójnie liczone roztrenowanie (usunięty człon wieku), ślepa ścieżka przebić · 04.08 LTP wygładzone + kwarantanna miernika ·
11.08 nowy miernik Quarq, kwarantanny, EF wraca; hamulce kotwicy EF; Xert breakthrough +34 W „nie gonimy” · 14.08 XSS z tętna dla kwarantanny ·
25.08 kotwice EF wyłączone + korekta zawyżonego FTP · 28.09 limit dopłaty z gotowości, kwarantanna 3 jazd z lipca · 04.10 próg niepewny 239–256 W ·
07.10 waga z body_measurements · 08.10 usunięta kotwica EF 11.08 (TP 255 → 239), przełom CP z potwierdzeniem · 14.10 VO2max zamrożony.
Wzór: **prawie każda zmiana łata skutek wadliwego miernika albo braku własnego pomiaru możliwości.**

### 6. Wstępna diagnoza (do potwierdzenia w Etapie 2)
1. **ModelQ nie ma własnego pomiaru możliwości.** Sygnatura to stan Xerta z 20.06 przesuwany wzorem za obciążeniem. Xert od sierpnia jest skażony,
   więc nowych kotwic z niego nie będzie — model „jedzie na czerwcu”.
2. **TP jest mechaniczną funkcją objętości (CTL).** Mniej jeździsz → TP spada o 0,66 W na punkt CTL, niezależnie od realnej mocy na progu.
3. **HIE od 2 miesięcy siedzi na ograniczniku** (−20 % od kotwicy). Wartość wyznacza bezpiecznik, nie dane. (W′ z drogi przypadkiem się zgadza — 18,6.)
4. **Jedyna droga „w górę” (przełom CP) od 08.10 nie zadziałała ani razu** — na 136 jazdach żadna moc 2–20 min nie przekroczyła krzywej modelu.
   To znaczy: model NIE jest zaniżony względem tego, co realnie pojechałeś; ale bez mocnych wysiłków nie da się stwierdzić, czy jest trafny.
5. **Dane wejściowe są niepewne**: 3 mierniki w roku, wady w lipcu–sierpniu, mokre podłoże zawyża „miernik/fizyka” do 1,2–1,3 nawet na sprawnym mierniku.
6. **Narosło wiele nakładających się mechanizmów** (EF, przełom, W′ z drogi, przegląd TP, kilku strażników) — każdy dodany pod konkretny objaw.

**Korekta mojej wcześniejszej wypowiedzi (14.10):** „mechanizm w górę jest wyłączony” — nieprecyzyjne. Wyłączona jest kotwica EF;
przełom CP z krzywej moc-czas działa od 08.10 (0 przełomów).

## Etap 2 — diagnoza na liczbach (2026-10-14)

**Uzupełnienie do pkt 4/6.1 (rozmowa z Michałem):** Xert do lipca był wiarygodny (lata na jego jazdach, dobrze oceniany algorytm);
od 08.07 ModelQ liczy WŁASNYM algorytmem z zamrożonych kotwic — celowo, żeby nie zależeć od żywego Xerta. To zadziałało:
sierpniowe skażenie Xerta (dane z wadliwego miernika, nie wada algorytmu) nie przeszło do ModelQ. Luka nie jest w odcięciu,
tylko w tym, że własny algorytm **przesuwa** wartości za obciążeniem, ale **nie uczy się nowych kotwic** z jazd.

### A. Czy w jazdach są wysiłki, z których da się mierzyć? — praktycznie NIE
Krzywa modelu P(d) = TP + HIE/d porównana z najlepszą mocą jazdy 2/5/10/20 min (training_sessions.mmp_*), 06.2025–10.2026:
| miernik | jazd | ≥ 95 % krzywej | ≥ 90 % | ≥ 85 % | maks. | mediana |
|---|---|---|---|---|---|---|
| sprawny / bez oceny | 266 | **0** | 4 | 11 | 0,94 | 0,66 |
| podejrzany (kwarantanna lub miernik/fizyka > 1,15) | 17 | 6 | 7 | 8 | 1,23 | 0,84 |
Najbliżej na sprawnym mierniku: 27.12.2025 (10 min 93 %), 20.06.2026 (10 min 92 %), 06.07 (5 min 91 %), 05.06 (2 min 94 %).
Wszystkie wysiłki „ponad krzywą” = Sycylia/Opolskie 08.2026 na wadliwym mierniku (1,20–1,48). Od nowego miernika (23.08): nic ≥ 88 %.
**Wniosek:** nie jeździsz maksymalnie 2–20 min. Każda metoda „kotwica z najlepszych mocy” (przełom CP, harvest MMP z planu lipcowego)
u Ciebie prawie nigdy nie zadziała — nie z powodu błędu, tylko braku takich wysiłków.

### B. Sprzeczność: W′bal schodzi do 0 bez wysiłków maksymalnych
Od nowego miernika W′bal (MQ2) zszedł do ≤ 2 % na 4 jazdach: 30.08 Włocławek (5,8 h, 0 %), 19.09 Marki (1,6 h, 2 %),
27.09 Żabia Wola (4,6 h, 1 %), 11.10 Brańszczyk (3,7 h, 0 %) — choć żadna nie miała mocy 2–20 min ≥ 88 % krzywej.
Model mówi „byłeś wyczerpany” (seria zrywów, niepełna regeneracja). **To jedyny realny test modelu, jaki mamy:**
jeśli w tych chwilach NIE czułeś końca sił → HIE (i/lub TP, i/lub tempo regeneracji) jest za nisko; jeśli czułeś → model trafny.
Rozstrzyga odczucie Michała (pytanie otwarte).

### C. Ograniczniki decydują zamiast danych
- HIE = 18,16 kJ (dolna granica −20 % od kotwicy 20.06) **przez 92 dni z rzędu** (od połowy lipca, w tym cały sierpień z wyjazdami).
- TP = czysta funkcja CTL (251 + 0,66 × ΔCTL); w granicach (225–281 W), bez ogranicznika — ale bez żadnej informacji o realnym progu.
- W′ z drogi (zdarzenia W′bal = 0) daje 18,6–18,8 kJ — to NIE jest niezależne potwierdzenie: liczy się z tego samego modelu
  W′bal, który ma HIE na ograniczniku (błędne koło).

### Podsumowanie diagnozy
1. Model od czerwca nie dostał żadnej nowej informacji o Twoich możliwościach i przy Twoim stylu jazdy (bez maksów 2–20 min)
   **nie ma z czego jej dostać** obecnymi metodami.
2. Wartość W′/HIE od 3 miesięcy wyznacza bezpiecznik, a jedyny „pomiar” W′ zależy od tego samego bezpiecznika.
3. Jedyny dostępny sprawdzian = Twoje odczucie przy W′bal ≈ 0 (pkt B).

## Naprawa Xerta (2026-10-14) — WYKONANA (decyzje Michala, Claude przez Chrome)
- Bagaz: Toskania ~16-18 kg (nie 10), Opolskie ~13,5 kg (nie 6) => czerwiec CZYSTY (miernik/fizyka ~1,00-1,02), kotwica 20.06 OK.
- Wycinanie jazd odrzucone (Xert zrobilby roztrenowanie). Uzyte: flaga Xerta „Flag the breakthrough changes as invalid”
  (jazda i obciazenie zostaja, nie zmienia sygnatury). Oznaczanie pojedynczo = „kret” (kolejne falszywe przelomy) =>
  oznaczone WSZYSTKIE 25 jazd 01.07-20.08.2026 (zweryfikowane API: flag=True x25).
- Pelny reset progresji (Profile Settings > Reset/Recalculate Entire Progression) ze startem Xerta 01.01.2020 jak dotad:
  TP 250 / HIE 21,0 / PP 1100 (z modelq2_xert_bench), obciazenie Auto-Calc. Formularz domyslnie podstawial DZISIEJSZA sygnature — pulapka.
- Zanik sygnatury: Optimal-Default -> **None - Training Load Matched** (bez maksow Optimal „roztrenowywal” do 223 W).
- Wynik (14.10): przelomy tylko 05.06, 06.06, 16.06 (-1), 20.06. Sygnatura Xert: **TP 231 W, HIE 24,2 kJ, PP 1092 W, LTP 171 W**.
  ModelQ: TP 239, HIE 18,2 (ogranicznik), LTP 193. => **TP zgodne (8 W)**; **HIE ModelQ wyraznie za nisko** (zgodne z odczuciem
  Michala przy W'bal=0: „trudno, nie odcielo, ale niedaleko”).
- Zostaje: XSS jazd z 07-08.2026 zawyzony (moc x1,07-1,48) — przy Training Load Matched moze lekko podnosic sygnature.
  Opcja na pozniej: podmiana plikow na skorygowane (/opt/qbot/artifacts/xert_korekta_2026.csv).
- Skrypty (tylko odczyt Xert API): /opt/qbot/artifacts/xert_list_jul_aug.py, xert_breakthroughs.py, xert_flags.py.

## Etap 3 — WDROZONE (2026-10-14)
1. Kotwica wlasna 14.10: TP 238,8 / HIE 20,0 / PP 988,8 (HIE z replay 4 jazd W'bal=0 + odczucie; bez wartosci z Xerta).
2. Czulosc HIE na TL_high 0,11 (z rocznych danych, fizjologia: pojemnosc beztlenowa zmienia sie wolno), granice +-10 %.
   Kontrola 4 jazd: 6,0 / 8,7 / 9,4 / 6,8 % (cel 5-15 %). Szczegoly: DECISIONS 2026-10-14.
3. Regula TP 0,45 W/CTL z CTL sprzed 14 dni (dane roczne r2 0,85; test vs Xert >90 dni MAE 7,9 -> 3,6 W).
   Skutek uboczny: LTHR 151 -> 148 i strefy HR w intervals.icu (krok lthr/lthr_sync). DECISIONS 2026-10-14.
4. Pytanie o odczucie (fitmodel/wbal_feel.py, od jazd 15.10.2026): jazda z min W'bal <= 5 % -> Telegram "Odcielo / Blisko /
   Mialem zapas" (wf:cut|close|ok:<id>, tabela qbot_v2.wbal_feel). Krok wbal_feel w daily_job. Nic nie zmienia w ModelQ;
   3x z rzedu "mialem zapas" (90 dni) -> notka o propozycji korekty HIE, decyzja Michala. Testy test_wbal_feel 4.
Pozostale punkty planu (TODO): pytanie po jezdzie z W'bal <= 5 % (Odcielo/Blisko/Zapas), miesieczny sprawdzian vs Xert
(propozycja kotwicy tylko za zgoda), bezpieczniki tygodniowe, usuniecie kotwicy EF z kodu, masy bagazu w meter_physics,
jeden dokument ModelQ; regula TP (0,66 W/CTL) do przegladu tym samym tokiem (fizjologia -> dane -> test).

## Etap 3 — plan naprawy do decyzji (TODO)
Warianty do opracowania: (1) naprawa Xerta u źródła (usunięcie/korekta jazd z wadliwego miernika 07–08.2026) i nowa kotwica z Xerta;
(2) krótki sprawdzian mocy co 6–8 tyg. (nie „test do trupa”, np. 2 × 8 min); (3) kotwica z odczucia: pytanie po jeździe,
gdy W′bal ≈ 0 („czułeś koniec / miałeś zapas”); (4) połączenia. Wymaga odpowiedzi Michała na pkt B.
