# QBot -- CURRENT (handoff sesji)


## Sesja 2026-07-06 -- domkniecie Komoot -> Karoo

Zbudowana i zweryfikowana na zywo bramka Komoot -> Karoo (wariant A) z przyciskami
Telegram. Test end-to-end: powiadomienie "TEST 18.05" -> [Analizuj] -> "Zanalizowano:
[Q] TEST 18.05 · 2026-05-18 · #2963663831".

Zrobione: sygnatura nazwy, dedup push (delete-before-create), fix kolejnosci (elevation
po precompute), watcher notify-only + analyze_tour/skip_tour, timer 5 min (User=qbot),
fix elevation.polyline (encoder 1D), callback w telegram_reply_processor (polling) +
poprawka "przyciski zostaja przy bledzie", chown outgoing/komoot na qbot.

Odkrycia: aktywny odbiornik updateow to nie cron (dlugo 409); po restartach 409 znikl.
qbot_api.py ma rownolegly handler webhooka (inna sesja) -- uspiony (brak webhooka).

Do commitu (root): telegram_reply_processor.py, qbot_api.py, docs/DECISIONS.md,
docs/TODO.md, docs/CURRENT.md.
