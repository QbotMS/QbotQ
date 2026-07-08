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
