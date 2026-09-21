"""Naped roweru z SRAM AXS: kaseta rozpoznawana z DEKLARACJI PRZERZUTKI (gear_rear_t),
odporna na bledy wpisu w Karoo, z dobieraniem "z sasiedztwa" i skalowalna na wiele rowerow.
DECISIONS 2026-09-20.

JAK DZIALA (kolejnosc dla jazdy z AXS):
  1) KLASYFIKACJA: patrzymy tylko na zeby CHARAKTERYSTYCZNE (wystepujace u danego roweru
     tylko w jednej z jego kaset) i wygrywa kaseta z wieksza liczba trafien. Odporne na
     kilka zle zapisanych rzedow z Karoo. Zrodlo 'axs'.
  2) SASIEDZTWO: gdy (1) nie rozstrzyga (jazda tylko na wspolnych zebatkach albo remis),
     bierzemy kasete z NAJBLIZSZEJ czasowo PEWNEJ (axs) jazdy TEGO SAMEGO roweru --
     kaseta nie zmienia sie z dnia na dzien. Zrodlo 'axs_fill'.
  3) ZAPAS: istniejacy wpis w ride_cassette (fizyka/manual). Zrodlo bez zmian.
Przod (chainring) wprost z AXS (mode gear_front_t). Obwod kola z fizyki rozwiniecia.
Kanoniczne zeby bierzemy z katalogu gear_cassette (nie zepsute z jazdy).

cassette_source w ride_drivetrain: 'axs' (z przerzutki) / 'axs_fill' (z sasiedztwa) /
  'physics'|'physics_fill'|'manual' (zapas) / 'brak'.

======================================================================================
JAK DODAC NOWY ROWER (np. Canyon Grail):
  1) Czujniki/serial -> rozpoznanie roweru: qbot3/rides/activity_devices.py (bike_for_ride,
     bike_sensor). Bez tego 'bike' bedzie puste i has_axs falszywe.
  2) Kaseta(y) tego roweru:
     - AXS  -> dopisz wpis do BIKE_AXS_CASSETTES ponizej (rower -> jego kasety).
               Kazda kaseta MUSI byc w katalogu qbot_v2.gear_cassette (kod + cogs).
     - mechaniczny (bez AXS) -> profil w qbot3/rides/gear_estimate.py (BIKE_GEARING).
  3) Nietypowy przod (owal) -> CHAINRING_LABELS ponizej.
Gdy roweru nie ma w BIKE_AXS_CASSETTES, kandydatami sa wszystkie kasety z katalogu poza
mechanicznymi (fallback) -- dziala, ale klasyfikacja jest ostrzejsza gdy lista jest waska,
wiec dla nowego roweru z AXS najlepiej dopisac jego kasety jawnie.
======================================================================================
"""
from __future__ import annotations
import os
import statistics
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

CIRC_MIN, CIRC_MAX = 2.05, 2.40
MIN_SAMPLES_PER_POS = 25
MIN_POSITIONS_CIRC = 4          # min pozycji na policzenie obwodu
MIN_OBS_FOR_AXS = 2            # min pozycji zaobserwowanych, by ufac dopasowaniu AXS

CHAINRING_LABELS = {41: "owal 40T (41 efekt.)", 40: "40T", 36: "36T"}

# Kasety mozliwe dla danego roweru z AXS (nazwa roweru = qbot_v2.bike_sensor / bike_for_ride).
# Dopisz nowy rower tutaj (patrz checklist w naglowku modulu).
BIKE_AXS_CASSETTES = {
    "Canyon Grizl": ("10-46", "10-52"),
    # Canyon Grail (jeszcze bez roweru: seriale czujnikow do dodania w activity_devices,
    # zeby bike_for_ride zwracal "Canyon Grail"). AXS, przod 40T (owal -> AXS raportuje 41,
    # etykieta z CHAINRING_LABELS ogarnie). Kaseta 10-46, mozliwe 10-52.
    "Canyon Grail": ("10-46", "10-52"),
}

_SQL_MPR = """
select gear_rear_num,
       percentile_cont(0.5) within group (order by speed_mps * 60.0 / cadence_rpm)
from qbot_v2.activity_record
where external_id = %s
  and gear_rear_num is not null
  and cadence_rpm between 60 and 100
  and speed_mps > 2.5
  and power_w > 60
group by 1
having count(*) >= %s
"""

_BIKE_CACHE: dict = {}


def _cog_at(cogs, pos):
    return cogs[len(cogs) - pos] if 1 <= pos <= len(cogs) else None


