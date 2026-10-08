# QBot — ekran SETUP

_Utworzono 2026-10-08. Żywy system wygrywa — weryfikuj na kodzie._

Strona `/setup.html` (poza repo, kopia w web_public/). Wejście: zębatka w stopce menu, nad przełącznikiem dzień/noc (`nav.js`).
Zakładki: `<button data-t>` w `#tabs` + `<section data-p>`; podzakładki `.st-sub` z `<button data-s>` i ramkami `iframe[data-s]`
(ładowane przy pierwszym otwarciu, wysokość = treść). Adres `#zakladka` albo `#zakladka-podzakladka` otwiera wprost.

- **Powiadomienia** — które rodzaje pokazuje dzwonek. Szczegóły: `docs/NOTIF_CENTER.md` (sekcja SETUP).
- **Trening** — Dostępność | Sezony | Ustawienia Trenera: ramki `trener-fragment.html?sub=dostep|sezon_ust|kalib`
  (ten sam trener.js, zapisy jak wcześniej). `sezon_ust` = tylko „Ustawienia sezonów” + „Zasady budowania sezonu”;
  w Treningu → Sezon zostaje wykres + plany objętości + odnośnik do SETUP. Trening nie ma już Dostępności ani Ustawień;
  stare `/trening.html#dostep|#kalib` przekierowują do `/setup.html#trening-dostep|kalib`.
- **Połączenia** — Strava | Komoot | Hammerhead/Karoo: ramki starych stron (`/strava.html`, `/komoot-dostep`, `/hammerhead-dostep`);
  stare adresy dalej działają. `nav.js` w ramce nie rysuje menu (klasa `html.qframe`).
- **Dostępy** — dawna kłódka z menu (prośby o dostęp demo przez QR z kodem, aktywne sesje, Zakończ, Wyloguj) osadzona w stronie:
  `nav.js window.qLockMount(el)`; okno `qLockOpen()` zostaje w kodzie. Link z Telegrama `?klodka=1` (dowolna strona) → `/setup.html#dostepy`.
- **Kontakty** — grupy adresów do zaproszeń/wysyłek planu: lista, nowa grupa, usuń grupę (z potwierdzeniem), dodaj/usuń adres,
  „odśwież” dla grup z wyprawy (RSVP). API bez zmian: `/api/mail-groups*`.

## Wyloguj (prawy górny róg)
Właściciel (`/auth/demo/whoami` kind=owner) dostaje przycisk wylogowania (`#qlogout`, z potwierdzeniem, POST `/auth/logout` → `/login`):
obok przycisku dzień/noc, gdy ten stoi w prawym górnym rogu (Forma, Trening, Garaż, Setup); na telefonie pozostałych stron —
w górnym pasku wysuwanego menu (górny pasek ekranu zajmuje tam wybór trasy/jazdy i styl mapy); na komputerze — pływający w rogu.
Tryb demo ma własny pasek z Wyloguj.
