# Do sprawdzenia

Pozycje nierozstrzygnięte po sprawdzeniu kodu, bazy, plików harmonogramów i dostępnych zrzutów. Pytania o aktywny serwer lub urządzenie pozostają otwarte.

## Pytania do Michała

### Albert — 18.10.2026

- Czy zwykły tekst Telegrama ma docelowo korzystać z tej samej ścieżki QBot/Alberta co MCP? (Tak/Nie)

### QExt2 — 18.10.2026

Brak decyzji wymagających odpowiedzi Michała.

### ModelQ — ograniczenia weryfikacji — 18.10.2026

- Zrzut ekranu i kod strony potwierdzają układ, a odczyt bazy potwierdza liczby. Nie uzyskano zalogowanego widoku na żywo, więc kliknięć ani bieżącego działania przycisków nie potwierdzono.
- W tabeli propozycji przełomu nie ma rekordów. Nie ma zatem przykładu decyzji Telegram do opisania.
- Tabele odczuć i historii alertów nie zawierają danych lub nie istnieją przed pierwszym zapisem; kod opisuje reguły, lecz odczyt nie potwierdza faktycznego doręczenia wiadomości.
- Kod importu zapisuje rekordy 1 Hz do `activity_record` po pobraniu aktywności. Nie przeprowadzono pełnego audytu wszystkich importerów ani wszystkich rodzajów aktywności; w hasłach opisano wyłącznie sprawdzony tor ModelQ.

### Mapa serwisu — 18.10.2026

- Czy można potwierdzić pełną listę zakładek strony `trening.html` i pozostałych ekranów, które renderują zakładki z JavaScriptu?
- Czy Michał może pomóc w weryfikacji: potwierdzić, czy i jak często QBot importuje aktywności ze Stravy oraz pobiera wellness z intervals.icu?
- Czy można potwierdzić konkretne wyzwalacze i odświeżanie danych RWGPS, Open-Meteo, OSM/Overpass, Google Places i Brokuła?
- Czy uzupełnić role pozostałych widoków pomocniczych i sprawdzić, czy istnieją dodatkowe strony poza katalogiem głównym `public`?

### Mapa zależności — 18.10.2026

- Czy Michał może pomóc w weryfikacji: potwierdzić, które ścieżki gotowości i warianty TSB są obecnie pokazywane na każdej stronie; kod korzysta z odrębnych pól `readiness_score`, `readiness_effective`, `tsb_raw`, `tsb_plus` i `tsb_real`?
- Czy można potwierdzić dokładne sprzężenie publikacji Strava z gotowym raportem jazdy; w tym etapie potwierdzono osobne moduły i mapowanie roweru, nie pełną zależność dla każdej publikacji?

### Forma — 18.10.2026

- (wyjaśnione poniżej) Interakcje strony sprawdzono w bieżącym kodzie; zalogowany podgląd nie zadziałał, bo `dev_fetch.py` nie znalazł danych logowania WEBAUTH. Nie jest to pytanie do właściciela.
- (wyjaśnione poniżej) Body Battery to w kodzie wejście do skorygowanego zmęczenia. Zrzut Formy nie ma osobnego kafla tego wskaźnika; dostępnych ekranów poza Formą nie da się potwierdzić bez działającego logowania.
- (wyjaśnione poniżej) Przykład obciążenia i świeżości pochodzi z odczytu siedmiu dni z bazy. Odrębne sumy jazd należy czytać jako osobne statystyki; nie utożsamiać ich z punktami obciążenia.

### Raport jazdy — 18.10.2026

- Brak nierozstrzygniętych pytań właścicielskich. Strona została odczytana zalogowanym żądaniem GET, a dostępność poszczególnych kart zależy od danych jazdy.

### Trasy — pogłębienie — 18.10.2026

- Poprawne pobranie danych raportu dnia potwierdzono odczytem GET 18.10.2026; dla Rembertowa z 17.10.2026 odpowiedź zawiera zakres, nawierzchnię i profil, a dostarczony zrzut pokazuje stan bez parametrów.
- Publikacja atrakcji `komoot-3120318768` zawierała w odczycie z 18.10.2026 dziewięciu kandydatów, w tym trzech rekomendowanych; podział ich źródeł nie został sprawdzony.
- Aktualnej dostępności Valhalli i odtworzenia objazdu S8 nie potwierdzono; przykłady historyczne należy traktować jako historyczne.
- Kod próbuje wczytać model czasu v3 z konfiguracji, a tabelę v2 zachowuje jako zapas; starszy opis raportu WWW nadal nazywa model v2.
- Odczyt z bazy potwierdził dla `komoot-2251353307` z 17.10.2026 dystans 53,7 km i trzy bliskie czasowo wpisy wersji; dla `komoot-3331694546` z 05.10.2026 potwierdził 182,6 km, 209 segmentów nawierzchni, 3654 próbki wysokości i 23 podjazdy.
- Pełnych, aktualnych list kategorii punktów nie potwierdzono w działającym interfejsie; hasła opisują zakres potwierdzony kodem i dokumentacją.
### Zdrowie — 18.10.2026

