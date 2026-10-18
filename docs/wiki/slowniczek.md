---
tytul: Słowniczek
dzial: ogolne
typ: pojecie
opis: Wyjaśnia skróty i techniczne słowa używane w wiki QBota.
tagi: [slowniczek, pojecia, skroty, definicje]
synonimy: [co znaczy, definicja, znaczenie skrotu, slownik qbot]
skroty: [CTL, ATL, TSB, TP, NP, IF, XSS]
gdzie_widac: [wiki, Forma, ModelQ, Raport jazdy]
liczby: []
zalezy_od: []
wplywa_na: []
zrodla_kodu: [hasla wiki i ich zrodla]
aktualizacja: 18.10.2026
---

# Słowniczek

## Ogólne

Skróty i pojęcia zebrane niżej są pogrupowane według tematu. Przy każdym haśle znajduje się odnośnik do miejsca, które opisuje je szerzej.

## Albert

Asystent QBota, który może dobierać narzędzia, odczytywać dane i wykonywać dozwolone zapisy. Nie każde pytanie trafia do niego; proste przypadki może obsłużyć router. Zobacz [routing pytań](albert/routing.md).

## AI (sztuczna inteligencja)

Funkcja, która analizuje zapytanie lub wynik na podstawie przekazanych jej danych. W Trenerze może sprawdzić tygodniowy plan, ale wyliczenia planu pozostają po stronie silnika. Zobacz [Trenera](trener/index.md).

## MCP

Protokół komunikacji, przez który zgodna aplikacja może wywołać narzędzia serwera QBota. Publiczne narzędzia MCP i wewnętrzne narzędzia Alberta to różne listy. Zobacz [MCP](albert/mcp.md).

## Routing pytania

Wybór drogi obsługi pytania: regułowy router albo Albert. Zobacz [routing pytań](albert/routing.md).

## Narzędzie Alberta

Funkcja serwerowa, z której Albert korzysta, by pobrać dane lub wykonać dozwoloną operację. Zobacz [narzędzia Alberta](albert/narzedzia.md).

## Pamięć potwierdzonych faktów

Mechanizm zapisu faktu zgłoszonego przez użytkownika. Nie oznacza niezależnej weryfikacji prawdziwości. Zobacz [pamięć Alberta](albert/pamiec.md).

## IF

Wskaźnik intensywności jazdy: NP podzielone przez próg mocy użyty w raporcie. Zobacz [NP i IF](raport-jazdy/np-if.md).

## EF

Współczynnik efektywności jazdy: moc znormalizowana podzielona przez średnie tętno. QExt2 może porównać bieżący wynik z typową wartością z wcześniejszych jazd. Zobacz [dane trasy dla QExt2](qext2/dane-trasy.md).

## NP

Moc znormalizowana, liczona z próbek mocy z uwzględnieniem mocniejszych odcinków. Zobacz [NP i IF](raport-jazdy/np-if.md).

## W1 i W2 raportu jazdy

W1 to policzone fakty raportu; W2 to osobny tekst analizy AI. Zobacz [Analizę jazdy](raport-jazdy/analiza-jazdy.md).

## Aktywność i próbki 1 Hz

Zapis jazdy i jej pomiarów co sekundę, między innymi mocy, tętna i prędkości. Próbki są przechowywane w `qbot_v2.activity_record` i służą do obliczeń opisanych w [mapie zależności](zaleznosci.md).

## ATL

Krótkoterminowe, wygładzane obciążenie treningowe. W bazie występuje w kilku wariantach, np. `atl_raw`, `atl_plus` i `atl_real`; ich znaczenie zależy od miejsca użycia. Zobacz [mapę zależności](zaleznosci.md).

## CTL (obciążenie długie)

Długoterminowe, wygładzane obciążenie treningowe. ModelQ publikuje je w `fitmodel_daily.ctl_xss`; inne obliczenia mogą używać pól `ctl_real`. Zobacz [ModelQ](modelq/index.md).

## Garaż

Moduł z zapisanym sprzętem, w tym rowerami i ubraniami. Część danych znajduje się w osobnej bazie `garage.db`; wynik mapowania roweru może trafić do raportu jazdy. Zobacz [Garaż](garaz/index.md) i [mapę zależności](zaleznosci.md).

## Fitting

