---
tytul: Punkty na trasie
dzial: trasy
typ: algorytm
opis: Pokazuje sklepy, wodę, jedzenie i usługi przy przebiegu trasy.
tagi: [punkty na trasie, zaopatrzenie, sklepy przy trasie, woda na trasie, jedzenie na trasie, route poi]
synonimy: [punkty na trasie, zaopatrzenie, sklepy przy trasie, woda na trasie, jedzenie na trasie, route poi]
skroty: [POI, OSM]
gdzie_widac: [Analiza trasy, Planer wyprawy]
liczby: [km, m]
zalezy_od: [trasy/store-i-wersje]
wplywa_na: [trasy/analiza-trasy, trasy/planer-wyprawy]
zrodla_kodu: [qbot3/routes/route_poi_store.py, qbot_v2.route_poi_layer, raport-render.js]
aktualizacja: 18.10.2026
---

# Punkty na trasie

## Co to jest

Punkty na trasie to warstwa logistyczna, na przykład sklepy, woda, jedzenie i usługi rowerowe. To odrębna warstwa od atrakcji turystycznych.

## Po co

Pomaga znaleźć miejsce zaopatrzenia lub usługę w pobliżu trasy.

## Skąd dane

Wyniki są przypisane do wersji trasy w warstwie `route_poi_layer`. Odcinki Planera mogą odziedziczyć punkty z trasy nadrzędnej. Dostępne kategorie oraz źródła zależą od uruchomionego wyszukiwania.

## Jak liczone

```mermaid
flowchart LR
  Route[Wersja trasy] --> Search[Wyszukanie punktów]
  Search --> Filter[Odległość i kategoria]
  Filter --> Store[Warstwa punktów]
  Parent[Trasa wyprawy] -->|podział zakresu| Store
  Store --> Report[Zaopatrzenie w raporcie]
```

## Gdzie to widać

Zakładka Zaopatrzenie w Analizie trasy. Nazwa zakładki i warstwa raportu są widoczne w aktualnym rendererze.

## Jak czytać

Punkt oznacza wpis znaleziony w źródle, nie gwarancję aktualnych godzin otwarcia, dostępności ani działającej usługi. Sprawdź źródło i datę danych.

## Decyzje i historia

Kod odróżnia logistyczne POI od atrakcji. Planer dziedziczy punkty z nadrzędnej trasy, zamiast mieszać je z listą atrakcji.

## Ograniczenia i pułapki

Katalog mapowy może być niepełny lub nieaktualny. Nie wszystkie kategorie muszą być dostępne dla każdej trasy.

## Wpływa na

Widok zaopatrzenia i dzienne trasy wyprawy.

## Zależy od

Warstwy punktów, źródła wyszukiwania i geometrii wersji.

## Powiązane hasła

- [Atrakcje](atrakcje.md)
- [Planer wyprawy](planer-wyprawy.md)
- [Analiza trasy](analiza-trasy.md)

### Jak powstaje lista zaopatrzenia

1. Dla zapisanej wersji trasy wyszukiwane są obiekty w jej pobliżu.
2. Wyniki są przypisywane do kategorii logistycznych i do kilometrażu trasy.
3. Punkty trafiają do osobnej warstwy. Planer może przenieść punkty z trasy głównej do odpowiednich etapów.
4. Raport pokazuje nazwę i położenie; dostępność punktu trzeba sprawdzić u źródła.

Kategorie dotyczą miejsc praktycznych, takich jak sklep, woda, jedzenie lub usługa rowerowa. Dokładna lista zależy od tagów znalezionych obiektów i bieżących źródeł; nie zakładam, że każda kategoria jest dostępna w każdym miejscu.

![Mapa i panel dnia w raporcie trasy](../img/ekrany/raport-trasy.png)

Na zrzucie przyciski pod mapą dotyczą widoku mapy i nakładki kwadratów. Punkty logistyczne otwiera się w zakładce „Zaopatrzenie” raportu, a nie przez te przyciski mapy.

### Decyzja przed wyjazdem

Jeśli sklep ma znaczenie dla zapasu jedzenia lub wody, sprawdź godziny otwarcia w dniu wyjazdu i zaplanuj drugi punkt. Zapisane godziny mogą pochodzić z wcześniejszego odczytu. Znaleziony punkt nie jest potwierdzeniem, że lokal będzie otwarty.

### Różnica między kilometrażem i odległością od drogi

Punkt ma pozycję na mapie i może mieć przypisany kilometr trasy oraz odległość od przebiegu. Kilometr mówi, gdzie mniej więcej wypada zjazd wzdłuż zaplanowanej drogi; odległość od trasy mówi, jak daleko obiekt jest od linii. Nie oznacza to automatycznie, że istnieje bezpieczny dojazd. Obejrzyj mapę przed zjechaniem z trasy.

Lista może być pusta z różnych przyczyn: dla wersji nie ma zapisanej warstwy, wyszukiwanie nie zwróciło kandydatów albo źródło nie dostarczyło danych. Sam pusty panel nie rozstrzyga, który przypadek zaszedł.

## Zrodla

- `/opt/qbot/app/docs/PLANER_WYPRAW_ATRAKCJE.md` — rozdzielenie logistyki i atrakcji.
- `/opt/qbot/app/qbot3/routes/route_poi_store.py` — zapis i odczyt POI.
- `/opt/qbot/app/qbot3/routes/route_attraction_store.py` — odrębny odczyt atrakcji.
- `/opt/qbot/app/sql/route_base_store_v1.sql` — `route_poi_layer`.
- `/opt/qbot/web/public/raport-render.js` — zakładka Zaopatrzenie.
