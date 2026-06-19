# ModelQ — pełna dokumentacja

**Model formy, metabolizmu i zarządzania treningiem dla QBota.**
Status: **wdrożony i żywy na prodzie** (E0–E9 + B1–B2 + T1–T2), w dziennym cronie i na endpoincie.
Data dokumentu: 2026-06-19. Spec źródłowy: `FITMODEL_SPEC.md` v2.0, taski: `FITMODEL_CLI_TASKS.md`.

> **Nazewnictwo.** Od 2026-06-19 model nazywamy **ModelQ**. To nazwa produktowa/koncepcyjna.
> Implementacja w kodzie i bazie pozostaje pod historycznym id `fitmodel` (pakiet `fitmodel/`,
> tabele `qbot_v2.fitmodel_*`, endpoint `/fitmodel/...`). Zmiana nazw w kodzie/DB to osobny,
> ryzykowny refactor (cron, endpoint, importy, migracja tabel) — NIE wykonany. Mapa nazw niżej (§13).

---

## 1. Filozofia i cel

ModelQ zastępuje Xert własnym, **submaksymalnym** modelem formy pod luźną jazdę gravelem.

- **FTP jako wyznacznik bezpiecznego pacingu**, nie cel treningowy. Zero wysiłków do trupa.
- **Niezależność od Xerta** — kotwica FTP liczona z własnych danych. Xert = wyłącznie linia benchmarku (gdy licencja wygaśnie, model stoi sam).
- **Cierpliwe strojenie, nie czułe** — sygnał jest celowo wolny (mediana 28 dni + tłumienie 50%). Lepiej spóźnić wykrycie trendu o tydzień niż złapać fałszywy skok.
- **Realistyczny rozwój** = więcej objętości + durability, nie bloki interwałowe.
- **Odporność warstwowa** — awaria wyższej warstwy nie blokuje rdzenia.
- Dokładność celowa: **±5–8 W na FTP**, ±20–30% na glikogenie. Świadomie akceptowana.

Wycięte świadomie: CP/W' z mean-max (wymaga maksów), strukturalne plany treningowe, bezwzględny skład ciała (tylko trendowo), optymalizacja pod szczyt formy.

---

## 2. Architektura

```
RDZEŃ                  EF → FTP_est | durability | decoupling
  ↑ moc + HR, segmenty steady-state

KONTEKST / WAŻENIE     readiness gate (sen/HRV) → czy jazda wchodzi do FTP
                       waga + skład ciała (Garmin) → W/kg

GLIKOGEN               bilans zbiornika (CHO in/out) → stan %

NAWIERZCHNIA           surface multiplier (OSM) → koszt fizjologiczny

── NADBUDOWA TRENINGOWA ──────────────────────────────────────
WIADRA (3 systemy)     tlenowe / progowe / neuro ← strain per jazda
ZARZĄDZANIE            tryb × budżet czasu × focus → targety wiader → endpoint QExt2
```

---

## 3. Źródła danych

| Strumień | Źródło | Dostęp |
|---|---|---|
| Moc, HR, prędkość, kadencja, nachylenie, GPS (1 Hz) | FIT z Karoo (Hammerhead) | `/opt/qbot/app/outgoing/michal/hammerhead_originals/` |
| Nocne HRV, sen, RHR | Garmin Connect (Fenix) | tabele wellness (`qbot_wellness_daily` itd.) |
| Waga + skład ciała | Garmin Connect | `body_*` / `fitmodel_daily.weight_kg` |
| Spożycie CHO | QBot nutrition log (LLM) | `qbot_v2` |
| Typ nawierzchni per segment | OSM (Overpass around:20m) | klasyfikator `scripts/lib/surface_classifier.py` + cache `data/fitmodel_surface_cache.json` |
| Temperatura jazdy | FIT / Open-Meteo | normalizacja EF |
| TP Xerta (benchmark) | `qbot_v2.xert_profile_snapshots.ftp_power_w` | dane Xerta już w QBocie |
| Czas w siodle / TSS | `qbot_v2.training_sessions` | budżet czasu (T1) |
| Profile tras / nawierzchnia tras | `route_parse_results`, `route_surface_profiles`, `route_surface_segments` | auto-focus Stan A (T2) |

