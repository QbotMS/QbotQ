# Serce (2026-10-12)

Cel: obserwowac tetno spoczynkowe, tetno przy stalej mocy, cisnienie krwi i EKG w jednym miejscu
(Forma > Serce) i dla Alberta (narzedzie `heart_health`). To sygnaly z danych, NIE diagnoza.

## Lancuch danych
- **Cisnienie:** cisnieniomierz Withings -> chmura Withings -> `qbot-withings-sync` (ten sam program i cron
  co waga, co 15 min, blokada /tmp/qbot-withings-garmin-sync.lock) -> Garmin Connect (`set_blood_pressure`,
  potwierdzenie odczytem zwrotnym) -> `qbot3/connectors/import_garmin_heart.py` -> `qbot_v2.blood_pressure`.
  Decyzja Michala: jedna droga przez Garmina, jak waga. Po wyslaniu nowego pomiaru sync od razu odpala import
  do bazy. Stan wyslanych: `state/processed_withings_measures.json`, klucz `bp`.
  Tylko pomiary z urzadzenia (attrib 0/2) -- jak przy wadze; 15.09.2023 13:00 (139/88) pominiety jako reczny.
- **EKG:** zegarek -> Garmin Connect -> `https://ghs.connect.garmin.com/ghs/ecg/v1/ecg/list?firstDay=&lastDay=&pageSize=`
  (adres podejrzany na stronie Garmin Connect 12.10; biblioteka garminconnect go nie ma; naglowki sesji QBota
  dzialaja) -> `qbot_v2.ecg_recording`. Pola: wynik rytmu (`rhythmClassification`, np. SINUS_NORMAL), srednie
  tetno, rmssdHrv, objawy, urzadzenie, detailId (szczegoly/przebieg -- nie pobierane).
- **Tetno przy mocy:** z `qbot_v2.activity_record`: srednie HR w sekundach z moca 140-180 W, od 15. do 120. minuty
  jazdy -> `qbot_v2.hr_at_power` (wiersz na kazda jazde; liczy sie gdy >= 5 min w pasmie).
- **Tetno spoczynkowe:** `qbot_v2.qbot_wellness_daily.resting_hr_bpm` (Garmin).

Import uruchamia straznik Garmina (`scripts/garmin_watch.py`, krok `heart` po `activities`), log
`/opt/qbot/logs/garmin_heart_import.log`. Tabele: `sql/heart_v1.sql`.

## Ocena (`qbot_heart.py`, jedno zrodlo dla strony i Alberta)
- Norma = mediana dni 29-365 wstecz; porownanie ze srednia ostatnich 28 dni.
- Tetno spoczynkowe: +3 uwaga, +5 wyraznie. Tetno przy mocy: +5 / +8 (rosnie tez po spadku formy i w chlodzie).
- Cisnienie (pomiary domowe, srednia serii): <130/80 prawidlowe, 130-134/80-84 wysokie prawidlowe,
  >=135/85 podwyzszone, >=180/110 pilnie do lekarza. Seria = 8 dni wstecz od ostatniego pomiaru;
  przy >= 3 dniach pierwszy dzien odrzucany. Pelny protokol: 7 dni, >= 6 pomiarow rano i >= 6 wieczorem.
- EKG: wszystko poza rytmem zatokowym = czerwone. Pomiary starsze niz 90 dni = "za stare".

## Protokol pomiarow (pokazany w zakladce)
7 dni, potem 1 dzien w tygodniu. Rano (do 1 h po wstaniu, po toalecie, przed kawa/jedzeniem/treningiem) i
wieczorem (przed snem, >= 1 h po jedzeniu, >= 2 h po treningu). 5 min siedzenia, reka na wysokosci serca,
2 pomiary co 1 min. EKG: rano po cisnieniu, po jezdzie po 10-15 min siedzenia, zawsze przy objawach.

