---
tytul: Wykresy Formy
dzial: forma
typ: zakladka
opis: Wykresy Formy pokazują dzienne serie obciążenia, zdrowia i aktywności.
tagi: ["wykresy", "forma", "obciążenie", "wellness"]
synonimy: ["wykres formy", "wykres treningowy", "chart", "wykresy zdrowia"]
skroty: ["CTL", "ATL", "TSB", "XSS"]
gdzie_widac: ["Forma", "Dziennik", "Trendy"]
liczby: ["28 dni", "XSS"]
zalezy_od: ["forma/ctl-atl-tsb", "forma/trendy", "forma/statystyki"]
wplywa_na: ["forma/index"]
zrodla_kodu: ["/opt/qbot/web/public/forma.html zakładki wykres Dziennika", "/opt/qbot/web/public/forma2-data.js serie i rysowanie", "/opt/qbot/app/qbot_web.py _build_forma_data API Formy", "qbot_v2.fitmodel_daily"]
aktualizacja: 18.10.2026
---
# Wykresy Formy

## Co to jest

Wykresy przedstawiają dzienne wartości treningowe i zdrowotne. W Formie ekran Dziennik pokazuje między innymi historię obciążenia z 28 dni, a zakładka Trendy pozwala przeglądać dłuższe serie.

## Po co

Wykres pomaga zauważyć, czy wartość rośnie, spada czy utrzymuje się. Jeśli linia przerywa się, sprawdź, czy brakowały pomiary; brak punktu nie oznacza zera.

## Skąd dane

Dziennik i Trendy pobierają dzienne serie z danych Formy. Statystyki aktywności korzystają z odrębnego API. Poszczególne serie mogą mieć inne źródła i jednostki.

## Jak liczone

1. Strona pobiera dzienne wartości z wybranego zakresu.
2. Widok rysuje każdą miarę jako osobną serię; słupki jazd pokazują obciążenie przypisane do dnia.
3. Dnia 18.10.2026 forma wynosiła 58,0, krótkie obciążenie surowe 60,1, krótkie faktyczne 74,5, a faktyczna świeżość −16,5.
4. Przeliczenie z danych: 58,0 − 74,5 = −16,5. Na zrzucie kafel zaokrągla świeżość do −17, więc odejmowanie wartości widocznych na ekranie może dać inny wynik.
5. [Wykres SVG](../img/forma-obciazenie-20261012-18.svg) przedstawia prawdziwe wartości z 12–18.10.2026; odczytuj go jako przykład danych, nie jako aktualny podgląd.

<details><summary>Wzór</summary>

Świeżość faktyczna = długie obciążenie − faktyczne krótkie obciążenie. Wygładzanie obciążenia opisuje [osobne hasło](ctl-atl-tsb.md).

</details>

```mermaid
flowchart LR
  A[Dane dzienne] --> B[API Formy]
  C[Aktywności] --> D[API statystyk]
  B --> E[Serie linii]
  D --> F[Sumy i słupki]
  E --> G[Wykres]
  F --> G
```

## Gdzie to widać

Forma → Dziennik oraz Trendy. Zrzut ekranu [głównej Formy](../img/ekrany/forma.png) pokazuje wykres 28 dni pod kaflami; legenda nad wykresem identyfikuje serie.

Na zrzucie szukaj najpierw tytułu „Obciążenie i forma · 28 dni”, a potem legendy: forma, zmęczenie faktyczne, zmęczenie z treningów i słupki XSS (punkty obciążenia; [słowniczek](../slowniczek.md)). Wspólna oś pozwala zobaczyć kierunek zmian, ale wartości należy odczytywać z etykiet i podpowiedzi, nie z samego położenia linii. Analiza wykresu bierze widoczny zakres oraz zaznaczone serie; kod ogranicza ich liczbę do 12 i prosi o interpretację bez porady treningowej.

## Jak czytać

Najpierw sprawdź nazwę serii i jednostkę. CTL (długie obciążenie), ATL (krótkie obciążenie) i TSB (różnica) nie są zamienne; rozwinięcia są w [słowniczku](../slowniczek.md). Słupki jazd to inna miara niż linie. Jeśli punktu brakuje, nie łącz go z zerem. Na zrzucie Forma legenda znajduje się nad wykresem, około jednej trzeciej wysokości strony.

## Decyzje i historia

Aktualna strona używa zakładek Dziennik, Trendy, Sezon i Statystyki. Starszy dokument układu opisuje wcześniejszy widok.

## Ograniczenia i pułapki

Nie sprawdzono każdego przełącznika na zalogowanej stronie. Kolory i interakcje mogą się zmienić; wartości i serie należy wiązać z legendą.

## Wpływa na / Zależy od

Wykresy pokazują dzienne serie i aktywności; nie wykonują zapisu treningu.

## Powiązane hasła

- [Forma, zmęczenie i świeżość](ctl-atl-tsb.md)
- [Trendy](trendy.md)
- [Statystyki](statystyki.md)
- [Sen](sen.md)
- [Masa ciała](waga.md)

## Zrodla

- `/opt/qbot/web/public/forma.html` — struktura zakładek i wykres Dziennika.
- `/opt/qbot/web/public/forma2-data.js` — serie i rysowanie.
- `/opt/qbot/app/qbot_web.py` — `_build_forma_data`, `/api/forma/data`.
- `/opt/qbot/app/qbot_web.py` — `/api/forma/analyze`, tryb analizy wykresu.
- `qbot_v2.fitmodel_daily` — wartości dzienne.