Poglądowe porównanie pozycji rowerzysty na rowerze na podstawie geometrii, ustawień i wymiarów. Nie zastępuje pomiaru specjalisty. Zobacz [Fitting](garaz/fitting.md).

## Zapas w Garażu

Szacowana liczba dni do zużycia kupionej rzeczy na podstawie opakowania i tempa zużycia. To prognoza, nie pomiar. Zobacz [przypomnienia zakupowe](garaz/przypomnienia-zakupowe.md).

## Notatka warsztatowa

Wpis właściciela o naprawie lub pracy przy rowerze. Nie zmienia automatycznie stanu części. Zobacz [notatki warsztatowe](garaz/notatki-warsztatowe.md).

## Gotowość

Wynik dzienny oparty na wellness, w szczególności HRV, tętnie spoczynkowym i śnie. Wpis samopoczucia lub choroby może wpłynąć na pole `readiness_effective`. Zobacz [Formę](forma/index.md) i [mapę zależności](zaleznosci.md).

## Body Battery

Wskaźnik Garmina oparty na doładowaniu i zużyciu. W QBocie obecny model używa różnicy zużycia dziennego i doładowania z nocy jako składnika zmęczenia faktycznego; nie jest osobnym kaflem Formy. Zobacz [Body Battery](forma/body-battery.md).

## Zmęczenie faktyczne

Wariant ATL uwzględniający obciążenie treningowe i sygnały stanu ciała. Powiązana świeżość to CTL minus ATL faktyczne. Zobacz [Formę, zmęczenie i świeżość](forma/ctl-atl-tsb.md).

## ATL (obciążenie krótkie)

Szybciej zmieniająca się średnia obciążenia treningowego; w ModelQ jej odpowiednikiem jest obciążenie z krótkiego okna. Zobacz [Formę](forma/ctl-atl-tsb.md).

## HIE

Parametr ModelQ opisujący część sygnatury związaną z wysiłkiem ponad progiem. Kod zapisuje go w kilodżulach; wpływa między innymi na wynik W′ i rozdział obciążenia. Zobacz [ModelQ](modelq/index.md).

## Kotwica ModelQ

Zapisany punkt odniesienia dla TP, HIE i PP, od którego ModelQ wylicza sygnatury kolejnych dni. Kotwica ma opis źródła i datę. Zobacz [kotwice ModelQ](modelq/kotwice.md).

## LTP

Niższy próg mocy wyprowadzany z TP i HIE, a w publikacji wygładzany w czasie. Nie jest tym samym co bieżący TP. Zobacz [LTP](modelq/ltp.md).

## MPA

Szacowana maksymalna moc dostępna w danej chwili, którą ModelQ wylicza ze stanu W′bal. Zobacz [W′bal](modelq/wprime-bal.md).

## HR

Tętno, czyli liczba uderzeń serca w ciągu minuty. W ModelQ jest awaryjnym źródłem obciążenia, gdy miernik mocy jest w kwarantannie. Zobacz [XSS z tętna](modelq/xss-z-tetna.md).

## HRV

Zmienność odstępów między uderzeniami serca, zapisywana jako jedna z miar wellness. Model gotowości porównuje ją z własną bazą z poprzednich dni. Zobacz [Zdrowie](zdrowie/index.md).

## Karoo / QExt2

Urządzenie Karoo i osobny projekt QExt2 przekazują aktywności oraz część pomiarów do dalszej analizy. W raporcie jazdy dane Karoo mogą być odrębnym źródłem W′bal. Zobacz [QExt2](qext2/index.md).

## ModelQ

Model QBota wyznaczający sygnaturę jazdy i obciążenie na podstawie danych treningowych. Wyniki trafiają między innymi do `modelq2_ride` i `fitmodel_daily`. Zobacz [ModelQ](modelq/index.md).

## PP

Moc szczytowa w sygnaturze ModelQ; parametr krzywej, nie rekord z jednej sekundy. Zobacz [PP](modelq/pp.md).

## Próg TP

Próg mocy używany przez ModelQ. W starszych kolumnach występuje pod nazwą CP lub FTP, ale `cp_modelq_w` przechowuje TP. Zobacz [TP](modelq/tp.md).

## TP (próg)

Próg mocy używany przez ModelQ do rozdzielania pracy na zakresy wysiłku. W dokumentacji QBota nie należy nazywać go FTP. Zobacz [ModelQ](modelq/index.md).

## CP

