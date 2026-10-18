---
tytul: Wiatr
dzial: pogoda
typ: liczba
opis: "Wyjaśnia prędkość, kierunek i porywy wiatru oraz ich wpływ względem trasy."
tagi: ["pogoda", "wiatr", "porywy", "trasa", "qext2"]
synonimy: ["wiatr na rowerze", "wiatr czolowy", "wiatr w plecy", "wind speed", "gust", "wiatr boczny"]
skroty: ["m/s", "QExt2"]
gdzie_widac: ["Pogoda", "Raport trasy", "QExt2"]
liczby: ["prędkość m/s", "porywy m/s"]
zalezy_od: ["pogoda/prognoza", "pogoda/pogoda-na-trasie"]
wplywa_na: ["pogoda/warunki-punktowe", "pogoda/pogoda-na-trasie", "pogoda/qext2"]
zrodla_kodu: ["qbot_wx.py forecast", "qbot_pogoda.py conditions_point", "qbot3/routes/route_meteo_engine.py wind_tail_ms wind_cross_ms", "qbot_api.py _qext2_weather_route", "docs/POGODA_RADAR.md"]
aktualizacja: 18.10.2026
---

# Wiatr

## Co to jest

Prognoza wiatru opisuje prędkość wiatru, jego kierunek oraz porywy. QBOT pokazuje prędkość wiatru w m/s.

## Po co

Wiatr pomaga ocenić warunki jazdy. Na trasie można odróżnić wiatr wzdłużny od poprzecznego, a w QExt2 także wiatr czołowy od wiatru w plecy.

## Skąd dane

Prognoza pochodzi z Open-Meteo i używa m/s. Dla wskazanego miejsca pobierane są kierunek i porywy. Silnik trasy wyznacza także składową wzdłużną i poprzeczną wiatru; QExt2 otrzymuje wzdłużną składową oraz porywy.

## Jak liczone

1. Prognoza dla punktu podaje prędkość, kierunek, porywy i czas. Prędkość jest wyrażona w m/s.
2. Dla trasy porównywany jest kierunek wiatru z kierunkiem danego odcinka. Wynik rozdziela wiatr wzdłuż trasy od wiatru bocznego.
3. Wartość wzdłużna po stronie silnika trasy dodatnia oznacza wiatr w plecy, a ujemna — czołowy. Odpowiedź QExt2 odwraca znak tej wartości: dodatnie `head` oznacza wiatr czołowy, ujemne — w plecy.
4. Wiatr, porywy i składowe są prognozami dla danego miejsca i czasu, a nie pomiarem z roweru.

Przykład z bazy: w podsumowaniu jazdy z 18.10.2026 mediana zmierzonego wiatru wynosiła 2,4 m/s, a udział czasu z wiatrem czołowym 11,4%. Są to odczyty z pól QExt2, nie prognoza kierunku dla trasy. Bez sparowanego kierunku wiatru i kierunku odcinka nie da się odtworzyć składowych dla tych 8743 próbek.

```mermaid
flowchart LR
  Prognoza[Prędkość i kierunek wiatru] --> Porownanie[Porównaj z kierunkiem trasy]
  Trasa[Kierunek jazdy] --> Porownanie
  Porownanie --> Skladowe[Wzdłuż i w poprzek]
  Skladowe --> QExt[Wiatr czołowy lub w plecy]
  Porywy[Porywy z prognozy] --> QExt
```

## Gdzie to widać

Kierunek i siła wiatru są pokazywane w warunkach pogodowych strony Pogoda. Prognoza trasy i QExt2 mogą pokazać składową względem kierunku jazdy.

![Kafelek wiatru po lewej i zakładka Wiatr pod mapą](../img/ekrany/pogoda.png)

## Jak czytać

Wartość w m/s to prędkość wiatru; większa wartość oznacza silniejszy wiatr. Składowa czołowa utrudnia jazdę, a składowa w plecy pomaga. Są to prognozowane składowe względem trasy, nie niezależny pomiar na rowerze.

## Decyzje i historia

Kod wspólnego transportu wymusza m/s. Starsze dokumenty mogą opisywać inne jednostki dla ruchu chmur na mapie radaru; prędkość przesuwania się opadu nie jest wiatrem przy ziemi.

## Ograniczenia i pułapki

Prognoza modelowa może różnić się od wiatru lokalnego, zwłaszcza za przeszkodami terenowymi. Nie należy utożsamiać prędkości przemieszczania się obrazu opadu z prędkością wiatru przy gruncie.

## Wpływa na

Ocena pogody na trasie, odczuwalna temperatura i dane pogodowe pokazywane QExt2.

## Zależy od

Prognozy kierunku i prędkości wiatru oraz geometrii trasy i przewidywanego kierunku jazdy.

## Powiązane hasła

- [Prognoza](prognoza.md)
- [Pogoda na trasie](pogoda-na-trasie.md)
- [Pogoda w QExt2](qext2.md)

## Zrodla

- `/opt/qbot/app/qbot_wx.py` — `forecast`, jednostka `ms`.
- `/opt/qbot/app/qbot_pogoda.py` — wybór wiatru i porywów w `conditions_point`.
- `/opt/qbot/app/qbot3/routes/route_meteo_engine.py` — `wind_tail_ms`, `wind_cross_ms`.
- `/opt/qbot/app/qbot_api.py` — `_qext2_weather_route`, `head`, `gust`.
- `qbot_v2.fitmodel_qext2_ride` — podsumowanie kontroli wiatru jazdy 24766557671 z 18.10.2026.
- `/opt/qbot/app/docs/POGODA_RADAR.md` — prędkość ruchu opadu w km/h, odróżniona od wiatru.