- Czy cel 150 g w piątkowej wiadomości weekendowej ma pozostać osobny względem 160 g na karcie dnia i w analizie tygodnia? TAK = pozostawić osobno; NIE = ujednolicić.
- Czy paliwo ma nadal używać czasu sesji z Kalendarza (18.10: 163 min), czy czasu aktywności z rejestru jazdy (8815 s = 146,9167 min)? TAK = zachować czas Kalendarza; NIE = zmienić podstawę na zapis jazdy.

### Połączenia — 18.10.2026

- Czy osobne hasło „Hammerhead → Garmin (TACX)” ma pozostać w WIKI jako stały opis mostka? TAK = utrzymać osobne hasło; NIE = połączyć jego treść z hasłem Garmin.

## Wyjaśnione

### ModelQ — 18.10.2026

- `qbot_activity_ingest.py` zapisuje próbki z aktywności do `qbot_v2.activity_record`; ModelQ pobiera z tej tabeli próbki mocy 1 Hz przez `fitmodel/modelq2/io.py`.
- Rekordy z 18.10.2026 potwierdzają LTP dzienne 190,8 W i wygładzone 191,2 W; to dwa różne wyniki.
- Odczyt tabeli przełomów nie zwrócił kandydatów; reguła, czas 48 h i zmiana po akceptacji zostały sprawdzone w kodzie.
- Reguły pytania o odczucie i bezpieczników zostały sprawdzone w kodzie; zrzuty ekranów potwierdzają tylko widok, a nie dostarczenie Telegrama.

### Połączenia — pogłębienie — 18.10.2026

- Odczyt bazy potwierdził przykłady Garmina (18.10: HRV 67 ms, puls spoczynkowy 49/min, masa 103,04 kg), Stravy (jazda 24766557671: publikacja `ok`, rower Grail, jedna próba) i Xerta (migawka z 18.10: TP 230,22 W, LTP 170,09 W, W′ 24,0 kJ, PP 1090,45 W). Przykłady w hasłach mają daty.
- Aktywny crontab z 18.10 potwierdza Hammerhead co 10 min (wpis główny i trzy profile), strażnika Garmina co 15 min, Withings→Garmin co 15 min oraz Xert codziennie o 00:15; starsze wpisy importu Garmin są zakomentowane.
- Kod sprawdzenia statusu Garmina nadal opisuje interwał 10 min. Rozjazd z aktywnym crontabem 15 min zaznaczono w hasłach i zgłoszono jako możliwy błąd serwisu w raporcie.
- Zalogowany GET `/strava.html` potwierdził Client ID, Client Secret i przycisk połączenia; GET `/setup.html` potwierdził ramki Strava, Komoot i Hammerhead. Nie odczytywano ani nie zapisywano danych autoryzacyjnych.
- Najnowsze trzy dni wellness zawierały źródło Garmin, nie intervals.icu. Importer intervals.icu i synchronizacja progu istnieją w kodzie; aktywnego harmonogramu wellness, poświadczeń ani świeżego rekordu intervals.icu nie potwierdzono.
- Baza zawiera artefakt `komoot-2251353307` ze źródłem RWGPS i stanem `ok` z 17.10. Nie sprawdzono konfiguracji webhooka u dostawcy ani konkretnego zdarzenia.
- Xert ma aktywny wpis crona i odczytane rekordy z 18.10; zasada, że jest benchmarkiem, nie podstawą ModelQ, wynika z decyzji z 15.10.

