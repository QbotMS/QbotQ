---
tytul: Tryb NAGRANIE (film z ekranu Karoo)
dzial: qext2
typ: funkcja
opis: Jak nagrać ekran Karoo „w trakcie jazdy” w domu, bez roweru, tak żeby nic nie trafiło do QBota, ModelQ ani Stravy.
tagi: [qext2, karoo, demo, nagranie, film, trailer]
synonimy: [tryb demo, tryb nagrania, nagranie ekranu karoo, demo do filmu, trailer qbot]
skroty: [FIT, W′bal, ETA, adb]
gdzie_widac: [Karoo, SETUP QExt2, Garaż, QExt2]
liczby: [60 s, 1 Hz, 180 s]
zalezy_od: [symulator.md, kokpit2.md, pogoda-info.md]
wplywa_na: [dziennik-jazdy.md, brama.md, autotest-karoo.md, pola-fit.md]
zrodla_kodu: [scripts/qext2_demo_scenario.py, fitmodel/qext2_demo.py, qbot_activity_ingest.py ingest_one _already mark_demo_skipped, fitmodel/fit_ingest.py ingest_fit_file, scripts/trigger_modelq_after_ride.py, web/public/qext2-nagranie.js, web/public/qext2-makieta.html, qext2 demo/RecMode.kt, qext2 demo/RecDemo.kt, qext2 demo/RecPolicy.kt]
aktualizacja: 21.10.2026
---

# Tryb NAGRANIE (film z ekranu Karoo)

Tryb NAGRANIE służy do jednej rzeczy: nagrania kilku sekund prawdziwego ekranu Karoo „w trakcie jazdy” do filmu o QBocie — w domu, bez roweru i bez czujników. Pola QExt2 pokazują wtedy gotowy, zmyślony scenariusz jazdy, a QExt2 nic nie wysyła do QBota.

To **inny przełącznik** niż „KOKPIT 2 i STATS v2: dane demo”. Tamten służy do projektowania pól i zostaje bez zmian. Działa od QExt2 0.4.20 (21.10.2026).

## Co widać na Karoo

Wszystkie trzy ekrany ożywają z jednego scenariusza (60 s w pętli, nowa klatka co sekundę):

