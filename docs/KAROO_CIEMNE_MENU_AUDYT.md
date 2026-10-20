# Karoo: dynamiczne tło QBota + ciemne menu po restarcie — opis do audytu

Sesja: karoo-tlo-2010 (20.10.2026). Dokument opisuje stan na 20.10 ok. 19:30, z podziałem na **ZWERYFIKOWANE** (sprawdzone na żywo na Karoo / serwerze) i **HIPOTEZA** (niesprawdzone). Uzupełnia `docs/KAROO_TLO.md`.

Urządzenie: Karoo 3 (`model k24`, nr `00447GA253070066`), Android 12 (SDK 32), bez roota. QExt2 = `com.qext2.primary`, wydanie (nie debuggable).

---

## 1. Tło ekranu startowego (Home Background)

### 1.1 Jak Karoo trzyma tło — ZWERYFIKOWANE
- Ustawienie globalne Androida `launcher.background.full_url` (+ `launcher.background.thumbnail_url`) = adres obrazka. Odczyt/zapis: `adb shell settings get|put global …`.
- Ekran startowy (`io.hammerhead.launcherapp`) pobiera obrazek przez sieć (Picasso; w APK napisy `launcher.background.*`, `BackgroundItem`, `com/squareup/picasso`). Systemowa tapeta Androida nieużywana (log: brak wallpaper, ustawienia domyślne).
- Zmiana ustawienia działa **od razu** (bez restartu). Przyjmowany dowolny `https://` i `http://127.0.0.1` (test przez `adb reverse`).
- Przełącznik `secure feature.launcher_background=0` istnieje, znaczenie nieznane (nie ruszany).

### 1.2 Geometria — ZWERYFIKOWANE (obrazek gradientowy kal2/kal3 + zrzuty `screencap`)
- Ekran 480×800. Karoo pokazuje **proporcjonalny wycinek** obrazka, powiększony ok. 2,5×. W obrazku 1440×2400: kafel profilu 1 = x 80–481, y 873–1585; widoczne tło = x 0–600, y 793–1613 (to samo proporcjonalnie przy 480×800).
- Ekran: tło 0–669 px; od y≈480 boki zakrywa `bottomBackground` (pasek menu); nazwa profilu w kaflu: tekst x105–225, y567–606 (ekran).

### 1.3 Łańcuch produkcyjny — ZWERYFIKOWANE
1. **QBot rysuje** (`qbot_karoo_tlo.py`, Pillow, czcionka Saira Semi Condensed): zdjęcie, czarny pas pod paskiem statusu, wygaszenie boków, w kaflu: QBot+data, stan dnia, gotowość (`readiness_effective`), świeżość (`tsb_real`) — ostatni dzień `/api/forma/data`, pogoda w oknie najbliższej jazdy `sport='rower'` z `qbot_v2.trainer_session` (bez jazdy: 2 h), „SPRAWDŹ ROWER” gdy `garage.db.bike_task` ma `todo`, logo w prawym dolnym rogu.
2. **QBot wystawia** (`qbot_web.py`, blok `KAROO TLO`, usługa `qbot-web`): `GET /karoo/tlo/<klucz>/aktualny` → `{url, wersja}`; `GET /karoo/tlo/<klucz>/<wersja>.png` (immutable); podgląd `GET /api/karoo/tlo` (właściciel). Klucz w `data/karoo_tlo/token` (600, poza gitem). Wyjątek w bramce logowania dla `/karoo/tlo/`. Przeliczenie najczęściej co 30 min, nowy plik tylko przy zmianie danych (wersja = SHA1 danych, 12 znaków), 5 ostatnich wersji.
3. **QBot podaje adres** Karoo w `ride-readiness` jako `homeBgUrl` (`mcp_server.py`, usługa **`q-bot`**).
4. **QExt2 wpisuje** (`launcher/HomeBackground.kt`, od 0.4.5): zapamiętuje `homeBgUrl`, co 30 min + przy starcie usługi + po jeździe (nigdy w trakcie nagrywania) pobiera `aktualny` i robi `Settings.Global.putString` obu kluczy, tylko gdy url inny. Uprawnienie `WRITE_SECURE_SETTINGS` nadane raz: `adb shell pm grant com.qext2.primary android.permission.WRITE_SECURE_SETTINGS` (stan: `granted=true`, przetrwało reinstalacje `-r`).
- Dziennik jazdy QExt2: `HOMEBG SET|SAME|NO_PERMISSION`, `HOMEBG_FAIL http=…`, `HOMEBG_SKIP`. Potwierdzone: `HOMEBG SET` po restartach i po zmianie danych.
- Commity: QBot `a3b3b6b`, `1a84e2c`; QExt2 `f65c490` (0.4.5).