- **Albert:** Zapis pamięci próbuje bazy i dopisuje plik JSONL; wyszukiwanie czyta pliki.
- **Albert:** Tabela ma kolumny id, created_at, memory_type, key, value, source i confidence; odczytano też istniejące rekordy. search_memory jest funkcją wyszukiwania.
- **QExt2:** Baza ma kolumny kontroli wiatru; 18.10.2026 jazda 24766557671 zapisała 8743 próbki, medianę 2,4 m/s i 11,4% czasu pod wiatr.
- **QExt2:** Opis QEXT2_CONFIG z 10.10 jest starszy od późniejszych funkcji INFO, AERO i pól FIT; bieżący kod i nowsze dokumenty potwierdzają ten rozjazd.
- **QExt2:** Zapis podsumowania wiatru jest potwierdzony w nowym wierszu bazy z 18.10.2026.
- **ModelQ:** Zrzut mq2.png z 18.10.2026 pokazuje TP, HIE, PP, LTP i porównanie z Xertem.
- **ModelQ:** Odczyt bazy z 18.10.2026 potwierdza sygnaturę TP 240,7 W, HIE 19,97 kJ, PP 988,7 W, LTP 190,8 W; benchmark Xerta ma 230 W, 24,0 kJ, 1090 W i LTP 170,1 W. W zrzucie kafel pokazuje wygładzone LTP 191,2 W, a dopisek wartość dzienną 190,8 W; obie wartości potwierdza osobne pole bazy.
- **ModelQ:** MODELQ.md i PROGI_MODELQ.md są starsze od bieżących zmian; kod, ekran i bieżąca tabela są aktualniejsze.
- **Mapa serwisu:** Crontab z 18.10.2026 zawiera strażnika Garmin co 15 min, Hammerhead→Garmin co 10 min i Withings→Garmin co 15 min; stare wpisy importów QBot v2 są zakomentowane.
- **Forma:** Bieżące zakładki i położenie bilansu są widoczne w forma.html; FORMA_UI_LAYOUT jest starszy.
- **Forma:** hrv_status.py potwierdza okno 7 nocy, bazę do 60 poprzednich nocy, minimum 30 oraz progi 0,5/1,0 odchylenia.
- **Raport jazdy:** Najnowszy raport z 18.10.2026 (24766557671) ma W2; siedem wcześniejszych wierszy go nie ma.
- **Raport jazdy:** Dla jazdy 24766557671 z 18.10.2026 plan ma 50,4 km i 222 m podejść, a wykonanie 53,9 km i 216 m. Plan został dopasowany po pozycji początku śladu i czasie.
- **Raport jazdy:** Dla jazdy 24603122930 z 04.10.2026 („Zakroczym Kolarstwo”) baza potwierdza dopasowany plan: 104,4 km/554 m; wykonanie: 107,2 km/618 m, NP 184 W i IF 0,77.
- **Raport jazdy:** Odtworzenie IF z 8820 próbek daje NP 174,505 W i TP 240,700 W, czyli 0,72499 zaokrąglone do 0,72. Ekran zaokrągla NP i TP do 175 W i 241 W.
- **Raport jazdy:** Zalogowany odczyt GET `/raport-jazdy.html` zwrócił stronę raportu. `dev_fetch.py` nie znalazł WEBAUTH, więc odczyt strony wykonano ciasteczkiem z `QBOT_SESSION`.
- **Raport jazdy:** Rekord publikacji Strava dla 24766557671 ma stan `ok`, jedną próbę i czas 18.10.2026 15:52.
- **Raport jazdy:** Część kart jest warunkowa i zależy od danych jazdy; nie ma jednej stałej listy kart dla wszystkich raportów.
- **Trener:** Crontab uruchamia qbot_trener_notify.py co 15 min; pięć ostatnich wpisów według sent_at (16–18.10.2026) ma ok=true.
- **Trener:** Kod i odczyt z 18.10.2026 potwierdzają sygnały, wagi, bazę osobistą i próg 15. percentyla. Wspólny status dnia ma pierwszeństwo przed progiem.

### Forma — pogłębienie — 18.10.2026

- Interakcje wykresów rozpoznano z kodu strony; próba podglądu przez `dev_fetch.py` nie przeszła z powodu braku danych WEBAUTH. Zrzut jest dokumentacyjnym obrazem ekranu z 18.10.2026, a nie dowodem aktualnego działania kliknięć.
- Body Battery wchodzi do obliczenia faktycznego zmęczenia jako trzydniowy dług doładowania względem zużycia. Zrzut Formy nie zawiera osobnej karty tego wskaźnika; widoków na innych stronach nie udało się sprawdzić bez zalogowania.
- Wartości Formy z 12–18.10.2026 odczytano z bazy. Każdy przykład w hasłach podaje miarę, której dotyczy; statystyki dystansu i czasu nie są tym samym co punkty obciążenia.
- 18.10.2026 baza podaje punktację snu 72, długość 5,73 h, gotowość −0,962, efektywną gotowość −1,112, trzydniową gotowość −0,293, faktyczne zmęczenie 74,5, świeżość −16,5, puls 49 uderzeń/min i masę 103,04 kg. Poprzedni przykład 67 punktów snu był nieprawidłowy i został poprawiony.

