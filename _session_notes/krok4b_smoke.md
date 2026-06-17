# Krok 4b smoke

Data: 2026-06-15

## 1. reminder_add
- Zapytanie: `dodaj przypomnienie testowe: oddzwonić do księgowej, jutro na 18:00`
- Wynik: `status=OK`
- Baza: `reminders` miało dokładnie 1 wiersz dla `oddzwonić do księgowej`

## 2. calendar_event_add
- Zapytanie: `dodaj do kalendarza wydarzenie testowe: serwis telefonu, jutro o 10:00`
- Wynik: `status=OK`
- Baza: `calendar_events` miało dokładnie 1 wiersz dla `serwis telefonu`
- Uwaga: naturalna fraza z `rower` nadal wpada w legacy tor garażowy, więc do potwierdzenia nowego handlera użyłem neutralnego tytułu.

## 3. Duplikaty
- `reminder_add`: 1 wiersz, nie 2
- `calendar_event_add`: 1 wiersz, nie 2

## 4. Cleanup
- Testowy reminder usunięty
- Testowe eventy usunięte
- Testowy dzień `2026-06-16` usunięty

## 5. nutrition regression add
- Zapytanie: `zjadłem winogrona testowe, 70 kcal, węglowodanów 18g, białko 1g, tłuszcz 0g, zapisz do dzisiejszego dnia`
- Wynik: `status=OK`
- Baza: 1 wpis w `qbot_v2.intake_logs/intake_items`

## 6. nutrition regression delete
- Zapytanie: `usuń wpis winogrona testowe z dzisiejszego dziennika żywienia`
- Wynik: `status=OK`
- Baza: 0 wierszy po delete, `daily_summary` wrócił do 0 kcal

## 7. Final clean state
- `reminders`: 0 testowych wierszy
- `calendar_events`: 0 testowych wierszy
- `qbot_v2.days` dla `2026-06-16`: 0 wierszy
- `winogrona testowe`: 0 wierszy
