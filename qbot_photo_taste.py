# -*- coding: utf-8 -*-
"""Gust zdjec Michala (2026-09-28): kalibracja w rundach.

Runda: QBot pobiera kandydatow ze Stravy (tylko >= MIN_PX na dluzszym boku), liczy proste cechy obrazu,
Michal na /zdjecia.html oznacza "podoba mi sie" / "nie", QBot dopasowuje regresje logistyczna (numpy, L2)
i w kolejnej rundzie ustawia kandydatow od najbardziej pasujacych (+ ~25% na probe).
Cechy: ostrosc, jasnosc, nasycenie, kolorowosc, szczegolowosc (krawedzie), zielen, niebo, poziome kadry,
rozdzielczosc, zlota godzina, jazda-wyjazd (km od domu), dlugosc jazdy."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageOps

MIN_PX = 1600
FEATS = ["ostrosc", "jasnosc", "nasycenie", "kolorowosc", "szczegoly", "zielen", "niebo", "poziome", "rozdzielczosc",
         "zlota_godzina", "wyjazd", "dluga_jazda"]
NAZWY = {"ostrosc": "ostrość", "jasnosc": "jasność", "nasycenie": "nasycenie kolorów", "kolorowosc": "kolorowość",
         "szczegoly": "dużo szczegółów", "zielen": "zieleń", "niebo": "niebo w kadrze", "poziome": "kadr poziomy",
         "rozdzielczosc": "rozdzielczość", "zlota_godzina": "złota godzina", "wyjazd": "zdjęcie z wyjazdu", "dluga_jazda": "długa jazda"}
# przed pierwszymi ocenami: ostre, poziome, z wyjazdow
PRIOR = {"ostrosc": 1.2, "poziome": 0.6, "wyjazd": 0.5, "rozdzielczosc": 0.3, "kolorowosc": 0.2}
CENTER = {"ostrosc": 5.6, "poziome": 0.5, "wyjazd": 0.5, "rozdzielczosc": 0.8, "kolorowosc": 0.15}


def image_features(path: str) -> dict:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    sm = im.copy(); sm.thumbnail((512, 512))
    a = np.asarray(sm, dtype=np.float32) / 255.0
    g = a.mean(axis=2)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    mx, mn = a.max(axis=2), a.min(axis=2)
    rg = a[..., 0] - a[..., 1]; yb = 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    top = a[: max(1, a.shape[0] // 3)]
    return {
        "ostrosc": float(np.log1p(lap.var() * 1e4)),
        "jasnosc": float(g.mean()),
        "nasycenie": float(((mx - mn) / (mx + 1e-6)).mean()),
        "kolorowosc": float(math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2)),
        "szczegoly": float(np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean()),
        "zielen": float(((a[..., 1] > a[..., 0]) & (a[..., 1] > a[..., 2])).mean()),
        "niebo": float(((top[..., 2] > top[..., 0] + 0.05) & (top[..., 2] > 0.45)).mean()),
        "poziome": 1.0 if w >= h * 1.1 else 0.0,
        "rozdzielczosc": float(min(1.0, max(w, h) / 2048.0)),
        "w": w, "h": h,
    }


def context_features(taken_hour, away_km, dist_km) -> dict:
    zg = 0.0
    if taken_hour is not None:
        zg = 1.0 if (taken_hour <= 8 or taken_hour >= 18) else 0.0
    return {"zlota_godzina": zg, "wyjazd": 1.0 if (away_km or 0) > 80 else 0.0, "dluga_jazda": float(min(1.0, (dist_km or 0) / 120.0))}


def _mat(rows):
    return np.array([[float((r or {}).get(k) or 0.0) for k in FEATS] for r in rows], dtype=np.float64)


def fit(feats: list, labels: list, l2: float = 6.0) -> dict | None:   # mocniejsza regularyzacja: przy malej liczbie ocen model byl zbyt pewny (99-100%)
    """Regresja logistyczna na cechach standaryzowanych. None gdy za malo ocen (< 3 na klase)."""
    y = np.array(labels, dtype=np.float64)
    if len(y) < 6 or y.sum() < 3 or (len(y) - y.sum()) < 3:
        return None
    X = _mat(feats); mu = X.mean(0); sd = X.std(0) + 1e-6; Z = (X - mu) / sd
    wv = np.zeros(Z.shape[1]); b = 0.0
    for _ in range(600):
        p = 1 / (1 + np.exp(-(Z @ wv + b)))
        gw = Z.T @ (p - y) / len(y) + l2 * wv / len(y); gb = float((p - y).mean())
        wv -= 0.5 * gw; b -= 0.5 * gb
    acc = float(((1 / (1 + np.exp(-(Z @ wv + b))) > 0.5) == (y > 0.5)).mean())
    return {"w": wv.tolist(), "b": b, "mu": mu.tolist(), "sd": sd.tolist(), "n": int(len(y)), "liked": int(y.sum()), "acc": acc}


def score(model: dict | None, f: dict) -> float:
    """0..1 - jak bardzo zdjecie pasuje do gustu (bez modelu: prior)."""
    if not f:
        return 0.0
    if not model:
        s = sum(PRIOR.get(k, 0) * (float(f.get(k) or 0) - CENTER.get(k, 0)) for k in FEATS)
        return float(1 / (1 + math.exp(-s)))
    x = (_mat([f])[0] - np.array(model["mu"])) / np.array(model["sd"])
    z = float(np.clip(x @ np.array(model["w"]) + model["b"], -30.0, 30.0))   # bez przepelnienia (kolumna REAL)
    return round(1 / (1 + math.exp(-z)), 5)


def explain(model: dict | None, top: int = 4) -> list:
    if not model:
        return [{"cecha": NAZWY[k], "waga": PRIOR[k], "znak": "+"} for k in PRIOR][:top]
    pairs = sorted(zip(FEATS, model["w"]), key=lambda t: -abs(t[1]))[:top]
    return [{"cecha": NAZWY[k], "waga": round(v, 2), "znak": "+" if v > 0 else "−"} for k, v in pairs]
