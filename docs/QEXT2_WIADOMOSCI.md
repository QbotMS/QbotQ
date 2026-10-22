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

- Tylko ważne wiadomości: Polska + świat. Bez plotek, celebrytów, clickbaitów, „szokujących” tytułów.
- **Aktualność najważniejsza**: QBot odpytuje kanały RSS **co 2 min** (zapytania warunkowe ETag / If-Modified-Since —
  praktycznie nasłuch; RSS sam nie wysyła powiadomień).
- **Jedno źródło wystarczy** — bez czekania na drugą redakcję; o tym, co przechodzi, decyduje wyłącznie ocena AI.
- **Bez dziennego limitu**: na Karoo idzie wszystko, co przejdzie filtr QBota, w rytmie publikacji RSS.
  Jedynym pokrętłem jest próg ważności AI (start ≥ 4 z 5).
- **Tylko wiadomości opublikowane w trakcie jazdy** (po starcie jazdy z Karoo). Wcześniejsze w ogóle nie trafiają na Karoo.
  Brak „wygasania po X h” — niepotrzebne.
- **Raz pokazana nie wraca** — także gdy tę samą wiadomość podadzą kolejne źródła (QBot grupuje duble i pamięta, co wysłał w tej jeździe).
- Pokazywać **także w jeździe** (nie tylko na postoju) i **z trasą oraz bez trasy** — gdy pasek jest pusty.
- Oznaczenie: **flaga Polski** dla Polski, **ikonka kuli ziemskiej** dla świata (ikony rysuje QExt2, QBot wysyła znacznik).
- **Strona podglądu w QBot SETUP > QExt2** (co zebrano, ocena AI, skrót, co poszło na Karoo, co odpadło i dlaczego).
- Zmiany pól QExt2 ogląda najpierw w symulatorze QBota (Garaż → QExt2 → Zmiany projektowane), bez buildów testowych.
- Bez dodatkowego szumu w Telegramie — wiadomości tylko na Karoo.

## Źródła — sprawdzone z serwera QBota 22.10.2026 (scripts/_tmp_rss_check.py)

Działają (RSS poprawny, aktualny):
- Polsat News: `https://www.polsatnews.pl/rss/polska.xml`, `https://www.polsatnews.pl/rss/swiat.xml`
- RMF24: `https://www.rmf24.pl/fakty/polska/feed`, `https://www.rmf24.pl/fakty/swiat/feed`
- Interia Fakty: `https://fakty.interia.pl/feed`
- Deutsche Welle po polsku: `https://rss.dw.com/xml/rss-pol-all`
- Euronews po polsku: `https://pl.euronews.com/rss`
- BBC World (EN, AI tłumaczy skrót): `https://feeds.bbci.co.uk/news/world/rss.xml`
- Bankier (gospodarka, rzadki): `https://www.bankier.pl/rss/wiadomosci.xml`

Nie działają z serwera: TVN24 (403 — blokuje serwer), PAP i Polskie Radio 24 (zepsuty XML), Rzeczpospolita (403), TVP Info (404).
Wykluczone z zasady: Gazeta.pl i portale plotkarskie.

## Odsiewanie — po stronie QBota

1. **Pobranie** kanałów co 2 min (warunkowo), zapis nagłówków do bazy (tytuł, źródło, link, data publikacji, czas pobrania).
2. **Grupowanie dubli** tej samej wiadomości z różnych źródeł (podobieństwo tytułów) — tylko po to, żeby nie wysłać jej drugi raz.
3. **Ocena ważności AI** (1–5) dla każdej nowej grupy, istniejącym w QBocie dostawcą LLM (bez nowego dostawcy):
   przechodzą m.in. wojna i bezpieczeństwo, katastrofy, ważne decyzje rządu/Sejmu/UE, gospodarka (stopy, kursy przy dużych
   zmianach), zdrowie publiczne; odpadają celebryci, sport (chyba że wyjątkowe), ciekawostki, kryminał lokalny, tytuły-przynęty.
   Do paska tylko ocena ≥ próg (start 4). AI przypisuje też kategorię: `pl` albo `world`.
4. **Skrót do paska**: AI robi wersję ≤ 32 znaki, po polsku, bez emocji, sam fakt.
5. **Podgląd w SETUP > QExt2**: lista nagłówków, grupy, ocena AI, skrót, co poszło na Karoo i kiedy, co odpadło i dlaczego.

