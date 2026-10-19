# -*- coding: utf-8 -*-
"""Testy SYNTETYCZNE Centrum CdA (fitmodel/cda.py) -- audyt AERO 19.10 (docs/AERO_CDA_AUDIT_HANDOFF_2026-10-19.md, rozdz. 8).

Sztuczne jazdy o ZNANYM CdA, Crr, wietrze (tests/cda_synth.py) -> te same funkcje co produkcja (cda.windows, cda.fit_ride,
cda.joint_fit) -> czy odzyskujemy prawde. Dwa rodzaje testow:
- OCHRONNE: tu algorytm MA dzialac (petla, wiatr, szum mocy) -- tolerancje ciasne;
- OGRANICZENIA (znane slabosci, opisane w docs/AERO_CDA.md): test pilnuje, ze slabosc jest taka, jak opisana. Jesli ktos ja
  naprawi, test zacznie padac -- wtedy zaktualizowac test i dokumentacje (to dobry znak).
Uruchomienie: .venv/bin/python3 -m unittest tests.test_cda_synthetic -v"""
import os
import random
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import cda  # noqa: E402
import cda_synth as S  # noqa: E402

TRUE = {1: 0.0055, 2: 0.0105, 3: 0.0120, 4: 0.0150}
CDA = 0.43
M = 117.0


def fit(rows, tr, crr=TRUE):
    w = cda.windows(rows, tr, M, 1013.0)
    f = cda.fit_ride(w, crr)
    return w, f


def err(x):
    return (x - CDA) / CDA


