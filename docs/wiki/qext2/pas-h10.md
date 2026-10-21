---
tytul: Pas Polar H10 na Karoo
dzial: qext2
typ: automat
opis: QExt2 sam włącza zapis odstępów między uderzeniami serca w pamięci pasa Polar H10 i po jeździe przekazuje je QBotowi.
tagi: [polar, h10, pas, hrv, karoo, bluetooth, pamięć pasa]
synonimy: [pas polar, polar h10, h10, pas tętna, pobierz z pasa, zapis rr, hrv z paska]
skroty: [RR, BLE, ANT+]
gdzie_widac: [Karoo, SETUP QExt2, Telegram Nowa jazda, Dziennik jazdy]
liczby: [1 nagranie w pasie, 4 próby po 30 s, 3 próby na końcu, 60 dni znaczników]
zalezy_od: [qext2/dziennik-jazdy, qext2/przeplyw-jazdy]
wplywa_na: [forma/hrv-z-jazdy]
zrodla_kodu: [QExt2 hrv/H10Recorder.kt, QExt2 setup/SetupActivity.kt, mcp_server.py _qext2_hrv_rr, qbot_v2.qext2_hrv_rr]
aktualizacja: 21.10.2026
---

# Pas Polar H10 na Karoo

## Co to jest

Automat w QExt2, który steruje pamięcią pasa Polar H10: na starcie jazdy włącza zapis, a po jeździe pobiera nagranie i wysyła je do QBota. Telefon i aplikacje Polara nie są potrzebne.

## Po co

Pas zapisuje odstęp między każdymi dwoma uderzeniami serca (RR). Z tego QBot liczy [HRV z jazdy](../forma/hrv-z-jazdy.md), czyli próg tlenowy bez testów. Karoo dostaje w tym czasie zwykłe tętno przez ANT+, jak z każdego pasa.

## Jak działa

- **W trakcie jazdy nie ma połączenia Bluetooth z pasem.** Pas zapisuje do własnej pamięci (jedno nagranie, ok. 20 h).
- **Pas sam nie zapisuje** — według dokumentacji Polara zapis trzeba uruchomić z zewnątrz. Robi to QExt2.
- **Start jazdy:** krótkie połączenie po zapamiętanym adresie Bluetooth. Stare nagranie z pasa: jeśli to jazda bez kopii, najpierw pobranie, potem usunięcie; następnie „zacznij zapis” z identyfikatorem `QX<czas startu>`. Pas nie wstał — próba co 30 s, razem 4.
- **Koniec jazdy:** stop zapisu, pobranie, plik na Karoo, wysyłka do QBota (Karoo samo czeka na internet). Po potwierdzeniu odbioru plik znika, zostaje znacznik na 60 dni.
- **Pamięć pasa czyszczona dopiero na starcie kolejnej jazdy**, gdy dane są bezpieczne w QBocie albo w pliku na Karoo.
- **Pas musi być „obudzony”**: czujnik wpięty w zwilżony pasek i założony. Odpięcie czujnika kończy zapis, niczego nie kasuje.

## Gdzie to widać

- **Karoo:** komunikaty „H10 zapis ✓”, „H10: zapis nie ruszył”, „H10 pobrane ✓ N uderzeń”, „H10: nie pobrano”.
- **SETUP QExt2 → karta „Pas Polar H10”:** „Zezwól na Bluetooth”, „Znajdź pas”, „Sprawdź połączenie” (stan zapisu, nagrania w pamięci, bateria), „Pobierz z pasa” (bez nowej jazdy, np. gdy Karoo wyłączono zaraz po jeździe; pasa nie czyści), „Zmień pas”.
- **Telegram „Nowa jazda”:** linijka „HRV z pasa” — pobrane / nie dotarło (→ Pobierz z pasa) / zapis nie ruszył.
- **Dziennik jazdy:** wpisy `H10_…` (połączenie, bateria, start, pobranie, wysyłka).

## Jak czytać

Nic nie przepada: najgorszy przypadek to opóźnienie do następnej jazdy. Brak linijki „HRV z pasa” na Telegramie = jazda bez pasa.

## Decyzje i historia

- 20.10.2026: wdrożenie (QExt2 0.4.14–0.4.16, build 365). SDK Polara 8.4.0-java17 (działa na Androidzie 12 w Karoo 3), minSdk 26.
- 0.4.15: łączenie po adresie Bluetooth — w tle Android nie pozwalał wyszukać pasa po numerze (2× brak połączenia na starcie).
- Michał: HRV nie jest potrzebne w trakcie jazdy, tylko po; zwykle wyłącza Karoo zaraz po zapisaniu jazdy — stąd przycisk „Pobierz z pasa” i status na Telegramie.
- Test na kanapie 20.10: start 7 s, pobranie i wysyłka 184 uderzeń / 150 s.

## Ograniczenia i pułapki

- Połączenie na końcu jazdy raz trwało 58 s (na starcie 2 s) — do obserwacji.
- Aktualizacja Karoo może zresetować zgodę na Bluetooth.
- Bateria pasa (CR2025): ostrzeżenie na Telegramie przy ≤20%.

## Powiązane hasła

- [HRV z jazdy](../forma/hrv-z-jazdy.md)
- [Dziennik jazdy](dziennik-jazdy.md)
- [Przepływ jazdy](przeplyw-jazdy.md)

## Zrodla

- QExt2 `app/src/main/kotlin/com/qext2/primary/hrv/H10Recorder.kt`, `setup/SetupActivity.kt` (karta H10)
- `mcp_server.py` `_qext2_hrv_rr`, tabela `qbot_v2.qext2_hrv_rr` (`sql/hrv_rr_v1.sql`)
- `docs/HRV_JAZDA.md`, `docs/TODO.md` [HRV-JAZDA]
