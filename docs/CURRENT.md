# QBot -- CURRENT (handoff sesji)


## Sesja 2026-07-17 (2) -- Raport trasy: proza LLM (split+retry) + Szczegoly UI + kalendarz dzwonek

Pelna decyzja: docs/DECISIONS.md (wpis 2026-07-17 (2)). Raport: docs/RAPORT_WEB.md
(sekcje "Proza LLM raportu (_report_prose)" i "Zakladka Szczegoly trasy").

WYKONANE (na zywo, zweryfikowane):
- Raport trasy -- pusta Strategia/Ubior/Opony: przyczyna = drugi (duzy) call LLM w _report_prose
  (qbot_web.py) czasem sie urywal (model rozumujacy wlicza reasoning do budzetu tokenow) i cala
  proza planu leciala na None (brak fallbacku). FIX (decyzja 1+2): rozbicie #2 na DWA mniejsze
  zapytania -- A: strategia; B: ubior + sprzet_opony -- po 4000 tokenow + helper _ask_plan z 1x
  retry gdy ktorys klucz nie jest dict (salvage czesciowy). Prompty A/B wycinane z istniejacego
  sys2 po markerach ("strategia: OBIEKT", "sprzet_opony: OBIEKT", "ubior: OBIEKT") -- jedno zrodlo
  promptu. Sygnatura zwrotu _report_prose bez zmian. Weryfikacja na zywo (bez zapisu snapshotu):
  _build_report_data(55930010) -> strategia dict (calosc + 5 etapow), ubior dict (2 zestawy),
  opony dict (wheelset), etapy pogody = 4. Stary snapshot z pusta strategia (np. 29 "Male Gosie")
  zostaje pusty -- przegenerowac (Parametry -> Generuj). REPO: qbot_web.py (restart + commit).
- Zakladka "Szczegoly trasy" (raport.css + raport-trasy.html, statyki poza repo):
  (a) scroll-lock -- strona nie scrolluje, scrolluje TYLKO okno zakladki
  (body.rtab-szczegoly{overflow:hidden}; wysokosc panelu w JS = innerHeight - top - 16,
  przeliczana na resize i przy zwijaniu Parametrow);
  (b) maly margines na dole (16 px pod panelem + 14 px padding w .multi-body);
  (c) delikatnie wieksze czcionki tekstow paneli (~+1 px na kluczowych klasach);
  (d) wieksze odstepy miedzy wierszami (line-height ~1.6-1.7 + oddech w wierszach tabel);
  (e) FIX czytelnosci: .press-cur (wyrozniony wiersz tabeli cisnien) mial zaszyte jasne tlo
  #f3efe6 -> w ciemnym motywie jasny tekst znikal; teraz rgba(60,107,71,.16) + color:var(--ink).
  Cache-bust raport.css ?v=2026071718. Zakladka Mapa i raport dnia nietkniete.
- Kalendarz (kalendarz-render.js + kalendarz.html, statyki poza repo): gdy dzien ma JAZDE i
  przypomnienie, belka przypomnienia (wypadala z komorki) zamieniana na maly dzwonek 🔔 w prawym
  dolnym rogu (liczba gdy >1, tooltip z trescia; klik w komorke otwiera dzien). Bez jazdy --
  belka jak dotad. Rezerwa .day.has-rem .marks{padding-right:20px}. JS ?v=17.

DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a): qbot_web.py (_report_prose split+retry) +
   docs/CURRENT.md + docs/DECISIONS.md + docs/RAPORT_WEB.md
   msg np.: "raport trasy: proza LLM split+retry; szczegoly UI; kalendarz dzwonek (+docs)"
   Statyki POZA repo (bez commitu): raport.css, raport-trasy.html, kalendarz-render.js, kalendarz.html

---

## Sesja 2026-07-17 -- Odzywianie (przebudowa), DZIS konfigurowalny, prefs na serwerze

Pelna decyzja: docs/DECISIONS.md (2026-07-17). Dane zakladki: docs/PROJEKT_ODZYWIANIE.md. UI: docs/FORMA_UI_LAYOUT.md (sekcje 5/9).

WYKONANE (na zywo, zweryfikowane):
- Odzywianie: sklad ciala przepiety body_daily -> widoki body_trend_full_composition / body_latest_full_composition (stare bylo z 2026-05-31; muscle_mass_kg to teraz realne kg ~68). Karta bilansu (uklad poziomy IN/OUT, makro z udzialem % i trendem w oknie), pasek skladu ciala jednolinijkowy z DELTA w oknie, wykres 9 chipow (sklad ciala rozbity na osobne, linie makro B/W/T na wspolnej skali gramow, waga czerwona linia na osi prawej, zjedzone LINIA zamiast overlay).
- DZIS konfigurowalny: przycisk "Dostosuj" (chipy on/off; grupy Panel/Moc/Obciazenie/Wellness/Zywienie), reuzycie tile(); widzety zywienia osadzone przez window.QNut (balanceHTML/bodyHTML) + notyfikacja window.renderTodayNut.
- Prefs na serwerze: tabela qbot_v2.ui_prefs + sql/ui_prefs_v1.sql (idempotentny, sprawdzony na bazie); endpointy GET/POST /api/prefs (_current_user z ciasteczka webauth). Round-trip GET->POST->GET OK (user=admin, wiersz testowy posprzatany). Front: zapis na serwer (debounce 400ms) + localStorage fallback; DZIS dociaga prefs przy starcie i nadpisuje lokalne.
- qbot-web zrestartowany (active). Statyki: forma.html, forma-render.js ?v=23, nutrition-render.js ?v=8 (poza repo, zywe od razu).

DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a): qbot_web.py + sql/ui_prefs_v1.sql
   msg: "DZIS: server-side prefs (ui_prefs + /api/prefs GET/POST)"
   (statyki w web/public sa POZA repo -- bez commitu)

UWAGA porzadkowa: kilka starych scripts/_tmp_*.py z wczesniejszych sesji (m.in. _tmp_deploy_js.py po awarii base64) -- do usuniecia recznie (rm niedostepny w DEV MCP).

---

## Sesja 2026-07-16 -- zaoranie starego podsystemu KALENDARZA (wariant B)

Pelna decyzja: docs/DECISIONS.md (2026-07-16). Skrot ponizej.

WYKONANE (na zywo, zweryfikowane):
- Backup 6 tabel: _bak_archive/20260716_190931_calendar_tables_backup.json (DDL+wiersze).
- Odpiety caly stary kalendarz (qcal) od Alberta, konektora ChatGPT, CLI, safety,
  raportu dziennego. Rejestr Alberta = 68 narzedzi, zero kalendarza (list_all_tools i
  tool_descriptions = BRAK); qbot-api/web/mcp-bridge/dev-mcp = active.
- DROP 6 tabel: public.{calendar_events, calendar_days, calendar_daily_snapshots,
  qcal_write_audit, reminders} + qbot_v2.calendar_events. Nowy kalendarz
  qbot_v2.calendar_entry nietkniety.
- Wariant B: event_morning_report.py + tools/trip_stages.py PRZEPIETE z calendar_events
  na qbot_planning_facts (route_stages). Zweryfikowane: start Toskanii 2026-06-05,
  okno eventu 06-05..06-11.
- Transport Telegrama i potwierdzenia tras nietkniete (smoke OK).
- 3 pliki-rdzen przeniesione do _bak_archive/20260716_calendar_core/ (mv zrobiony):
  qbot_calendar_core.py, qbot_calendar_cli.py, qbot_qcal_cli.py.

SPRZATANIE POZOSTALOSCI (runda 2, zweryfikowane importy):
- Produkcyjne, izolowane: qbot_capabilities.py (usuniete 6 wpisow qcal, zostalo 16),
  core/change_log.py (mapowania na skasowane tabele), qbot3/llm/openai_provider.py
  (przyklad promptu z calendar_events), qbot3/context_builder.py (wskazowka calendar_snapshot),
  qbot3/query_decomposer.py (mapy pol calendar_event_add/reminder_add).
- Testowe: qbot3/llm/mock_provider.py (3 galezie kalendarzowe = fikcja testowa) + usuniete
  6 testow kalendarza/qcal w test_qbot3_acceptance.py. Suite: 59 testow, tylko 3 wczesniejsze
  faile (nutrition WRITE_INCONSISTENT / naming qbot.query / core.planner -- NIE nasze).

DECYZJA (A): pozostale odwolania qcal w ZYWYM klasyfikatorze zapytan
(qbot_query_router.py ~40, write_router.py ~8, qbot_orchestrator.py ~9, drobne w innych)
ZOSTAWIONE swiadomie. Sa martwe i bezpieczne: readery zneutralizowane (NO_DATA), writery
odrzucane przez allowliste, narzedzia wyrejestrowane, ZADNE nie wykonuje SQL na skasowanych
tabelach. Pelne wyciecie = spory refaktor zywej sciezki klasyfikacji, niski zysk, wieksze
ryzyko -- odlozone. grep na 'qcal'/'calendar' NIE bedzie czysty i to jest OK.

TESTY (uruchamiane programowo przez unittest; DEV MCP blokuje pytest z argumentami):
- tests/test_qbot_qcal_telegram.py -> 12/12 PASS, bez zmian (transport + confirm_route_analysis).
- tests/test_route_precompute_trigger.py -> 17/17 PASS, bez zmian.
- tests/test_qbot3_acceptance.py -> 59 testow; poprawki: test_table_describe (calendar_events
  -> training_sessions), test_tool_registry_includes_all (usuniete asercje qcal_*), usuniete
  6 testow kalendarza/qcal. Pozostale 3 faile WCZESNIEJSZE/niezwiazane (patrz DECISIONS).

DO DOKONCZENIA (recznie / Desktop Commander -- brak commit/push w DEV MCP):
1. Commit (qbot przez runuser) + push (root). tool_registry.py i albert.py MUSZA byc
   w tym samym commicie (juz zmienione razem). Pliki-rdzen: git zobaczy jako usuniete
   (przeniesione do _bak_archive) -- podac jawnie lub osobny 'git rm'.

PLIKI ZMIENIONE (repo, do commitu):
  qbot3/safety.py, qbot3/agent_runtime.py, qbot3/tool_registry.py, qbot3/llm/albert.py,
  qbot_mcp_adapter.py, qbot_query_planner.py, qbot_query_router.py, qbot_ask_cli.py,
  qbot_nutrition_cli.py, qbot_capabilities.py, qbot_qcal_telegram.py,
  daily_report_adapter.py, core/registry.py, core/change_log.py,
  event_morning_report.py, tools/trip_stages.py,
  qbot3/llm/openai_provider.py, qbot3/llm/mock_provider.py, qbot3/context_builder.py,
  qbot3/query_decomposer.py,
  tests/test_qbot3_acceptance.py,
  docs/DECISIONS.md, docs/CURRENT.md, docs/CONTEXT.md
  USUNIETE z repo (przeniesione do _bak_archive/20260716_calendar_core/):
  qbot_calendar_core.py, qbot_calendar_cli.py, qbot_qcal_cli.py
