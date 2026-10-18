# Do sprawdzenia

Pozycje nierozstrzygnięte po sprawdzeniu kodu, bazy, plików harmonogramów i dostępnych zrzutów. Pytania o aktywny serwer lub urządzenie pozostają otwarte.

## Pytania do Michała

### Albert — 18.10.2026

- Czy Michał może udostępnić wynik `tools/list` z działającego serwera, aby porównać go z kodem adaptera i architekturą?
- Czy zwykły tekst Telegrama ma docelowo trafiać do Alberta/QBot3, czy ma pozostać przy obecnym handlerze, który przekazuje go do qbot_query? Kod pokazuje bieżący przepływ, ale nie decyzję docelową?

### QExt2 — 18.10.2026

- Czy można potwierdzić częstotliwość i opóźnienie synchronizacji FIT z Hammerhead dla aktywnego konta?
- Czy można pobrać reprezentatywną odpowiedź `/ride-readiness` używaną przez Karoo, aby potwierdzić rzeczywiste wartości `todayFactor`, progu i W′?
- Czy można potwierdzić na danych z urządzenia bieżące ustawienia AUTO/pacing oraz wynik AERO; w tym etapie sprawdzono kod, ale nie pobrano dziennika z Karoo?
- Czy można udostępnić otwarty zrzut zakładki QExt2 w SETUP oraz ekran INFO/KOKPIT 2 z urządzenia? Dostępny `setup.png` pokazuje zakładkę QExt2 zamkniętą.
- Czy można wskazać zapis konkretnej próby bramy? Kod potwierdza limity i weryfikację położenia, ale nie znaleziono przykładu historycznej próby w bazie.
- Czy można potwierdzić zrzut lub zapis pola AERO z Karoo? QBot nie podsumowuje obecnie pól AERO z FIT.
- Czy można udostępnić odpowiedź gotowości oraz dane nawierzchni/punktów/profilu czasu/typowego EF rzeczywiście pobrane przez aktywne Karoo? Kod i filtry są znane, ale nie przechwycono odpowiedzi ani nie potwierdzono jej widoku na urządzeniu.

### Pogoda — 18.10.2026

- Czy Michał może udostępnić dostęp do sprawdzenia: zalogowanego widoku strony ani tego, jak dokładnie QExt2 renderuje każde pole odpowiedzi API; opis interfejsu oparto na aktualnym `pogoda.html` i kodzie endpointów?
- Czy rozszerzyć opisy o charakteru dnia, warunków punktowych, mapy modeli/zespołu, pogody na weekend ani pogody dla ubioru. To widoczne lub wywoływane funkcje poza zakresem ukończonych haseł?

### ModelQ — 18.10.2026

- Do potwierdzenia pozostaje pełny mechanizm zapisu wszystkich rodzajów aktywności do `activity_record`; w tym etapie sprawdzono konsumenta ModelQ i przykłady jazd z 16.10 oraz 18.10.2026.
- Nie sprawdzono zalogowanego ekranu na żywo. Zrzut pokazuje LTP wygładzone 191,2 W i dzienne 190,8 W; odczyt bazy potwierdza oba pola.
- Nie odczytano konkretnego kandydata przełomu mocy i jego decyzji z Telegrama; nie sprawdzono też historii wysłanych pytań o odczucie.
- Automatyczne alerty i propozycje są opisane na podstawie kodu; nie odczytano historii wysyłek Telegrama ani zapisanych odpowiedzi użytkownika.

### Mapa serwisu — 18.10.2026

- Czy można potwierdzić pełną listę zakładek strony `trening.html` i pozostałych ekranów, które renderują zakładki z JavaScriptu?
- Czy Michał może pomóc w weryfikacji: potwierdzić, czy i jak często QBot importuje aktywności ze Stravy oraz pobiera wellness z intervals.icu?
- Czy można potwierdzić konkretne wyzwalacze i odświeżanie danych RWGPS, Open-Meteo, OSM/Overpass, Google Places i Brokuła?
- Czy uzupełnić role pozostałych widoków pomocniczych i sprawdzić, czy istnieją dodatkowe strony poza katalogiem głównym `public`?

### Mapa zależności — 18.10.2026

