from __future__ import annotations

"""FITMODEL -- dzienny orkiestrator pipeline'u.

Uruchamia po kolei, z ODPORNOSCIA WARSTWOWA (awaria jednego kroku nie blokuje
reszty -- spec sek. 1): ingest nowych FIT -> resolver (fitmodel_daily) ->
CP/W' z krzywej mocy -> glikogen -> tagowanie nawierzchni (+kalibracja) ->
ride_buckets -> benchmark Xert.

Kazdy krok ma wlasny try/except i raport czasu. Jedno wspolne polaczenie DB.
Wpiety w cron (codziennie). Log: /opt/qbot/logs/fitmodel_daily.log
"""

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect

# ModelQ v2 jest jedynym modelem zasilajacym fitmodel_daily (adapter fitmodel.modelq2.publish).
# Silniki poprzedniej generacji sa w archiwum /opt/qbot/archive/modelq_v1/.
# Rollback: patrz docs/architecture/MODELQ_V2.md + tabele qbot_v2.*_v1_backup.

FIT_DIR = "/opt/qbot/artifacts/fit"


def _step(name, fn):
    t0 = time.time()
    try:
        result = fn()
        dt = time.time() - t0
        print(f"[OK ] {name} ({dt:.1f}s) -> {result}")
        return True
    except Exception as exc:
        dt = time.time() - t0
        print(f"[ERR] {name} ({dt:.1f}s): {exc}")
        traceback.print_exc()
        return False


