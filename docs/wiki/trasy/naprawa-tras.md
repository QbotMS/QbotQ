---
tytul: Naprawa tras
dzial: trasy
typ: strona
opis: Pokazuje odcinki o złej nawierzchni i proponuje objazdy do oceny człowieka.
tagi: [naprawa tras, objazd, zly odcinek, ryzykowna nawierzchnia, kategoria nawierzchni, route repair, route detour]
synonimy: [naprawa tras, objazd, zly odcinek, ryzykowna nawierzchnia, route repair, route detour]
skroty: [OSM]
gdzie_widac: [Naprawa trasy, WWW]
liczby: [km, m]
zalezy_od: [trasy/store-i-wersje, trasy/nawierzchnia]
wplywa_na: [trasy/analiza-trasy]
zrodla_kodu: [qbot_web.py endpointy naprawy tras (surface-segments, segments/candidate, _detour_surface_categories), naprawa-trasy.html, qbot3/routes/route_surface_category_store.py, qbot3/routes/route_surface_context_store.py, tools/rwgps/route_surface_engine.py, Valhalla]
aktualizacja: 19.10.2026
---

# Naprawa tras

## Co to jest

Strona, która pokazuje na trasie odcinki o złej nawierzchni i na żądanie proponuje objazd. Objazd to propozycja do Twojej oceny — moduł sam nie zmienia trasy.

## Po co

Żeby przed wyjazdem znaleźć fragmenty, które mogą być nieprzejezdne albo bardzo wolne, i zobaczyć, czy da się je ominąć lepszą drogą.

## Skąd dane

Lista tras pochodzi z magazynu tras z policzoną nawierzchnią. Ocena nawierzchni to te same 5 kategorii co w Analizie trasy (od „twarda szybka" do „ryzyko/niepewne"). Drogę objazdu wyznacza dziś publiczny silnik tras Valhalla, ale ocenia ją QBot swoim modelem.

## Jak liczone

```mermaid
flowchart TD
  Store[Trasa z 5 kategoriami nawierzchni] --> Prog{Kategoria >= progu?}
  Prog -->|kat. 5 zawsze, kat. 4 z przełącznikiem| Risk[Odcinki do naprawy]
  Risk --> Anchors[Punkty przed i za odcinkiem]
  Anchors --> Router[Wyznaczenie objazdu]
  Router --> Judge[Ocena objazdu tym samym modelem 5 kategorii]
  Judge --> Map[Podgląd na mapie]
  Map --> Human[Decyzja człowieka]
```

## Gdzie to widać

Strona WWW `naprawa-trasy.html` (menu, sekcja testowa), z mapą i tabelą odcinków.

## Jak czytać

Odcinek do naprawy to fragment o kategorii 5 (ryzyko/niepewne), a po włączeniu przełącznika także 4 (trudna/wolna). Przy każdym odcinku widać rozkład kategorii i powód. Objazd ma własny rozkład kategorii liczony tak samo jak w Analizie trasy, więc oba wyniki można wprost porównać. Zwróć uwagę na długość objazdu — wybór lepszej nawierzchni często oznacza dodatkowe kilometry.

## Decyzje i historia

- 01.07.2026: pierwsza wersja; objazdy oceniała Valhalla własną skalą nawierzchni, inną niż reszta QBota — znana rozbieżność „dwóch systemów oceny".
- 19.10.2026: moduł wznowiony. Jedna ocena nawierzchni: odcinki i objazdy liczone 5 kategoriami z Analizy trasy (z kontekstem terenu WorldCover dla dróg bez opisu). Kat. 5 zawsze, kat. 4 przełącznikiem. Odcinek na samym starcie lub mecie trasy też dostaje objazd. Trasa liczona starym modelem pokazuje komunikat „przelicz trasę".
- Plan: własny mini-router na lokalnej bazie dróg Polski (szybszy, wyznacza drogę naszym modelem; Valhalla zostaje poza Polską), ekran nadzoru z wariantami i akceptacją objazdów, zapis jako osobna trasa „NAPRAWA" + GPX.

## Ograniczenia i pułapki

Valhalla to zewnętrzny serwer i może nie odpowiadać. Ocena jednego objazdu trwa kilka sekund. Objazd z linii na mapie nie sprawdza ruchu, zakazów wjazdu ani bezpieczeństwa skrętów. Brak kandydata nie znaczy, że droga jest zamknięta — tylko że w tym wywołaniu nie znaleziono lepszego połączenia.

## Wpływa na

Decyzję o ręcznej poprawie trasy przed wyjazdem.

## Zależy od

Magazynu tras z 5 kategoriami nawierzchni, lokalnej bazy dróg OSM, warstwy WorldCover i (na razie) serwera Valhalla.

## Powiązane hasła

- [Nawierzchnia](nawierzchnia.md)
- [Magazyn i wersje tras](store-i-wersje.md)
- [Analiza trasy](analiza-trasy.md)

### Co dzieje się po kliknięciu

1. Wybierz trasę z listy tras z policzoną nawierzchnią i kliknij „Wczytaj".
2. Mapa i tabela pokazują odcinki do naprawy z kilometrażem, rozkładem kategorii i powodem.
3. Kliknij odcinek albo „Nowy kandydat", aby poprosić o objazd.
4. QBot szuka objazdu w coraz większym promieniu (0,3 / 1 / 2 / 3 km) i każdy ocenia swoim modelem 5 kategorii; zatrzymuje się, gdy zła nawierzchnia objazdu spadnie poniżej 200 m, inaczej pokazuje najlepszy znaleziony.
5. Obejrzyj objazd. Strona nie zapisuje poprawionej trasy (zapis — kolejny etap).

Odcinki złej nawierzchni krótsze niż 200 m nie są zgłaszane osobno, a bliskie (przerwa < 200 m) są scalane. To reguły grupowania, nie dowód, że krótki fragment jest dobry.

![Widok naprawy trasy przed wczytaniem danych](../img/ekrany/naprawa-trasy.png)

## Zrodla

- `/opt/qbot/app/docs/PROJEKT_NAPRAWA_TRAS.md` — zakres, decyzje, wyniki testów, plan.
- `/opt/qbot/app/qbot_web.py` — endpointy odcinków i kandydata, ocena objazdu `_detour_surface_categories`.
- `/opt/qbot/web/public/naprawa-trasy.html` — interfejs podglądu.
- `/opt/qbot/app/qbot3/routes/route_surface_category_store.py` — model 5 kategorii.
- `/opt/qbot/app/qbot3/routes/route_surface_context_store.py` — kontekst terenu (WorldCover).
- `/opt/qbot/app/tools/rwgps/route_surface_engine.py` — silnik nawierzchni śladu.