- Czy Michał może pomóc w weryfikacji: potwierdzić, które ścieżki gotowości i warianty TSB są obecnie pokazywane na każdej stronie; kod korzysta z odrębnych pól `readiness_score`, `readiness_effective`, `tsb_raw`, `tsb_plus` i `tsb_real`?
- Czy można potwierdzić na reprezentatywnych jazdach zgodność W′bal z Karoo/QExt2 i odtworzeniem ModelQ; kod dopuszcza kilka źródeł, ale nie dowodzi ich zgodności dla wszystkich jazd?
- Czy można potwierdzić dokładne sprzężenie publikacji Strava z gotowym raportem jazdy; w tym etapie potwierdzono osobne moduły i mapowanie roweru, nie pełną zależność dla każdej publikacji?

### Forma — 18.10.2026

- Czy Michał może udostępnić dane potrzebne do potwierdzenia: zachowania każdej interakcji wykresów przez zalogowaną stronę WWW; opis oparto na bieżącym HTML/JS?
- Czy Michał może pomóc w weryfikacji: nie zweryfikowano aktualnej definicji ani wyświetlania Body Battery na innych stronach poza wpływem `real_load.py`; w Formie nie znaleziono osobnego widoku?
- Czy Michał może pomóc w weryfikacji: statystyki jazd opisano na podstawie frontu i endpointu; nie pobierano sum z bazy, więc nie podano przykładu liczbowego dla wybranego okresu?

### Raport jazdy — 18.10.2026

- Czy można pobrać mały odczyt bazy dla konkretnej jazdy z dopasowanym planem, aby podać przykład liczbowy porównania planu i wykonania?
- Czy Michał może udostępnić przykład z 04.10.2026, aby porównać go z aktualnym kodem?
- Czy Michał może udostępnić dostęp do sprawdzenia: strony WWW po zalogowaniu; opis widoków oparto na aktualnych plikach HTML/JS oraz danych zapisanych w bazie?
- Wyświetlony IF w raporcie z 18.10.2026 to 0,72, przy widocznym NP 175 W i progu 241 W; dzielenie zaokrąglonych liczb daje około 0,73. Potrzebne są niezaokrąglone wartości wejściowe, by wyjaśnić różnicę.
- Nie odczytano konkretnego raportu z dopasowanym planem ani stanu publikacji Strava dla aktywności z przykładu. Nie wnioskuj o dopasowaniu lub publikacji na podstawie samego raportu.
- Nie potwierdzono kompletnej listy ikon/kart oraz warstw widocznych dla każdego raportu w działającej stronie. Zrzut i statyczny kod potwierdzają główny układ, lecz widoki zależą od danych jazdy.

### Trasy — 18.10.2026

- Czy Michał może udostępnić odczyt potrzebny do sprawdzenia: z bazy publikacji atrakcji dla trasy `komoot-3120318768`; liczby 26 wpisów Wikipedii, 58 obiektów OSM i 9 kandydatów pochodzą z dokumentu Planera z 18.07.2026?
- Czy Michał może udostępnić dane potrzebne do potwierdzenia: na żywo dostępności publicznej Valhalli ani ponownego wyniku dla odcinka S8 wymienionego w dokumentacji naprawy tras?
- Czy Michał może pomóc w weryfikacji: nie uruchamiano strony WWW po zalogowaniu; sprawdzono pliki HTML/JS i kod endpointów, nie pełną interakcję w przeglądarce?
- Czy Michał chce, aby wiki opisała rozjazd wersji czasu przejazdu bez rozstrzygania działającego wyniku na żywo?

### Trasy — pogłębienie 18.10.2026