def main() -> None:
    print(f"=== FITMODEL daily {datetime.now().isoformat(timespec='seconds')} ===")
    conn = _db_connect()
    try:
        # 1. Ingest nowych jazd -> fitmodel_segment
        def _ingest():
            from fitmodel.fit_ingest import ingest_all_new
            return ingest_all_new(FIT_DIR, conn)
        _step("ingest_fit", _ingest)

        # 2c. Wskaznik gotowosci (HRV+RHR+sen, baseline 60d) -> fitmodel_daily
        def _readiness():
            from fitmodel.readiness import save_readiness
            from datetime import date, timedelta
            # ostatnie 8 dni: dopina spozniony wellness (Garmin sync z opoznieniem)
            today = date.today()
            out = None
            for i in range(7, -1, -1):
                out = save_readiness(conn, today - timedelta(days=i))
            return out
        _step("readiness", _readiness)

        # 2c1. Siatka bezpieczenstwa: wpisy choroba/feel dodane w ostatnich 2 dniach,
        # ale dotyczace dni SPOZA okna 8 dni (wpis wsteczny) -> przelicz tamte dni.
        def _readiness_backfill():
            from fitmodel.readiness import recalc_recent_subjective_entries
            return recalc_recent_subjective_entries(conn, since_days=2)
        _step("readiness_backfill", _readiness_backfill)

        # 2d. Krok 3 -- W'bal tick-po-ticku dla nowych jazd -> fitmodel_wbal_ride
        def _wbal_replay():
            from fitmodel.wbal_replay import run_for_new_rides
            return run_for_new_rides()
        _step("wbal_replay", _wbal_replay)

        # 2b. ModelQ v2 -- jedyne zrodlo prawdy: XSS nowych jazd + sygnatura MQ2 + publish -> fitmodel_daily.
        # Zastepuje ftp_resolver/cp_wprime/training_load/cp_v3. Konsumenci czytaja te same
        # kolumny (ftp_est_w, cp_modelq_w, ltp_modelq_w, wprime_modelq_kj, ctl_xss/atl/tsb) z MQ2.
        # 2026-10-08: dynamiczne LTHR (fitmodel/lthr.py) PRZED modelq2 -- XSS z tetna nowych jazd liczy sie od niego
        def _lthr():
            from fitmodel.lthr import run_daily as lthr_run
            return lthr_run(conn)
        _step("lthr", _lthr)

        def _modelq2():
            from fitmodel.modelq2.publish import run_daily_v2
            return run_daily_v2(conn)
        _step("modelq2_v2", _modelq2)

        # 2026-09-28: kontrola spojnosci ModelQ (tylko odczyt): kazda jazda 1Hz ma XSS, obciazenie dnia
        # z przyrostu ATL == suma XSS jazd, brak duplikatow. Problem -> alert Telegram.
        def _mq2_integrity():
            from fitmodel.modelq2.integrity import run_and_alert
            from fitmodel.power_meter_guard import _telegram_send
            return run_and_alert(conn, send=_telegram_send)
        _step("modelq2_integrity", _mq2_integrity)
        # 2026-09-28: 2-3 zdjecia z kazdej NOWEJ jazdy (>= 30 km) wybrane nauczonym gustem -> START
        def _strava_auto():
            import qbot_strava
            return qbot_strava.run_auto()
        _step("strava_auto_photos", _strava_auto)

        # 2b1. L3 -- ukryte zmeczenie (subiektywny koszt jazdy) -> atl_plus/tsb_plus
        # (addytywne, audytowalne, odwracalne). PO modelq2 (baza atl_plus=atl_raw).
        # Przelacznik: QBOT_L3_HIDDEN_FATIGUE=0.
        def _hidden_fatigue():
            from fitmodel.modelq2.hidden_fatigue import apply_hidden_fatigue
            return apply_hidden_fatigue(conn)
        _step("hidden_fatigue", _hidden_fatigue)

        # 2b2. Kotwica W' z drogi (#3a): Wbal=0%% z QExt2 -> pewnosc W' 'high'.
        def _wprime_anchor():
            from fitmodel.wprime_anchor import apply_road_anchor
            return apply_road_anchor(conn)
        _step("wprime_anchor", _wprime_anchor)

        # 2b3. Kotwica W' z drogi -- WARTOSC (Wariant b): dolna granica W' z doła
        # Wbal=0 (replay_deficit) -> fitmodel_daily.wprime_road_kj. NIE rusza
        # wprime_modelq_kj; konsument bierze max(MQ2, road).
        def _wprime_road():
            from fitmodel.wprime_road import compute_road_wprime
            return compute_road_wprime(conn)
        _step("wprime_road", _wprime_road)

        # 2b4. Straznik miernika mocy: P@HR nowych jazd vs baza temperaturowa
        # (proteza MagicZero -- spindle DUB-PWR nie auto-zeruje w trakcie jazdy).
        # ALERT na Telegram przy mocnym odchyle/serii/wzroscie w trakcie.
        def _pm_guard():
            # 2026-09-28: stary straznik (P@HR) liczy i zapisuje dalej, ale BEZ Telegrama -
            # dawal falszywe alarmy (zwlaszcza po zmianie miernika). Pytania wysyla load_guard.
            from fitmodel.power_meter_guard import check_new_rides as pm_check
            return pm_check(conn, lookback_days=7, send=None)
        _step("power_meter_guard", _pm_guard)

        # 2d2. Straznik OBCIAZENIA: XSS z mocy vs XSS z tetna; jazda >=2 h poza x0.7-1.4
        # -> pytanie na Telegramie (Moc OK / Licz z tetna). Nic nie podmienia sam.
        def _load_guard():
            from fitmodel.load_guard import run as lg_run
            return lg_run(conn)
        _step("load_guard", _load_guard)

        # 2d3. Straznik korekty ciala (fitmodel/real_load_guard.py): TYLKO powiadomienie na Telegram, gdy faktyczne
        # zmeczenie/swiezosc moga sie rozjezdzac (sila, dane, dominacja jednego sygnalu, trwala rozbieznosc). Nic nie zmienia.
        def _rl_guard():
            from fitmodel.real_load_guard import run as rlg_run
            from fitmodel.power_meter_guard import _telegram_send
            return rlg_run(conn, send=_telegram_send)
        _step("real_load_guard", _rl_guard)

        # 2d4. Przeglad progu TP (fitmodel/tp_recheck.py, DECISIONS 2026-10-04): gdy zajdzie wyzwalacz
        # (dni/jazdy/h/km od uzbrojenia) i okno EF jest czyste (bez infekcji, >= 8 segmentow) ->
        # jeden raport na Telegram (dolna granica TP z W'bal + TP z EF). Nic nie zmienia w modelu.
        def _tp_recheck():
            from fitmodel.tp_recheck import run as tpr_run
            from fitmodel.power_meter_guard import _telegram_send
            return tpr_run(conn, send=_telegram_send)
        _step("tp_recheck", _tp_recheck)

        # 2d5. Prog mocy na Karoo (fitmodel/threshold_sync.py, DECISIONS 2026-10-04): TP ModelQ (cp_modelq_w)
        # -> intervals.icu FTP (histereza 2%, bez /apply) -> Hammerhead -> Karoo -> threshold_power w FIT
        # -> IF/TSS w Garmin Connect. Zmiana i blad -> threshold_sync_log + Telegram; blad nie jest polykany.
        def _threshold_sync():
            from fitmodel.threshold_sync import run as ts_run
            from fitmodel.power_meter_guard import _telegram_send
            return ts_run(conn, send=_telegram_send)
        _step("threshold_sync", _threshold_sync)

        def _lthr_sync():
            from fitmodel.threshold_sync import run_lthr
            from fitmodel.power_meter_guard import _telegram_send
            return run_lthr(conn, send=_telegram_send)
        _step("lthr_sync", _lthr_sync)

        # 2e. Ryczalt kaloryczny z eventu kalendarza (wakacje: kcal_planned).
        # Dni bez realnego jedzenia dostaja szacunek X kcal + makra jak w
        # presetach. Wlasne polaczenie (psycopg3, dict_row) -- ten pipeline
        # jedzie na psycopg2. Okno 7 dni wstecz do WCZORAJ wlacznie.
        def _event_intake():
            from qbot_nutrition_db import _conn as _nconn
            import qbot_event_intake as _evi
            with _nconn() as c2:
                res = _evi.fill_recent(c2, days_back=7)
            zap = sum(1 for r in res if r["action"] == "zapisany_ryczalt")
            return {"dni_sprawdzone": len(res), "dopisane_ryczalty": zap}
        _step("event_intake", _event_intake)

        # 3. Glikogen -> fitmodel_daily
        def _glyco():
            from fitmodel.glycogen import update_glycogen_in_daily
            return update_glycogen_in_daily(conn, FIT_DIR, days=30)
        _step("glycogen", _glyco)

        # 4. Tagowanie nawierzchni nowych segmentow + kalibracja (cache OSM)
        def _surface():
            from fitmodel.surface_tag import tag_segments, calibrate
            res = tag_segments(conn, only_untagged=True, use_cache=True, dry_run=False)
            tagged = sum(1 for r in res if r["dominant"])
            rep = calibrate(conn, dry_run=False)
            return {"nowe_otagowane": tagged, "kalibracja_update": rep["updated"]}
        _step("surface_tag", _surface)

        # 5. Ride buckets nowych jazd -> fitmodel_ride_buckets
        def _buckets():
            from fitmodel.ride_buckets import process_rides
            res = process_rides(conn, only_new=True, dry_run=False)
            return {"nowe_jazdy": len(res)}
        _step("ride_buckets", _buckets)

        # 6. Benchmark Xert (UPSERT biezacy tydzien; FTP vs TP + CP vs LTP + W' vs HIE)
        def _xert():
            from fitmodel.xert_bench import run_weekly_benchmark
            return run_weekly_benchmark(conn, dry_run=False)
        _step("xert_bench", _xert)

        # 6b. 2026-10-07: dzienny dopis Xerta do modelq2_xert_bench (wykres ModelQ vs Xert).
        # TYLKO benchmark -- ModelQ tej tabeli nie czyta (tests/test_xert_isolation.py).
        def _xert_daily():
            from fitmodel.xert_daily_bench import run_daily_xert_bench
            return run_daily_xert_bench(conn)
        _step("xert_daily_bench", _xert_daily)

        # 7. Plan tygodnia (tryb=PROPOZYCJA do zatwierdzenia) -> fitmodel_week_plan
        def _plan():
            from fitmodel.week_planner import build_plan, upsert_plan
            p = build_plan(conn)
            upsert_plan(conn, p)
            return {"week": p["week"], "mode": p["mode"],
                    "budget_h": p["time_budget_h"], "feasible": p["feasible"]}
        _step("week_planner", _plan)
    finally:
        conn.close()
    print("=== koniec ===")


