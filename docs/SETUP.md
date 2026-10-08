# QBot — ekran SETUP

_Utworzono 2026-10-08. Żywy system wygrywa — weryfikuj na kodzie._

- Strona `/setup.html` (poza repo, kopia w web_public/). Wejście: zębatka w stopce menu, nad przełącznikiem dzień/noc (`nav.js`, stopka).
- Zakładki (`<button data-t>` w `#tabs` + `<section data-p>`; adres `#nazwa` otwiera zakładkę):
  - **Powiadomienia** — które rodzaje pokazuje dzwonek. Szczegóły: `docs/NOTIF_CENTER.md` (sekcja SETUP).
  - **Trening** — Dostępność i Ustawienia Trenera (dawniej podzakładki Treningu „Dostępność” i „Ustawienia” = kalibracja).
    Podzakładki u góry (`.st-sub`): **Dostępność** | **Ustawienia Trenera** — jedna ramka naraz
    (`trener-fragment.html?sub=dostep` / `?sub=kalib`, ten sam kod trener.js, zapisy jak wcześniej), ładowana przy pierwszym
    otwarciu, wysokość = treść. Adres `#trening-dostep` / `#trening-kalib` otwiera podzakładkę wprost.
- Trening (`trener.js` SUBS, `trener-m.js` TABS): bez Dostępności i Ustawień. Stare linki `/trening.html#dostep|#kalib` przekierowują do `/setup.html#trening-dostep|kalib`.
