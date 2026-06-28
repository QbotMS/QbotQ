# QBot project gap analysis - 2026-05-19

Porownanie zalozen projektowych QBot z aktualnym stanem `/opt/qbot/app`.

## Status ogolny

QBot ma dzialajacy szkielet projektu: MCP server, garaz, wellness, Intervals,
Garmin, Xert, pogode, raport dzienny, Telegram/email replies i klient LLM.
Nie jest jednak w pelni zgodny z instrukcja projektowa jako system zachowan.
Najwieksze rozjazdy sa w automatycznym egzekwowaniu zasad Q oraz w raporcie
jazdy.

## Zgodne lub prawie zgodne

- LLM: obecnie aktywny jest Anthropic przez `ANTHROPIC_API_KEY`.
- Jezyk/styl: prompty raportow wymuszaja polski, konkretny styl i brak
  wymyslania w ograniczonym zakresie.
- MCP: istnieja narzedzia wskazane w projekcie:
  `get_activities`, `get_activity_details`, `get_route_surface`,
  `get_xert_status`, `get_xert_activities`, `get_wellness`,
  `get_garmin_wellness`, `save_wellness`, `garage_overview`,
  `search_garage`, `save_bike`, `save_component`, `save_fitting`,
  `save_gear`, `save_memory`, `save_trip`, `create_packing_list`,
  `get_trips`, `get_trip`, `get_packing_summary`, `update_item`,
  `delete_item`, `update_packing_item`, `get_weather`,
  `list_local_fit_files`.
- Pogoda MCP: `get_weather` zwraca `teraz`, `hourly_forecast`, `prognoza`
  i uzywa jednostek C oraz m/s.
- Raport dzienny: korzysta z Intervals wellness, Xert, Garmin, pogody,
  danych kalorii i tripow. Po poprawce czeka na sen do 09:00 i ma fallback
  tekstowy.
- Raport dzienny generuje narrację jednym strukturalnym wywołaniem LLM JSON
  zamiast serii osobnych calli.
- Reguły gotowości treningowej są wydzielone do `qbot_readiness.py` i używane
  przez raport dzienny, szablon email oraz raport jazdy.
- Lokalni klienci MCP uzywaja wspolnego `qbot_mcp_client.py`, ktory poprawnie
  wysyla `notifications/initialized` po `initialize`.
- Telegram replies: parsuja wellness, gear, kalendarz i zapisuja przez MCP.
- Email replies: parsuja odpowiedzi na raporty dzienne i raporty jazd oraz
  czesc danych zapisuje do wellness/memory/calendar.

## Centralna instrukcja Q

Projekt zaklada, ze Q zawsze dziala wedlug pelnej instrukcji. Stan po naprawie:
dodano `QBOT_INSTRUCTIONS.md` i `qgpt_client.py` automatycznie dokleja te
reguly do system promptow.

Nadal kazdy modul ma wlasne, skrocone prompty domenowe:

- `daily_report.py`
- `email_template.py`
- `ride_report.py`
- `telegram_reply_processor.py`
- `email_reply_processor.py`

Skutek po naprawie: zasady ogolne sa juz wspolne dla wywolan LLM, ale pelna
instrukcja projektowa nie jest jeszcze przełożona na egzekwowalny pipeline.
Najwieksza luka nadal dotyczy raportu jazdy i twardych krokow walidacyjnych.

## Raport jazdy vs protokol 6-krokowy

`ride_report.py` pobiera:

- `get_activity_details`
- `get_route_surface`
- `get_xert_status`
- `get_garmin_wellness`
- Intervals wellness
- ostatnie aktywnosci
- gear
- tripy
- kalendarz

To jest dobry fundament, ale nie realizuje w pelni protokolu projektowego.
Po kolejnej naprawie raport ma juz deterministyczna warstwe `build_ride_protocol`
i sekcje HTML `Protokół 1-6`, ktore jawnie pokazuja zdrowie, komentarz,
teren, moc/HR/kadencje, porownanie i dlugie jazdy.

Pozostale braki:

- Porownanie z podobnymi jazdami jest uproszczone do ostatnich aktywnosci,
  z podstawowym filtrem choroby/kontuzji/przerwy, ale bez zaawansowanego
  szukania dalej wstecz, gdy 7 dni jest puste.