---

## 4. Komponenty (pakiet `fitmodel/`)

| Plik | Etap | Co robi |
|---|---|---|
| `fit_ingest.py` | E1–E2 | Czyta FIT (1 Hz), segmentuje steady-state, filtr jakości HR, EF_norm → `fitmodel_segment`. Załatany na fallback `psycopg2→psycopg`. |
| `ftp_resolver.py` | E3–E4 | Kotwica data-derived, FTP_est = anchor × (EF_med28/EF_anchor) z tłumieniem; readiness gate; job tygodniowy → `fitmodel_daily`. |
| `glycogen.py` | E5 | Dzienny bilans glikogenu (CHO in/out z mocy), resety, limit resyntezy → `fitmodel_daily`. |
| `surface_tag.py` | E6 | Tag nawierzchni per segment (GPS z FIT → Overpass → słownik) + kalibracja `mult=EF_asfalt/EF_typ` z bramką n≥10. |
| `buckets.py` | B1 | Czysta funkcja: strumień mocy + FTP → (low/high/peak/d_strain). strain=i⁴·(100/3600). |
| `ride_buckets.py` | B2 | Uruchamia B1 na historii → `fitmodel_ride_buckets`. |
| `xert_bench.py` | E7 | Tygodniowy log (ftp_est, xert_tp, delta) → `fitmodel_xert_bench`. |
| `week_planner.py` | T1 | Plan tygodnia: budżet czasu × tryb × focus → `fitmodel_week_plan`. Tryb = propozycja do zatwierdzenia. |
| `focus.py` | T2 | Auto-focus: Stan A (profil trasy) / Stan B (deficyt → najsłabsze wiadro). |
| `api.py` | E8/B3 | Payload endpointu QExt2 (`build_active_payload`). |
| `brief.py` | E9 | Modularne sekcje do raportu (dobowa + tygodniowa). |
| `daily_job.py` | — | Orkiestrator dziennego pipeline'u (odporność warstwowa). |

---

## 5. Schemat DB (`qbot_v2`, 7 tabel)

```sql
fitmodel_segment ( id, ride_id, started_at, dur_s, np_w, hr_avg, cadence_avg,
  temp_c, surface_type, ef_raw, ef_norm, hr_quality_ok, readiness_weight, created_at )

fitmodel_daily ( day PK, ftp_est_w, ef_med_28d, weight_kg, w_per_kg,
  glycogen_pct, glycogen_g, sleep_h, hrv_night, rhr, notes )

fitmodel_xert_bench ( week PK, ftp_est_w, xert_tp_w, delta_w, xert_breakthrough, note )

fitmodel_surface_cal ( surface_type PK, mult, n_segments, updated_at )

fitmodel_param ( key PK, value, updated_at, source )

fitmodel_ride_buckets ( ride_id PK, started_at, low_strain, high_strain, peak_strain,
  d_strain, total_strain, ride_mode, ftp_used_w, created_at )      -- B2

fitmodel_week_plan ( week PK, mode, time_budget_h, focus_source,
  target_low, target_high, target_peak, feasible, note, created_at ) -- T1
```

**Parametry (`fitmodel_param`, stan 2026-06-19):** `ftp_anchor_w=245` (zamrożona), `ef_anchor=1.600`, `ftp_damping_factor=0.50`, `ef_window_days=28`, `hr_max_bpm=184`, `k_temp=0.004`, `t_ref_c=20.0`, `glycogen_capacity_g_per_kg=9.0` (samoskalibrowane z 8), `glycogen_drain_base_g_day=110.0`, `cho_absorption_factor=0.85`. `kj_gate=1500` — NIE w param, stała w silniku.

