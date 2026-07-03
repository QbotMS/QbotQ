# -*- coding: utf-8 -*-
"""Testy odczuwalnej Steadmana (headline 'odczuwalna' w METEO).

Model: R. G. Steadman (1984) / BOM. Radiacja przez Tmrt (globe solver),
czlon radiacyjny ograniczony do +RAD_CAP_C. Wiatr = 10 m [m/s].
"""
import unittest

from qbot3.routes.route_utci import (apparent_temp_steadman, q_net_from_tmrt,
                                      RAD_CAP_C)


class TestSteadman(unittest.TestCase):
    def test_chlod_wietrznie_ponizej_powietrza(self):
        # 16 C, RH 78%, wiatr 6 m/s, cien (Tmrt~=Ta) -> odczuwalna pod termometrem
        at = apparent_temp_steadman(16.0, 78.0, 6.0, 16.2)
        self.assertLess(at, 16.0)
        self.assertGreater(at, 8.0)      # ale nie ekstremalnie nisko

    def test_upal_slonce_powyzej_powietrza(self):
        # 32 C, RH 42%, wiatr 4 m/s, mocne slonce (Tmrt 47) -> nad termometrem
        at = apparent_temp_steadman(32.0, 42.0, 4.0, 47.0)
        self.assertGreater(at, 32.0)

    def test_bez_radiacji_domyslnie(self):
        # tmrt=None -> wersja bez slonca (temp+wilg+wiatr)
        at = apparent_temp_steadman(16.0, 78.0, 6.0)
        self.assertLess(at, 16.0)

    def test_monotonicznosc_wiatr(self):
        # wiecej wiatru -> nizsza odczuwalna (przy stalej reszcie)
        a = apparent_temp_steadman(20.0, 50.0, 2.0, 25.0)
        b = apparent_temp_steadman(20.0, 50.0, 8.0, 25.0)
        self.assertGreater(a, b)

    def test_monotonicznosc_slonce(self):
        # wiecej slonca (wyzszy Tmrt) -> wyzsza odczuwalna
        a = apparent_temp_steadman(20.0, 50.0, 3.0, 20.0)
        b = apparent_temp_steadman(20.0, 50.0, 3.0, 40.0)
        self.assertGreater(b, a)

    def test_cap_radiacyjny(self):
        # przy skrajnym Tmrt bonus radiacyjny nie przekracza RAD_CAP_C
        base = apparent_temp_steadman(16.0, 50.0, 1.0, 16.0)   # Tmrt=Ta -> ~0 radiacji
        capped = apparent_temp_steadman(16.0, 50.0, 1.0, 90.0)  # ekstremalne slonce
        # roznica to sam czlon radiacyjny (te same constanty), <= cap + drobny margines
        self.assertLessEqual(capped - base, RAD_CAP_C + 0.01)
        # i realnie dobija do capa (nie utknelo nisko)
        self.assertGreater(capped - base, RAD_CAP_C - 0.5)

    def test_q_net_znak(self):
        self.assertGreater(q_net_from_tmrt(20.0, 40.0), 0.0)   # Tmrt>Ta -> dodatnie
        self.assertLess(q_net_from_tmrt(20.0, 5.0), 0.0)       # Tmrt<Ta -> ujemne (chlodzenie)


if __name__ == "__main__":
    unittest.main()