- Nie udało się zalogować przez `dev_fetch.py`: brak danych logowania WEBAUTH. Zrzuty w `img/ekrany/` wykorzystano jako dowód wyglądu, ale nie potwierdzają działania przycisków ani wszystkich zakładek.
- Nie sprawdzono poprawnego otwarcia `/raport-dzien.html`; dostępny zrzut pokazuje „Brak parametrów (route_id, days)”.
- Bieżącej publikacji atrakcji dla `komoot-3120318768` oraz aktualnej dostępności Valhalli nie potwierdzono. Liczb historycznych nie przedstawiono jako bieżącego wyniku.
- Baza potwierdziła dla `komoot-2251353307` z 17.10.2026 dystans 53,7 km i trzy bliskie czasowo wpisy wersji. Dla przykładu `komoot-3331694546` z 05.10.2026 potwierdzono 182,6 km, 209 segmentów nawierzchni, 3654 próbki wysokości i 23 podjazdy. Odczyt próbek co około 18,3 km wykorzystano w SVG profilu.
- Wpis z poprzedniego etapu o „pełnych osobnych hasłach dla wszystkich trybów i kategorii punktów” pozostaje częściowo otwarty: dokumentacja opisuje tryby czasu i rozdział punktów od atrakcji, ale pełnych, aktualnych list kategorii nie udało się potwierdzić w aktywnym interfejsie.
### Trener — 18.10.2026

- Nie otwarto interaktywnie szczegółów dnia ani edytora ćwiczeń po zalogowaniu. Zrzut potwierdza główny ekran Kalendarza, a kod strony opisuje dostępne akcje.
- Rozbieżność 18.10.2026: zrzut Kalendarza pokazuje 158 planowanych XSS dla trasy, a odczyt sesji ma 156. Nie ustalono źródła różnicy.
- Nie pobrano w tym etapie przykładowego aktywnego celu ani indywidualnych reguł dostępności. Opis celów i reguł opiera się na kodzie; liczby tygodnia i wykonania sprawdzono osobno.
- Nie sprawdzono, czy konkretna wiadomość pogodowa została doręczona ani czy właściciel zaakceptował/odrzucił konkretną propozycję.
- Przykłady bilansu z kafelków Kalendarza widoczne na zrzucie nie zostały porównane z odpowiedzią ekranu Bilans i waga. Nie należy utożsamiać dziennego kafelka z 14-dniową średnią.
- Wykres SVG XSS przedstawia odczytane wartości sesji 14.10, 16.10 i 18.10. Wartość z 18.10 w zrzucie jest zaokrąglona; dokładna wartość w bazie wynosi 157,699996948242.


### Zdrowie — 18.10.2026

- Czy Michał może udostępnić dostęp do sprawdzenia: zalogowanego widoku Zdrowia ani aktualnych stron statycznych; opis interfejsu oparto na kodzie API i dokumentacji?
- Czy Michał może udostępnić odczyt potrzebny do sprawdzenia: tabel suplementów i serca z bazy. Szczegóły tych modułów pochodzą z dokumentów `docs/SUPLEMENTY.md` i `docs/SERCE.md`?
- Czy Michał może pomóc w weryfikacji: nie uzyskano przykładowego historycznego wyniku planu weekendu ani jego rzeczywistego zatwierdzenia; opisano przepływ i dane wejściowe z kodu?
- Czy Michał może potwierdzić faktyczną dostawę porannej wiadomości z planem weekendu?
- Czy Michał może udostępnić dane potrzebne do potwierdzenia: na bazie historii suplementów przykładu regularności ani porównania wpływu na noc?

### Garaż — 18.10.2026

- Nie odczytano bezpośrednio bieżących rekordów bazy SQLite w trybie tylko do odczytu: komponentów, przypisań opon, notatek, fittingu, zakupów, faworytów, obserwacji i rekomendacji. Liczba 68 oraz widoczne przykłady pochodzą ze zrzutu `garaz.png` z 18.10.2026.
- Brak przykładu z rzeczywistego wpisu zakupowego oraz przykładu porównania dwóch konfiguracji fittingu z kompletem wymiarów i datą.
- Nie potwierdzono bieżącej strony po zalogowaniu ani wszystkich zakładek i przycisków. Zrzut pokazuje wyłącznie widok Rower.
- Do dalszego pogłębienia pozostają istniejące hasła `rozpoznawanie-roweru.md`, `wybor-roweru.md`, `kola-opony.md`, `doradca-ubioru.md`, `faworyci-ubioru.md` i `obserwacje-sprzetu.md`; brakuje w nich przykładów z rzeczywistych danych.

