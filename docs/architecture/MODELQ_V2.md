# ModelQ v2 (MQ2) -- dokumentacja architektury

**Status:** produkcja od 2026-07-08 (jedyne zrodlo prawdy dla `fitmodel_daily`).
**Zastepuje:** ModelQ v1 (`cp_v3` / `cp_wprime` / `training_load` / EF-anchored `ftp_est`) -- wycofany do `archive/modelq_v1/`.
**Pakiet:** `fitmodel/modelq2/` (zero dziedziczenia po v1).

---

## 1. Po co i czym rozni sie od v1

ModelQ v1 systematycznie **zawyzal** dwie kluczowe wielkosci:
- prog: `ftp_est_w` ~251-257 W wobec realnego progu ~240-245 W (potwierdzone Xertem i krzywymi MMP),
- forme: `ctl_xss` przeszacowany o ~16 pkt (81 zamiast ~65).

MQ2 liczy pelna **sygnature fizjologiczna** (TP/HIE/PP/LTP) dryfujaca w czasie wokol
kilku **zamrozonych kotwic**, oraz forme (CTL/ATL/TSB) z jednego, spojnego strumienia
XSS. Model jest **samodzielny**: nie czyta zadnych kolumn v1 ani zywego Xerta -- Xert
sluzyl wylacznie do wyznaczenia i walidacji kotwic (potem zamrozonych).

Cel projektowy: pelne decoupling od Xerta przy zachowaniu jego trafnosci (mediana bledu
TP ~2-4 W na biezacym oknie).

---

## 2. Architektura -- 6 filarow

| Filar | Modul | Rola |
|------|-------|------|
| 0 -- Sygnatura | `signature.py` | Dataclass `Signature` (TP, HIE_kJ, PP, LTP); `from_kj`, `LTP = TP - HIE/400` |
| 1 -- MPA / W'bal | `mpa.py` | W'bal (Skiba) + MPA (Maximal Power Available) na progu MQ2 |
| 2 -- Przebicia | `breakthrough.py` | Grupowanie zdarzen wyczerpania W' z filtrami szumu |
| 3+6 -- Zanik / forma sygnatury | `decay.py` | Dryf TP/HIE/PP/LTP w czasie wokol kotwic (DecayAnchor) |
| 4 -- XSS | `xss.py` | Strain per jazda w koszykach Low/High/Peak |
| 5 -- Obciazenie | `training_load.py` | CTL/ATL/TSB jako 3x EWMA ze strumienia XSS |

Pozostale: `io.py` (odczyt `activity_record`), `progression.py` (budowa i zapis szeregu
sygnatur -> `modelq2_signature`), `publish.py` (adapter -> `fitmodel_daily`).

---

## 3. Sygnatura i kotwice

**Sygnatura** to czworka wielkosci na dany dzien:
- **TP** (Threshold Power) -- prog, odpowiednik FTP/CP,
- **HIE** (High Intensity Energy, kJ) -- pojemnosc beztlenowa, odpowiednik W',
- **PP** (Peak Power) -- moc szczytowa,
- **LTP** (Lower Threshold Power) = `TP - HIE/400`.

Sygnatura nie jest liczona od zera kazdego dnia -- **dryfuje** wokol **kotwic**
(zamrozone punkty kalibracyjne wyznaczone historycznie z Xerta i krzywych MMP).
Tabela: `qbot_v2.modelq2_anchor` (`day, tp_w, hie_kj, pp_w, ctl_anchor`).

**5 kotwic (stan 2026-07):**

| Dzien | TP | HIE kJ | PP | CTL_anchor | rola |
|-------|----|--------|----|-----------|------|
| 2025-12-27 | 244 | 20.6 | 1002 | 44 | zima |
| 2026-02-22 | 239 | 20.2 | 986 | 32.6 | luka zima-wiosna (marzec) |
| 2026-03-29 | 245 | 22.5 | 1030 | 61.8 | wiosna |
| 2026-05-16 | 245 | 21.3 | 1006 | 59.6 | luka wiosna-lato (maj) |
| 2026-06-20 | 251 | 22.7 | 1009 | 76.1 | lato |

Kazdy dzien bierze **najblizsza czasowo** kotwice. Kotwice 02-22 i 05-16 dodano, bo
dni w formie wiosennej/letniej-przejsciowej braly odlegla kotwice o innym CTL i dryf
TP odjezdzal o ~10 W. Skrypt zasiewajacy: `scripts/mq2_seed_anchors.py`.

> Rekalibracja: gdy forma trwale odjedzie od kotwic, dokladamy nowa kotwice
> (z przebicia lub Xerta). To rzadka, swiadoma operacja -- nie automat.

---

## 4. Dryf sygnatury (`decay.py`)

Kazda wielkosc dryfuje inaczej wzgledem kotwicy:

**TP -- dryf za wlasnym CTL** (nie za czasem):
```
tp(day) = tp_anchor - TP_DECAY_W_PER_DAY * (day - anchor_day)
                    + TP_K_DRIFT * (ctl(day) - ctl_anchor)
TP_DECAY_W_PER_DAY = 0.15     # powolny zanik bazowy
TP_K_DRIFT         = 0.66     # reakcja na zmiane formy (CTL z XSS)
```
gdzie `ctl(day) = tl_low + tl_high + tl_peak` z filaru obciazenia. To ta sama mechanika
co dawny `cp_v3`, ale karmiona **wlasnym** CTL MQ2, nie ctl_xss v1.

**HIE -- dryf za koszykiem High** (+/-20%): rosnie po twardych interwalach, opada w ich
braku. **PP -- dryf za HIE** (`pp_drift = 1 + PP_K*(hie_ratio-1)`, `PP_K=0.10`, miekki
bezpiecznik 0.93-1.07). **LTP** -- pochodna: `TP - HIE/400`.

