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

## Rodzaje jazd (2026-10-09 b) – uczone z nazw Michala na Stravie
- Nazwa ~ „mam” = **do Mamy**, ~ „biom” = **MyBiom**. Model: kafelki zoom 15 sladow GPS tych jazd (cache 6 h).
- **do Mamy**: >= 60% „rdzenia” (kafelki obecne w >= 60% jazd do Mamy) i >= 60% sladu na znanych drogach, 10–45 km
  -> **BEZ opisu** (pole opisu czyszczone), rower ustawiany normalnie.
- **MyBiom**: >= 60% rdzenia lasow i >= 80% sladu w znanych kafelkach, 10–45 km -> region zawsze **„Przepiękna Puszcza Słupecka”**.
- Walidacja 09.10 (88 jazd do 45 km, kazda wykluczona z wlasnego modelu): do Mamy 10/10, bez falszywych wsrod nazwanych;
  MyBiom 17/20 (pominiete: nowe sciezki, 42 km, jazda w innym miejscu). Dodatkowo QBot rozpoznaje jazdy po tych samych lasach / do Mamy
  nazwane inaczej („Afternoon Ride”, „To las”). Skrypt: `scripts/_tmp_validate_kind.py`.

## Opis (format zatwierdzony przez Michala)
1. `📍 <region>: <km> km i <m> m w górę — 🛣️ X% asfaltu, 🌾 Y% szutru, 🪨 Z% ujebów.`
   Nawierzchnia z `ride_report_data` (5 kategorii): twarda szybka = asfalt; dobry/zwykly gravel = szuter; trudna/wolna + ryzyko = **ujeby** (dosłownie).
2. Wysilek wzgledem WLASNEJ historii (percentyle bez biezacej jazdy). **W'bal / bak NIGDY w tekscie** (dane prywatne, 2026-10-09 b):
   - 🥵 **Wpierdol**: min W'bal < 10% i XSS/h >= p75,
   - 💪 **Mocno, ale stabilnie**: srednie tetno >= p75 LUB srednia moc >= p75 LUB XSS >= p75, a min W'bal >= 25%
     (ponizej 25% -> „💪 Mocno: … z ostrymi akcentami”),
   - 😌 **Lekko**: tetno < mediana i moc < mediana i XSS/h < mediana,
   - ⚡ **Równa, solidna jazda**: pozostale.
   (Poprawka po 08.10: krotka jazda z wysokim tetnem nie moze byc „lekka” tylko dlatego, ze laczne XSS jest male.)
3. Opcjonalnie: `🟩 N nowych kwadratów` (zoom 14, historia GPS QBota od 01.01.2025), `⭐ atrakcja` (0–1, ocenia AI), `☕ przerwa: <miejscowosc>` (>= 15 min).
4. `🤖 Albert · QBot`.

## Zrodla i zabezpieczenia
- Miejscowosci/gminy/powiaty: Nominatim (co 8 km sladu, cache `qbot_v2.geo_rev_cache`, 1 zapytanie / 1,2 s).
- Atrakcje: Wikidane (SPARQL `wikibase:box` co 5 km sladu): obiekty z rejestru zabytkow (P1435) lub z >= 2 Wikipediami, <= 400 m od sladu.
- **Prywatnosc**: nic w promieniu 3 km od startu i mety; zadnych danych zdrowotnych, W'bal, FTP, planow Trenera.
- **AI** (`qgpt_json`) wybiera TYLKO region i atrakcje z list QBota; liczby wstawia QBot. Atrakcja spoza listy jest odrzucana,
  region z nazwa spoza danych tez (wtedy region = „między A a B” z miejscowosci).

## Wymagania i obsluga
- Uprawnienia Stravy: `read,activity:read_all,activity:write,profile:read_all`. Po wdrozeniu trzeba RAZ kliknac
  „Połącz ze Stravą” na /strava.html. Bez `activity:write` automat nic nie wysyla i zostawia powiadomienie.
- Wylacznik: zmienna `QBOT_STRAVA_PUBLISH=0` w srodowisku qbot-web.
- Podglad bez wysylania (~15–60 s, NIE przez dev_shell_exec): `.venv/bin/python3 qbot_strava_publish.py --dry <ride_key> [--no-ai]`.

## Tytul aktywnosci (2026-10-09 e)
Tylko w miejsce DOMYSLNEJ nazwy (Afternoon Ride, Popołudniowa jazda, „<Miasto> Kolarstwo” z Garmina itd. – `is_default_name`).
Poetyka tytulow zostaje Michalowi; QBot daje rzeczowa „metryczke”:
- MyBiom -> `MyBIOM`, do Mamy -> `do Mamy` (bez [Qbot]),
- pozostale: `[Qbot] A – B · <etykieta> <ikona jazdy> <pogoda>` (BEZ km – sa w polu Stravy),
  - A – B: najwazniejsze miejscowosci po drodze (miasta > miasteczka > wsie, Nominatim co 4 km), bez okolic startu/mety,
  - etykieta: `bikepacking Dn` (kolejne dni ze startem > 80 km od Warszawy; 1. dzien QBot jeszcze nie wie) / `wyprawa` (>= 80 km) /
    `gravel` (szuter+ujeby > 30%) / `szosa` (asfalt > 85%) / `mix`,
  - ikona jazdy: 🥵 💪 ⚡ 😌 (jak w opisie),
  - pogoda (blok weather raportu z jazdy, maks. 2): ☀️ 🌤️ ☁️ / 🌧️ (❄️ gdy srednio <= 1°C) + 💨 (wiatr >= 8 m/s) / 🔥 (>= 28°C) / 🥶 (<= 0°C).
- W tytulach i atrakcjach NIGDY obiektow religijnych ani cmentarzy (filtr `_SACRAL`, decyzja Michala); „ujeby” tylko w opisie.
Przyklady: 04.10 `[Qbot] Wyszogród – Czerwińsk nad Wisłą · wyprawa 💪 ☁️`, 06.10 `[Qbot] Warszawa – Marki · mix 💪 ☁️`.

## Otwarte
- Ilustracja/grafika z jazdy (API Stravy nie pozwala wgrywac zdjec – do zaprojektowania osobno).