- Czy Michał może udostępnić dostęp do sprawdzenia: aktualnego widoku Garażu i Analizy trasy przez zalogowaną przeglądarkę?
- Czy Michał może udostępnić odczyt potrzebny do sprawdzenia: konkretnego wpisu z `qbot_v2.route_kit`, `qbot_v2.route_outfit`, `qbot_v2.route_outfit_fav` ani obserwacji z `garage.db`; hasła opisują przepływ bez przykładu liczbowego tych wyników?
- Czy Michał może udostępnić dane potrzebne do potwierdzenia: pełnego aktualnego układu strony Garażu i liczby rekordów opon. Do hasła Kół i opon nie dodano przykładu z bazy?
### Połączenia — 18.10.2026

- Czy można potwierdzić odczytem aktywnych crontabów/timerów rzeczywiste harmonogramy Garmin, Hammerhead, Withings, Komoot i Strava. Opisy statusu zawierają oczekiwane interwały, nie dowód aktywnej konfiguracji?
- Czy Michał może pomóc w weryfikacji: sprawdzić, czy intervals.icu ma aktywny importer, jakie zapisuje pola i do jakiej tabeli. `qbot_status_checks.CHECKS` nie zawiera osobnego checku tej usługi?
- Czy Michał może pomóc w weryfikacji: odczytać krótki, przykładowy wiersz dla integracji z bazy i zweryfikować widoki Strava/SETUP po zalogowaniu?
- Czy Michał może pomóc w weryfikacji: ustalić, czy osobny opis Hammerhead → Garmin/TACX ma być utrzymywany jako hasło w planie; dodano je do listy na podstawie aktualnego checku Status?

### System — 18.10.2026

- Czy można sprawdzić timer i wynik ostatniej kopii PostgreSQL oraz czy plik kopii istnieje; w etapie potwierdzono skrypt i kontrolę Statusu, nie odczytano bieżącego stanu?
- Czy Michał może pomóc w weryfikacji: potwierdzić, czy `QBOT_LEGACY_USAGE` jest aktywny i czy planowana decyzja z 22.10.2026 została wykonana. Data decyzji w `LEGACY_USAGE.md` jest późniejsza niż data tego etapu (18.10.2026), a kontrola w aktualnym kodzie ma stan `off`?
- Czy można sprawdzić w przeglądarce aktualne działanie powiadomień, demo i motywu; weryfikacja opierała się na kodzie i dokumentach?
- Czy Michał chce, aby w wiki przeprowadzić pełną kontrolę tych pięciu datowanych dokumentów względem kodu?

### System — pogłębienie — 18.10.2026

- `dev_fetch.py` nie uzyskał konfiguracji WEBAUTH, więc nie potwierdzono bieżącego zalogowanego widoku SETUP, zakładki Kontakty ani ustawień dzwonka w przeglądarce.
- Odczyt `qbot_status_checks.py` o 15:17 wykazał, że część odpowiedzi systemd była niedostępna; porównanie z zielonym zrzutem z 14:23 pozostaje nierozstrzygnięte.
- W bazie sprawdzono wyłącznie podsumowanie dzwonka: 3 nieprzeczytane, 30 widocznych nieukrytych wpisów z ostatnich 14 dni, ostatnia zmiana 13:45. Nie odczytano treści tych 3 pozycji.
- Nie sprawdzono pełnej retencji danych we wszystkich tabelach i plikach. Okresy 14 dni (kopie) i 90 dni (historia dzwonka) dotyczą tylko opisanych mechanizmów.
- Zrzut SETUP jest częściowo zasłonięty menu; kategorie po lewej stronie, których nazw nie widać, nie zostały dopowiedziane.
- Dokument `LEGACY_USAGE.md` zawiera przyszłą wobec tego etapu datę decyzji 22.10.2026; jej znaczenie i wykonanie pozostają nieznane.

## Wyjasnione

### Połączenia — pogłębienie — 18.10.2026