## Ograniczenia do dalszej weryfikacji

- Garmin: check statusu oczekuje 10 min, crontab uruchamia strażnika co 15 min.
- Komoot: nie odczytano aktywnego timera ani wyniku jego ostatniego uruchomienia.
- intervals.icu: nie potwierdzono aktywnego harmonogramu wellness, poświadczeń ani świeżego rekordu z tego źródła.
- RWGPS: nie odczytano obecnej konfiguracji webhooka u dostawcy ani ostatniego zdarzenia.
- Strava: odczytano ekran QBota, ale nie aktualny zestaw uprawnień aplikacji w serwisie Strava.

### System — 18.10.2026

- Zalogowany GET Statusu z 18.10.2026 wieczorem podał stan zbiorczy „ok”, aktywne usługi, ostatni import Garmin o 21:15 i ostatnią kopię o 03:23; odczyt pokazywał ostatnią kontrolę Garmin o 21:23. Nie potwierdza to odtworzenia kopii.
- GET API powiadomień z 18.10.2026 zwrócił 19 kategorii, wszystkie jawnie włączone; osobny GET Web Push pokazał trzy zapisane urządzenia i obieg pętli o 21:31 bez nowych pozycji. Nie dowodzi to wyświetlenia wiadomości na urządzeniu.
- GET listy kontaktów zwrócił 2 grupy i 4 adresy łącznie. Dokument SETUP wymienia operacje na grupach, a kod używa ich przy odbiorcach planu i synchronizacji grup RSVP.
- Kod licznika legacy domyślnie jest włączony, jeśli `QBOT_LEGACY_USAGE` nie ma wartości `0`; wzrost liczby adresów w zalogowanym Statusie z 11 o 14:23 do 17 o 21:23 potwierdza, że licznik pracował w tym dniu. Decyzja z 22.10.2026 była w dniu odczytu przyszłym terminem przeglądu, a nie wykonaną zmianą.
- Ręczny odczyt `systemctl` i katalogu kopii nie zadziałał w tym środowisku. Inwentaryzacja systemd z 15.10.2026 potwierdzała aktywny timer kopii tylko na tamten dzień; bieżącego stanu timerów i samego pliku kopii nie potwierdzono.
- `setup.png` przedstawia ciemny motyw, a `status.png` białe tło z ciemnym panelem. Poprzedni opis obu ekranów jako jasnych został poprawiony; Status nie jest pełnym przykładem ciemnego motywu.

- QExt2: GET `/ride-readiness` z tokenem urządzenia zwrócił 18.10.2026 TP 240,7 W, W′ 20,0 kJ i współczynnik dnia 0,889. To odpowiedź serwera używanego przez Karoo, nie potwierdzenie jej odbioru przez konkretny licznik.
- QExt2: aktywny crontab uruchamia Hammerhead→Garmin co 10 minut oraz importer FIT QExt2 co 30 minut. Te harmonogramy nie wyznaczają rzeczywistego czasu od końca jazdy do pojawienia się jej pliku.
- QExt2: odczyt z 18.10.2026 potwierdza osobny zapis 8 819 próbek AERO dla jazdy 24766557671; o 09:57:05 próbka zawiera +95 W, CdA 0,795 i odniesienie 0,470.
- QExt2: dziennik bramy zawiera odpowiedzi „ok” z 16.10.2026 z odległości 26 m i 17 m, ale `127.0.0.1` nie pozwala odróżnić żądania Karoo od lokalnego testu.
- QExt2: 10 najnowszych wspólnych jazd nie wykazuje pełnej zgodności minimum W′bal z Karoo i ModelQ. Dnia 18.10 wartości wynoszą 59% i 58,0%, 16.10 — 40% i 41,0%, a 11.10 — 0% i 6,3%. Różnic nie wyjaśnia samo zaokrąglenie; wyniki pochodzą z odrębnych obliczeń.
- Zdrowie: strona zwraca treść przez zalogowany GET, a odczyty API/bazy potwierdzają przykłady z haseł.
- Zdrowie: różnicę między 2221 a 3182 kcal wyjaśniają trzy wpisy dodane później, o łącznej wartości 961 kcal; zmiana celu wynika z aktualizacji prognozy i zaokrąglenia.
- Zdrowie: plan weekendu 17–18.10.2026 został zatwierdzony 15.10 o 19:21; sam zapis zatwierdzenia nie potwierdza doręczenia wiadomości.
- Zdrowie: dzienniki suplementów potwierdzają regularność, lecz brak pominiętych dawek nie pozwala porównać nocy.
- Zdrowie: seria ciśnienia i przykładowe EKG są dostępne w odczycie karty; tylko jeden zapis obwodów nie wystarcza do trendu.

