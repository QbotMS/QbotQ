# Garaż → Zakupy (planowane zakupy)

Start: 2026-10-13. Zakładka „Zakupy” w Garażu (`/garaz.html#zakupy`): lista rzeczy do kupienia (rower + zdrowie) i lista kupionych.

## Decyzje (Michał, 2026-10-13)
- Zakres: zakupy rowerowe (części, odzież, wyposażenie) i okołozdrowotne (suple, sprzęt typu waga/zatyczki).
- Priorytet w bazie: 1 Pilne / 2 Wkrótce / 3 Kiedyś; lista sortowana po priorytecie.
- Dodawanie: wklejasz link → „Pobierz dane” → QBot wypełnia pola (istniejący `/api/garage/scrape`, `qbot_gear_scrape.py`).
- „Kupione” → pozycja przechodzi do listy Kupione (data + zapłacona cena). Przy rzeczy rowerowej QBot proponuje dodanie do Garażu: otwiera ISTNIEJĄCE okno (Odzież / Sprzęt / komponent Roweru) z linkiem, ceną, datą i odpala tam „Zaciągnij dane”.
- Szukanie najniższej ceny (etap 3): najskuteczniej = AI z wyszukiwarką (cały internet) + Ceneo; każda oferta weryfikowana otwarciem strony sklepu; 3–5 ofert, na przycisk.
- Przypomnienia o zużyciu (etap 2): Dzwonek + Telegram (jedna zbiorcza wiadomość, przyciski „Kup ponownie” / „Odłóż 7 dni”).
- Gmail (etap 4): auto-oznaczanie „Kupione” z maili potwierdzenia zamówienia — wymaga podłączenia dostępu do Gmaila na serwerze.

## Etapy
1. [2026-10-13] Zakładka, okno z linkiem, priorytet, Kupione, propozycja dodania do Garażu.
2. [2026-10-13] Zużycie i przypomnienia — ZROBIONE (opis niżej). UWAGA: suplementy — powiązać z modułem `qbot_supplements.py` (qbot_v2.supplement / supplement_log = rzeczywiste przyjęcia i dawki), zamiast liczyć z „dziennego zużycia” wpisanego ręcznie. Dla rzeczy spoza modułu suplementów (np. zatyczki) — opakowanie + zużycie dzienne.
3. Najniższa cena.
4. Gmail.

## Warstwy
- DANE: `garage.db`, tabela `shop_items` (tworzona przez `qbot_zakupy_api.py`, IF NOT EXISTS).
- API: `qbot_zakupy_api.py` → `/api/zakupy/list|save|bought|unbought|delete` (zapisy tylko właściciel; demo = odczyt). Montaż w `qbot_web.py` przed `app.mount("/")`.
- FRONT (poza repo, żywe od razu): `garaz-zakupy.js` (samodzielna zakładka jak `garaz-notatki.js`), znaczniki i style w `garaz.html`, pole szukania w `garaz-search.js` (MAP `tabZakupy`).
- Miniatura: przy zapisie z `image_url` serwer robi JPEG 320 px (data URI w `thumb`) — lista nie zależy od hotlinków sklepu.
- Testy: `tests/test_zakupy.py` (tymczasowa baza).

## Etap 2 — zapas i przypomnienia (2026-10-13)
- Pola pozycji: `pack_units` (np. 90) × `qty`, `pack_unit` (kaps./szt./par…), `opened_at` (otwarte od; domyślnie data zakupu),
  `lead_days` (przypomnij N dni przed końcem, domyślnie 10).
- Zużycie — jedno z dwóch:
  - ręczne `per_day` (np. 2 dziennie),
  - powiązanie z Zdrowie → Suplementy (`supplement_id`, `per_intake` = jednostek na przyjęcie). Liczone dni wg harmonogramu
    suplementu (dni tygodnia) od otwarcia do wczoraj MINUS dni oznaczone „pominięte”. Dzień niepotwierdzony liczy się jako
    wzięty — przypomnienie raczej za wcześnie niż za późno. Suplement wyłączony = brak prognozy końca.
- Przypomnienie (gdy zostało ≤ `lead_days` dni, pozycja nie odłożona i bez dokupienia):
  - Dzwonek: `live:zakupy:<id>` (qbot_notif.sync_live → `qbot_zakupy_api.notif_items`), przycisk „Kup ponownie”;
    w Ustawieniach powiadomień źródło „Zakupy → Kończy się zapas”.
  - Telegram: linia „🛒 Kończy się: …” w PORANNEJ wiadomości (qbot_trener_notify, jak suplementy) + przyciski
    „Kup ponownie” (`zk:r:<id>`) i „+7 dni” (`zk:z:<id>`), obsługa w telegram_reply_processor → `handle_callback`;
    po kliknięciu znika tylko wiersz tej pozycji. Bez osobnej wiadomości.
- „Kup ponownie” = kopia na listę Do kupienia (priorytet Pilne, `refill_of`), idempotentnie; oryginał przestaje przypominać.
  Usunięcie kopii = oryginał znów przypomina. Zakup kopii: otwarcie = przewidywany koniec poprzedniego opakowania
  (jeśli później niż data zakupu).
- Testy: `tests/test_zakupy.py` (9). Żywo sprawdzone: okno, pasek zapasu, Dzwonek, linia poranna, Kup ponownie.