- Nie odczytano bieżących rekordów z bazy dla Stravy, Garmina, Withings, Komoot, RWGPS ani Xerta. Liczniki 415/202/122 w `img/ekrany/strava.png` są tylko liczbami widocznymi na dostarczonym zrzucie; nie mają potwierdzonej daty odczytu.
- Harmonogram Garmina wymaga rozstrzygnięcia: `docs/STATUS.md` i kontrola statusu podają sprawdzanie co 10 minut, a `docs/DECISIONS.md` z 08.10.2026 opisuje strażnika co 15 minut i odrzucenie starych wpisów importów. Nie odczytano aktywnego crontaba/timera w tym etapie.
- Nie odczytano działających uprawnień Stravy ani widoku strony po zalogowaniu. Zrzut potwierdza układ, ale nie aktualny stan autoryzacji.
- Nie pobrano przykładu wellness z intervals.icu ani nie sprawdzono bieżących poświadczeń/harmonogramu; kod statusu i importu wellness istnieje, a kod synchronizacji progu wskazuje próg 2%.
- Nie sprawdzono aktualnej konfiguracji webhooka RWGPS ani ostatniego zdarzenia webhook.
- Nie pobrano ostatniego rekordu porównawczego Xerta. Decyzja w `docs/DECISIONS.md` z 07.10.2026 mówi, że benchmark Xerta nie wpływa na ModelQ.

- **Pogoda:** odczyt bazy 18.10.2026 14:40: dla wyprzedzenia 30 min radar miał 0 trafień, 0 fałszywych alarmów, 2 przeoczenia i 958 poprawnych wskazań braku opadu. Wcześniejszy przykład z 10:05 nie jest najnowszy.

- **Albert:** Zapis pamięci próbuje bazy i dopisuje plik JSONL; wyszukiwanie czyta pliki.
- **Albert:** Tabela ma kolumny id, created_at, memory_type, key, value, source i confidence; odczytano też istniejące rekordy. search_memory jest funkcją wyszukiwania.
- **QExt2:** Baza ma kolumny kontroli wiatru; 18.10.2026 jazda 24766557671 zapisała 8743 próbki, medianę 2,4 m/s i 11,4% czasu pod wiatr.
- **QExt2:** Opis QEXT2_CONFIG z 10.10 jest starszy od późniejszych funkcji INFO, AERO i pól FIT; bieżący kod i nowsze dokumenty potwierdzają ten rozjazd.
- **QExt2:** Zapis podsumowania wiatru jest potwierdzony w nowym wierszu bazy z 18.10.2026.
- **Pogoda:** W bazie znaleziono zapis dla 04.10.2026: temperatura 15,8°C, opad 0,0 mm i wiatr 2,6 m/s.
- **Pogoda:** Odczyt 18.10.2026 zwrócił zero zapisanych alertów; nie ma przykładu aktywnego alertu z tego dnia.
- **Pogoda:** nie znaleziono w bazie przykładowego dnia z wartościami CAPE i LI, by krok po kroku odtworzyć klasyfikację charakteru dnia.
- **Pogoda:** wagi oceny weekendowej 0–100, lista miejsc i historyczny wynik rekomendacji nie zostały zweryfikowane.
- **Pogoda:** bieżący ekran doradcy ubioru i przykład rekomendacji na trasie nie zostały sprawdzone.
- **Pogoda:** komplet modeli i wszystkie przedziały kolorów legendy mapy wymagają weryfikacji.
- **Pogoda:** nie znaleziono potwierdzonego przykładu z bazy dla oceny Okna jazdy ani rekomendacji weekendowej; przykłady liczbowe tych wyników wymagają osobnego odczytu.
- **Pogoda:** brak historycznego alertu deszczowego do pokazania jako przykładu; odczyt 18.10.2026 nie zwrócił zapisanych alertów.
- **Pogoda:** nie znaleziono przykładu z bazy dla segmentowej prognozy pogody na trasie przekazanej QExt2.
- **Pogoda:** METEO_ENGINE z 01.07.2026 jest starszy: bieżący kod używa silnika dla raportu, strony i QExt2.
- **ModelQ:** Zrzut mq2.png z 18.10.2026 pokazuje TP, HIE, PP, LTP i porównanie z Xertem.
- **ModelQ:** Odczyt bazy z 18.10.2026 potwierdza sygnaturę TP 240,7 W, HIE 19,97 kJ, PP 988,7 W, LTP 190,8 W; benchmark Xerta ma 230 W, 24,0 kJ, 1090 W i LTP 170,1 W. W zrzucie kafel pokazuje wygładzone LTP 191,2 W, a dopisek wartość dzienną 190,8 W; obie wartości potwierdza osobne pole bazy.
- **ModelQ:** MODELQ.md i PROGI_MODELQ.md są starsze od bieżących zmian; kod, ekran i bieżąca tabela są aktualniejsze.
- **Mapa serwisu:** Crontab z 18.10.2026 zawiera strażnika Garmin co 15 min, Hammerhead→Garmin co 10 min i Withings→Garmin co 15 min; stare wpisy importów QBot v2 są zakomentowane.
- **Forma:** Bieżące zakładki i położenie bilansu są widoczne w forma.html; FORMA_UI_LAYOUT jest starszy.
- **Forma:** hrv_status.py potwierdza okno 7 nocy, bazę do 60 poprzednich nocy, minimum 30 oraz progi 0,5/1,0 odchylenia.
- **Raport jazdy:** Najnowszy raport z 18.10.2026 (24766557671) ma W2; siedem wcześniejszych wierszy go nie ma.
- **Trener:** Crontab uruchamia qbot_trener_notify.py co 15 min; pięć ostatnich wpisów według sent_at (16–18.10.2026) ma ok=true.
- **Garaż:** Bieżący gear_kit.py stwierdza, że zadania serwisowe nie wpływają na wybór roweru; wiki przyjmuje kod, a nie starszy opis OUTFIT_FAVORITES.
- **Trener:** Kod i odczyt z 18.10.2026 potwierdzają sygnały, wagi, bazę osobistą i próg 15. percentyla. Wspólny status dnia ma pierwszeństwo przed progiem.

