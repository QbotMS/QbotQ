---
tytul: Bateria (Body Battery)
dzial: zdrowie
typ: liczba
opis: Pokazuje, jak noc naładowała Body Battery, ile i czym rozładował ją dzień, jak wyglądał wieczór przed snem i czy była drzemka.
tagi: [body battery, stres, regeneracja, sen, drzemka, kroki]
synonimy: [bateria, energia, stres dnia, drzemka, wieczór przed snem]
skroty: [BB, TSS, HRV]
gdzie_widac: [Zdrowie › Serce, wieczorna linia snu]
liczby: [3 min, 2 h, 70 pkt, 01.06.2026]
zalezy_od: [sen, serce, spo2]
wplywa_na: []
zrodla_kodu: [qbot_battery.py, qbot3/connectors/import_garmin_heart.py import_stress, qbot_food_api.py battery, web/public/zdrowie-serce2.js, fitmodel/sleep_target.py evening_line]
aktualizacja: 20.10.2026
---
# Bateria (Body Battery)

## Co to jest

Zegarek co 3 minuty liczy poziom „baterii” (Body Battery, 0–100) i stres. QBot czyta to jak baterię: ile naładowała noc, ile zużył dzień i czym, z jaką baterią i w jakim napięciu poszedłeś spać.

## Po co

Twoje dane pokazują, że najsilniejszy wpływ na noc mają **2 godziny przed snem** — mocniejszy niż trening — oraz to, z jaką baterią kładziesz się spać.

## Skąd dane

Krzywa stresu i baterii z Garmina (od 01.06.2026, starszej Garmin nie oddaje), pora snu, jazdy (TSS), kroki i drzemki wykryte przez zegarek.

## Co wynika z danych (06–10.2026, 141 dni)

- Dzień zużywa typowo ok. 70 punktów (rano ~83, do łóżka ~9), noc ładuje ok. 70 — bez zapasu.
- Baterię rozładowują głównie **kroki**; trening i minuty stresu znacznie mniej.
- Spokojny wieczór (stres w 2 h przed snem ≤ ~32): noc +72, ocena snu 82, HRV 82. Nerwowy (≥ ~53): +62, 78, 75.
- Do łóżka z baterią ≤ ~5 → rano ok. 66; z baterią ≥ ~16 → rano ok. 95.
- Progi (25% i 75% Twoich dni) liczą się na bieżąco.

## Drzemki

Drzemka wykryta przez zegarek jest pokazywana w szczegółach dnia i w wieczornej linii snu („wliczona do snu doby”). Cel snu na razie się nie zmienia — od czerwca były tylko 2 drzemki z krzywą baterii, za mało, by zmierzyć ich wpływ.

## Gdzie to widać

Zdrowie › Serce: kafel „Bateria (Body Battery)”, panel „Bateria” na wspólnej osi czasu (bateria rano, do łóżka, drzemki), szczegóły dnia z krzywą baterii i stresu (pasy: jazda, drzemka). W szczegółach nocy („Oddech w nocy”): stres 2 h przed snem i bateria na dobranoc.
