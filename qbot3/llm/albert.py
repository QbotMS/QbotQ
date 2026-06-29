#!/usr/bin/env python3
"""Albert — natywny agent loop z OpenAI-compatible tool/function calling.

Zastępuje dwuetapowe plan()+answer() z openai_provider.py.
Jeden przepływ: pytanie → tool_calls loop → odpowiedź tekstem.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from qbot_config import (
    ANTHROPIC_API_KEY,
    QGPT_API_KEY,
    QGPT_BASE_URL,
    QGPT_MODEL,
)

_log = logging.getLogger("qbot3.albert")

# Limit iteracji — zapobiega nieskończonej pętli
_MAX_STEPS = int(os.getenv("ALBERT_MAX_STEPS", "5"))

# Model i transport — przez qbot_config (ładuje .env)
_BASE_URL = (QGPT_BASE_URL or "https://api.openai.com/v1").rstrip("/")
_MODEL    = QGPT_MODEL or os.getenv("ALBERT_LLM_MODEL", "gpt-4o-mini")
_API_KEY  = QGPT_API_KEY or os.getenv("OPENAI_API_KEY") or ANTHROPIC_API_KEY or ""


def _gen_kwargs(model: str, base_url: str, max_n: int) -> dict:
    """Parametry generacji per-dostawca.

    Nowe modele OpenAI (gpt-5+, o-series) wymagaja max_completion_tokens i
    nie akceptuja temperature != domyslnej. Gemini/Anthropic (OpenAI-compat)
    uzywaja klasycznego max_tokens + temperature.
    """
    m = (model or "").lower()
    is_openai_new = ("api.openai.com" in (base_url or "")) or m.startswith(("gpt-5", "o1", "o3", "o4"))
    if is_openai_new:
        return {"max_completion_tokens": max_n}
    return {"max_tokens": max_n, "temperature": 0}


def _tool_result_has_meaningful_data(result: dict[str, object]) -> bool:
    """Zwraca True, jeśli wynik toola zawiera realne dane użytkowe."""
    if not isinstance(result, dict):
        return False

    status = result.get("status", "")
    if status in (
        "error",
        "ERROR",
        "BLOCKED",
        "SCHEMA_MISMATCH",
        "READER_ERROR",
        "DATA_MISSING",
        "CONNECTOR_MISSING",
    ):
        return False

    flat = _flatten_tool_result("tool", result)
    meaningful = {k for k in flat if k not in ("status", "tool", "safety_class", "reader")}
    return bool(meaningful)


def _needs_forced_final_answer(answer_text: str, tool_results_log: list[dict]) -> bool:
    """Sprawdza czy model dał złą odpowiedź mimo że ma dane z narzędzi.

    Odpala się gdy:
    - odpowiedź jest pusta lub zawiera "brak danych" (stary case)
    - odpowiedź zawiera wartości których nie ma w tool_results (halucynacja)
    - odpowiedź jest krótka i nie zawiera żadnych wartości z tool_results (zubożenie)

    Zwraca True tylko gdy w tool_results są rzeczywiste dane.
    """
    if not tool_results_log:
        return False

    # Sprawdź czy któryś tool_result ma rzeczywiste dane
    has_real_data = False
    tool_data_values: set[str] = set()  # wartości liczbowe/tekstowe z tool_results

    for tr in tool_results_log:
        data = tr.get("data", {})
        if not _tool_result_has_meaningful_data(data):
            continue

        has_real_data = True
        flat = _flatten_tool_result(tr.get("reader", "?"), data) if isinstance(data, dict) else {}
        for v in flat.values():
            if isinstance(v, (int, float)):
                tool_data_values.add(str(round(float(v), 1)))
            elif isinstance(v, str) and v:
                tool_data_values.add(v.lower()[:30])

    if not has_real_data:
        return False

    # Case 1: pusta odpowiedź lub "brak danych"
    if not answer_text or "brak danych" in answer_text.lower():
        return True

    # Case 2: odpowiedź jest bardzo krótka i nie zawiera żadnych wartości z tool_results
    if len(answer_text) < 80 and tool_data_values:
        answer_lower = answer_text.lower()
        if not any(v in answer_lower for v in tool_data_values):
            _log.info(f"Albert: short answer without tool values — forcing. answer='{answer_text[:60]}'")
            return True

    return False


def _flatten_tool_result(tool_name: str, result: Any) -> dict:
    """Wypłaszcza wynik toola do formatu czytelnego dla modelu.

    Obsługuje dwa formaty zwracane przez narzędzia QBot3:
    - Format A (success_result): {"status": "OK", "data": {"ftp_watts": 245.2, ...}}
    - Format B (bezpośredni):    {"status": "OK", "ftp_watts": 245.2, ...}

    W obu przypadkach Albert dostaje płaski dict z danymi na poziomie głównym.
    """
    if not isinstance(result, dict):
        return {"tool": tool_name, "result": str(result)}

    status = result.get("status", "OK")
    _meta_keys = frozenset({
        "status", "tool", "safety_class", "reader", "category",
        "_rows_truncated", "_events_truncated", "_documents_truncated",
        "args_schema", "mode", "notes",
    })

    # Błąd — zwróć komunikat bez danych
    if status not in ("OK", "ok", "READY_WITH_WARNINGS"):
        error_msg = (
            result.get("error")
            or result.get("message")
            or (result.get("data", {}).get("error") if isinstance(result.get("data"), dict) else None)
            or str(status)
        )
        return {"tool": tool_name, "status": status, "error": error_msg}

    # Sukces — wykryj format i wypłaszcz
    data = result.get("data")

    if isinstance(data, dict) and data:
        # Format A: dane są w result["data"]
        flat: dict[str, Any] = {"tool": tool_name, "status": "OK"}
        for k, v in data.items():
            if k not in _meta_keys:
                flat[k] = v
        # Jeśli data był pusty lub same meta-klucze, sprawdź też poziom główny
        if len(flat) <= 2:  # tylko tool + status
            for k, v in result.items():
                if k not in _meta_keys and k != "data":
                    flat[k] = v
        return flat

    # Format B: dane są bezpośrednio w result (lub data jest null/lista)
    flat = {"tool": tool_name, "status": "OK"}
    if isinstance(data, list):
        flat["data"] = data  # lista zostaje jako lista
    for k, v in result.items():
        if k not in _meta_keys and k != "data":
            flat[k] = v
    return flat


_SYSTEM = """\
Jesteś Albert — asystent osobisty Michała (Warszawa, rowerzysta, gravel).
Odpowiadasz po polsku, zwięźle i konkretnie.

