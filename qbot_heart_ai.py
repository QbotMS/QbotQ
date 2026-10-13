"""Serce - AI (2026-10-13): komentarz kontekstowy do EKG + raport dla lekarza po serii pomiarow (PDF).

Zasada jak w Trendach: QBot LICZY fakty (EKG, cisnienie, sen, HRV, tetno spoczynkowe, trening), AI tylko je opisuje.
  * komentarz EKG: tylko gdy cos odstaje (regula: status warn/bad albo cisnienie >= 130/80 w tej samej sesji);
    2-3 zdania o kontekscie (sen, trening, stres), bez powtarzania interpretacji regul i bez diagnozy.
  * raport po serii: strona podsumowania (AI + tabele policzone przez QBota + puste pola: leki, objawy) i strony EKG z serii.
Wyniki AI w qbot_v2.heart_ai (klucz z hashem faktow -> te same dane = ten sam tekst, bez ponownego wywolania).
Bez nowych wiadomosci na Telegramie. Dokumentacja: docs/SERCE.md. Testy: tests/test_heart_ai.py.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

V_ECG, V_REP = 1, 1

PROMPT_ECG = (
    "Jesteś lekarzem sportowym. Dostajesz policzone przez system dane jednego 30-sekundowego EKG z zegarka (jedno odprowadzenie) "
    "oraz kontekst: noc przed (sen, HRV nocne, tętno spoczynkowe, stres – z normą osobistą z 28 dni), trening z ostatnich 2 dni "
    "i ciśnienie z tej samej sesji. Ocena reguł ('interpretacja_regul') jest pokazana obok – NIE powtarzaj jej. "
    "Twoje zadanie: w 2-3 krótkich zdaniach (maks. 60 słów) powiedz, co z kontekstu może tłumaczyć to, co odstaje, "
    "albo wprost, że kontekst tego nie tłumaczy. Zasady: tylko liczby z danych, nie licz nowych; tryb przypuszczający; "
    "bez diagnozy, bez leków; oceny (prawidłowe / wysokie prawidłowe / podwyższone) przepisuj z interpretacja_regul, nie oceniaj sam; jednostki z nazw pól (tętno w ud./min, HRV w ms); jeśli coś wymaga lekarza, powiedz to jednym zdaniem. Pisz po polsku, zwyczajnym językiem. "
    "Zwróć WYŁĄCZNIE JSON: {\"komentarz\": \"...\", \"czynniki\": [\"sen\"|\"trening\"|\"stres\"|\"pora_dnia\"|\"cisnienie\"|\"brak\"]}"
)

PROMPT_REP = (
    "Przygotowujesz stronę dla lekarza (internisty/kardiologa) z domowych pomiarów pacjenta: 7-dniowa seria ciśnienia "
    "(rano i wieczorem, po 2 pomiary), nagrania EKG z zegarka (jedno odprowadzenie, 30 s, analiza uderzeń systemu), tętno spoczynkowe "
    "i HRV z zegarka na tle normy osobistej z roku, objętość treningu (pacjent jeździ amatorsko na rowerze). Wszystko jest już policzone – "
    "nie licz nowych liczb i nie wymyślaj danych. Oceny (w normie / podwyższone) przepisuj z pola ocena_qbot, nie oceniaj sam; jednostki z nazw pól. Zasady: rzeczowo, bez diagnozy i bez zaleceń leczenia; podawaj kluczowe liczby; "
    "zaznacz ograniczenia (zegarek, jedno odprowadzenie, niepełna seria). 'podsumowanie' = 4-6 zdań (maks. 110 słów); "
    "'pytania' = 2-4 krótkie pytania, które pacjent może zadać lekarzowi; 'uwagi_pomiarow' = maks. 1 zdanie o jakości/kompletności serii. "
    "Pisz po polsku. Zwróć WYŁĄCZNIE JSON: {\"podsumowanie\": \"...\", \"pytania\": [\"...\"], \"uwagi_pomiarow\": \"...\"}"
)


def _conn():
    from fitmodel.api import _db_connect
    return _db_connect()


def _hash(o) -> str:
    return hashlib.sha1(json.dumps(o, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _cache_get(key: str):
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("SELECT value FROM qbot_v2.heart_ai WHERE key=%s", (key,))
        r = cur.fetchone()
        return r[0] if r else None
    finally:
        c.close()


def _cache_put(key: str, value: dict) -> None:
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("INSERT INTO qbot_v2.heart_ai (key, value) VALUES (%s, %s::jsonb) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, created_at=now()",
                    (key, json.dumps(value, ensure_ascii=False)))
        c.commit()
    finally:
        c.close()


def _words(t, n):
    w = str(t or "").split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def _ai(prompt: str, facts: dict) -> dict:
    import qbot_food_log as F
    return F._ai_json(prompt, [{"type": "text", "text": json.dumps(facts, ensure_ascii=False, default=str)}])


# ---------------- kontekst (fakty liczone przez QBota) ----------------

def _wellness_ctx(cur, day: date) -> dict:
    cur.execute("""SELECT date, max(sleep_duration_min), max(sleep_score), max(hrv_ms),
                          coalesce(max(resting_hr_bpm) FILTER (WHERE source='garmin'), max(resting_hr_bpm)), max(stress_avg), max(body_battery_start)
                   FROM qbot_v2.qbot_wellness_daily WHERE date BETWEEN %s AND %s GROUP BY date ORDER BY date""",
                (day - timedelta(days=28), day))
    rows = cur.fetchall()
    names = ["sen_min", "sen_score_pkt", "hrv_noc_ms", "tetno_spocz_ud_min", "stres_sr_pkt", "body_battery_rano_pkt"]
    today = next((r for r in rows if r[0] == day), None)
    out = {}
    for k, nm in enumerate(names, 1):
        hist = [float(r[k]) for r in rows if r[0] < day and r[k] is not None]
        v = float(today[k]) if today and today[k] is not None else None
        norm = round(sum(hist) / len(hist), 1) if len(hist) >= 7 else None
        out[nm] = {"wartosc": v, "norma_28d": norm, "roznica": round(v - norm, 1) if v is not None and norm is not None else None}
    return out


def _training_ctx(cur, until: datetime) -> list[dict]:
    cur.execute("""SELECT date, sport_type, round(duration_s/60.0) AS min, tss, started_at FROM qbot_v2.training_sessions
                   WHERE date BETWEEN %s AND %s ORDER BY date""", (until.date() - timedelta(days=2), until.date()))
    out = []
    for d, sp, mn, tss, st in cur.fetchall():
        if st is not None and (st.astimezone().replace(tzinfo=None) if st.tzinfo else st) > until:
            continue
        out.append({"dzien": d.isoformat(), "sport": sp, "min": int(mn or 0), "tss": round(float(tss)) if tss is not None else None,
                    "dni_przed": (until.date() - d).days})
    return out


def ecg_facts(d: dict) -> dict:
    an = d.get("analysis") or {}
    when = d.get("started_local")
    c = _conn()
    try:
        cur = c.cursor()
        well = _wellness_ctx(cur, when.date()) if when else {}
        tr = _training_ctx(cur, when) if when else []
    finally:
        c.close()
    import qbot_heart as H
    ctx = H._ecg_ctx(d)
    return {
        "nagranie": {"kiedy": when.strftime("%d.%m.%Y %H:%M") if when else None, "pora": ("rano" if when and when.hour < 12 else "wieczor"),
                     "wynik_garmin": d.get("label"), "tetno_sr": an.get("hr_mean"), "tetno_min": an.get("hr_min"), "tetno_max": an.get("hr_max"),
                     "hrv_rmssd_qbot": an.get("rmssd"), "hrv_rmssd_garmin": d.get("rmssd_hrv"),
                     "nieregularne": [i["label"] for i in an.get("irregular") or [] if i.get("kind") != "ksztalt"]},
        "interpretacja_regul": [p["text"] for p in d.get("interpretation") or []],
        "uwaga": "oceny (prawidlowe / wysokie prawidlowe / podwyzszone) sa w interpretacja_regul - przepisz je, nie oceniaj sam",
        "inne_nagrania_hrv": [{"kiedy": o["local"].strftime("%d.%m %H:%M"), "rmssd": o["rmssd"]} for o in ctx["others"]],
        "cisnienie_sesja": [{"godz": b["local"].strftime("%H:%M"), "cisnienie": f"{b['sys']}/{b['dia']}"} for b in ctx["bp"]],
        "noc_przed": well,
        "trening_2_dni": tr,
    }


def ecg_needs_ai(d: dict) -> bool:
    for p in d.get("interpretation") or []:
        if p["status"] in ("warn", "bad"):
            return True
        if p["text"].startswith("Ciśnienie") and p["status"] != "good":
            return True
    return False


def ecg_comment(d: dict, compute: bool = True) -> dict | None:
    """Komentarz AI do nagrania (z pamieci; compute=True -> policz, jesli brak)."""
    if not ecg_needs_ai(d):
        return None
    facts = ecg_facts(d)
    key = f"ecg:{d['detail_id']}:v{V_ECG}:{_hash(facts)}"
    got = _cache_get(key)
    if got or not compute:
        return got
    j = _ai(PROMPT_ECG, facts)
    val = {"komentarz": _words(j.get("komentarz"), 70), "czynniki": [str(x) for x in (j.get("czynniki") or [])][:4],
           "at": datetime.now().strftime("%d.%m.%Y %H:%M")}
    _cache_put(key, val)
    return val


# ---------------- raport po serii ----------------

def series_facts(today: date | None = None) -> dict:
    import qbot_heart as H
    data = H.build_heart_data(days=60, today=today)
    bp = data["bp"]["summary"]
    rows = data["bp"]["all"]
    per_day: dict[str, dict] = {}
    if bp:
        for m in rows:
            d0 = m["local"][:10]
            if bp["from"] <= d0 <= bp["to"]:
                slot = "rano" if int(m["local"][11:13]) < 12 else "wieczor"
                per_day.setdefault(d0, {"rano": [], "wieczor": []})[slot].append((m["sys"], m["dia"], m["pulse"]))
    table = []
    for d0 in sorted(per_day):
        row = {"dzien": d0}
        for slot in ("rano", "wieczor"):
            xs = per_day[d0][slot]
            row[slot] = (f"{round(sum(x[0] for x in xs) / len(xs))}/{round(sum(x[1] for x in xs) / len(xs))}" + (f" ({len(xs)})" if len(xs) != 2 else "")) if xs else "—"
        table.append(row)
    ecg_in = [e for e in data["ecg"]["list"] if bp and e["local"] and e["local"][:10] >= bp["from"]] if bp else data["ecg"]["list"][-3:]
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("""SELECT date, max(hrv_ms), max(weight_kg) FROM qbot_v2.qbot_wellness_daily WHERE date >= %s GROUP BY date ORDER BY date""",
                    ((today or date.today()) - timedelta(days=365),))
        wr = cur.fetchall()
        cur.execute("""SELECT date_trunc('week', date)::date, round(sum(duration_s)/3600.0, 1) FROM qbot_v2.training_sessions
                       WHERE date >= %s GROUP BY 1 ORDER BY 1""", ((today or date.today()) - timedelta(days=28),))
        weeks = [{"tydzien_od": w.isoformat(), "h": float(h)} for w, h in cur.fetchall()]
    finally:
        c.close()
    t0 = today or date.today()
    h28 = [float(v) for d0, v, _ in wr if v is not None and d0 > t0 - timedelta(days=28)]
    hn = sorted(float(v) for d0, v, _ in wr if v is not None and d0 <= t0 - timedelta(days=28))
    wts = [(d0, float(w)) for d0, _, w in wr if w is not None and d0 > t0 - timedelta(days=28)]
    old = [m for m in rows if bp and m["local"][:10] < bp["from"]]
    return {
        "dzis": t0.isoformat(),
        "seria_cisnienia": bp,
        "cisnienie_dzien_po_dniu": table,
        "cisnienie_wczesniej": [{"kiedy": m["local"][:16], "cisnienie": f"{m['sys']}/{m['dia']}"} for m in old[-6:]],
        "ekg_w_serii": [{"kiedy": e["local"], "wynik": e["label"], "tetno": e["hr"], "an": e.get("an")} for e in ecg_in],
        "tetno_spoczynkowe_ud_min": {"srednia_28_dni": data["rhr"].get("recent"), "norma_roku": data["rhr"].get("norm"),
                                     "roznica": data["rhr"].get("delta"), "srednia_7_dni": data["rhr"].get("last7")},
        "tetno_przy_mocy_140_180W_ud_min": {"srednia_28_dni": data["hrp"].get("recent"), "norma_roku": data["hrp"].get("norm"),
                                            "roznica": data["hrp"].get("delta"), "jazd": data["hrp"].get("rides")},
        "ocena_qbot": [p["text"] for p in data["points"]],
        "hrv_noc": {"sr_28d": round(sum(h28) / len(h28), 1) if h28 else None, "mediana_roku": hn[len(hn) // 2] if hn else None},
        "waga": {"start_28d": wts[0][1] if wts else None, "koniec": wts[-1][1] if wts else None},
        "trening_h_tydzien": weeks,
    }


def report_ai(facts: dict, compute: bool = True) -> dict | None:
    key = f"report:v{V_REP}:{_hash(facts)}"
    got = _cache_get(key)
    if got or not compute:
        return got
    j = _ai(PROMPT_REP, facts)
    val = {"podsumowanie": _words(j.get("podsumowanie"), 130), "pytania": [_words(q, 25) for q in (j.get("pytania") or [])][:4],
           "uwagi_pomiarow": _words(j.get("uwagi_pomiarow"), 30), "at": datetime.now().strftime("%d.%m.%Y %H:%M")}
    _cache_put(key, val)
    return val


def _d(iso: str | None) -> str:
    if not iso:
        return "—"
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"


def report_pdf(facts: dict, ai: dict | None) -> bytes:
    """Strona 1: podsumowanie dla lekarza; dalej strony EKG z serii (qbot_ecg.page_image)."""
    from PIL import Image, ImageDraw
    import qbot_ecg as Q
    import qbot_heart as H
    dpi, mm = 150, 150 / 25.4
    W, Hh = int(297 * mm), int(210 * mm)
    img = Image.new("RGB", (W, Hh), "white")
    dr = ImageDraw.Draw(img)
    L, R = int(16 * mm), W - int(16 * mm)
    y = int(12 * mm)
    f_h, f_b, f_t, f_s = Q._font(30, True), Q._font(19, True), Q._font(18), Q._font(15)

    def para(txt, font=f_t, col="black", width=None, gap=4):
        nonlocal y
        for ln in Q.wrap(dr, txt, font, (width or (R - L))):
            dr.text((L, y), ln, fill=col, font=font)
            y += font.size + gap

    bp = facts.get("seria_cisnienia")
    span = f"{_d(bp['from'])}–{_d(bp['to'])}" if bp else "brak serii"
    dr.text((L, y), "Domowe pomiary: ciśnienie, EKG z zegarka, tętno", fill="black", font=f_h); y += 44
    dr.text((L, y), f"Seria: {span} · wydruk {_d(facts['dzis'])} · Pacjent: ______________________   Leki: ______________________",
            fill="black", font=f_t); y += 34
    if ai:
        dr.text((L, y), "Podsumowanie", fill="black", font=f_b); y += 28
        para(ai.get("podsumowanie") or "")
        if ai.get("uwagi_pomiarow"):
            para(ai["uwagi_pomiarow"], f_s, (90, 90, 90))
        y += 6
    else:
        para("Podsumowanie AI niedostępne – poniżej dane policzone przez system.", f_s, (90, 90, 90))

    # tabela cisnienia (lewa kolumna) i liczby (prawa)
    colw = (R - L) // 2 - int(6 * mm)
    y0 = y
    dr.text((L, y), "Ciśnienie (średnia z 2 pomiarów)", fill="black", font=f_b); y += 28
    dr.text((L, y), "Dzień", font=f_b, fill="black"); dr.text((L + 160, y), "Rano", font=f_b, fill="black"); dr.text((L + 330, y), "Wieczór", font=f_b, fill="black"); y += 26
    for r in facts.get("cisnienie_dzien_po_dniu") or []:
        dr.text((L, y), _d(r["dzien"]), font=f_t, fill="black")
        for x0, k in ((160, "rano"), (330, "wieczor")):
            v = r[k]
            hi = False
            try:
                s_, d_ = (int(t) for t in v.split(" ")[0].split("/"))
                hi = s_ >= 135 or d_ >= 85
            except Exception:
                pass
            dr.text((L + x0, y), v, font=f_t, fill=(180, 0, 0) if hi else "black")
        y += 24
    if bp:
        y += 4
        para(f"Średnia serii (bez 1. dnia przy ≥3 dniach): {bp['sys']}/{bp['dia']} mmHg, tętno {bp.get('pulse') or '—'} · "
             f"rano {bp['morning']['sys']}/{bp['morning']['dia']} ({bp['morning']['n']}) · wieczorem {bp['evening']['sys']}/{bp['evening']['dia']} ({bp['evening']['n']}) · "
             f"{bp['label']}{'' if bp['protocol_ok'] else ' · seria niepełna'}", f_s, width=colw)
    old = facts.get("cisnienie_wczesniej") or []
    if old:
        para("Wcześniej: " + "; ".join(f"{_d(o['kiedy'][:10])} {o['cisnienie']}" for o in old), f_s, (90, 90, 90), width=colw)
    yl = y
    y = y0
    X = L + colw + int(12 * mm)

    def rline(txt, font=f_t, col="black"):
        nonlocal y
        for ln in Q.wrap(dr, txt, font, R - X):
            dr.text((X, y), ln, fill=col, font=font); y += font.size + 4

    rline("EKG z zegarka (Lead I, 30 s)", f_b); y += 4
    for e in facts.get("ekg_w_serii") or []:
        an = e.get("an") or {}
        rline(f"{_d(e['kiedy'][:10])} {e['kiedy'][11:16]} · {e['wynik']} · tętno {e['tetno']} · HRV {an.get('rmssd', '—')} ms · "
              f"nieregularne {an.get('n_irregular', '—')}", f_s)
    if not facts.get("ekg_w_serii"):
        rline("brak nagrań w serii", f_s)
    y += 8
    rs, hp, hv = facts["tetno_spoczynkowe_ud_min"], facts["tetno_przy_mocy_140_180W_ud_min"], facts["hrv_noc"]
    rline("Zegarek: tętno i HRV", f_b); y += 4
    rline(f"Tętno spoczynkowe: średnio {rs.get('srednia_28_dni')} z 28 dni (norma z roku {rs.get('norma_roku')})", f_s)
    rline(f"Tętno przy mocy 140–180 W na rowerze: {hp.get('srednia_28_dni')} (norma {hp.get('norma_roku')}, {hp.get('jazd')} jazd)", f_s)
    rline(f"HRV nocne: średnio {hv.get('sr_28d')} ms z 28 dni (mediana roku {hv.get('mediana_roku')})", f_s)
    wg = facts.get("waga") or {}
    if wg.get("koniec"):
        rline(f"Waga: {wg.get('start_28d')} → {wg.get('koniec')} kg (28 dni)", f_s)
    wk = facts.get("trening_h_tydzien") or []
    if wk:
        rline("Trening (h/tydz.): " + ", ".join(f"{_d(w['tydzien_od'])[:5]}: {w['h']:.1f}".replace(".", ",") for w in wk), f_s)
    y = max(y, yl) + 10
    if ai and ai.get("pytania"):
        dr.text((L, y), "Pytania do lekarza", fill="black", font=f_b); y += 28
        for q in ai["pytania"]:
            para("• " + q)
    y += 6
    para("Objawy (kołatanie, zawroty, ból w klatce, duszność): _____________________________________________", f_t)
    para("Źródła: ciśnieniomierz Withings, zegarek Garmin (EKG: aplikacja Garmin; uderzenia, HRV i nieregularności – analiza QBot, orientacyjna). "
         "Podsumowanie napisane przez AI na podstawie policzonych danych; nie jest diagnozą.", f_s, (90, 90, 90))

    pages = []
    ids = []
    c = _conn()
    try:
        cur = c.cursor()
        if bp:
            cur.execute("SELECT detail_id FROM qbot_v2.ecg_recording WHERE samples IS NOT NULL AND started_local >= %s ORDER BY started_local",
                        (bp["from"],))
        else:
            cur.execute("SELECT detail_id FROM qbot_v2.ecg_recording WHERE samples IS NOT NULL ORDER BY started_local DESC LIMIT 3")
        ids = [r[0] for r in cur.fetchall()]
    finally:
        c.close()
    for did in ids[-14:]:
        rec = H.ecg_record(did)
        if rec and rec.get("samples"):
            pages.append(Q.page_image(rec))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=dpi, save_all=True, append_images=pages)
    return buf.getvalue()
