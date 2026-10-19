---
tytul: Białko
dzial: zdrowie
typ: liczba
opis: Pokazuje ilość białka w zapisanych posiłkach i porównuje ją z celem dnia.
tagi: [białko, jedzenie, cel dzienny, brokuł]
synonimy: [protein, proteiny, ile bialka, bialko dziennie, białko na dzień]
skroty: []
gdzie_widac: [Zdrowie, Brokuł, Trener]
liczby: [g]
zalezy_od: [dziennik, cel-kcal, weekend]
wplywa_na: [dziennik, weekend]
zrodla_kodu: [qbot_food_plan.py PROTEIN_TARGET norms, qbot_food_api.py, qbot_v2.albert_day_view]
aktualizacja: 19.10.2026
---
# Białko

## Co to jest

Białko jest jednym ze składników pokazywanych w dzienniku. W planie QBota ma cel 160 g dziennie. Należy do makroskładników ([wyjaśnienie](../slowniczek.md#makroskladniki)).

## Po co

Pomaga sprawdzić, czy zapisane posiłki zbliżają się do przyjętego celu.

## Skąd dane

Gramy białka pochodzą z menu Brokuła i wpisów jedzenia. Wartości dzienne są sumowane w podsumowaniu dnia i tygodnia.

## Jak liczone

```mermaid
flowchart LR
  A[Zapisane posiłki] --> C[Suma białka]
  B[Cel z planu] --> C
  C --> D[Porównanie dnia]
  C --> E[Średnia tygodnia]
```


Cel białka wynosi 160 g we wszystkich widokach. Karta oznacza tę wartość jako „ok” od 90%, czyli od 144 g. W analizie tygodnia ostrzeżenie pojawia się, gdy średnia z zamkniętych dni jest niższa niż 85% celu.

### Przykład krok po kroku

1. Na zrzucie z 18.10.2026 karta pokazuje 148 g białka przy celu 160 g.
2. Różnica wynosi 160 − 148 = 12 g. Karta pokazuje „ok”, bo 148 g przekracza próg 90% × 160 g = 144 g.
3. Odczyt 18.10.2026 zawierał później 181 g. To o 21 g więcej niż cel 160 g.
4. Wartość „ok” jest etykietą reguły aplikacji, nie oceną medyczną.

Przykład z bazy: 14.10.2026 dzienny widok danych zawiera 185,1 g białka w zapisanym jedzeniu.

## Gdzie to widać

Karta dnia i analiza tygodnia w Zdrowiu, a także wiadomości Trenera.

![Wartość białka i cel na karcie Dziś](../img/ekrany/zdrowie.png)

## Jak czytać

„Ok” na kafelku Brokuła oznacza osiągnięcie 90% celu. To próg prezentacji, a nie osobna norma medyczna.

## Decyzje i historia

Decyzja Michała z 19.10.2026: jeden cel 160 g we wszystkich miejscach. Wcześniejsza piątkowa wiadomość weekendowa podawała 150 g; kod został ujednolicony.

## Ograniczenia i pułapki

Suma zależy od jakości danych w menu i szacunków porcji. W tygodniowej analizie białko liczone jest z całego zapisanego jedzenia.

## Wpływa na

Status białka dnia, zalecenia w porannym podsumowaniu i plan weekendu.

## Zależy od

Zapisanych makr posiłków oraz celu z moduł planowania.

## Powiązane hasła

- [Dziennik jedzenia](dziennik.md)
- [Cel kcal](cel-kcal.md)
- [Plan weekendu](weekend.md)

## Jak czytać praktycznie

Jeśli w ciągu dnia widzisz wartość poniżej celu, potraktuj „brakuje” jako różnicę do planu. Na zrzucie z 18.10 różnica to 12 g (160 − 148). Późniejszy odczyt tego dnia pokazał 181 g, czyli o 21 g więcej niż cel. Przyrost wynika z trzech wpisów dodanych po zrzucie.

Przy planie weekendu wartości białka w potrawach są szacunkami. Sprawdź wielkość porcji i etykietę produktu, gdy zależy Ci na dokładnym rachunku. Nie przenoś progu statusu „ok” na indywidualną ocenę zdrowia.

## Co zrobić przy rozbieżności

Niezależnie od tego, czy planujesz dzień, tydzień czy weekend, porównuj zapisane posiłki z celem 160 g.

## Zrodla

- `/opt/qbot/app/qbot_food_plan.py` — `PROTEIN_TARGET`, `norms`.
- `/opt/qbot/app/qbot_food_api.py` — status białka i analiza tygodnia.
- `qbot_v2.albert_day_view` — dane z 14.10.2026.
