"""qbot_karoo_tlo.py - dynamiczne tlo ekranu startowego Karoo (Home Background) z danymi QBota.

2026-10-20 (sesja karoo-tlo-2010). Uklad zatwierdzony przez Michala na testach z Karoo:
- obraz 1440 x 2400 (Karoo pokazuje proporcjonalny wycinek: kafel profilu 1 = x 80-481, y 873-1585),
- zdjecie na caly widoczny obszar, czarny pas pod paskiem statusu, boki wygaszone do czerni przy dolnym pasku,
- kafel: lekka mgielka na brzegach (jak u Karoo przy wymuszonym ciemnym menu) + lagodne przyciemnienie srodka,
- dane: QBot + data, stan dnia, gotowosc, swiezosc, pogoda na nastepna jazde z Trenera (inaczej najblizsze 2 h),
  "SPRAWDZ ROWER" gdy sa niezrobione zadania serwisowe, logo QBot w prawym dolnym rogu kafla.
Wspolrzedne tekstu w "jednostkach kafla" 336 x 590 (= piksele ekranu Karoo w kaflu).
Dane zbiera qbot_web._karoo_tlo_data(); ten modul tylko rysuje (bez bazy, bez sieci).
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CW_IMG, CH_IMG = 1440, 2400
VIS = (0, 793, 600, 820)            # widoczny obszar tla (x, y, w, h) w px obrazka
CARD = (80, 873, 401, 712)          # kafel profilu 1 (x, y, w, h) w px obrazka
SPLIT = 500                         # od tej wysokosci kafla (px obrazka) boki ekranu zakrywa czarny pasek Karoo
UNIT_W = 336                        # szerokosc kafla w jednostkach ekranu Karoo
K = CARD[2] / UNIT_W                # px obrazka na jednostke
SS = 2                              # nadprobkowanie warstwy kafla (gladkie ksztalty)
FONT_DIR = "/opt/qbot/web/public/fonts/"
F_BOLD = FONT_DIR + "SairaSemiCondensed-Bold.ttf"
F_SEMI = FONT_DIR + "SairaSemiCondensed-SemiBold.ttf"

INK = (233, 228, 218)              # #e9e4da - opisy
ORANGE = (255, 122, 0)
STATUS = {"w_normie": ("W NORMIE", (123, 201, 111)), "uwaga": ("UWAGA", (242, 179, 61)),
          "zmeczony": ("ZMĘCZONY", (242, 179, 61)), "przeciazenie": ("PRZECIĄŻENIE", (255, 90, 90))}
DNI = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]


def fnum(x, d=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return ("%.*f" % (d, float(x))).replace(".", ",").replace("-", "−")


def fsg(x, d=0):
    if x is None:
        return "–"
    s = fnum(x, d)
    return ("+" + s) if float(x) > 0 and s.strip("0,−") else s


def color_r(r):
    if r is None:
        return (245, 241, 234)
    return (123, 201, 111) if r > 0.5 else ((255, 90, 90) if r < -0.5 else (245, 241, 234))


def color_tsb(t):
    if t is None:
        return (245, 241, 234)
    if t > 15:
        return (123, 201, 111)
    if t < -20:
        return (255, 90, 90)
    if t < -5:
        return (242, 179, 61)
    return (245, 241, 234)


def weather_window(hours: list, t0, t1) -> dict:
    """Godziny prognozy nachodzace na okno [t0, t1). hours: lista dictow z /api/pogoda/warunki (iso 'YYYY-MM-DDTHH:MM')."""
    from datetime import datetime, timedelta
    sel = []
    for g in hours or []:
        try:
            t = datetime.fromisoformat(str(g.get("iso"))[:16])
        except ValueError:
            continue
        if t > t0 - timedelta(seconds=3599) and t < t1:
            sel.append(g)
    if not sel:
        return {"n": 0}
    num = lambda k: [float(g.get(k) or 0) for g in sel]
    return {"n": len(sel), "tmin": min(num("temp")), "tmax": max(num("temp")), "odcz": min(num("odcz")),
            "opad": sum(max(float(g.get("opad") or 0), float(g.get("snieg") or 0)) for g in sel),
            "wiatr": sum(num("wiatr")) / len(sel), "por": max(num("porywy")),
            "kier": float(sel[0].get("kier") or 0), "skad": sel[0].get("skad") or ""}


# ---------------------------------------------------------------- rysowanie
def _font(path, size_u):
    return ImageFont.truetype(path, max(6, int(round(size_u * K * SS))))


def _p(u):
    return u * K * SS


def _text(layer, shadow, xy_u, txt, size_u, col, bold=True, anchor="ls", shade=True):
    f = _font(F_BOLD if bold else F_SEMI, size_u)
    x, y = _p(xy_u[0]), _p(xy_u[1])
    if shade:
        ImageDraw.Draw(shadow).text((x, y + _p(1.5)), txt, font=f, fill=(0, 0, 0, 217), anchor=anchor)
    ImageDraw.Draw(layer).text((x, y), txt, font=f, fill=tuple(col) + (255,), anchor=anchor)


def _cover(photo: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / photo.width, h / photo.height)
    im = photo.resize((max(1, round(photo.width * s)), max(1, round(photo.height * s))), Image.LANCZOS)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


def _vgrad(w, h, a0, a1):
    g = Image.linear_gradient("L").resize((w, h))      # 0 u gory -> 255 u dolu
    return g.point(lambda v: int(a0 + (a1 - a0) * v / 255))


def _logo(layer, shadow, cx_u, cy_u, r_u):
    """Logo QBot rysowane od nowa: pierscien Q z pomaranczowym gradientem, ogonek, biala linia pulsu."""
    cx, cy, r = _p(cx_u), _p(cy_u), _p(r_u)
    w_ring, w_tail, w_pulse = _p(7.5), _p(8), _p(4.2)
    shape = Image.new("L", layer.size, 0)
    d = ImageDraw.Draw(shape)
    d.ellipse((cx - r - w_ring / 2, cy - r - w_ring / 2, cx + r + w_ring / 2, cy + r + w_ring / 2), fill=255)
    d.ellipse((cx - r + w_ring / 2, cy - r + w_ring / 2, cx + r - w_ring / 2, cy + r - w_ring / 2), fill=0)
    a = (cx + r * 0.72, cy + r * 0.72)
    b = (cx + r * 1.18, cy + r * 1.18)
    d.line([a, b], fill=255, width=int(w_tail))
    for q in (a, b):
        d.ellipse((q[0] - w_tail / 2, q[1] - w_tail / 2, q[0] + w_tail / 2, q[1] + w_tail / 2), fill=255)
    sh = shape.filter(ImageFilter.GaussianBlur(_p(6)))
    shadow.paste((0, 0, 0, 255), (0, 0), sh.point(lambda v: int(v * 0.65)))
    # gradient #FFB347 -> #FF6A00 po przekatnej
    grad = Image.linear_gradient("L").rotate(45, expand=True).resize(layer.size)
    c0, c1 = (255, 179, 71), (255, 106, 0)
    col = Image.merge("RGB", [grad.point(lambda v, i=i: int(c0[i] + (c1[i] - c0[i]) * v / 255)) for i in range(3)])
    layer.paste(col, (0, 0), shape)
    d2 = ImageDraw.Draw(layer)
    pts = [(-21, 4), (-14, 4), (-9, -3), (-3, 8), (3, -16), (9, 9), (14, 0), (19, 0)]
    d2.line([(cx + _p(x), cy + _p(y)) for x, y in pts], fill=(255, 255, 255, 255), width=int(w_pulse), joint="curve")
    dr = _p(3.6)
    d2.ellipse((cx + _p(23) - dr, cy - dr, cx + _p(23) + dr, cy + dr), fill=(255, 138, 31, 255))


def render(data: dict, photo_path: str) -> bytes:
    """data: {date_label, status, r, tsb, head, title, W, bike_tasks}. Zwraca PNG 1440 x 2400."""
    base = Image.new("RGB", (CW_IMG, CH_IMG), (0, 0, 0))
    vx, vy, vw, vh = VIS
    try:
        photo = Image.open(photo_path).convert("RGB")
        base.paste(_cover(photo, vw, vh), (vx, vy))
    except OSError:
        pass
    black = Image.new("RGB", (CW_IMG, CH_IMG), (0, 0, 0))
    # czarny pas pod paskiem statusu + przejscie
    base.paste((0, 0, 0), (0, 0, CW_IMG, 842))
    base.paste(black.crop((0, 0, CW_IMG, 63)), (0, 842), _vgrad(CW_IMG, 63, 255, 0))
    # boki: wygaszenie do czerni przy dolnym pasku Karoo
    cx, cy, cw, ch = CARD
    side = _vgrad(cx, 183, 0, 255)
    base.paste(black.crop((0, 0, cx, 183)), (0, 1190), side)
    base.paste(black.crop((0, 0, CW_IMG - cx - cw, 183)), (cx + cw, 1190), _vgrad(CW_IMG - cx - cw, 183, 0, 255))
    base.paste((0, 0, 0), (0, 1373, cx, CH_IMG))
    base.paste((0, 0, 0), (cx + cw, 1373, CW_IMG, CH_IMG))
    base.paste((0, 0, 0), (0, vy + vh, CW_IMG, CH_IMG))

    # kafel: ciemny srodek z miekkimi brzegami (40%, rozmycie 60)
    pad = 160
    m = Image.new("L", (cw + 2 * pad, ch + 2 * pad), 0)
    dm = ImageDraw.Draw(m)
    dm.rectangle((pad + 30, pad + 30, pad + cw - 30, pad + ch + 200), fill=102)
    dm.rectangle((pad - 60, pad + SPLIT - 40, pad + cw + 60, pad + ch), fill=102)
    m = m.filter(ImageFilter.GaussianBlur(30)).crop((pad, pad, pad + cw, pad + ch))
    tile = base.crop((cx, cy, cx + cw, cy + ch))
    tile = Image.composite(Image.new("RGB", tile.size, (6, 8, 8)), tile, m)
    # lekka mgielka na brzegach (14% bieli), znika do srodka i ponizej SPLIT
    inner = Image.new("L", (cw + 2 * pad, ch + 2 * pad), 0)
    ImageDraw.Draw(inner).rectangle((pad + 30, pad + 30, pad + cw - 30, pad + ch + 200), fill=255)
    inner = inner.filter(ImageFilter.GaussianBlur(11)).crop((pad, pad, pad + cw, pad + ch))
    veil = inner.point(lambda v: int(36 * (255 - v) / 255))
    fade = Image.new("L", (cw, ch), 255)
    fade.paste(_vgrad(cw, 140, 255, 0), (0, SPLIT - 140))
    fade.paste(0, (0, SPLIT, cw, ch))
    veil = Image.composite(veil, Image.new("L", (cw, ch), 0), fade)
    tile = Image.composite(Image.new("RGB", tile.size, (255, 255, 255)), tile, veil)
    base.paste(tile, (cx, cy))

    # warstwa danych (nadprobkowana)
    LW, LH = cw * SS, ch * SS
    layer = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    L, R, M = 44, 292, 168
    _text(layer, shadow, (L, 64), "QBot", 26, ORANGE)
    _text(layer, shadow, (R, 64), data.get("date_label", ""), 21, INK, bold=False, anchor="rs")
    st_word, st_col = data.get("status") or ("–", (207, 207, 207))
    sp = Image.new("L", (LW, LH), 0)
    ImageDraw.Draw(sp).rounded_rectangle((_p(L), _p(80), _p(R), _p(128)), radius=_p(12), fill=255)
    shadow.paste((0, 0, 0, 255), (0, 0), sp.filter(ImageFilter.GaussianBlur(_p(4))).point(lambda v: int(v * 0.5)))
    ImageDraw.Draw(layer).rounded_rectangle((_p(L), _p(80), _p(R), _p(128)), radius=_p(12), fill=tuple(st_col) + (255,))
    _text(layer, shadow, (M, 114), st_word, 28, (17, 17, 17), anchor="ms", shade=False)
    r, tsb = data.get("r"), data.get("tsb")
    _text(layer, shadow, (106, 190), fsg(r, 1), 54, color_r(r), anchor="ms")
    _text(layer, shadow, (106, 214), "gotowość", 18, INK, bold=False, anchor="ms")
    _text(layer, shadow, (230, 190), fsg(None if tsb is None else round(tsb)), 54, color_tsb(tsb), anchor="ms")
    _text(layer, shadow, (230, 214), "świeżość", 18, INK, bold=False, anchor="ms")
    dl = ImageDraw.Draw(layer)
    dl.line([(_p(M), _p(146)), (_p(M), _p(216))], fill=(255, 255, 255, 71), width=max(1, int(_p(1.5))))
    dl.line([(_p(L), _p(234)), (_p(R), _p(234))], fill=(255, 255, 255, 71), width=max(1, int(_p(1.5))))
    _text(layer, shadow, (L, 264), data.get("head", ""), 20, (255, 154, 60))
    title = data.get("title")
    if title:
        title = title if len(title) <= 22 else title[:21] + "…"
        _text(layer, shadow, (L, 288), title, 18, INK, bold=False)
    W = data.get("W") or {"n": 0}
    y0 = 346 if title else 322
    if not W.get("n"):
        _text(layer, shadow, (L, y0), "brak prognozy", 22, INK, bold=False)
    else:
        t = fnum(W["tmin"]) + "°" if round(W["tmin"]) == round(W["tmax"]) else fnum(W["tmin"]) + "–" + fnum(W["tmax"]) + "°"
        _text(layer, shadow, (L, y0), t, 54, (255, 255, 255))
        _text(layer, shadow, (L, y0 + 24), "odczuwalna " + fnum(W["odcz"]) + "°", 18, INK, bold=False)
        ang = math.radians((W.get("kier") or 0) + 180)
        ax, ay = 204, y0 - 18
        poly = []
        for px, py in [(0, -16), (10, 12), (0, 6), (-10, 12)]:
            rx = px * math.cos(ang) - py * math.sin(ang)
            ry = px * math.sin(ang) + py * math.cos(ang)
            poly.append((_p(ax + rx), _p(ay + ry)))
        ImageDraw.Draw(shadow).polygon([(x, y + _p(1.5)) for x, y in poly], fill=(0, 0, 0, 200))
        dl.polygon(poly, fill=(255, 255, 255, 255))
        _text(layer, shadow, (224, y0 - 4), fnum(W["wiatr"], 1), 34, (255, 255, 255))
        _text(layer, shadow, (224, y0 + 18), "m/s · " + str(W.get("skad") or ""), 16, INK, bold=False)
        wet = W["opad"] >= 0.1
        _text(layer, shadow, (L, y0 + 60), (fnum(W["opad"], 1) + " mm" if wet else "bez opadu") + " · porywy " + fnum(W["por"]),
              19, (124, 192, 255) if wet else (255, 255, 255), bold=False)
    if data.get("bike_tasks"):
        f = _font(F_BOLD, 19)
        tw = ImageDraw.Draw(layer).textlength("SPRAWDŹ ROWER", font=f) / (K * SS)
        pw2 = tw + 56
        px = (UNIT_W - pw2) / 2
        pm = Image.new("L", (LW, LH), 0)
        ImageDraw.Draw(pm).rounded_rectangle((_p(px), _p(446), _p(px + pw2), _p(482)), radius=_p(18), fill=255)
        shadow.paste((0, 0, 0, 255), (0, 0), pm.filter(ImageFilter.GaussianBlur(_p(5))).point(lambda v: int(v * 0.55)))
        dl.rounded_rectangle((_p(px), _p(446), _p(px + pw2), _p(482)), radius=_p(18), fill=(255, 194, 51, 255))
        dl.polygon([(_p(px + 20), _p(454)), (_p(px + 31), _p(474)), (_p(px + 9), _p(474))], fill=(26, 18, 5, 255))
        dl.rectangle((_p(px + 19), _p(460), _p(px + 21.4), _p(468)), fill=(255, 194, 51, 255))
        dl.rectangle((_p(px + 19), _p(470), _p(px + 21.4), _p(472.4)), fill=(255, 194, 51, 255))
        dl.text((_p(px + 39), _p(471)), "SPRAWDŹ ROWER", font=f, fill=(26, 18, 5, 255), anchor="ls")
    _logo(layer, shadow, 272, 528, 30)

    shadow = shadow.filter(ImageFilter.GaussianBlur(_p(3.5)))
    comp = Image.alpha_composite(shadow, layer).resize((cw, ch), Image.LANCZOS)
    tile = base.crop((cx, cy, cx + cw, cy + ch)).convert("RGBA")
    base.paste(Image.alpha_composite(tile, comp).convert("RGB"), (cx, cy))
    out = io.BytesIO()
    base.save(out, "PNG", optimize=True)
    return out.getvalue()


def status_of(day_status: str | None):
    return STATUS.get(day_status or "", (str(day_status or "–").replace("_", " ").upper(), (207, 207, 207)))