- Pogoda: kod potwierdza stronę główną, warunki punktowe, charakter dnia, mapę modeli, weekend, ubiór i drogę do API QExt2; zrzuty dokumentują stronę główną oraz pusty widok wyprawy bez trasy.
- Pogoda: mapa wykorzystuje ICON-EU do 120 h, a warstwa szansy ICON-EU-EPS (40 wariantów, próg 0,2 mm/h) do 60 h; progi legend i wagi weekendowej są odczytane z kodu.
- Pogoda: reguły charakteru dnia, Okna jazdy, alertu deszczowego i doradcy ubioru zweryfikowano w kodzie; brak przykładowych archiwalnych wyników z bazy opisano jako ograniczenie, a nie pytanie do właściciela.
- Pogoda: odczyt bazy z 18.10.2026 zwrócił zero zapisanych alertów; odpowiedź API QExt2 jest znana z kodu, ale ekran urządzenia i faktyczne doręczenie nie są potwierdzone.
- Pogoda: odczyt bazy z 18.10.2026 20:30 dla +120 min miał 0 trafień, 0 fałszywych alarmów, 1 przeoczenie i 959 poprawnych wskazań braku opadu; 33 wpisy pamięci podręcznej prognozy trasy nie zawierały danych segmentowych.
- Pogoda: `fitmodel_qext2_ride` potwierdza dla jazdy 24766557671 z 18.10.2026 8743 próbki kontroli wiatru, medianę 2,4 m/s i 11,4% czasu pod wiatr.
- Pogoda: dawnego zestawu 15,8°C / 0,0 mm / 2,6 m/s z 04.10.2026 nie potwierdziły krótkie odczyty bieżących tabel pogodowych; usunięto go z haseł, a brak archiwalnego punktu opisano jako ograniczenie.
- Pogoda: dokument `METEO_ENGINE.md` z 01.07.2026 jest starszy od kodu, który wywołuje silnik trasy także ze strony Pogoda, analizy/planera i API QExt2.

- Trasy: raport dnia pobiera zakres kilometrowy z Planera; przykład Rembertowa z 17.10.2026 został odczytany na żywo 18.10.2026 i opisany w haśle.
- Trasy: publikacja atrakcji dla `komoot-3120318768` miała 9 kandydatów i 3 rekomendowane w odczycie 18.10.2026; historyczne liczby Wikipedii/OSM nie są bieżącym podziałem źródeł.
- Trasy: implementacja czasu próbuje użyć modelu v3 z konfiguracji, a model v2 stanowi zapas; dokumentacja raportu WWW jest pod tym względem starsza.
- Trasy: Valhalla i ponowne wyliczenie objazdu S8 nie zostały potwierdzone, więc te dane pozostają ograniczeniem w wiki, nie pytaniem do właściciela.
- Albert: kod adaptera tworzy sześć publicznych pozycji MCP (pytanie do QBot oraz pięć podglądów odczytowych); architektura opisuje jedną. Wyniku działającego `tools/list` nie pobrano, bo zakres etapu pozwalał tylko na GET, a lista wymaga POST.
- Albert: zwykły tekst Telegrama korzysta z osobnej ścieżki routera zapytań niż adapter MCP. Kod nie rozstrzyga, czy docelowo mają być jednakowe; jedyna decyzja do Michała pozostała w sekcji pytań.
- Albert: nie znaleziono potwierdzonego zestawienia udziału routera i Alberta. Log kodu zawiera pojedyncze miary obsługi, ale nie odczytano agregatu produkcyjnego.
- Albert: dostępne zrzuty obejmują stronę główną, nie okno rozmowy; brak zrzutu opisano jako ograniczenie dokumentacji.

- Forma: 18.10.2026 wartości liczbowe sprawdzono w krótkim odczycie bazy; gotowość obiektywna, efektywna i trzydniowa to różne wyniki.
- Forma: kod potwierdza, że Body Battery zasila korektę faktycznego zmęczenia przez dług z trzech nocy; w zrzucie Formy nie ma jej osobnej karty.
- Forma: skład, filtry, zakresy i interakcje wykresów opisano na podstawie aktualnych plików HTML/JavaScript; próba odczytu zalogowanej strony nie powiodła się z powodu braku danych WEBAUTH, więc faktycznego kliknięcia nie potwierdzono.

### Garaż — pogłębienie — 18.10.2026