### Forma — pogłębienie — 18.10.2026

- Nie sprawdzono interakcji wszystkich przycisków, legend i powiększania wykresów w zalogowanej przeglądarce. Opis odpowiada kodowi HTML/JS i API.
- W widoku Forma nie znaleziono osobnej karty Body Battery. Jej wpływ na zmęczenie faktyczne potwierdzono w kodzie, ale nie sprawdzono innego ekranu użytkownika.
- Dla Statystyk nie pobrano przykładu sum kilometrów/czasu z endpointu; przykład w haśle dotyczy XSS z krótkiego odczytu bazy.
- Nie potwierdzono w tym etapie aktualności przykładowego zrzutu przez zalogowaną stronę. Zrzuty są ilustracją dokumentacyjną.

### Zdrowie — pogłębienie — 18.10.2026

- Na zrzucie z 18.10.2026 karta Dziś pokazuje 1155/3100 kcal i 70/160 g białka. Późniejszy odczyt bazy tego dnia pokazuje 1873 kcal i 136,7 g białka; energia ma status częściowy. Są to odczyty z różnych chwil.
- W kodzie progi białka nie są jednolite: `qbot_food_plan.py` definiuje cel 150 g, a API i ekran używają `PROTEIN_TARGET` (zrzut 160 g). Trzeba ustalić, czy to zamierzone rozdzielenie.
- W bazie jest jeden pomiar obwodów: 13.10.2026, talia 109 cm i biodra 112,5 cm. Nie można na tej podstawie opisać trendu.
- Nie sprawdzono zalogowanego widoku WWW, zatwierdzonego historycznego planu weekendowego, pełnych rekordów ciśnienia/ECG ani dokładnych instrukcji wykonywania pomiaru taśmą.

## Albert — kwestie niepotwierdzone (18.10.2026)

- Wynik `tools/list` z działającego serwera MCP; kod adaptera i dokument architektury podają różną liczbę publicznych narzędzi.
- Docelowa decyzja, czy zwykły tekst Telegrama ma korzystać z tej samej drogi Alberta co MCP.
- Rzeczywisty ekran rozmowy Alberta po stronie klienta; dostępne zrzuty pokazują stronę główną, nie rozmowę.
- Udział pytań obsługiwanych przez router i Albert; nie znaleziono potwierdzonego zestawienia produkcyjnego.


## Spójność końcowa — 18.10.2026

- > DO SPRAWDZENIA: rozbudować krótsze hasła do zwyczajowej długości 4–10 KB i dodać krokowe przykłady z bazy dla algorytmów, których przykładów jeszcze brakuje. Średnia długość 151 stron działów wynosi 3 720 bajtów; nie oznacza to, że każde hasło mieści się w wymaganym zakresie.

## System — metaznaczniki — 18.10.2026

- Nie udało się potwierdzić, które funkcje korzystają z grup adresów zakładki Kontakty ani gdzie są zapisane.
