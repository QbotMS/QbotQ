# QExt2 — ważne wiadomości (RSS) w pasku komunikatów KOKPIT

Pomysł do osobnej sesji. Spisane 22.10.2026 (sesja qext2proj-2210). Status: **pomysł, nic nie zbudowane**.
Najpierw budujemy i dopracowujemy w QBocie, dopiero potem w QExt2 (jeden build, po obejrzeniu w symulatorze).

## Po co

Przy jeździe **bez trasy** pasek komunikatów KOKPIT prawie milczy. Sprawdzone w kodzie QExt2 (`RouteMessageEngine.kt`):
bez trasy pokazywane są tylko ostrzeżenia (W′, deszcz/burza/śnieg, jedzenie, brak czujnika, komunikat centrali QBota);
nawierzchnia, podjazdy, zjazdy, punkty (woda/sklep) i zmrok (liczony od ETA) wymagają trasy. Gdy nic nie alarmuje — pusto.

Michał chce w tę ciszę **istotne wiadomości z Polski i ze świata** — tylko ważne rzeczy, nie „newsy” typu Gazeta.pl.

## Decyzje i wymagania Michała (22.10.2026)

- Tylko ważne wiadomości: Polska + świat. Bez plotek, celebrytów, clickbaitów, „szokujących” tytułów.
- Zbudować i dopracować w QBocie (podgląd na stronie), dopiero potem przenieść do QExt2.
- Zmiany pól QExt2 ogląda najpierw w symulatorze QBota (Garaż → QExt2 → Zmiany projektowane), bez buildów testowych.

## Źródła (kandydaci — do weryfikacji w sesji)

Potwierdzone 22.10.2026 (strony z listą kanałów):
- Polsat News: `https://www.polsatnews.pl/rss/polska.xml`, `https://www.polsatnews.pl/rss/swiat.xml`
- TVN24 kraj: `https://tvn24.pl/wiadomosci-z-kraju,3.xml`

Do sprawdzenia (czy kanał RSS istnieje i działa): PAP (pap.pl), Polskie Radio 24, Rzeczpospolita, BBC World, Reuters/AP (często bez publicznego RSS).
Zasada: kilka niezależnych źródeł (potrzebne do kroku „co najmniej 2 źródła” niżej). Gazeta.pl i portale plotkarskie — wykluczone.

## Odsiewanie (serce funkcji) — po stronie QBota

1. **Pobranie** kanałów co ~15 min (cron/wątek w QBocie), zapis nagłówków do bazy (tytuł, źródło, link, data).
2. **Grupowanie** tej samej wiadomości z różnych źródeł (podobieństwo tytułów; AI lub prosta miara). Wiadomość jest kandydatem,
   gdy podaje ją **co najmniej 2 niezależne źródła** (ważne rzeczy podają wszyscy, plotki zwykle jeden portal).
3. **Ocena ważności AI** (skala 1–5) z krótką instrukcją: przechodzą m.in. wojna i bezpieczeństwo, katastrofy, ważne decyzje
   rządu/Sejmu/UE, gospodarka (stopy, kursy przy dużych zmianach), zdrowie publiczne; odpadają celebryci, sport (chyba że wyjątkowe),
   ciekawostki, kryminał lokalny, tytuły-przynęty. Do paska tylko ocena ≥ 4 (próg do dopracowania).
4. **Skrót do paska**: AI robi wersję ≤ 32 znaki (cała treść w jednej linii dużą czcionką), po polsku, bez emocji, sam fakt.
5. **Limit**: najwyżej kilka wiadomości dziennie (start: 6/dzień), każda pokazywana 1–2 razy; stare wygasają (np. po 6 h).
6. **Podgląd w QBocie** (strona do dopracowania przez Michała): lista zebranych nagłówków, grupy, ocena AI, skrót, co poszło do paska
   i dlaczego odpadło — żeby dało się stroić progi bez Karoo.

Koszt: ocena AI tylko dla nowych grup (kilkadziesiąt dziennie) — pomijalny; policzyć w sesji.

## W jakiej formie trafia do QExt2 (kontrakt)

QExt2 **niczego nie ocenia ani nie skraca** — tylko wyświetla gotowe teksty z QBota i liczy, ile razy pokazał.

### Endpoint QBota

(Teksty w przykładzie są zmyślone — tylko ilustracja formatu.)

`GET /api/qext2/news` (Bearer jak pozostałe endpointy QExt2). QExt2 pobiera go razem z pogodą INFO (ten sam rytm ~15 min,
to samo `KarooSdkHttpCaller`) — **bez dodatkowego stałego łącza** (bateria Karoo). Odpowiedź:

