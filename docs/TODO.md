# QBot — TODO

> Rzeczy do zrobienia, żeby nie uciekły. Najnowsze na górze.
> To NIE jest CONTEXT.md (auto-gen) ani DECISIONS.md (decyzje). Tu leżą otwarte zadania.

---

## Bramka walidacji treści POI/warstw + auto-wznawianie pobierania (odłożone 2026-07-03)

**Kontekst / dlaczego:** Telegram melduje „✅ Analiza zakończona. Dane zapisane w DB", nawet gdy dane są ucięte/śmieciowe. Przyczyna (potwierdzona na kodzie):
- `route_precompute_orchestrator._run_job` oznacza warstwę `complete`, jeśli writer NIE rzucił wyjątku — nie sprawdza treści.
- `route_precompute_trigger._precompute_complete` → ✅, gdy wszystkie warstwy `complete` (+ surface/frames OK). Zero walidacji zawartości.
- `technical_completeness=COMPLETE` mierzy tylko pokrycie fragmentów pobierania (missing_chunks), nie poprawność treści.
- Liczniki `summary` liczą listę PRZED obcięciem — mogą się rozjeżdżać z tym, co realnie w DB (był bug `[:15]/[:12]` w analizatorze, już podniesiony do `[:200]`).

**Do zbudowania:**
1. **Bramka walidacji z odczytem zwrotnym z DB** po każdej warstwie (progi per warstwa):
   - POI: zaopatrzenie sięga ~≥90% dystansu trasy; ≥1 punkt w każdej tercji; atrakcje po bramce jakości.
   - nawierzchnia: pokrycie ~100% węzłów osi; frames > 0.
2. **Auto-wznawianie (ograniczone) — tylko braki transientne:**
   - Jeśli `missing_chunks` obecne (sieć/timeout/throttle) → pętla celowanego retry (analizator MA już: retry ×3 + backoff, bisekcję, `retry_payload_json`, `merge`, wejście `retry_mode`/`retry_chunk_id`) + scalanie; limit np. 2–3 rundy.
   - Jeśli bramka nie przechodzi, a `missing_chunks` puste (COMPLETE-ale-zły-content = BŁĄD LOGIKI, jak dawny cap) → NIE wznawiać (odtworzy ten sam bubel); **eskalować do człowieka**.
3. **Uczciwy komunikat Telegram:** ✅ tylko po przejściu bramki; inaczej ⚠️ z konkretem („zaopatrzenie tylko do 48/106 km", „POI: brak w Q3"); pokazywać realne liczby (sklepy X, atrakcje Y, % nawierzchni), nie suche „Dane zapisane w DB".

**Zakres plików:** `qbot3/routes/route_precompute_orchestrator.py`, `qbot3/artifacts/route_analyzer.py` (retry/merge już są), `scripts/route_precompute_trigger.py` (komunikat + gating). Decyzja przed kodem: najpierw plan progów.
