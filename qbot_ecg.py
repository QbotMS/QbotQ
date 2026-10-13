"""EKG z zegarka (2026-10-13): analiza uderzen z surowego przebiegu + PDF do pobrania.

Zrodlo: Garmin GHS /ghs/ecg/v1/ecg/<detailId> -> reading.samples (Lead I, 30 s, 128 Hz; wartosci wg Garmina w mV),
zapisywane przez qbot3/connectors/import_garmin_heart.py w qbot_v2.ecg_recording (samples, sample_rate, lead, analysis).

analyze(samples, fs) -> uderzenia (R), odstepy RR, tetno uderzenie po uderzeniu, HRV (RMSSD, SDNN, pNN50 z czystych
odstepow NN), nieregularne uderzenia (przedwczesne / z pauza / wydluzona przerwa / odmienny ksztalt).
To ORIENTACYJNA analiza jednego odprowadzenia, nie diagnoza. Testy: tests/test_ecg.py. Dokumentacja: docs/SERCE.md.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import numpy as np

VERSION = 2
UPS = 4               # dokladnosc polozenia R: 128 Hz -> 512 Hz (jak nagrywa zegarek)
PREMATURE = 0.80      # RR krotszy niz 80% lokalnej normy = przedwczesne
PAUSE = 1.10          # nastepny RR dluzszy niz 110% = pauza wyrownawcza
LONG = 1.25           # RR dluzszy niz 125% (bez przedwczesnego przed nim) = wydluzona przerwa
SHAPE_CORR = 0.85     # korelacja ksztaltu z typowym uderzeniem ponizej = odmienny ksztalt

KIND_PL = {
    "przedwczesne_pauza": "przedwczesne uderzenie z pauzą",
    "przedwczesne": "przedwczesne uderzenie",
    "przerwa": "wydłużona przerwa",
    "ksztalt": "odmienny kształt (prawdopodobnie zakłócenie)",
}


def _bandpass(x: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, filtfilt
    b, a = butter(2, [lo / (fs / 2), min(hi / (fs / 2), 0.99)], btype="band")
    return filtfilt(b, a, x)


def detect_r(samples: list[float], fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Zalamki R (indeksy probek) + sygnal po usunieciu linii bazowej (do rysowania/ksztaltu)."""
    from scipy.signal import find_peaks
    x = np.asarray(samples, dtype=float)
    base = _bandpass(x, fs, 0.5, 40.0)
    f = _bandpass(x, fs, 5.0, 18.0)
    e = np.diff(f, prepend=f[0]) ** 2
    w = max(1, int(round(0.15 * fs)))
    integ = np.convolve(e, np.ones(w) / w, mode="same")
    edge = int(0.3 * fs)
    core = integ[edge:-edge] if len(integ) > 2 * edge else integ
    thr = 0.25 * float(np.percentile(core, 99)) if len(core) else 0.0
    pk, _ = find_peaks(integ, height=thr, distance=int(0.3 * fs))
    # biegunowosc: w odprowadzeniu I R zwykle dodatni; jesli wychylenia ujemne dominuja - odwroc
    half = int(0.1 * fs)
    pos = [base[max(0, p - half):p + half].max() for p in pk] or [0]
    neg = [-base[max(0, p - half):p + half].min() for p in pk] or [0]
    sgn = 1.0 if np.median(pos) >= np.median(neg) else -1.0
    r = []
    for p in pk:
        a, b = max(0, p - half), min(len(base), p + half)
        r.append(a + int(np.argmax(sgn * base[a:b])))
    r = np.array(sorted(set(r)), dtype=int)
    # odrzuc uderzenia przy samych brzegach nagrania (niepelne)
    r = r[(r > int(0.15 * fs)) & (r < len(x) - int(0.15 * fs))]
    return r, base * sgn


