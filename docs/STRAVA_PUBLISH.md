# Strava: automatyczny rower + opis „Albert · QBot” (2026-10-09)

Kod: `qbot_strava_publish.py` (watek startowany z `qbot_strava.build_router` w qbot-web). Testy: `tests/test_strava_publish.py`.

## Co robi
Co 20 min (6:00–23:59) pobiera aktywnosci Stravy z ostatnich 3 dni, a dla kazdej jazdy od **09.10.2026**
(`START_FROM`, starszych nie przepisuje) wykonuje jeden `PUT /activities/{id}`:
- **gear_id** – rower z czujnikow (`qbot_v2.activity_device`): AXS 10625 = Grizl, AXS 27856 = Grail, brak AXS = Monster.
  Rower QBota -> rower Stravy: `qbot_v2.strava_gear_map`, uzupelniane samo z `GET /athlete` (nazwa zawiera grizl / grail / monster|grand canyon).
  Gdy dopasowanie niejednoznaczne – powiadomienie w dzwonku z lista rowerow ze Stravy.
- **description** – ZAWSZE nadpisuje (decyzja Michala: nie prowadzi notatek na Stravie).
Powiazanie jazda <-> aktywnosc Stravy: `qbot_v2.strava_activity.ride_key` (dopasowanie po czasie startu +-15 min, istniejacy mechanizm).
Stan: `qbot_v2.strava_publish` (status ok / czeka / blad, opis, fakty, proby). Czeka maks. 24 przebiegi (~8 h) na czujniki,
raport z jazdy i W'bal; potem wysyla to, co ma (bez roweru -> powiadomienie).

## Opis (format zatwierdzony przez Michala)
1. `📍 <region>: <km> km i <m> m w górę — 🛣️ X% asfaltu, 🌾 Y% szutru, 🪨 Z% ujebów.`
   Nawierzchnia z `ride_report_data` (5 kategorii): twarda szybka = asfalt; dobry/zwykly gravel = szuter; trudna/wolna + ryzyko = **ujeby** (dosłownie).
2. Wysilek z `fitmodel_wbal_ride` wzgledem WLASNEJ historii (percentyle bez biezacej jazdy):
   - 🥵 **Wpierdol**: min W'bal < 10% i XSS/h >= p75,
   - 💪 **Mocno, ale stabilnie**: XSS >= p75 i min W'bal >= 25%,
   - 😌 **Lekko**: XSS < mediana i min W'bal > 50%,
   - ⚡ **Równa, solidna jazda**: pozostale.
3. Opcjonalnie: `🟩 N nowych kwadratów` (zoom 14, historia GPS QBota od 01.01.2025), `⭐ atrakcja` (0–1, ocenia AI), `☕ przerwa: <miejscowosc>` (>= 15 min).
4. `🤖 Albert · QBot`.

## Zrodla i zabezpieczenia
- Miejscowosci/gminy/powiaty: Nominatim (co 8 km sladu, cache `qbot_v2.geo_rev_cache`, 1 zapytanie / 1,2 s).
- Atrakcje: Wikidane (SPARQL `wikibase:box` co 5 km sladu): obiekty z rejestru zabytkow (P1435) lub z >= 2 Wikipediami, <= 400 m od sladu.
- **Prywatnosc**: nic w promieniu 3 km od startu i mety; zadnych danych zdrowotnych, FTP, planow Trenera.
- **AI** (`qgpt_json`) wybiera TYLKO region i atrakcje z list QBota; liczby wstawia QBot. Atrakcja spoza listy jest odrzucana,
  region z nazwa spoza danych tez (wtedy region = „między A a B” z miejscowosci).

## Wymagania i obsluga
- Uprawnienia Stravy: `read,activity:read_all,activity:write,profile:read_all`. Po wdrozeniu trzeba RAZ kliknac
  „Połącz ze Stravą” na /strava.html. Bez `activity:write` automat nic nie wysyla i zostawia powiadomienie.
- Wylacznik: zmienna `QBOT_STRAVA_PUBLISH=0` w srodowisku qbot-web.
- Podglad bez wysylania (~1 min, NIE przez dev_shell_exec): `.venv/bin/python3 qbot_strava_publish.py --dry <ride_key>`.

## Na pozniej
- Ilustracja/grafika z jazdy (API Stravy nie pozwala wgrywac zdjec – do zaprojektowania osobno).