class Ochronne(unittest.TestCase):
    def test_petla_rozne_wiatry(self):
        for ws, wd in ((0, 0), (2, 45), (4, 200), (6, 300)):
            rows, tr = S.ride(S.loop_legs(), CDA, TRUE, ws, wd, M, seed=ws + 1)
            w, f = fit(rows, tr)
            print("petla wiatr %d m/s z %3d: CdA %.4f (%+.1f%%), wiatr %.2f z %d, odcinkow %d"
                  % (ws, wd, f["cda"], 100 * err(f["cda"]), f["wind"], f["wind_from"], len(w)))
            self.assertLess(abs(err(f["cda"])), 0.02)
            self.assertLess(abs(f["wind"] - ws), 0.5)
            if ws >= 2:
                d = abs((f["wind_from"] - wd + 180) % 360 - 180)
                self.assertLessEqual(d, 20)

    def test_tam_i_z_powrotem(self):
        rows, tr = S.ride([(0, 6000, 1), (180, 6000, 1)], CDA, TRUE, 3.0, 0, M)
        w, f = fit(rows, tr)
        print("tam i z powrotem, wiatr 3 m/s: CdA %.4f (%+.1f%%), spread %.2f" % (f["cda"], 100 * err(f["cda"]), cda.spread(w)))
        self.assertLess(abs(err(f["cda"])), 0.02)

    def test_szum_i_zmiennosc_mocy(self):
        for nz, pw in ((0.02, 0.0), (0.10, 0.0), (0.05, 0.15)):
            rows, tr = S.ride(S.loop_legs(), CDA, TRUE, 2, 120, M, noise=nz, power_wave=pw)
            _w, f = fit(rows, tr)
            print("szum %d%%, fala %d%%: CdA %.4f (%+.1f%%)" % (nz * 100, pw * 100, f["cda"], 100 * err(f["cda"])))
            self.assertLess(abs(err(f["cda"])), 0.02)

    def test_wspolne_crr_z_dobra_kotwica(self):
        rnd = random.Random(7)
        rides = []
        for i in range(8):
            rows, tr = S.ride(S.loop_legs(cats=(1, 2, 3, 2)), CDA, TRUE, rnd.uniform(0, 4), rnd.uniform(0, 360), M,
                              power=rnd.uniform(150, 230), seed=i + 10)
            rides.append(({"external_id": str(i)}, cda.windows(rows, tr, M, 1013.0)))
        crr, _counts, res = cda.joint_fit(rides)
        cdas = sorted(f["cda"] for f in res)
        med = cdas[len(cdas) // 2]
        print("wspolne Crr (kotwica dobra): Crr2 %.4f (prawda %.4f), Crr3 %.4f (%.4f), CdA mediana %.4f (%+.1f%%)"
              % (crr[2], TRUE[2], crr[3], TRUE[3], med, 100 * err(med)))
        self.assertLess(abs(err(med)), 0.05)
        self.assertLess(abs(crr[2] - TRUE[2]) / TRUE[2], 0.15)
        self.assertLess(abs(crr[3] - TRUE[3]) / TRUE[3], 0.15)


    def test_korekta_dryfu_wysokosci_na_petli(self):
        """19.10: ten sam blad wysokosci 0,1 % co w Ograniczenia.test_blad_nachylenia, ale po cda.detrend_altitude (petla)."""
        rows, tr = S.ride(S.loop_legs(), CDA, TRUE, 0, 0, M, grade_bias=0.001)
        rows2, drift = cda.detrend_altitude(rows)
        _w, f = fit(rows2, tr)
        print("blad nachylenia +0,1%% po korekcie petli (dryf %.1f m): CdA %.4f (%+.1f%%)" % (drift, f["cda"], 100 * err(f["cda"])))
        self.assertIsNotNone(drift)
        self.assertLess(abs(err(f["cda"])), 0.02)

    def test_korekta_nie_rusza_trasy_w_jedna_strone(self):
        rows, _tr = S.ride([(0, 12000, 1)], CDA, TRUE, 0, 0, M, grade_bias=0.001)
        _rows2, drift = cda.detrend_altitude(rows)
        self.assertIsNone(drift)


    def test_ocena_jakosci(self):
        rows, tr = S.ride(S.loop_legs(), CDA, TRUE, 2, 45, M)
        w, f = fit(rows, tr)
        q, why = cda.ride_quality(len(w), cda.spread(w), f["cda"], f["se"], float((w[:, 5] != 1).mean()))
        self.assertEqual(q, "A", why)            # petla: duzo odcinkow, rozne kierunki, maly blad, 50 % szutru
        rows, tr = S.ride([(0, 12000, 1)], CDA, TRUE, 3.0, 0, M)
        w, f = fit(rows, tr)
        q, why = cda.ride_quality(len(w), cda.spread(w), f["cda"], f["se"], 0.0)
        self.assertIsNone(q, why)


class Ograniczenia(unittest.TestCase):
    def test_jeden_kierunek_wiatr_nie_do_rozdzielenia(self):
        """Jazda w jednym kierunku: wiatru nie da sie oddzielic od CdA. Sygnal: dir_spread ~0."""
        worst = 0.0
        for wd in (0, 90, 180):
            rows, tr = S.ride([(0, 12000, 1)], CDA, TRUE, 3.0, wd, M)
            w, f = fit(rows, tr)
            worst = max(worst, abs(err(f["cda"])))
            print("jeden kierunek, wiatr 3 m/s z %3d: CdA %.4f (%+.1f%%), spread %.2f" % (wd, f["cda"], 100 * err(f["cda"]), cda.spread(w)))
            self.assertLess(cda.spread(w), 0.1)
        self.assertGreater(worst, 0.05)

    def test_blad_nachylenia(self):
        """Staly blad wysokosci 0,1 % (np. zmiana cisnienia w trakcie jazdy) zmienia CdA o ok. 10 %."""
        rows, tr = S.ride(S.loop_legs(), CDA, TRUE, 0, 0, M, grade_bias=0.001)
        _w, f = fit(rows, tr)
        print("blad nachylenia +0,1%%: CdA %.4f (%+.1f%%)" % (f["cda"], 100 * err(f["cda"])))
        self.assertGreater(abs(err(f["cda"])), 0.05)

    def test_mokra_droga_wchodzi_do_cda(self):
        """Opor drogi x1,2 (mokro) przy liczeniu ze zwyklym Crr: zawyzone CdA (stan drogi, rozdz. 7 T6)."""
        rows, tr = S.ride(S.loop_legs(), CDA, TRUE, 2, 120, M, crr_scale=1.2)
        _w, f = fit(rows, tr)
        print("mokra droga (Crr x1,2): CdA %.4f (%+.1f%%)" % (f["cda"], 100 * err(f["cda"])))
        self.assertGreater(err(f["cda"]), 0.05)

    def test_zla_kotwica_przesuwa_poziom(self):
        """Prawdziwy asfalt 0,0065 przy kotwicy 0,0055: poziom CdA zawyzony; Crr szutru zanizony."""
        rnd = random.Random(9)
        t2 = dict(TRUE); t2[1] = 0.0065
        rides = []
        for i in range(8):
            rows, tr = S.ride(S.loop_legs(cats=(1, 2, 3, 2)), CDA, t2, rnd.uniform(0, 4), rnd.uniform(0, 360), M,
                              power=rnd.uniform(150, 230), seed=i + 30)
            rides.append(({"external_id": str(i)}, cda.windows(rows, tr, M, 1013.0)))
        crr, _c, res = cda.joint_fit(rides)
        cdas = sorted(f["cda"] for f in res)
        med = cdas[len(cdas) // 2]
        print("zla kotwica (+0,001): CdA mediana %.4f (%+.1f%%), Crr2 %.4f (prawda %.4f)" % (med, 100 * err(med), crr[2], t2[2]))
        self.assertGreater(err(med), 0.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