Historyczna nazwa techniczna spotykana w polach QExt2 i starszych zapisach QBota. Przy opisie progu ModelQ używaj nazwy [TP](modelq/tp.md); pole CP zapisane przez QExt2 nie musi być tym samym co TP.

## GPS

System satelitarny, z którego licznik ustala swoje położenie. Pozycja GPS potrzebna jest między innymi do pogody punktowej i sprawdzenia odległości od bramy. Zobacz [pogodę INFO](qext2/pogoda-info.md) i [bramę](qext2/brama.md).

## TSB

Różnica między długoterminowym i krótkoterminowym obciążeniem, używana jako wskaźnik formy/świeżości. QBota zapisuje warianty surowe i skorygowane, dlatego nazwa pola ma znaczenie. Zobacz [mapę zależności](zaleznosci.md).

## Trener

Moduł układający i pokazujący sesje treningowe z uwzględnieniem kalendarza, celów, dostępności, gotowości i pogody. Zobacz [Trenera](trener/index.md).

## Planowane obciążenie

Wartość wysiłku przypisana przez Trenera do zaplanowanej sesji. Może się różnić od obciążenia po rzeczywistym treningu. Zobacz [XSS w Trenerze](trener/xss.md).

## Adaptacja planu

Propozycja zmiany dalszych sesji po porównaniu planu z zapisanym wykonaniem. Warto sprawdzić powód i zdecydować, czy ją przyjąć. Zobacz [adaptację planu](trener/adaptacja.md).

## Okno treningowe

Godziny, w których trening może się zmieścić. Reguła może dotyczyć konkretnych dni lub rodzajów aktywności. Zobacz [dostępność](trener/dostepnosc.md).

## Faza sezonu

Odcinek roku treningowego, na przykład baza, budowa, taper, regeneracja lub roztrenowanie. Zobacz [sezon](trener/sezon.md).

## Sesja z trasą

Jazda planowana w Kalendarzu na podstawie przypiętej trasy. Może zastępować osobny wpis wydarzenia tego dnia. Zobacz [trasy w Treningu](trener/trasy.md).

## W′ (W prime)

Zapas pracy ponad progiem, zapisany jako energia. ModelQ wyznacza go w ramach sygnatury; raport może pokazywać, jak zapas zmieniał się podczas jazdy. Zobacz [ModelQ](modelq/index.md) i [raport jazdy](raport-jazdy/index.md).

## W′bal

Pozostały zapas W′ w trakcie jazdy. Raport może pokazywać wynik z Karoo/QExt2 albo odtworzenie z próbek aktywności; należy czytać także informację o źródle. Zobacz [raport jazdy](raport-jazdy/index.md) i [mapę zależności](zaleznosci.md).

## XSS

Punkty obciążenia Xert liczone w ModelQ. ModelQ dzieli je na Low, High i Peak; istnieje też starszy, oddzielny wynik XSS zapisany przez replay W′bal. Zobacz [ModelQ](modelq/index.md) i [mapę zależności](zaleznosci.md).

## Xert jako benchmark

Oddzielny wynik porównawczy. Według decyzji z 15.10.2026 Xert nie jest wejściem bieżących obliczeń QBota. Zobacz [Xert jako sprawdzian](modelq/xert.md).

## W1 raportu jazdy

Zestaw policzonych faktów o konkretnej jeździe, które raport zapisuje i pokazuje na stronie. W1 może zawierać dane z pomiarów oraz wyniki dodatkowych obliczeń. Zobacz [Analizę jazdy](raport-jazdy/analiza-jazdy.md).

## W2 raportu jazdy

Opcjonalny komentarz AI do faktów zapisanych w W1. W2 może nie powstać dla każdej jazdy i nie zastępuje pomiarów. Zobacz [Analizę AI](raport-jazdy/analiza-ai.md).

## Czas ruchu i czas całkowity

Czas ruchu obejmuje jazdę w ruchu. Czas całkowity uwzględnia także postoje. W raporcie prędkość brutto jest liczona z czasu całkowitego, a netto z czasu ruchu. Zobacz [Analizę jazdy](raport-jazdy/analiza-jazdy.md).

## Warstwa mapy

Sposób kolorowania śladu jazdy na mapie, na przykład według stref mocy albo nawierzchni. Zmiana warstwy zmienia widok danych na mapie, nie zapis samej jazdy. Zobacz [Raport jazdy](raport-jazdy/index.md).


