# QBot — Centrum powiadomień (dzwonek)

_Utworzono 2026-10-08. Żywy system wygrywa — weryfikuj na kodzie._

## Co to jest
Dzwonek w lewym menu (pod ☰, na każdej stronie z nav.js). Pomarańczowa plakietka z liczbą = nieprzeczytane.
Na telefonie ta sama plakietka jest na pływającym przycisku menu. Klik → panel wysuwany obok dzwonka
(komputer: tuż przy menu, na wysokości dzwonka; telefon: pełna wysokość z lewej). Zamykanie: ×, Esc, klik obok,
ponowny klik w dzwonek. Otwarcie panelu oznacza wszystko jako przeczytane. Telegram działa jak dotąd — dzwonek go nie zastępuje.

## Warstwy
- Tabela `qbot_v2.notif` (`sql/notif_v1.sql`): key (unikalny), kind, title, body, url, action (JSONB), read_at, resolved_at.
- Logika: `qbot_notif.py` — `push()` (zmiana treści lub ponowne otwarcie ⇒ nieprzeczytane), `resolve()`, `sync_live()`, `listing()`, `mark_read()`, `dismiss()`.
- API (`qbot_web.py`): `GET /api/notif` (stan na żywo przeliczany najwyżej co 60 s), `POST /api/notif/read` ({ids} albo {} = wszystkie), `POST /api/notif/dismiss` ({id}).
- Front: `nav.js` (`qBell`, odpytywanie co 2 min i przy powrocie na kartę), style w `nav.css` (sekcja CENTRUM POWIADOMIEN). Statyki poza repo, kopia w web_public/.

## Dwa rodzaje pozycji
1. **Stan na żywo** (`live:*`) — liczony przy odczycie, sam znika gdy warunek ustąpi:
   - `live:rower:<bike_id>` — otwarte zadania przy rowerze (garage.db `bike_task`), przycisk „Zrobione”, link do jazdy;
   - `live:trasa:<id>` — trasy czekające na potwierdzenie w Telegramie (`telegram_pending_actions`, status pending, nieprzeterminowane);
   - `live:dane:sen|waga` — brak świeżych danych > 3 dni (`qbot_wellness_daily.sleep_score`, `fitmodel_daily.weight_kg`).
2. **Zdarzenia** (`trener:*`) — kopia wiadomości Trenera: plan tygodnia, rozliczenie, zmiana planu z Kalendarza, przeliczenie po wykonaniu (`qbot_trener_notify._nc`). Widoczne 14 dni, można „ukryj”.

## Jak dodać nowe źródło
Zdarzenie: `import qbot_notif as NF; NF.push(cur, "<modul>:<id>", "<kind>", tytul, tresc, url)` + commit.
Stan na żywo: dopisz funkcję `live_*` i jej wywołanie w `sync_live` (osobny try — błąd jednego źródła nie blokuje reszty).
Ikony rodzajów: `KIND_ICON` w `qbot_notif.py`.

## Krok 2 (otwarte)
Jazdy (nowa jazda / raport / brak ubioru), System (usługi, dysk, logowania, QR demo), Pogoda przed jazdą.

## Testy
`tests/test_notif.py` (4).