---

## 6. Formuły rdzenia

**Segmentacja (4.1):** czas ≥600 s, po ≥1200 s od startu, CV(P)≤0,10, HR 0,65–0,85·HRmax (przy hrmax=184 → ~120–156 bpm). Filtr jakości HR: cadence lock (|HR−kadencja|<3 przez >30 s), skok HR>15 bpm bez zmiany mocy, płaskość σ<1 przez >60 s.

**Efficiency Factor (4.2):**
```
EF_raw  = NP_segment / HR_avg
EF_norm = EF_raw × (1 + k_temp·(T_ref − T_ride)) × surface_mult     # k_temp=0.004, T_ref=20°C
Sygnał  = mediana krocząca EF_norm z 28 dni
```

**FTP_est (4.3):**
```
FTP_anchor = robust z najlepszych podtrzymywanych wysiłków (≥40 min NP) lub best-20min×0.95
             — tylko hr_quality_ok, spoza zmęczenia; ZAMROŻONA na t0 (=245 W)
FTP_est(t) = FTP_anchor × (EF_med28(t) / EF_anchor)
zmiana_tyg = clip(±0.5·Δ)   # tłumienie 50%, anti-jitter
```
Rewalidacja kotwicy co ~3–4 mies. Aktualizacja: job tygodniowy (teraz codziennie w cronie).

**Glikogen (4.6):**
```
pojemność ≈ 9 g/kg (samokalibracja ze zdarzeń bonk)
stan(t) = clip( stan(t−1) + CHO_in·0.85 − CHO_ride − 110, 0, pojemność )
CHO_ride = Σ_sek [ (P/0.23) × cho_fraction(%FTP) / 4 ]
```
Resety po dniu wolnym z CHO>5–6 g/kg; limit resyntezy ≤5–7 g/kg/dobę.

**Multiplier nawierzchni (4.7):** `mult[typ] = EF_asfalt_med / EF_typ_med`, nadpisywany tylko dla typów z n≥10 segmentów; inaczej literatura.

**Readiness gate (4.8):** waga 1.0; sen<6 h lub HRV<baseline → 0.3–0.5; flaga złego samopoczucia → 0.0 (tylko dla FTP).

**Strain / wiadra (5.1–5.3):**
```
i = P/FTP_est;  strain_sec = i⁴ × (100/3600)        # 1h @ FTP = 100
i<0.90 → Low | 0.90≤i<1.20 → High | i≥1.20 → Peak    # praca sekunda-po-sekundzie łapie zrywy
spływ w dół: High→Low, Peak→High+Low (lekko)
durability: dur_mult = 1 + clip((kJ−kj_gate)/kj_gate, 0, 1); D += strain·(dur_mult−1)  # cap ×2
```

**Tryb → total (T1):** regeneracja ×0,65 (zeruje High/Peak), podtrzymanie ×1,0, rozwój ×1,075. Tryb = **propozycja** (HRV gdy jest, inaczej trend obciążenia z poprzedniego pełnego tygodnia), wymaga zatwierdzenia.

**Focus (T2):** Stan A z profilu trasy (dystans→Low, m/km→High, luźna nawierzchnia→Peak) + dryf czasu ku dacie; Stan B = nacisk na najsłabsze wiadro (odwrotność udziałów rolling-load). `focus_source ∈ {route, deficit, manual}`.

---

## 7. Dzienny pipeline (cron 04:45)

`fitmodel/daily_job.py` — orkiestrator z **odpornością warstwową** (try/except per krok, awaria jednego nie blokuje reszty). 7 kroków, w kolejności:

