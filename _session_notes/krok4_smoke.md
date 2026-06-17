# Krok 4 smoke

Data: 2026-06-15

## Smoke wykonany
- Zapytanie: `dodaj przypomnienie o testowym spotkaniu jutro o 12:00`
- Wynik: `status=draft_incomplete`
- `WRITE_DRAFT` message nie zawiera już odwołania do `qbot.action_execute`
- W treści jest teraz uczciwy komunikat, że dana operacja nie jest jeszcze wspierana przez automatyczny zapis w `qbot.query`

## Decyzja
- Nie usuwałem `qbot.action_execute` z `tools/list`, bo diagnoza pokazała zbyt duże ryzyko regresji dla częstych write-intentów: kalendarz, przypomnienia, pamięć, planowanie, trening.
