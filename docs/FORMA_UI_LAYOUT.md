# QBot — Koncepcja LAYOUT stron webowych (Forma & Wellness jako wzorzec)

_Utworzono: 2026-07-17. Zaktualizowano: 2026-07-17 (hero split + aktywności, panel szczegółów jazdy, no-store /api, DZIŚ bez scrolla, Doradca czyta plan, powiększanie kafla)._
_Źródło prawdy o układzie/UI stron qbot-web opartych na tokenach._
_Żywy system wygrywa — zawsze weryfikuj na plikach. Pliki .html/.js/.css są POZA repo (`/opt/qbot/web/public`), działają od razu; wdrażaj bajt-w-bajt przez `dev_write_file`. `qbot_web.py` JEST w repo → restart `qbot-web` + commit._

Strona pilotażowa i wzorzec: **`forma.html`** ("Forma & Wellness"). Nowe strony/lab mają iść tym samym wzorcem.

---

## 1. Architektura warstwowa (jak raport tras)

Per strona rozdzielamy cztery warstwy:

- **DANE** — endpointy w `qbot_web.py`. Forma:
  - `GET /api/forma/data?start&end` → `_build_forma_data`; pola w `_FORMA_FIELDS`; wiersz `_forma_row_out`. Zwraca `{series:[...], latest:{pole:{value,day}}}`.
  - `GET /api/forma/activities?n=3` → N ostatnich aktywności z `qbot_v2.training_sessions` (sort po `COALESCE(started_at, date)`), pola: date, started_at, sport_type, name(=activity_name), distance_m, duration_s, elevation_m, tss, external_id.
  - `GET /api/forma/activity?external_id=` → szczegóły jednej jazdy (moc śr/NP/max, IF, HR śr/max, kadencja, kalorie, TSS, przewyższenie…) + `has_report` (EXISTS w `qbot_v2.ride_report_data` po `ride_key`=external_id).
  - `GET/POST /api/prefs` → ustawienia UI per konto (patrz sekcja 9).