## Pliki
`withings_auth.py` (fetch_blood_pressure; status 601 = blad przejsciowy), `qbot-withings-sync` (sync_bp),
`qbot3/connectors/import_garmin_heart.py`, `qbot_heart.py`, `qbot_web.py` (GET /api/forma/heart),
`/opt/qbot/web/public/forma.html` + `forma-serce.js` (poza repo, kopia web_public/), `qbot3/tool_registry.py`
(heart_health) + prompt `qbot3/llm/albert.py`, testy `tests/test_heart.py`.


## 12.10.2026: widok przeniesiony do Zdrowie → Serce
forma-serce.js bez zmian, osadzony w /zdrowie.html (#p-serce); obok zdrowie-serce.js: HRV (norma z roku vs 28 dni) i serce a jedzenie/waga (/api/jedzenie/heart_plus). Forma nie ma już zakładki Serce (forma.html#serce przekierowuje).


## EKG: przebieg, uderzenia, HRV, nieregularne, PDF (2026-10-13)
- Szczegol nagrania: `https://ghs.connect.garmin.com/ghs/ecg/v1/ecg/<detailId>` (podejrzane na stronie Garmin Connect) ->
  `reading.samples` (Lead I, 30 s, 3840 probek, 128 Hz; zegarek nagrywa 512 Hz), `summary` jak lista.
  Import: `import_garmin_heart._ecg_details` (nagrania bez przebiegu; przy nowej wersji analizy przelicza z zapisanego przebiegu).
  Kolumny `ecg_recording`: samples, sample_rate, lead, analysis (`sql/heart_v2.sql`).
- Analiza `qbot_ecg.analyze` (wersja w `analysis.v`): zalamki R (filtr 5-18 Hz, energia, prog adaptacyjny, odstep min. 0,3 s),
  polozenie R doprecyzowane do 1/4 probki (512 Hz), odstepy RR, tetno uderzenie po uderzeniu, HRV z czystych odstepow NN
  (RMSSD, SDNN, pNN50). Nieregularne (rytm): przedwczesne (< 80% lokalnej normy RR, z pauza > 110%), wydluzona przerwa (> 125%).
  Odmienny ksztalt przy normalnym rytmie (korelacja z typowym uderzeniem < 0,85) liczony osobno jako `n_shape`
  ("prawdopodobnie zaklocenie"), nie jako nieregularne. Orientacyjnie: jedno odprowadzenie, nie diagnoza.
- Porownanie z Garminem (13.10): tetno zgodne (52,3 vs 52; 59,8 vs 59; 77,6 vs 77). RMSSD rozne (75 vs 90; 50 vs 38; 21 vs 36) -
  QBot liczy z wykrytych uderzen (sprawdzone recznie na liscie RR), Garmin wlasna metoda; na stronie oba.
- Strona Zdrowie > Serce: tabela EKG (HRV z uderzen, liczba nieregularnych, PDF), klik w wiersz = przebieg (wykres interaktywny:
  zoom przeciagnieciem, dwuklik = calosc, dymek na uderzeniu = odstep RR i tetno; trojkaty: uderzenia, czerwone: nieregularne).
- PDF: `GET /api/forma/ecg.pdf?id=<detailId>` (`qbot_ecg.pdf_bytes`, PIL, czcionka Liberation Sans): A4 poziomo, siatka 25 mm/s
  i 10 mm/mV, 3 pasy po 10 s, kalibracja 1 mV, podsumowanie i zastrzezenia. Dane: `GET /api/forma/ecg?id=`.
- Testy: `tests/test_ecg.py` (syntetyczne EKG: rowny rytm, RMSSD, przedwczesne z pauza, brak sygnalu, PDF).

- Interpretacja (2026-10-13, `qbot_ecg.interpret`, bez AI, regulowa): rytm (zatokowy / pobudzenia / brak potwierdzenia),
  wahania tetna w rytmie oddechu (niemiarowosc oddechowa, prawidlowa), wolne/szybkie tetno, HRV na tle Twoich nagran z tej
  samej pory dnia (mediana od 3 nagran; wczesniej tylko zakres), cisnienie z tej samej sesji (+-45 min; <130/80 prawidlowe,
  130-134/80-84 wysokie prawidlowe, >=135/85 powyzej progu domowego), jakosc sygnalu. Na stronie pod przebiegiem i w PDF.


## AI (2026-10-13, qbot_heart_ai.py) - kontekst do EKG + raport dla lekarza
Zasada jak w Trendach: QBot liczy fakty, AI je opisuje; oceny (prawidlowe / podwyzszone) AI przepisuje z regul QBota.
- Komentarz do EKG: tylko gdy cos odstaje (regula warn/bad albo cisnienie z sesji >= 130/80). Fakty: nagranie, interpretacja
  regul, inne nagrania (HRV), cisnienie z sesji, noc przed (sen, HRV nocne, tetno spocz., stres, body battery vs norma 28 dni),
  trening z 2 dni przed nagraniem. 2-3 zdania. POST /api/forma/ecg/ai?id= (wlasciciel), GET /api/forma/ecg zwraca zapamietany.
- Raport dla lekarza: GET /api/forma/heart/report.pdf - strona 1: podsumowanie AI, uwagi o serii, tabela cisnienia dzien po dniu
  (rano/wieczor, czerwone >= 135/85), srednie serii, wczesniejsze pomiary, EKG z serii, tetno spoczynkowe / przy mocy / HRV nocne vs
  norma, waga, godziny treningu, pytania do lekarza, puste pola: pacjent, leki, objawy; dalej strony EKG z serii (maks. 14).
  Przycisk "Raport dla lekarza (PDF)" w karcie Cisnienie + licznik serii (dni z 7, rano/wieczor).
- Pamiec: qbot_v2.heart_ai (sql/heart_v3.sql), klucz z hashem faktow (te same dane = bez ponownego wywolania AI).
  Model: qbot_food_log._ai_json (cfg.ANTHROPIC_MODEL, temperature 0). Bez Telegrama. Testy: tests/test_heart_ai.py.


## Cisnienie a regeneracja, cialo, sen/SpO2 (2026-10-13)
- `qbot_heart.nexus` (reguly): cisnienie serii vs regeneracja (tetno spocz. delta >= 3, HRV nocne 7 dni < 90% mediany roku, sen 7 dni
  krotszy o > 45 min) -> "stala cecha" albo "czesc moze byc chwilowa"; roznica rano/wieczor >= 15 mmHg skurczowego; wczesniejsze
  pomiary powyzej progu; od 5 dni serii korelacja porannego cisnienia ze snem, HRV i TSS dnia przed (|r| >= 0,6, ostroznie).
- `extras`: wzrost (athlete_profile), waga (body_measurements; tkanka tluszczowa z wagi pominieta - skacze 22/32%), BMI, talia i
  biodra (body_circumference), talia/wzrost (progi 0,5 / 0,6; talia 94 / 102 cm), sen 7 dni vs wczesniej, HRV nocne vs mediana roku,
  SpO2 nocne: `qbot_v2.spo2_daily` (sql/heart_v4.sql; Garmin get_spo2_data: srednia, srednia we snie, NAJNIZSZA; import w
  import_garmin_heart --only spo2, codziennie 3 noce, backfill 30 nocy 13.10). Prog: najnizsza < 90% w >= 30% nocy -> zapytac o bezdech.
- Strona: karta "Cisnienie a regeneracja" (punkty + kafle: talia, waga/BMI, sen, saturacja). Raport PDF: strona 2 (regeneracja,
  cialo, sen i saturacja, pytania, pola do uzupelnienia: badania krwi i moczu, palenie, alkohol, kawa, rodzina, chrapanie, objawy).
- VO2max: Garmin get_max_metrics zwraca pusta liste (13.10) - nie dodane.