1. **ingest_fit** — nowe FIT → `fitmodel_segment`
2. **ftp_resolver** — FTP_est → `fitmodel_daily`
3. **glycogen** — bilans glikogenu → `fitmodel_daily`
4. **surface_tag** — tag nowych segmentów + kalibracja `fitmodel_surface_cal`
5. **ride_buckets** — nowe jazdy → `fitmodel_ride_buckets`
6. **xert_bench** — benchmark bieżącego tygodnia (UPSERT)
7. **week_planner** — plan tygodnia → `fitmodel_week_plan`

Crontab: `45 4 * * * cd /opt/qbot/app && .venv/bin/python3 -m fitmodel.daily_job >> /opt/qbot/logs/fitmodel_daily.log 2>&1`. Pierwszy bieg ~150 s.

Uruchomienie ręczne: `cd /opt/qbot/app && .venv/bin/python3 -m fitmodel.daily_job`. Pojedyncze moduły mają `--dry-run` (gdzie dotyczy).

---

## 8. Endpoint QExt2

```
GET /fitmodel/buckets/active
→ { ride_mode, block_source, targeting: bool, week, feasible,
    today_targets: { low, high, peak },     # tygodniowy target / 7
    week_fill_pct: { low, high, peak },      # wypełnienie z ride_buckets od poniedziałku
    params: { ftp_w, kj_gate, torque_ref } }
```
`ride_mode=expedition` → `targeting=false` (silnik liczy do historii, pole milczy). Połączenie DB bez root-only env (usługa działa jako `qbot`, lokalny trust). Pole danych na Karoo — **poza zakresem** (implementowane osobno w QExt2).

---

## 9. Integracja: raport + /help

- `fitmodel/brief.py`: `daily_section()` (FTP_est, W/kg, glikogen, sugestia fuelingu) + `weekly_section()` (rozkład wiader vs target, tryb). Modularne, fail-safe. Wpięte w `daily_report.py` (dopina do `_tg`).
- `/help` (`qbot_query_handler.py`): blok **FORMA (FITMODEL)** opisujący, że forma pojawia się w raporcie dobowym.

---

## 10. Stan danych i kalibracji (2026-06-19)

- **Segmenty:** 33, okno 2026-05-02 → 06-16, wszystkie `hr_quality_ok`. Nawierzchnia: asfalt 16, compacted 8, unpaved 4, gravel 4, 1×NULL (brak dróg w OSM).
- **Ride buckets:** 21 jazd (02.05–16.06).
- **FTP_est ≈ 240,4 W**; kotwica 245 W; **W/kg ≈ 2,4**.
- **Benchmark Xert:** tydz. 2026-06-15 → ftp_est 240,4 / xert_tp 244,7 / **delta −4,3 W** (kotwica lekko zaniżona — po bezpiecznej stronie pacingu).
- **Surface_cal:** asphalt 1,00 (n=16, referencja, skalibrowane); compacted 1,04 / gravel 1,07 / unpaved 1,10 / sand 1,15 (literatura, n=0 — czekają na ≥10 seg/typ).

---

## 11. Ograniczenia (uczciwie)

- **HR z nadgarstka = sufit dokładności.** Cały model stoi na `EF=moc/HR`; wrist optical bywa zaszumiony na szutrze (cadence lock) — stąd filtr 4.1. Poprawi to pasek piersiowy (czyste 1 Hz HR), nie kolejne jazdy.
- **Kotwica data-derived bywa zaniżona** (jazda submax) — akceptowalne dla pacingu, kwantyfikowane benchmarkiem (−4,3 W).
- **Wiadro neuro = przybliżenie strefowe** (brak PP/sygnatury). Tlenowe i progowe odtwarzane dobrze, neuro zgrubnie.
- **Kalibracja off-road** czeka na ≥10 segmentów/typ; do tego czasu literatura.
- **Glikogen kumuluje błąd** → resety + samokalibracja.
- **DFA-a1 nieaktywne** — wymaga zapisu RR (patrz §12). Działa tylko w przód.
- **torque_ref niepoliczony** (§5.4 spec) — endpoint zwraca null.
- **Tryb bez HRV** — `hrv_night` pusty (brak zapisu RR), tryb leci z trendu obciążenia.
- **Auto-focus Stan A** wymaga eventu z trasą GPX; kalendarz nie ma linku event↔trasa i 0 przyszłych eventów → domyślnie Stan B.

