"""Sprzet: stan nawierzchni, lampki, rowery (qbot3/routes/gear_kit.py) - bez AI i bez sieci. Dok.: docs/OUTFIT_FAVORITES.md"""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3.routes import gear_kit as K  # noqa: E402


def pw(h24, h48, d7):
    return {"ok": True, "opady_mm_max": {"24h": h24, "48h": h48, "72h": h48, "7d": d7}, "ostatni_deszcz_h_temu": None}


UNP = {"asfalt": 60, "szuter": 20, "ujeby": 20}


class T(unittest.TestCase):
    def test_states(self):
        self.assertEqual(K.surface_state(pw(0, 0, 0), UNP, {})["stan"], "sucho")
        self.assertEqual(K.surface_state(pw(0.6, 0.6, 3), UNP, {})["stan"], "wilgotno")
        self.assertEqual(K.surface_state(pw(4, 4, 6), UNP, {})["stan"], "mokro")
        self.assertEqual(K.surface_state(pw(9, 12, 20), UNP, {})["stan"], "bloto")
        self.assertEqual(K.surface_state(pw(9, 12, 20), {"asfalt": 95, "szuter": 5, "ujeby": 0}, {})["stan"], "mokro")
        self.assertEqual(K.surface_state(pw(0, 0, 0), UNP, {"max_proc": 60, "suma_mm": 2})["stan"], "mokro")
        self.assertEqual(K.surface_state({"ok": False, "blad": "x"}, UNP, {})["stan"], "nieznany")

    def test_unpaved(self):
        d = {"details": {"surface": {"by_cat": [{"k": 1, "km": 50}, {"k": 2, "km": 25}, {"k": 4, "km": 25}]}}}
        self.assertEqual(K.unpaved_pct(d), {"asfalt": 50, "szuter": 25, "ujeby": 25})

    def test_lights(self):
        base = {"details": {"weather": {"slonce": {"wschod": "06:50", "zachod": "17:45"}}}, "time": {"total_h": 4}}
        ok = K.accessories(base, "09:00", {"widocznosc_min_m": 20000}, {"stan": "sucho"})
        self.assertEqual(ok["lampki"]["potrzeba"], "niepotrzebne")
        self.assertEqual(ok["blotniki"]["potrzeba"], "niepotrzebne")
        dawn = K.accessories(base, "06:00", {"widocznosc_min_m": 20000}, {"stan": "mokro", "opis": "mokro"})
        self.assertEqual(dawn["lampki"]["potrzeba"], "wymagane")
        self.assertEqual(dawn["blotniki"]["potrzeba"], "zalecane")
        dusk = K.accessories(base, "13:30", {}, {"stan": "sucho"})       # meta 17:30 < 30 min przed zachodem
        self.assertEqual(dusk["lampki"]["potrzeba"], "wymagane")
        fog = K.accessories(base, "09:00", {"widocznosc_min_m": 600}, {"stan": "sucho"})
        self.assertEqual(fog["lampki"]["potrzeba"], "wymagane")

    def test_bikes_excludes_partner(self):
        names = " ".join("%s %s" % (b["nazwa"], b["ksywa"] or "") for b in K.bikes())
        self.assertNotIn("Go\u015bki", names)
        self.assertTrue(K.bikes())

    def test_manual_and_rules(self):
        bs = K.bikes()
        r = K.manual_bike(bs[0]["id"], {"km": 80})
        self.assertTrue(r["ok"] and r["recznie"])
        self.assertFalse(K.manual_bike(999999)["ok"])
        self.assertTrue(any("Monster" in x for x in K.BIKE_RULES))
        self.assertTrue(all("do_zrobienia" not in b for b in bs), "zadania serwisowe nie ida do wyboru roweru")


if __name__ == "__main__":
    unittest.main()
