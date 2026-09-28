# Garaż — dokumentacja modułu (stan 2026-09-24)

Strona: `/garaz.html` (statyki poza repo: `/opt/qbot/web/public/`, cache-busting `?v=N`).
Baza: SQLite `/opt/qbot/app/data/garage.db` (`GARAGE_DB`). Serwer: `qbot_web.py` (`qbot-web`, restart po zmianie).

## Pliki frontu
| plik | rola |
|---|---|
| `garaz.html` | szkielet, CSS (styl wspólny `ui2.css` + `nav.css`), okna edycji (komponent, opona, rower) |
| `garaz-render.js` | zakładka Odzież |
| `garaz-columns.js` | katalog kolumn tabel + zapis widoku (`ui_prefs`) |
| `garaz-tabs.js` | Sprzęt, Rower (kafelki rowerów, komponenty, opony), okna edycji, `DIMS_SPEC` (wymiary części) |
| `garaz-fit.js` | zakładka Fitting (`window.QFit`): geometria, ustawienia, ciało, rysunek SVG, oceny kątów |

## Model danych (garage.db)
- `bikes`: + `nickname`, `photo`, `thumb`. Usunięcie roweru blokowane, gdy ma komponenty lub fitting.
- `components`: `bike_id` (rower), `category` = **angielski kod** (np. `wheels`, `stem`, `handlebar`) — używa go kod (ciśnienia, Albert). Na ekranie tłumaczone przez `CAT_PL` w `garaz-tabs.js`. `dims` (JSON) = wymiary do fittingu wg kategorii:
  - `stem`: length_mm, angle_deg, stack_mm
  - `handlebar`: bar_type (drop/flat), width_mm, reach_mm, drop_mm, rise_mm, backsweep_deg, flare_deg
  - `saddle`: length_mm, width_mm · `seatpost`: offset_mm, travel_mm, length_mm · `crankset`: crank_mm
  - `aero bars`: extension_mm, pad_angle_deg, pad_stack_mm (nad górą kierownicy), pad_setback_mm (względem zacisku, ujemne = za zaciskiem)
- `tires`: `wheel_id` (→ komponent `wheels`) + `position` przód/tył; brak koła = „w garażu”/„wycofana”. Jedno miejsce = jedna opona; zapis na zajęte miejsce odsyła poprzednią do garażu. `fits_wheelset` wypełniane automatycznie nazwą koła.
- `bike_geometry` (1 wiersz/rower): katalog ramy — stack, reach, kąty, długości, koła, `bar_type` (zapas, gdy kierownica bez `dims`), źródło.
- `fitting` (ustawienia z historią): części (`stem_id`, `bar_id`, `saddle_id`, `seatpost_id`, `crank_id`, `aero_id`), regulacje (wysokość/setback/kąt siodła, `spacer_mm`, `headset_cap_mm`, `stem_flipped`), `is_current`, `photo`/`thumb`. Stare pola liczbowe (stem_length_mm itd.) = zapas „gdy brak części”. `reach_mm/stack_mm/drop_mm` = wartości zmierzone przez fittera.
- `rider_body`: pomiary ciała z datą (historia); model bierze najnowszy.

## Endpointy
`GET /api/bike/config` (rowery, komponenty, opony, fitting, geometry, body, weight z Garmina) ·
`POST /api/bike/component/save|toggle|delete` · `/api/bike/tire/save|delete` · `/api/bike/bike/save|delete` ·
`/api/bike/fitting/save|delete` (save aktualizuje tylko przysłane pola) · `/api/bike/geometry/save` · `/api/bike/body/save|delete` ·
zdjęcia: `/api/garage/photo`, `/photo/from-url`, `/photo/delete` z `entity` ∈ gear, equipment, component, bike, fitting.

## Model fittingu (garaz-fit.js)
- Układ: oś suportu = (0,0), mm, oś Y w górę. Wysokość siodła = od osi suportu wzdłuż rury podsiodłowej; setback = czubek siodła za pionem suportu.
- Zacisk kierownicy = góra główki → podkładki + czapka + 18 mm wzdłuż sterów → mostek (długość, kąt wzgl. prostopadłej do sterów; `stem_flipped` odwraca znak).
- Chwyty = zacisk + wznios (rise) w górę + reach do przodu − cofnięcie z backsweepu. Raportowane osobno: zacisk i chwyty.
- Aero: gdy ustawienie ma lemondkę i włączony przełącznik — łokieć na podłokietniku, przedramię pod kątem podłokietników.
- Sylwetka: proporcje ze wzrostu (udo 0.245H, podudzie 0.246H skalowane długością kroku; tułów 0.295H; ramię 0.186H; przedramię 0.16H), nadpisywane pomiarami z `rider_body`. Dokładność kątów ciała ±kilka stopni.
- Zakresy ocen: kolano w dole 140–150°, biodro w górze korby 45–60°, plecy 30–45° (aero 20–35°), bark 80–95° (aero 80–100°). Opisy w dymkach (`TIPS`).
- Braki danych zastępowane domyślnymi i wypisywane pod rysunkiem jako „Założenia”.
- Kończyny rysowane jako wypełnione kształty (`CAP`), nie kreski (kreski znikały w podglądzie czatu).

## Stan danych Grizla (2026-09-24)
- Ustawienia: „Fitter 2025 – bez lemondki”, „Fitter 2025 – z lemondką” (historia: Gear Groove 80 mm, podkładki 25 mm, moduł offsetu, C13; zdjęcie z fittingu) oraz „Moje – aktualne (z lemondką)” (Zipp SL 90 mm −6° potwierdzone, podkładki 5 mm, siodło C17 750 mm).
- Do uzupełnienia: setback siodła w „Moje”, kąt Gear Groove (przyjęte −6°), geometria Monstera (rozmiar ramy nieznany), pomiar ud i podudzi taśmą.

## Znane ograniczenia
- Kalkulator ciśnień i opis roweru dla Alberta biorą koła/komponenty obu rowerów naraz (brak filtra `bike_id`).
- Sylwetka nie modeluje pochylenia miednicy ani długości stopy; długości nóg ze zdjęcia odrzucone jako niewiarygodne.
