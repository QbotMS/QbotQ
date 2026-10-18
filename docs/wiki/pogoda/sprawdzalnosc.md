---
tytul: Sprawdzalność prognoz
dzial: pogoda
typ: algorytm
opis: "Porównuje zapisane prognozy z późniejszym pomiarem lub obrazem radaru."
tagi: ["pogoda", "sprawdzalność", "prognoza", "błąd", "radar"]
synonimy: ["trafnosc prognozy", "jak sprawdza sie prognoza", "forecast verification", "blad prognozy", "mae", "csi"]
skroty: ["MAE", "bias", "CSI", "IMGW", "OPERA"]
gdzie_widac: ["Pogoda", "Sprawdzalność"]
liczby: ["30 min", "60 min", "960 przypadków"]
zalezy_od: ["pogoda/prognoza", "pogoda/radar"]
wplywa_na: ["pogoda/index", "pogoda/warunki-punktowe", "pogoda/pogoda-na-trasie"]
zrodla_kodu: ["qbot_pogoda_verif.py score score_cached tick przydzial", "qbot_radar_verif.py evaluate summary", "qbot_eps_verif.py", "qbot_web.py API sprawdzalności", "qbot_v2.pogoda_radar_verif", "docs/POGODA_SPRAWDZALNOSC.md"]
aktualizacja: 18.10.2026
---

# Sprawdzalność prognoz

## Co to jest

Sprawdzalność to porównanie wcześniejszej prognozy z późniejszym pomiarem lub obrazem radaru. QBOT prowadzi osobne oceny prognoz pogody i krótkiego przesuwania opadu radarowego.

## Po co

Dzięki porównaniu można pokazać, jak trafiały wcześniejsze prognozy, i wybierać modele dla niektórych parametrów i horyzontów.

## Skąd dane

Ocena prognoz punktowych korzysta z pomiarów IMGW i wcześniejszych prognoz Open-Meteo. Ocena radaru porównuje poprzednie przewidywanie przesunięcia z późniejszym obrazem OPERA. Osobna ocena dotyczy szansy opadu z zespołu.

## Jak liczone

Dla temperatury, wiatru i porywów obliczane są [średni błąd bezwzględny (MAE)](../slowniczek.md#mae) i odchylenie średnie ([bias](../slowniczek.md#bias-prognozy)). Opad jest oceniany jako trafienie, fałszywy alarm lub przeoczony opad. Wyniki są dzielone według modelu i wyprzedzenia.

Przykład z bazy: 18.10.2026 14:40, ocena radaru z wyprzedzeniem 30 minut: trafienia 0, fałszywe alarmy 0, przeoczenia 2, poprawne wskazania braku opadu 958. Razem jest 960 przypadków. Dla wyprzedzenia 60 minut zapisano: 1 trafienie, 0 fałszywych alarmów, 1 przeoczenie i 958 poprawnych wskazań braku opadu. Jedna chwila nie wystarcza do oceny typowej jakości.

1. Dla +30 min dodaj cztery kategorie: 0 + 0 + 2 + 958 = 960 ocenionych przypadków.
2. Wśród tych 960 przypadków radar nie trafił opadu ani razu, nie ogłosił fałszywego deszczu, a 2 opady przeoczył.
3. Dla +60 min liczba trafień wynosiła 1, a liczba przeoczeń 1. Sama zmiana jednej próbki nie jest dowodem trwałej poprawy.

<details>
<summary>Wzór</summary>

CSI (wskaźnik trafności opadu) = trafienia / (trafienia + fałszywe alarmy + przeoczenia). Dla +30 min w tym odczycie: 0 / (0 + 0 + 2) = 0. Poprawne wskazania braku opadu nie wchodzą do tego wzoru.

</details>

![Przykładowe liczby sprawdzalności radaru z 18.10.2026 14:40](../img/radar-sprawdzalnosc.svg)

```mermaid
flowchart LR
  Prognoza[Zapisana prognoza] --> Porownanie[Połącz z późniejszą obserwacją]
  IMGW[Pomiar IMGW] --> Pogoda[Ocena prognozy pogody]
  Porownanie --> Pogoda
  Radar0[Wcześniejsza klatka radaru] --> OcenaR[Ocena przesunięcia opadu]
  Radar1[Późniejsza klatka radaru] --> OcenaR
  Pogoda --> Tabele[Tabele sprawdzalności]
  OcenaR --> Tabele
  Tabele --> Dobor[Dobór modelu według parametru i czasu]
  Tabele --> WWW[Widok sprawdzalności]
```

## Gdzie to widać

Strona Pogoda ma panel sprawdzalności. Serwis udostępnia osobne wyniki dla modeli, radaru i szansy opadu. Wcześniejsza ocena wybranych prognoz wpływa na dobór modelu dla pogody punktowej i trasowej.

![Mapa i szczegóły strony Pogoda](../img/ekrany/pogoda.png)

## Jak czytać

[MAE](../slowniczek.md#mae) pokazuje przeciętną wielkość błędu; [bias](../slowniczek.md#bias-prognozy) pokazuje, czy prognozy przeciętnie zawyżały czy zaniżały wynik. [CSI](../slowniczek.md#csi) opadu uwzględnia trafienia, fałszywe alarmy i przeoczenia; poprawne wskazania braku opadu nie zwiększają tego wskaźnika. Zawsze patrz na liczbę przypadków i okres danych. Wpisy z jednego dnia nie są stabilną oceną sezonu.

## Decyzje i historia

Dokumentacja projektu opisuje pomiary IMGW, wcześniejsze prognozy oraz osobne oceny radaru i zespołu. Bieżący kod wykorzystuje część wyników do doboru modeli.

## Ograniczenia i pułapki

Archiwum IMGW może pojawiać się z opóźnieniem. Bieżące pomiary API nie zawierają wszystkich pól archiwum. Porównanie godzinowych modeli z pomiarem stacyjnym ma ograniczenia przestrzenne i czasowe. Dla radaru wynik zależy od liczby przypadków z opadem.

## Wpływa na

Dobór modeli prognozy dla części funkcji punktowych i trasowych oraz widok sprawdzalności na stronie Pogoda.

## Zależy od

Archiwum i API IMGW, Previous Runs Open-Meteo, archiwizowanych klatek OPERA oraz działających automatów zapisu wyników.

## Powiązane hasła

- [Prognoza](prognoza.md)
- [Radar](radar.md)
- [Okno jazdy](okno-jazdy.md)

## Zrodla

- `/opt/qbot/app/qbot_pogoda_verif.py` — `score`, `score_cached`, `tick`, `przydzial`.
- `/opt/qbot/app/qbot_radar_verif.py` — `evaluate`, `summary`.
- `/opt/qbot/app/qbot_eps_verif.py` — ocena prognozy zespołowej.
- `/opt/qbot/app/qbot_web.py` — endpointy `/api/pogoda/sprawdzalnosc*`.
- `qbot_v2.pogoda_radar_verif` — odczyt wpisów z 18.10.2026 14:40.
- `/opt/qbot/app/docs/POGODA_SPRAWDZALNOSC.md` — definicje i zakres pomiarów.