def refine_r(sig: np.ndarray, r: np.ndarray, fs: float) -> np.ndarray:
    """Polozenie R z dokladnoscia do 1/UPS probki: przebieg w okolicy zalamka przeprobkowany x UPS (FFT)."""
    from scipy.signal import resample
    out = []
    h = 6
    for i in r:
        a, b = max(0, i - h), min(len(sig), i + h + 1)
        seg = resample(sig[a:b], (b - a) * UPS)
        out.append(a + float(np.argmax(seg)) / UPS)
    return np.array(out, dtype=float)


def analyze(samples: list[float], fs: float) -> dict[str, Any]:
    if not samples or not fs:
        return {"v": VERSION, "ok": False, "error": "brak przebiegu"}
    r, sig = detect_r(samples, fs)
    out: dict[str, Any] = {"v": VERSION, "ok": True, "fs": fs, "r_idx": [int(i) for i in r], "n_beats": int(len(r))}
    if len(r) < 6:
        out.update(ok=False, error="za mało wykrytych uderzeń (słaby kontakt?)", quality="słaba")
        return out
    rf = refine_r(sig, r, fs)
    rr = np.diff(rf) / fs * 1000.0
    out["rr_ms"] = [int(round(v)) for v in rr]
    out["r_t"] = [round(float(v) / fs, 4) for v in rf]

    # ksztalt: korelacja z typowym (medianowym) uderzeniem
    a0, a1 = int(0.2 * fs), int(0.4 * fs)
    wins = [(i, sig[i - a0:i + a1]) for i in r if i - a0 >= 0 and i + a1 <= len(sig)]
    corr: dict[int, float] = {}
    if len(wins) >= 4:
        tpl = np.median(np.vstack([w for _, w in wins]), axis=0)
        for i, w in wins:
            c = np.corrcoef(tpl, w)[0, 1]
            corr[int(i)] = float(c) if np.isfinite(c) else 1.0

    flags: dict[int, dict] = {}   # klucz = numer uderzenia (indeks w r)
    n = len(rr)
    for k in range(n):
        neigh = [rr[j] for j in range(max(0, k - 4), min(n, k + 5)) if j != k]
        ref = float(np.median(neigh)) if neigh else float(rr[k])
        beat = k + 1                                     # uderzenie konczace odstep k
        if rr[k] < PREMATURE * ref:
            pause = k + 1 < n and rr[k + 1] > PAUSE * ref
            flags[beat] = {"kind": "przedwczesne_pauza" if pause else "przedwczesne", "rr_ms": int(round(rr[k])), "ref_ms": int(round(ref))}
        elif rr[k] > LONG * ref and (beat - 1) not in flags:
            flags[beat] = {"kind": "przerwa", "rr_ms": int(round(rr[k])), "ref_ms": int(round(ref))}
    for bi, i in enumerate(r):
        c = corr.get(int(i))
        if c is not None and c < SHAPE_CORR and bi not in flags:
            flags[bi] = {"kind": "ksztalt", "corr": round(c, 2)}
        elif c is not None and bi in flags:
            flags[bi]["corr"] = round(c, 2)

    irr = []
    for bi in sorted(flags):
        f = dict(flags[bi], beat=bi, t_s=round(float(r[bi]) / fs, 2), label=KIND_PL[flags[bi]["kind"]])
        irr.append(f)
    out["irregular"] = irr
    out["n_irregular"] = sum(1 for f in irr if f["kind"] != "ksztalt")   # rytm: przedwczesne / przerwy
    out["n_shape"] = sum(1 for f in irr if f["kind"] == "ksztalt")       # sam ksztalt przy normalnym rytmie
    bad = {bi for bi, f in flags.items() if f["kind"] != "ksztalt"}

    # czyste odstepy NN: bez odstepow dotykajacych oznaczonego uderzenia
    nn = np.array([rr[k] for k in range(n) if k not in bad and (k + 1) not in bad])
    hr = 60000.0 / rr
    out.update(hr_mean=round(float(60000.0 / rr.mean()), 1), hr_min=round(float(hr.min()), 1), hr_max=round(float(hr.max()), 1))
    if len(nn) >= 5:
        d = np.diff(nn)
        out.update(rmssd=round(float(np.sqrt(np.mean(d ** 2))), 1), sdnn=round(float(np.std(nn, ddof=1)), 1),
                   pnn50=round(float(np.mean(np.abs(d) > 50) * 100), 1), nn_count=int(len(nn)))
    bad_rr = int(np.sum((rr < 300) | (rr > 2000)))
    out["quality"] = "słaba" if bad_rr > 2 or len(r) < 0.6 * (len(samples) / fs) * (out["hr_mean"] / 60) else "dobra"
    return out


