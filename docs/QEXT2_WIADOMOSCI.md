# QExt2 — ważne wiadomości (RSS) w pasku komunikatów KOKPIT

Spisane 22.10.2026 (sesja qext2proj-2210), decyzje doprecyzowane 22.10.2026 (sesja news-2210).
Status: **decyzje zebrane, źródła sprawdzone (krok 1 zrobiony), budowa QBota (krok 2) — następna**.
Najpierw budujemy i dopracowujemy w QBocie, dopiero potem w QExt2 (jeden build, po obejrzeniu w symulatorze).

## Po co

Przy jeździe **bez trasy** pasek komunikatów KOKPIT prawie milczy. Sprawdzone w kodzie QExt2 (`RouteMessageEngine.kt`):
bez trasy pokazywane są tylko ostrzeżenia (W′, deszcz/burza/śnieg, jedzenie, brak czujnika, komunikat centrali QBota);
nawierzchnia, podjazdy, zjazdy, punkty (woda/sklep) i zmrok (liczony od ETA) wymagają trasy. Gdy nic nie alarmuje — pusto.

Michał chce w tę ciszę **istotne wiadomości z Polski i ze świata** — tylko ważne rzeczy, nie „newsy” typu Gazeta.pl.

## Decyzje Michała (22.10.2026) — wiążące

- Tylko ważne wiadomości. Bez plotek, celebrytów, clickbaitów, „szokujących” tytułów.
- **Aktualność najważniejsza**: QBot odpytuje kanały RSS **co 2 min** (zapytania warunkowe ETag / If-Modified-Since —
  praktycznie nasłuch; RSS sam nie wysyła powiadomień).
- **Jedno źródło wystarczy** — bez czekania na drugą redakcję; o tym, co przechodzi, decyduje ocena AI.
- **Bez dziennego limitu**: na Karoo idzie wszystko, co przejdzie filtr QBota, w rytmie publikacji RSS.
- **Tylko wiadomości opublikowane w trakcie jazdy** (po starcie jazdy z Karoo). Wcześniejsze w ogóle nie trafiają na Karoo.
- **Raz pokazana nie wraca** — także gdy tę samą wiadomość podadzą kolejne źródła (QBot grupuje duble i pamięta, co wysłał w tej jeździe).
- Pokazywać **także w jeździe** (nie tylko na postoju) i **z trasą oraz bez trasy** — gdy pasek jest pusty.
- Ikona przed tekstem: **flaga Polski** dla Polski, **kula ziemska** dla świata, **flaga kraju** dla źródeł lokalnych (np. Włochy).
- **Źródła konfigurowalne w SETUP** (dodawanie, ważność kanału, okres aktywności) — sekcja niżej.
- **Wszystko po polsku**: AI tłumaczy każdą wiadomość z obcego źródła na polski (język kanału wykrywany sam).
- **Strona podglądu w QBot SETUP > QExt2** (co zebrano, ocena AI, skrót, co poszło na Karoo, co odpadło i dlaczego).
- Zmiany pól QExt2 ogląda najpierw w symulatorze QBota (Garaż → QExt2 → Zmiany projektowane), bez buildów testowych.
- Bez dodatkowego szumu w Telegramie — wiadomości tylko na Karoo.

## Źródła w SETUP > QExt2 > Wiadomości

Lista źródeł trzymana w bazie QBota (nie w kodzie). Domyślnie wpisane kanały sprawdzone niżej. Każde źródło ma:

- **nazwa** i **adres RSS**. Po dodaniu QBot od razu sprawdza kanał i pokazuje: działa / nie działa + 2 ostatnie nagłówki.
- **ikona**: `pl` (flaga Polski), `world` (kula ziemska) albo kod kraju ISO (np. `it` = flaga Włoch).
- **język** — wykrywany automatycznie; skrót zawsze po polsku (tłumaczenie robi AI w tym samym kroku co ocena i skrót).
- **ważność kanału** — przesuwa próg oceny AI dla tego kanału:
  - wysoka → przechodzi ocena ≥ 3,
  - normalna → ≥ 4,
  - niska → tylko 5,
  - wyłączony → kanał nie jest pobierany.
  Gdy kilka wiadomości czeka naraz, pierwsze idą te z ważniejszego kanału, potem wyższa ocena AI.
