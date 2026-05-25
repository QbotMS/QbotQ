"""
email_template.py v3 — email-safe HTML, działa w Gmail web
Ciemne tło przez bgcolor (atrybut HTML, Gmail nie może go usunąć)
"""
import json
import re
import html
import base64
from datetime import date
from functools import lru_cache
from pathlib import Path
from qbot_readiness import evaluate_readiness

BG      = "#0f1117"
BG2     = "#1a1d27"
BG3     = "#22263a"
BG_OK   = "#0d2318"
BG_WARN = "#241c08"
BG_BAD  = "#220d0d"
TXT     = "#f5f6fa"
TXT2    = "#c8cdd8"
TXT3    = "#4a5166"
OK      = "#5dba7a"
WARN    = "#e8a840"
BAD     = "#e05555"
BORDER  = "#2a2e3d"
TUSCANY_BANNER_PATH = Path(__file__).resolve().parent / "outgoing" / "banners" / "tuscany_gravel_banner.png"

def card(label, value, sub=None, color=None, bg=None):
    c  = color or TXT
    bg = bg or BG2
    sub_html = f'<div style="font-size:12px;color:{TXT2};margin-top:3px;">{sub}</div>' if sub else ""
    return f"""<td style="padding:5px;" width="33%">
      <table width="100%" cellpadding="14" cellspacing="0" bgcolor="{bg}"
             style="border-radius:10px;border:1px solid {BORDER};">
        <tr><td>
          <div style="font-size:12px;color:{TXT2};margin-bottom:4px;">{label}</div>
          <div style="font-size:22px;font-weight:bold;color:{c};">{value}</div>
          {sub_html}
        </td></tr>
      </table>
    </td>"""

def row3(*cards_html):
    return f'<table width="100%" cellpadding="0" cellspacing="0"><tr>{"".join(cards_html)}</tr></table>'

def section_label(text):
    return (f'<div style="font-size:11px;font-weight:bold;color:{TXT3};'
            f'text-transform:uppercase;letter-spacing:1.2px;'
            f'margin:0 0 12px 0;">{text}</div>')

def comment(text):
    return (f'<div style="font-size:19px;color:{TXT2};line-height:1.8;text-align:justify;'
            f'margin:12px 0 0 0;padding:0 2px;">{text}</div>')

def small_note(text, color=None):
    c = color or TXT2
    return (
        f'<table width="100%" cellpadding="12" cellspacing="0" bgcolor="{BG2}"'
        f' style="border-radius:8px;border:1px solid {BORDER};margin-bottom:8px;">'
        f'<tr><td style="font-size:14px;color:{c};line-height:1.55;">{text}</td></tr></table>'
    )

def sep():
    return f'<div style="border-top:1px solid {BORDER};margin:22px 0;"></div>'

def hrv_chart(values):
    if not values: return ""
    mv = max(values) or 1
    bars = ""
    for i, v in enumerate(values):
        h   = max(4, int((v/mv)*50))
        c   = OK if v >= 80 else (WARN if v >= 70 else BAD)
        bold = "font-weight:bold;" if i == len(values)-1 else ""
        bars += (f'<td style="text-align:center;vertical-align:bottom;padding:0 2px;">'
                 f'<div style="background:{c};width:24px;height:{h}px;'
                 f'border-radius:3px 3px 0 0;margin:0 auto;"></div>'
                 f'<div style="font-size:11px;color:{TXT2};margin-top:4px;{bold}">{int(v)}</div>'
                 f'</td>')
    return f"""<table width="100%" cellpadding="14" cellspacing="0" bgcolor="{BG2}"
       style="border-radius:10px;border:1px solid {BORDER};margin-bottom:10px;">
  <tr><td>
    <div style="font-size:12px;color:{TXT3};margin-bottom:10px;">Trend HRV — ostatnie dni</div>
    <table cellpadding="0" cellspacing="0"><tr>{bars}</tr></table>
  </td></tr>
</table>"""

def tbl(headers, rows):
    ths = "".join(
        f'<th style="text-align:{"left"if i==0 else"right"};padding:8px 6px;'
        f'font-size:12px;color:{TXT3};border-bottom:1px solid {BORDER};'
        f'font-weight:normal;">{h}</th>'
        for i,h in enumerate(headers)
    )
    trs = ""
    for j,row in enumerate(rows):
        bdr = f"border-bottom:1px solid {BORDER};" if j<len(rows)-1 else ""
        tds = ""
        for i,cell in enumerate(row):
            val   = cell[0] if isinstance(cell,tuple) else cell
            style = cell[1] if isinstance(cell,tuple) and len(cell)>1 else ""
            align = "left" if i==0 else "right"
            tds += (f'<td style="text-align:{align};padding:10px 6px;'
                    f'font-size:14px;{style}">{val}</td>')
        trs += f'<tr style="{bdr}">{tds}</tr>'
    return f'<table width="100%" cellpadding="0" cellspacing="0"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'

def delta(now, prev, hi=True):
    if now is None or prev is None: return "—", TXT2
    d = round(now-prev, 1)
    c = OK if (d>0)==hi else (BAD if abs(d)>3 else WARN)
    return (f"+{d}" if d>0 else str(d)), c


