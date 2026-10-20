# Tło ekranu startowego Karoo (KAROO TLO)

Wdrożone 20.10.2026 (sesja karoo-tlo-2010). Kod: `qbot_karoo_tlo.py` (rysowanie), `qbot_web.py` blok `KAROO TLO` (dane, adresy).

## Jak działa Karoo (zmierzone na Karoo 3, Android 12)
- Tło ekranu startowego = ustawienie globalne Androida `launcher.background.full_url` (adres obrazka). Ekran startowy pobiera obrazek przez sieć (Picasso) i zapamiętuje go po adresie, dlatego **każda nowa wersja ma nowy adres**.
- Zmiana ustawienia działa od razu (bez restartu); przyjmowany jest dowolny adres http/https.
- Karoo pokazuje proporcjonalny, ok. 2,5x powiększony wycinek: w obrazku 1440 x 2400 kafel profilu 1 to x 80–481, y 873–1585; widoczne tło x 0–600, y 793–1613. Od połowy ekranu boki zakrywa dolny pasek menu.
- Wymuszony ciemny tryb (`setprop debug.hwui.force_dark true`) przyciemnia menu, ale kładzie jasną mgiełkę (ok. 50% bieli) wokół kafla i znika po restarcie. Aplikacja nie może go ustawić sama; możliwa droga: debugowanie bezprzewodowe w zaufanej sieci (zweryfikowane: port TLS otwiera się po zatwierdzeniu sieci na Karoo).

## Obrazek
1440 x 2400 PNG: zdjęcie na cały widoczny obszar, czarny pas pod paskiem statusu, boki wygaszone do czerni przy dolnym pasku, w kaflu lekkie przyciemnienie i dane:
QBot + data, stan dnia (pasek w kolorze), gotowość i świeżość (jak tarcza Startu: `readiness_effective`, `tsb_real`, ostatni dzień `/api/forma/data`), pogoda na najbliższą jazdę rowerową z Trenera (`qbot_v2.trainer_session`, sport='rower', okno start–koniec; bez jazdy: najbliższe 2 h; `/api/pogoda/warunki` dla domu QBota), „SPRAWDŹ ROWER” gdy w `garage.db.bike_task` są zadania `todo`, logo QBot w prawym dolnym rogu kafla. Czcionka Saira Semi Condensed.
Zdjęcie v1: jedno stałe (`KAROO_TLO_FOTO`, Oppelner Gravelzug D2, 02.08.2026). Pula zdjęć i rotacja — później.

## Adresy
- `GET /karoo/tlo/<klucz>/aktualny` → `{url, wersja}` — publiczne, dla QExt2. Przelicza dane najczęściej co 30 min; nowy PNG tylko gdy dane się zmieniły (wersja = skrót danych).
- `GET /karoo/tlo/<klucz>/<wersja>.png` — publiczne, `Cache-Control: immutable`; trzymane 5 ostatnich wersji.
- `GET /api/karoo/tlo` (`?odswiez=1`) — tylko zalogowany właściciel: adres, dane, adres dla QExt2.
- Klucz: `data/karoo_tlo/token` (tworzony automatycznie, 600, poza gitem). Zły klucz → 404. Wyjątek w bramce logowania: ścieżki `/karoo/tlo/`.

## Po stronie Karoo (projekt QExt2 — osobno)
Od QExt2 0.4.5 (build 350, commit f65c490): adres `aktualny` przychodzi w `ride-readiness` jako `homeBgUrl` (mcp_server.py, usluga q-bot); QExt2 zapisuje go i co 30 min, po jezdzie i przy starcie uslugi (poza jazda) ustawia tlo. Wpisy w dzienniku jazdy QExt2: `HOMEBG SET|SAME|NO_PERMISSION`, `HOMEBG_FAIL`, `HOMEBG_SKIP`.
QExt2 co 30 min i przy starcie, tylko poza jazdą: pobiera `aktualny` i wpisuje `url` do `launcher.background.full_url` (wymaga jednorazowo `adb shell pm grant com.qext2.primary android.permission.WRITE_SECURE_SETTINGS`). Ręcznie: `adb shell settings put global launcher.background.full_url "<url>"`.
