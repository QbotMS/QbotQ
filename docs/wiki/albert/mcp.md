---
tytul: Albert przez MCP
dzial: albert
typ: polaczenie
opis: Opisuje rozmowę z QBotem przez zgodną aplikację-klienta i granice tego połączenia.
tagi: [mcp, polaczenie, pytania, albert, odczyt]
synonimy: [mcp, qbot mcp, polaczenie mcp, klient mcp, rozmowa przez mcp, qbot query, integracja mcp]
skroty: [MCP]
gdzie_widac: [MCP]
liczby: []
zalezy_od: [albert/routing, albert/narzedzia, albert/ograniczenia]
wplywa_na: [albert/index, albert/routing]
zrodla_kodu: [qbot3/adapters/mcp_adapter.py handle_qbot3_mcp _list_tools _call_tool, qbot3/tool_registry.py mcp_tools_list]
aktualizacja: 19.10.2026
---

# Albert przez MCP

## Co to jest

MCP to sposób połączenia zgodnej aplikacji z QBotem ([słowniczek](../slowniczek.md#mcp)). Użytkownik zadaje pytanie, a odpowiedź przygotowuje QBot po stronie serwera.

## Po co

Pozwala rozmawiać z QBotem z aplikacji-klienta bez ręcznego wybierania wewnętrznej czynności. Albert może zostać uruchomiony po routerze, jeśli pytanie tego wymaga.

## Skąd dane

Aktualny kod adaptera składa listę z sześciu pozycji: jednej do zadawania pytań oraz pięciu do podglądu bazy QBot i Garażu. Podglądy są ograniczone do odczytu. Dokument architektury opisuje jedną pozycję. Nie pobrano wyniku działającego serwera: instrukcja etapu dopuszczała wyłącznie HTTP GET, a pobranie listy MCP wymaga żądania POST.

## Jak liczone

1. Aplikacja-klient wysyła tekst pytania jako żądanie QBot.
2. QBot próbuje obsłużyć pytanie krótką regułową ścieżką.
3. Nierozpoznane lub wymagające dalszej analizy pytanie może trafić do Alberta.
4. Albert dobiera wewnętrzne narzędzia, odbiera wyniki i formułuje odpowiedź.
5. Odpowiedź wraca do klienta. Pytania i podglądy danych mają różne zastosowania: zwykłe pytanie powinno iść przez czynność rozmowy, a surowy podgląd danych służy do sprawdzenia ograniczonego wycinka.

```mermaid
flowchart TD
 Pytanie[Pytanie] --> Kanal[Wybrany kanał]
 Kanal --> Router[Router prostych spraw]
 Router -->|pasuje| Prosta[Odpowiedź routera]
 Router -->|nie pasuje| Albert[Albert]
 Albert --> Narzedzia[Narzędzia dostępne dla pytania]
 Narzedzia --> Wynik[Dane lub status]
 Wynik --> Albert
 Albert --> Odpowiedz[Odpowiedź w kanale]
 Prosta --> Odpowiedz
```

## Gdzie to widać

W aplikacji połączonej z QBotem. Dostarczony zrzut pokazuje stronę główną, lewy pasek nawigacji i kafle wypraw; nie pokazuje klienta MCP ani okna rozmowy. Nie można z niego wywnioskować, czy połączenie MCP działa.

![Strona główna QBota, bez widoku klienta MCP](../img/ekrany/index.png)

## Jak czytać

Publiczne czynności klienta i wewnętrzne narzędzia Alberta to dwie różne listy. Obecność w kodzie adaptera nie potwierdza, że serwer w tej chwili zwraca tę samą listę. Nie należy utożsamiać MCP z bezpośrednim dostępem do wszystkich danych QBota.

## Decyzje i historia

19.10.2026: odczytany kod adaptera nadal publikuje pytanie do QBot oraz pięć narzędzi podglądu tylko do odczytu. Dokument architektury i bieżący kod są tu rozbieżne; w opisie liczby narzędzi rozstrzyga kod. Lista działającego serwera nie była pobierana, bo wymaga żądania POST, a zakres dopuszczał wyłącznie GET. Ścieżka zapisu administracyjnego widoczna w kodzie nie jest dowodem publikacji jej klientowi.

## Ograniczenia i pułapki

- Połączenie i uwierzytelnienie zależą od klienta oraz konfiguracji serwera.
- Narzędzia odczytu bazy nie są narzędziami Alberta do dowolnych zapisów.
- Nie sprawdzono odpowiedzi aktywnego serwera ani konkretnego klienta. To ograniczenie zakresu dostępu, nie pytanie o decyzję właściciela.
## Powiązane hasła

- [Routing pytań](routing.md)
- [Narzędzia Alberta](narzedzia.md)
- [Telegram](telegram.md)
- [Ograniczenia Alberta](ograniczenia.md)
- [Słowniczek](../slowniczek.md)

## Wpływa na / Zależy od

- Wpływa na: dostępu aplikacji-klienta do pytań QBota i ograniczonego podglądu
- Zależy od: adaptera MCP, klienta i ustawień serwera

## Zrodla

- `/opt/qbot/app/qbot3/adapters/mcp_adapter.py — handle_qbot3_mcp, _list_tools, _call_tool`
- `/opt/qbot/app/qbot3/tool_registry.py — mcp_tools_list`
- `/opt/qbot/app/docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md — Publiczny MCP`
