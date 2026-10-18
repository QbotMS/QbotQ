---
tytul: Mapa modeli i zespołu
dzial: pogoda
typ: strona
opis: "Wyjaśnia mapę prognozy opadu i wariantów zespołu modeli."
tagi: ["pogoda", "mapa", "modele", "opad", "prognoza"]
synonimy: ["mapa opadow", "mapa prognozy", "mapa modeli", "ensemble forecast", "eps", "mapa deszczu"]
skroty: ["OPERA", "ICON-EU-EPS", "mm/h"]
gdzie_widac: ["Pogoda", "Mapa", "Radar szczegóły i modele"]
liczby: ["0,2 mm/h", "60 h", "30 min"]
zalezy_od: ["pogoda/prognoza", "pogoda/radar"]
wplywa_na: ["pogoda/warunki-punktowe", "pogoda/okno-jazdy", "pogoda/ostrzezenia"]
zrodla_kodu: ["qbot_pogoda_map.py latest_run build eps_build", "web_public/pogoda.html warstwy i legenda", "qbot_web.py api_pogoda_mapa_meta api_pogoda_mapa_png", "qbot_v2.pogoda_radar_verif"]
aktualizacja: 18.10.2026
---

# Mapa modeli i zespołu

## Co to jest

Mapa modeli pokazuje prognozowane obszary opadu na mapie dla wybranego czasu. Dla krótkiego horyzontu można zobaczyć radar, jego przesunięcie oraz dalszą prognozę modelową. Przy opadzie może pojawić się także mapa szansy z wielu wariantów prognozy.

## Po co

Użyj mapy, gdy chcesz sprawdzić, czy opad jest lokalny, czy obejmuje większy obszar. Zespół modeli pomaga zobaczyć rozrzut możliwych scenariuszy; nie rozstrzyga, który wariant na pewno się wydarzy.

## Skąd dane

Mapa modeli pobiera przebieg prognozy z serwisu meteorologicznego. Warstwa zespołowa jest wyliczana z wariantów [ICON-EU-EPS](../slowniczek.md#icon-eu-eps). Radar pochodzi z [OPERA](../slowniczek.md#opera). Bieżąca strona opisuje na mapie model, przebieg prognozy i — gdy dostępna — szansę opadu.

## Jak liczone

1. Serwer sprawdza najnowszy dostępny przebieg modelu i buduje warstwy mapy.
2. Wybierz czas na osi. Oś opadu przechodzi od obrazów radaru przez krótkie przesunięcie obrazu do prognozy modelowej.
3. Gdy wybrana warstwa zespołu jest dostępna, kolor pokazuje szansę przekroczenia progu opadu 0,2 [mm/h](../slowniczek.md#mmh). Na stronie warstwa zespołu jest ograniczona do horyzontu do 60 godzin.
4. Przezroczystość warstwy modelu jest ograniczana, gdy prognoza nie zgadza się z aktualnym radarem. Na ekranie może być pokazana zgodność procentowa.

Przykład z bazy: w ocenie radaru z 18.10.2026 14:40 dla prognozy +30 minut zapisano 2 przeoczone przypadki opadu oraz 958 poprawnych wskazań braku opadu. To nie jest „trafność modelu zespołowego”, tylko ocena konkretnej warstwy radaru w jednym kroku czasu.

```mermaid
flowchart TD
  Czas[Wybrany czas] --> Zrodlo{Dostępna warstwa?}
  Radar[OPERA] --> Krotko[Krótkie przesunięcie]
  Model[Przebieg modelu] --> Mapa[Warstwa na mapie]
  Zespol[Warianty zespołu] --> Szansa[Szansa opadu ≥ 0,2 mm/h]
  Krotko --> Mapa
  Szansa --> Mapa
  Mapa --> Odczyt[Legenda i oś czasu]
  Zrodlo --> Mapa
```

## Gdzie to widać

Na mapie głównej przełącz warstwę lub rozwiń szczegóły i modele. Legenda pojawia się w dolnym prawym obszarze mapy. Oś czasu jest u dołu ekranu. Zrzut pokazuje siatkę niebieskich komórek na mapie: to widok kwadratów, a nie mapa szansy opadu.

![Mapa i oś czasu strony Pogoda](../img/ekrany/pogoda.png)

## Jak czytać

Kolory warstwy opisuje legenda aktywnej warstwy. „Szansa opadu” oznacza udział wariantów zespołu przekraczających próg, a nie udział czasu, w którym będzie padać. Jeśli mapa modelu jest opisana jako rozbieżna z radarem, traktuj ją ostrożniej w najbliższej godzinie.

## Ograniczenia i pułapki

Brak warstwy może wynikać z niedostępnego przebiegu lub poza horyzontem zespołu. Kwadraty na ekranie głównym mają osobny cel i nie należy czytać ich jako intensywności opadu. Nie udało się w tej rundzie odczytać legendy wszystkich skal ani potwierdzić każdego dostępnego modelu.

> DO SPRAWDZENIA: Pełna lista modeli i opis wszystkich przedziałów kolorów legendy w aktualnej stronie.

## Wpływa na

Interpretację opadu w punkcie, Okno jazdy i ostrzeżenia o deszczu.

## Zależy od

Aktualnego przebiegu modelu, wariantów zespołu i dostępnych obrazów radaru.

## Powiązane hasła

- [Radar](radar.md)
- [Prognoza](prognoza.md)
- [Sprawdzalność prognoz](sprawdzalnosc.md)
- [Slowniczek](../slowniczek.md)

## Zrodla

- `/opt/qbot/app/qbot_pogoda_map.py` — `latest_run`, `build`, `eps_build`.
- `/opt/qbot/app/web_public/pogoda.html` — wybór warstw, legenda, oś czasu.
- `/opt/qbot/app/qbot_web.py` — `api_pogoda_mapa_meta`, `api_pogoda_mapa_png`.
- `qbot_v2.pogoda_radar_verif` — odczyt 18.10.2026 14:40.