## Wykładnicze wygładzanie

Sposób liczenia średniej, w którym nowszy dzień ma większy wpływ niż starsze dni. ModelQ używa go między innymi do wygładzania LTP. Zobacz [LTP](modelq/ltp.md).

## Punkt kotwiczący

Zapisany parametr odniesienia, od którego ModelQ oblicza dalsze wartości. Zobacz [kotwice](modelq/kotwice.md).

## PDF

Portable Document Format — format pliku, który zachowuje układ raportu i można go otworzyć w przeglądarce lub czytniku dokumentów. Zobacz [zaproszenia dla gości](trasy/zaproszenia-gosci.md).

## GPX

Plik zawierający przebieg trasy lub zapis przejazdu. W route store plik aktywnej trasy i jej historyczne wersje są obsługiwane osobno. Zobacz [magazyn i wersje tras](trasy/store-i-wersje.md).

## OSM

OpenStreetMap — mapa tworzona i aktualizowana przez społeczność. QBot korzysta z jej tagów dróg przy opisie nawierzchni; dane mogą być niepełne lub nieaktualne. Zobacz [nawierzchnię trasy](trasy/nawierzchnia.md).

## POI

Punkt przydatny na trasie, na przykład sklep lub źródło wody. W QBocie punkty logistyczne i atrakcje mają oddzielne warstwy. Zobacz [punkty na trasie](trasy/punkty-na-trasie.md) oraz [atrakcje](trasy/atrakcje.md).

## Route store

Magazyn tras: zapis geometrii, wersji i wyników obliczeń. Zobacz [magazyn i wersje tras](trasy/store-i-wersje.md).

## Model czasu przejazdu

Obliczenie prędkości na odcinkach i przewidywanych krótkich postojów; długie postoje trzeba zadeklarować. Zobacz [czas przejazdu](trasy/czas-przejazdu.md).

## Zrodla

- `/opt/qbot/app/fitmodel/modelq2/xss.py` — nazwy TP, HIE, PP, XSS i sposób obliczania składowych.
- `/opt/qbot/app/fitmodel/modelq2/training_load.py` — obciążenie długie i krótkie oraz ich różnica.
- `/opt/qbot/app/fitmodel/readiness.py` — źródła gotowości i `readiness_effective`.
- `/opt/qbot/app/qbot3/rides/ride_report_builder.py` — źródła XSS i W′bal w raporcie.
- `/opt/qbot/app/qbot3/rides/activity_devices.py` — rozpoznawanie roweru.
- `/opt/qbot/app/qbot3/routes/outfit_advisor.py` — wykorzystanie Garażu w doradcy ubioru.
- `/opt/qbot/app/qbot_trener_engine.py` — dane wejściowe planu Trenera.
# XSS

Punkty obciążenia używane przez ModelQ. W Trenerze służą do opisania planowanego wysiłku oraz porównania go z wykonanym treningiem. Nie są minutami.

# Okno dostępności

Powtarzający się albo jednorazowy przedział dni i godzin, w którym można albo nie można zaplanować treningu. Rodzaj wpisu określa jego rolę.

# Faza sezonu

Część roku treningowego, np. baza, budowa, taper, jazda sezonowa albo roztrenowanie. Faza wpływa między innymi na docelową objętość tygodnia.

# W′ / W prime

Zapas wysiłku ponad próg w modelu jazdy. To pojęcie modelowe, niezwiązane z FTP.

## ICON-EU-EPS

Zespół prognoz pogodowych ICON-EU. QBOT liczy szansę opadu jako udział wariantów przekraczających ustalony próg opadu. Zobacz [prognozę](pogoda/prognoza.md).

## IMGW

Instytut Meteorologii i Gospodarki Wodnej, którego pomiary stacyjne QBot wykorzystuje do oceny wcześniejszych prognoz. Zobacz [sprawdzalność pogody](pogoda/sprawdzalnosc.md).

## MAE

Średni błąd bezwzględny: przeciętna odległość prognozy od późniejszego pomiaru, bez względu na to, czy prognoza była wyższa czy niższa. Zobacz [sprawdzalność](pogoda/sprawdzalnosc.md).

## CSI

Wskaźnik trafności prognozy opadu, który uwzględnia trafienia, fałszywe alarmy i przeoczenia. Poprawne wskazania braku opadu nie zwiększają tego wskaźnika. Zobacz [sprawdzalność prognoz](pogoda/sprawdzalnosc.md).