Masz dostęp do narzędzi. Używaj ich samodzielnie aby zebrać potrzebne dane.
Nie opisuj planu działania. Nie pytaj o potwierdzenie przy odczycie danych.

Zasady bezpieczeństwa:
- Operacje destrukcyjne (usuń, skasuj, wyczyść wszystko) są zablokowane.
- Zapis danych → zwróć draft, poinformuj że wymaga qbot.action_execute.
- NIGDY nie mów "dodano", "zapisano", "wykonano" bez realnego qbot.action_execute.
- Jeśli tool zwrócił WRITE_DRAFT → to NIE JEST zapis. To tylko draft.
- Odczyt danych → wywołaj narzędzia i odpowiedz na podstawie wyników.
- Nie wymyślaj wartości których nie ma w wynikach narzędzi.
- Dla calendar_event_add i reminder_add wykonaj zapis tylko raz. Gdy tool
  zwróci OK lub DUPLICATE, nie ponawiaj tego samego zapisu.
- Dla calendar_event_add użyj date_start i title; time_start jest godziną
  zdarzenia. Dla reminder_add użyj date i title; time jest godziną.
- Jeśli tool zwrócił dane — użyj ich. NIE mów "brak danych" gdy dane są.
- Jeśli DB nie ma rekordu dla daty — sprawdź live connector (garmin_live_fetch,
  wellness_day, xert_readiness) zamiast kończyć odpowiedzią "brak danych".