@lru_cache(maxsize=1)
def _tuscany_banner_data_uri():
    if not TUSCANY_BANNER_PATH.exists():
        return None
    encoded = base64.b64encode(TUSCANY_BANNER_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ── Nowe komponenty wizualne ─────────────────────────────────────────────────

def header_svg():
    return (
        '<svg width="640" height="80" viewBox="0 0 640 80" xmlns="http://www.w3.org/2000/svg"'
        ' style="display:block;border-radius:12px;margin-bottom:18px;max-width:100%;">'
        '<defs>'
        '<linearGradient id="hg" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#0d1e35"/>'
        '<stop offset="100%" stop-color="#0f1117"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="640" height="80" fill="url(#hg)"/>'
        '<polygon points="260,6 400,72 120,72" fill="#1a3050" opacity="0.7"/>'
        '<polygon points="390,14 510,72 270,72" fill="#122540" opacity="0.85"/>'
        '<polygon points="490,18 590,72 390,72" fill="#0c1c30" opacity="0.9"/>'
        '<path d="M0,74 Q160,62 320,67 Q480,72 640,60" stroke="#1e3a5f" stroke-width="3" fill="none"/>'
        '<circle cx="70" cy="22" r="17" fill="#e8a840" opacity="0.9"/>'
        '<circle cx="70" cy="22" r="23" fill="none" stroke="#e8a840" stroke-width="1" opacity="0.25"/>'
        # Bike silhouette
        '<g transform="translate(582,42)" fill="none" stroke="#5dba7a" stroke-width="2" opacity="0.75">'
        '<circle cx="-20" cy="16" r="11"/>'
        '<circle cx="20" cy="16" r="11"/>'
        '<polyline points="-20,16 -10,4 4,4 20,16" />'
        '<polyline points="4,4 -5,16 -20,16"/>'
        '<polyline points="4,4 4,-3 10,-3"/>'
        '<circle cx="4" cy="-3" r="2" fill="#5dba7a" stroke="none"/>'
        '</g>'
        '<text x="320" y="42" text-anchor="middle" fill="#ffffff" font-family="Arial,sans-serif"'
        ' font-size="13" letter-spacing="3" opacity="0.55">Q · RAPORT KOLARZA</text>'
        '</svg>'
    )


WMO_EMOJI = {
    0:"☀️", 1:"🌤️", 2:"⛅", 3:"☁️",
    45:"🌫️", 48:"🌫️",
    51:"🌦️", 53:"🌦️", 55:"🌧️",
    56:"🌧️", 57:"🌧️",
    61:"🌧️", 63:"🌧️", 65:"🌧️",
    66:"🌧️", 67:"🌧️",
    71:"❄️", 73:"❄️", 75:"❄️", 77:"🌨️",
    80:"🌦️", 81:"🌧️", 82:"⛈️",
    85:"🌨️", 86:"🌨️",
    95:"⛈️", 96:"⛈️", 99:"⛈️",
}


def weather_hours_chart(hours):
    """Kafelki pogody co 3 godziny dla dzisiejszego dnia."""
    if not hours:
        return ""
    n    = len(hours)
    wpct = f"{100 // n}%"
    cells = ""
    for h in hours:
        temp  = h.get("temp")
        wind  = h.get("wiatr_ms")
        cloud = h.get("zachmurzenie")
        kod   = int(h.get("kod") or 0)
        emoji = WMO_EMOJI.get(kod, "🌡️")
        t_col = BAD  if temp is not None and temp < 5  else (WARN if temp is not None and temp < 14 else OK)
        w_col = BAD  if wind is not None and wind > 8  else (WARN if wind is not None and wind > 5  else TXT2)
        cells += (
            f'<td style="padding:3px;text-align:center;vertical-align:top;" width="{wpct}">'
            f'<table width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG2}"'
            f' style="border-radius:8px;border:1px solid {BORDER};">'
            f'<tr><td style="padding:8px 4px;text-align:center;">'
            f'<div style="font-size:11px;color:{TXT3};font-weight:bold;margin-bottom:4px;">'
            f'{h.get("godzina","")}</div>'
            f'<div style="font-size:22px;line-height:1.25;">{emoji}</div>'
            f'<div style="font-size:15px;font-weight:bold;color:{t_col};margin-top:4px;">'
            f'{f"{temp:.0f}°" if temp is not None else "—"}</div>'
            f'<div style="font-size:11px;color:{w_col};margin-top:2px;">'
            f'{f"{wind} m/s" if wind is not None else "—"}</div>'
            f'<div style="font-size:11px;color:{TXT3};margin-top:1px;">'
            f'{f"☁ {int(cloud)}%" if cloud is not None else "—"}</div>'
            f'</td></tr></table></td>'
        )
    return (
        f'<div style="margin-top:12px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>'
        f'</div>'
    )


def calorie_chart(historia):
    """7-dniowy wykres: przyjęte kcal (niebieski) + bilans (zielony/czerwony)."""
    valid = [h for h in (historia or [])
             if h.get("przyjete") and h.get("bilans") is not None]
    if len(valid) < 2:
        return ""

    max_p  = max(h["przyjete"] for h in valid) or 1
    max_b  = max(abs(h["bilans"]) for h in valid) or 1
    BAR_H  = 60
    BIL_H  = 36

    cols = ""
    for h in valid:
        dzien = h["data"][5:].replace("-", ".")
        p     = h["przyjete"]
        b     = h["bilans"]
        p_h   = max(4, int(p / max_p * BAR_H))
        b_h   = max(4, int(abs(b) / max_b * BIL_H))
        b_col = OK if b >= 0 else BAD
        b_lbl = f"+{b}" if b > 0 else str(b)
        cols += (
            f'<td style="text-align:center;padding:0 3px;vertical-align:bottom;">'
            f'<div style="background:#2d4a7a;width:28px;height:{p_h}px;'
            f'border-radius:3px 3px 0 0;margin:0 auto;" title="{p} kcal"></div>'
            f'<div style="height:2px;background:{BORDER};margin:1px auto;width:28px;"></div>'
            f'<div style="background:{b_col};width:28px;height:{b_h}px;'
            f'border-radius:0 0 3px 3px;margin:0 auto;opacity:0.85;" title="{b_lbl} kcal"></div>'
            f'<div style="font-size:10px;color:{TXT3};margin-top:4px;">{dzien}</div>'
            f'<div style="font-size:10px;color:{b_col};font-weight:bold;">{b_lbl}</div>'
            f'</td>'
        )

    # Trend: ostatnie 3 vs pierwsze 3
    first3     = [h["bilans"] for h in valid[:3]]
    last3      = [h["bilans"] for h in valid[-3:]]
    trend_diff = sum(last3) / len(last3) - sum(first3) / len(first3)
    if trend_diff > 100:
        trend_txt, trend_col = "↗ bilans się poprawia", OK
    elif trend_diff < -100:
        trend_txt, trend_col = "↘ bilans się pogarsza", BAD
    else:
        trend_txt, trend_col = "→ bilans stabilny", TXT2

    legend = (
        f'<table cellpadding="0" cellspacing="4" style="margin-bottom:10px;"><tr>'
        f'<td><div style="width:12px;height:12px;background:#2d4a7a;border-radius:2px;"></div></td>'
        f'<td style="padding-right:16px;font-size:12px;color:{TXT2};">Przyjęte kcal</td>'
        f'<td><div style="width:12px;height:12px;background:{BAD};border-radius:2px;"></div></td>'
        f'<td style="padding-right:16px;font-size:12px;color:{TXT2};">Deficyt</td>'
        f'<td><div style="width:12px;height:12px;background:{OK};border-radius:2px;"></div></td>'
        f'<td style="font-size:12px;color:{TXT2};">Nadwyżka</td>'
        f'</tr></table>'
    )

    return (
        legend +
        f'<table width="100%" cellpadding="14" cellspacing="0" bgcolor="{BG2}"'
        f' style="border-radius:10px;border:1px solid {BORDER};margin-bottom:4px;"><tr><td>'
        f'<table cellpadding="0" cellspacing="0"><tr>{cols}</tr></table>'
        f'<div style="font-size:13px;color:{trend_col};font-weight:bold;margin-top:10px;">'
        f'{trend_txt}</div>'
        f'</td></tr></table>'
    )


def event_banner_svg(trip_name):
    """Deterministyczny baner eventu bez zewnętrznych obrazów."""
    name = html.escape(trip_name or "Wyjazd")
    key = name.lower()
    if any(x in key for x in ["tuscany", "toskania", "toskan"]):
        # Komiksowo-gravelowy baner inspirowany dostarczonym artworkiem.
        return (
            f'<svg width="640" height="208" viewBox="0 0 640 208" xmlns="http://www.w3.org/2000/svg"'
            f' style="display:block;border-radius:16px;margin:0 0 14px 0;max-width:100%;">'
            f'<defs>'
            f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="#f3ddb0"/>'
            f'<stop offset="100%" stop-color="#c7a06a"/>'
            f'</linearGradient>'
            f'<linearGradient id="haze" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0%" stop-color="#f8f0d0" stop-opacity="0.4"/>'
            f'<stop offset="100%" stop-color="#f8f0d0" stop-opacity="0"/>'
            f'</linearGradient>'
            f'<filter id="grain" x="-20%" y="-20%" width="140%" height="140%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" stitchTiles="stitch"/>'
            f'<feColorMatrix type="saturate" values="0"/>'
            f'<feComponentTransfer><feFuncA type="table" tableValues="0 0.07"/></feComponentTransfer>'
            f'</filter>'
            f'</defs>'
            f'<rect width="640" height="208" fill="url(#sky)"/>'
            f'<rect width="640" height="208" fill="url(#haze)"/>'
            f'<rect width="640" height="208" filter="url(#grain)" opacity="0.16"/>'
            f'<path d="M0,162 C88,120 142,104 206,110 C280,117 336,154 412,136 C490,118 548,86 640,100 L640,208 L0,208 Z" fill="#6a6d56"/>'
            f'<path d="M0,146 C96,104 154,90 224,92 C300,94 348,132 420,120 C494,108 552,78 640,84 L640,208 L0,208 Z" fill="#7d7f60"/>'
            f'<path d="M0,130 C86,92 148,76 226,80 C300,84 354,120 430,108 C508,96 564,66 640,70 L640,208 L0,208 Z" fill="#9c9168"/>'
            f'<path d="M34,120 C86,94 136,78 196,82" stroke="#f0e3b8" stroke-width="2" fill="none" stroke-dasharray="3 7" opacity="0.25"/>'
            f'<path d="M86,126 C136,102 178,88 244,86" stroke="#f0e3b8" stroke-width="2" fill="none" stroke-dasharray="2 7" opacity="0.18"/>'
            f'<path d="M238,208 C262,174 284,146 308,124 C334,100 360,86 390,72" stroke="#f4e8d1" stroke-width="7" fill="none" stroke-linecap="round"/>'
            f'<path d="M238,208 C262,174 284,146 308,124 C334,100 360,86 390,72" stroke="#f6d38b" stroke-width="2" fill="none" stroke-linecap="round" opacity="0.36"/>'
            f'<path d="M72,170 C118,150 150,126 200,112" stroke="#8b6a3f" stroke-width="10" fill="none" opacity="0.4" stroke-linecap="round"/>'
            f'<path d="M94,160 C118,148 142,136 176,122" stroke="#3f4731" stroke-width="4" fill="none" opacity="0.6" stroke-linecap="round"/>'
            f'<g transform="translate(486,24)">'
            f'<path d="M44,0 L56,0 L58,18 L42,18 Z" fill="#2d2a23"/>'
            f'<rect x="46" y="18" width="8" height="116" rx="4" fill="#2d2a23"/>'
            f'<path d="M-8,26 L48,26 L48,54 L-8,54 Z" fill="#e0c79a" stroke="#2d2a23" stroke-width="2"/>'
            f'<path d="M-2,34 L44,34" stroke="#2d2a23" stroke-width="2" opacity="0.45"/>'
            f'<text x="20" y="43" text-anchor="middle" fill="#1f1b17" font-family="Arial,sans-serif" font-size="12" font-weight="bold">STRADA BIANCA</text>'
            f'<path d="M-8,58 L48,58 L48,86 L-8,86 Z" fill="#e0c79a" stroke="#2d2a23" stroke-width="2"/>'
            f'<path d="M-2,66 L44,66" stroke="#2d2a23" stroke-width="2" opacity="0.45"/>'
            f'<text x="20" y="75" text-anchor="middle" fill="#1f1b17" font-family="Arial,sans-serif" font-size="12" font-weight="bold">SALITE</text>'
            f'<path d="M-8,90 L48,90 L48,118 L-8,118 Z" fill="#e0c79a" stroke="#2d2a23" stroke-width="2"/>'
            f'<path d="M-2,98 L44,98" stroke="#2d2a23" stroke-width="2" opacity="0.45"/>'
            f'<text x="20" y="107" text-anchor="middle" fill="#1f1b17" font-family="Arial,sans-serif" font-size="12" font-weight="bold">PANORAMA</text>'
            f'</g>'
            f'<g transform="translate(438,74)" fill="none" stroke="#1f1b17" stroke-width="3">'
            f'<circle cx="0" cy="82" r="22"/>'
            f'<circle cx="48" cy="82" r="22"/>'
            f'<path d="M0,82 L14,50 L35,50 L48,82"/>'
            f'<path d="M14,50 L26,30 L42,30"/>'
            f'<path d="M29,30 L32,18"/>'
            f'</g>'
            f'<g transform="translate(445,66)">'
            f'<circle cx="26" cy="78" r="2.5" fill="#f59a1a"/>'
            f'<circle cx="59" cy="72" r="2.5" fill="#f59a1a"/>'
            f'<circle cx="34" cy="40" r="2.5" fill="#f59a1a"/>'
            f'<circle cx="8" cy="48" r="2.5" fill="#f59a1a"/>'
            f'<path d="M26,78 C20,70 18,60 24,52 C28,46 35,42 44,42" stroke="#f59a1a" stroke-width="2" fill="none" opacity="0.9"/>'
            f'<path d="M59,72 C54,64 52,56 58,48 C63,42 70,39 78,40" stroke="#f59a1a" stroke-width="2" fill="none" opacity="0.9"/>'
            f'</g>'
            f'<g transform="translate(416,74)" opacity="0.98">'
            f'<path d="M0,98 C2,72 8,46 16,28 C24,10 34,0 48,0 C56,0 62,2 68,8 C58,20 50,36 42,58 C36,76 30,92 24,106" fill="#1e1c1c"/>'
            f'<path d="M18,26 C32,24 46,28 58,38 C62,42 68,50 72,58 C78,70 82,86 84,102 L68,102 C66,88 62,74 56,62 C50,50 42,42 32,38 C24,34 18,32 12,34 Z" fill="#1e1c1c"/>'
            f'<path d="M34,6 L50,0 L66,10 L62,28 L44,30 L34,18 Z" fill="#ff7c10"/>'
            f'<path d="M28,0 L50,0 L64,10 L58,18 L44,18 L34,10 Z" fill="#ff7c10" opacity="0.95"/>'
            f'<rect x="30" y="44" width="30" height="36" rx="8" fill="#ff7c10"/>'
            f'<path d="M18,60 C24,56 30,54 36,54 C42,54 48,56 54,60" stroke="#ff7c10" stroke-width="5" fill="none" stroke-linecap="round"/>'
            f'<path d="M30,76 C28,92 24,108 18,122" stroke="#1e1c1c" stroke-width="4" fill="none" stroke-linecap="round"/>'
            f'<path d="M56,78 C62,94 66,108 68,124" stroke="#1e1c1c" stroke-width="4" fill="none" stroke-linecap="round"/>'
            f'<path d="M44,80 C46,102 50,120 56,136" stroke="#1e1c1c" stroke-width="4" fill="none" stroke-linecap="round"/>'
            f'<path d="M16,120 C32,106 48,104 66,112" stroke="#1e1c1c" stroke-width="4" fill="none"/>'
            f'<path d="M20,138 C40,122 60,122 78,132" stroke="#1e1c1c" stroke-width="4" fill="none"/>'
            f'<path d="M0,132 C10,152 28,164 46,164 C60,164 74,156 84,142" stroke="#1e1c1c" stroke-width="4" fill="none" opacity="0.9"/>'
            f'<path d="M42,104 C48,108 52,114 56,122" stroke="#f59a1a" stroke-width="4" fill="none" stroke-linecap="round"/>'
            f'</g>'
            f'<rect x="26" y="22" width="248" height="86" rx="16" fill="#0f0f0e" opacity="0.88"/>'
            f'<text x="48" y="56" text-anchor="start" fill="#f8e7ba" font-family="Impact,Arial Black,sans-serif"'
            f' font-size="30" font-weight="bold" letter-spacing="0.2">TOSCANA</text>'
            f'<text x="48" y="92" text-anchor="start" fill="#ff7c10" font-family="Impact,Arial Black,sans-serif"'
            f' font-size="36" font-weight="bold" letter-spacing="0.3">GRAVEL</text>'
            f'<path d="M48,106 L274,106" stroke="#ff7c10" stroke-width="5" opacity="0.9"/>'
            f'<text x="52" y="124" text-anchor="start" fill="#ead8b8" font-family="Arial,sans-serif"'
            f' font-size="11" letter-spacing="1.4" opacity="0.92">DUST. CLIMBS. COFFEE. REPEAT.</text>'
            f'</svg>'
        )
    elif any(x in key for x in ["alps", "alpy", "mont"]):
        sky_top = "#6f93b8"
        sky_bottom = "#102136"
        hill_far = "#335777"
        hill_mid = "#244761"
        hill_near = "#162d45"
        field = "#dfeaf7"
        road = "#eef6ff"
        tree = "#8ec5ff"
        sun = "#d8efff"
        text_bg = "#0f1117"
    else:
        sky_top = "#54708d"
        sky_bottom = "#101a2a"
        hill_far = "#3e5f7b"
        hill_mid = "#294357"
        hill_near = "#18293b"
        field = "#dde7f4"
        road = "#edf3ff"
        tree = "#b7c8dd"
        sun = "#f0b25c"
        text_bg = "#0f1117"

    return (
        f'<svg width="640" height="208" viewBox="0 0 640 208" xmlns="http://www.w3.org/2000/svg"'
        f' style="display:block;border-radius:16px;margin:0 0 14px 0;max-width:100%;">'
        f'<defs>'
        f'<linearGradient id="ebg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{sky_top}"/>'
        f'<stop offset="100%" stop-color="{sky_bottom}"/>'
        f'</linearGradient>'
        f'<filter id="grain" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>'
        f'<feColorMatrix type="saturate" values="0"/>'
        f'<feComponentTransfer><feFuncA type="table" tableValues="0 0.06"/></feComponentTransfer>'
        f'</filter>'
        f'</defs>'
        f'<rect width="640" height="208" fill="url(#ebg)"/>'
        f'<rect width="640" height="208" filter="url(#grain)" opacity="0.15"/>'
        f'<circle cx="498" cy="60" r="22" fill="{sun}" opacity="0.8"/>'
        f'<circle cx="498" cy="60" r="36" fill="none" stroke="{sun}" stroke-width="2" opacity="0.08"/>'
        f'<path d="M0,154 C88,126 146,86 228,98 C298,108 338,150 412,134 C488,118 544,80 640,100 L640,208 L0,208 Z" fill="{hill_near}" opacity="0.96"/>'
        f'<path d="M0,136 C86,106 162,74 252,86 C326,96 378,140 460,124 C522,112 574,88 640,90 L640,208 L0,208 Z" fill="{hill_mid}" opacity="0.92"/>'
        f'<path d="M0,116 C96,84 176,60 264,72 C340,82 394,120 470,108 C548,96 588,76 640,74 L640,208 L0,208 Z" fill="{hill_far}" opacity="0.88"/>'
        f'<path d="M320,208 C336,170 358,136 380,104 C392,86 406,72 420,62" stroke="{road}" stroke-width="7" fill="none" opacity="0.92" stroke-linecap="round"/>'
        f'<path d="M320,208 C336,170 358,136 380,104 C392,86 406,72 420,62" stroke="{field}" stroke-width="1.8" fill="none" opacity="0.22" stroke-linecap="round"/>'
        f'<path d="M28,106 C94,96 130,84 190,90 C246,96 280,112 330,108" stroke="{label_bg}" stroke-width="1.2" fill="none" opacity="0.14" stroke-dasharray="2 8"/>'
        f'<path d="M46,126 C108,116 148,104 206,110 C258,116 298,130 348,126" stroke="{label_bg}" stroke-width="1.2" fill="none" opacity="0.10" stroke-dasharray="2 10"/>'
        f'<g transform="translate(454,116)" opacity="0.85">'
        f'<path d="M0,42 C-5,28 -4,16 2,0 C8,16 7,28 0,42 Z" fill="{tree}"/>'
        f'<path d="M12,42 C7,28 8,16 14,0 C20,16 19,28 12,42 Z" fill="{tree}"/>'
        f'<path d="M24,42 C19,28 20,16 26,0 C32,16 31,28 24,42 Z" fill="{tree}"/>'
        f'</g>'
        f'<g transform="translate(514,108)" opacity="0.65">'
        f'<path d="M0,50 C-4,34 -3,22 2,4 C7,22 6,34 0,50 Z" fill="{tree}"/>'
        f'<path d="M10,50 C6,34 7,22 12,4 C17,22 16,34 10,50 Z" fill="{tree}"/>'
        f'</g>'
        f'<g transform="translate(474,84)" opacity="0.5">'
        f'<circle cx="0" cy="0" r="6" fill="none" stroke="{label_bg}" stroke-width="1.6"/>'
        f'<circle cx="34" cy="0" r="6" fill="none" stroke="{label_bg}" stroke-width="1.6"/>'
        f'<path d="M0,0 L12,0 L18,-10 L24,-10 L34,0" stroke="{label_bg}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M18,-10 L14,-16 L8,-16" stroke="{label_bg}" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
        f'</g>'
        f'<rect x="28" y="24" width="282" height="86" rx="16" fill="{text_bg}" opacity="0.82"/>'
        f'<text x="48" y="54" text-anchor="start" fill="#2a231c" font-family="Georgia,Times New Roman,serif"'
        f' font-size="28" font-weight="bold" letter-spacing="0.1">{name}</text>'
        f'<text x="48" y="78" text-anchor="start" fill="#5a4c3d" font-family="Arial,sans-serif"'
        f' font-size="10" letter-spacing="3.4" opacity="0.9">MAGAZINE EDITION · BIKEPACKING GRAVEL STYLE</text>'
        f'<text x="48" y="97" text-anchor="start" fill="#6c5b49" font-family="Arial,sans-serif"'
        f' font-size="11" opacity="0.88">Warm gravel roads, long light, and a calm pace.</text>'
        f'<rect x="28" y="154" width="216" height="30" rx="15" fill="{label_bg}" opacity="0.98"/>'
        f'<text x="136" y="173" text-anchor="middle" fill="{label_txt}" font-family="Arial,sans-serif"'
        f' font-size="11" font-weight="bold" letter-spacing="2.2">TUSCANY TRAIL · 2026</text>'
        f'</svg>'
        )


def event_banner_markup(trip_name, banner_cid=None):
    name = html.escape(trip_name or "Wyjazd")
    key = name.lower()
    if any(x in key for x in ["tuscany", "toskania", "toskan"]):
        if banner_cid:
            return (
                f'<img src="cid:{html.escape(banner_cid)}" width="640" alt="{name} banner" '
                f'style="display:block;border-radius:16px;margin:0 0 14px 0;max-width:100%;height:auto;" />'
            )
        data_uri = _tuscany_banner_data_uri()
        if data_uri:
            return (
                f'<img src="{data_uri}" width="640" alt="{name} banner" '
                f'style="display:block;border-radius:16px;margin:0 0 14px 0;max-width:100%;height:auto;" />'
            )
    return event_banner_svg(trip_name)


def _extract_json_object(text):
    clean = (text or "").strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        return json.loads(clean[start:end + 1])
    raise ValueError("no JSON object in AI response")


def _fallback_narrative(d):
    s = d.get("sen", {})
    r = d.get("regeneracja", {})
    f_ = d.get("forma", {})
    b = d.get("bilans", {})
    p = d.get("pogoda", {})
    brak_snu = d.get("brak_danych_snu", False)
    hrv = r.get("hrv")
    hrv_norma = r.get("hrv_norma")
    sleep_h = s.get("czas_h")
    readiness = evaluate_readiness(
        hrv=hrv,
        hrv_norm=hrv_norma,
        body_battery=r.get("body_battery_rano"),
        sleep_hours=None if brak_snu else sleep_h,
        form=f_.get("swiezosc"),
    )
    verdict = readiness.verdict
    short = readiness.short
    sleep_txt = "Brak danych snu, więc nie ma podstaw do mocnej oceny regeneracji ze snu." if brak_snu else f"Sen wyniósł {sleep_h or '—'} h; potraktuj to jako główny limit dzisiejszej intensywności."
    hrv_txt = f"HRV dziś to {hrv or '—'} ms przy normie {hrv_norma or '—'} ms. To jest najważniejszy sygnał gotowości na dziś."
    return {
        "tldr": f"Dziś decyzję treningową oprzyj na HRV, śnie i pogodzie. {sleep_txt} {hrv_txt} Pogoda: maksymalnie {p.get('temp_max', '—')}, wiatr {p.get('wiatr_ms') or p.get('wiatr_max', '—')}.",
        "kom_sen": sleep_txt,
        "kom_reg": hrv_txt,
        "kom_frm": f"Xert TP: {f_.get('tp_teraz_w') or '—'} W, świeżość: {f_.get('swiezosc') or '—'}. To ustawiaj ponad ambicją na pojedynczy trening.",
        "kom_bil": f"Bilans wczoraj: {b.get('wczoraj_kcal', '—')} kcal, średnia 7 dni: {b.get('srednia_7d_kcal', '—')} kcal. Nie tnij paliwa, jeśli planujesz jazdę.",
        "verdict": verdict,
        "skrot": short,
        "kom_rek": f"Werdykt: {verdict}. Zrób {short}; trzymaj intensywność tak, żeby nie pogorszyć regeneracji. Jeśli tętno będzie nietypowo wysokie względem mocy, skróć jazdę. Priorytetem jest stabilny blok przygotowań, nie pojedynczy mocny dzień.",
        "kom_rad": "Najlepsza decyzja na dziś to taka, po której jutro nadal możesz trenować bez długu regeneracyjnego.",
    }


def _daily_narrative(d, ai_fn, system):
    ds = json.dumps(d, ensure_ascii=False)
    brak_snu = d.get("brak_danych_snu", False)
    hrv_fakt = (d.get("regeneracja", {}) or {}).get("hrv_fakt") or ""
    prompt = (
        f"{system}\n\nDane: {ds}\n\n"
        "Zwróć TYLKO poprawny JSON bez markdown. Klucze: "
        "tldr, kom_sen, kom_reg, kom_frm, kom_bil, verdict, skrot, kom_rek, kom_rad. "
        "Wymagania: tldr 3-4 zdania; kom_sen 2-3 zdania; kom_reg 2-3 zdania; "
        "kom_frm 2-3 zdania; kom_bil 2 zdania; verdict jedno z TAK, OGRANICZ, ODPUSC; "
        "skrot max 8 słów; kom_rek 5 zdań z jedną liczbą czasu w minutach i strefą HR lub mocy; "
        "kom_rad dokładnie 1 zdanie. Wszystko po polsku, bez nagłówków i bez markdown. "
        "Uwzględnij Tuscany Trail tylko jeśli występuje w danych. "
    )
    if brak_snu:
        prompt += "Brak danych snu: zaznacz to w kom_sen i nie udawaj, że znasz fazy snu. "
    if hrv_fakt:
        prompt += f"Krytyczny fakt HRV: {hrv_fakt}. Nie odwracaj kierunku. "
    try:
        out = _extract_json_object(ai_fn(prompt, max_t=1800))
    except Exception as exc:
        print(f"AI narrative fallback: {exc}")
        out = _fallback_narrative(d)
    fallback = _fallback_narrative(d)
    for key, value in fallback.items():
        if not out.get(key):
            out[key] = value
    if out.get("verdict") not in ("TAK", "OGRANICZ", "ODPUSC"):
        out["verdict"] = fallback["verdict"]
    return out


def render(d, ai_fn, banner_cid=None):
    today_str = d.get("dzisiaj", date.today().isoformat())
    today_dt  = date.fromisoformat(today_str)
    dni  = ["Poniedziałek","Wtorek","Środa","Czwartek","Piątek","Sobota","Niedziela"]
    mce  = ["","stycznia","lutego","marca","kwietnia","maja","czerwca",
            "lipca","sierpnia","września","października","listopada","grudnia"]
    dfmt = f"{dni[today_dt.weekday()]}, {today_dt.day} {mce[today_dt.month]} {today_dt.year}"

    p            = d.get("pogoda", {})
    s            = d.get("sen", {})
    r            = d.get("regeneracja", {})
    f_           = d.get("forma", {})
    b            = d.get("bilans", {})
    wy           = d.get("wyjazdy", [])
    coach        = d.get("coach", {})
    brak_snu     = d.get("brak_danych_snu", False)
    ds           = json.dumps(d, ensure_ascii=False)

    SYS = ("Jesteś Q — trenerem kolarskim. Piszesz WYŁĄCZNIE po polsku. "
           "ABSOLUTNY ZAKAZ używania innych języków, cyrylicy ani obcych słów. "
           "Zawsze mów do odbiorcy w drugiej osobie liczby pojedynczej ('ty', 'twoje', 'twój'). "
           "Bez markdown gwiazdek. Styl: konkretny trener, pełne zdania, zero ogólników.")

    narrative = _daily_narrative(d, ai_fn, SYS)
    tldr = narrative["tldr"]
    kom_sen = narrative["kom_sen"]
    kom_reg = narrative["kom_reg"]
    kom_frm = narrative["kom_frm"]
    kom_bil = narrative["kom_bil"]
    _verdict = narrative["verdict"]
    _skrot = narrative["skrot"]
    _vbg  = {"TAK": BG_OK,   "OGRANICZ": BG_WARN,   "ODPUSC": BG_BAD}
    _vtxt = {"TAK": OK,       "OGRANICZ": WARN,       "ODPUSC": BAD}
    _vlbl = {"TAK": "✅ TAK — normalny trening", "OGRANICZ": "⚠️ OGRANICZ", "ODPUSC": "🛑 ODPUŚĆ — dziś bez treningu"}
    _verdict_html = (
        f'<table width="100%" cellpadding="18" cellspacing="0" bgcolor="{_vbg.get(_verdict, BG_WARN)}"'
        f' style="border-radius:10px;border:1px solid {BORDER};margin-bottom:14px;">'
        f'<tr><td>'
        f'<div style="font-size:20px;font-weight:bold;color:{_vtxt.get(_verdict, WARN)};">'
        f'{_vlbl.get(_verdict, _verdict)}</div>'
        f'<div style="font-size:16px;color:{_vtxt.get(_verdict, WARN)};margin-top:6px;">{_skrot}</div>'
        f'</td></tr></table>'
    )

    def _strip_hdr(text, *hdrs):
        for h in hdrs:
            for sep in ("\n\n", "\n", ": ", " "):
                if text.startswith(h + sep):
                    text = text[len(h + sep):]
                    break
            if text.upper().startswith(h):
                text = text[len(h):].lstrip(": \n")
        return text.strip()

    kom_rek = _strip_hdr(narrative["kom_rek"], "REKOMENDACJA")
    kom_rad = _strip_hdr(narrative["kom_rad"], "RADA TRENERA", "RADA")

    # Coach blocks: deterministic decision support.
    c_decision = coach.get("decision", {}) or {}
    c_alerts = coach.get("risk_alerts", []) or []
    c_plan = coach.get("plan_adjustment", []) or []
    c_fuel = coach.get("fuel", {}) or {}
    c_event = coach.get("event")
    c_verdict = c_decision.get("verdict") or _verdict
    c_col = _vtxt.get(c_verdict, WARN)
    decision_html = (
        row3(
            card("Decyzja", c_decision.get("action", _skrot), color=c_col, bg=_vbg.get(c_verdict, BG_WARN)),
            card("Czas", c_decision.get("duration", "—"), color=c_col),
            card("Intensywność", c_decision.get("intensity", "—"), color=c_col),
        ) +
        (small_note("Powody: " + "; ".join(c_decision.get("why", []))) if c_decision.get("why") else "")
    )
    alerts_html = "".join(small_note(a, BAD if i == 0 else WARN) for i, a in enumerate(c_alerts))
    if not alerts_html:
        alerts_html = small_note("Brak dużej czerwonej flagi w dostępnych danych.", OK)
    plan_html = tbl(["Dzień", "Kalendarz", "Korekta"], [
        [(row.get("date", "—"), f"color:{TXT2};"), row.get("event", "—"), row.get("suggestion", "—")]
        for row in c_plan
    ]) if c_plan else small_note("Brak danych kalendarza na najbliższe dni.")
    fuel_html = (
        row3(
            card("Masa", c_fuel.get("weight", "—")),
            card("Węgle na jazdę", c_fuel.get("carbs", "—"), color=OK),
            card("Dzisiaj", c_fuel.get("daily", "—"), color=WARN),
        ) +
        (small_note(c_fuel["warning"], BAD) if c_fuel.get("warning") else "")
    )
    event_html = ""
    if c_event:
        event_html = (
            sep() +
            section_label(f"Event: {c_event.get('name', 'wyjazd')} — za {c_event.get('days_to', '?')} dni") +
            row3(
                card("Priorytet", c_event.get("focus", "—"), color=WARN),
                card("Lista", "sprawdź setup", color=OK),
                card("Tryb", "bez nadrabiania", color=TXT2),
            ) +
            "".join(small_note(item) for item in c_event.get("checklist", []))
        )

    # Pogoda
    deszcz  = p.get("deszcz_okno")
    wiatr_v = p.get("wiatr_ms") or p.get("wiatr_max","—")
    wiatr_k = p.get("kierunek_wiatru","")
    wiatr_s = f"{wiatr_v} {wiatr_k}".strip() if wiatr_k else wiatr_v
    zachod  = p.get("zachod_slonca","—")
    zachm   = int(p.get("zachmurzenie_proc",0))

    pog = (
        row3(
            card("Temperatura maks.", p.get("temp_max","—")),
            card("Wiatr", wiatr_s),
            card("Zachmurzenie", f"{zachm}%",
                 color=WARN if zachm > 70 else OK),
        ) + "<div style='height:10px'></div>" +
        row3(
            card("Zachód słońca", zachod),
            card("Okno suche", p.get("sucho_do","cały dzień"), color=OK, bg=BG_OK),
            card("Deszcz", deszcz or "brak",
                 color=BAD if deszcz else TXT3, bg=BG_BAD if deszcz else BG2),
        )
    )

    # Sen
    sh  = s.get("czas_h",0)
    sc  = OK if sh>=7 else (WARN if sh>=6 else BAD)
    gl  = s.get("gleboki_min")
    rem = s.get("rem_min")
    if brak_snu:
        sen = (f'<table width="100%" cellpadding="14" cellspacing="0" bgcolor="{BG_WARN}"'
               f' style="border-radius:10px;border:1px solid {BORDER};margin-bottom:10px;">'
               f'<tr><td>'
               f'<div style="font-size:15px;color:{WARN};font-weight:bold;">⚠️ Brak danych ze snu</div>'
               f'<div style="font-size:13px;color:{TXT2};margin-top:6px;">'
               f'Zegarek nie był założony lub dane nie zsynchronizowały się z Garminem.</div>'
               f'</td></tr></table>')
    else:
        sen = row3(
            card("Czas snu", f"{int(sh)}h {int((sh%1)*60)}min", color=sc),
            card("Score", f"{int(s.get('score',0))}/100 {s.get('ocena','') or ''}", color=WARN),
            card("Sen głęboki", f"{gl} min" if gl else "—",
                 sub=f"REM: {rem} min" if rem else None,
                 color=OK if gl and gl>90 else WARN),
        )

    # Regeneracja
    hrv     = r.get("hrv")
    hrv_n   = r.get("hrv_norma")
    hrv_c   = OK if hrv and hrv_n and hrv>=hrv_n else WARN
    bb_r    = r.get("body_battery_rano")
    bb_w    = r.get("body_battery_min")
    bb_s    = f"{bb_r}" if bb_r else "—"
    bb_color = (OK if bb_r and bb_r >= 75 else (WARN if bb_r and bb_r >= 50 else BAD)) if bb_r else TXT2
    reg = row3(
        card("HRV dziś", f"{int(hrv)} ms" if hrv else "—",
             sub=f"norma: {int(hrv_n)} ms" if hrv_n else None, color=hrv_c),
        card("Tętno spocz.", f"{r.get('tetno_spoczynkowe','—')} bpm", color=OK),
        card("Body Battery", bb_s, color=bb_color),
    )

    # Forma
    tp_n,tp_p = f_.get("tp_teraz_w"), f_.get("tp_7dni_temu_w")
    cl_n,cl_p = f_.get("obciazenie_dlugoterminowe"), f_.get("obciazenie_dlugoterminowe_7d")
    sw        = f_.get("swiezosc")
    tp_d,tp_c = delta(tp_n,tp_p)
    cl_d,cl_c = delta(cl_n,cl_p)
    sw_d,sw_c = delta(sw,0.2)
    frm = tbl(
        ["Wskaźnik","Teraz","7 dni temu","Zmiana"],
        [
            [("Moc progowa","font-weight:bold;"),
             (f"{tp_n} W" if tp_n else "—","font-weight:bold;"),
             (f"{tp_p} W" if tp_p else "—",f"color:{TXT2};"),
             (tp_d,f"color:{tp_c};")],
            [("Obciążenie długoterminowe","font-weight:bold;"),
             (str(cl_n) if cl_n else "—","font-weight:bold;"),
             (str(cl_p) if cl_p else "—",f"color:{TXT2};"),
             (cl_d,f"color:{cl_c};")],
            [("Świeżość","font-weight:bold;"),
             (f"+{sw}" if sw else "—",f"font-weight:bold;color:{OK};"),
             ("0.2",f"color:{TXT2};"),
             (sw_d,f"color:{sw_c};")],
        ]
    )

    # Wyjazd
    trip = ""
    if wy:
        t    = wy[0]
        dys  = t.get("distance_km", "?")
        elv  = int(t.get("elevation_m", 0))
        tname = t.get("name", "Wyjazd")
        trip = f"""
        {sep()}
        {section_label(f"{tname} — za {t.get('days_to','?')} dni")}
        {event_banner_markup(tname, banner_cid=banner_cid)}
        {row3(card("Start", "2.06 Florencja"), card("Dystans", f"{dys} km"),
               card("Przewyższenie", f"{elv:,} m".replace(",", ".")))}
        {comment(kom_frm)}
        """

    # Bilans
    yest  = b.get("wczoraj_kcal")
    avg   = b.get("srednia_7d_kcal")
    wd    = b.get("waga_dzis_kg")
    wd_date = b.get("waga_dzis_date")
    wd_fallback = bool(b.get("waga_dzis_fallback"))
    wt    = b.get("waga_tydzien_temu_kg")
    wt_date = b.get("waga_tydzien_temu_date")
    wa    = b.get("waga_anchor_kg")
    wdate = b.get("waga_anchor_date", "05.05")
    hist  = b.get("historia_7d", [])

    def bc(v): return OK if v and v > -100 else (WARN if v and v > -500 else BAD)
    def wd2(a, bb):
        if a is None or bb is None: return "—"
        d = round(a - bb, 1)
        return f"{'−' if d < 0 else '+'}{abs(d)} kg"

    def dmy(s):
        if not s:
            return None
        parts = str(s).split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}"
        return str(s)

    weight_label = "Ostatnia waga" if wd_fallback else "Waga dziś"
    weight_row_label = f"Ostatnie ważenie ({dmy(wd_date)})" if wd_fallback and wd_date else "Dziś"
    week_label = f"Tydzień temu ({dmy(wt_date)})" if wt_date else "Tydzień temu"
    weight_sub = f"z {dmy(wd_date)}" if wd_fallback and wd_date else None
    if wa:
        anchor_delta = f"vs {wdate}: {wd2(wd,wa)}"
        weight_sub = f"{weight_sub} | {anchor_delta}" if weight_sub else anchor_delta

    bil = (
        row3(
            card("Wczoraj", f"{'+'if yest and yest>0 else''}{yest} kcal" if yest is not None else "—",
                 color=bc(yest), bg=BG_OK if yest and yest > -100 else BG_WARN),
            card("Średnia 7 dni", f"{'+'if avg and avg>0 else''}{avg} kcal" if avg is not None else "—",
                 color=bc(avg), bg=BG_WARN if avg and avg < -100 else BG2),
            card(weight_label, f"{wd} kg" if wd else "—",
                 sub=weight_sub, color=OK),
        ) +
        "<div style='height:12px'></div>" +
        calorie_chart(hist) +
        "<div style='height:12px'></div>" +
        tbl(["Data", "Waga", "Zmiana"], [
            [(weight_row_label, "font-weight:bold;"),
             (f"{wd} kg" if wd else "—", "font-weight:bold;"), ("—",)],
            [(week_label, f"color:{TXT2};"),
             (f"{wt} kg" if wt else "—",), (wd2(wd, wt), f"color:{OK};")],
            [(f"Punkt startowy ({wdate})", f"color:{TXT2};"),
             (f"{wa} kg" if wa else "—",), (wd2(wd, wa), f"color:{OK};")],
        ])
    )

    rek = f'<div style="font-size:19px;color:{TXT};line-height:1.85;text-align:justify;">{kom_rek}</div>'

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<style type="text/css">
  body, html {{ background-color:{BG} !important; margin:0; padding:0; }}