```json
{
  "generated": "2026-10-22T14:05:00+02:00",
  "ttl_min": 15,
  "items": [
    {
      "id": "n20261022-0007",
      "lead": "PL:",
      "accent": "Sejm uchwalił budżet na 2027",
      "importance": 5,
      "show_max": 2,
      "expires": "2026-10-22T20:05:00+02:00"
    },
    {
      "id": "n20261022-0009",
      "lead": "ŚWIAT:",
      "accent": "Szczyt UE: porozumienie ws. energii",
      "importance": 4,
      "show_max": 1,
      "expires": "2026-10-22T19:30:00+02:00"
    }
  ]
}
```

- `lead` / `accent` — dokładnie pola komunikatu paska (`RouteMsg.lead` szary / `RouteMsg.accent` biały pogrubiony). `lead` = „PL:” albo „ŚWIAT:”.
- `accent` ≤ 32 znaki (QBot pilnuje; QExt2 i tak ma skracanie „…” w `drawMsg` jako bezpiecznik).
- Kolejność w `items` = priorytet (najważniejsze pierwsze). Puste `items` = nic nie pokazuj.
- `expires` — po tym czasie QExt2 nie pokazuje wpisu (ważne bez zasięgu: zostaje ostatnia lista, ale stare wygasają).

### Zasady po stronie QExt2

- Nowy rodzaj komunikatu `MsgKind.NEWS`, **najniższy priorytet**: pokazywany tylko, gdy lista komunikatów jest pusta
  (żadnego ostrzeżenia). Każde ostrzeżenie natychmiast go zastępuje.
- Działa z trasą i bez trasy (z trasą też, gdy pasek pusty) — do decyzji w sesji.
- Licznik pokazań per `id` w pamięci jazdy; po `show_max` wpis znika. Jeden wpis na ekranie ok. 10 s, potem pusto / następny.
- Ustawienie w QBot SETUP > QExt2 (`qext2_config.MESSAGES`, `cfgId = "news"`): wł./wył., kolejność, poziom (info = ciemne tło).
- Otwarte: tylko na postoju / przy małej prędkości, czy także w jeździe (Michał nie zdecydował).

### Gdzie to wpiąć w kodzie (rozpoznane 22.10)

- QBot: nowy moduł pobierania i oceny + endpoint w `qbot_api.py` (obok `/api/weather/*`, `/api/surface/by-name` itd.),
  `qext2_config.py` — wpis `news` w MESSAGES; strona podglądu w QBot Lab.
- QExt2: pobranie w `info/InfoWeather.kt` (ten sam tick) albo osobny mały obiekt `NewsFeed` wołany z tego samego miejsca;
  komunikat w `kokpit/RouteMessageEngine.kt` (lista `out`, gałąź bez trasy w linii `if (!i.hasRoute)`).
  **Uwaga:** wspólna kolejka komunikatów `active/ActiveMessageHub` jest używana przez KOKPIT — przy usuwaniu starych pól ACTIVE
  (build 0.4.27) pakiet `active` zostaje.
- Symulator QBota: przykładowe wiadomości w `qext2-sim/projekt/qext2-makieta.js` (MSG `news`) + wariant „wiadomości: wł./wył.”.

## Plan sesji

1. Weryfikacja źródeł RSS (które działają, częstotliwość, kodowanie) — wybór 4–6 niezależnych.
2. QBot: pobieranie + zapis + grupowanie + ocena AI + skrót + limit; endpoint `/api/qext2/news`.
3. QBot: strona podglądu (co zebrano, co przeszło, dlaczego) — Michał stroi progi.
4. Symulator: projekt komunikatu NEWS w KOKPIT (Zmiany projektowane), akceptacja.
5. QExt2: pobranie + `MsgKind.NEWS` + ustawienie w SETUP — jeden build.
6. Wiki: hasło `qext2/wiadomosci` + aktualizacja `qext2/komunikaty`; TODO → ZROBIONE.

## Otwarte pytania do Michała

- Pokazywać tylko na postoju / przy małej prędkości, czy także w jeździe?
- Także przy jeździe z trasą (gdy pasek pusty), czy tylko bez trasy?
- Limit dziennie (start 6) i próg ważności (start ≥ 4) — do strojenia na stronie podglądu.
- Czy wiadomości mają też iść gdzie indziej (np. Telegram), czy tylko Karoo? (Michał nie chce dodatkowego szumu w Telegramie.)
