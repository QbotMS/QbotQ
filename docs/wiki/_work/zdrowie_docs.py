from pathlib import Path
p=Path('/opt/qbot/app/docs/wiki')
# Write only Markdown files inside the wiki.
def put(name, body):
    (p/'zdrowie'/name).write_text(body.strip()+'\n', encoding='utf-8')
put('index.md', '''# Zdrowie i jedzenie

## Co to jest

To miejsce do przeglądu jedzenia, planu energii, ciała i pomiarów zdrowotnych. Część liczb pochodzi z urządzeń, część z wpisów Michała, a plan posiłków i cele są wyliczeniami QBota.

## Po co

Rano można sprawdzić plan dnia, po posiłku uzupełnić dziennik, a wieczorem zobaczyć podsumowanie. Karty Serce i Ciało pomagają zebrać historię do własnego przeglądu lub rozmowy z lekarzem. Wynik aplikacji nie jest diagnozą.

## Skąd dane

Dziennik przyjmuje wpisy ręczne i posiłki z Brokuła. Energia i część pomiarów ciała przychodzi z Garmina lub Withings. Sen pochodzi z Garmina. Potwierdzenia posiłków, okna i suplementów wymagają działania użytkownika. Plan dnia uwzględnia planowany trening oraz tygodniowy cel.

## Jak przejść przez dzień

1. Otwórz kartę **Dziś**. Sprawdź cel kcal, białko, plan jedzenia i trening. To plan/stan na moment odczytu, nie obietnica dokładnego wydatku.
2. Po jedzeniu naciśnij „Zjadłem” przy posiłku albo dopisz pozycję. Wpisy z niepewną porcją mogą być szacowane i można je poprawić.
3. Zamknij dzień, gdy wpisy są kompletne. Samo przekroczenie celu nie przekreśla licznika regularności.
4. W kolejnych kartach sprawdź tydzień, ciało, Serce, suplementy i Passę według potrzeb.

Przykład z bazy za 14.10.2026: zapisano 2604 kcal jedzenia, 185,1 g białka i wydatek 3034 kcal. Rachunek bilansu: 2604 − 3034 = −430 kcal. Są to zapisane/wyliczone dane jednego dnia, nie pomiar zmiany masy.

```mermaid
flowchart LR
  A[Jedzenie i potwierdzenia] --> D[Dziennik dnia]
  B[Garmin i Withings] --> C[Pomiary]
  E[Trening i cel tygodnia] --> F[Plan kcal i paliwa]
  D --> G[Podsumowanie]
  F --> G
  C --> H[Ciało i Serce]
  G --> I[Strona Zdrowie]
  H --> I
```

## Gdzie to widać

Główny ekran ma górny pasek zakładek, tygodniowy pasek planu, plan weekendu, kartę „Dziś” i listę „Zjedzone”. Na dostarczonym zrzucie z 18.10.2026 widać również „Okno 10–20”, „Obwody” i liczniki w nagłówku. Obraz pokazuje konkretny stan tego ekranu, a nie zawsze aktualne dane:

![Ekran Zdrowie: tydzień, weekend, dzienny bilans, okno, obwody i wpisy jedzenia](../img/ekrany/zdrowie.png)

| Co widać na ekranie | Hasło |
|---|---|
| Tydzień, plan deficytu i kafle dni | [Cel kcal](cel-kcal.md) |
| Plan weekendu i przyciski „Zjadłem” | [Plan weekendu](weekend.md), [Brokuł](brokul.md) |
| Kcal, białko, węglowodany i tłuszcz | [Energia](energia.md), [Białko](bialko.md), [Dziennik](dziennik.md) |
| Spalone kcal i pozostałe kcal | [Energia](energia.md), [Cel kcal](cel-kcal.md) |
| „Co jeszcze zjeść” | [Białko](bialko.md), [Paliwo na rower](paliwo-rower.md) |
| Okno 10–20 | [Okno 10–20](okno-10-20.md) |
| Obwody i pomiar talii | [Obwody](obwody.md) |
| Lista zjedzonych wpisów i korekty | [Dziennik](dziennik.md) |
| Passy w nagłówku | [Passa](passa.md) |
| Zakładki Ciało, Serce i Suplementy | [Masa ciała](masa-ciala.md), [Serce](serce.md), [Suplementy](suplementy.md) |
| Sen | [Sen](sen.md) |

## Jak czytać

Zielony pasek w tygodniu pokazuje postęp wobec planu; wynik i etykiety należy czytać razem z zamkniętymi dniami. Wpis „przed nami” nie jest spożyciem. „Zostało” porównuje dzienny cel z dotychczasowym zapisem. Energia z urządzenia jest szacunkiem, a jedzenie bez wpisu nie jest uwzględnione.

Zrzut pokazuje 18.10.2026 między innymi 1155/3100 kcal i 70/160 g białka. Odczyt późniejszy z bazy dla tego dnia daje 1873 kcal i 136,7 g białka; dzienna energia urządzenia ma status częściowy. To różne chwile/stany i nie wolno traktować zrzutu jako aktualnego odczytu.

## Ograniczenia i pułapki

Zrzut ekranu jest automatycznym ujęciem jednej chwili. Widoczne w nim dane mogą być starsze od aktualnej bazy. Część dziennych celów jest prognozą, a część zamkniętego dnia może bazować na danych rzeczywistych. Tętno, ciśnienie, skład ciała i sen z urządzeń wymagają ostrożnej interpretacji.

## Wpływa na / Zależy od

- Dziennik zasila bilans, ocenę celu, Passę i część raportu Trenera.
- Plan kcal i paliwo zależą od danych energii, planu treningów i celu tygodnia.
- Karty Serce, Sen, Ciało i Suplementy zależą od pomiarów lub potwierdzeń.

## Powiązane hasła

- [Forma i Wellness](../forma/index.md)
- [Trener](../trener/index.md)
- [Połączenia Garmin i Withings](../polaczenia/index.md)

## Zrodla

- `/opt/qbot/app/qbot_food_api.py` — `day_card`, `analysis`, `week_analysis`, `body_comp`, `circ_get`.
- `/opt/qbot/app/qbot_food_plan.py` — `day_plan`, `expend`, `week_deficits`.
- `/opt/qbot/app/qbot_heart.py` — reguły karty zdrowia.
- `qbot_v2.intake_logs`, `qbot_v2.intake_items`, `qbot_v2.energy_daily`, `qbot_v2.body_circumference` — odczyty z 14–18.10.2026.
- `img/ekrany/zdrowie.png` — zrzut ekranu z 18.10.2026.''')
put('obwody.md', '''# Obwody ciała

## Co to jest

Obwody to ręcznie wpisywane pomiary talii, bioder, klatki piersiowej, uda, ramienia i szyi. Wykres pozwala porównywać zapisane pomiary w czasie.

## Po co

Jeśli masa z wagi zmienia się z dnia na dzień, pomiar talii w odstępach czasu daje dodatkowy punkt odniesienia. W karcie Serce talia oraz relacja talii do wzrostu są używane jako sygnały w podsumowaniu.

## Skąd dane

Pomiary wpisuje się ręcznie w karcie „Obwody”. Wartość talii jest wymagana, pozostałe pola są opcjonalne. Wpis można poprawić dla danego dnia. Widok danych udostępnia historię do 1500 dni.

## Jak liczone

1. Wybierz dzień pomiaru i wpisz obwód w centymetrach. Kod przyjmuje wartości od 15 do 250 cm.
2. Wpisz co najmniej talię; pozostałe wymiary można zostawić puste.
3. Zapisz. Jeśli istnieje już pomiar z tego dnia, nowy zapis go zastępuje.
4. Porównuj pomiary z podobnych warunków. W karcie Serce talia/wzrost jest obliczana z wysokością 177 cm. Przykład danych z 13.10.2026: talia 109 cm, więc 109 ÷ 177 = 0,616, pokazywane po zaokrągleniu jako 0,62.

<details><summary>Wzór</summary>

Talia/wzrost = obwód talii w cm ÷ wzrost w cm. Dla danych z 13.10.2026: 109 ÷ 177 = 0,6158, czyli 0,62 po zaokrągleniu do dwóch miejsc.

</details>

```mermaid
flowchart TD
  A[Pomiar taśmą] --> B[Wpisz datę i talię]
  B --> C[Dodaj opcjonalne wymiary]
  C --> D[Zapis w historii]
  D --> E[Wykres obwodów]
  D --> F[Talia do wzrostu w Serce]
```

## Gdzie to widać

Na zrzucie ekranu z 18.10.2026 karta „Obwody” znajduje się po prawej stronie, pod kartą „Okno 10–20”. Tekst wskazuje ostatni pomiar: 13.10, talia 109 cm i talia/wzrost 0,62. Przycisk „Zmierz” prowadzi do wpisu pomiaru.

![Karta obwodów na stronie Zdrowie](../img/ekrany/zdrowie.png)

## Jak czytać

Kod karty Serce oznacza talię od 94 cm lub talia/wzrost od 0,50 jako ostrzeżenie, a talię od 102 cm lub relację od 0,60 jako mocniejszy sygnał. To progi wyświetlane przez QBot, a nie diagnoza. Pojedynczy centymetr ani różnica między dwoma pomiarami nie przesądza o zmianie zdrowia.

## Ograniczenia i pułapki

Baza potwierdza jeden zapis obwodów: 13.10.2026. Zrzut pokazuje ten sam wynik. Nie ma więc podstaw do opisania rzeczywistego trendu ani tempa zmiany. Dokładne wskazówki pomiaru taśmą nie zostały potwierdzone w kodzie.

> DO SPRAWDZENIA: instrukcja pomiaru taśmą na stronie i ewentualne dodatkowe reguły prezentacji wykresu obwodów.

## Wpływa na

Karta Ciała oraz część sygnałów w karcie Serce i raporcie dla lekarza.

## Zależy od

Ręcznego pomiaru i wpisania daty. Wartość relacji talii do wzrostu zależy od ustawionego wzrostu używanego przez kartę.

## Powiązane hasła

- [Masa ciała](masa-ciala.md)
- [Serce](serce.md)
- [Energia](energia.md)

## Zrodla

- `/opt/qbot/app/qbot_food_api.py` — endpointy `/circ` i `/body`, walidacja oraz zapis.
- `/opt/qbot/app/qbot_heart.py` — `body_status`, progi talii i talia/wzrost.
- `qbot_v2.body_circumference` — pomiar z 13.10.2026.
- `img/ekrany/zdrowie.png` — karta Obwody.''')
# Add a concrete, date-stamped reading exercise to each existing health topic.
examples = {
'dziennik.md': '''### Przykład krok po kroku

1. Wybierz konkretny dzień i wpisz to, co rzeczywiście zjedzono. Wartość z menu nie jest potwierdzeniem spożycia.
2. Dla 14.10.2026 baza sumuje 2604 kcal i 185,1 g białka.
3. To suma wpisów w dzienniku; nie jest pomiarem urządzenia.
4. Jeśli później poprawisz porcję, suma dnia zmieni się razem z wpisem.

Na zrzucie z 18.10 karta „Zjedzone” pokazuje trzy pozycje, w tym 654, 218 i 283 kcal. Późniejszy odczyt bazy tego dnia wynosi 1873 kcal. To kontrola przyrostu wpisów w czasie, nie błąd rachunku.''',
'energia.md': '''### Przykład krok po kroku

1. Odczytaj jedzenie z dziennika za 14.10.2026: 2604 kcal.
2. Odczytaj wydatek za ten dzień: 3034 kcal.
3. Odejmij wydatek od jedzenia: 2604 − 3034 = −430 kcal.
4. Wynik ujemny oznacza, że zapisano mniej energii niż system przypisał do wydatku.

Na 18.10 energia urządzenia miała status częściowy, z wartością 2397 kcal w odczycie po południu. Kod w takim przypadku może uzupełniać prognozę dnia; nie należy traktować wczesnej liczby jako końcowej.''',
'cel-kcal.md': '''### Przykład krok po kroku

1. Dla minionego, kompletnego dnia kod pobiera rzeczywisty zapis wydatku. 14.10.2026 wynosił on 3034 kcal.
2. Odejmowane jest planowane ograniczenie energii. W tygodniowym planie lekkie dni mają domyślnie 300 kcal, a dni treningowe dzielą pozostały budżet z ograniczeniem 300–900 kcal.
3. Jeśli kalibracja z rozbieżności masy jest gotowa, jest odejmowana; jej maksymalna korekta to 500 kcal w każdą stronę.
4. Prognoza zaokrągla cel do 50 kcal i nie schodzi poniżej 1800 kcal. Rzeczywisty miniony wydatek nie przechodzi zaokrąglenia do 50.

Nie wyliczam celu 14.10 wstecz z samego bilansu: cel, kalibracja i plan tygodnia to osobne składniki.''',
'bialko.md': '''### Przykład krok po kroku

1. Zsumuj białko z zapisanych posiłków. 14.10.2026 baza pokazuje 185,1 g.
2. Porównaj z celem dnia widocznym w karcie. Zrzut z 18.10 pokazuje 160 g.
3. Na tym zrzucie dzienna suma 70 g pozostawia 90 g do celu: 160 − 70 = 90 g.
4. Reguła statusu menu Brokuła uznaje „ok” od 90% celu; przy celu 160 g jest to 144 g. To osobny próg od odczytu „ile zostało”.

W kodzie istnieje także stała celu używana w planie żywienia. Jej wartość różni się między modułami (150 g w `qbot_food_plan.py`, 160 g jako `PROTEIN_TARGET` w API). Nie ujednolicam tych reguł bez rozstrzygającego potwierdzenia interfejsu.''',
'okno-10-20.md': '''### Przykład krok po kroku

1. Dla 14.10.2026 wpisy jedzenia sumują się do 2604 kcal, ale sama suma nie mówi, o której godzinie jedzono.
2. Reguła sprawdza zapisaną porę posiłku: przed 10:00 lub od 20:00 wpis jest poza oknem.
3. Michał może potwierdzić stan do 12:00 następnego dnia. To ręczne potwierdzenie jest osobnym źródłem statusu.
4. Dzień z treningiem co najmniej 90 minut lub wskazanym wyjazdem jest neutralny według reguł passy.

W dostępnych danych nie potwierdziłem statusu okna dla 14.10. Nie wyciągam go z samej sumy kalorii.''',
'paliwo-rower.md': '''### Przykład krok po kroku

1. Sprawdź, czy w planie jest jazda rowerowa trwająca co najmniej 75 minut.
2. Pierwsze 45 minut nie zwiększa tej dokładki.
3. Dla 105 minut zostaje 60 minut: 50 g/h × 60/60 = 50 g węglowodanów.
4. Wynik jest zaokrąglany do 10 g; dla kilku kwalifikujących się jazd wartości są sumowane.

W dziennym zestawieniu 18.10.2026 widnieje jazda 163 min. Weryfikacja długości planu: 163 ≥ 75, czas po pierwszych 45 min to 118 min; obliczenie daje 98,3 g, po zaokrągleniu do 10 g — 100 g. To przykład reguły zastosowanej do czasu pokazanego na zrzucie, nie potwierdzenie faktycznie zjedzonej ilości.''',
'brokul.md': '''### Przykład krok po kroku

1. Importowane menu tworzy zaplanowane pozycje, które czekają na decyzję.
2. Dopiero oznaczenie posiłku jako zjedzonego dodaje go do dnia spożycia.
3. Posiłek przeniesiony do lodówki jest rozliczany w dniu faktycznego zjedzenia.
4. Na zrzucie 18.10.2026 śniadanie, obiad, przekąska i kolacja mają stan „Zjadłem”; widnieje też usunięta propozycja rowerowa z opcją przywrócenia.

Karta podaje 2486 kcal dla planu weekendu; nie oznacza to, że tyle już zjedzono. Baza dla 14.10.2026 potwierdza 2604 kcal dziennych wpisów, ale nie rozdzielam ich na catering i jedzenie własne bez odczytu poszczególnych pozycji.''',
'weekend.md': '''### Przykład krok po kroku

1. Dla soboty i niedzieli QBot przygotowuje cele energii i białka oraz uwzględnia trening.
2. Wygenerowane propozycje można wybierać, poprawiać lub zmieniać porcje.
3. Po zatwierdzeniu plan może pokazać składniki listy zakupów i pozycje w karcie dnia.
4. W zrzucie z 18.10.2026 widoczny jest nagłówek „Plan weekendu” oraz 2486 kcal i odnośnik „zmień”. Ten zrzut nie dowodzi, że plan został zatwierdzony ani że dana wartość jest sumą całego dnia.

Nie znaleziono w krótkim odczycie przykładu historycznego planu weekendu ze statusem zatwierdzenia. Dlatego nie podaję przykładowego jadłospisu jako faktu z bazy.''',
'suplementy.md': '''### Przykład krok po kroku

1. Lista planu określa pozycje i dni, w których są przewidziane.
2. Potwierdzenie „Wszystkie” zapisuje przyjęcie pozycji z poprzedniego dnia, ale nie nadpisuje wcześniejszych ręcznych wyjątków.
3. W bazie są po trzy potwierdzenia dziennie od 13.10 do 17.10.2026; jest to liczba zapisów, nie dowód, że lista zawierała dokładnie trzy pozycje każdego dnia.
4. Porównanie nocy wymaga co najmniej siedmiu potwierdzonych nocy w każdej z porównywanych grup.

Karta pokazuje regularność z 35 dni. Brak wpisu pozostaje niepotwierdzony, a nie automatycznie „pominięty”.''',
'serce.md': '''### Przykład krok po kroku

1. W przypadku ciśnienia kod zbiera serię z maksymalnie 8 dni wstecz od ostatniego pomiaru.
2. Jeśli seria obejmuje co najmniej 3 dni, odrzuca pierwszy dzień, a średnią wylicza z pozostałych odczytów.
3. Średnia poniżej 130/80 ma etykietę „prawidłowe”; 130–134 lub 80–84 to „wysokie prawidłowe”; od 135 lub 85 — „podwyższone”; od 180 lub 110 — pilny sygnał do kontaktu z lekarzem.
4. Pełny protokół zbiera 7 dni, z co najmniej 6 pomiarami rano i 6 wieczorem.

Baza pomiarów suplementów nie jest przykładem dla ciśnienia. Nie podaję bieżącej średniej ciśnienia bez odczytu właściwej serii.''',
'passa.md': '''### Przykład krok po kroku

1. Każdy licznik czyta inny warunek: zamknięcie dziennika, potwierdzenie okna, wykonanie planu lub tygodniowy bilans.
2. Dla dnia jedzenia ważne jest terminowe zamknięcie; przekroczenie celu kcal samo w sobie nie zrywa licznika.
3. Potwierdzenie okna można podać do południa następnego dnia; długi trening i wskazane wyjazdy dają dzień neutralny.
4. Po każdych 7 dniach może dojść jedno zamrożenie, maksymalnie dwa. Zamrożenie chroni licznik przed jednym niezaliczonym dniem.

Przykład z bazy za 14.10.2026 potwierdza 2604 kcal zapisane, ale nie mówi sam w sobie, czy dzień był zamknięty ani czy okno zostało dotrzymane.''',
'masa-ciala.md': '''### Przykład krok po kroku

1. Wybierz pomiar z konkretnej daty, a nie wartość powieloną w szeregu dziennym.
2. Baza ma pomiary masy 103,65 kg (14.10.2026), 102,92 kg (16.10.2026) i 103,04 kg (18.10.2026).
3. Różnice między kolejnymi odczytami to −0,73 kg, a potem +0,12 kg.
4. Tak krótka zmienność nie stanowi potwierdzenia utraty lub przyrostu tkanki. Porównuj dłuższy trend oraz pomiary wykonane w podobnych warunkach.

Od 12.10.2026 w pomiarach składu ciała jest zmiana trybu „Athlete”; porównanie procentu tłuszczu przez tę granicę może mieszać zmianę algorytmu z fizyczną zmianą ciała.''',
'sen.md': '''### Przykład krok po kroku

1. Wynik snu jest odczytem urządzenia, a nie oceną lekarską.
2. Baza pokazuje `sleep_score` 72 za noc z 18.10.2026, 89 za 17.10 i 72 za 16.10.
3. Analiza tygodnia żywienia dzieli noce na wynik co najmniej 70 i wynik poniżej 70.
4. W tych trzech przykładach wszystkie wyniki są w pierwszej grupie; nie wystarczają jednak do wnioskowania o przyczynie ani trendzie.

HRV (zmienność rytmu serca; [słowniczek](../slowniczek.md#hrv)) i tętno spoczynkowe są osobnymi pomiarami i nie należy ich utożsamiać z oceną snu.'''
}
for name, extra in examples.items():
    f=p/'zdrowie'/name
    s=f.read_text(encoding='utf-8')
    marker='## Gdzie to widać'
    if marker in s:
        s=s.replace(marker, extra+'\n\n'+marker, 1)
    f.write_text(s, encoding='utf-8')