## Nowcast

Krótka prognoza oparta na aktualnych obrazach i ruchu opadu. W QBocie radarowy nowcast przesuwa ostatni obraz wzdłuż oszacowanego ruchu. Zobacz [radar](pogoda/radar.md).

## OPERA

Europejski kompozyt danych z radarów pogodowych, z którego QBOT pobiera obrazy opadu. Zobacz [radar](pogoda/radar.md).

## WBGT

Wskaźnik obciążenia organizmu upałem, uwzględniający między innymi temperaturę, wilgotność i promieniowanie. Silnik trasy porównuje go z limitem zależnym od nachylenia. Zobacz [pogodę na trasie](pogoda/pogoda-na-trasie.md).

## UTCI

Wskaźnik odczuwalnego wpływu pogody na człowieka. Na trasie uwzględnia także wiatr pozorny związany z jazdą. Zobacz [pogodę na trasie](pogoda/pogoda-na-trasie.md).

## Bias prognozy

Średnia różnica prognozy i obserwacji ze znakiem. Pokazuje, czy model przeciętnie zawyżał czy zaniżał wartość. Zobacz [sprawdzalność](pogoda/sprawdzalnosc.md).

## CAPE

Miara energii dostępnej dla unoszącego się powietrza. Pomaga rozpoznać warunki sprzyjające opadom konwekcyjnym; sama nie oznacza, że burza wystąpi. Zobacz [charakter dnia](pogoda/charakter-dnia.md).

## LI

Wskaźnik stabilności atmosfery. W połączeniu z CAPE może wskazywać warunki sprzyjające rozwojowi chmur. Zobacz [charakter dnia](pogoda/charakter-dnia.md).

## Prognoza zespołowa

Zestaw wariantów prognozy pokazujący rozrzut możliwych warunków. Udział wariantów z opadem jest wynikiem modelu, a nie gwarancją deszczu. Zobacz [mapę modeli](pogoda/mapa-modeli.md).

## Temperatura odczuwalna

Ocena wpływu warunków takich jak wiatr i słońce na odczuwanie temperatury. Nie jest tym samym co temperatura powietrza. Zobacz [warunki punktowe](pogoda/warunki-punktowe.md).

## mm/h

Milimetry opadu na godzinę. Jednostka opisuje natężenie opadu; suma z dłuższego czasu jest podawana w milimetrach. Zobacz [radar](pogoda/radar.md).


## Makroskładniki

Białko, węglowodany i tłuszcze — składniki jedzenia, których ilość QBot zapisuje w gramach. Zobacz [białko](zdrowie/bialko.md) i [dziennik jedzenia](zdrowie/dziennik.md).

## Zamrożenie passy

Zapas, który może ochronić licznik Passy przed przerwaniem po niezaliczonym dniu. W kodzie maksymalny zapas wynosi dwa osobno dla liczników wspierających tę regułę. Zobacz [Passę](zdrowie/passa.md).

## HR

Tętno, czyli liczba uderzeń serca w ciągu minuty. W ModelQ jest awaryjnym źródłem obciążenia, gdy miernik mocy jest w kwarantannie. Zobacz [XSS z tętna](modelq/xss-z-tetna.md).

## HRV

Zmienność odstępów między uderzeniami serca. QBOT porównuje ją z własną historią; różne urządzenia mogą liczyć ją odmiennie. Zobacz [Serce](zdrowie/serce.md).

## Faworyci ubioru

Rzeczy wskazane przez Michała dla stroju na konkretną trasę i dzień. Doradca zachowuje je w jednym zestawie, nawet gdy zgłasza ostrzeżenie o dopasowaniu. Zobacz [faworytów ubioru](garaz/faworyci-ubioru.md).

## Audyt odzieży

Zapisane cechy i oceny odzieży, które doradca łączy z doświadczeniem z jazd. Obserwacje nie zmieniają audytu bez zatwierdzenia przez Michała. Zobacz [obserwacje sprzętu](garaz/obserwacje-sprzetu.md).

## Numer ANT

Identyfikator urządzenia lub czujnika w danych FIT. QBot może użyć go do rozróżnienia rowerów. Zobacz [rozpoznawanie roweru](garaz/rozpoznawanie-roweru.md).

