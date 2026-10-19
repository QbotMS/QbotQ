# Zadanie dla sesji QExt2: pole AERO v3 („POZYCJA”)

Data: 19.10.2026. Źródło: audyt `docs/AERO_CDA_AUDIT_HANDOFF_2026-10-19.md`, opis QBota `docs/AERO_CDA.md`, decyzje Michała 19.10.
QExt2 to osobny projekt — to zadanie opisuje, CO ma się zmienić i DLACZEGO; implementacja w repo QExt2.

## 1. Cel (decyzja Michała 19.10)
Pole AERO ma pomagać **optymalizować opór, na który Michał ma wpływ** (pozycja: klamki, dolny chwyt, lemondka, łokcie), żeby jeździć
efektywniej. **Nie** ma mierzyć zmiany nawierzchni (asfalt → szuter) — to oczywiste i nic nie daje na żywo.
Pole pokazuje **jedną liczbę: POZYCJA** w watach względem odniesienia („teraz” vs „przed chwilą”), z odjętym wpływem wiatru i drogi.

## 2. Co pokazały testy QBota (ważne dla projektu)
- Dla wykrywania ZMIAN stały błąd masy i Crr jest przesunięciem, które odejmuje się między „teraz” a „odniesieniem”.
  Szkodzi to, co się **zmienia** między tymi chwilami: (a) kierunek względem wiatru, (b) nachylenie, (c) nawierzchnia.
- Sztuczne jazdy (QBot `tests/test_cda_synthetic.py`): błąd nachylenia 0,1 % → CdA −8 %; jazda w jednym kierunku z wiatrem 3 m/s → +9…+19 %;
  mokra droga (Crr ×1,2) → +14 %.
- Na szutrze (MyBIOM, 19.10): opór drogi różni się **między miejscami o ~35 W** (25 km/h) i **między dniami o +10–16 W** (20 km/h).
  Mapa nawierzchni tego nie widzi → **na szutrze pole może mieć tylko „niską pewność”**. Wiarygodne będzie głównie na asfalcie.
- Jazda 18.10 miała pole **v1** (commit v2 `da7d0a9` po jeździe) — v2 nie było jeszcze sprawdzone na prawdziwej jeździe.

## 3. Priorytety v3 (kolejność ma znaczenie)
1. **Wiatr w równaniu.** Prędkość względem powietrza: `v_pow = v + wiatr_czołowy` (karoo-headwind na żywo; składowa wzdłuż kursu).
   Bez tego każdy zakręt względem wiatru wygląda jak zmiana pozycji.
2. **Nachylenie i przyspieszenie jako bilans na oknie** (np. 20–30 s): `ΔE_pot` z różnicy wysokości na oknie, `ΔE_kin` z prędkości na końcach,
   zamiast chwilowego `grade` (dziś surowy strumień Karoo, `RideDataAggregator.kt:722`, współczynnik filtra 1,0).
3. **Nawierzchnia:** przy zmianie klasy nawierzchni (z profilu trasy, `SurfaceProfileCache`) → reset odniesienia albo „niska pewność”.
   Na szutrze zawsze „niska pewność”. Bez trasy: nawierzchnia nieznana → liczyć jak asfalt i oznaczyć niską pewność.
4. **Parametry z QBota** (`aeroModel`, rozdz. 4) zamiast stałych: masa (waga + 14 kg zamiast +9), Crr asfalt / szuter, sprawność.
   CdA roweru tylko jako punkt startowy / do skali — pole liczy ZMIANĘ.

