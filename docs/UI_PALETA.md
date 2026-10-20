# UI — paleta kolorów serwisu (obowiązuje od 2026-10-14)

**Reguła (decyzja Michała 14.10.2026): każda nowa i każda przerabiana strona używa palety UI2.** Stara paleta `theme.css`
(zielono-złota) jest wycofywana — nie podłączaj jej do nowych stron.

- **Jedno źródło kolorów:** `web/public/ui2-tokens.css` — zmienne jasnego (`:root`) i ciemnego (`html.theme-dark`) motywu:
  tło `--bg`, karty `--card`, `--well`, tekst `--ink/--ink2/--muted`, linie `--line/--line2`, akcent `--accent/--accent-ink/--accent-bg`,
  stany `--good/--warn/--bad (+ -bg)`, barwy danych `--blue/--purple/--amber/--green`.
- `ui2.css` = tokeny (import `ui2-tokens.css`) + komponenty (karty, pill, siatki). Strony z własnym układem (mapy: Pogoda) podłączają
  **tylko** `ui2-tokens.css`, żeby klasy ui2 (`.seg`, `.legend`, `.bar`…) nie zderzały się z ich klasami.
- **Bez kolorów na sztywno w kodzie stron.** Kolory danych (serie wykresów, paski) jako zmienne strony wyprowadzone z tokenów
  (np. Pogoda: `--d-blue`, `--d-model`, wersja `html.theme-dark` dla jaśniejszych odcieni); w JS przez `css("--nazwa")`.
- Wyjątki: standardowe skale danych (radar dBZ, mapa szansy opadu) — rozpoznawalne, nie zmieniamy pod paletę.
- Mapy PNG generowane na serwerze (np. ocena weekendu) używają barw z tokenów ui2 (wartości z komentarzem w kodzie).
- Strony na UI2: Forma (`forma.html`, `ui2.css`), Pogoda (`pogoda.html`, `ui2-tokens.css`, od 14.10.2026).


## Szerokosc stron (20.10.2026, szer-2010)
`.wrap` w ui2.css: max-width 2000 px, boczny margines clamp(28px,3vw,56px) (bylo 1500 px / 32 px; Start index.html bylo 1426 px). Decyzja Michala po stronie testowej Formy: wykorzystac szerokosc, ale zostawic minimalny margines, zeby strona nie byla duszna. Raport jazdy, Analiza trasy, Garaz -- pelna szerokosc jak dotad.
