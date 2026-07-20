"""Kotwica W' z drogi (#3a).

Zdarzenie W'bal=0% na twardym wysilku (QExt2, tabela qbot_v2.fitmodel_qext2_ride)
to REALNY pomiar wyczerpania. Jesli jest swiezy i czysty -> podnosi PEWNOSC W'
(wprime_confidence='high'); NIE zmienia samej wartosci wprime_modelq_kj.

Wariant b (wsteczne policzenie wartosci W' z wysilku w momencie W'bal=0) -- patrz
docs/TODO.md sekcja [W-PRIME-KOTWICA-B]. Tu celowo tylko pewnosc (niskie ryzyko).

Wpiete jako krok "wprime_anchor" w fitmodel/daily_job.py (po modelq2_v2).
"""
from __future__ import annotations

MIN_ZERO_S = 10       # min. sekund z W'bal=0, by odrzucic pojedyncze glitche czujnika
WINDOW_DAYS = 42      # jak dlugo kotwica podtrzymuje 'high' (pamiec formy ~6 tyg)


def apply_road_anchor(conn, window_days: int = WINDOW_DAYS, min_zero_s: int = MIN_ZERO_S) -> dict:
    """Ustawia wprime_confidence/source w qbot_v2.fitmodel_daily wg kotwic z drogi.

    - dzien objety swiezea kotwica (Wbal=0 >= min_zero_s w [day-window, day]) -> 'high'
    - dzien z policzonym W' bez kotwicy -> 'medium' (harvest MQ2) zamiast NULL
    - dzien bez W' -> bez zmian
    Nie rusza wprime_modelq_kj.
    """
    cur = conn.cursor()
    # 1) kotwice z rozwiazywalna data. Data z ROZLOZONEGO 1 Hz (activity_record.MIN(ts)),
    #    NIE z JOIN do training_sessions.external_id -- utwardzenie 2026-07-20: duplikaty
    #    aktywnosci Garmin / natywne pliki Karoo bez 1 Hz same odpadaja (redundantne wobec
    #    kanonicznej jazdy, ktora 1 Hz ma). Zdarzenie bez strumienia -> ride_date=None -> skip.
    cur.execute(
        "SELECT (SELECT MIN(a.ts)::date FROM qbot_v2.activity_record a "
        "        WHERE a.external_id = q.ride_id) AS ride_date, "
        "       q.wbal_zero_seconds "
        "FROM qbot_v2.fitmodel_qext2_ride q "
        "WHERE q.wbal_zero_seconds >= %s",
        (min_zero_s,),
    )
    anchors = [(r[0], int(r[1])) for r in cur.fetchall() if r[0] is not None]

    # 2) dni w fitmodel_daily + czy maja policzone W'
    cur.execute(
        "SELECT day, (wprime_modelq_kj IS NOT NULL) FROM qbot_v2.fitmodel_daily ORDER BY day"
    )
    days = cur.fetchall()

    updates = []
    for day, has_wp in days:
        best = None  # najswiezsza kotwica w oknie [day-window, day]
        for adate, zs in anchors:
            if adate <= day and (day - adate).days <= window_days:
                if best is None or adate > best[0]:
                    best = (adate, zs)
        if best is not None:
            conf = "high"
            src = "kotwica z drogi: Wbal=0%% na jezdzie %s (%ds)" % (best[0].isoformat(), best[1])
        elif has_wp:
            conf = "medium"
            src = "harvest MQ2"
        else:
            continue
        updates.append((conf, src, day))

    for conf, src, day in updates:
        cur.execute(
            "UPDATE qbot_v2.fitmodel_daily SET wprime_confidence=%s, wprime_source=%s WHERE day=%s",
            (conf, src, day),
        )
    conn.commit()

    n_high = sum(1 for u in updates if u[0] == "high")
    return {"updated": len(updates), "high": n_high, "medium": len(updates) - n_high,
            "anchors": len(anchors)}