- **KOKPIT 2** — komunikat „za 0,8 km: podjazd”, potem moc rośnie, rezerwa [W′bal](../modelq/wprime-bal.md) spada i pojawia się „BOMBA”, na szczycie „ODBUDOWA”, na zjeździe ok. 50 km/h; dalej ostrzeżenie o deszczu i zmiana nawierzchni. Działają też [pole dynamiczne](pole-dynamiczne.md), strzałka wiatru, belka trasy i [ETA](../slowniczek.md#eta).
- **STATS v2** — NP, IF, rezerwa, XSS, plan czasu, okna PRZEBIEG i TEMPO.
- **INFO** — trasa, przewyższenie i pogoda na trasie.

Czas w scenariuszu jest przyspieszony, żeby cały podjazd zmieścił się w minucie. Liczby na ekranie są realistyczne.

W prawym górnym rogu pól pali się mała czerwona kropka — znak, że tryb jest włączony. Do kadru można ją ukryć.

## Prywatność

Scenariusz jest zmyślony. Nie ma w nim współrzędnych, nazw miejsc ani wagi. Próg mocy jest umowny (CP 250 W), nie Twój. Brama zawsze pokazuje „za daleko”. Pogoda INFO też jest zmyślona: w tym trybie Karoo nie pyta QBota o pogodę dla swojego położenia.

**Uwaga:** mapa Karoo pod polami KOKPIT 2 pochodzi z samego Karoo. Pokaże okolice domu, więc na nagranie wyłącz GPS na Karoo albo przytnij kadr do samych pól.

## Czego tryb NIE robi (bezpieczeństwo danych)

| Co | W trybie NAGRANIE |
|---|---|
| [Dziennik jazdy](dziennik-jazdy.md) | nie powstaje i nie jest wysyłany |
| HRV z pasa H10 | pas nie jest uruchamiany, nic nie jest wysyłane |
| [Brama](brama.md) | dotknięcie nie otwiera bramy (pokazuje „BŁĄD · tryb nagrania”) |
| [Autotest Karoo](autotest-karoo.md) | raport nie jest wysyłany |
| Sygnał jazdy (radar deszczu, pogoda INFO) | nie jest wysyłany |
| Plik jazdy (FIT) | gdy ktoś wciśnie START, każda sekunda ma pole `qext2_demo = 1` i nic więcej z QExt2 |

QBot pomija plik z `qext2_demo = 1`. Taka jazda nie trafia do bazy jazd, ModelQ, raportu jazdy, statystyk ani Telegramu „Nowa jazda”. Ślad zostaje w tabeli plików z dopiskiem „jazda z trybu NAGRANIE QExt2 – pominięta”.

**Strava i intervals.icu** dostają jazdę z Garmina bez udziału QBota, więc tego znacznika nie widzą. Dlatego jazdę nagrania trzeba **odrzucić na Karoo**. Najprościej nie wciskać START, bo pola rysują się także bez nagrywania jazdy, a plik jazdy wtedy w ogóle nie powstaje.

Gdy tryb jest wyłączony, QExt2 działa dokładnie jak wcześniej: wszystko jest wysyłane, a pola `qext2_demo` w pliku nie ma. Sprawdza to test `RecPolicyTest` w QExt2.

## Jak włączyć i wyłączyć

1. Na Karoo otwórz ustawienia QExt2 (SETUP).
2. Karta **„Tryb NAGRANIE (film, bez roweru)”**: przycisk **Włącz** albo **Wyłącz**. Tryb nie wyłącza się sam.
3. Po zmianie wyjdź z ekranu z polami i wejdź na niego ponownie.
4. Kropka: gdy tryb jest włączony, w tej samej karcie jest przycisk „Ukryj kropkę na polach” albo „Pokaż kropkę na polach”.

## Nagranie ekranu — krok po kroku

1. Włącz tryb NAGRANIE (jak wyżej). Wyłącz GPS na Karoo albo zaplanuj przycięcie mapy.
2. Wejdź na stronę jazdy z KOKPIT 2. **Nie wciskaj START.**
3. Na Macu nagrywaj ekran Karoo przez USB: `adb shell screenrecord` (najwyżej 180 s na plik) albo `scrcpy` z zapisem. Pliki trafiają do `~/Movies/QBot-trailer/karoo/`. Długie nagrania idą przez kolejkę lokalną.
4. Nagraj po 20–30 s KOKPIT 2, STATS v2 i INFO oraz jedno ujęcie z przechodzeniem między ekranami.
5. Jeśli START został wciśnięty: zatrzymaj jazdę i **ODRZUĆ** ją (nie zapisuj).
6. **Wyłącz tryb NAGRANIE** w SETUP QExt2.

## Ten sam scenariusz w symulatorze (Garaż)

W Garażu, zakładka QExt2, jest przycisk scenariusza **„🎬 Nagranie (trailer)”**. Odtwarza ten sam plik, który gra Karoo, więc można obejrzeć film przed nagraniem.

Scenariusz ma jedno źródło: skrypt `scripts/qext2_demo_scenario.py`. Zapisuje on ten sam plik w dwóch miejscach: dla symulatora (`/qext2-sim/demo-nagranie.json`) i dla QExt2 (`assets/demo_nagranie.json`, wchodzi do APK). Podgląd przebiegu daje opcja `--podglad`, a zgodność obu kopii sprawdza `--check`.

## Ograniczenia

- Zmiana trybu działa po ponownym wejściu na stronę z polami.
- Mapa Karoo nie należy do scenariusza: to prawdziwa mapa urządzenia.
- Zmiana scenariusza w skrypcie trafia na Karoo dopiero z nowym buildem QExt2.

## Powiązane hasła

- [Symulator QExt2](symulator.md)
- [KOKPIT 2 i ustawienia](kokpit2.md)
- [Pola FIT QExt2](pola-fit.md)
- [Dziennik jazdy](dziennik-jazdy.md)
- [Brama](brama.md)
- [Autotest Karoo](autotest-karoo.md)

## Zrodla

- `scripts/qext2_demo_scenario.py` — scenariusz (jedno źródło).
- `fitmodel/qext2_demo.py` — rozpoznanie pliku jazdy z `qext2_demo = 1`.
- `qbot_activity_ingest.py` (`ingest_one`, `mark_demo_skipped`, `_already`), `scripts/trigger_modelq_after_ride.py`, `fitmodel/fit_ingest.py` (`ingest_fit_file`) — pomijanie przy imporcie.
- `web/public/qext2-nagranie.js`, `web/public/qext2-makieta.html` — scenariusz w symulatorze.
- QExt2: `demo/RecMode.kt`, `demo/RecDemo.kt`, `demo/RecPolicy.kt` oraz zmiany w polach, `QExt2PrimaryExtension.kt` (FIT, start i koniec jazdy), `RideLogUpload.kt`, `H10Recorder.kt`, `KarooHealth.kt`, `GateController.kt`, `SetupActivity.kt`; kontrakt `docs/KONTRAKT_DANYCH.md` pkt 6.
- Testy: `tests/test_qext2_demo.py` (QBot), `RecPolicyTest.kt` (QExt2).