## AUTO QExt2

Tryb, w którym QExt2 na Karoo dobiera strategię na podstawie szacowanej rezerwy na mecie. QBot przekazuje dane startowe, a wybór trybu wykonuje Karoo. Zobacz [tryb AUTO](qext2/tryb-auto.md).

## Developer fields FIT

Dodatkowe pola zapisywane w pliku FIT przez aplikację, która utworzyła plik. QBot tworzy podsumowanie wybranych pomiarów QExt2, a próbki pola AERO zachowuje osobno do porównania z własnym obliczeniem. Zobacz [pola FIT QExt2](qext2/pola-fit.md).

## Pacing

Ocena bieżącej mocy względem wyliczonego pułapu. W QExt2 pułap uwzględnia tryb jazdy i rezerwę. Zobacz [pacing na Karoo](qext2/pacing.md).

## RSRV

Procent rezerwy wyliczany przez QExt2. Tryb AUTO używa zmian RSRV i czasu do mety do wyboru strategii jazdy. Zobacz [tryb AUTO](qext2/tryb-auto.md).

## FIT

Format pliku, w którym licznik zapisuje aktywność i jej próbki. QBot może odczytać z niego także dodatkowe pola QExt2. Zobacz [pola FIT QExt2](qext2/pola-fit.md).

## ETA

Przewidywany czas przyjazdu. QExt2 wykorzystuje czas do mety, gdy szacuje końcową rezerwę w trybie AUTO. Zobacz [tryb AUTO](qext2/tryb-auto.md).

## AERO

Wariant pola QExt2, który pokazuje oszacowanie zmiany związanej z oporem powietrza. Jest obliczeniem QExt2, a nie bezpośrednim odczytem z miernika mocy. QBot zapisuje jego próbki z FIT do osobnego archiwum i używa ich jako porównania, nie jako wejścia do własnego obliczenia CdA. Zobacz [pole dynamiczne](qext2/pole-dynamiczne.md).

## CdA

Współczynnik oporu aerodynamicznego rowerzysty i roweru. Wartość AERO jest szacunkiem z modelu, nie bezpośrednim pomiarem. Zobacz [pole dynamiczne](qext2/pole-dynamiczne.md).

## DYNAMIC

Wariant pola QExt2, który przełącza rotujące wskazania w jednym miejscu na ekranie. Zobacz [pole dynamiczne](qext2/pole-dynamiczne.md).

## KOKPIT 2

Układ pól QExt2 na ekranie jazdy Karoo, dla którego QBot udostępnia ustawienia komunikatów i kolorów. Zobacz [KOKPIT 2](qext2/kokpit2.md).

## Pole dynamiczne

Miejsce w KOKPIT 2, które może pokazywać rotujące wskazania albo szacunek AERO. Zobacz [pole dynamiczne](qext2/pole-dynamiczne.md).

## OAuth

Sposób logowania aplikacji do usługi zewnętrznej za zgodą właściciela konta. QBot używa go między innymi do połączenia ze Stravą. Zobacz [połączenie ze Stravą](polaczenia/strava.md).

## TACX

Rodzaj aktywności, pod którym automat zapisuje w Garminie jazdy przekazane z Hammerheada. Zobacz [przekazanie Hammerhead → Garmin](polaczenia/hammerhead-garmin.md).

## Benchmark

Wynik zewnętrzny używany do porównania. Xert pełni tę rolę wobec ModelQ, ale nie ustala jego parametrów. Zobacz [Xert jako sprawdzian](modelq/xert.md).

## Kod QR

Obraz, który telefon może zeskanować, by odczytać zawartą w nim informację. W QBocie służy do rozpoczęcia ograniczonego dostępu demo. Zobacz [dostęp demo](system/dostep-demo.md).

## Web Push

Powiadomienie wysyłane przez przeglądarkę, także gdy strona QBota jest zamknięta, jeśli użytkownik wcześniej włączył tę funkcję. Zobacz [Centrum powiadomień](system/centrum-powiadomien.md).

## UI2

Wspólny wariant wyglądu stron QBota z jasną i ciemną paletą. Zobacz [paletę UI](system/paleta-ui.md).

## LTHR

Próg tętna używany przez intervals.icu do wyznaczania stref tętna. Zobacz [połączenie z intervals.icu](polaczenia/intervals-icu.md).

## System