def run_after_ride(reason: str = "") -> None:
    """Lekki recompute ModelQ po NOWEJ jezdzie (podzbior main()).

    Wchodzi tylko to, co zalezy od jazdy: ingest FIT -> gotowosc (tylko dzis) ->
    W'bal replay -> ModelQ v2 (XSS+sygnatura+publish) -> kotwice W' -> ukryte
    zmeczenie -> glikogen (okno 3 dni). NIE rusza nawierzchni/wiader/Xert/planu --
    to zostaje w nocnym main() jako niezalezny pelny sweep. Odpornosc warstwowa
    jak w main(): awaria kroku nie blokuje reszty ani ingestu jazdy.
    """
    print(f"=== FITMODEL after_ride {datetime.now().isoformat(timespec='seconds')} ({reason}) ===")
    conn = _db_connect()
    try:
        def _ingest():
            from fitmodel.fit_ingest import ingest_all_new
            return ingest_all_new(FIT_DIR, conn)
        _step("ingest_fit", _ingest)

        def _readiness():
            from fitmodel.readiness import save_readiness
            from datetime import date
            return save_readiness(conn, date.today())
        _step("readiness_today", _readiness)

        def _wbal_replay():
            from fitmodel.wbal_replay import run_for_new_rides
            return run_for_new_rides()
        _step("wbal_replay", _wbal_replay)

        # 2026-10-08: dynamiczne LTHR (fitmodel/lthr.py) PRZED modelq2 -- XSS z tetna nowych jazd liczy sie od niego
        def _lthr():
            from fitmodel.lthr import run_daily as lthr_run
            return lthr_run(conn)
        _step("lthr", _lthr)

        def _modelq2():
            from fitmodel.modelq2.publish import run_daily_v2
            return run_daily_v2(conn)
        _step("modelq2_v2", _modelq2)

        def _hidden_fatigue():
            from fitmodel.modelq2.hidden_fatigue import apply_hidden_fatigue
            return apply_hidden_fatigue(conn)
        _step("hidden_fatigue", _hidden_fatigue)

        def _wprime_anchor():
            from fitmodel.wprime_anchor import apply_road_anchor
            return apply_road_anchor(conn)
        _step("wprime_anchor", _wprime_anchor)

        def _wprime_road():
            from fitmodel.wprime_road import compute_road_wprime
            return compute_road_wprime(conn)
        _step("wprime_road", _wprime_road)

        # 2b4. Straznik miernika mocy: P@HR nowych jazd vs baza temperaturowa
        # (proteza MagicZero -- spindle DUB-PWR nie auto-zeruje w trakcie jazdy).
        # ALERT na Telegram przy mocnym odchyle/serii/wzroscie w trakcie.
        def _pm_guard():
            # 2026-09-28: stary straznik (P@HR) liczy i zapisuje dalej, ale BEZ Telegrama -
            # dawal falszywe alarmy (zwlaszcza po zmianie miernika). Pytania wysyla load_guard.
            from fitmodel.power_meter_guard import check_new_rides as pm_check
            return pm_check(conn, lookback_days=7, send=None)
        _step("power_meter_guard", _pm_guard)

        # 2d2. Straznik OBCIAZENIA: XSS z mocy vs XSS z tetna; jazda >=2 h poza x0.7-1.4
        # -> pytanie na Telegramie (Moc OK / Licz z tetna). Nic nie podmienia sam.
        def _load_guard():
            from fitmodel.load_guard import run as lg_run
            return lg_run(conn)
        _step("load_guard", _load_guard)

        def _glyco():
            from fitmodel.glycogen import update_glycogen_in_daily
            return update_glycogen_in_daily(conn, FIT_DIR, days=3)
        _step("glycogen", _glyco)
    finally:
        conn.close()
    print("=== after_ride koniec ===")


if __name__ == "__main__":
    main()
