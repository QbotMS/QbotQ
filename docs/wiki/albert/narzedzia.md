# Narzędzia Alberta

## Co to jest

Narzędzia to czynności dostępne Albertowi: jedne pobierają informacje, inne mogą zapisać zmianę. To Albert dobiera je do pytania; lista narzędzi nie jest menu, które użytkownik musi znać.

## Po co

Dzięki narzędziom odpowiedź może opierać się na danych QBota. Ta sama rozmowa może wymagać jednego odczytu albo kilku kolejnych kroków.

## Skąd dane

Przy uruchomieniu pytania serwer przygotowuje opisy dostępnych czynności. Albert otrzymuje ich opisy i może wywołać te, które pasują do pytania. Nie każda czynność z zaplecza jest bezpośrednio widoczna klientowi MCP.

## Jak liczone

1. Pytanie określa potrzebny temat, np. „jaka była moja ostatnia jazda?”.
2. Albert wybiera odczyt dotyczący jazdy, jeśli jest dostępny w danym uruchomieniu.
3. Czynność zwraca dane albo informację o błędzie/braku danych.
4. Albert odpowiada na podstawie wyniku. Przy zapisie sprawdza status, zamiast zakładać, że zmiana się udała.

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

## Główne grupy

- Trening i forma: bieżący status formy, gotowość, ostatnie jazdy i tydzień Trenera.
- Trasy: lista, raport i profil zaplanowanej trasy, czas przejazdu oraz wybrane operacje na trasie.
- Pogoda: pogoda teraz, okno jazdy i prognozy powiązane z trasą.
- Zdrowie i jedzenie: sen, wellness, serce, suplementy, podsumowanie i rejestr posiłków.
- Notatki: fakty do planowania i pamięć potwierdzonych informacji.
- System: status i wybrane informacje diagnostyczne.
- Pliki i integracje: odczyt listy artefaktów, RWGPS oraz Garaż.
- Surowy podgląd: ograniczone narzędzia odczytu bazy i Garażu.

To grupy tematyczne potwierdzone w rejestrze; nie oznaczają, że każde narzędzie jest włączone i działa w każdej chwili. Pełne nazwy są celowo pozostawione w źródłach.

## Gdzie to widać

Zwykle widzisz odpowiedź, nie nazwę czynności. Klient MCP publikuje osobną, węższą listę. Bieżący kod deklaruje `qbot_query` i zestaw narzędzi odczytu bazy/Garażu; dokument architektury mówi o samym `qbot_query`. To potwierdzony rozjazd. Nie sprawdzono odpowiedzi żywego serwera.

## Jak czytać

Jeśli Albert napisał, że coś zapisał, ważny jest potwierdzony wynik operacji. Sama obecność funkcji w kodzie nie potwierdza działania usługi, poprawności danych ani dostępu w każdym kanale.

## Decyzje i historia

Opis czynności przekazywany Albertowi pochodzi z rejestru i promptu. Zasada projektu wymaga uaktualnienia instrukcji Alberta przy zmianie rejestru. Trasy obsługują aktualne narzędzia; nie należy przypisywać ich nieistniejącemu Plannerowi v2.

## Ograniczenia i pułapki

Odczyt i zapis podlegają różnym zabezpieczeniom. Usuwanie lub zmiana danych może mieć dodatkowe potwierdzenia. Lista publiczna MCP nie jest pełną listą wewnętrznych możliwości Alberta.
## Powiązane hasła

- [Routing pytań](routing.md)
- [Pamięć Alberta](pamiec.md)
- [MCP](mcp.md)
- [Ograniczenia Alberta](ograniczenia.md)
- [Słowniczek](../slowniczek.md)

## Wpływa na / Zależy od

- Wpływa na: dane użyte w odpowiedzi oraz wybrane zapisy
- Zależy od: rejestru, instrukcji Alberta, połączeń i zabezpieczeń

## Zrodla

- `/opt/qbot/app/qbot3/tool_registry.py — _init_registry, tool_descriptions, tool loaders`
- `/opt/qbot/app/qbot3/agent_runtime.py — _execute_single_tool, orchestrate_query`
- `/opt/qbot/app/qbot3/llm/albert.py — _SYSTEM, build_tools_spec`
- `/opt/qbot/app/qbot3/adapters/mcp_adapter.py — _list_tools`
