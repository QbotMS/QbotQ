---
tytul: Tło ekranu startowego Karoo
dzial: qext2
typ: funkcja
opis: QBot rysuje tło ekranu startowego Karoo z danymi dnia i pogodą na najbliższą jazdę.
tagi: [karoo, tlo, ekran startowy, home background]
synonimy: [tapeta karoo, tlo karoo, home background]
skroty: []
gdzie_widac: [Karoo — ekran startowy, kafel profilu]
liczby: [1440 x 2400, 30 min]
zalezy_od: [forma/index, trener/index, pogoda/index]
wplywa_na: []
zrodla_kodu: [qbot_karoo_tlo.py, qbot_web.py KAROO TLO, docs/KAROO_TLO.md]
aktualizacja: 20.10.2026
---

# Tło ekranu startowego Karoo

## Co to jest
Obrazek, który Karoo pokazuje na ekranie startowym. QBot rysuje go sam: w kaflu profilu widać stan dnia, gotowość, świeżość, pogodę na najbliższą jazdę z Trenera (gdy jej nie ma — na najbliższe 2 godziny), ostrzeżenie „SPRAWDŹ ROWER” i logo QBota.

## Po co
Przed wyjazdem, bez otwierania telefonu, widać na Karoo, w jakiej jesteś formie i jaka będzie pogoda w czasie zaplanowanej jazdy.

## Jak działa
1. Co najwyżej co 30 minut QBot sprawdza dane. Nowy obrazek powstaje tylko wtedy, gdy coś się zmieniło.
2. Każda wersja ma inny adres, bo Karoo pamięta obrazki po adresie.
3. Karoo dostaje adres aktualnej wersji (docelowo pobiera go sam QExt2).

## Jak czytać
Kolory gotowości i świeżości są takie jak na tarczy Startu. „SPRAWDŹ ROWER” znika, gdy odhaczysz zadania serwisowe zaznaczone w Raporcie z jazdy.

## Ograniczenia
- Karoo powiększa obrazek ok. 2,5 raza i pokazuje tylko jego wycinek; układ jest dopasowany do kafla profilu 1.
- Ciemne menu Karoo (wymuszony ciemny tryb) znika po restarcie urządzenia.
- Na razie jedno stałe zdjęcie.

## Zrodla
- `qbot_karoo_tlo.py`, `qbot_web.py` (blok KAROO TLO), `docs/KAROO_TLO.md`.
