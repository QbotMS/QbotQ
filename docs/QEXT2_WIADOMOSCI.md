# QExt2 — ważne wiadomości (RSS) w pasku komunikatów KOKPIT

Spisane 22.10.2026 (sesja qext2proj-2210), decyzje doprecyzowane 22.10.2026 (sesja news-2210).
Status: **QBot NA PRODUKCJI 22.10.2026 (kroki 1-3: pobieranie, AI, pole `news`, SETUP > QExt2 > Wiadomosci https://albert.cytr.us/setup.html#qext2-news). Zostaje krok 4-5 — QExt2 w osobnej sesji QExt2.**
Najpierw budujemy i dopracowujemy w QBocie, dopiero potem w QExt2 (jeden build, po obejrzeniu w symulatorze).

## Po co

Przy jeździe **bez trasy** pasek komunikatów KOKPIT prawie milczy. Sprawdzone w kodzie QExt2 (`RouteMessageEngine.kt`):
bez trasy pokazywane są tylko ostrzeżenia (W′, deszcz/burza/śnieg, jedzenie, brak czujnika, komunikat centrali QBota);
nawierzchnia, podjazdy, zjazdy, punkty (woda/sklep) i zmrok (liczony od ETA) wymagają trasy. Gdy nic nie alarmuje — pusto.

Michał chce w tę ciszę **istotne wiadomości z Polski i ze świata** — tylko ważne rzeczy, nie „newsy” typu Gazeta.pl.

## Decyzje Michała (22.10.2026) — wiążące

- Tylko ważne wiadomości. Bez plotek, celebrytów, clickbaitów, „szokujących” tytułów.
- **Kryterium ważności (22.10.2026, po przeglądzie pierwszych wyników):** „czy to zmienia moją sytuację albo wiedzę”.
  Tło (kolejne ataki w trwającej wojnie, katastrofy i pogoda za granicą, ewakuacje firm, epidemie poza Europą, gospodarka)
  — nie, nawet gdy poważne. Ocenę 4–5 mogą dostać tylko kategorie wybrane przez Michała:
  Polska — atak/zagrożenie dla Polski i alarmy RCB, duże decyzje państwa (rząd, Sejm, prezydent), wielkie wydarzenia
  (śmierć ważnej osoby, katastrofa w Polsce); świat — przełom (początek/koniec wojny, rozejm), atak na kraj NATO/UE,
  wydarzenie, o którym mówi cały świat (np. nowy papież); kultura i sport — rozstrzygnięcia głośnych spraw (np. nowy Bond).
  Portfel (stopy, kurs, paliwa) — Michał NIE wybrał.
  Dopisane z pierwszych ocen 👍 Michała (22.10): rozstrzygnięcie głośnej sprawy w Polsce (zatrzymanie „Jaszczura”),
  **bezpieczeństwo regionu** — groźby atomowe Rosji, szpieg zatrzymany u sąsiada, masowe protesty w kraju sąsiednim.
  Tytuł-pytanie na ważny temat nie odpada — AI przepisuje go na fakt („Zełenski o groźbie atomowej Putina”).
- **Formułowanie (poprawione 22.10 wg przykładów Michała):** KONKRET — kto (nazwisko, partia, instytucja) i co dokładnie
  zrobił: „Nowe zasady budowy tras rowerowych”, „PiS: wniosek o odwołanie Kierwińskiego”, „Sikorski rzucił wyzwanie
  Mentzenowi”. **Bez „Polska:”** — flaga już to mówi (bezpiecznik `clean_text` wycina przedrostek). Dla świata kraj na
  początku („Francja: powódź, 4 ofiary”), bo kula ziemska nie mówi, gdzie. Limit skrótu **40 znaków** (było 32 — za mało
  na nazwisko); czy 40 mieści się na pasku KOKPIT 2 dużą czcionką — do sprawdzenia w symulatorze (krok 4).
- **Legia.net (22.10.2026, prośba Michała):** `https://legia.net/rss`, ikona **⚽** (`icon = sport`, QExt2 musi ją narysować),
  ważność wysoka. Osobna miara `rodzaj = klub`: 4–5 = końcowy wynik meczu, zmiana trenera, potwierdzony ważny transfer,
  awans/odpadnięcie w pucharach, mistrzostwo, spadek, kara; 1–2 = zapowiedzi, wywiady, plotki, konkursy, bilety, kibice,
  młodzież, felietony. Skrót: „Legia – Lech 2:1”, „Legia: nowy trener X Y”.
- **Wiadomości lokalne Warszawa (22.10.2026, prośba Michała):** RMF24 · Warszawa, Warszawa w Pigułce, Miejski Reporter,
  Google News · Warszawa (zbiera m.in. TVN Warszawa, który blokuje serwer). Ikona **📍** (`icon = local`, QExt2 musi ją
  narysować), ważność kanałów **wysoka** (próg 4 — lokalne rzadko podają 2 redakcje). **Osobna miara** dla `rodzaj = lokalne`:
  co zmienia jazdę po Warszawie — zamknięte ulice, mosty, ścieżki rowerowe, remonty i objazdy, blokady miasta (demonstracje,
  maratony, wizyty), poważne zdarzenia z zagrożeniem (pożar, ewakuacja, obława), alerty pogodowe i smogowe, nowe trasy
  rowerowe, Veturilo, ważne decyzje miasta. Odpadają kultura, gastronomia, drobny kryminał, ciekawostki.
  Nie działają z serwera: TVN Warszawa (403), UM Warszawa (403), ZDM (brak RSS), Halo Warszawa i Wawalove (certyfikat).
- **Kanały rowerowe (22.10.2026, wybór Michała):** Gravel Cyclist, Bikerumor, Bikepacking.com, The Radavist, BikeRadar
  (przez Google News — własny RSS 404), Cyclingnews, Escape Collective. Ikona **🚲** (`icon = bike`, QExt2 musi ją narysować).
  **Osobna miara AI** dla `rodzaj = rower`: 4–5 = premiera nowego roweru gravel znanej marki, nowa grupa osprzętu
  (SRAM, Shimano, Campagnolo), nowy licznik Hammerhead/Garmin/Wahoo, nowy sprzęt do bikepackingu; 1–2 = recenzje, testy,
  poradniki, listy prezentowe, filmy, relacje z wypraw, wyścigi, treści sponsorowane. Skrót: marka + model + co nowego
  („Garmin Edge 1060: sterowanie głosem”). Premia 2 redakcji działa tu naturalnie — premiery podaje kilka serwisów naraz.
  Polskie serwisy rowerowe (RowerTour, Bikeboard, Szosa.org, BikeWorld) nie mają działającego RSS z serwera; road.cc 410.
- **Rower (kategoria i, 22.10):** sprawy rowerzystów w Polsce — przepisy, budowa i zasady tras, zmiany w ruchu dla rowerów,
  także projekty i konsultacje (Michał: „potrzebuję” wiadomości o nowych zasadach budowy tras).
- **Nauka na ocenach Michała:** w podglądzie przy każdej wiadomości 👍 ważne / 👎 nieważne; 40 ostatnich ocen idzie do
  instrukcji AI jako przykłady jego miary (`user_vote`, `examples`, POST /api/setup/qext2/news/vote). Pierwsze 6 ocen
  (wszystkie „nieważne”) wpisane z rozmowy 22.10: atak na Kijów, Łozowa, Aramco, Ebola, powodzie we Francji, 9 ofiar na Ukrainie.
- **Tylko fakty dokonane, zero przynęt** (22.10.2026): „Kto zostanie nowym Bondem? Zostało trzech kandydatów” — nie;
  „X Y został nowym Bondem” — tak. Skrót = zdanie oznajmujące *kto/co → co się stało*, nigdy pytanie. Rozstrzygnięcie
  głośnej sprawy (także kultura, sport) może przejść. Bezpiecznik w kodzie: skrót z „?” albo zaczynający się od
  kto/co/czy/dlaczego/jak/ile nie idzie na Karoo (`is_fact`).
- **Aktualność najważniejsza**: QBot odpytuje kanały RSS **co 2 min** (zapytania warunkowe ETag / If-Modified-Since —
  praktycznie nasłuch; RSS sam nie wysyła powiadomień).
- **Jedno źródło wystarczy** — bez czekania na drugą redakcję; o tym, co przechodzi, decyduje ocena AI.
- **Bez dziennego limitu**: na Karoo idzie wszystko, co przejdzie filtr QBota, w rytmie publikacji RSS.
- **Tylko wiadomości opublikowane w trakcie jazdy** (po starcie jazdy z Karoo). Wcześniejsze w ogóle nie trafiają na Karoo.
- **Raz pokazana nie wraca** — także gdy tę samą wiadomość podadzą kolejne źródła (QBot grupuje duble i pamięta, co wysłał w tej jeździe).
- Pokazywać **także w jeździe** (nie tylko na postoju) i **z trasą oraz bez trasy** — gdy pasek jest pusty.
- Ikona przed tekstem: **flaga Polski** dla Polski, **kula ziemska** dla świata, **flaga kraju** dla źródeł lokalnych (np. Włochy).
- **Źródła konfigurowalne w SETUP** (dodawanie, ważność kanału, okres aktywności, ważność czasowa) — sekcja niżej.
- **Wszystko po polsku**: AI tłumaczy każdą wiadomość z obcego źródła na polski (język kanału wykrywany sam).
- **Strona podglądu w QBot SETUP > QExt2** (co zebrano, ocena AI, skrót, co poszło na Karoo, co odpadło i dlaczego).
- Zmiany pól QExt2 ogląda najpierw w symulatorze QBota (Garaż → QExt2 → Zmiany projektowane), bez buildów testowych.
- Bez dodatkowego szumu w Telegramie — wiadomości tylko na Karoo.

## Źródła w SETUP > QExt2 > Wiadomości

Lista źródeł trzymana w bazie QBota (nie w kodzie). Domyślnie wpisane kanały sprawdzone niżej. Każde źródło ma:

- **nazwa** i **adres RSS**. Po dodaniu QBot od razu sprawdza kanał i pokazuje: działa / nie działa + 2 ostatnie nagłówki.
- **ikona**: `pl` (flaga Polski), `world` (kula ziemska) albo kod kraju ISO (np. `it` = flaga Włoch).
- **język** — wykrywany automatycznie; skrót zawsze po polsku (tłumaczenie robi AI w tym samym kroku co ocena i skrót).
- **ważność kanału** (zwykła) — przesuwa próg oceny AI dla tego kanału:
  - wysoka → przechodzi ocena ≥ 4 (3 z premią),
  - normalna → tylko 5 (4 z premią),
  - niska → tylko 5 (bez premii),
  (22.10.2026, akceptacja Michała: start surowszy niż pierwotne 3/4/5 — w 2 h przechodziło 10 wiadomości.)
  **Premia 2 redakcji:** ocena o 1 niższa od progu przechodzi, gdy tę samą wiadomość podadzą co najmniej 2 różne
  redakcje (Polsat PL i Polsat Świat = jedna). Wiadomości nad progiem idą od razu, bez czekania. Czeka najwyżej 6 h.
  - wyłączony → kanał nie jest pobierany.
  Gdy kilka wiadomości czeka naraz, pierwsze idą te z ważniejszego kanału, potem wyższa ocena AI.
- **ważność czasowa** (opcjonalna, decyzja 22.10.2026) — inna ważność w okresie od–do (np. niska od 01.05 do 14.05).
  Poza tym okresem kanał sam wraca do ważności zwykłej — nic nie trzeba przestawiać po powrocie. Można dodać kilka okresów.
- **okres aktywności**: **stałe** albo **od–do** (daty). Poza okresem kanał nie jest pobierany.

Przykład Sycylia: włoskie źródła `it`, ważność wysoka, aktywne od–do = daty wyjazdu; polskie kanały: ważność czasowa
niska w te same daty. Po powrocie włoskie same się wyłączają, polskie same wracają na normalną.

## Źródła domyślne — sprawdzone z serwera QBota 22.10.2026 (scripts/_tmp_rss_check.py)

Działają (RSS poprawny, aktualny):
- Polsat News: `https://www.polsatnews.pl/rss/polska.xml` (pl), `https://www.polsatnews.pl/rss/swiat.xml` (world)
- RMF24: `https://www.rmf24.pl/fakty/polska/feed` (pl), `https://www.rmf24.pl/fakty/swiat/feed` (world)
- Interia Fakty: `https://fakty.interia.pl/feed` (pl/world — AI rozstrzyga)
- Deutsche Welle po polsku: `https://rss.dw.com/xml/rss-pol-all` (world)
- Euronews po polsku: `https://pl.euronews.com/rss` (world)
- BBC World (EN): `https://feeds.bbci.co.uk/news/world/rss.xml` (world)
- Reuters przez Google News (EN, agencyjny, Reuters nie ma już publicznego RSS): `https://news.google.com/rss/search?q=when:24h+site:reuters.com&ceid=US:en&hl=en-US&gl=US` (world) — dodany 22.10.2026
- Bankier (gospodarka + świat): `https://www.bankier.pl/rss/wiadomosci.xml` (auto — mieszany, AI rozstrzyga)

Kanał mieszany (Interia) — ikonę `pl`/`world` wybiera AI na podstawie treści; kanały z ikoną kraju zawsze dostają flagę tego kraju.

Nie działają z serwera: TVN24 (403 — blokuje serwer), PAP i Polskie Radio 24 (zepsuty XML), Rzeczpospolita (403), TVP Info (404).
Wykluczone z zasady: Gazeta.pl i portale plotkarskie.

## Odsiewanie — po stronie QBota

1. **Pobranie** aktywnych kanałów co 2 min (warunkowo), zapis nagłówków do bazy (tytuł, opis, źródło, link, data publikacji, czas pobrania).
2. **Grupowanie dubli** tej samej wiadomości z różnych źródeł (także między językami) — tylko po to, żeby nie wysłać jej drugi raz.
3. **Jedno wywołanie AI na nową grupę** (istniejący w QBocie dostawca LLM, bez nowego): ocena ważności 1–5, kategoria
   (`pl`/`world` dla kanałów mieszanych), skrót ≤ 32 znaki **po polsku** (tłumaczenie), bez emocji, sam fakt.
   Przechodzą m.in. wojna i bezpieczeństwo, katastrofy, ważne decyzje rządu/parlamentu/UE, gospodarka (duże zmiany), zdrowie
   publiczne; dla źródeł lokalnych także to, co ważne dla kogoś, kto tam jedzie rowerem (strajki transportu, zamknięte drogi,
   pożary, erupcje, alerty pogodowe). Odpadają celebryci, sport (chyba że wyjątkowe), ciekawostki, kryminał lokalny, przynęty.
4. **Próg** = zależny od ważności kanału obowiązującej w chwili oceny (czasowa, jeśli trwa; inaczej zwykła) — 4/5/5,
   plus premia 2 redakcji (status `czeka` → `przeszlo` w `promote`).
5. **Podgląd w SETUP > QExt2**: lista nagłówków, grupy, ocena AI, skrót, co poszło na Karoo i kiedy, co odpadło i dlaczego.

Koszt AI: jedno wywołanie na nową grupę (kilkadziesiąt–sto dziennie) — do policzenia w kroku 2.

## Jak trafia do QExt2 (kontrakt)

QExt2 **niczego nie ocenia, nie tłumaczy ani nie skraca** — tylko wyświetla gotowe teksty z QBota.

### Kanał: odpowiedź na sygnał jazdy (bez nowego łącza)

Sprawdzone 22.10 w `qbot_karoo_live.py`: QExt2 w trakcie jazdy co ~5 min wysyła sygnał pozycji
(`mcp_server.py` POST `/ride-readiness` z `{"ping": {lat, lon}}`, `_qext2_ping`). Pierwszy sygnał = start jazdy
(`karoo_live.started_at`), 15 min ciszy = koniec. Odpowiedź już niesie ostrzeżenie o deszczu (`rain`).
Wiadomości dokładamy do **tej samej odpowiedzi** jako pole `news` — zero dodatkowych połączeń (bateria Karoo),
opóźnienie od publikacji do Karoo ok. 2–7 min.

(Teksty w przykładzie są zmyślone — tylko ilustracja formatu.)

```json
"news": [
  {"id": "n20261022-0007", "icon": "pl",    "text": "Sejm uchwalił budżet na 2027", "importance": 5, "published": "14:02"},
  {"id": "n20261022-0011", "icon": "it",    "text": "Strajk promów na Sycylię", "importance": 4, "published": "14:03"},
  {"id": "n20261022-0009", "icon": "world", "text": "Szczyt UE: porozumienie ws. energii", "importance": 4, "published": "14:05"}
]
```

- `icon` — `pl` (flaga Polski), `world` (kula ziemska) albo kod kraju ISO (flaga kraju). QExt2 rysuje ikonę; nieznany kod → kula.
- `text` → `RouteMsg.accent`, zawsze po polsku, ≤ 32 znaki (QBot pilnuje; QExt2 ma skracanie „…” w `drawMsg` jako bezpiecznik).
- Tylko wpisy opublikowane po `started_at` bieżącej jazdy i jeszcze **niewysłane w tej jeździe**; QBot oznacza je jako wysłane
  w chwili odpowiedzi. Kolejność = priorytet. Brak pola / pusta lista = nic nie pokazuj.

### Zasady po stronie QExt2

- Nowy rodzaj komunikatu `MsgKind.NEWS`. **Decyzja Michała 22.10.2026 (krok 4):** wiadomość **przerywa** komunikaty
  o podjazdach i nawierzchni (także dalekie, domyślne) oraz pusty pasek — wchodzi na **15 s faktycznie na ekranie**
  (Michał 22.10: min. 10 s; czas czekania za ostrzeżeniem się nie liczy), potem pasek wraca do nich.
  Pierwszeństwo przed wiadomością mają: W′, deszcz/burza/śnieg, jedzenie, zmrok, zjazd, punkty woda/sklep, centrala QBota —
  gdy któryś jest na liście, wiadomość czeka. Działa z trasą i bez trasy, także w jeździe.
- Każdy wpis pokazany raz (15 s na ekranie), potem następny w kolejce lub pusto; nie wraca.
- Flagi: zestaw rysowanych ikon (pl, kula + najczęstsze kraje wyjazdowe); brak flagi danego kraju → kula.
- Ustawienie w QBot SETUP > QExt2 (`qext2_config.MESSAGES`, `cfgId = "news"`): wł./wył., kolejność, poziom (info = ciemne tło).

### Gdzie to wpiąć w kodzie

- QBot: nowy moduł `qbot_news.py` (pobieranie, zapis, grupowanie, AI: ocena + tłumaczenie + skrót), wątek/timer co 2 min;
  tabele `qbot_v2.news_source` (źródła z SETUP: ważność zwykła, okres aktywności), `qbot_v2.news_source_period`
  (ważności czasowe od–do), `qbot_v2.news_item`, `qbot_v2.news_sent` (co wysłane w której jeździe);
  pole `news` w odpowiedzi `_qext2_ping` (`mcp_server.py`) obok `rain`; `qext2_config.py` — wpis `news` w MESSAGES;
  SETUP > QExt2 > Wiadomości: lista źródeł + podgląd (qbot_web.py + strona SETUP).
- QExt2: odczyt pola `news` z odpowiedzi sygnału jazdy; komunikat w `kokpit/RouteMessageEngine.kt` (lista `out`);
  ikony flag i kuli w rysowaniu paska. Wspólna kolejka `active/ActiveMessageHub` zostaje (używa jej KOKPIT).
- Symulator QBota: przykładowe wiadomości w `qext2-sim/projekt/qext2-makieta.js` (MSG `news`) + wariant „wiadomości: wł./wył.”.

## Plan sesji

1. ~~Weryfikacja źródeł RSS~~ — zrobione 22.10.2026 (sesja news-2210).
2. ~~QBot: tabele + pobieranie co 2 min + grupowanie dubli + AI (ocena, tłumaczenie, skrót) + progi wg ważności kanału
   (zwykłej / czasowej); pole `news` w odpowiedzi sygnału jazdy~~ — zrobione 22.10.2026 (qbot_news.py). Szczegóły wdrożenia:
   AI ocenia tylko nagłówki z ostatnich 2 h; paczki po 20 w jednym wywołaniu; za długie skróty AI przepisuje krócej
   (shorten, 2 rundy, potem obcięcie); najwyżej 5 wpisów na sygnał jazdy; nagłówki kasowane po 14 dniach;
   test 22.10 (jazda testowa od 13:30, wycofana): sygnał 1 = 4 wiadomości, sygnał 2 i 3 = pusto (nie wracają).
3. QBot: SETUP > QExt2 > Wiadomości (źródła + podgląd) — najpierw makieta do akceptacji Michała.
4. Symulator: komunikat NEWS z flagą / kulą w KOKPIT (Zmiany projektowane), akceptacja.
5. QExt2: odczyt `news` + `MsgKind.NEWS` + ikony + ustawienie w SETUP — jeden build.
6. Wiki: hasło `qext2/wiadomosci` + aktualizacja `qext2/komunikaty`; TODO → ZROBIONE.