Dni bez jazdy: XSS=0, sygnatura dryfuje (zanik). Szereg rozciagany do **dzis**.

---

## 5. Forma -- CTL/ATL/TSB (`training_load.py`)

Jeden strumien XSS -> trzy wykladnicze srednie kroczace:
```
CTL = EWMA(XSS, tau=42 dni)      # przewlekle obciazenie ("fitness")
ATL = EWMA(XSS, tau=7 dni)       # ostre obciazenie ("fatigue")
TSB = CTL - ATL                  # bilans ("forma")
```
CTL to suma trzech koszykow (`tl_low + tl_high + tl_peak`). Ta sama liczba zasila dryf TP
(sekcja 4) -- forma i prog sa spojne.

---

## 6. XSS -- strain per jazda (`xss.py`)

XSS (eXertion Strain Score) w trzech koszykach wg intensywnosci wzgledem progu:
- **Low** (#4ADE80), **High** (#FACC15), **Peak** (#FF5252).

Formula bazowa (kotwiczona: 1h @ prog = 100):
```
strain_rate = (power / CP_eff) * (1 + beta*fatigue) * (100/3600) * dt,  beta = 1.0
```
Po cutoverze XSS jest liczony na **progu MQ2** (nizszy niz zawyzony v1 -> XSS realnie
wyzszy). Tabela per jazda: `qbot_v2.modelq2_ride`.

---

## 7. Cutover i adapter (`publish.py`)

MQ2 nie zmienil konsumentow -- **adapter** zapisuje wynik MQ2 w te same kolumny
`fitmodel_daily`, ktore czytaja web, raporty W1 i Karoo (przez `qbot_api`).

`publish.py`:
- `ingest_new_rides_xss(conn)` -- XSS nowych jazd z **sygnatury MQ2 sprzed jazdy**
  (kauzalnie -- Xert jest odciety),
- `publish_to_daily(conn)` -- MQ2 -> `fitmodel_daily`,
- `run_daily_v2(conn)` -- XSS nowych -> `build_and_store` -> publish. Wpiety w `daily_job` jako krok `modelq2_v2`.

**Mapowanie kolumn (adapter):**

| fitmodel_daily | <- MQ2 | uwaga |
|----------------|--------|-------|
| `ftp_est_w` | TP | prog; Karoo `ftp_watts` |
| `cp_modelq_w` | TP | historycznie ~prog (nie LTP) |
| `ltp_modelq_w` | LTP | Karoo `ltp_watts` |
| `wprime_modelq_kj` | HIE | Karoo `wprime_kj` |
| `pp_modelq_w` | PP | |
| `ctl_xss` | CTL | |
| `atl_raw`, `atl_plus` | ATL | korekta readiness pominieta |
| `tsb_raw`, `tsb_plus` | TSB | |

Swiadome skoki wartosci przy cutoverze: FTP na Karoo 251 -> ~242, forma CTL 81 -> ~65.

---

## 8. Tabele

| Tabela | Zawartosc |
|--------|-----------|
| `modelq2_anchor` | 5 zamrozonych kotwic (day, tp_w, hie_kj, pp_w, ctl_anchor) |
| `modelq2_signature` | sygnatura per dzien (tp/hie/pp/ltp/ctl/atl/tsb/tl_low/tl_high/tl_peak) |
| `modelq2_ride` | XSS per jazda (Low/High/Peak) |
| `modelq2_xert_bench` | benchmark Xerta (walidacja, tylko referencja) |
| `fitmodel_wbal_ride` | W'bal/XSS per jazda (przeliczone na progu MQ2) |

---

## 9. Pliki

```
fitmodel/modelq2/
  signature.py      Filar 0
  mpa.py            Filar 1
  breakthrough.py   Filar 2
  decay.py          Filar 3+6 (dryf + kotwice)
  xss.py            Filar 4
  training_load.py  Filar 5
  io.py             odczyt activity_record
  progression.py    budowa + zapis szeregu sygnatur
  publish.py        adapter -> fitmodel_daily (cutover)
scripts/
  mq2_seed_anchors.py   zasiew 5 kotwic
  mq2_backfill.py       przeliczenie historyczne
```

Pipeline: `fitmodel/daily_job.py` -> krok `modelq2_v2` (`run_daily_v2`). Kroki wspolne
(niezalezne od modelu): ingest, readiness, wbal_replay, glycogen, surface_tag,
ride_buckets, xert_bench, week_planner.

---

## 10. Walidacja (biezace okno vs Xert)

- TP: mediana ~2 W, max ~10 W
- HIE: ~1.5 kJ
- PP: ~7 W (avg 1011 vs Xert 1012, sd 15.6 vs ~15, 0% na podlodze)
- LTP: ~1 W

Historia sprzed pierwszej kotwicy (2025) do ~32 W bledu -- ignorowana zgodnie z zasada
"liczy sie biezace okno".

---

## 11. Rollback

Model v2 jest domyslny i jedyny w `daily_job` (flaga `QBOT_MODELQ` usunieta).
Awaryjny powrot do v1:

1. **Kod:** `git mv archive/modelq_v1/*.py fitmodel/`, przywroc gowetke silnikow v1
   w `daily_job.py` i flage (patrz `archive/modelq_v1/README.md` + historia git).
2. **Dane:** odtworz z backupow `qbot_v2.fitmodel_daily_v1_backup` (1590 wierszy) oraz
   `qbot_v2.fitmodel_wbal_ride_v1_backup` (330).

`ftp_resolver.py` pozostaje w `fitmodel/` (zawiera `_db_connect` uzywany globalnie);
jego `run_weekly_job` (FTP v1) jest martwym kodem.