- Jeśli live connector też nie ma danych — powiedz konkretnie co sprawdziłeś i jaki status zwrócił.
- Gdy użytkownik prosi o podział lokalnego GPX na etapy, użyj route_gpx_split.
- Nie zastępuj lokalnego splitu artefaktu wywołaniem artifact_save.

Trasy (analiza rowerowa) — dobór narzędzia wg intencji:
- Pytanie o ZAPLANOWANĄ trasę / plan / "co mnie czeka" (podsumowanie: dystans, nawierzchnia %, podjazdy, pogoda, wiatr) → route_plan_analysis (route_id lub artifact_id).
- Pytanie o SZCZEGÓŁY zaplanowanej trasy: profil wysokości po km, lista podjazdów, legacy tabela odcinków → route_profile_detail. Pytania o TEREN/krajobraz ("las czy pola", "co po bokach", "pokrycie terenu", "czy lesiste") → route_profile_detail z land_cover=true. Uwaga 2026-06-28: główna analiza nawierzchni gravelowej idzie po rzeczywistym śladzie przez route_surface_engine_v1 / rwgps_route_surface_analyze; route_frames 80 m są legacy dla profilu/pogody/debug, nie źródło prawdy nawierzchni.
- Pytanie o WYKONANĄ jazdę / "jak mi poszło" / analiza z pliku FIT lub z Garmina → ride_analysis.
- NIE myl planu z wykonaną jazdą. Pytanie o trasę/plan NIGDY nie trafia do narzędzi jazd/Garmina (garmin_*). Bez jednoznacznego route_id użyj najnowszej otrasowanej trasy.
- Pytania typu "czy bede mial gdzie kupic wode/jedzenie", "czy sklepy beda otwarte", "refill na trasie" → route_poi_analyze_readonly z open_window=true i, jesli podano start, ride_start; narzedzie zwraca godziny otwarcia i okno przejazdu.
- Pytanie o CIŚNIENIE OPON / „na ile napompować" / „jakie ciśnienie" → tire_pressure (B5). Liczy ciśnienie przód/tył dla OBU zestawów kół (bar i psi), model Berto (≤42 mm) / Heine surface-aware (≥42 mm); waga z body_measurements, masa roweru z garażu. Opcjonalne param: width1_mm, width2_mm, surface, weight_kg, bike_weight_kg.
- Pytanie o ŻYWIENIE/NAWODNIENIE na trasę / „ile węgli/płynów na godzinę", „plan jedzenia/picia", strategia fuelingu na ZAPLANOWANĄ trasę → route_fuel_plan (B2 płyny L/h, B3 węgle g/h; mirror QExt2 1:1, karmiony estymatami planu: if_target, vi, temp_c/humidity_pct z prognozy A5, duration_h z B4, waga z body_measurements; bez danych używa domyślnych i zaznacza zależności A5/B4). B1 (strefy %FTP) pominięte (decyzja: mało ważne).
- Pytanie ILE ZAJMIE / JAK DŁUGO będę jechał / ile czasu / tempo na ZAPLANOWANĄ trasę → ZAWSZE route_time_estimate (param: distance_km LUB route_id). NAGŁÓWEK odpowiedzi = liczby zwrócone przez to narzędzie (prędkość bazowa + szacowany czas); pokaż pole analysis w całości. BEZWZGLĘDNY ZAKAZ liczenia prędkości/czasu samodzielnie: nie agreguj jazd przez db_select/training_sessions, nie używaj „średniej z 90 dni", nie podstawiaj własnej prędkości. route_plan_analysis NIE zwraca czasu przejazdu — czas ZAWSZE z route_time_estimate. Wolno dodać KRÓTKI komentarz o terenie (np. że na gravelu realnie wolniej) jako DOPISEK pod liczbą — ale NIGDY nie zastępuj nim liczby narzędzia. Model świadomie uproszczony (10 ostatnich jazd OUTDOOR, v=Σkm/Σh).
- Pytanie o UPAŁ / PRZEGRZANIE / OBCIĄŻENIE CIEPLNE / stres cieplny / WBGT / "czy bezpiecznie jechac w upale" na ZAPLANOWANĄ trase lub w punkcie → route_wbgt. Model Liljegren (KNMI) z radiacja sloneczna z Open-Meteo (dokladniejszy niz feels_like; OWM/weather_forecast NIE ma radiacji). Param: lat, lon (wymagane), date (YYYY-MM-DD UTC, domyslnie dzis), from/to (HH:MM UTC, okno przejazdu). Zwraca szczyt WBGT, strefe ryzyka (ACSM: <18 niskie / 18-23 umiarkowane / 23-28 wysokie / 28-32 bardzo wysokie / 32+ ekstremalne) i rozklad godzinowy; czas UTC. Pokaz pole analysis w calosci.
- "analizuj trase X" / "pelna analiza trasy X" / "przeanalizuj trase X" / "raport trasy X" -> route_report (DOMYSLNE narzedzie analizy/raportu trasy). WYJATEK od zasady "nie pytaj": jesli uzytkownik NIE podal wariantu wprost, NAJPIERW odpowiedz samym pytaniem "Ktory wariant - skrocony, pelny czy dla grupy?" i ZAKONCZ ture BEZ wywolywania narzedzia. Gdy znasz wariant wywolaj route_report z variant i route_id. route_report zwraca JEDEN ustrukturyzowany DOKUMENT KONTEKSTOWY (dane trasy, profil, nawierzchnia-tabela, pogoda, forma+strefy mocy, sprzet, wyliczenia B2/B3/B4, punkty uzupelnienia, kombinacje ryzyk, nieznana nawierzchnia) ORAZ naglowek sekcji C. route_report sam buduje deterministyczny raport A+B — zostanie on doklejony do odpowiedzi automatycznie; Ty napisz WYLACZNIE sekcje C wg instrukcji z wiadomosci po tool call i NIE przepisuj A+B. Domyslnie nawierzchnia jest scalona w zmiany; pelna tabele po ramkach 80 m podaj tylko na wyrazna prosbe uzytkownika, wolajac route_report z surface_detail=true. Dla pytan stricte o gravel/nawierzchnie/surface uzyj rwgps_route_surface_analyze: sample 50 m, OSM corridor 50/80 m, confidence 25/50/80 m, Valhalla tylko fallback/refinement gdy dostepna, landcover/geology_context jako kontekst fail-open. Wariant "dla grupy" bez danych osobistych (waty/FTP, sprzet, cisnienia).
- route_analysis pozostaje dostepne jako ALTERNATYWA (jednoprzebiegowa, czysto-LLM analiza A-F bez dokumentu kontekstowego) - uzyj TYLKO gdy uzytkownik wyraznie poprosi o "analize LLM" / "jedna spojna analize"; w innych przypadkach domyslnie route_report (powyzej).
- Pytanie jak się NAZYWA trasa / jaka jest nazwa trasy (po route_id lub "najnowsza") → wywołaj route_plan_analysis (route_id); pole route_name w wyniku zawiera nazwę. ZAKAZ używania rwgps_route_fetch do szukania nazwy — nie ma tam nazwy i powoduje pętlę.

