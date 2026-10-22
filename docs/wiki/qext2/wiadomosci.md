---
tytul: Ważne wiadomości na Karoo (RSS)
dzial: qext2
typ: funkcja
opis: QBot co 2 min czyta kanały RSS, AI ocenia ważność i robi polski skrót do 32 znaków; w jeździe Karoo dostaje tylko ważne wiadomości opublikowane po starcie, każdą raz.
tagi: [qext2, karoo, wiadomosci, rss, news, kokpit, ai]
synonimy: [newsy na karoo, wiadomości w pasku, qext2-news, ważne wiadomości, kanały rss]
skroty: [RSS, AI]
gdzie_widac: [KOKPIT 2 pasek komunikatów, SETUP QExt2]
liczby: [2 min, 32 znaki, 3/4/5 próg, 2 h, 5 na sygnał]
zalezy_od: [komunikaty.md, przeplyw-jazdy.md]
wplywa_na: [kokpit2.md, komunikaty.md]
zrodla_kodu: [qbot_news.py, qbot_web.py _news_loop, mcp_server.py _qext2_ping, qext2_config.py MESSAGES news, scripts/news_status.py]
aktualizacja: 22.10.2026
---

# Ważne wiadomości na Karoo (RSS)

## Co to jest

Gdy pasek komunikatów KOKPIT 2 milczy (żadnego ostrzeżenia), pokazuje ważną wiadomość z Polski albo ze świata — z flagą Polski, kulą ziemską albo flagą kraju (źródła lokalne, np. na wyjeździe). Tylko rzeczy naprawdę ważne, bez plotek i clickbaitów.

## Jak działa (QBot)

- **Co 2 min** QBot sprawdza kanały RSS (tylko „czy coś nowego”). Źródła są w bazie (`news_source`), domyślnie 9 sprawdzonych 22.10.2026: Polsat News (PL, Świat), RMF24 (PL, Świat), Interia, Deutsche Welle PL, Euronews PL, BBC World, Bankier.
- **AI ocenia** każdy nowy nagłówek (z ostatnich 2 h) w skali 1–5, wybiera ikonę i pisze **skrót po polsku do 32 znaków** (tłumaczy z każdego języka). Gdy skrót wyjdzie za długi, AI przepisuje go krócej. AI rozpoznaje też duble — tę samą wiadomość z różnych redakcji.
- **Próg wg ważności kanału**: wysoka = ocena ≥ 3, normalna ≥ 4, niska = tylko 5, wyłączony = nie pobierany. **Ważność czasowa** (od–do) nadpisuje zwykłą w swoim okresie, potem kanał sam wraca. **Okres aktywności**: stałe albo od–do.
- Jedno źródło wystarczy — nie czeka na drugą redakcję. Bez dziennego limitu.
- **Tylko fakty dokonane** (decyzja Michała 22.10.2026): przynęty, pytania i zapowiedzi odpadają („Kto zostanie nowym Bondem?” — nie, „X Y został nowym Bondem” — tak). Skrót to zawsze zdanie *kto/co → co się stało*, bez pytajnika.

## Jak trafia na Karoo

- Karoo w jeździe co ~5 min wysyła sygnał pozycji; w odpowiedzi (obok ostrzeżenia o deszczu) dostaje pole `news` — bez dodatkowego łącza.
- Tylko wiadomości **opublikowane po starcie jazdy**, które przeszły próg; każda grupa (dubel) **raz w całej jeździe**. Najwyżej 5 na jeden sygnał, reszta przy następnym. Kolejność: ważność kanału, ocena AI, czas.
- Włącznik: SETUP QBota > QExt2 > komunikaty → „Ważne wiadomości (RSS)”.
- Po stronie QExt2 (osobny build): komunikat o najniższym priorytecie, tylko gdy pasek pusty, z trasą i bez, także w jeździe.

## Podgląd

Do czasu strony w SETUP > QExt2 > Wiadomości: `.venv/bin/python3 scripts/news_status.py 40` — stan kanałów, co przeszło, co odpadło i dlaczego.

## Ograniczenia i pułapki

- RSS sam nie powiadamia — opóźnienie od publikacji do Karoo ok. 2–7 min.
- TVN24, Rzeczpospolita (blokują serwer), PAP i Polskie Radio 24 (zepsuty kanał) nie działają z serwera QBota.
- Ocena AI bywa niekonsekwentna między redakcjami (ta sama sprawa raz 3, raz 4) — strojenie progów na stronie podglądu.

## Powiązane hasła

[Komunikaty KOKPIT](komunikaty.md) · [KOKPIT 2](kokpit2.md) · [Przepływ jazdy](przeplyw-jazdy.md)
