"""LTP zmierzone z dryfu tetna (krok 2, 2026-07-26).

DLACZEGO ISTNIEJE
-----------------
LTP w ModelQ wychodzi ze wzoru `LTP = TP - HIE/400` (ten sam, ktorego uzywa Xert).
To jest WYLICZENIE z dwoch parametrow, a nie pomiar. Zbiegajac sie z Xertem
zbiegalismy sie z jego zalozeniami o TP i HIE, nie z fizjologia Michala.
Ten modul daje LTP mierzone NIEZALEZNIE: bez Xerta, bez kotwic, bez W'.

ZASADA
------
Prog tlenowy to najwyzsza moc, przy ktorej tetno jest STABILNE. Ponizej progu
organizm jest w stanie ustalonym -- tetno stoi. Powyzej pojawia sie dryf: przy tej
samej mocy tetno rosnie. Szukamy wiec mocy, przy ktorej dryf skokowo rusza.

Moc musi byc DOPASOWANA miedzy polowkami okna (<=5% roznicy), inaczej mylimy dryf
sercowy ze zwolnieniem tempa. To ta sama poprawka, ktora zastapila stary wskaznik
decouplingu w QExt2.

WYNIK POMIARU 2026-07-26
------------------------
Zrodlo: 306 okien 10-minutowych z 96 jazd, 180 dni, `qbot_v2.activity_record` 1 Hz.
Pominiete pierwsze 20 min kazdej jazdy (rozjazd zaniza dryf).

    moc      n   mediana dryfu
    130 W   16      0.36%
    140 W   33      0.81%
    150 W   42      0.18%
    160 W   41      0.56%
    170 W   42      0.50%
    -------------------------  <-- SKOK
    180 W   32      1.92%
    190 W   39      1.87%
    200 W   26      1.53%

Do 170 W dryf ~0.5%. Miedzy 170 a 180 W rosnie prawie czterokrotnie i nie wraca.

    WYNIK WYCOFANY 2026-07-26 -- patrz sekcja o regresji segmentowej nizej.
    Ten skok okazal sie efektem szerokosci koszyka. Przy koszykach 5 W znika,
    a regresja segmentowa nie znajduje istotnego zalamania nigdzie w 140-230 W.

OGRANICZENIA (nie przeceniac)
-----------------------------
- Okna 10 min sa krotkie; klasyczne protokoly dryfu uzywaja 30-60 min.
- Powyzej 200 W probka cienieje (17 i 9 okien) -- Michal nie utrzymuje takiej mocy
  rowno przez 10 min na gravelu. Gorna czesc tabeli jest niepewna.
- Zadna mediana nie przekracza 2%, wiec prog czytamy ze SKOKU, nie z przekroczenia
  progu bezwzglednego.
- Jazda w terenie jest zaszumiona: wiatr, podjazdy, temperatura.

PROBY ZAWEZENIA -- OBIE NIEUDANE (2026-07-26). NIE POWTARZAC.
-------------------------------------------------------------
**1. Dluzsze okna NIE dzialaja -- niszcza sygnal.** Sweep na 199 jazdach z roku:
    okno 10 min: 541 okien -> skok 170/180  (sygnal czysty)
    okno 15 min: 381 okien -> skok 210/220  (ale n=5 i 4 w tych koszykach)
    okno 20 min: 314 okien -> BRAK skoku, dryf plaski wszedzie
    okno 30 min: 234 okien -> skok 200/210  (n=8)
Powod: na gravelu nie ma 20-30 min naprawde rownego wysilku. Zeby cokolwiek
przeszlo przez filtr, trzeba rozluznic tolerancje mocy do 7-8%, a wtedy do okna
wchodza wysilki niejednorodne i dryf sie rozmywa. Klasyczne protokoly 30-60 min
zakladaja jazde na trenazerze albo rowna szose -- tu nie maja zastosowania.

**2. Gestsze koszyki (5 W) NIE zawezaja -- ujawniaja szum.** 1075 okien, krok 60 s:
    155 W  n=81  -1.24%      185 W  n=68   0.74%
    160 W  n=79  -1.43%      190 W  n=60   0.68%
    165 W  n=82   0.45%      195 W  n=58   1.89%
    170 W  n=66   0.37%      200 W  n=51   0.99%
    175 W  n=60   1.55%      205 W  n=37  -0.17%
    180 W  n=60   1.84%      210 W  n=32   1.89%
Brak trwalego przedzialu z mediana >=1.0%. Czysty skok widoczny przy koszykach
co 10 W byl czesciowo EFEKTEM SZEROKOSCI KOSZYKA -- usrednienie ukrywalo szum.

**Niekontrolowane zaklocenie:** dolek -1.2%/-1.4% przy 155-160 W na ~80 oknach.
Ujemny dryf przy stalej mocy nie ma sensu fizjologicznego -- to prawie na pewno
zjazdy i schladzanie (tetno spada mimo formalnie zgodnej mocy).

**CO BY FAKTYCZNIE ZAWEZILO** (osobne zadanie, nie strojenie parametrow):
- odfiltrowac odcinki ze spadkiem wysokosci (`activity_record.altitude_m`)
- uwzglednic temperature (`activity_record.temperature_c`)
- zamiast median po koszykach -- regresja tetno~moc na calych jazdach

Wniosek: 170-185 W zostaje, ale z NIZSZA pewnoscia niz sugeruje tabela 10 W.
Nie ma podstaw ani do zawezenia, ani do przesuniecia.

Przeliczyc, gdy przybedzie jazd -- funkcja `measure()` jest do tego gotowa.
"""
from __future__ import annotations