### 1.4 Do audytu (tło)
- Zdjęcie v1 stałe: `KAROO_TLO_FOTO` (Oppelner Gravelzug D2, 02.08.2026). Pula/rotacja — nie zrobione (decyzja Michała: później).
- Podgląd w Garażu > QExt2 — nie zrobiony (decyzja: później).
- Klucz w adresie trafia do dziennika jazdy tylko jako końcówka pliku (`…/<wersja>.png`), nie w całości — sprawdzić przy przeglądzie `RideFileLog`.

---

## 2. Ciemne menu po restarcie

### 2.1 Fakty — ZWERYFIKOWANE
- Ciemny wygląd menu daje Androidowe „wymuszone ciemne” (`setprop debug.hwui.force_dark true` + `am force-stop io.hammerhead.launcherapp`). Ustawia to tylko powłoka (uid shell); **znika po restarcie**.
- Ustawienia Karoo nie mają ciemnego menu (tylko „in-Ride Dark Mode”). Ukryty `secure feature.auto_dark_mode` — po ustawieniu na 1 Karoo zeruje go przy starcie (flaga z serwera Hammerhead) — ślepa uliczka.
- Skutki uboczne force_dark (zmierzone): pasek menu czarny (jasność 235→27), żółty przycisk startu ciemnobrązowy, cień kafla i warstwa wokół kafla odwrócone na **jasną mgiełkę** (ok. 50% bieli nad tłem), napisy paska statusu zostają białe.

### 2.2 Dlaczego nie bezpośrednio z QExt2 — wnioski
- Aplikacja nie może zmienić `debug.*` (SELinux `debug_prop` tylko dla shell/system) — **reguła Androida, nie test** (QExt2 wydaniowe, `run-as` niedostępne).
- Rozwiązanie: QExt2 łączy się z **własnym adbd przez TLS (debugowanie bezprzewodowe)** i wykonuje komendę jako shell.

### 2.3 Weryfikacja drogi — ZWERYFIKOWANE
1. `settings put global adb_wifi_enabled 1` (z kabla) → adbd: „TlsServer running on port …”, mDNS `_adb-tls-connect._tcp` — **tylko gdy sieć Wi-Fi zatwierdzona na Karoo** (systemowe okno „zezwolić na debugowanie bezprzewodowe w tej sieci?”). Bez zatwierdzenia port się nie otwiera.
2. Klucz zatwierdzony przez USB łączy się po TLS **bez parowania kodem**: test `adb forward tcp:15555 tcp:<port>` + `adb connect 127.0.0.1:15555` z Maca — `device`. (Mac nie dosięga Karoo po sieci: izolacja klientów w sieci gości — `nc` do 192.168.0.40 nieudane.)
3. Osobny klucz dla QExt2: `adb keygen` w `~/karoo_tlo/qk/.android/adbkey` na Macu, zatwierdzony na Karoo przez USB (serwer adb uruchomiony z `HOME=~/karoo_tlo/qk`, okno „zezwól na debugowanie USB”, Michał: zawsze). Konwersja: `openssl pkcs8 -topk8 -nocrypt … -outform DER` → `qext2_key.der`, `openssl req -x509 … -outform DER` → `qext2_cert.der`; wgrane do `/sdcard/Android/data/com.qext2.primary/files/adb/`.