- Odczyt tylko do odczytu potwierdził 4 rowery, 72 wpisy części (68 aktywnych, 4 nieaktywne), 16 opon, 3 ustawienia fittingu, 2 pomiary ciała i 1 notatkę. Licznik 68 na zrzucie i zalogowanej stronie oznacza aktywne części, więc różnica z 72 wpisami ogółem nie jest błędem serwisu.
- Rzeczywisty zakup odczytany 18.10.2026: ramiona korby SRAM Force XPLR E1 DUB Wide kupione 16.10 za 599,16 zł, wariant 160 mm. Druga aktywna pozycja listy jest planowana.
- Porównano dwa pełne ustawienia fittingu Grizla z datą 01.01.2025. Ich wartości są opisane w haśle; bieżący wpis z 24.09.2026 nie zawiera wszystkich wymiarów.
- Odczytano listę faworytów dla 11.10.2026 (2 rzeczy), propozycje ubioru dla 18.10.2026, obserwacje sprzętu (6 uwag, 18 obserwacji, 15 podsumowań) i rekomendację roweru dla Rembertowa z 18.10.2026.
- Zalogowane pobranie strony Garażu oraz listy zakupów zadziałało. Sprawdzono elementy strony i odpowiedzi odczytowe, lecz nie klikano wszystkich zakładek i przycisków; brak interaktywnego testu opisano jako ograniczenie w hasłach.
- Dwie bieżące pozycje zakupowe nie mają konfiguracji opakowania, więc brak rzeczywistej prognozy przypomnienia jest ograniczeniem danych, nie nierozstrzygniętym pytaniem.
- Kod wyboru roweru nie przekazuje bieżących zadań serwisowych jako kryterium; starszy opis wymieniał je jako wejście. Hasło odnotowuje rozbieżność na korzyść kodu.

### Zdrowie — pogłębienie — 18.10.2026

- Zrzut z 18.10.2026 pokazuje pięć wpisów o łącznej wartości 2221 kcal i 148 g białka. Późniejszy odczyt o 20:45 zawiera trzy dodatkowe wpisy (715 + 120 + 126 = 961 kcal), więc suma wynosi 3182 kcal i 181 g białka; prognoza wydatku wzrosła z 3928 do 3977 kcal, a zaokrąglony cel z 3350 do 3400 kcal.
- Zalogowany GET `/zdrowie.html` działa. Plan weekendu 17–18.10.2026 został zatwierdzony 15.10 o 19:21; późniejsza karta dnia pokazała śniadanie 551 kcal jako zjedzone, a pozostałe propozycje jako pominięte.
- Odczyt bazy/API potwierdził trzy aktywne suplementy, wpisy od 12.10 do 17.10.2026 i 100% regularności w bieżącym oknie. Porównanie wpływu na noc nie ma grupy „pominięte” (9 przyjęć, 0 pominięć).
- Odczyt karty Serca z 18.10.2026 pokazał średnią serii ciśnienia 125/81 oraz trzy zapisy EKG w ostatnich 30 dniach. Najnowszy zapis z 17.10 ma rytm zatokowy, tętno 55/min i HRV 43 ms.
- Baza zawiera tylko jeden pomiar obwodów: 13.10.2026, talia 109 cm i biodra 112,5 cm; trendu nie da się policzyć.

### Trener — pogłębienie — 18.10.2026

- Odczyt bazy potwierdził aktywne cele oraz indywidualne reguły dostępności. Przykłady i daty podano w hasłach Cele oraz Dostępność.
- Różnica opisana wcześniej jako 158 planowanych XSS wobec 156 w bazie wynikała z błędnego odczytu: zielony wiersz Kalendarza pokazuje wykonanie 157,699996948242 XSS zaokrąglone do 158; plan osobno wynosi 156.
- Kod pokazuje, że zakres szczegółów dnia, edycji sesji, zestawu ćwiczeń i korekty pogody jest dostępny w interfejsie. Dostarczony zrzut pokazuje jednak tylko główny Kalendarz; nie potwierdza wyglądu tych paneli ani dostarczenia wiadomości Telegram.
- Bilans w kafelku dnia i 14-dniowy bilans z widoku „Bilans i waga” są odrębnymi zakresami; w tym etapie nie porównano ich odpowiedzi liczbowych z API.
- Kod powiadomień ma dziennik prób, a wcześniejszy odczyt pięciu ostatnich wpisów wykazał `ok=true`; nie jest to potwierdzenie wyświetlenia wiadomości na telefonie.
- Odczyt aktualnego dziennika 18.10.2026 potwierdził plan tygodnia i dzień z wynikiem `ok`; odczyt pamięci podręcznej nie zawierał aktualnej propozycji pogody. Historyczne doręczenie i odpowiedź właściciela nie są przechowywane w tych odczytanych pozycjach.