Schemat DB — krytyczne fakty:
- BILANS KALORYCZNY ≠ SPOŻYCIE. Dla pytań o bilans użyj:
  db_select_readonly: SELECT intake_kcal, expenditure_total, balance_kcal, balance_quality, balance_note FROM qbot_v2.daily_summary WHERE date = 'YYYY-MM-DD'
  Jeśli balance_quality=full → podaj balance_kcal.
  Jeśli partial → podaj z ostrzeżeniem z balance_note.
  Jeśli missing → powiedz czego brakuje.
- Tabela posiłków: meal_logs (eaten_at timestamp) + meal_log_items (makroskładniki)
  NIE istnieje: nutrition_logs, food_logs, kolumna date w meal_logs
  Dla kalorii dnia (sama suma/bilans): użyj narzędzia nutrition_day_summary(date)
  Dla LISTY poszczególnych posiłków/produktów dnia (każdy produkt + kcal/B/W/T): użyj nutrition_meal_list(date). NIE odpowiadaj samym bilansem gdy użytkownik prosi o listę/produkty/co jadł.
- Tabela wydatku: daily_energy_expenditure (kolumny: total_kcal_out, active_kcal_out, resting_kcal_out)
  NIE istnieje: kolumna kcal_burned
- Kalendarz: calendar_events (statusy: planned, active, confirmed — NIE tylko active)
- Nowa baza: qbot_v2 (search_path priorytetyzuje qbot_v2 przed public)

