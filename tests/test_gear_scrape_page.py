"""Testy: pretty_name, page_html/scrape_page bez sieci (LLM i wybor zdjecia wylaczone)."""
import json
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_gear_scrape as S  # noqa: E402

PROD = {"@context": "https://schema.org", "@type": "Product", "name": "PRZYMIAR TRZYPUNKTOWY ZUŻYCIA ŁAŃCUCHA BITUL CH012",
        "brand": "Bitul", "sku": "18387279238",
        "image": [{"@type": "ImageObject", "url": "https://a.allegroimg.com/original/a/PRZYMIAR"},
                  {"@type": "ImageObject", "url": "https://a.allegroimg.com/original/b/PRZYMIAR-2"}],
        "offers": {"@type": "Offer", "price": "129.00", "priceCurrency": "PLN"}}
PAGE = {"url": "https://allegro.pl/oferta/przymiar-trzypunktowy-zuzycia-lancucha-bitul-ch012-18387279238",
        "canonical": "https://allegro.pl/produkt/przymiar-do-lancucha-bitul-ch012",
        "title": "Przymiar do łańcucha Bitul CH012", "ld": [json.dumps({"@type": "WebPage"}), json.dumps(PROD)],
        "meta": {"og:title": PROD["name"]}, "text": "Urządzenie do pomiaru długości łańcucha </script><b>x</b>"}


class Nazwa(unittest.TestCase):
    def test_wielkie_litery(self):
        self.assertEqual(S.pretty_name(PROD["name"], "Bitul"), "Przymiar trzypunktowy zużycia łańcucha Bitul CH012")

    def test_normalna_nazwa_bez_zmian(self):
        self.assertEqual(S.pretty_name("Przymiar Park Tool CC-3.2", "Park Tool"), "Przymiar Park Tool CC-3.2")


class StronaZPrzegladarki(unittest.TestCase):
    def test_pola(self):
        r = S.scrape_page(PAGE, use_llm=False, pick_image=False)
        f = r["fields"]
        self.assertEqual(f["brand"], "Bitul")
        self.assertEqual(f["price"], "129.00")
        self.assertEqual(f["currency"], "PLN")
        self.assertEqual(f["model"], "Przymiar trzypunktowy zużycia łańcucha Bitul CH012")
        self.assertEqual(r["images"][:2], ["https://a.allegroimg.com/original/a/PRZYMIAR", "https://a.allegroimg.com/original/b/PRZYMIAR-2"])
        self.assertEqual(r["url"], PAGE["url"])   # link oferty, nie canonical
        self.assertTrue(r["from_browser"])

    def test_bez_adresu(self):
        with self.assertRaises(ValueError):
            S.scrape_page({"ld": []}, use_llm=False)

    def test_ld_nie_zamyka_skryptu(self):
        h = S.page_html({"ld": ['{"a":"</script><script>alert(1)</script>"}'], "url": "https://x.pl"})
        self.assertEqual(h.count("</script>"), 1)


class ZdjecieZPrzegladarki(unittest.TestCase):
    def test_kopia_i_odczyt_z_dysku(self):
        import base64, io
        from PIL import Image
        im = Image.new("RGB", (400, 300), (200, 30, 30))
        b = io.BytesIO(); im.save(b, "JPEG")
        data = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
        r = S.scrape_page(dict(PAGE, image_data=data), use_llm=False, pick_image=False)
        url = r["fields"]["image"]
        self.assertTrue(url.startswith(S.QBOT_PUBLIC + "/gear/shop/"))
        self.assertEqual(r["sources"]["image"], "przegladarka")
        raw = S._fetch_image(url)                       # bez sieci: plik z dysku
        self.assertEqual(Image.open(io.BytesIO(raw)).size, (400, 300))
        os.remove(S._local_path(url))

    def test_zle_dane_i_sciezka(self):
        self.assertIsNone(S.store_image_data("data:text/html;base64,PGI+"))
        self.assertIsNone(S._local_path(S.QBOT_PUBLIC + "/gear/../../etc/passwd"))


if __name__ == "__main__":
    unittest.main()
