"""Planer silowni AI - czesci czyste (qbot_trener_sila_ai)."""
import unittest

import qbot_trener_sila_ai as SA
from qbot_trener_sila import fam


def P(key, grp, wclass="C", tier="P", equip=None, kod="X/Y"):
    return {"key": key, "name": key, "grp": grp, "wclass": wclass, "tier": tier, "level": 1, "img": True,
            "equip": equip or [], "garmin_kod": kod, "prio": 1}


class TestAllowed(unittest.TestCase):
    def test_sprzet(self):
        on = {"hantle", "lawka", "mata", "guma_mocna"}
        self.assertIsNone(SA.allowed(P("bench_press_db", "klatka", equip=["h2", "lawka"]), on, set()))
        self.assertEqual(SA.allowed(P("band_squat", "nogi", equip=["mini"]), on, set()), "brak mini bandu")
        self.assertIsNone(SA.allowed(P("band_curl", "ramiona", equip=["guma"]), on, set()))
        self.assertIn("lekkiej", SA.allowed(P("band_external_rotation", "barki", equip=["guma"]), on, set()))
        self.assertEqual(SA.allowed(P("bench_press_db", "klatka", equip=["h2"]), {"lawka"}, set()), "brak hantli")

    def test_wskazowka_i_garmin(self):
        on = {"hantle"}
        self.assertEqual(SA.allowed(P("walking_lunge_db", "nogi", equip=["h2"]), on, {"walking_lunge_db"}), "wskazówka")
        self.assertEqual(SA.allowed(P("cuban_rotation_db", "barki", equip=["h2"], kod=None), on, set()), "brak w Garmin")
        self.assertIsNone(SA.allowed(P("arm_circles", "rozgrzewka", kod=None), on, set()))


class TestVariant(unittest.TestCase):
    def test_dluga_jazda_jutro(self):
        v, why = SA.variant_rule([{"sport": "rower", "rel": 1, "min": 180, "dluga": False}])
        self.assertEqual(v, "gora"); self.assertIn("jutro", why)

    def test_bez_dlugiej(self):
        v, _ = SA.variant_rule([{"sport": "rower", "rel": 2, "min": 180, "dluga": False},
                                {"sport": "rower", "rel": -1, "min": 60, "dluga": False}])
        self.assertEqual(v, "cale")

    def test_wybor_uzytkownika(self):
        self.assertEqual(SA.resolve_variant({"opts": {"sila_variant": "dol"}}, [])[1], "dol")
        self.assertEqual(SA.resolve_variant({"opts": {"sila_variant": "zle"}}, [])[0], "ai")


class TestValidate(unittest.TestCase):
    def setUp(self):
        xs = [P("bench_press_db", "klatka"), P("floor_press_db", "klatka"), P("row_one_arm_db", "plecy"),
              P("goblet_squat_db", "nogi"), P("bicep_curl_db", "ramiona", "L"), P("hammer_curl_db", "ramiona", "L"),
              P("lateral_raise_db", "barki", "L"), P("plank_forearm", "core", "0"), P("dead_bug", "core", "0"),
              P("rdl_db", "tyl", "S")]
        self.by = {x["key"]: x for x in xs}

    def test_dubel_rodziny_i_spoza_listy(self):
        keys = ["bench_press_db", "floor_press_db", "nieistnieje", "row_one_arm_db", "goblet_squat_db",
                "bicep_curl_db", "hammer_curl_db", "plank_forearm", "dead_bug"]
        out, notes = SA.validate_selection(keys, self.by, n=8, acc_sets={"biceps": SA.BICEPS}, min_acc=2, fam=fam)
        self.assertNotIn("floor_press_db", out)          # ta sama rodzina co wyciskanie na lawce
        self.assertNotIn("nieistnieje", out)
        self.assertTrue(any("spoza" in n for n in notes))

    def test_trzecia_klasa_ciezaru(self):
        keys = ["bench_press_db", "row_one_arm_db", "goblet_squat_db", "bicep_curl_db", "hammer_curl_db", "rdl_db", "plank_forearm"]
        out, _ = SA.validate_selection(keys, self.by, n=7, acc_sets={}, min_acc=2, fam=fam)
        self.assertNotIn("rdl_db", out)                  # S = 3. klasa obok C i L

    def test_za_malo(self):
        out, _ = SA.validate_selection(["bench_press_db", "x", "y"], self.by, n=8, acc_sets={}, min_acc=2, fam=fam)
        self.assertEqual(out, [])

    def test_ensure_accent(self):
        chosen = [self.by[k] for k in ("bench_press_db", "row_one_arm_db", "goblet_squat_db", "lateral_raise_db", "plank_forearm")]
        out = SA.ensure_accent(chosen, list(self.by.values()), {"biceps": SA.BICEPS}, 2, fam, set())
        self.assertEqual(sum(1 for x in out if x["key"] in SA.BICEPS), 2)   # akcent: 2 odmiany uginania sa dozwolone
        self.assertTrue(all(x.get("accent") for x in out if x["key"] in SA.BICEPS))