# ---------------- interpretacja (krotko, regulowa - bez AI) ----------------

def _pl(x, d=0) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def interpret(rec: dict[str, Any], ctx: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Kilka zdan: co wynik znaczy, czego nie widac na wykresie. status: good / warn / bad / info.

    ctx: {"others": [{"local": datetime, "rmssd": float}], "bp": [{"local": datetime, "sys", "dia"}] w +-45 min,
          "rhr_norm": float}"""
    ctx = ctx or {}
    an = rec.get("analysis") or {}
    out: list[dict[str, str]] = []
    code = rec.get("classification") or ""
    if not an.get("ok"):
        return [{"status": "info", "text": f"Analiza uderzeń niemożliwa ({an.get('error') or 'brak przebiegu'}). Powtórz nagranie: ręka oparta, palec na ramce bez ruchu."}]
    sinus = code in ("SINUS_NORMAL", "SINUS_RHYTHM")
    ni, nsh = int(an.get("n_irregular") or 0), int(an.get("n_shape") or 0)

    # 1. rytm
    if not sinus:
        out.append({"status": "bad", "text": "Garmin nie potwierdził rytmu zatokowego. Zrób drugie nagranie; jeśli wynik się powtórzy albo masz objawy – lekarz (PDF poniżej)."})
    elif ni == 0:
        out.append({"status": "good", "text": f"Rytm zatokowy, wszystkie {an.get('n_beats')} uderzeń w regularnych odstępach – bez dodatkowych pobudzeń."})
    else:
        kinds = ", ".join(sorted({i["label"] for i in an.get("irregular") or [] if i.get("kind") != "ksztalt"}))
        out.append({"status": "warn", "text": f"Rytm zatokowy, ale {ni} uderzenie(a) poza rytmem ({kinds}). Pojedyncze pobudzenia zdarzają się u zdrowych (kawa, zmęczenie); "
                                                 "jeśli wracają w kolejnych nagraniach albo czujesz kołatanie – pokaż PDF lekarzowi."})

    # 2. wahania tetna w rytmie oddechu
    hmin, hmax, hmean = an.get("hr_min"), an.get("hr_max"), an.get("hr_mean")
    if sinus and ni == 0 and hmin and hmax and hmax - hmin >= 8:
        out.append({"status": "good", "text": f"Tętno faluje {_pl(hmin)}–{_pl(hmax)} w rytmie oddechu (niemiarowość oddechowa) – to prawidłowe i typowe przy dobrej kondycji w spoczynku, nie zaburzenie rytmu."})
    if hmean and hmean < 50:
        out.append({"status": "info", "text": f"Średnio {_pl(hmean)} ud./min – wolne tętno, typowe u trenujących. Niepokojące tylko z zawrotami głowy, omdleniami lub dużym osłabieniem."})
    elif hmean and hmean > 90:
        out.append({"status": "warn", "text": f"Średnio {_pl(hmean)} ud./min w spoczynku – wysoko. Sprawdź, czy odpocząłeś 5 min przed nagraniem."})

    # 3. HRV na tle Twoich nagran (rano z rano, wieczor z wieczorem)
    rm = an.get("rmssd")
    when = rec.get("started_local")
    others = [o for o in ctx.get("others") or [] if o.get("rmssd") is not None]
    if rm is not None and when is not None:
        same = [o for o in others if (o["local"].hour < 12) == (when.hour < 12)]
        part = "porannych" if when.hour < 12 else "wieczornych"
        if len(same) >= 3:
            vals = sorted(o["rmssd"] for o in same)
            medv = vals[len(vals) // 2]
            d = rm - medv
            st = "warn" if d < -0.25 * medv else "good"
            txt = (f"HRV {_pl(rm)} ms vs Twoja mediana {part} nagrań {_pl(medv)} ms" +
                   (" – wyraźnie niżej: zmęczenie, słaby sen, stres albo początek infekcji." if st == "warn" else " – w normie."))
            out.append({"status": st, "text": txt})
        elif others:
            lo, hi = min(o["rmssd"] for o in others), max(o["rmssd"] for o in others)
            out.append({"status": "info", "text": f"HRV {_pl(rm)} ms (inne nagrania: {_pl(lo)}–{_pl(hi)} ms). Porównuj rano z rano – wieczorem, po dniu i kawie, HRV jest zwykle niższe. "
                                                   f"Ocena trendu od 3 nagrań z tej samej pory."})

    # 4. cisnienie z tej samej sesji
    bp = ctx.get("bp") or []
    if bp:
        s_ = round(sum(x["sys"] for x in bp) / len(bp)); d_ = round(sum(x["dia"] for x in bp) / len(bp))
        if s_ >= 135 or d_ >= 85:
            st, tx = "warn", " – powyżej progu dla pomiarów domowych (135/85). O wyniku zdecyduje średnia z 7-dniowej serii."
        elif s_ >= 130 or d_ >= 80:
            st, tx = "info", " – wysokie prawidłowe (granica 130/80), jeszcze nie nadciśnienie. O wyniku zdecyduje średnia z serii."
        else:
            st, tx = "good", " – prawidłowe."
        out.append({"status": st, "text": f"Ciśnienie w tej samej sesji: {s_}/{d_}{tx}"})

    # 5. jakosc
    if nsh:
        out.append({"status": "info", "text": f"{nsh} uderzenie(a) o innym kształcie przy normalnym rytmie – najpewniej ruch ręki albo słaby kontakt palca; nie wpływa na wynik."})
    elif an.get("quality") != "dobra":
        out.append({"status": "info", "text": "Słabszy sygnał – wynik orientacyjny. Przy następnym nagraniu oprzyj rękę i nie ruszaj palcem."})
    return out


# ---------------- PDF (dla lekarza) ----------------

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except Exception:
        return ImageFont.load_default(size=size)


def pdf_bytes(rec: dict[str, Any]) -> bytes:
    """A4 poziomo, siatka EKG 25 mm/s i 10 mm/mV, 3 pasy po 10 s, oznaczone uderzenia + podsumowanie."""
    from PIL import Image, ImageDraw
    dpi = 150
    mm = dpi / 25.4
    W, H = int(297 * mm), int(210 * mm)
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    fs = float(rec.get("sample_rate") or 128.0)
    x = np.asarray(rec.get("samples") or [], dtype=float)
    an = rec.get("analysis") or {}
    left, top = int(18 * mm), int(14 * mm)

    # naglowek
    when = rec.get("started_local")
    when_s = when.strftime("%d.%m.%Y %H:%M") if isinstance(when, datetime) else str(when or "")[:16]
    dr.text((left, top), f"Zapis EKG — {when_s}", fill="black", font=_font(30, True))
    dev = rec.get("device") or "zegarek"
    l2 = (f"Wynik Garmina: {rec.get('label') or rec.get('classification') or '—'} · średnie tętno {rec.get('hr_avg') or '—'} ud./min · "
          f"{dev} · odprowadzenie {rec.get('lead') or 'I'} · {int(fs)} Hz · 30 s")
    dr.text((left, top + int(9 * mm)), l2, fill="black", font=_font(20))
    if an.get("ok"):
        l3 = (f"Analiza QBot: {an.get('n_beats')} uderzeń · tętno {an.get('hr_min'):.0f}–{an.get('hr_max'):.0f} (średnio {an.get('hr_mean'):.0f}) · "
              f"HRV RMSSD {an.get('rmssd', '—')} ms · SDNN {an.get('sdnn', '—')} ms · pNN50 {an.get('pnn50', '—')}% · "
              f"nieregularne: {an.get('n_irregular', 0)} · zakłócenia kształtu: {an.get('n_shape', 0)} · jakość sygnału: {an.get('quality')}")
    else:
        l3 = f"Analiza QBot: {an.get('error') or 'brak'}"
    dr.text((left, top + int(16 * mm)), l3, fill="black", font=_font(20))
    irr = an.get("irregular") or []
    if irr:
        txt = "Nieregularne: " + "; ".join(f"{i['t_s']:.1f} s {i['label']}" for i in irr[:8]) + (" …" if len(irr) > 8 else "")
        dr.text((left, top + int(23 * mm)), txt, fill=(180, 0, 0), font=_font(19))

    # siatka + przebieg: 3 pasy po 10 s
    strip_h = int(36 * mm)
    y0 = top + int(32 * mm)
    sec_px = 25 * mm
    mv_px = 10 * mm
    r_idx = set(an.get("r_idx") or [])
    irr_t = {round(i["t_s"], 2) for i in irr}
    for s in range(3):
        ys = y0 + s * (strip_h + int(6 * mm))
        x_end = left + int(250 * mm)
        for k in range(0, 251):
            xx = left + k * mm
            dr.line([(xx, ys), (xx, ys + strip_h)], fill=(240, 180, 180) if k % 5 == 0 else (252, 228, 228), width=2 if k % 5 == 0 else 1)
        for k in range(0, int(strip_h / mm) + 1):
            yy = ys + k * mm
            dr.line([(left, yy), (x_end, yy)], fill=(240, 180, 180) if k % 5 == 0 else (252, 228, 228), width=2 if k % 5 == 0 else 1)
        base_y = ys + strip_h * 0.68
        a, b = int(s * 10 * fs), int(min(len(x), (s + 1) * 10 * fs))
        if b - a > 1:
            seg = x[a:b] - np.median(x[a:b])
            pts = [(left + (i / fs) * sec_px, base_y - v * mv_px) for i, v in enumerate(seg)]
            dr.line(pts, fill="black", width=2)
            for ri in r_idx:
                if a <= ri < b:
                    px = left + ((ri - a) / fs) * sec_px
                    red = round(ri / fs, 2) in irr_t
                    dr.polygon([(px, ys + 4), (px - 6, ys + 16), (px + 6, ys + 16)], fill=(200, 0, 0) if red else (90, 90, 90))
        dr.text((left - int(14 * mm), ys + strip_h / 2 - 10), f"{s * 10}–{s * 10 + 10} s", fill="black", font=_font(17))
        # kalibracja 1 mV
        cx = x_end + int(4 * mm)
        dr.line([(cx, base_y), (cx + 2 * mm, base_y), (cx + 2 * mm, base_y - mv_px), (cx + 7 * mm, base_y - mv_px),
                 (cx + 7 * mm, base_y), (cx + 9 * mm, base_y)], fill="black", width=2)
        dr.text((cx, base_y + 6), "1 mV", fill="black", font=_font(15))

    yi = y0 + 3 * (strip_h + int(6 * mm)) - int(2 * mm)
    for it in (rec.get("interpretation") or [])[:5]:
        mark = {"good": "+", "warn": "!", "bad": "!!", "info": "-"}.get(it["status"], "·")
        col = (180, 0, 0) if it["status"] in ("warn", "bad") else (30, 30, 30)
        dr.text((left, yi), f"{mark} {it['text']}"[:230], fill=col, font=_font(16))
        yi += int(5 * mm)
    foot = ("25 mm/s · 10 mm/mV. Zapis z zegarka: jedno odprowadzenie, 30 s. Nie wykrywa zawału, niedokrwienia ani zmian strukturalnych. "
            "Wynik rytmu: aplikacja EKG Garmin. Uderzenia, HRV i nieregularności: orientacyjna analiza QBot (trójkąty: wykryte uderzenia, czerwone: nieregularne).")
    dr.text((left, H - int(14 * mm)), foot, fill=(60, 60, 60), font=_font(15))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=dpi)
    return buf.getvalue()