- **ANALIZA (LLM)** — `POST /api/forma/analyze` (tryby `today` / `coach` / `chart`). Wspólny styl = `_STYLE`, mapa serii dla chart = `_MAP`. Każdy tryb dostaje subiektyw z `qbot_v2.calendar_entry` (feel/choroba). **Doradca (`coach`) dodatkowo czyta ZAPLANOWANE wpisy** — `_forma_planned_events(conn, days_ahead=21)` (kind='event', horyzont 21 dni: data + „za N dni", tytuł, godzina, typ urlop/delegacja/rest, notatka) i dopasowuje poradę na najbliższą jazdę + 7 dni do planu (tapering przed długą jazdą/zawodami, uwzględnienie urlopu/delegacji).
- **RYSOWANIE / LOGIKA** — `/opt/qbot/web/public/forma-render.js` (`boot()` pobiera dane, renderuje hero/kafle/wykres/źródła/aktywności).
- **STRUKTURA + STYLE LOKALNE** — `/opt/qbot/web/public/forma.html` (`:root{}` = paleta DZIENNA + CSS strony + sekcje `<section data-qtab>`).

Reguła edycji: wygląd globalny → `theme.css`/lokalny `<style>` w html; rysowanie/wykres → `*-render.js`; dane → endpoint w `qbot_web.py` (repo, restart+commit); struktura/formularze → `*.html`.

Uwaga wdrożeniowa: middleware `_no_cache_static` wymusza rewalidację `.html/.js/.css`. **Od 2026-07-17 ustawia też `Cache-Control: no-store` dla wszystkich `/api/`** — naprawa błędu „wykresy/dane nie odświeżają się po jeździe" (przeglądarka podawała stary JSON, mimo świeżej bazy). Statyki są za logowaniem (webauth) — weryfikacja HTTP z serwera trafia w stronę logowania; testuj przez ciasteczko (`_webauth_cookie_make`) albo grep na dysku, nie curl.

---

## 2. Komponenty wielokrotnego użytku (współdzielone przez strony)

- **`theme.css`** — motyw ciemny: `html.theme-dark{ ...tokeny... }`. Włączany pre-paint inline skryptem w `<head>` (`localStorage qtheme==="dark"`).
- **`nav.css` + `nav.js`** — lewy rail (menu), zwijany (`localStorage qnav_collapsed`), mobilny off-canvas + FAB, stopka z przełącznikiem motywu (dzień/noc). Rail ciemnozielony w obu motywach.
- **`tabs.css` + `tabs.js`** — górne zakładki treści. Owijasz bloki w `<section data-qtab="Nazwa">`; `tabs.js` buduje pasek i chowa nieaktywne przez atrybut `hidden` (`.qtab-panel[hidden]{display:none!important}`). **Montaż**: jeśli istnieje `#qtabs-mount`, pasek ląduje tam (sticky nagłówek Formy); inaczej przed pierwszą sekcją. Pamięta wybór (`#slug` w URL + `localStorage`).
- **`aside.css`** — prawy wysuwany panel (drawer). Logika w `forma-render.js` (`_asideEls`, `asideShow(title,html)`). Zakładka „Analiza AI" (`.qaside-tab`) w 1/4 wysokości od góry, zawsze widoczna; klik generuje analizę (`today`) jeśli jeszcze nie ma, inaczej otwiera panel. **Ten sam drawer służy do szczegółów jazdy** (sekcja 10). Klasy stanu na `body`: `qaside-has` (jest treść) + `qaside-open` (otwarty).

Adopcja na nowej stronie: dołącz `theme.css`, `nav.css/js`, `tabs.css/js`, opcjonalnie `aside.css`; owiń treść w `<section data-qtab>`; używaj tokenów.

---

## 3. System tokenów kolorów

Paleta DZIENNA w `forma.html :root{}`, NOCNA nadpisuje w `theme.css html.theme-dark{}`.

Tokeny bazowe (wszystkie strony): `--ink, --ink2, --muted, --line, --paper, --card, --panel, --accent, --accent-bg, --good/-bg, --bad/-bg, --warn/-bg`.

Tokeny NOCNE dodatkowe (fallback do bazowych w dzień, więc dzień bez zmian):
- `--frame` — tło karty wykresu i kafli (ciemniejsze niż zwykłe `--card`).
- `--side` — tło paneli bocznych (rail + prawy drawer), najciemniejsze.
- `--btnoff` — tło WYŁĄCZONYCH przycisków/chipów.
- `--chart-bg` — „koryto" wykresu (tło `#chartbox`), bardzo ciemne.
- `--chart-border` — ramka wykresu (ciemnobrązowa nocą).

Charakter palety: **dzień** = beż/krem tło + ciemnozielone akcenty + brąz/taupe; **noc** = leśna zieleń tła + beżowy tekst + tan/brąz akcenty.

Hierarchia jasności NOCĄ (od najciemniejszego): panele boczne `--side` / koryto wykresu `--chart-bg` → tło strony `--paper` → ramka/kafle `--frame`.

Zasady kontrastu:
- Kafle (`.tile`) i karta wykresu dzielą to samo tło (`--frame` nocą).
- Element wyłączony (chip/przycisk) recesuje ku `--btnoff`; włączony wybija się (`--accent-bg` + akcent + pogrubienie).

---

## 4. Nieruchomy nagłówek (sticky) — wzorzec

`<div class="qhead">` (`position:sticky; top:0`) zawiera:
1. `.qhead-row` — tytuł strony (lewy) + **wskaźniki źródeł danych** `#qsrc` (prawy).
2. `#qtabs-mount` — tu `tabs.js` wstawia pasek zakładek.

Pasek zakładek wewnątrz `.qhead` jest odsztywniony (`.qhead .qtabs-bar{position:static}`). Wysokość nagłówka + zakładek (~103 px) + paddingi `.wrap` to ~158–165 px narzutu — istotne dla „DZIŚ bez scrolla" (sekcja 9).

**Wskaźniki źródeł** (`renderSources()`): lista `SOURCES` (nazwa → klucze serii). Dla każdego źródła szukamy najnowszego dnia z danymi i liczymy wiek: kropka **zielona ≤1 dzień**, **pomarańczowa ≤3 dni**, **czerwona** starsze/brak. Dymek pokazuje datę ostatnich danych.

---

## 5. Zakładki Formy

`Dziś` (KONFIGUROWALNY panel — sekcja 9) · `Wskaźniki` (kafle Moc/Obciążenie/Wellness + selektor okna zmiany) · `Wykres` · `Odżywianie` (żywienie + skład ciała; patrz docs/PROJEKT_ODZYWIANIE.md).

Cel UX: **treść zakładki mieści się bez scrollowania**. Kafle zwarte (mniejszy padding/mini-wykres/wartość), ciaśniejsze podnagłówki, nagłówek sticky. Zakładka **DZIŚ ma twardy limit wysokości** (mieści się w jednym ekranie — sekcja 9).

---

## 6. Wykres (forma-render.js)

- **Definicja serii** = obiekt `M{ klucz:{ f:pole, label, unit, grp, dir, dec, col, dash?, desc, interp } }`. Grupy do kafli = `GROUPS`, kolejność/legenda = `CHART_ORDER`, jednostki osi = `GRPU`.
- **3 tryby** (`#chartmode`, `localStorage qforma_chartmode`): `norm` (0–100% we własnym zakresie, wspólna oś), `panels` (małe wielokrotności), `abs` (wartości bezwzględne, osie po jednostkach).
- **Belka pigułek** (`#chartlegend`) NAD wykresem; chipy `#checks` (włącz/wyłącz serie) osobno.
- **Interakcja**: kursor (linia + kropki + tooltip), zoom przeciągnięciem po X (zagnieżdżalny), klik = reset.
- Jeden inline SVG (bez CDN); siatka/osie w szarościach z przezroczystością.

### Konwencja kolorów i stylów linii (WAŻNE)
- **Kolor = tożsamość kategorii; styl linii (dash) = druga oś rozróżnienia.**
- **Żaden kolor nie powtarza się między kategoriami.** W obrębie kategorii dopuszczalny wspólny kolor przy różnym stylu.
- **Wellness** rysujemy częściej liniami przerywanymi, w RÓŻNYCH wzorach.
- Szczegóły: HRV i RHR ta sama czerwień (różny dash); W/kg w kolorze CP (inny dash); LTP jasny fiolet; ATL+/TSB+ = kolory ATL/TSB, przerywane.

---

## 7. Dane Formy (fakty)

- Źródło = `qbot_v2.fitmodel_daily` (dzień po dniu). Kanoniczne FTP = `fitmodel_daily.ftp_est_w`; `cp_modelq_w` to obecnie LTP-podobne (patrz DECISIONS/MODELQ).
- **Sen = scoring** (`sleep_score`, agregacja `max` per dzień z `qbot_v2.qbot_wellness_daily` — 2 wiersze/dzień z różnych źródeł).
- **Waga** = `weight_kg` z `fitmodel_daily`.
- Aktywności/szczegóły jazdy = `qbot_v2.training_sessions` (kol.: date, started_at, sport_type, activity_name[miejsce+dyscyplina], distance_m, duration_s, elevation_m, tss, avg/normalized/max_power_w, intensity_factor, avg/max_hr_bpm, avg_cadence_rpm, calories, external_id). **Brak osobnej kolumny lokalizacji** — „gdzie" bierzemy z `activity_name`.
- Raport trasy istnieje, gdy `qbot_v2.ride_report_data.ride_key` = external_id danej jazdy (patrz docs/RAPORT_WEB.md).
- L2/L3 (gotowość efektywna, ATL+/TSB+) — patrz DECISIONS.md.

---

## 8. Checklist dla nowej strony w tym stylu

1. Dołącz `theme.css`, `nav.css/js`, `tabs.css/js` (+ `aside.css` jeśli analiza AI).
2. `:root{}` = paleta dzienna (skopiuj z `forma.html`); noc dziedziczy z `theme.css`.
3. Nagłówek: `.qhead` (sticky) z `.qhead-row` (tytuł + `#qsrc`) i `#qtabs-mount`.
4. Treść w `<section data-qtab="...">`.
5. Używaj tokenów zamiast twardych kolorów.
6. Dane przez endpoint w `qbot_web.py` (odpowiedzi `/api/` dostają no-store z middleware); rysowanie w dedykowanym `*-render.js`.
7. Wdrożenie: statyki `dev_write_file` (żywe od razu); `qbot_web.py` → restart `qbot-web` + commit (repo).

---

## 9. Zakładka „Dziś" — konfigurowalny panel + hero split + brak scrolla

**Idea:** użytkownik sam wybiera, co widzi (kafle z innych zakładek + widżety żywienia). Wybór zapamiętany — najpierw serwer (idzie za kontem), z localStorage jako cache/fallbackiem.

**Struktura (forma.html):** sekcja `<section data-qtab="Dziś">`: nagłówek + `#dzis-edit` „Dostosuj" (toggle) → panel `#dzis-cust` (chipy on/off, grupy Panel / Moc / Obciążenie / Wellness / Żywienie) → `#hero` → `#dzis-board` (siatka kafli) + `#dzis-nut` (widżety żywienia).

**Hero = split na 2 (`renderHero`):** `.hero-split` (grid 1fr 1fr; na wąskim ekranie 1 kolumna):
- lewa `.hero` — stan dnia (Świeży/Neutralny/Zmęczony wg TSB + HRV/RHR), przyciski Analiza/Doradca;
- prawa `.hero.hero-acts` — **Ostatnie aktywności** (3), z `/api/forma/activities`, w globalnej `ACTS` (fetch w `boot`, re-render hero po dociągnięciu). Każda aktywność = **2 wiersze**: (1) dyscyplina + kiedy („dziś 18:50"/„wczoraj"/dd.mm), (2) nazwa (link) + po prawej dystans km (lub czas) + TSS. Mapa PL dyscyplin = `SPORTPL`/`sportLabel`.

**Logika (forma-render.js):**
- Stan `DZIS = {hero:bool, keys:[...]}`; `keys` mieszają klucze `M` i tokeny żywienia (`nut_balance`,`nut_body`).
- `renderToday()` — hero pokaż/ukryj, kafle przez `tile()`, żywienie przez `window.QNut`. `renderDzisCust()`/`wireDzis()` = panel „Dostosuj".
- Widżety żywienia: `window.QNut.{ready,balanceHTML,bodyHTML}`; `renderCards()` (nutrition) woła `window.renderTodayNut`.

**Ustawienia serwerowe (idzie za kontem):**
- Tabela `qbot_v2.ui_prefs(username, pref_key, value jsonb, updated_at, PK(username,pref_key))`, migracja `sql/ui_prefs_v1.sql` (idempotentna).
- `GET /api/prefs?key=` / `POST /api/prefs {key,value}` (upsert), użytkownik z ciasteczka (`_current_user`). Klucz `pref_key='dzis'` → `{hero, keys}`.
- Front: start → `GET` nadpisuje lokalne; `saveDzis()` = `POST` (debounce 400 ms) + `localStorage qdzis_widgets`.

**Brak scrolla (twardy limit):** aktywny panel DZIŚ ma `.qtab-panel[data-qtab="Dziś"]{max-height:calc(100dvh - 168px);overflow:hidden}` (+ fallback `vh`), `#dzis-board{overflow:hidden}`, zmniejszony dolny padding `.wrap` i ciaśniejszy hero. 168 px ≈ nagłówek + pasek zakładek + paddingi. Kompromis: przy nadmiarze wybranych kafli/widżetów nadmiar jest **przycinany**, nie scrollowany; dymki hover kafli w górnym rzędzie mogą być przycięte przez `overflow:hidden`.

**Fazy dalej:** widżet wykresu formy w DZIŚ; widżet wykresu odżywiania w DZIŚ.

---

## 10. Interakcje: panel szczegółów jazdy + powiększanie kafla

**Szczegóły jazdy (reużycie prawego drawera):** nazwa aktywności w hero to link (`.act-n.lnk` + „›", `data-eid`=external_id). `openRide(eid,name)`:
- toggle — drugi klik w tę samą jazdę **zamyka** panel (`_openRideEid` + zdjęcie `qaside-open`); `runAnalyze()` czyści `_openRideEid`;
- fetch `/api/forma/activity?external_id=` → `rideDetailHtml(a)` w `asideShow(...)` (te same tokeny co reszta): dyscyplina, kiedy, dystans, czas, przewyższenie, TSS, moc śr/NP/max, IF, HR śr/max, kadencja, kalorie (wiersze puste pomijane);
- jeśli `a.has_report` → przycisk `.rd-btn` „Otwórz raport trasy ↗" linkujący do `/raport-jazdy.html?ride=<external_id>` w nowej karcie (`target="_blank" rel="noopener"`).

**Powiększanie kafla (`openTileZoom`):** każdy `.tile` ma `data-k`; delegowany klik na `document` otwiera modal `.tilez-back/.tilez` (position:fixed, z-index 200) z: dużą wartością + jednostką, deltą w oknie, **powiększonym mini-wykresem** (`.tilez-chart .mini{height:170px}`), pełnym opisem i interpretacją metryki. Zamknięcie: **klik gdziekolwiek** (tło, karta, „×") lub Esc. Działa na zakładkach Wskaźniki i DZIŚ (widżety żywienia to nie kafle → nieobjęte).