- **Audyt tygodniowy** — zaplanowane raz w tygodniu porządki i kontrole QBota.
- **Demo** — ograniczony, czasowy podgląd serwisu przyznawany przez właściciela.
- **Legacy** — starsza część systemu, która może nadal obsługiwać niektóre ścieżki.
- **Retencja** — czas, przez jaki system przechowuje pliki przed ich usunięciem lub przeniesieniem.
- **Token CSS** — nazwana wartość stylu, na przykład kolor tła, używana przez stronę.
- **Web Push** — powiadomienie wysyłane przez przeglądarkę także wtedy, gdy strona QBota jest zamknięta; wymaga wcześniejszego włączenia na urządzeniu. Zobacz [Centrum powiadomień](system/centrum-powiadomien.md).
- **Sesja demo** — czasowy dostęp gościa do ograniczonego podglądu. Nie daje pełnych praw właściciela. Zobacz [Dostęp demo](system/dostep-demo.md).
- **Token palety** — nazwana wartość koloru używana przez stronę, np. kolor tła lub ostrzeżenia. Sam kolor nie przesądza o znaczeniu na każdym ekranie. Zobacz [Paletę UI](system/paleta-ui.md).
- **Stan `off`** — oznaczenie funkcji świadomie wyłączonej w danej kontroli. Nie jest równoznaczne z błędem. Zobacz [Status](system/status.md).
- **Automat** — zadanie wykonywane według harmonogramu bez ręcznego otwierania strony. Sam opis harmonogramu nie potwierdza, że zadanie jest obecnie aktywne. Zobacz [Automaty](system/automaty.md).
- **Wpis na żywo** — przypomnienie, którego widoczność zależy od aktualnego warunku; może samo się zamknąć, gdy warunek zniknie. Zobacz [Centrum powiadomień](system/centrum-powiadomien.md).
- **UI2** — wspólny zestaw kolorów i elementów wyglądu stron QBota, dostępny w motywie jasnym i ciemnym. Zobacz [Paletę UI](system/paleta-ui.md).
- **Kod QR** — dwuwymiarowy kod graficzny, który można zeskanować aparatem telefonu. Zobacz [Dostęp demo](system/dostep-demo.md).
- **Strażnik** — automatyczna kontrola, która obserwuje dane lub prośbę i może wysłać informację, zadać pytanie albo zablokować działanie. Zobacz [dział Strażnicy](straznicy/index.md).
- **P@HR** — moc uzyskiwana przy podobnym tętnie; w QBocie jest wskaźnikiem formy, nie aktywnym strażnikiem miernika. Zobacz [strażnika obciążenia](straznicy/obciazenie.md).
- **Kwarantanna jazdy** — oznaczenie, że wybrane obliczenia pomijają jazdę z podejrzanym miernikiem; trening może nadal być uwzględniony przez obciążenie z tętna. Zobacz [strażnika obciążenia](straznicy/obciazenie.md).
- **Watchdog** — angielska nazwa automatu, który okresowo sprawdza działanie innej funkcji. Zobacz [strażnika Garmina](straznicy/garmin.md).

## Gotowość obiektywna i efektywna

Gotowość obiektywna wynika z HRV, pulsu spoczynkowego i długości snu. Wersja efektywna może dodatkowo uwzględniać samopoczucie i chorobę wpisane w Kalendarzu. Zobacz [gotowość](forma/gotowosc.md).

## Świeżość faktyczna

Różnica między długim obciążeniem a krótkim obciążeniem skorygowanym o sygnały ciała. Nie jest tym samym co świeżość surowa. Zobacz [Formę i świeżość](forma/ctl-atl-tsb.md).

## RHR

Puls spoczynkowy, czyli liczba uderzeń serca na minutę w spoczynku. Zobacz [normę pulsu](forma/norma-tetna.md).

## EWMA

Średnia, w której nowsze dni mają większy wpływ niż starsze. W obciążeniu treningowym używane są różne okresy krótkie i długie. Zobacz [Formę i świeżość](forma/ctl-atl-tsb.md).

## Overpass

Usługa wyszukiwania danych OpenStreetMap. QBot może z niej pobierać informacje o drogach, gdy nie używa lokalnego zestawu danych. Zobacz [nawierzchnię trasy](trasy/nawierzchnia.md).

## Valhalla