### 2.4 Kod QExt2 — `launcher/DarkMenu.kt` (0.4.6–0.4.9)
- Biblioteki: `com.github.MuntashirAkon:libadb-android:3.1.1` (jitpack, repo dopisane w `settings.gradle.kts`), `org.conscrypt:conscrypt-android:2.5.2`.
- `QAdbManager : AbsAdbConnectionManager` (klucz PKCS8 + cert X.509 z plików powyżej, `setApi(SDK_INT)`).
- `DarkMenu.ensure()` (osobny wątek, wywoływane w pętli 30 min razem z tłem, poza jazdą):
  - raz na uruchomienie Karoo (`Settings.Global boot_count`, zapis `done_boot`), max 3 próby na uruchomienie;
  - bez Wi-Fi → `NO_WIFI` (próba nie liczona; 0.4.8: sprawdzenie w try, uprawnienie `ACCESS_NETWORK_STATE`);
  - `adb_wifi_enabled=1`, 5 s, `autoConnect(ctx, 25 s)` (mDNS), `openStream("shell:setprop debug.hwui.force_dark true && echo QEXT2_OK; am force-stop io.hammerhead.launcherapp")`, czytanie do `QEXT2_OK` (0.4.9: `IOException Stream closed` po komendzie = norma), potem **zawsze** `adb_wifi_enabled=0`;
  - wynik w dzienniku: `DARKMENU SET boot=N | CONNECT_FAIL | ERR:… | NO_KEY | NO_WIFI`; w QExt2PrimaryExtension ponowienie po 60 s przy `CONNECT_FAIL/ERR`.
- Historia: 0.4.6 `fd0c239`; 0.4.7 `cc64d7f` — **pętla padania** (brak `ACCESS_NETWORK_STATE`, wyjątek poza try) — cofnięte instalacją 0.4.6; 0.4.8 `dcbe7d9` naprawa; 0.4.9 `9cd3c2d` odczyt odpowiedzi.
- Testy z restartem (`adb reboot`): boot 344 — `DARKMENU SET` za 1. razem, `adb_wifi=0`, bez padnięć; boot 345 (włączenie przez Michała) — 1. próba `Timed out … host address and port`, 2. po 60 s `SET`.

### 2.5 PROBLEM OTWARTY — powtarzające się pytanie na Karoo
- Michał zgłasza: przy (prawie) każdym włączeniu Karoo pytanie o debugowanie; 20.10 ok. 10 razy. Sieć: jedna, „DWL Guest”, 2,4 GHz, BSSID `2e:87:ba:84:de:dc`.
- Część pytań to skutek testów (kilkanaście restartów i ręczne włączanie `adb_wifi`), ale zgłoszenie dotyczy też normalnego włączenia.
- W logcat przy starcie: `E AdbDebuggingManager: Expected keyStore, but got tag=adbKey` (2×, 18:47:36).
- **HIPOTEZA 1:** AdbDebuggingManager nie odczytuje swojego pliku kluczy/zaufanych sieci (`/data/misc/adb/adb_temp_keys.xml`), więc „zawsze zezwalaj w tej sieci” nie jest pamiętane. Do sprawdzenia w źródłach AOSP 12 (`AdbDebuggingManager.AdbKeyStore.readTempKeysFile`) — czy po tym błędzie ginie lista sieci i czy zapis ją naprawia.
- **HIPOTEZA 2:** to nie okno sieci, tylko okno autoryzacji **klucza** dla połączenia Wi-Fi/TLS (klucz QExt2 ma opis `michals.@MacBook-Air-Michal.local` — wygląda jak Mac). Log z udanego połączenia: `Received WIFI TLS connected key message: … michals.@MacBook-Air-Michal.local`.
- **Pierwszy krok audytu:** ustalić, KTÓRE okno się pokazuje (dokładny tekst / zrzut `adb exec-out screencap -p` w chwili pytania) i porównać z `dumpsys adb` / logcat `AdbDebuggingManager` z tej samej chwili. Bez tego każda poprawka jest strzałem.
- Michał NIE chce rezygnacji z automatu („nie umiem zrobić, to się wycofajmy” odrzucone) — rozwiązanie ma usunąć pytania przy zachowaniu automatycznego ciemnego menu.

