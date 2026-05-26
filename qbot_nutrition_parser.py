#!/usr/bin/env python3
"""QBot Nutrition Intake Parser — natural language → structured food/hydration/fueling entries."""
from __future__ import annotations

import re
from typing import Any


# ── Regex patterns ────────────────────────────────────────────────────────
# Quantity + unit + food name: "200 g skyru", "40 g płatków", "500 ml izo"
_QTY_UNIT_FOOD = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(g|ml|l|kg|szt|łyż|łyżka|łyżek|łyżki|szkl|szklanka|szklanki|szklanek|plaster|plastrów|plastry|porcj|porcja|porcje)\s+(.+?)(?:[,.;]|$|\s+z\s+|\s+i\s+|\s+oraz\s+|\s+a\s+)",
    re.IGNORECASE,
)

# Standalone food with count: "2 bułki", "3 jaj", "banana", "jabłko"
_STANDALONE_FOOD = re.compile(
    r"(\d+)\s+(szt\.?)?\s*([a-ząćęłńóśźż\s]+?)(?:[,.;]|$|\s+z\s+|\s+i\s+|\s+oraz\s+|\s+a\s+)",
    re.IGNORECASE,
)

# Hydration: "wypiłem 500 ml", "500 ml izo", "woda 300 ml"
_HYDRATION = re.compile(
    r"(?:wypi[łl]\w*\s+)?(\d+(?:[.,]\d+)?)\s*(ml|l)\s*(.+?)?(?:[,.;]|$|\s+z\s+|\s+i\s+|\s+oraz\s+)",
    re.IGNORECASE,
)

# Fueling/gel: "żel 30 g carb", "żel carbs 22"
_FUELING = re.compile(
    r"(?:żel|gel|batony?|batona?)\s+.*?(\d+(?:[.,]\d+)?)\s*(?:g\s*)?(?:carb|węgli|węglowodan)",
    re.IGNORECASE,
)

# Carb-only fueling: "30 g carb", "40 g węgli"
_CARB_ONLY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*g\s*(?:carb|węgli|węglowodan)",
    re.IGNORECASE,
)

# Known units → grams conversion (approximate)
_UNIT_TO_GRAMS: dict[str, float] = {
    "g": 1.0,
    "ml": 1.0,
    "l": 1000.0,
    "kg": 1000.0,
    "szt": 1.0,
    "łyżka": 15.0,
    "łyżki": 15.0,
    "łyżek": 15.0,
    "łyż": 15.0,
    "szklanka": 250.0,
    "szklanki": 250.0,
    "szklanek": 250.0,
    "szkl": 250.0,
    "plaster": 30.0,
    "plastry": 30.0,
    "plastrów": 30.0,
    "porcja": 1.0,
    "porcje": 1.0,
    "porcj": 1.0,
}

# Food name normalization — common aliases → DB name
_FOOD_ALIASES: dict[str, str] = {
    "skyr": "skyr naturalny",
    "skyr naturalny": "skyr naturalny",
    "banan": "banan",
    "jabłko": "jabłko",
    "jajko": "jajko",
    "jaja": "jajko",
    "jaj": "jajko",
    "jajecznica": "jajecznica",
    "płatki": "płatki owsiane",
    "płatków": "płatki owsiane",
    "płatki owsiane": "płatki owsiane",
    "owsianka": "płatki owsiane",
    "bułka": "bułka pszenna",
    "bułki": "bułka pszenna",
    "chleb": "chleb razowy",
    "ryż": "ryż biały gotowany",
    "makaron": "makaron pełnoziarnisty gotowany",
    "kurczak": "pierś z kurczaka",
    "pierś": "pierś z kurczaka",
    "łosoś": "łosoś atlantycki",
    "twaróg": "twaróg półtłusty",
    "ser biały": "twaróg półtłusty",
    "jogurt": "jogurt naturalny",
    "mleko": "mleko 2%",
    "masło": "masło orzechowe",
    "orzechy": "orzechy włoskie",
    "oliwa": "oliwa z oliwek",
    "miód": "miód",
    "czekolada": "czekolada gorzka",
    "białko": "odżywka białkowa",
    "odżywka": "odżywka białkowa",
    "kreatyna": "kreatyna",
    "banany": "banan",
    "jabłka": "jabłko",
    "woda": "woda",
    "izo": "izotonik",
    "izotonik": "izotonik",
    "elektrolity": "izotonik",
    "żel": "żel energetyczny",
    "gel": "żel energetyczny",
    "batony": "batony energetyczne",
    "baton": "batony energetyczne",
    "orzech": "orzechy włoskie",
    # Polish declension forms — dopełniacz, narzędnik, etc.
    "skyru": "skyr naturalny",
    "skyru naturalnego": "skyr naturalny",
    "banana": "banan",
    "jabłka": "jabłko",
    "płatków": "płatki owsiane",
    "płatków owsianych": "płatki owsiane",
    "płatkami": "płatki owsiane",
    "jajek": "jajko",
    "jajka": "jajko",
    "jajecznicy": "jajecznica",
    "jajecznicę": "jajecznica",
    "bułek": "bułka pszenna",
    "bułkę": "bułka pszenna",
    "chleba": "chleb razowy",
    "ryżu": "ryż biały gotowany",
    "makaronu": "makaron pełnoziarnisty gotowany",
    "kurczaka": "pierś z kurczaka",
    "piersi": "pierś z kurczaka",
    "łososia": "łosoś atlantycki",
    "twarogu": "twaróg półtłusty",
    "jogurtu": "jogurt naturalny",
    "jogurtu naturalnego": "jogurt naturalny",
    "mleka": "mleko 2%",
    "masła": "masło orzechowe",
    "masła orzechowego": "masło orzechowe",
    "orzechów": "orzechy włoskie",
    "orzechów włoskich": "orzechy włoskie",
    "oliwy": "oliwa z oliwek",
    "miodu": "miód",
    "czekolady": "czekolada gorzka",
    "czekolady gorzkiej": "czekolada gorzka 70%",
    "odżywki": "odżywka białkowa",
    "odżywki białkowej": "odżywka białkowa",
    "kreatyny": "kreatyna",
    "soku": "sok pomarańczowy",
    "soku pomarańczowego": "sok pomarańczowy",
    "kawy": "kawa czarna",
    "żeli": "żel energetyczny",
    "żelu": "żel energetyczny",
    "batonów": "batony energetyczne",
    "batona": "batony energetyczne",
    "izotoniku": "izotonik",
    "wody": "woda",
    "szynki": "szynka drobiowa",
    "szynki drobiowej": "szynka drobiowa",
    "sera": "ser żółty",
    "sera żółtego": "ser żółty",
    "brokuła": "brokuł",
    "szpinaku": "szpinak",
    "awokado": "awokado",
    "pomidora": "pomidor",
    "ogórka": "ogórek",
    "kasz": "kasza gryczana gotowana",
    "kaszy": "kasza gryczana gotowana",
    "kaszy gryczanej": "kasza gryczana gotowana",
    "ziemniaków": "ziemniaki gotowane",
    "batatów": "bataty gotowane",
    "żela": "żel energetyczny",
    "żel energetyczny": "żel energetyczny",
    # Common typos and diacritic-less variants
    "platkow": "płatki owsiane",
    "platkow owsianych": "płatki owsiane",
    "platki": "płatki owsiane",
}

