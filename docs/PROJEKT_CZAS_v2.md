# PROJEKT: Model estymacji czasu przejazdu (route_time_estimate v2)

> Jeden dokument startowy dla NOWEJ SESJI. Stan na 2026-06-30.
> Szczegóły i dowody: docs exchange CURRENT.md (wpisy „B4-v2 …") oraz docs/DECISIONS.md.
> Konwencja: po polsku, bez spekulacji, „bez dowodu nie ma sukcesu", weryfikacja jako qbot, .bak przed zmianą.

## Cel
Estymować czas przejazdu ZAPLANOWANEJ trasy realistycznie: prędkość ruchu (moving) liczona PER SEGMENT z krzywej
nawierzchnia×nachylenie + OSOBNO model stopów. Wyjście = PROFIL CZASU ZEGAROWEGO per segment (nie jedna liczba),
żeby druga połowa trasy miała poprawny czas dotarcia (pod pogodę/WBGT i godziny otwarcia POI).

## Stan obecny (do zastąpienia)
v1 `route_time_estimate` = średnia prędkość z 10 ostatnich jazd outdoor, czas = dist/v. Wady (zdiagnozowane):
duration_s w bazie to czas RUCHU → v1 ignoruje stopy; miesza nawierzchnie/teren w jedną średnią. Działa, ale prymitywne.

## CO GOTOWE (analiza + kalibracja — ZAMKNIĘTE, nie przeliczać)
### Krzywa prędkości (kanon)
Skalibrowana na grade ze SRTM wygładzonym oknem 200 m (spójna z ETA). Prędkość MOVING [km/h], grade w %:
- asfalt:        v = 27.4 − 1.73 · grade
- nieutwardzona: v = 24.6 − 1.14 · grade
- offset nawierzchni na płasko: +3.5 km/h (asfalt > szuter)
Metoda: 7 jazd referencyjnych (ostatnie 3 mies., >70 km), nawierzchnia per punkt z `route_surface_engine`, grade z
`route_elevation_engine` (SRTM, okno 200 m), liczone per rekord; confound mocy rozwiązany (parowanie wewnątrz jazd:
asfalt 223 W vs szuter 219 W na podjeździe). Nawierzchnia BINARNA: utwardzona vs nieutwardzona (decyzja użytkownika).

### Inne ustalenia
- BRAK FADINGU z dystansem do ~100 km — prędkość moving płaska. Kara za długość trasy idzie w STOPY, NIE w prędkość.
- ASYMETRIA SZUTRU: na nieutwardzonej zjazd dokłada mniej niż podjazd zabiera (nie odzyskuje się czasu na zjeździe).
  Do uwzględnienia w v2: osobne nachylenie podjazd/zjazd dla szutru + cap prędkości zjazdu. (Jedna prosta linia to spłaszcza.)
- POGODA POZA modelem czasu (decyzja 2026-06-30) — patrz docs/PROJEKT_METEO.md, Wątek 3.
- Wiatr ZAWSZE w m/s.

### Polityka odświeżania krzywej (zaprojektowana, NIE zakodowana)
- AUTOMAT per jazda: każda nowa jazda >50 km outdoor (bez virtual/miejskich/nie-rowerowych) aktualizuje LUB potwierdza krzywą.
- Okno KROCZĄCE 30 dni. Dwa bezpieczniki: (1) za mało jazd w oknie → zamroź ostatnią dobrą krzywą (zima sama wypada);
  (2) komórka bez pokrycia (np. brak stromych zjazdów) → nie nadpisuj, trzymaj ostatnią + flaga low-confidence.
- Koszt: drogie tylko tagowanie nawierzchni (Overpass) = RAZ na jazdę, cache po sha; refit z okna = ułamek sekundy.
  Zapisywać WKŁAD jazdy (sumy per komórka + downsampled punkty), nie przemielać 2,4 mln rekordów.
- KSZTAŁT vs POZIOM: kształt krzywej (v vs grade×surface) stabilny z dłuższej kotwicy; poziom (forma) z okna 30 dni.
  FTP/bieżąca typowa MOC jako sygnał poziomu — DO TESTU (FTP = sufit, nie output dnia; prędkość napędza moc faktyczna).

## MODEL STOPÓW (przeanalizowany, NIE zakodowany — to połowa modelu, której brakuje)
Z analizy 335 jazd 2025+:
- MIKRO (<2 min): 85% sztuk, ale 22% czasu (światła/skrzyżowania). ~0.55 min/km MEDIANA, rozsiane proporcjonalnie do dystansu.
- DŁUGIE (≥5 min): 3% sztuk, ale ~62% czasu (sam ≥10 min = 50%). Mediana 10 min, ~1 na jazdę; w 54% jazd ≥1, w 46% BRAK.
  Oś ZAMIARU (tryb): wyścig 0 długich / sport-touring ~1 / turystyka 1+.
- POZYCJA długich: szczyt mid-ride (mediana frakcji 0.47; Q1/Q2/Q3/Q4 = 20/38/27/14). RECENT podbija Q4 (24% vs hist 12%)
  → prior z recency-ogonem ku Q4 jako FALLBACK.
- KOTWICZENIE długich w realnych POI z analizy trasy (Google Places — NIE Overpass; Overpass kiepski do POI).
  Prior mid-ride tylko gdy brak danych POI.
- TEREN/URBANIZACJA moduluje liczbę/długość/pozycję długich (HIPOTEZA): bezludne → krótsze/rzadsze; gęste amenities →
  więcej/dłuższe i kotwiczą pozycję. Sygnał z analizy trasy (gęstość POI/land_cover).

## WYJŚCIE MODELU v2
PROFIL CZASU ZEGAROWEGO per segment = start + Σ czas_ruchu + Σ czas_stopów_dotąd.
- Mikro proporcjonalnie do dystansu; długi(e) wstawione w pozycji (kotwica POI albo prior mid-ride z ogonem Q4).
- Schodek czasu na pozycji długiego postoju → druga połowa trasy przesunięta → poprawny WBGT/pogoda po trasie i
  sprawdzanie godzin otwarcia POI w momencie dotarcia.
- W raporcie: czas_RUCHU i czas_CAŁKOWITY(tryb) podawane ODDZIELNIE + profil.

## WEJŚCIA v2 (potwierdzone)
- grade per segment 50 m (z `route_elevation_engine`, okno 200 m) — patrz „Warunek spójności".
- surface per segment (z `route_surface_engine`); binarka paved/unpaved.
- POI z analizy trasy (Google Places) na okazje/kotwice postojów.
- tryb jazdy (wyścig/sport-touring/turystyka) → liczba długich stopów.
- opcjonalnie moc/FTP(257) jako sygnał poziomu (do testu, nie wymagane na start).

## ARCHITEKTURA / WPIĘCIE
- Konsument: `route_analysis_run.assumed_speed_model` → ETA per segment (overlay zależny od start_time).
- WARUNEK SPÓJNOŚCI (twardy): grade dla ETA liczone TYM SAMYM oknem co kalibracja, tj. `route_elevation_engine.
  smooth_elevation(window_m=200)`. NIE używać `route_axis_segments.avg_grade_pct` (netto 50 m) — to nie jest kanon grade.
  (Zastrzeżenie zapisane też w DECISIONS.md.)
- STATUS wpięcia: `route_elevation_engine` (2C) jest WYŁĄCZONE w orchestratorze; `route_analysis_run` nietknięty →
  strona KONSUMENTA jeszcze nie istnieje. To zależność od drugiej sesji.

## DO ZBUDOWANIA (TODO — to jest niezamknięte; sama kalibracja ≠ model)
1. `route_time_estimate v2`: prędkość moving per segment z krzywej (grade+surface) + asymetria szutru (osobne podjazd/zjazd) + cap zjazdu.
2. Model STOPÓW: mikro (~0.55 min/km × dystans) + długie (× tryb, kotwiczone w POI / prior mid-ride z ogonem Q4) + modulacja terenem/POI density.
3. PROFIL CZASU ZEGAROWEGO per segment (start + Σruch + Σstopy) + rozdzielenie czas_ruchu / czas_całkowity w raporcie.
4. AUTOMAT REKALIBRACJI krzywej (okno 30 dni, wkład per jazda, dwa bezpieczniki, kształt vs poziom).
5. WPIĘCIE w `route_analysis_run` (gdy druga sesja włączy 2C + przygotuje assumed_speed_model).
6. (opcjonalnie) test sygnału poziomu: FitModel dzienne FTP + moc per jazda vs czysty pace level.

## ZALEŻNOŚCI / BLOKERY
- 2C (`route_elevation_engine`) włączone w orchestratorze + `route_analysis_run` gotowy na assumed_speed_model — DRUGA SESJA.
  OBSERWACJA 2026-06-30: `qbot_route_time_tools.py` jest aktualnie zmodyfikowany (niezacommitowany) przez drugą sesję →
  UZGODNIĆ kto buduje v2, żeby się nie rozjechać. Krzywa i okno 200 m są gotowe i czekają.
- POI (Google Places) + land_cover/POI density z analizy trasy — do kotwiczenia i modulacji stopów.

## DANE I NARZĘDZIA GOTOWE (klocki)
- `activity_record` (qbot_v2): 335 jazd 2025+, 2,38 mln rekordów 1 Hz z pozycją — baza kalibracji.
- `route_surface_engine` (nawierzchnia per punkt/segment, OSM, korytarzowy Overpass + cache).
- `route_elevation_engine` (2C): SRTM30m + wygładzanie; `build_route_elevation_profile`, `smooth_elevation(200)`, `_frame_grades`.
- Artefakty kalibracji: `/opt/qbot/artifacts/analysis/` — `exec_surface_segments.json`, `exec_elev_<eid>.json`, `exec_*.gpx`
  (7 jazd ref: 23317695684 Wyszogród, 23166590846 Castagneto, 23155690938 Palaia, 22961142284 Skarżysko,
  22655494086 Piaski-Paplin, 22571518498 Suchedniów, 22490117393 Brańszczyk).
- Krzywa kanoniczna zapisana w DECISIONS.md (wpis „okno grade = 200 m") i CURRENT.md.

## ZASADY NADRZĘDNE (wiążące)
- Prędkość MOVING i czas CAŁKOWITY (z postojami) — zawsze ODDZIELNIE.
- Grade liczone oknem 200 m, spójnie z ETA. Nawierzchnia binarna paved/unpaved.
- Bez fadingu do 100 km; kara za dystans → tylko w stopach.
- Pogoda poza modelem czasu. Wiatr m/s. Bez fabrykowania dowodów; uczciwe „nie wiem".

## Status jednym zdaniem
KALIBRACJA (krzywa prędkości) zamknięta i spójna z ETA; ale MODEL CZASU v2 NIE jest zbudowany — brak modelu stopów,
profilu czasu zegarowego, asymetrii szutru, automatu rekalibracji i wpięcia w route_analysis_run. Uruchomienie silnika
przewyższeń odblokowało tylko kalibrację, nie domknęło modelu. Powiązanie z meteo: profil czasu zegarowego daje poprawny
czas dotarcia dla pogody/WBGT i godzin POI; wiatr efektywny (meteo Tier 2) potrzebuje prędkości per segment z tego modelu.
