"""Silnik presetow zywieniowych — model SPOZYCIA BEZWZGLEDNEGO.

3 poziomy = typowe spozycie (kcal), NIEZALEZNE od spalenia danego dnia:
  - malo jadlem / normalnie / popuscilem
Kalorie = stale kotwice percepcji uzytkownika (ANCHORS_KCAL).
Makra   = mediana z realnych, czystych dni logowanych o spozyciu w paśmie
          wokol danej kotwicy (zeby wegle do glikogenu byly prawdziwe;
          same sie aktualizuja z nowymi logami).
Bilans do wagi liczony jest OSOBNO (spozycie - faktyczny wydatek dnia) —
tego modul NIE robi.
"""
import statistics as _st

# Kotwice percepcji (kcal). Edytowalne — docelowo z ustawien uzytkownika.
ANCHORS_KCAL = {"malo": 2200, "normalnie": 2700, "popuscilem": 3100}
# Etykiety do UI
LABELS = {"malo": "mało jadłem", "normalnie": "normalnie", "popuscilem": "popuściłem"}
# Pasma (min,max) kcal do liczenia makr wokol kazdej kotwicy
BANDS = {"malo": (1900, 2400), "normalnie": (2450, 2950), "popuscilem": (2950, 3400)}
SAMPLE_TARGET = 30
MIN_KCAL = 1200
# Fallback: gdy pasmo puste, rozklad makr wg tego udzialu energii (C/P/F)
FALLBACK_SPLIT = {"carb": 0.50, "prot": 0.20, "fat": 0.30}


def _macros_from_split(kcal):
    return {
        "carbs_g": round(kcal * FALLBACK_SPLIT["carb"] / 4),
        "protein_g": round(kcal * FALLBACK_SPLIT["prot"] / 4),
        "fat_g": round(kcal * FALLBACK_SPLIT["fat"] / 9),
    }


def compute_presets(conn):
    """conn: psycopg z row_factory=dict_row. Zwraca 3 poziomy (kcal + makra)."""
    rows = conn.execute(
        "SELECT l.date, SUM(i.kcal) kcal, SUM(i.carbs_g) carbs, "
        "SUM(i.protein_g) prot, SUM(i.fat_g) fat, "
        "bool_or(l.quality_status='estimated' OR l.source ILIKE '%recovery%' "
        "OR l.source ILIKE '%preset%') tainted "
        "FROM qbot_v2.intake_logs l "
        "JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
        "GROUP BY l.date ORDER BY l.date DESC"
    ).fetchall()

    samples = []
    for r in rows:
        kcal = float(r["kcal"] or 0)
        if r["tainted"] or kcal < MIN_KCAL:
            continue
        samples.append({
            "kcal": kcal,
            "carbs": float(r["carbs"] or 0),
            "prot": float(r["prot"] or 0),
            "fat": float(r["fat"] or 0),
        })
        if len(samples) >= SAMPLE_TARGET:
            break

    def _med(vals):
        return round(_st.median(vals)) if vals else 0

    levels = {}
    for key, anchor in ANCHORS_KCAL.items():
        lo, hi = BANDS[key]
        g = [s for s in samples if lo <= s["kcal"] <= hi]
        if g:
            macros = {"carbs_g": _med([s["carbs"] for s in g]),
                      "protein_g": _med([s["prot"] for s in g]),
                      "fat_g": _med([s["fat"] for s in g])}
        else:
            macros = _macros_from_split(anchor)
        levels[key] = {"label": LABELS[key], "kcal": anchor,
                       "n_days": len(g), "low_confidence": len(g) < 5, **macros}
    return {"model": "absolute_intake", "generated_from_days": len(samples), "levels": levels}
