---
tytul: Okno jazdy
dzial: pogoda
typ: algorytm
opis: "Porównuje możliwe godziny startu i ocenia pogodę podczas planowanej jazdy."
tagi: ["pogoda", "okno jazdy", "start", "deszcz", "wiatr"]
synonimy: ["kiedy jechac", "najlepsza godzina jazdy", "okno pogodowe", "ride window", "pogoda na start"]
skroty: ["ICON-EU-EPS"]
gdzie_widac: ["Pogoda", "Okno jazdy", "Trener"]
liczby: ["krok 30 min", "ocena 0–100", "kara 10 punktów"]
zalezy_od: ["pogoda/prognoza", "pogoda/radar", "pogoda/sprawdzalnosc", "trener/index"]
wplywa_na: ["pogoda/index"]
zrodla_kodu: ["qbot_pogoda_okno.py STEP_MIN window", "qbot_pogoda.py kara_komfort", "web/public/pogoda.html Okno jazdy", "docs/POGODA_OKNO.md"]
aktualizacja: 18.10.2026
---

# Okno jazdy

## Co to jest

Okno jazdy porównuje pogodę dla możliwych godzin startu i pokazuje ocenę warunków na jazdę. Można analizować wybraną jazdę z kalendarza albo podać dzień, godzinę i czas samodzielnie.

## Po co

Pomaga zdecydować, czy warto przesunąć start, biorąc pod uwagę deszcz, wiatr, zimno, upał, śliskość i zmrok.

## Skąd dane

Widok bierze dostępność i plan jazdy z Trenera, warunki dla punktu, szansę opadu z zespołu [ICON-EU-EPS](../slowniczek.md#icon-eu-eps) oraz — dla najbliższej godziny — [krótką prognozę radarową](radar.md). Można porównać kilka kolejnych dni i zmienić czas lub długość jazdy.

## Jak liczone

1. Tworzy warianty startu co 30 minut w dostępnych oknach rowerowych Trenera.
2. Usuwa warianty kolidujące z zajętością i innymi sesjami.
3. Dla każdego wariantu sprawdza prognozę na czas jazdy; dla najbliższej godziny uwzględnia radar.
4. Nakłada kary za opad i jego szansę, porywy, oblodzenie, mgłę, mokrą nawierzchnię, zmrok oraz odczuwalny chłód lub upał.
5. Pokazuje ocenę od 0 do 100 i tekstowe uwagi.

Ocena zaczyna się od 100 punktów i spada o 10 punktów za każdą jednostkę naliczonej kary. Wynik nie wychodzi poza zakres 0–100. Progi planowania pochodzą z ustawień Trenera. Osobna ocena komfortu służy do porównania wygody i nie jest tym samym co progi planowania.

```mermaid
flowchart TD
  Plan[Plan i dostępność Trenera] --> Starty[Możliwe starty co 30 minut]
  Zajecia[Zajętość i sesje] --> Starty
  Starty --> Prognoza[Prognoza na czas jazdy]
  Radar[Radar dla bliskiego startu] --> Ocena[Ocena wariantu]
  Prognoza --> Ocena
  Ocena --> Kary[Kary pogodowe i uwagi]
  Kary --> Wynik[Ocena 0–100]
  Wynik --> Strona[Panel Okno jazdy]
```

## Gdzie to widać

Strona Pogoda, panel „Okno jazdy — przesunąć czy moknąć?”. Można zmienić dzień, start i czas. Widoczny jest też tryb czasu albo dystansu z przyjętą średnią prędkością.

![Strona Pogoda z mapą i panelem dolnym; Okno jazdy jest osobną sekcją](../img/ekrany/pogoda.png)

## Jak czytać

Wyższa liczba oznacza mniej naliczonych kar w modelu, nie gwarancję dobrej jazdy. Porównuj warianty dla tego samego czasu i dystansu. Kolor wyniku w obecnym interfejsie: od 80 zielony, od 50 akcentowy, niżej czerwony.

## Decyzje i historia

Starszy opis okna jazdy podaje krok 30 minut. Bieżący panel pozwala również wskazać konkretny plan. Oceny komfortu i planowania mają osobne kary oraz progi.

## Ograniczenia i pułapki

Wynik zależy od prognozy dla jednego punktu (dom lub pozycja wskazana przez użytkownika), nie od pełnej trasy. Radar jest przydatny tylko dla krótkiego horyzontu. Ocena nie zastępuje ostrzeżenia silnika trasy ani obserwacji warunków.

## Wpływa na

Porównanie godzin startu w dziale Pogoda; nie zmienia samoczynnie planu treningowego.

## Zależy od

Dostępności Trenera, danych prognozy, danych zespołu, radaru oraz podanego czasu trwania lub dystansu jazdy.

## Powiązane hasła

- [Prognoza](prognoza.md)
- [Radar](radar.md)
- [Sprawdzalność prognoz](sprawdzalnosc.md)
- [Trener](../trener/index.md)

## Zrodla

- `/opt/qbot/app/qbot_pogoda_okno.py` — `STEP_MIN`, generowanie i ocena startów.
- `/opt/qbot/app/qbot_pogoda.py` — warunki punktowe i `kara_komfort`.
- `/opt/qbot/web/public/pogoda.html` — panel Okna jazdy, kolory i sterowanie.
- `/opt/qbot/app/docs/POGODA_OKNO.md` — założenia i dane wejściowe.