# Small, self-contained SVG from verified daily food and energy figures (14-17.10).
svg='''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="330" viewBox="0 0 760 330" role="img" aria-labelledby="title desc"><title id="title">Jedzenie i wydatek energii 14–17 października 2026</title><desc id="desc">Słupki kcal z dziennika i całkowity wydatek. Źródłem są dzienne rekordy bazy; wartości wydatku 14–17 października mają status full.</desc><rect width="760" height="330" fill="#fffdf8"/><text x="24" y="30" font-family="sans-serif" font-size="19" font-weight="bold" fill="#263238">Jedzenie i wydatek · 14–17.10.2026</text><text x="24" y="53" font-family="sans-serif" font-size="12" fill="#58656a">kcal dziennie · porównanie dwóch zapisów, nie pomiar zmiany masy</text><rect x="505" y="18" width="12" height="12" fill="#ed7625"/><text x="523" y="29" font-family="sans-serif" font-size="12" fill="#263238">zjedzone</text><rect x="600" y="18" width="12" height="12" fill="#4d7e2b"/><text x="618" y="29" font-family="sans-serif" font-size="12" fill="#263238">wydatek</text><line x1="70" y1="270" x2="720" y2="270" stroke="#748087"/><line x1="70" y1="205" x2="720" y2="205" stroke="#e4ded3"/><line x1="70" y1="140" x2="720" y2="140" stroke="#e4ded3"/><line x1="70" y1="75" x2="720" y2="75" stroke="#e4ded3"/><text x="20" y="274" font-family="sans-serif" font-size="11" fill="#58656a">0</text><text x="11" y="209" font-family="sans-serif" font-size="11" fill="#58656a">1000</text><text x="11" y="144" font-family="sans-serif" font-size="11" fill="#58656a">2000</text><text x="11" y="79" font-family="sans-serif" font-size="11" fill="#58656a">3000</text>'''
data=[('14.10',2604,3034),('15.10',2249,2535),('16.10',2736,3452),('17.10',2083,2426)]
for i,(d,food,energy) in enumerate(data):
    x=125+i*150
    hf=food/4000*195; he=energy/4000*195
    svg+=f'<rect x="{x}" y="{270-hf:.1f}" width="42" height="{hf:.1f}" fill="#ed7625"/><rect x="{x+46}" y="{270-he:.1f}" width="42" height="{he:.1f}" fill="#4d7e2b"/><text x="{x-3}" y="{265-hf:.1f}" font-family="sans-serif" font-size="11" fill="#263238">{food}</text><text x="{x+43}" y="{265-he:.1f}" font-family="sans-serif" font-size="11" fill="#263238">{energy}</text><text x="{x+8}" y="293" font-family="sans-serif" font-size="13" fill="#263238">{d}</text>'
svg+='''<text x="24" y="320" font-family="sans-serif" font-size="11" fill="#58656a">Źródło: qbot_v2.intake_logs / intake_items oraz energy_daily, rekordy full.</text></svg>'''
(p/'img/zdrowie-energia-20261014-17.svg').write_text(svg,encoding='utf-8')
# Reference the chart in the relevant article.
f=p/'zdrowie/energia.md'; s=f.read_text(); anchor='## Gdzie to widać'; s=s.replace(anchor,'![Porównanie zapisanych kcal jedzenia i wydatku, 14–17.10.2026](../img/zdrowie-energia-20261014-17.svg)\n\n'+anchor,1); f.write_text(s)