## 4. Wejście z QBota: `aeroModel` w `/ride-readiness` (gotowe 19.10)
`fitmodel/cda.py: karoo_aero_model()`, dołączane w `qbot_api.py` do odpowiedzi `/ride-readiness`. Przykład (stan 19.10):
```json
"aeroModel": {
  "version": 1,
  "updatedAt": "2026-10-19T13:37:10+02:00",
  "riderKg": 103.04,
  "extraKg": 14.0,
  "eta": 0.976,
  "crr": {"asphalt": 0.0055, "gravel": 0.01026, "unknown": 0.00788,
          "byCategory": {"1": 0.0055, "2": 0.00974, "3": 0.01107, "4": 0.00996}},
  "cdaByBike": {"Grail": 0.4321, "Grizl": 0.3607, "Monster": 0.6235},
  "cdaDefault": 0.3918,
  "axsToBike": {"27856": "Grail", "10625": "Grizl"},
  "notes": "CdA = srednia z jazd (bez podzialu na pozycje). Grizl: miesza klamki, dolny chwyt i lemondke."
}
```
- Kategorie nawierzchni QBota: 1 twarda szybka (asfalt), 2 dobry gravel, 3 zwykły gravel, 4 trudna/wolna, 5 ryzyko/niepewna.
- Rower: przerzutka AXS (numer ANT) → `axsToBike`; brak AXS przy czujnikach → Monster (reguła QBota `activity_devices.bike_from_devices`).
- Brak `aeroModel` (QBot niedostępny) → stałe zapasowe jak dziś, pole oznacza „bez parametrów QBota”.

## 5. Zapis do FIT (żeby QBot mógł sprawdzić v3)
Zostawić obecne 4 pola (`qext2_aero_state`, `qext2_aero_dw_w`, `qext2_aero_cda`, `qext2_aero_ref_cda`) i dodać:
- `qext2_aero_ver` (np. 3) — wersja algorytmu w tej jeździe;
- `qext2_aero_conf` (0–2: brak / niska / dobra) — pewność z punktu 3;
- `qext2_aero_wind_head` (m/s) — składowa czołowa wiatru użyta w równaniu;
- `qext2_aero_surface` (klasa nawierzchni użyta w danej sekundzie).
QBot (`fitmodel/qext2_aero.py`) dopisze je do `qext2_aero_record` i sprawdzian w Centrum CdA porówna „POZYCJĘ” pola z wyliczeniem QBota
na tych samych odcinkach (QBot też odejmuje wiatr i drogę — wtedy porównanie będzie uczciwe).

## 6. Testy (wymagane przed jazdą)
- **Syntetyczne** (wzór: QBot `tests/cda_synth.py`): znane CdA, Crr, wiatr; scenariusze: pętla z wiatrem, zmiana kursu przy wietrze 3–6 m/s,
  przejście asfalt → szuter, błąd nachylenia, szum mocy, skok pozycji (np. −15 % CdA na 2 min). Kryteria:
  zmiana kursu przy wietrze NIE daje fałszywej zmiany > 10 W; skok pozycji −15 % wykryty w ≤ 30 s; przejście na szuter → „niska pewność”, nie „zmiana pozycji”.
- **Odtworzenie prawdziwej jazdy** tym samym kodem co na Karoo (FIT 18.10 i kolejne) — wynik musi się zgadzać z zapisem pola.

## 7. Kryteria odbioru
- Pole na asfalcie łapie zmianę klamki → dolny chwyt / lemondka (Michał może zrobić jedną pętlę testową albo nacisnąć „okrążenie” przy zmianie).
- Brak fałszywych zmian przy zakrętach względem wiatru.
- QBot Centrum CdA → „Pole AERO na Karoo — sprawdzian” pokazuje dla jazdy v3: wersję, % czasu pewnego, zmiany, zgodność z QBotem.

## windScale — wiatr z prognozy przy rowerze (2026-10-19, decyzja Michała)
- QBot sprawdził na jazdach (ten sam model co Centrum CdA): wiatr Open-Meteo na 10 m pasuje do danych dopiero po pomnożeniu
  przez **k ≈ 0,25–0,5** (mediana z 10 jazd 0,25). Bez mnożnika Karoo przeliczy wiatr 2–4× za mocno → zakręty wyglądają jak zmiana pozycji.
- aeroModel (/ride-readiness) ma pola `windScale` (mediana k z jazd OK z 120 dni; < 5 jazd → 0,3), `windScaleN`, `windScaleSource`.
- **QExt2 v3: `wiatr_czołowy = windScale × headwind z karoo-headwind`** przed `v_pow = v + wiatr_czołowy`. Do FIT zapisywać użytą wartość
  (`qext2_aero_wind_head`), żeby QBot porównywał uczciwie.
- QBot liczy k per jazda w nocnym CdA (`fitmodel/cda.update_wind_scale`, tabela `qbot_v2.cda_wind_scale`); Centrum CdA dalej dopasowuje
  stały wiatr do jazdy (godzinowy z prognozy wypadł średnio o 4% gorzej — sprawdzone 19.10).