Zewnętrzny silnik trasowania, który może zaproponować inny przebieg dla wybranego fragmentu. Propozycja wymaga obejrzenia; nie zmienia automatycznie zapisanej trasy. Zobacz [naprawę tras](trasy/naprawa-tras.md).

## Migawka raportu

Zapis danych użytych przy jednym wyliczeniu raportu. Odtworzenie migawki pokazuje zapisane dane i nie oznacza pobrania nowej prognozy. Zobacz [Analizę trasy](trasy/analiza-trasy.md).

## Wersja trasy

Zapis konkretnego przebiegu trasy. Obliczenia nawierzchni i wysokości odnoszą się do tej wersji, więc po zmianie śladu mogą być potrzebne nowe wyniki. Zobacz [magazyn i wersje tras](trasy/store-i-wersje.md).

## Kwadrat mapy

Pole siatki używane do śledzenia pokrytego obszaru. Nakładka kwadratów jest niezależna od kolorów nawierzchni na trasie. Zobacz [kwadraty na mapie](trasy/kwadraty-mapy.md).


## Zdrowie i jedzenie

Zobacz [dział Zdrowie](zdrowie/index.md).

- **kcal** — kilokaloria, jednostka energii używana przy jedzeniu i wydatku.
- **Makroskładniki (makra)** — białko, węglowodany i tłuszcz w jedzeniu.
- **HRV** — zmienność rytmu serca, czyli różnice czasu między kolejnymi uderzeniami. Zegarek szacuje ją z pomiarów.
- **RHR** — tętno spoczynkowe, najczęściej podawane jako uderzenia na minutę.
- **SpO₂** — szacowany poziom nasycenia krwi tlenem, podawany w procentach. Odczyt z nadgarstka może być niedokładny.
- **Talia/wzrost** — obwód talii podzielony przez wzrost, obie wartości w tych samych jednostkach.
- **Bilans energii** — energia zapisana w jedzeniu minus energia przypisana do wydatku.
- **Dzień neutralny** — nie zwiększa i nie przerywa danego licznika regularności.
- **Zamrożenie passy** — zapas pozwalający utrzymać licznik mimo jednego niezaliczonego dnia, zgodnie z regułą danego licznika.

- **EKG** — elektrokardiogram, zapis elektrycznej pracy serca. Pojedynczy zapis z zegarka nie zastępuje badania lekarskiego.
- **BMI** — wskaźnik masy ciała, wyliczony z masy i wzrostu; u osób z dużą masą mięśniową może być mylący.
- **SpO₂** — szacowany procent nasycenia krwi tlenem. Pomiar z nadgarstka bywa niedokładny.

## Router pytań

Regułowa część QBota, która próbuje rozpoznać proste pytanie i odpowiedzieć bez Alberta. Jeśli pytanie nie pasuje, może zostać przekazane dalej. Zobacz [routing](albert/routing.md).

## Narzędzie Alberta

Czynność serwerowa dostępna Albertowi, na przykład pobranie informacji lub wykonanie dozwolonego zapisu. Lista wewnętrzna nie jest tym samym co lista widoczna w aplikacji MCP. Zobacz [narzędzia Alberta](albert/narzedzia.md).

## Pamięć rozmowy

Zapis faktów lub podsumowań, które mogą być użyte później. W QBot pamięć rozmowy i notatki planowania są oddzielnymi mechanizmami. Zobacz [pamięć Alberta](albert/pamiec.md).

## TACX

Typ aktywności używany w przekazaniu jazdy z Hammerhead do Garmin Connect. W tym przepływie QBot pobiera plik jazdy z Hammerheada, przygotowuje go i przesyła do Garmina. Szczegóły: [Hammerhead → Garmin](polaczenia/hammerhead-garmin.md).

## Wellness

Codzienne pomiary samopoczucia i organizmu, na przykład sen, masa ciała, HRV i puls spoczynkowy. Różne źródła mogą dostarczać różne zestawy danych. Zobacz [Garmin](polaczenia/garmin.md) i [intervals.icu](polaczenia/intervals-icu.md).

## FTP w intervals.icu

Pole progu mocy po stronie intervals.icu. QBot może je aktualizować wartością TP wyznaczoną przez ModelQ. Nie jest to samo w sobie potwierdzenie, że QBot przyjął tę wartość jako własny próg. Zobacz [TP](modelq/tp.md) i [intervals.icu](polaczenia/intervals-icu.md).