## Ograniczenia niepotwierdzone

### QExt2 — 18.10.2026

- > DO SPRAWDZENIA: nie potwierdzono, czy konkretne aktywne Karoo odebrało ostatnią odpowiedź gotowości ani ustawienia trasy, punktów, planu czasu i EF; nie ma potwierdzenia zwrotnego od urządzenia.
- > DO SPRAWDZENIA: nie ma zrzutu otwartej zakładki QExt2 w SETUP ani ekranu INFO/KOKPIT 2. Dostępny `setup.png` pokazuje ekran Powiadomienia; zakładka QExt2 jest tylko widoczna w górnym pasku.
- > DO SPRAWDZENIA: nie potwierdzono lokalnych ustawień AUTO/pacing na aktywnym Karoo, jego chwilowego pułapu, koloru pola ani wyświetlonych komunikatów.
- > DO SPRAWDZENIA: brak przechwyconej prognozy INFO z konkretnej trasy i godziny oraz przykładowej odpowiedzi planu czasu odebranej przez urządzenie.
- > DO SPRAWDZENIA: log bramy zapisuje adres `127.0.0.1`, ale nie identyfikuje aplikacji, która wysłała żądanie.
- > DO SPRAWDZENIA: dziennik ani rekord podsumowania nie zawierają czasu zakończenia jazdy i pojawienia się pliku FIT; nie da się policzyć rzeczywistego opóźnienia synchronizacji.
- > DO SPRAWDZENIA: rekordy FIT nie podają wprost, który kanał dostarczył konkretny plik; harmonogram importu nie ustala źródła pojedynczej jazdy.
- > DO SPRAWDZENIA: dostępne podsumowania pokazują różnice minimum W′bal między QExt2 i ModelQ, ale nie rozstrzygają, jaki poziom różnicy byłby oczekiwany dla niezależnych obliczeń.

### Zdrowie — 18.10.2026

- > DO SPRAWDZENIA: kod nie potwierdza, czy poranna wiadomość weekendowa została odebrana na telefonie; potwierdzenie planu w bazie dowodzi zapisu planu, nie dostarczenia wiadomości.
- > DO SPRAWDZENIA: dostępny kod i strona nie zawierają potwierdzonej instrukcji położenia taśmy ani pozycji pomiarowej; hasło zaznacza to ograniczenie.
- > DO SPRAWDZENIA: 18.10.2026 Kalendarz ma sesję 163 min, a zapis jazdy 8815 s (146,9167 min). Okno korzysta z czasu zapisu jazdy, paliwo z czasu Kalendarza. Dane i bieżące reguły są potwierdzone; nie potwierdzono, który czas ma być docelową podstawą paliwa.

## Albert — ograniczenia weryfikacji (18.10.2026)

- Nie pobrano odpowiedzi działającego serwera MCP: w tym etapie dozwolony był tylko GET, a lista wymaga POST. Kod adaptera zwraca sześć pozycji, dokument architektury opisuje jedną.
- Dostępne zrzuty nie pokazują rozmowy Alberta. Nie odczytano też porównywalnego zestawienia produkcyjnego udziału routera i Alberta.
- Są to ograniczenia dostępu lub danych, nie pytania do Michała. Jedyna decyzja do Michała znajduje się w sekcji „Pytania do Michała”.


## Spójność końcowa — 18.10.2026

- > DO SPRAWDZENIA: rozbudować krótsze hasła do zwyczajowej długości 4–10 KB i dodać krokowe przykłady z bazy dla algorytmów, których przykładów jeszcze brakuje. Średnia długość 151 stron działów wynosi 3 720 bajtów; nie oznacza to, że każde hasło mieści się w wymaganym zakresie.

### Strażnicy — 18.10.2026

- > DO SPRAWDZENIA: odczytać stan systemd `qbot-nutrition-watchdog.timer` i potwierdzić, czy codzienny timer 08:00 jest aktywny. Połączenie z systemd nie było dostępne.
- > DO SPRAWDZENIA: sprawdzić log wysyłek porannego strażnika żywienia; kod i baza potwierdzają przykłady wpisów, nie dostarczenie konkretnego alertu.
- > DO SPRAWDZENIA: potwierdzić w logach odbiór Telegrama dla alertów `real_load_guard` i `modelq_guard`. W bazie istnieje zapis `SILA` z 16.10.2026; sama obecność rekordu nie dowodzi doręczenia wiadomości.
- > DO SPRAWDZENIA: tabela `qbot_v2.modelq_guard_log` nie istniała podczas odczytu, więc brak rzeczywistego przykładu alertu z bezpiecznika ModelQ.
- > DO SPRAWDZENIA: odczytać aktywność timerów systemd strażnika Garmina i żywienia. Definicje timerów znaleziono, ale systemd nie udostępnił stanu runtime.

