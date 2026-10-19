---
tytul: Dziennik zmian
dzial: dziennik
typ: przeglad
opis: Dzien po dniu: zakresy prac w QBocie (kto, co, kiedy); szczegolowy rejestr ruchow po wejsciu w dzien.
tagi: [dziennik, changelog, sesje]
synonimy: [log zmian, historia zmian, changelog, co zrobiono]
aktualizacja: 19.10.2026
---

# Dziennik zmian

Dzień po dniu: **co faktycznie robiono**. Kliknij datę, żeby zobaczyć pełny rejestr ruchów tego dnia (każde zajęcie plików, commit i praca w tle). Zbiera się samo; o 23:50 dopisywane jest podsumowanie dnia.

## [19.10.2026](2026-10-19.md)

| Sesja | Co robiono | Godziny | Zmiany |
|---|---|---|---|
| claude-tzfix | forma-cda.js: data lokalna zamiast UTC (audyt) | 07:32–07:33 | 0 commitów, 1 plik |
| wiki-1910 | Bialko 160 wszedzie, paliwo z faktycznego czasu jazdy, wiki Hammerhead do Garmin | 07:36–07:41 | 2 commity, 23 pliki |
| claude-aero | docs/AERO_CDA.md -- pelny opis do audytu | 07:41–08:29 (od 18.10) | 0 commitów, 1 plik |
| albert-tg-1910 | Telegram: tekst zaczynajacy sie od ? lub Albert idzie do Alberta; Forma bez FTP, wiki CP | 07:53–08:34 | 6 commitów, 7 plików |
| dziennik-1910 | Dziennik na dwoch poziomach: Zakresy prac (tabela) + Rejestr ruchow zwiniety pod sesja | 08:42–08:42 | 1 commit, 6 plików |

[Rejestr ruchów 19.10 →](2026-10-19.md)

## [18.10.2026](2026-10-18.md)

Dziś QBot dostał w Formie nowe centrum do porównywania oporu powietrza i toczenia oraz krzywą najlepszej mocy. Raport jazdy korzysta teraz ze wspólnego modelu oporów, a obciążenie tras uwzględnia kalibrację tego modelu. Poprawiono także planowanie treningu z trasą, obsługę sprzętu i podgląd zmian ekranów QExt2. Cotygodniowy przegląd trafia do Telegrama; usunięto stare, nieużywane raporty mailowe. Dodano wyszukiwalną Wiki QBota i powiązanie jej z menu oraz Albertem.

| Sesja | Co robiono | Godziny | Zmiany |
|---|---|---|---|
| bez-nazwy | Trener: klik dnia przy czekajacej zmianie; trasa z Kalendarza zastepuje reczna jazde; pole Trasa w oknie treni…; Trener: klik dnia przy czekajacej zmianie; trasa z Kalendarza zastepuje reczna jazde; pole Trasa; bez dubli ja…; Glikogen: zapas dostepny do jazdy (nogi 57% miesni + watroba) -> param glycogen_ride_capacity_g co noc, ride_g… (+12) | 09:38–21:57 | 15 commitów, 352 pliki |
| dziennik-1810 | Dziennik zmian + auto-aktualizacja wiki | 20:33–20:35 | 1 commit, 12 plików |
| claude-aero | DECISIONS etap B odrzucony; Centrum CdA produkcyjnie; docs Centrum CdA (+4) | 20:38–21:32 | 0 commitów, 11 plików |
| qext2log-1810 | QExt2: log buildow + symulator per build + automat; QExt2 automat: nowe dane pol do symulacji (AI) + test | 20:39–20:58 | 0 commitów, 5 plików |
| wiki-1810 | Albert: narzedzie wiki + ikonki ? + strzalki mapy | 20:40–21:19 | 4 commity, 29 plików |
| claude-mail | Wylaczenie raportow mailowych poza raportem z jazdy (ride_report_notify); Sprzatanie starych raportow mailowych | 21:06–21:18 | 0 commitów, 9 plików |
| wiki-bg | WIKI-QBOT szkice w tle (codex) | 21:37–21:57 | 0 commitów, 1 plik |
| wiki-noc | Wiki + dziennik 18.10.2026 (noc); nocna aktualizacja wiki i dziennika | 23:52–23:52 | 1 commit, 15 plików |

[Rejestr ruchów 18.10 →](2026-10-18.md)