def _load_cassettes(conn):
    cur = conn.cursor()
    cur.execute("select code, cogs from qbot_v2.gear_cassette")
    return {c: list(g) for c, g in cur.fetchall()}


def _bike(conn, external_id):
    """bike_for_ride z pamiecia podreczna (dobieranie sasiadow wola to wielokrotnie)."""
    if external_id not in _BIKE_CACHE:
        from qbot3.rides.activity_devices import bike_for_ride
        _BIKE_CACHE[external_id] = bike_for_ride(conn, external_id)
    return _BIKE_CACHE[external_id]


def _mechanical_codes():
    try:
        from qbot3.rides.gear_estimate import BIKE_GEARING
        return {g["cassette_code"] for g in BIKE_GEARING.values()}
    except Exception:
        return set()


def _axs_candidates(cassettes, bike):
    """Kasety-kandydaci dla tego roweru. Jawna lista per rower; inaczej wszystkie
    katalogowe poza mechanicznymi (rowery bez AXS)."""
    codes = BIKE_AXS_CASSETTES.get(bike)
    if codes:
        cand = {c: cassettes[c] for c in codes if c in cassettes}
        if cand:
            return cand
    mech = _mechanical_codes()
    cand = {c: v for c, v in cassettes.items() if c not in mech}
    return cand or cassettes


def cassette_from_axs(conn, external_id, cassettes, bike):
    """Klasyfikuje jazde do JEDNEJ z kaset roweru po zebach zadeklarowanych przez
    przerzutke. Decyduje WIEKSZOSC zebow CHARAKTERYSTYCZNYCH (tylko w jednej z kaset-
    kandydatow), a nie zgodnosc wszystkich pozycji -> odporne na bledy wpisu w Karoo.
    Zwraca (code, note) albo (None, powod)."""
    cur = conn.cursor()
    cur.execute("""select gear_rear_num, gear_rear_t
                   from qbot_v2.activity_record
                   where external_id = %s and gear_rear_num is not null and gear_rear_t is not null
                   group by 1, 2 order by 1""", (external_id,))
    pairs = [(int(p), int(t)) for p, t in cur.fetchall()]
    obs = {t for _, t in pairs}
    if len(obs) < MIN_OBS_FOR_AXS:
        return None, "za malo pozycji z AXS (%d)" % len(obs)
    cand = _axs_candidates(cassettes, bike)
    excl = {}
    for code, cogs in cand.items():
        others = set()
        for c2, g2 in cand.items():
            if c2 != code:
                others |= set(g2)
        excl[code] = set(cogs) - others
    scores = {code: len(obs & excl[code]) for code in cand}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_n = ranked[0]
    second_n = ranked[1][1] if len(ranked) > 1 else 0
    votes = ", ".join("%s=%d" % (c, n) for c, n in ranked)
    if best_n >= 1 and best_n > second_n:
        mism = sum(1 for p, t in pairs if _cog_at(cand[best], p) != t)
        note = "AXS: %d zebow char. dla %s (%s)" % (best_n, best, votes)
        if mism:
            note += "; %d poz. niezgodnych z katalogiem (mozliwy blad wpisu w Karoo)" % mism
        return best, note
    return None, "AXS nierozstrzygajacy (%s)" % votes


def nearest_axs_cassette(conn, target_day, bike):
    """Kaseta z NAJBLIZSZEJ czasowo PEWNEJ (source='axs') jazdy tego samego roweru.
    Zwraca (code, dist_dni, day_zrodla) albo None."""
    if not target_day or not bike:
        return None
    cur = conn.cursor()
    cur.execute("""select external_id, day, cassette_code from qbot_v2.ride_drivetrain
                   where cassette_source = 'axs' and cassette_code is not null and day is not null""")
    best = None
    for ext, day, code in cur.fetchall():
        if _bike(conn, ext).get("bike") != bike:
            continue
        dist = abs((day - target_day).days)
        if best is None or dist < best[0]:
            best = (dist, code, day)
    if best:
        return best[1], best[0], best[2]
    return None


def _circumference(conn, external_id, front_t, cogs):
    if not (front_t and cogs):
        return None, 0
    cur = conn.cursor()
    cur.execute(_SQL_MPR, (external_id, MIN_SAMPLES_PER_POS))
    vals = []
    for pos, mpr in cur.fetchall():
        t = _cog_at(cogs, int(pos))
        if t and mpr:
            vals.append(float(mpr) * t / float(front_t))
    if len(vals) >= MIN_POSITIONS_CIRC:
        return statistics.median(vals), len(vals)
    return None, len(vals)