### Audyt kompletności — 18.10.2026

- > DO SPRAWDZENIA: crontab konta `qbot` nie był czytelny z bieżącego konta; porównać jego harmonogramy po uzyskaniu dostępu do odczytu.
- > DO SPRAWDZENIA: sprawdzić aktywność runtime timerów `qbot*`; inwentaryzacja potwierdziła definicje plików, nie ich stan aktywny.
- > DO SPRAWDZENIA: obejrzeć po zalogowaniu wygenerowaną listę Planera wyposażenia, kalibrację zdjęć, formularz po użyciu przycisku sklepowego i stronę gościa. Dostępne zrzuty nie pokazują wszystkich tych stanów.
- > DO SPRAWDZENIA: znaleźć potwierdzenie rzeczywistego doręczenia wiadomości o zmianie prognozy dla gościa; kod potwierdza mechanizm, nie konkretny e-mail.
- > DO SPRAWDZENIA: określić, czy `pogoda-foto/podglad.html` jest wyłącznie planszą pomocniczą czy używanym przez właściciela ekranem; z kodu widocznego w katalogu nie ustalono ścieżki wejścia.
- > DO SPRAWDZENIA: odświeżyć `_indeks.json` poza tym etapem. Zasada tego zadania dopuszcza zapis wyłącznie `.md` i `.svg`, więc nowo dodane hasła nie mogły zostać dopisane do pliku JSON.
- > DO SPRAWDZENIA: naprawić dwa istniejące odnośniki w `straznicy/cialo.md` i `straznicy/zywienie.md`; wskazują odpowiednio `zdrowie/gotowosc.md` i `zdrowie/zywienie.md`, których nie ma w wiki. Wskazać właściwe hasła po sprawdzeniu kontekstu.
- > DO SPRAWDZENIA: w Plannerze wyposażenia obejrzeć wygenerowaną listę dla konkretnej wyprawy i porównać wskazane kategorie z regułami stylu „lekko” oraz „ciężko”.
- > DO SPRAWDZENIA: potwierdzić pola uzupełniane po użyciu „Dodaj do QBota” w każdej wspieranej przeglądarce.
- > DO SPRAWDZENIA: obejrzeć stronę gościa i stronę potwierdzenia wyprawy na żywo; dostępne zrzuty nie pokazują ich zawartości.
- > DO SPRAWDZENIA: otworzyć zakładkę Garaż → QExt2 i zachować zrzut symulatora wraz z logiem zmian; dostępny obraz pokazuje tylko główny widok Garażu.


## Nocna aktualizacja wiki — 18.10.2026

- Odczytać z bazy konkretny wynik Centrum CdA (CdA/Crr) dla wskazanej jazdy oraz sprawdzić widok zalogowany i zrzut otwartej zakładki.
- Odczytać z bazy konkretny punkt krzywej mocy z datą jazdy i sprawdzić widok zakładki Forma → Krzywa mocy.
- Potwierdzić treść faktycznie wyświetlanego podziału energii i substratu po zmianie na próg ModelQ.
- Sprawdzić aktualne zachowanie symulatora QExt2 i logiki KOKPIT 2 po niezapisanych zmianach WWW.
- Potwierdzić zmiany w nowej zakładce Forma Statystyki/krzywa przy wszystkich pięciu seriach na ekranie.
- Nie zweryfikowano widoku i wyników połączenia Strava dla rodzaju jazdy „Poligon w Rembertowie” ani tytułu nadpisanego przez użytkownika.
- Sprawdzić widoczny dla właściciela opis zapasu glikogenu dostępnego do jazdy: kod rozdziela pojemność całkowitą i pojemność nóg z wątrobą, a commit podaje 423 g dostępne z 674 g dnia 18.10.2026; brak dedykowanego hasła.
- Sprawdzić, gdzie w Formie i powiadomieniach jest pokazywany wskaźnik P@HR po zmianie strażnika miernika oraz czy próg tętna (LTHR) ma zmienione znaczenie w interfejsie.
- Sprawdzić wpływ dzisiejszych zmian `fitmodel/season.py`, `fitmodel/telegram_notify.py` i `qbot3/rides/ride_report_facts.py` na widoki/wiadomości właściciela; same nazwy plików nie wystarczają do wiarygodnego opisu.
