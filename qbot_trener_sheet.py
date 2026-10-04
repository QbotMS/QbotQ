"""TRENER - sciaga treningu silowego z grafikami (PDF: JEDNA strona A4, 2 kolumny kart, dopasowanie skali 100%->74%;
nie miesci sie -> zapas _build_pdf_multi): dane (JSON dla /sciaga.html) i PDF z serwera (2026-10-03).

PDF bez reportlab: kazda strona A4 rysowana w Pillow (150 dpi) z WKLEJONYMI grafikami cwiczen
(/opt/qbot/web/public/cwiczenia/<key>.webp), zapis Image.save(pdf, save_all). Zasada uzytkownika: PDF bez wszystkich grafik
= BLAD - build_pdf() rzuca SheetError z lista brakujacych, zamiast oddac plik (grafika jest czescia strony, wiec nie moze
"nie dojsc" przy otwieraniu). Ciezar bloku: set_block_kg() zapisuje kg do trainer_exercise_user.weight_kg dla cwiczen bloku
i przelicza zapisany zestaw (qbot_trener_sila.render ze zrodla _src). Testy: tests/test_trener_sheet.py.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date

from PIL import Image, ImageDraw, ImageFont

IMG_DIR = "/opt/qbot/web/public/cwiczenia"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_C = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
W, H, M = 1240, 1754, 56          # A4 przy 150 dpi
INK, MUT, NAVY = (23, 32, 42), (75, 86, 99), (19, 32, 46)
BLK = {"C": (181, 83, 15), "S": (31, 95, 168), "L": (47, 125, 50), "0": (90, 99, 110)}
BG, GOOD, BAD = (243, 245, 248), (47, 125, 50), (179, 38, 30)
DN = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


class SheetError(Exception):
    pass


def _f(path, size):
    return ImageFont.truetype(path if os.path.exists(path) else FONT, size)


def sheet_data(c, user: str, sid: int) -> dict:
    """Sesja silowa + zestaw z bazy + kroki/dobrze/blad cwiczen."""
    import qbot_trener_engine as E
    import qbot_trener_ratings as TR
    from datetime import timedelta
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s", (sid, user))
    r = c.fetchone()
    if not r:
        raise SheetError("nie ma takiej sesji")
    s = dict(r)
    if s["sport"] != "sila":
        raise SheetError("ściąga jest tylko dla treningu siłowego")
    ws = s["day"] - timedelta(days=s["day"].weekday())
    phase = E.plan_week(E.build_context(c, user, ws))["phase"]
    d = TR.details_for(c, user, s, phase)
    if not d or d.get("engine") != "baza1":
        raise SheetError("ten trening ma stary zestaw (sprzed bazy ćwiczeń) — ściąga z grafikami jest dla nowych treningów")
    keys = [e["key"] for e in d["exercises"]] + [w["key"] for w in d.get("warmup") or []]
    c.execute("SELECT key, steps, ok, bad, muscles FROM qbot_v2.trainer_exercise WHERE key = ANY(%s)", (keys,))
    info = {}
    for x in c.fetchall():
        st = x["steps"]
        if isinstance(st, str):
            st = json.loads(st)
        info[x["key"]] = {"steps": st or [], "ok": x["ok"], "bad": x["bad"], "muscles": x["muscles"]}
    st = s.get("start_time")
    return {"session": {"id": s["id"], "day": s["day"].isoformat(), "dow": DN[s["day"].weekday()], "name": s["name"],
                        "start": st.strftime("%H:%M") if st else None, "dur_min": s["dur_min"], "status": s["status"],
                        "phase": phase, "editable": s["status"] == "plan" and s["day"] >= date.today()},
            "details": {k: v for k, v in d.items() if k != "_src"}, "info": info}


def set_block_kg(c, user: str, sid: int, letter: str, kg: float) -> dict:
    import qbot_trener_sila as SX
    if not (0 < kg <= 40):
        raise SheetError("ciężar: 0,5–40 kg")
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s", (sid, user))
    s = c.fetchone()
    if not s or s["sport"] != "sila":
        raise SheetError("nie ma takiej sesji siłowej")
    c.execute("SELECT data FROM qbot_v2.trainer_workout WHERE username=%s AND day=%s AND sport='sila'", (user, s["day"]))
    row = c.fetchone()
    data = row["data"] if row else None
    if isinstance(data, str):
        data = json.loads(data)
    if not data or "_src" not in data:
        raise SheetError("brak zapisanego zestawu dla tego treningu")
    b = [x for x in data["blocks"] if x["letter"] == letter]
    if not b or b[0]["wclass"] == "0":
        raise SheetError("nie ma takiego bloku z hantlami")
    keys = [e["key"] for e in data["exercises"] if e["n"] in b[0]["items"] and e["wclass"] != "0"]
    for k in keys:
        c.execute("INSERT INTO qbot_v2.trainer_exercise_user (username, key, weight_kg) VALUES (%s,%s,%s) "
                  "ON CONFLICT (username, key) DO UPDATE SET weight_kg=EXCLUDED.weight_kg, updated_at=now()", (user, k, kg))
    src = data["_src"]
    c.execute("SELECT key, weight_kg FROM qbot_v2.trainer_exercise_user WHERE username=%s AND weight_kg IS NOT NULL", (user,))
    w = {r["key"]: float(r["weight_kg"]) for r in c.fetchall()}
    ch = {"accent": src["accent"], "skip": src["skip"], "chosen": src["chosen"]}
    out = SX.render(ch, SX.build_blocks(ch["chosen"], w), src["warmup"], src["phase"], src["cut"])
    out["_src"] = src
    c.execute("UPDATE qbot_v2.trainer_workout SET data=%s::jsonb, updated_at=now() WHERE username=%s AND day=%s AND sport='sila'",
              (json.dumps(out, ensure_ascii=False), user, s["day"]))
    return {"ok": True, "letter": letter, "kg": kg, "exercises": len(keys)}


# ---------------- PDF ----------------
def _wrap(dr, text, font, width):
    out, line = [], ""
    for word in str(text or "").split():
        t = (line + " " + word).strip()
        if dr.textlength(t, font=font) <= width:
            line = t
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out


def _build_pdf_multi(data: dict) -> tuple[bytes, dict]:
    """Zapas (2026-10-03): stary uklad wielostronicowy - gdy trening nie miesci sie na 1 stronie nawet po zmniejszeniu."""
    """PDF A4 z grafikami. Zwraca (bajty, raport). Brak ktorejkolwiek grafiki -> SheetError (nie oddajemy pliku bez grafik)."""
    d, s, info = data["details"], data["session"], data["info"]
    imgs, missing = {}, []
    for e in d["exercises"]:
        p = os.path.join(IMG_DIR, e["key"] + ".webp")
        try:
            im = Image.open(p).convert("RGB")
            im.load()
            imgs[e["key"]] = im
        except Exception:
            missing.append(e["name"])
    if missing:
        raise SheetError("brak grafik: " + ", ".join(missing) + " — PDF nie został utworzony")
    f_t, f_h, f_b, f_r, f_s, f_n = _f(FONT_C, 44), _f(FONT_C, 30), _f(FONT_B, 25), _f(FONT, 22), _f(FONT, 19), _f(FONT_C, 40)
    pages, placed = [], 0
    pg = dr = None
    y = 0

    def new_page(first):
        nonlocal pg, dr, y
        pg = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(pg); pages.append(pg)
        hh = 150 if first else 90
        dr.rectangle([0, 0, W, hh], fill=NAVY)
        dr.text((M, 28 if first else 24), (d.get("title") or "Siła").upper() if first else "ściąga · cd.", font=f_t if first else f_h, fill="white")
        if first:
            sub = f"{s['dow']} {s['day'][8:10]}.{s['day'][5:7]}" + (f" · {s['start']}" if s.get("start") else "") + f" · {s['dur_min']}′ · {d.get('rounds')} × każdy blok"
            dr.text((M, 92), sub, font=f_r, fill=(214, 221, 230))
        y = hh + 24

    def need(h):
        if y + h > H - 60:
            new_page(False)

    new_page(True)
    if d.get("warmup"):
        t = "Rozgrzewka 5′: " + " · ".join(f"{w['name']} {w.get('dose') or ''}".strip() for w in d["warmup"])
        lines = _wrap(dr, t, f_r, W - 2 * M - 30)
        bh = 24 + len(lines) * 30
        need(bh)
        dr.rounded_rectangle([M, y, W - M, y + bh], 14, fill=(255, 244, 229))
        for i, ln in enumerate(lines):
            dr.text((M + 16, y + 12 + i * 30), ln, font=f_r, fill=INK)
        y += bh + 18
    exs = {e["n"]: e for e in d["exercises"]}
    prev = None
    for b in d["blocks"]:
        if b["wclass"] != "0" and prev is not None and prev != b["kg"]:
            need(50)
            dr.rounded_rectangle([M, y, W - M, y + 40], 10, outline=(138, 148, 160), width=2)
            msg = f"Zmiana obciążenia: {prev} → {b['kg']} kg"
            dr.text(((W - dr.textlength(msg, font=f_b)) / 2, y + 7), msg, font=f_b, fill=INK)
            y += 54
        if b["wclass"] != "0":
            prev = b["kg"]
        need(64 + 300)
        col = BLK.get(b["wclass"], BLK["0"])
        dr.rounded_rectangle([M, y, W - M, y + 52], 12, fill=col)
        dr.text((M + 18, y + 9), b["head"].upper(), font=f_h, fill="white")
        r = f"{d.get('rounds')} × runda"
        dr.text((W - M - 18 - dr.textlength(r, font=f_b), y + 13), r, font=f_b, fill="white")
        y += 66
        for n in b["items"]:
            e = exs[n]; inf = info.get(e["key"], {})
            iw, ih = 360, 240
            tx = M + iw + 34; tw = W - M - tx - 16
            name_l = _wrap(dr, e["name"], f_b, tw - 120)
            body = [f"{i + 1}. {st}" for i, st in enumerate(inf.get("steps") or [])]
            body_l = [ln for t in body for ln in _wrap(dr, t, f_s, tw)]
            ok_l = _wrap(dr, "✓ " + inf["ok"], f_s, tw) if inf.get("ok") else []
            bad_l = _wrap(dr, "✕ " + inf["bad"], f_s, tw) if inf.get("bad") else []
            ch = max(ih + 24, 30 + len(name_l) * 32 + 32 + (len(body_l) + len(ok_l) + len(bad_l)) * 27 + 20)
            need(ch + 14)
            dr.rounded_rectangle([M, y, W - M, y + ch], 16, fill=BG)
            im = imgs[e["key"]].copy(); im.thumbnail((iw, ih), Image.LANCZOS)
            pg.paste(im, (M + 12 + (iw - im.width) // 2, y + 12 + (ih - im.height) // 2)); placed += 1
            dr.text((tx, y + 12), str(e["n"]), font=f_n, fill=col)
            for i, ln in enumerate(name_l):
                dr.text((tx + 46, y + 16 + i * 32), ln, font=f_b, fill=INK)
            dose = e.get("dose") or ""
            dr.text((W - M - 16 - dr.textlength(dose, font=f_b), y + 16), dose, font=f_b, fill=INK)
            yy = y + 16 + len(name_l) * 32 + 4
            dr.text((tx, yy), e["group"] + (" · akcent dnia" if e.get("accent") else ""), font=f_s, fill=MUT); yy += 32
            for ln in body_l:
                dr.text((tx, yy), ln, font=f_s, fill=INK); yy += 27
            for ln in ok_l:
                dr.text((tx, yy), ln, font=f_s, fill=GOOD); yy += 27
            for ln in bad_l:
                dr.text((tx, yy), ln, font=f_s, fill=BAD); yy += 27
            y += ch + 14
    note = [ln for ln in d.get("text", "").split("\n") if ln.startswith("Uwaga:") or ln.startswith("Pominięte")]
    if note:
        lines = [ln for t in note for ln in _wrap(dr, t, f_s, W - 2 * M - 30)]
        need(24 + len(lines) * 27)
        for ln in lines:
            dr.text((M, y), ln, font=f_s, fill=MUT); y += 27
    for i, p in enumerate(pages):
        ImageDraw.Draw(p).text((W - M - 60, H - 40), f"{i + 1} / {len(pages)}", font=f_s, fill=MUT)
    if placed != len(d["exercises"]):
        raise SheetError(f"wklejono {placed} z {len(d['exercises'])} grafik — PDF nie został utworzony")
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=150, save_all=True, append_images=pages[1:], quality=85)
    pdf = buf.getvalue()
    n_img = pdf.count(b"/Subtype /Image")
    if n_img < len(pages):
        raise SheetError("PDF nie zawiera stron-grafik — nie oddaję pliku")
    return pdf, {"pages": len(pages), "images": placed, "exercises": len(d["exercises"]), "bytes": len(pdf)}


# ---------------- PDF na 1 strone (2026-10-03, zaakceptowany podglad) ----------------
SCALES = [1.0, 0.93, 0.86, 0.8, 0.74]
GAP = 16


def _layout1(d, s, info, imgs, k, pg=None):
    """Uklad 1-stronicowy w skali k. pg=None -> tylko pomiar. Zwraca (wysokosc, wklejone grafiki)."""
    M1 = 40
    F = {"t": _f(FONT_C, 40 * k), "r": _f(FONT, 20 * k), "h": _f(FONT_C, 27 * k), "b": _f(FONT_B, 21 * k), "s": _f(FONT, 16.5 * k),
         "n": _f(FONT_C, 30 * k), "x": _f(FONT_B, 18 * k)}
    dr = ImageDraw.Draw(pg if pg is not None else Image.new("RGB", (10, 10)))
    hh = int(118 * k)
    if pg is not None:
        dr.rectangle([0, 0, W, hh], fill=NAVY)
        dr.text((M1, int(18 * k)), (d.get("title") or "Siła").upper(), font=F["t"], fill="white")
        sub = f"{s['dow']} {s['day'][8:10]}.{s['day'][5:7]}" + (f" · {s['start']}" if s.get("start") else "") + f" · {s['dur_min']}′ · {d.get('rounds')} × każdy blok"
        dr.text((M1, int(72 * k)), sub, font=F["r"], fill=(214, 221, 230))
    y = hh + int(16 * k)
    if d.get("warmup"):
        t = "Rozgrzewka 5′: " + " · ".join(f"{w['name']} {w.get('dose') or ''}".strip() for w in d["warmup"])
        ls = _wrap(dr, t, F["r"], W - 2 * M1 - 28)
        bh = int(14 * k) * 2 + len(ls) * int(27 * k)
        if pg is not None:
            dr.rounded_rectangle([M1, y, W - M1, y + bh], 12, fill=(255, 244, 229))
            for i, ln in enumerate(ls):
                dr.text((M1 + 14, y + int(12 * k) + i * int(27 * k)), ln, font=F["r"], fill=INK)
        y += bh + int(12 * k)
    cw = (W - 2 * M1 - GAP) // 2
    iw = int(210 * k); ih = iw * 2 // 3
    exs = {e["n"]: e for e in d["exercises"]}
    prev, placed = None, 0

    def card(e, col, x0, y0, draw, rh=None):
        nonlocal placed
        inf = info.get(e["key"], {})
        tx = x0 + iw + 22; tw = x0 + cw - tx - 12
        dose = e.get("dose") or ""
        name = _wrap(dr, e["name"], F["b"], tw - int(34 * k))
        body = [ln for i, t in enumerate(inf.get("steps") or []) for ln in _wrap(dr, f"{i + 1}. {t}", F["s"], tw)]
        ok = _wrap(dr, "✓ " + inf["ok"], F["s"], tw) if inf.get("ok") else []
        bad = _wrap(dr, "✕ " + inf["bad"], F["s"], tw) if inf.get("bad") else []
        lh, nh = int(22 * k), int(27 * k)
        ch = max(ih + 20, int(10 * k) + len(name) * nh + lh * (1 + len(body) + len(ok) + len(bad)) + int(10 * k))
        if draw:
            dr.rounded_rectangle([x0, y0, x0 + cw, y0 + (rh or ch)], 14, fill=BG)
            im = imgs[e["key"]].copy(); im.thumbnail((iw, ih), Image.LANCZOS)
            pg.paste(im, (x0 + 10 + (iw - im.width) // 2, y0 + 10 + (ih - im.height) // 2)); placed += 1
            yy = y0 + int(10 * k)
            dr.text((tx, yy - 2), str(e["n"]), font=F["n"], fill=col)
            for i, ln in enumerate(name):
                dr.text((tx + int(34 * k), yy + i * nh), ln, font=F["b"], fill=INK)
            yy += len(name) * nh
            g = e["group"] + (" · akcent" if e.get("accent") else "") + "  ·  "
            dr.text((tx, yy), g, font=F["s"], fill=MUT)
            dr.text((tx + dr.textlength(g, font=F["s"]), yy - 1), dose, font=F["x"], fill=col); yy += lh
            for ln in body:
                dr.text((tx, yy), ln, font=F["s"], fill=INK); yy += lh
            for ln in ok:
                dr.text((tx, yy), ln, font=F["s"], fill=GOOD); yy += lh
            for ln in bad:
                dr.text((tx, yy), ln, font=F["s"], fill=BAD); yy += lh
        return ch

    for b in d["blocks"]:
        if b["wclass"] != "0" and prev is not None and prev != b["kg"]:
            if pg is not None:
                dr.rounded_rectangle([M1, y, W - M1, y + int(36 * k)], 10, outline=(138, 148, 160), width=2)
                msg = f"Zmiana obciążenia: {prev} → {b['kg']} kg"
                dr.text(((W - dr.textlength(msg, font=F["b"])) / 2, y + int(6 * k)), msg, font=F["b"], fill=INK)
            y += int(46 * k)
        if b["wclass"] != "0":
            prev = b["kg"]
        col = BLK.get(b["wclass"], BLK["0"]); bh = int(44 * k)
        if pg is not None:
            dr.rounded_rectangle([M1, y, W - M1, y + bh], 10, fill=col)
            dr.text((M1 + 14, y + int(7 * k)), b["head"].upper(), font=F["h"], fill="white")
            r = f"{d.get('rounds')} × runda"
            dr.text((W - M1 - 14 - dr.textlength(r, font=F["b"]), y + int(10 * k)), r, font=F["b"], fill="white")
        y += bh + int(10 * k)
        items = [exs[n] for n in b["items"]]
        for i in range(0, len(items), 2):
            row = items[i:i + 2]
            rh = max(card(e, col, M1 + j * (cw + GAP), y, False) for j, e in enumerate(row))
            if pg is not None:
                for j, e in enumerate(row):
                    card(e, col, M1 + j * (cw + GAP), y, True, rh)
            y += rh + int(10 * k)
    for t in [ln for ln in d.get("text", "").split("\n") if ln.startswith("Uwaga:") or ln.startswith("Pominięte")]:
        for ln in _wrap(dr, t, F["s"], W - 2 * M1):
            if pg is not None:
                dr.text((M1, y), ln, font=F["s"], fill=MUT)
            y += int(22 * k)
    return y + int(20 * k), placed


def build_pdf(data: dict) -> tuple[bytes, dict]:
    """PDF na JEDNEJ stronie (skala 100% -> 74%); nie miesci sie -> _build_pdf_multi. Brak grafiki = SheetError."""
    d, s, info = data["details"], data["session"], data["info"]
    imgs, missing = {}, []
    for e in d["exercises"]:
        try:
            im = Image.open(os.path.join(IMG_DIR, e["key"] + ".webp")).convert("RGB"); im.load(); imgs[e["key"]] = im
        except Exception:
            missing.append(e["name"])
    if missing:
        raise SheetError("brak grafik: " + ", ".join(missing) + " — PDF nie został utworzony")
    k = None
    for sc in SCALES:
        if _layout1(d, s, info, imgs, sc)[0] <= H:
            k = sc
            break
    if k is None:
        pdf, rep = _build_pdf_multi(data)
        rep["layout"] = "multi"
        return pdf, rep
    pg = Image.new("RGB", (W, H), "white")
    _, placed = _layout1(d, s, info, imgs, k, pg)
    if placed != len(d["exercises"]):
        raise SheetError(f"wklejono {placed} z {len(d['exercises'])} grafik — PDF nie został utworzony")
    buf = io.BytesIO()
    pg.save(buf, "PDF", resolution=150, quality=85)
    pdf = buf.getvalue()
    if pdf.count(b"/Subtype /Image") < 1:
        raise SheetError("PDF nie zawiera grafiki strony — nie oddaję pliku")
    return pdf, {"pages": 1, "images": placed, "exercises": len(d["exercises"]), "bytes": len(pdf), "scale": k, "layout": "1 strona"}