# Polish declension endings to strip for fuzzy matching
_POLISH_GENITIVE_ENDINGS = [
    "u", "a", "ów", "i", "y", "ego", "ej", "ych", "ich", "owej", "owego",
]

def _strip_polish_ending(word: str) -> str:
    """Strip common Polish genitive/narzędnik endings for fuzzy matching."""
    word = word.lower().strip()
    for ending in sorted(_POLISH_GENITIVE_ENDINGS, key=len, reverse=True):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            stem = word[:-len(ending)]
            # Try adding back common nominative endings
            for nom_end in ("a", "y", "e", "o", ""):
                yield stem + nom_end
    yield word


def _normalize_unit(raw: str | None) -> str:
    if not raw:
        return "g"
    u = raw.lower().strip()
    if u in ("l", "litr", "litry", "litrów"):
        return "l"
    if u in ("ml",):
        return "ml"
    if u in ("kg", "kilogram", "kilogramy"):
        return "kg"
    if u in ("szt", "sztuka", "sztuki"):
        return "szt"
    for key in _UNIT_TO_GRAMS:
        if u.startswith(key):
            return key
    return u


def _unit_to_grams(amount: float, unit: str) -> float:
    u = _normalize_unit(unit)
    factor = _UNIT_TO_GRAMS.get(u, 1.0)
    if u in ("l",):
        factor = 1000.0
    return amount * factor


def _normalize_food_name(raw: str) -> str:
    name = raw.strip().lower().rstrip(",. ")
    # Exact alias match
    for variant, canonical in _FOOD_ALIASES.items():
        if name == variant:
            return canonical
    # Strip ending "a" (common Polish feminine singular → plural fix)
    if name.endswith("a") and len(name) > 3:
        singular = name[:-1]
        if singular in _FOOD_ALIASES:
            return _FOOD_ALIASES[singular]
    # Multi-word phrases: try each word combination
    words = name.split()
    if len(words) >= 2:
        # Try full phrases first
        for n in range(len(words), 0, -1):
            for start in range(0, len(words) - n + 1):
                phrase = " ".join(words[start:start+n])
                if phrase in _FOOD_ALIASES:
                    return _FOOD_ALIASES[phrase]
    # Try individual words
    for word in words:
        if word in _FOOD_ALIASES:
            return _FOOD_ALIASES[word]
    # Fuzzy stem matching
    for word in words:
        for stem in _strip_polish_ending(word):
            if stem in _FOOD_ALIASES:
                return _FOOD_ALIASES[stem]
    return name