- **okres aktywności**: **stałe** albo **od–do** (daty). Poza okresem kanał nie jest pobierany.
  Przykład Sycylia: włoskie źródła `it`, ważność wysoka, od–do = daty wyjazdu; polskie na ten czas ważność niska.
  **Otwarte:** ważność polskich kanałów też z datami od–do (żeby po powrocie sama wróciła na normalną), czy przestawiana ręcznie.

## Źródła domyślne — sprawdzone z serwera QBota 22.10.2026 (scripts/_tmp_rss_check.py)

Działają (RSS poprawny, aktualny):
- Polsat News: `https://www.polsatnews.pl/rss/polska.xml` (pl), `https://www.polsatnews.pl/rss/swiat.xml` (world)
- RMF24: `https://www.rmf24.pl/fakty/polska/feed` (pl), `https://www.rmf24.pl/fakty/swiat/feed` (world)
- Interia Fakty: `https://fakty.interia.pl/feed` (pl/world — AI rozstrzyga)
- Deutsche Welle po polsku: `https://rss.dw.com/xml/rss-pol-all` (world)
- Euronews po polsku: `https://pl.euronews.com/rss` (world)
- BBC World (EN): `https://feeds.bbci.co.uk/news/world/rss.xml` (world)
- Bankier (gospodarka, rzadki): `https://www.bankier.pl/rss/wiadomosci.xml` (pl)

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
4. **Próg** = zależny od ważności kanału (3/4/5).
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

- Nowy rodzaj komunikatu `MsgKind.NEWS`, **najniższy priorytet**: pokazywany tylko, gdy lista komunikatów jest pusta
  (żadnego ostrzeżenia), z trasą i bez trasy, także w jeździe. Każde ostrzeżenie natychmiast go zastępuje.
- Każdy wpis pokazany raz (ok. 10 s), potem następny w kolejce lub pusto; nie wraca.
- Flagi: zestaw rysowanych ikon (pl, kula + najczęstsze kraje wyjazdowe); brak flagi danego kraju → kula.
- Ustawienie w QBot SETUP > QExt2 (`qext2_config.MESSAGES`, `cfgId = "news"`): wł./wył., kolejność, poziom (info = ciemne tło).

### Gdzie to wpiąć w kodzie

- QBot: nowy moduł `qbot_news.py` (pobieranie, zapis, grupowanie, AI: ocena + tłumaczenie + skrót), wątek/timer co 2 min;
  tabele `qbot_v2.news_source` (źródła z SETUP), `qbot_v2.news_item`, `qbot_v2.news_sent` (co wysłane w której jeździe);
  pole `news` w odpowiedzi `_qext2_ping` (`mcp_server.py`) obok `rain`; `qext2_config.py` — wpis `news` w MESSAGES;
  SETUP > QExt2 > Wiadomości: lista źródeł + podgląd (qbot_web.py + strona SETUP).
- QExt2: odczyt pola `news` z odpowiedzi sygnału jazdy; komunikat w `kokpit/RouteMessageEngine.kt` (lista `out`);
  ikony flag i kuli w rysowaniu paska. Wspólna kolejka `active/ActiveMessageHub` zostaje (używa jej KOKPIT).
- Symulator QBota: przykładowe wiadomości w `qext2-sim/projekt/qext2-makieta.js` (MSG `news`) + wariant „wiadomości: wł./wył.”.

## Plan sesji

1. ~~Weryfikacja źródeł RSS~~ — zrobione 22.10.2026 (sesja news-2210).
2. QBot: tabele + pobieranie co 2 min + grupowanie dubli + AI (ocena, tłumaczenie, skrót) + progi wg ważności kanału;
   pole `news` w odpowiedzi sygnału jazdy.
3. QBot: SETUP > QExt2 > Wiadomości (źródła + podgląd) — najpierw makieta do akceptacji Michała.
4. Symulator: komunikat NEWS z flagą / kulą w KOKPIT (Zmiany projektowane), akceptacja.
5. QExt2: odczyt `news` + `MsgKind.NEWS` + ikony + ustawienie w SETUP — jeden build.
6. Wiki: hasło `qext2/wiadomosci` + aktualizacja `qext2/komunikaty`; TODO → ZROBIONE.
