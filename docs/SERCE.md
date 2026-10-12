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