---

## 12. Tętno / pasek / DFA-a1

- **Teraz:** HR z nadgarstka (zegarek). FIT z Karoo zapisuje tylko 1 Hz `heart_rate` — **zero `hrv`/RR**.
- **Pasek Michała:** Hammerhead HRM **1.0** (ACC-SNR-HR-1.0) — RR/HRV dodano dopiero w 2.0, więc **1.0 RR nie nadaje**. Daje za to czyste tętno EKG (walidacja dryfu nadgarstka).
- **DFA-a1 (LT1, kontrola krzyżowa FTP)** potrzebuje RR beat-to-beat. Łańcuch: (1) pasek nadający RR (HH 2.0 / Polar H10 / Garmin HRM-Pro), (2) urządzenie zapisujące RR do FIT (`hrv`). Karoo — niepotwierdzone, czy utrwala RR.
- **Plan:** Michał testuje HH 2.0; pierwsza jazda → sprawdzić `get_messages("hrv")` w FIT. Brak RR → zwrot. Szczegóły w pamięci konta (`qbot-fitmodel-chest-strap-validation`).

---

## 13. Mapa nazw (ModelQ ↔ implementacja)

| Warstwa | Nazwa produktowa | Identyfikator w kodzie/DB |
|---|---|---|
| Model | **ModelQ** | `fitmodel` (pakiet, prefiks) |
| Pakiet kodu | ModelQ | `/opt/qbot/app/fitmodel/` |
| Tabele | ModelQ | `qbot_v2.fitmodel_*` (7 tabel) |
| Endpoint | ModelQ | `GET /fitmodel/buckets/active` |
| Cron / log | ModelQ daily | `fitmodel.daily_job`, `logs/fitmodel_daily.log` |

Zmiana identyfikatorów `fitmodel*` → `modelq*` to osobny refactor (migracja tabel, podmiana importów, route, crona, restart usługi) — **nie wykonany**, do decyzji.

---

## 14. Roadmapa / otwarte

- **HRV/RR z paska** → odblokowuje DFA-a1 + tryb liczony z HRV. Najpilniejsze (działa tylko w przód).
- **Kalibracja nawierzchni off-road** → automatycznie, gdy uzbiera się ≥10 seg/typ.
- **torque_ref** → percentyl rozkładu moc/kadencja (§5.4), do policzenia okresowo.
- **Link event↔trasa w kalendarzu** → odblokowuje auto-focus Stan A (rozkład pod nadchodzącą wyprawę).
- **Pole QExt2 na Karoo** → konsumpcja endpointu (po stronie QExt2, Michał).
- **Ewentualny rename** `fitmodel*` → `modelq*` w kodzie/DB.

---

## 15. Operacje

- **Repo:** `QbotMS/QbotQ`, pakiet `fitmodel/`. Commity ModelQ na `main`: `ee32e80` (E6/E7/B1/B2+cron), `bea6ab2` (T1), `5d4d5d8` (T2), `e71393c` (E8), `1900de4` (E9).
- **Serwer:** `olga181.mikrus.xyz`, venv `/opt/qbot/app/.venv`, usługa `qbot-api` (8002), DB `qbot_v2`.
- **Backupy** edytowanych plików: `*.py.bak.<ts>` w katalogach (gitignored).
- **Smoke:** `curl localhost:8002/fitmodel/buckets/active`; `python3 -m fitmodel.brief`; `python3 -m fitmodel.week_planner`.
- **Po zmianie kodu serwera:** `systemctl restart qbot-api` + smoke; commit wymaga zgody.
