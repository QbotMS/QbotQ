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
2. Zużycie i przypomnienia. UWAGA: suplementy — powiązać z modułem `qbot_supplements.py` (qbot_v2.supplement / supplement_log = rzeczywiste przyjęcia i dawki), zamiast liczyć z „dziennego zużycia” wpisanego ręcznie. Dla rzeczy spoza modułu suplementów (np. zatyczki) — opakowanie + zużycie dzienne.
3. Najniższa cena.
4. Gmail.

## Warstwy
- DANE: `garage.db`, tabela `shop_items` (tworzona przez `qbot_zakupy_api.py`, IF NOT EXISTS).
- API: `qbot_zakupy_api.py` → `/api/zakupy/list|save|bought|unbought|delete` (zapisy tylko właściciel; demo = odczyt). Montaż w `qbot_web.py` przed `app.mount("/")`.
- FRONT (poza repo, żywe od razu): `garaz-zakupy.js` (samodzielna zakładka jak `garaz-notatki.js`), znaczniki i style w `garaz.html`, pole szukania w `garaz-search.js` (MAP `tabZakupy`).
- Miniatura: przy zapisie z `image_url` serwer robi JPEG 320 px (data URI w `thumb`) — lista nie zależy od hotlinków sklepu.
- Testy: `tests/test_zakupy.py` (tymczasowa baza).