</style>
</head>
<body bgcolor="{BG}" style="background-color:{BG} !important; margin:0; padding:0;">
<div style="background-color:{BG};margin:0;padding:0;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background-color:{BG} !important;">
<tr><td bgcolor="{BG}" style="background-color:{BG} !important;">
<table width="640" cellpadding="28" cellspacing="0" bgcolor="{BG}"
       align="center" style="font-family:Arial,sans-serif;color:{TXT};font-size:17px;line-height:1.65;background-color:{BG};">
<tr><td bgcolor="{BG}" style="background-color:{BG} !important;">

  {header_svg()}

  <div style="border-bottom:2px solid {BORDER};padding-bottom:16px;margin-bottom:22px;">
    <div style="font-size:12px;color:{TXT3};text-transform:uppercase;
      letter-spacing:1px;margin-bottom:6px;">{dfmt}</div>
    <div style="font-size:22px;font-weight:bold;color:{TXT};margin-bottom:14px;">Raport Q</div>
    <table width="100%" cellpadding="16" cellspacing="0" bgcolor="{BG_WARN}"
           style="border-radius:10px;border:1px solid {BORDER};">
      <tr><td style="font-size:19px;color:{WARN};line-height:1.75;">{tldr}</td></tr>
    </table>
  </div>

  {section_label("Decyzja treningowa")}
  {decision_html}

  {section_label("Pogoda")}
  {pog}
  {weather_hours_chart(p.get("godzinowa", []))}
  {comment(f"Startuj przed {p.get('sucho_do','14:00').replace('sucho do ','')} — masz okno na spokojny trening. Zabierz wiatrówkę." if deszcz else "Dziś bez deszczu — pełna swoboda planowania.")}

  {sep()}
  {section_label("Sen")}
  {sen}
  {comment(kom_sen)}

  {sep()}
  {section_label("Regeneracja")}
  {reg}
  <div style="height:10px;"></div>
  {hrv_chart(r.get("hrv_trend_7d", []))}
  {comment(kom_reg)}

  {sep()}
  {section_label("Forma")}
  {frm}
  {trip if not wy else ""}
  {trip if wy else ""}

  {sep()}
  {section_label("Bilans kaloryczny i waga")}
  {bil}
  {comment(kom_bil)}

  {sep()}
  {section_label("Alerty ryzyka")}
  {alerts_html}

  {sep()}
  {section_label("Korekta planu — 3 dni")}
  {plan_html}

  {sep()}
  {section_label("Paliwo i masa")}
  {fuel_html}

  {event_html}

  {sep()}
  {section_label("Rekomendacja na dziś")}
  {_verdict_html}
  {rek}

  {sep()}
  <table width="100%" cellpadding="16" cellspacing="0" bgcolor="{BG2}"
         style="border-radius:10px;border:1px solid {BORDER};">
    <tr><td>
      <div style="font-size:11px;font-weight:bold;color:{TXT3};text-transform:uppercase;
        letter-spacing:1px;margin-bottom:8px;">Rada trenera</div>
      <div style="font-size:19px;color:{TXT};line-height:1.8;text-align:justify;">{kom_rad}</div>
    </td></tr>
  </table>

  <div style="margin-top:22px;font-size:12px;color:{TXT3};text-align:center;">
    Q · {dfmt}
  </div>

</td></tr>
</table>
</td></tr>
</table>
</div>
</body>
</html>
"""