Koszt AI: tylko nowe grupy (kilkadziesiąt–sto dziennie) — do policzenia w kroku 2.

## Jak trafia do QExt2 (kontrakt)

QExt2 **niczego nie ocenia ani nie skraca** — tylko wyświetla gotowe teksty z QBota.

### Kanał: odpowiedź na sygnał jazdy (bez nowego łącza)

Sprawdzone 22.10 w `qbot_karoo_live.py`: QExt2 w trakcie jazdy co ~5 min wysyła sygnał pozycji
(`mcp_server.py` POST `/ride-readiness` z `{"ping": {lat, lon}}`, `_qext2_ping`). Pierwszy sygnał = start jazdy
(`karoo_live.started_at`), 15 min ciszy = koniec. Odpowiedź już niesie ostrzeżenie o deszczu (`rain`).
Wiadomości dokładamy do **tej samej odpowiedzi** jako pole `news` — zero dodatkowych połączeń (bateria Karoo),
opóźnienie od publikacji do Karoo ok. 2–7 min.

(Teksty w przykładzie są zmyślone — tylko ilustracja formatu.)

```json
"news": [
  {"id": "n20261022-0007", "cat": "pl",    "text": "Sejm uchwalił budżet na 2027", "importance": 5, "published": "14:02"},
  {"id": "n20261022-0009", "cat": "world", "text": "Szczyt UE: porozumienie ws. energii", "importance": 4, "published": "14:05"}
]
```

- `cat` — `pl` (QExt2 rysuje flagę Polski) albo `world` (ikonka kuli ziemskiej). `text` → `RouteMsg.accent`.
- `text` ≤ 32 znaki (QBot pilnuje; QExt2 i tak ma skracanie „…” w `drawMsg` jako bezpiecznik).
- Tylko wpisy opublikowane po `started_at` bieżącej jazdy i jeszcze **niewysłane w tej jeździe**; QBot oznacza je jako wysłane
  w chwili odpowiedzi. Kolejność = priorytet (najważniejsze pierwsze). Brak pola / pusta lista = nic nie pokazuj.

### Zasady po stronie QExt2

- Nowy rodzaj komunikatu `MsgKind.NEWS`, **najniższy priorytet**: pokazywany tylko, gdy lista komunikatów jest pusta
  (żadnego ostrzeżenia), z trasą i bez trasy, także w jeździe. Każde ostrzeżenie natychmiast go zastępuje.
- Każdy wpis pokazany raz (ok. 10 s), potem następny w kolejce lub pusto; nie wraca.
- Ustawienie w QBot SETUP > QExt2 (`qext2_config.MESSAGES`, `cfgId = "news"`): wł./wył., kolejność, poziom (info = ciemne tło).

### Gdzie to wpiąć w kodzie

- QBot: nowy moduł `qbot_news.py` (pobieranie, zapis, grupowanie, ocena AI, skrót), wątek/timer co 2 min;
  pole `news` w odpowiedzi `_qext2_ping` (`mcp_server.py`) obok `rain`; `qext2_config.py` — wpis `news` w MESSAGES;
  podgląd w SETUP > QExt2 (qbot_web.py + strona SETUP).
- QExt2: odczyt pola `news` z odpowiedzi sygnału jazdy; komunikat w `kokpit/RouteMessageEngine.kt` (lista `out`);
  ikony flagi i kuli w rysowaniu paska. Wspólna kolejka `active/ActiveMessageHub` zostaje (używa jej KOKPIT).
- Symulator QBota: przykładowe wiadomości w `qext2-sim/projekt/qext2-makieta.js` (MSG `news`) + wariant „wiadomości: wł./wył.”.

## Plan sesji

1. ~~Weryfikacja źródeł RSS~~ — zrobione 22.10.2026 (sesja news-2210).
2. QBot: pobieranie co 2 min + zapis + grupowanie dubli + ocena AI + skrót; pole `news` w odpowiedzi sygnału jazdy.
3. QBot: podgląd w SETUP > QExt2 — najpierw makieta do akceptacji Michała.
4. Symulator: komunikat NEWS z flagą / kulą w KOKPIT (Zmiany projektowane), akceptacja.
5. QExt2: odczyt `news` + `MsgKind.NEWS` + ikony + ustawienie w SETUP — jeden build.
6. Wiki: hasło `qext2/wiadomosci` + aktualizacja `qext2/komunikaty`; TODO → ZROBIONE.