class TestAlternatives(unittest.TestCase):
    def test_trzy_propozycje_ta_sama_partia(self):
        from qbot_trener_sila import rank_alternatives
        pool = [P("bicep_curl_db", "ramiona", "L"), P("hammer_curl_db", "ramiona", "L"), P("band_curl", "ramiona", "0"),
                P("skull_crusher_db", "ramiona", "L"), P("bench_press_db", "klatka"), P("pushup", "klatka", "0"),
                P("floor_press_db", "klatka"), P("db_fly", "klatka", "L"), P("pushup_wide", "klatka", "0", tier="X")]
        chosen = [dict(pool[0], accent=True), pool[4], pool[3]]
        alts = rank_alternatives(pool, chosen, "bench_press_db", ban=set(), last=set(), maxlvl=3)
        keys = [a["x"]["key"] for a in alts]
        self.assertLessEqual(len(keys), 3)
        self.assertNotIn("pushup_wide", keys)                 # X (sprzet / wskazowka) nigdy
        self.assertEqual(keys[0], "floor_press_db")             # ten sam ciezar bloku pierwszy
        self.assertTrue(all(pool_x in ("floor_press_db", "pushup", "db_fly") for pool_x in keys))
        b = rank_alternatives(pool, chosen, "bicep_curl_db", ban=set(), last=set(), maxlvl=3)
        self.assertEqual({a["x"]["key"] for a in b} & {"skull_crusher_db"}, set())   # biceps != triceps


class TestGarminDose(unittest.TestCase):
    def test_powtorzenia_i_czas(self):
        import qbot_trener_garmin as TG
        self.assertIsNone(TG._secs("10"))
        self.assertIsNone(TG._secs("10 × 2 s"))                    # superman: powtorzenia
        self.assertEqual(TG._secs("20–30 s / stronę"), 30)
        self.assertEqual(TG._reps("8–12", "rt"), 12)
        self.assertEqual(TG._reps("8–12", "bz"), 10)
        self.assertEqual(TG._reps("8 / nogę", "rt"), 8)
        self.assertEqual(TG._reps("10 + 10"), 20)


class TestGarminRounds(unittest.TestCase):
    def test_rundy_rozpisane(self):
        import qbot_trener_garmin as TG

        class Cur:
            def execute(self, *a, **k): pass
            def fetchall(self): return [{"key": "bench_press_db", "garmin_kod": "BENCH_PRESS/DUMBBELL_BENCH_PRESS"},
                                        {"key": "row_one_arm_db", "garmin_kod": "ROW/DUMBBELL_ROW"}]
        data = {"rounds": 2, "title": "T", "text": "x / 20 s przerwy · przerwa między rundami 1 min", "_src": {"phase": "rt"},
                "exercises": [{"n": 1, "key": "bench_press_db", "name": "Wyciskanie", "dose": "10"},
                              {"n": 2, "key": "row_one_arm_db", "name": "Wiosłowanie", "dose": "10 / stronę"}],
                "blocks": [{"letter": "A", "kg": 10, "items": [1, 2]}], "warmup": []}
        dto, _w, _s = TG.build(Cur(), data, "2026-10-23")
        st = dto["workoutSegments"][0]["workoutSteps"]
        self.assertFalse(any(x.get("type") == "RepeatGroupDTO" for x in st))     # bez powtorzen-grup
        ex = [x for x in st if x["stepType"]["stepTypeKey"] == "interval"]
        self.assertEqual(len(ex), 2 * (1 + 2))                                       # 2 rundy x (1 + 2 strony)
        self.assertTrue(ex[0]["description"].startswith("A1/2"))
        self.assertTrue(ex[-1]["description"].startswith("A2/2"))


class TestText(unittest.TestCase):
    def test_short(self):
        t = "Pierwsze zdanie jest tutaj. Drugie zdanie jest dużo dłuższe i nie zmieści się w limicie znaków wcale."
        self.assertEqual(SA.short_text(t, 60), "Pierwsze zdanie jest tutaj.")
        self.assertTrue(SA.short_text("a" * 10 + " " + "b" * 80, 50).endswith("…"))


class TestPrefs(unittest.TestCase):
    def test_clean(self):
        p = SA.clean_prefs({"equipment": [{"n": "Hantle", "kind": "hantle", "on": 1}, {"n": "Kettlebell 16", "kind": "kettlebell"}],
                            "accents": ["biceps", "zle", "biceps"], "tips": ["  mały pokój  ", ""]})
        self.assertEqual([e["on"] for e in p["equipment"]], [True, False])
        self.assertEqual(p["accents"], ["biceps"])
        self.assertEqual(p["tips"], ["mały pokój"])
        with self.assertRaises(ValueError):
            SA.clean_prefs({"equipment": [{"n": "", "kind": "hantle"}]})


if __name__ == "__main__":
    unittest.main()