### 2.7 ROZWIAZANIE problemu 2.5 — ZWERYFIKOWANE (20.10, ok. 20:50)
- Przyczyna potwierdzona: `adb shell dumpsys adb` — keystore zawiera klucze (Mac, QExt2) z `lastConnection`, ale **zero wpisow zaufanych sieci**, mimo ze Michal zawsze zaznaczal „Always allow on this network”. Karoo nie zapisuje zaufanych sieci (bug systemu) → okno przy kazdym wlaczeniu debugowania. Hipoteza 2 (okno klucza) odpada. Stały port (`setprop persist.adb.tcp.port`) zablokowany przez Karoo.
- Okno (uiautomator): `com.android.systemui/.wifi.WifiDebuggingActivity`, tytul `android:id/alertTitle` „Allow wireless debugging on this network?”, pole `android:id/alwaysUse`, przycisk `android:id/button1` „ALLOW”.
- QExt2 `launcher/DebugDialogClicker.kt` = usluga ulatwien dostepu (tylko pakiet `com.android.systemui`, flagi `flagReportViewIds|flagRetrieveInteractiveWindows`). QExt2 wlacza ja sam (`Settings.Secure enabled_accessibility_services` + `accessibility_enabled=1`, WRITE_SECURE_SETTINGS). Dziala tylko gdy uzbrojona przez DarkMenu (45 s przy starcie) i tylko dla tego okna (id + tytul EN/PL lub klasa okna): zaznacza „Always”, klika ALLOW. DarkMenu dodatkowo odpytuje usluge co 0,5 s przez 20 s.
- Build 365 (`04fc82f`): okno NIE klikniete — bez `flagReportViewIds` `findAccessibilityNodeInfosByViewId` nic nie zwraca. Build 366 (`7452dca`) z flaga + aktywnym sprawdzaniem: po `adb reboot` dziennik `DARKMENU_DIALOG CLICKED` (20:50:02) i `DARKMENU SET boot=349 dialog=CLICKED` (20:50:06); `force_dark=true`, `adb_wifi_enabled=0`, 0 padniec, na wierzchu ekran startowy (okno nie wisi).
- Do audytu bezpieczenstwa: usluga ulatwien dostepu QExt2 jest stale wlaczona (bezczynna poza 45 s przy starcie), zakres pakietu ograniczony do systemui.

### 2.6 Bezpieczeństwo — do oceny
- Prywatny klucz adb QExt2: na Karoo w `/sdcard/Android/data/com.qext2.primary/files/adb/` (dostęp: QExt2 i powłoka adb; inne aplikacje bez dostępu przy scoped storage), kopia na Macu `~/karoo_tlo/qk/`. Klucz daje powłokę adb na Karoo. Rozważyć: przeniesienie do pamięci wewnętrznej aplikacji i skasowanie kopii zewnętrznej, usunięcie kopii z Maca.
- Debugowanie bezprzewodowe włączone tylko na kilka sekund, tylko w zatwierdzonej sieci; w sieci gości izolacja klientów (sprawdzone: Mac nie łączy się z Karoo).
- Na Macu po testach zostały procesy: `python3 -m http.server 8765` i `upl.py` (8766) w `~/karoo_tlo` oraz `adb reverse tcp:8765` — do zamknięcia.

---

## 3. Inne zmiany QExt2 tej sesji (kontekst)
- 0.4.10 `1d04600` INFO bez trasy: wykres siły wiatru (`ws` z `/api/weather/point`, QBot `1027d36`).
- 0.4.11 `91dd361` dziennik: `BIKE_DETECTED`; lampa: `LIGHT_SET … err=`, ponowne podłączenie po DeadObject.
- 0.4.12 `245a600` lampa: tapnięcie → pierwszy tryb przyjęty przez lampę; pacing: pułap od (LTP+CP)/2.
- 0.4.13 `398d31f` bieg Monstera: moc ≥ 50 W, mediana 5 s, zmiana po 3 odczytach, obwód 2,35 m (symulacja 20.10: 346 → 38 zmian).
- `b04d31d` (bez zmiany wersji, `build.gradle.kts` zajęty przez sesję hrv-h10-2010): migawka jazdy tylko przy nagrywaniu, wznowiona stara jazda bez nagrywania odrzucana po 10 s (po restarcie DST pokazywało 21 km).
- Na Karoo zainstalowane **0.4.13 (358)**. Buildy 359–361 (0.4.14 H10, inna sesja) **nie przechodzą** — `b04d31d` czeka na zielony build.
