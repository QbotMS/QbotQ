"""Pogoda: conditions_point -- komplet pol wiersza i godziny wielkosci 'z poprzedniej godziny' (bez sieci: atrapa Open-Meteo).
Powstal 14.10.2026 po dwoch regresjach (komentarz w srodku slownika wycial pola wiatr, potem kier/skad)."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_pogoda as PG  # noqa: E402

POLA = {"iso", "t", "przeszlosc", "temp", "odcz", "rh", "rosa_pkt", "opad", "snieg", "wiatr", "porywy", "kier", "skad", "widocznosc",
        "grunt", "kod", "chmury", "dzien", "mgla", "lod", "nawierzchnia", "zapas_rosy", "szansa", "odcz_om", "utci", "wbgt", "na_rowerze", "pokrywa_cm"}


def _fake(n=30):
    tt = [f"2026-10-14T{h:02d}:00" for h in range(24)] + [f"2026-10-15T{h:02d}:00" for h in range(n - 24)]
    hr = {"time": tt}
    for v in PG.HOURLY.split(","):
        hr[f"{v}_best_match"] = [float(i) for i in range(n)]      # wartosc = indeks -> latwo sprawdzic przesuniecie
    return {"hourly": hr}


class Warunki(unittest.TestCase):
    def setUp(self):
        PG._CC.clear()
        import qbot_wx
        qbot_wx._C.clear()
        asg = {p: {d: {"model": "best_match", "opis": "x", "wartosc": None, "zakres": "x"} for d in (1, 2, 3)}
               for p in ("temp", "wiatr", "poryw", "opad")}
        self.p = [mock.patch("qbot_pogoda_verif.przydzial", return_value=asg),
                  mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(_fake()).encode())),
                  mock.patch("qbot_pogoda_okno._ens_prob", return_value={"2026-10-14T05": 0.5})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_komplet_pol(self):
        w = PG.conditions_point(52.3, 21.1, 6)
        self.assertEqual(w["status"], "OK")
        brak = POLA - set(w["godziny"][0])
        self.assertFalse(brak, f"brak pol: {brak}")

    def test_godziny_z_poprzedniej_godziny(self):
        r = PG.conditions_point(52.3, 21.1, 6)["godziny"]
        for i in (0, 5):
            self.assertEqual(r[i]["temp"], float(i))          # chwilowe: znacznik T
            self.assertEqual(r[i]["wiatr"], float(i))
            self.assertEqual(r[i]["kier"], float(i))
            self.assertEqual(r[i]["opad"], float(i + 1))      # godzina T..T+1: znacznik T+1
            self.assertEqual(r[i]["porywy"], float(i + 1))
            self.assertEqual(r[i]["snieg"], float(i + 1))
        self.assertEqual(r[5]["szansa"], 0.5)                 # szansa przypisana do godziny poczatku


if __name__ == "__main__":
    unittest.main()
