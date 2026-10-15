# ModelQ — jak działa (stan na 2026-10-15)

Jeden dokument „jak jest teraz”. Historia zmian i diagnoza: `docs/MODELQ_PRZEGLAD.md`; uzasadnienia decyzji: `docs/DECISIONS.md`
(wpisy 2026-10-14). Gdy dokument rozjeżdża się z kodem — wygrywa kod, a dokument trzeba poprawić.

## 1. Co ModelQ podaje (fitmodel_daily, publikacja `fitmodel/modelq2/publish.py`)
| pole | znaczenie |
|---|---|
| `cp_modelq_w` = `ftp_est_w` | **TP** — próg (nazwa „cp” historyczna, to nie CP z krzywej moc-czas). Idzie na Karoo (`threshold_sync` → intervals.icu) |
| `wprime_modelq_kj` | **HIE** — zapas na mocne wysiłki (odpowiednik W′); W′bal na Karoo i w raportach |
| `pp_modelq_w` | **PP** — moc szczytowa |
| `ltp_modelq_w` | **LTP** = wygładzone (EMA 28 d) TP − HIE/400 |
| `ctl_xss`, `atl_*`, `tsb_*` | forma / zmęczenie / świeżość z XSS ModelQ (kanon świeżości: wersja „po korekcie”) |
Dane per jazda: `qbot_v2.modelq2_ride` (XSS low/high/peak/total, min W′bal, sygnatura użyta do jazdy). Sygnatura dzienna: `qbot_v2.modelq2_signature`.
**Konsumenci:** Karoo/QExt2, Trener, raporty jazd i tras, Forma/web, Albert, W′bal, glikogen, LTHR/HRR, dryf/upał, VO₂max (zamrożony).

## 2. Skąd biorą się wartości
**Kotwice** (`qbot_v2.modelq2_anchor`) — punkty, w których sygnatura jest znana:
| dzień | TP | HIE | PP | źródło |
|---|---|---|---|---|
| 27.12.2025, 22.02, 29.03, 16.05, 20.06.2026 | 239–251 W | 20,2–22,7 kJ | ~1000 W | przepisane z Xerta (zamrożone 08.07.2026, Xert wtedy wiarygodny) |
| **14.10.2026** | **238,8** | **20,0** | **988,8** | **własna**: TP/PP z ModelQ, HIE z jazd z W′bal≈0 i odczucia Michała |
**Dzień między kotwicami** (`fitmodel/modelq2/decay.py`, najbliższa kotwica):
- **TP** = TP_kotwicy + **0,45 W × (CTL sprzed 14 dni − CTL kotwicy sprzed 14 dni)**, granice −10 % / +12 %.
  Fizjologia: próg adaptuje się do obciążenia z opóźnieniem i umiarkowanie. Dane roczne: r² 0,85 przy opóźnieniu 14 dni.
- **HIE** = HIE_kotwicy × (TL_high dnia / TL_high kotwicy)^**0,11**, granice ±10 %.
  Fizjologia: pojemność beztlenowa zmienia się wolno i mało zależy od bieżącej ilości mocnej jazdy (dane roczne: TL_high ×4,3 → HIE ×1,17).
- **PP** idzie za HIE w 10 % amplitudy (`PP_K`).
**Zasada:** fizjologia mówi co i jak szybko może się zmieniać, dane Michała ustawiają poziom. Bez dopasowywania parametrów do kilku jazd.

## 3. Skąd ModelQ dostaje nowe informacje
| mechanizm | plik | co robi |
|---|---|---|
| odczucie przy niskim zapasie | `fitmodel/wbal_feel.py` | jazda z min W′bal ≤ 5 % → Telegram „Odcięło / Blisko / Miałem zapas”; 3× „zapas” → propozycja korekty HIE (decyzja Michała) |
| przełom CP | `fitmodel/cp_breakthrough.py` | moc 2/5/10/20 min ponad krzywą modelu → pytanie na Telegramie (rzadkie: Michał nie jeździ maksów) |
| nowa kotwica | skrypt jak `scripts/mq2_add_anchor_20261014.py` | ręcznie, po decyzji; kopie `bak_*` przed zmianą |
Usunięte: kotwica EF (moc/tętno) — wrażliwa na wadliwy miernik, wyłączona 25.08, kod usunięty 14.10.

## 4. Strażnicy (tylko Telegram, nic nie zmieniają)
- `fitmodel/modelq_guard.py` — poniedziałki: TP/HIE na granicy dryfu ≥ 14 dni, kotwica > 90 dni; 1. poniedziałek miesiąca: sprawdzian z Xertem (TP > 5 % → propozycja przeglądu; HIE informacyjnie).
- `fitmodel/power_meter_guard.py`, `fitmodel/load_guard.py`, kwarantanna jazd — podejrzany miernik / obciążenie.
- `fitmodel/meter_physics.py` — miernik vs fizyka podjazdów (masy bagażu w `LUGGAGE`).

## 5. Xert
Niezależny sprawdzian, **nic z Xerta nie jest przenoszone do ModelQ**. Naprawiony 14.10.2026: 25 jazd 01.07–20.08 z wadliwego
miernika oznaczone „invalid breakthrough”, pełny reset od startu 2020 (TP 250 / HIE 21,0 / PP 1100), zanik sygnatury
„None – Training Load Matched”. Wynik: TP 231 (ModelQ 239). HIE Xerta (24 kJ) zawyżone przez XSS z wadliwych jazd.
Kopia dzienna: `qbot_v2.modelq2_xert_bench`; dni 07.07–14.10.2026 = Xert sprzed naprawy → `valid=false`, pomijane w wykresie
`/api/modelq2/data`, w `modelq_guard` i w bloku benchmark raportu jazdy (dane zostają). Od 15.10 kopia po naprawie (TP 231 / HIE 24,2).

## 6. Procedury
- **Zmiana reguły / kotwicy:** kopie tabel (`modelq2_anchor`, `modelq2_signature`, `modelq2_ride`, `fitmodel_daily` → `qbot_v2.bak_<data>_*`),
  zmiana, `build_and_store`, przeliczenie XSS/W′bal jazd (`replay_mpa` + `compute_xss`), `build_and_store`, `publish_to_daily`,
  `fitmodel.daily_job.main()`, kontrola. Wzory: `scripts/mq2_recalc_tp_20261014.py`, `scripts/mq2_add_anchor_20261014.py`.
- **Uwaga:** `daily_job` przelicza też LTHR i wysyła strefy HR do intervals.icu — zmiana XSS może przesunąć LTHR (14.10: 151 → 148, zaakceptowane).
- Testy: `tests/test_modelq2.py`, `test_wbal_feel.py`, `test_modelq_guard.py`.
