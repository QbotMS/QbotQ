# Suplementy i leki (2026-10-13)

Decyzje Michala: potwierdzanie RANO za dzien poprzedni, jednym przyciskiem "Wszystkie" w porannej wiadomosci 7:00; wyjatki
poprawia recznie w Zdrowie > Suplementy; bez passy - tylko statystyka regularnosci. Dzien liczy sie po kliknieciu (nic automatycznie).

## Dane (sql/supl_v1.sql)
- `qbot_v2.supplement`: nazwa, rodzaj (suplement / lek), pora (rano / wieczor / przed_snem / dowolnie), dni tygodnia (NULL = codziennie,
  0 = pn), aktywny / wstrzymany, usuniety (miekko - historia zostaje), kolejnosc.
- `qbot_v2.supplement_dose`: wersje dawki od `valid_from` (zmiana dawki = nowa wersja; wczesniejsze dni zostaja ze stara).
- `qbot_v2.supplement_log`: dzien, pozycja, wziete / pominiete, faktyczna dawka, zrodlo (telegram / web).
- Start 13.10.2026: Magnez 100 mg (w ciagu dnia), Witamina D3 4000 j.m. (w ciagu dnia), Melatonina 1 mg (przed snem).

## Przeplyw
- Poranna wiadomosc 7:00 (qbot_trener_notify): linia "💊 Wczoraj (DD.MM): ..." + przycisk "💊 Wczoraj wszystkie wziete"
  (`tr:supl:RRRRMMDD`) - tylko gdy cos zaplanowane i niepotwierdzone. Klik -> `confirm_all` (nie nadpisuje recznych wpisow),
  pozostale przyciski wiadomosci zostaja. W fazie "totalny luz" poranna wiadomosc nie wychodzi - wtedy tylko strona.
- Strona Zdrowie > Suplementy (`zdrowie-supl.js`): lista (dodaj / edytuj z dawka "od dnia" / wstrzymaj / usun), regularnosc 35 dni,
  kalendarz przyjec (klik kratki: wziete -> pominiete -> niepotwierdzone; klik daty: wszystkie wziete tego dnia; dzis pomijany).
- Raport dla lekarza (Serce): "Leki i suplementy" wypelniane automatycznie (`report_lines`), AI dostaje liste w faktach.
- API: `GET /api/supl`, `POST /api/supl`, `PUT|DELETE /api/supl/{id}`, `POST /api/supl/log` (zapis tylko wlasciciel).

## Pomysly na pozniej
- Melatonina a sen/HRV (dni z i bez) po kilku tygodniach danych; witamina D - przy badaniach krwi oznaczyc 25(OH)D.
- Albert: narzedzie do odczytu listy (wymaga aktualizacji promptu w tym samym commicie).