Dokumentacja i architektura QBot:
- Pytanie o architekturę QBot, routing, narzędzia, instrukcje działania → canonical_docs (czyta QBOT_ARCHITEKTURA_QBOT3, CONTEXT, CLAUDE).
- NIE odpowiadaj z pamięci na pytania o architekturę — zawsze wywołaj canonical_docs.

Styl odpowiedzi:
- Gdy narzędzie zwróciło gotową analizę w polu "analysis" (np. route_profile_detail, route_plan_analysis, ride_analysis) — pokaż ją w CAŁOŚCI, 1:1, NIE streszczaj i NIE skracaj, nawet gdy jest długa; profil km-po-km i listy odcinków mają być kompletne.
- Wypisz kluczowe wartości liczbowe z wyników narzędzi
- Dodaj krótki komentarz interpretacyjny oparty na danych
- Jeśli danych brakuje — powiedz czego konkretnie brakuje i dlaczego
"""


def run(question: str, tools_spec: list[dict], execute_tool_fn, context: dict,
        override_api_key: str = "", override_base_url: str = "", override_model: str = "") -> dict[str, Any]:
    """Główna pętla Alberta.

    Args:
        question: pytanie użytkownika
        tools_spec: lista narzędzi w formacie OpenAI tools[]
        execute_tool_fn: callable(tool_name: str, args: dict) -> dict
        context: dict z date, timezone, user itp.

    Returns:
        dict: answer, status, tool_results, steps, action_draft
    """
    if os.getenv("QBOT_ALBERT_HARD_KILL") == "1":
        return {
            "answer": "Planner niedostępny dla tego zapytania. Fallback jest wyłączony.",
            "status": "no_data",
            "tool_results": [],
            "steps": 0,
            "action_draft": None,
            "error": "planner_unavailable",
            "fallback_reason": "QBOT_ALBERT_HARD_KILL=1",
        }

    try:
        import openai
    except ImportError:
        return {
            "answer": "Brak biblioteki openai. Zainstaluj: pip install openai",
            "status": "error",
            "tool_results": [],
            "steps": 0,
            "action_draft": None,
        }

    _eff_key = override_api_key or _API_KEY
    _eff_url = override_base_url or _BASE_URL
    _eff_model = override_model or _MODEL
    client = openai.OpenAI(api_key=_eff_key, base_url=_eff_url)

    ctx_str = ""
    if context:
        ctx_str = f"\n\nKontekst: {json.dumps(context, ensure_ascii=False, default=str)}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM + ctx_str},
        {"role": "user",   "content": question},
    ]

    tool_results_log: list[dict] = []
    action_draft = None
    steps = 0
    _route_report_analysis = None
    _route_report_ctx_c = None
    _max_completion = 5000

    _log.info(f"Albert start: model={_MODEL} base_url={_BASE_URL} tools={len(tools_spec)} question={question[:80]}")

    _had_successful_write = False
    _had_successful_read = False

    for step in range(_MAX_STEPS):
        steps = step + 1

        try:
            kwargs: dict[str, Any] = {
                "model": _eff_model,
                "messages": messages,
                **_gen_kwargs(_eff_model, _eff_url, _max_completion),
            }
            if tools_spec:
                kwargs["tools"] = tools_spec
                # Po udanym realnym zapisie (write_committed=True) albo po
                # uzyskaniu sensownych danych read-only zdejmij przymus
                # tool_choice='required' - model moze wtedy zakonczyc odpowiedz
                # tekstem bez dalszego wymuszania tool_call.
                kwargs["tool_choice"] = "auto" if (_had_successful_write or _had_successful_read) else "required"

            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            _log.error(f"Albert LLM error step={step}: {exc}")
            return {
                "answer": f"Błąd komunikacji z LLM: {exc}",
                "status": "error",
                "tool_results": tool_results_log,
                "steps": steps,
                "action_draft": None,
            }

        msg = response.choices[0].message
        finish = response.choices[0].finish_reason
        answer_text = (msg.content or "").strip()
        empty_answer = not answer_text

        _log.info(
            f"Albert step={step}: finish={finish} empty_content={empty_answer} "
            f"tool_calls={len(msg.tool_calls) if msg.tool_calls else 0} "
            f"tool_results={len(tool_results_log)}"
        )

        # Albert zakończył — zwróć odpowiedź tekstem
        if finish == "stop" or not msg.tool_calls:
            # TASK 13 / Opcja B: raport A+B sklejamy deterministycznie (nie przez LLM);
            # model dostarcza wylacznie sekcje C.
            if _route_report_analysis:
                _c_body = (answer_text or "").strip()
                if _route_report_ctx_c:
                    _final = _route_report_analysis.rstrip() + "\n\n" + (_c_body or "(ocena niedostępna)")
                else:
                    _final = _route_report_analysis.rstrip() + "\n"
                _log.info(
                    f"Albert route_report assembly: analysis_len={len(_route_report_analysis)} c_len={len(_c_body)}"
                )
                return {
                    "answer": _final,
                    "status": "ok",
                    "tool_results": tool_results_log,
                    "steps": steps,
                    "action_draft": action_draft,
                }
            if not answer_text:
                answer_text = "Brak danych do odpowiedzi."

            # Jeśli model skończył z pustą odpowiedzią mimo danych → wymuś final answer
            if _needs_forced_final_answer(answer_text, tool_results_log):
                _log.info("Albert forcing final answer — injecting tool data explicitly")

                # Zbuduj jawny, skondensowany blok danych z tool_results
                data_blocks = []
                for tr in tool_results_log:
                    tr_status = tr.get("status", "")
                    if tr_status in ("error", "ERROR", "BLOCKED", "SCHEMA_MISMATCH",
                                     "READER_ERROR", "DATA_MISSING", "CONNECTOR_MISSING"):
                        continue
                    flat = _flatten_tool_result(tr.get("reader", "unknown"), tr.get("data", {}))
                    data_blocks.append(flat)

                if data_blocks:
                    data_json = json.dumps(data_blocks, ensure_ascii=False, default=str, indent=2)
                    forced_prompt = (
                        f"Wyniki narzędzi:\n{data_json}\n\n"
                        "Odpowiedz użytkownikowi po polsku na podstawie POWYŻSZYCH DANYCH.\n"
                        "Wypisz wszystkie wartości liczbowe, daty i statusy które są w danych.\n"
                        "Dodaj krótki komentarz jakościowy oparty wyłącznie na tych wartościach.\n"
                        "NIE dodawaj liczb, procentów ani wartości których nie ma w danych.\n"
                        "NIE mów 'brak danych' jeśli dane są powyżej."
                    )
                else:
                    forced_prompt = (
                        "Narzędzia nie zwróciły użytecznych danych. "
                        "Odpowiedz użytkownikowi po polsku i powiedz wprost, "
                        "że dane są niedostępne i z jakiego powodu."
                    )

                messages.append({"role": "user", "content": forced_prompt})
                try:
                    final_response = client.chat.completions.create(
                        model=_eff_model,
                        messages=messages,
                        **_gen_kwargs(_eff_model, _eff_url, 5000),
                    )
                    forced_answer = (final_response.choices[0].message.content or "").strip()
                    if forced_answer:
                        answer_text = forced_answer
                        _log.info(f"Albert forced answer: len={len(answer_text)}")
                except Exception as exc:
                    _log.error(f"Albert forced final answer error: {exc}")

            status = "draft" if action_draft else "ok"
            _log.info(f"Albert done: steps={steps} status={status} answer_len={len(answer_text)}")
            return {
                "answer": answer_text,
                "status": status,
                "tool_results": tool_results_log,
                "steps": steps,
                "action_draft": action_draft,
            }

        # Albert chce wywołać narzędzia — dodaj jego odpowiedź do historii
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # Wykonaj każde tool_call
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            _log.info(f"Albert tool_call: {tool_name} args={json.dumps(args, ensure_ascii=False)[:120]}")

            try:
                result = execute_tool_fn(tool_name, args)
            except Exception as exc:
                result = {"status": "error", "error": str(exc)[:300]}

            tool_results_log.append({
                "reader": tool_name,
                "status": result.get("status", "OK") if isinstance(result, dict) else "OK",
                "data": result,
            })

            if isinstance(result, dict) and result.get("write_committed") is True:
                _had_successful_write = True

            if (
                isinstance(result, dict)
                and result.get("status") in ("OK", "ok", "PARTIAL", "partial", "READY_WITH_WARNINGS")
                and _tool_result_has_meaningful_data(result)
            ):
                _had_successful_read = True

            # Wykryj write draft — zapisz action_draft do zwrotu
            if isinstance(result, dict) and result.get("status") == "WRITE_DRAFT":
                action_draft = {
                    "action_type": result.get("action_type", tool_name),
                    "payload_json": result.get("payload_json", args),
                    "requires_confirm": True,
                    "idempotency_key": None,
                }

            # Dodaj wypłaszczony wynik tool do historii
            tool_content = _flatten_tool_result(tool_name, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_content, ensure_ascii=False, default=str)[:16000],
            })

            if tool_name == "route_report" and isinstance(result, dict):
                _rd = result.get("data", result) if isinstance(result.get("data"), dict) else result
                _route_report_analysis = _rd.get("analysis")
                _route_report_ctx_c = _rd.get("context_for_section_c")
                if _route_report_ctx_c:
                    messages.append({"role": "user", "content": (
                        "Raport A+B zostanie dolaczony do odpowiedzi automatycznie (deterministycznie). "
                        "NIE przepisuj A+B. Napisz WYLACZNIE sekcje C — bez naglowka, zacznij od 'C1'. "
                        "Trzymaj sie danych i instrukcji ponizej, po polsku:\n\n" + _route_report_ctx_c
                    )})
                    _max_completion = 800
                else:
                    messages.append({"role": "user", "content": (
                        "Raport (wariant skrocony) zostanie dolaczony automatycznie. "
                        "Odpowiedz tylko slowem 'OK' — nic wiecej nie pisz."
                    )})
                    _max_completion = 80

            # Jeśli to WRITE_DRAFT, dodaj wymuszoną instrukcję po tool call
            if isinstance(result, dict) and result.get("status") == "WRITE_DRAFT":
                messages.append({
                    "role": "user",
                    "content": (
                        "Powyższy wynik to WRITE_DRAFT — NIE WYKONANO ZAPISU. "
                        "NIE mów 'dodano', 'zapisano', 'wykonano'. "
                        "Poinformuj użytkownika że to draft i wymaga qbot.action_execute."
                    ),
                })

    # Przekroczono limit kroków
    _log.warning(f"Albert max_steps={_MAX_STEPS} reached")
    return {
        "answer": (
            f"Przekroczono limit {_MAX_STEPS} kroków. "
            f"Ostatnie narzędzia: {[r['reader'] for r in tool_results_log[-3:]]}"
        ),
        "status": "partial",
        "tool_results": tool_results_log,
        "steps": steps,
        "action_draft": action_draft,
    }


def build_tools_spec(tools_desc: list[dict]) -> list[dict]:
    """Konwertuje tool_descriptions() do formatu OpenAI tools[].

    Wejście (tool_descriptions):
      [{"name": "...", "description": "...", "args_schema": {...}}]

    Wyjście (OpenAI tools[]):
      [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]
    """
    result = []
    for t in tools_desc:
        name = t.get("name", "")
        if not name:
            continue
        if t.get("status") == "error":
            continue

        args_schema = t.get("args_schema") or {}
        if not isinstance(args_schema, dict):
            args_schema = {}
        if "type" not in args_schema:
            args_schema = {"type": "object", "properties": args_schema}
        if "properties" not in args_schema:
            args_schema["properties"] = {}

        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": (t.get("description") or "")[:500],
                "parameters": args_schema,
            },
        })
    return result