# --- WYNIK: LTP NIE USTALONE TA METODA (2026-07-26) ---
# Zakres 170-185 W, wpisany tu pierwotnie, ZOSTAL WYCOFANY. Byl artefaktem
# szerokosci koszyka, nie pomiarem. Trzy podejscia, coraz uczciwsze, dawaly
# coraz slabszy wynik:
#   koszyki 10 W        -> pozorny czysty skok 170/180 W
#   koszyki 5 W         -> szum, brak trwalego przedzialu
#   regresja segmentowa -> BRAK istotnego punktu zalamania
# Regresja segmentowa (1075 okien, prog szukany w 140-230 W) znalazla minimum
# przy 162 W, ale poprawa RSS wzgledem samej stalej to 1.72% wobec 1.28% dla
# zwyklej prostej -- model z zalamaniem jest praktycznie rownie dobry jak bez.
# Profil RSS plaski: 36099 (160 W) -> 36509 (220 W), rozrzut <1%.
#
# CO JEST PRAWDZIWE: dryf ROSNIE z moca, +0.025 %/W, wspolczynnik stabilny we
# wszystkich wariantach (z temperatura, bez zjazdow, z delta wysokosci).
# CZEGO NIE MA: mozliwosci wskazania WARTOSCI progu. Wynik zalezy calkowicie od
# arbitralnie przyjetego progu dryfu: 0% -> 138 W, 1% -> 178 W, 2% -> 218 W.
LTP_MEASURED_LO_W = None
LTP_MEASURED_HI_W = None
LTP_DRIFT_SLOPE_PCT_PER_W = 0.025
LTP_MEASURED_NOTE = ("LTP niezalezne: NIE USTALONE. Dryf tetna rosnie z moca "
                     "(+0.025 %/W, 1075 okien 10 min, 199 jazd, rok), ale regresja "
                     "segmentowa nie znajduje punktu zalamania -- wartosci progu "
                     "ta metoda wyznaczyc sie nie da. Szczegoly: fitmodel/ltp_hrdrift.py")

# --- parametry pomiaru ---
WIN_S = 600
STEP_S = 120
MAX_DP_PCT = 5.0
MAX_COAST_FRAC = 0.15
SKIP_START_S = 1200
MIN_POWER_W = 120


def measure(conn, days: int = 180) -> dict:
    """Przelicza LTP z dryfu tetna na swiezych danych. Read-only, nic nie zapisuje.

    Zwraca {'windows': n, 'buckets': {moc: mediana_dryfu}, 'step_at': (dol, gora)}.
    'step_at' to pierwsze przejscie, gdzie mediana dryfu rosnie co najmniej 3x
    wzgledem sredniej z nizszych koszykow -- czyli kandydat na prog.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT external_id FROM qbot_v2.activity_record "
        "WHERE ts >= current_date - %s GROUP BY external_id HAVING count(*) >= 3000",
        (days,),
    )
    rides = [r[0] for r in cur.fetchall()]

    samples = []
    for eid in rides:
        cur.execute(
            "SELECT power_w, hr_bpm FROM qbot_v2.activity_record "
            "WHERE external_id = %s ORDER BY sec", (eid,))
        rows = cur.fetchall()
        P = [r[0] for r in rows]
        H = [r[1] for r in rows]
        for a in range(SKIP_START_S, max(0, len(rows) - WIN_S), STEP_S):
            p = P[a:a + WIN_S]
            h = H[a:a + WIN_S]
            if sum(1 for x in h if x is None) > WIN_S * 0.05:
                continue
            if sum(1 for x in p if x is None) > WIN_S * 0.05:
                continue
            p = [x if x is not None else 0 for x in p]
            h = [x for x in h if x is not None]
            if len(h) < WIN_S * 0.95:
                continue
            if sum(1 for x in p if x == 0) > WIN_S * MAX_COAST_FRAC:
                continue
            half = WIN_S // 2
            p1 = sum(p[:half]) / half
            p2 = sum(p[half:]) / (WIN_S - half)
            if p1 < MIN_POWER_W or abs(p2 - p1) / p1 * 100.0 > MAX_DP_PCT:
                continue
            hh = len(h) // 2
            h1 = sum(h[:hh]) / hh
            h2 = sum(h[hh:]) / (len(h) - hh)
            if h1 <= 0:
                continue
            samples.append(((p1 + p2) / 2.0, (h2 - h1) / h1 * 100.0))

    raw = {}
    for pw, dr in samples:
        raw.setdefault(int(pw // 10) * 10, []).append(dr)

    buckets = {}
    for b, v in raw.items():
        if len(v) < 4:
            continue
        v = sorted(v)
        buckets[b] = v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2

    step_at = None
    keys = sorted(buckets)
    for i in range(3, len(keys)):
        # MEDIANA nizszych koszykow, nie srednia: skrajne koszyki maja malo okien
        # i pojedynczy odstajacy (np. 120 W = 1.59% przy n=7) zawyzalby baze tak,
        # ze realny skok 0.50% -> 1.92% na 170/180 W nie zostalby wykryty.
        below = sorted(buckets[k] for k in keys[:i])
        m = len(below)
        base = below[m // 2] if m % 2 else (below[m // 2 - 1] + below[m // 2]) / 2
        if base > 0 and buckets[keys[i]] >= 3.0 * base and buckets[keys[i]] >= 1.5:
            step_at = (keys[i - 1], keys[i])
            break

    return {"windows": len(samples), "buckets": buckets, "step_at": step_at}