def _lookup_food(db_name: str) -> dict | None:
    try:
        from qbot_nutrition_db import food_item_get_by_name
        # Try exact match first
        result = food_item_get_by_name(db_name)
        if result:
            return result
        # Try ILIKE fuzzy match
        from qbot_nutrition_db import food_item_search
        results = food_item_search(db_name, limit=3)
        if results:
            return results[0]
        # Try without last word if multi-word
        words = db_name.split()
        if len(words) >= 2:
            shorter = " ".join(words[:-1])
            result = food_item_get_by_name(shorter)
            if result:
                return result
            results = food_item_search(shorter, limit=3)
            if results:
                return results[0]
        return None
    except Exception:
        return None


def parse_intake(text: str) -> dict[str, Any]:
    """Parse natural language intake text into structured entries.
    
    Returns:
        {
            "ok": true/false,
            "meal_items": [{food_name, amount, unit, food_found, ...}],
            "hydration": [{fluid_ml, sodium_mg, ...}],
            "fueling": [{carbs_g, ...}],
            "unknown": [names of foods not found in DB],
            "raw": original_text
        }
    """
    text = text.strip()
    result: dict[str, Any] = {
        "ok": True,
        "meal_items": [],
        "hydration": [],
        "fueling": [],
        "unknown": [],
        "raw": text,
    }

    # Early hydration-only patterns
    hyd_match = _HYDRATION.findall(text)
    for match in hyd_match:
        amount_str, unit, food = match
        amount = float(amount_str.replace(",", "."))
        fluid_ml = amount * 1000 if _normalize_unit(unit) == "l" else amount
        result["hydration"].append({
            "fluid_ml": fluid_ml,
            "sodium_mg": 0,
            "note": food.strip() if food.strip() else None,
        })

    # Fueling — carbs on-the-go
    carb_matches = _CARB_ONLY.findall(text)
    for match in carb_matches:
        # match is string from capture group
        carbs = float(match.replace(",", "."))
        result["fueling"].append({"carbs_g": carbs})

    # Meal items — quantity+unit+food
    qty_matches = _QTY_UNIT_FOOD.findall(text)
    seen_foods: set[str] = set()
    for match in qty_matches:
        amount_str, unit, food_name = match
        amount = float(amount_str.replace(",", "."))
        normalized_food = _normalize_food_name(food_name)
        if normalized_food in seen_foods:
            continue
        seen_foods.add(normalized_food)
        grams_est = _unit_to_grams(amount, unit)

        food_db = _lookup_food(normalized_food)
        item = {
            "food_name": food_name.strip(),
            "food_normalized": normalized_food,
            "amount": amount,
            "unit": _normalize_unit(unit),
            "grams_est": grams_est,
            "food_found": food_db is not None,
        }
        if food_db:
            factor = grams_est / 100.0
            item["food_id"] = food_db["id"]
            item["kcal"] = round((food_db.get("kcal_per_100g") or 0) * factor, 1)
            item["carbs_g"] = round((food_db.get("carbs_per_100g") or 0) * factor, 1)
            item["protein_g"] = round((food_db.get("protein_per_100g") or 0) * factor, 1)
            item["fat_g"] = round((food_db.get("fat_per_100g") or 0) * factor, 1)
            item["fiber_g"] = round((food_db.get("fiber_per_100g") or 0) * factor, 1)
            item["sodium_mg"] = round((food_db.get("sodium_per_100g") or 0) * factor, 1)
        else:
            result["unknown"].append(normalized_food)
        result["meal_items"].append(item)

    # If no structured matches found, try simple food-name-only parsing
    if not result["meal_items"] and not result["hydration"] and not result["fueling"]:
        parts = re.split(r"[,.;]|\s+z\s+|\s+i\s+|\s+oraz\s+|\s+a\s+", text)
        for part in parts:
            part = part.strip().lower()
            if not part or len(part) < 2:
                continue
            # Try qty+food
            qm = re.match(r"(\d+)\s*(?:szt\.?)?\s*(.+)", part)
            if qm:
                amount = float(qm.group(1))
                food_name = qm.group(2).strip()
            else:
                amount = 1
                food_name = part
            normalized = _normalize_food_name(food_name)
            if normalized in seen_foods:
                continue
            seen_foods.add(normalized)
            food_db = _lookup_food(normalized)
            item = {
                "food_name": food_name,
                "food_normalized": normalized,
                "amount": amount,
                "unit": "szt" if amount >= 1 else "g",
                "grams_est": amount * 100 if amount >= 1 else 100,
                "food_found": food_db is not None,
            }
            if food_db:
                factor = (amount * 100) / 100.0 if amount >= 1 else 1.0
                item["food_id"] = food_db["id"]
                item["kcal"] = round((food_db.get("kcal_per_100g") or 0) * factor, 1)
                item["carbs_g"] = round((food_db.get("carbs_per_100g") or 0) * factor, 1)
                item["protein_g"] = round((food_db.get("protein_per_100g") or 0) * factor, 1)
                item["fat_g"] = round((food_db.get("fat_per_100g") or 0) * factor, 1)
                item["fiber_g"] = round((food_db.get("fiber_per_100g") or 0) * factor, 1)
                item["sodium_mg"] = round((food_db.get("sodium_per_100g") or 0) * factor, 1)
            else:
                result["unknown"].append(normalized)
            result["meal_items"].append(item)

    result["ok"] = True
    return result