def _upsert_cassette(conn, external_id, code, source, note):
    conn.cursor().execute(
        "insert into qbot_v2.ride_cassette (external_id, cassette_code, source, note) "
        "values (%s, %s, %s, %s) "
        "on conflict (external_id) do update set cassette_code = excluded.cassette_code, "
        "source = excluded.source, note = excluded.note",
        (external_id, code, source, note))


def _upsert_drivetrain(conn, row):
    conn.cursor().execute(
        "insert into qbot_v2.ride_drivetrain (external_id, day, chainring_t, chainring_label, "
        "cassette_code, cassette_source, circumference_m, positions, flag, note, computed_at) "
        "values (%(external_id)s, %(day)s, %(chainring_t)s, %(chainring_label)s, %(cassette_code)s, "
        "%(cassette_source)s, %(circumference_m)s, %(positions)s, %(flag)s, %(note)s, now()) "
        "on conflict (external_id) do update set day=excluded.day, chainring_t=excluded.chainring_t, "
        "chainring_label=excluded.chainring_label, cassette_code=excluded.cassette_code, "
        "cassette_source=excluded.cassette_source, circumference_m=excluded.circumference_m, "
        "positions=excluded.positions, flag=excluded.flag, note=excluded.note, computed_at=now()",
        row)


def build_ride(conn, external_id: str) -> dict | None:
    """Buduje ride_drivetrain dla jazdy na rowerze z AXS. Zwraca podsumowanie albo None
    (gdy rower nie ma AXS -- wtedy naped robi gear_estimate)."""
    b = _bike(conn, external_id)
    if not b.get("has_axs"):
        return None
    bike = b.get("bike")

    cur = conn.cursor()
    cur.execute("select mode() within group (order by gear_front_t) "
                "from qbot_v2.activity_record where external_id=%s and gear_front_t is not null",
                (external_id,))
    front_t = cur.fetchone()[0]
    cur.execute("select min(ts)::date from qbot_v2.activity_record where external_id=%s", (external_id,))
    day = cur.fetchone()[0]

    cassettes = _load_cassettes(conn)

    # 1) kaseta z przerzutki (AXS)
    code, cass_note = cassette_from_axs(conn, external_id, cassettes, bike)
    if code:
        _upsert_cassette(conn, external_id, code, "axs", cass_note)
        cass_src = "axs"
    else:
        # 2) dobierz z najblizszej PEWNEJ (axs) jazdy tego samego roweru
        nb = nearest_axs_cassette(conn, day, bike)
        if nb:
            code, dist, src_day = nb
            cass_note = "dobrane z jazdy %s (+/-%d dni); %s" % (src_day, dist, cass_note)
            _upsert_cassette(conn, external_id, code, "axs_fill", cass_note)
            cass_src = "axs_fill"
        else:
            # 3) zapas: istniejacy wpis w ride_cassette (np. fizyka/manual)
            cur.execute("select cassette_code, source from qbot_v2.ride_cassette where external_id=%s",
                        (external_id,))
            r = cur.fetchone()
            code = r[0] if r else None
            cass_src = (r[1] if r else None) or "brak"

    flags = []
    if not front_t:
        flags.append("brak przedniej zebatki z AXS")
    if not code:
        flags.append("brak kasety (AXS niejednoznaczny, brak sasiada i pomiaru): " + cass_note)

    circ, npos = (None, 0)
    if front_t and code and code in cassettes:
        circ, npos = _circumference(conn, external_id, front_t, cassettes[code])
        if circ is None:
            flags.append("za malo danych na obwod (%d poz.)" % npos)
        elif not (CIRC_MIN <= circ <= CIRC_MAX):
            flags.append("obwod %.3f m poza zakresem -- sprawdz przod albo kola" % circ)

    label = CHAINRING_LABELS.get(front_t, ("%dT" % front_t) if front_t else None)
    src_txt = {"axs": "naped z AXS", "axs_fill": "kaseta z sasiedztwa"}.get(cass_src,
                                                                            "kaseta zapasowo z %s" % cass_src)
    note = "%s: %s" % (src_txt, cass_note)
    if flags:
        note = note + "; " + "; ".join(flags)
    row = {
        "external_id": external_id, "day": day, "chainring_t": front_t,
        "chainring_label": label, "cassette_code": code, "cassette_source": cass_src,
        "circumference_m": circ, "positions": npos,
        "flag": "ok" if not flags else "uwaga", "note": note,
    }
    _upsert_drivetrain(conn, row)
    conn.commit()
    return {"ok": True, "bike": bike, "cassette": code, "cassette_source": cass_src,
            "chainring_t": front_t, "circumference_m": circ, "positions": npos, "flag": row["flag"]}
