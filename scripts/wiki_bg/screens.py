#!/usr/bin/env python3
"""WIKI -- zrzuty ekranow stron QBot Lab (Playwright, zalogowany przez ciasteczko jak dev_fetch).
Wynik: docs/wiki/img/ekrany/<strona>[__<zakladka>].png (desktop) i <strona>__mobile.png + indeks.md.
Tylko odczyt (otwiera strony, klika zakladki). Uruchamiane z wiki_bg/pass2.py."""
import os, re, sys, time
sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/scripts")
from dev_fetch import get_auth

OUT = "/opt/qbot/app/docs/wiki/img/ekrany"
BASE = "http://127.0.0.1:30181"
PAGES = ["index", "dashboard", "forma", "mq2", "trening", "raport-jazdy", "raport-trasy", "raport-dzien",
         "naprawa-trasy", "planer-wyprawy", "planer-wyposazenia", "pogoda", "pogoda-wyprawy", "zdrowie",
         "garaz", "strava", "zdjecia", "cwiczenia", "status", "setup", "sciaga", "qbot-dodaj"]


def slug(s):
    s = s.lower().strip()
    for a, b in zip("ąćęłńóśźż", "acelnoszz"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:30] or "x"


def main():
    from playwright.sync_api import sync_playwright
    users, sign, make = get_auth()
    cookie, _ = make(sorted(users)[0], sign)
    os.makedirs(OUT, exist_ok=True)
    idx = ["# Zrzuty ekranow (automatyczne, " + time.strftime("%d.%m.%Y %H:%M") + ")", ""]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for mode, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
            ctx = b.new_context(viewport=vp, device_scale_factor=1, is_mobile=(mode == "mobile"))
            ctx.add_cookies([{"name": "qbot_session", "value": cookie, "url": BASE}])
            pg = ctx.new_page()
            for name in PAGES:
                try:
                    for _try in range(8):  # qbot-web bywa restartowany przez inne sesje
                        try:
                            pg.goto(f"{BASE}/{name}.html", wait_until="networkidle", timeout=45000)
                            break
                        except Exception as _e:
                            if "ERR_CONNECTION_REFUSED" not in str(_e) or _try == 7:
                                raise
                            time.sleep(20)
                    pg.wait_for_timeout(2500)
                    if "logowanie" in (pg.title() or "").lower():
                        idx.append(f"- {name}: STRONA LOGOWANIA (ciasteczko odrzucone)")
                        continue
                    f = f"{name}__mobile.png" if mode == "mobile" else f"{name}.png"
                    pg.screenshot(path=f"{OUT}/{f}", full_page=(mode == "desktop"))
                    idx.append(f"- [{name} ({mode})]({f})")
                    if mode != "desktop":
                        continue
                    tabs = pg.locator("#qtabs-mount button, #qtabs-mount a, .qtabs button")
                    labels = [t.strip() for t in tabs.all_inner_texts()][:12]
                    for i, lab in enumerate(labels):
                        if i == 0 or not lab:
                            continue
                        try:
                            tabs.nth(i).click(timeout=5000)
                            pg.wait_for_timeout(2500)
                            f2 = f"{name}__{slug(lab)}.png"
                            pg.screenshot(path=f"{OUT}/{f2}", full_page=True)
                            idx.append(f"  - [{name} / {lab}]({f2})")
                        except Exception as e:
                            idx.append(f"  - {name} / {lab}: blad {str(e)[:80]}")
                except Exception as e:
                    idx.append(f"- {name} ({mode}): blad {str(e)[:120]}")
            ctx.close()
        b.close()
    open(f"{OUT}/indeks.md", "w").write("\n".join(idx) + "\n")
    print("\n".join(idx))


if __name__ == "__main__":
    main()