- Dlugie jazdy >3h lub >80 km maja osobna sekcje i liste poprzednich dlugich
  jazd, ale power fade/cardiac drift dla pierwszej i drugiej polowy nadal
  wymagaja danych splitow/streamow.
- Layout HTML raportu jazdy ma 9 sekcji, ale nie odpowiada dokladnie
  projektowemu layoutowi tekstowemu "OCENA JAZDY"; ma jednak jawne bloki
  protokolu przed stara czescia interpretacyjna.
- `ride_report.py` jest teraz zaplanowany w cronie qbot co 30 minut.
- Ryzyko techniczne oznaczania przed wysylka zostalo naprawione: raport jazdy
  ma teraz statusy `in_progress`, `sent`, `failed`, a `failed` nie blokuje
  ponowienia.

## Pogoda

MCP `get_weather` jest zgodne ze specyfikacja. `daily_report.py` uzywa teraz
MCP `get_weather`; bezposredni fallback Open-Meteo zostal usuniety.

## Automatyczny zapis do garazu

Czesciowo wdrozone:

- Telegram zapisuje wellness i gear observations.
- Email replies zapisuja wellness, suplementy, schedule, nutrition/health,
  gear notes i kalendarz w wybranych przypadkach.
- `db.save_memory` dziala.
- MCP `save_memory` dopisuje do istniejacego topicu i pomija dokladne duplikaty.
- `replace_memory` istnieje jako osobne narzedzie dla snapshotow/stanu biezacego.
- Gear notes sa teraz klasyfikowane do `save_gear`, `save_component` albo
  `save_memory`, zamiast zawsze trafiać do memory.
- Jasne wzmianki o nowym rowerze trafiają do `save_bike`; fitting bez pewnego
  `bike_id` trafia do osobnego topicu `fitting_note`.

Braki wzgledem projektu:

- Nie ma uniwersalnej reguly "na koniec dluzszej rozmowy zapisz ustalenia" dla
  wszystkich kanalow.
- Potwierdzenia nie sa w standardzie `📝 Zapisano do garażu`; czesc kanalow
  odpowiada `✅ Zapisano`.

## Priorytety zrodel danych

Projekt: Xert -> Intervals wellness -> Garmin.

Stan:

- Raport dzienny korzysta ze wspólnej funkcji gotowości w `qbot_readiness.py`.
- Raport jazdy pobiera Xert, Intervals i Garmin, ale interpretacje oddaje w
  duzej mierze do LLM zamiast miec twarde reguly walidacyjne.

## Profil zawodnika i fitting

Projekt zawiera konkretne stale: Michał, Canyon Grizl, FTP 236/246, fitting.

Stan:

- Czesc profilu jest pobierana z Intervals/Xert/gear.
- Kadencja gravel jest czesciowo uwzgledniona w `get_route_surface` i promptach.
- Nie widac centralnego zasobu z pelnym profilem i fittingiem jako stalego
  kontekstu dla wszystkich modulow.

## Karoo 3 / SDK

Stan kodu zawiera integracje Hammerhead/Garmin sync i QLab export, ale zalozenia
o projektach Karoo SDK (`gross average speed`, `battery depletion ETA`) nie sa
widoczne jako aktywny modul w `/opt/qbot/app`.

## Znane problemy runtime

- Hammerhead/Garmin sync nie przerywa juz pracy na
  `FitParseError: No such field 2 for dev_data_index 3`, ale metryki raportowe
  moga byc zdegradowane dla plikow, ktorych `fitparse` nie potrafi odczytac.
- `ride_report.py` jest w cronie qbot co 30 minut.

## Priorytetowe rekomendacje

1. Dopracowac raport jazdy: zaawansowane porownania dalej niz 7 dni i docelowy layout zgodny 1:1 ze
   specyfikacja.
2. Dopracowac zapisy sprzetowe: mapowac realne zmiany sprzetu na
   `save_component`/`save_gear`, nie tylko `save_memory`.
3. Zapisac profil zawodnika/fitting jako centralny kontekst wykorzystywany przez
   wszystkie moduly.
