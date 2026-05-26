#!/usr/bin/env python3
"""QBot Nutrition — seed common food items into PostgreSQL."""
from __future__ import annotations

import os, sys
sys.path.insert(0, "/opt/qbot/app")

SEED_FOODS = [
    # Dane: kcal, carbs, protein, fat, fiber, sodium per 100g
    # source: Polish food databases, manufacturer labels
    {"name": "skyr naturalny", "brand": "Pilos", "kcal_per_100g": 63, "carbs_per_100g": 4, "protein_per_100g": 11, "fat_per_100g": 0.2, "sodium_per_100g": 0.04},
    {"name": "banan", "kcal_per_100g": 89, "carbs_per_100g": 23, "protein_per_100g": 1.1, "fat_per_100g": 0.3, "fiber_per_100g": 2.6},
    {"name": "jabłko", "kcal_per_100g": 52, "carbs_per_100g": 14, "protein_per_100g": 0.3, "fat_per_100g": 0.2, "fiber_per_100g": 2.4},
    {"name": "płatki owsiane", "kcal_per_100g": 370, "carbs_per_100g": 67, "protein_per_100g": 14, "fat_per_100g": 7, "fiber_per_100g": 10},
    {"name": "jajko", "kcal_per_100g": 155, "carbs_per_100g": 0.7, "protein_per_100g": 13, "fat_per_100g": 11, "fiber_per_100g": 0},
    {"name": "jajecznica", "kcal_per_100g": 182, "carbs_per_100g": 1.5, "protein_per_100g": 12, "fat_per_100g": 14, "fiber_per_100g": 0},
    {"name": "bułka pszenna", "kcal_per_100g": 265, "carbs_per_100g": 54, "protein_per_100g": 8, "fat_per_100g": 3, "fiber_per_100g": 2},
    {"name": "chleb razowy", "kcal_per_100g": 220, "carbs_per_100g": 42, "protein_per_100g": 8, "fat_per_100g": 2, "fiber_per_100g": 7},
    {"name": "ryż biały gotowany", "kcal_per_100g": 130, "carbs_per_100g": 28, "protein_per_100g": 2.7, "fat_per_100g": 0.3, "fiber_per_100g": 0.4},
    {"name": "makaron pełnoziarnisty gotowany", "kcal_per_100g": 131, "carbs_per_100g": 25, "protein_per_100g": 5, "fat_per_100g": 0.8, "fiber_per_100g": 3.5},
    {"name": "pierś z kurczaka", "kcal_per_100g": 165, "carbs_per_100g": 0, "protein_per_100g": 31, "fat_per_100g": 3.6, "fiber_per_100g": 0},
    {"name": "łosoś atlantycki", "kcal_per_100g": 208, "carbs_per_100g": 0, "protein_per_100g": 20, "fat_per_100g": 13, "fiber_per_100g": 0, "sodium_per_100g": 0.06},
    {"name": "twaróg półtłusty", "kcal_per_100g": 110, "carbs_per_100g": 3, "protein_per_100g": 17, "fat_per_100g": 4, "fiber_per_100g": 0},
    {"name": "jogurt naturalny", "kcal_per_100g": 61, "carbs_per_100g": 5, "protein_per_100g": 4.5, "fat_per_100g": 2.5, "fiber_per_100g": 0},
    {"name": "mleko 2%", "kcal_per_100g": 50, "carbs_per_100g": 5, "protein_per_100g": 3.5, "fat_per_100g": 2, "fiber_per_100g": 0, "sodium_per_100g": 0.04},
    {"name": "masło orzechowe", "kcal_per_100g": 588, "carbs_per_100g": 20, "protein_per_100g": 25, "fat_per_100g": 50, "fiber_per_100g": 6},
    {"name": "orzechy włoskie", "kcal_per_100g": 654, "carbs_per_100g": 14, "protein_per_100g": 15, "fat_per_100g": 65, "fiber_per_100g": 7},
    {"name": "oliwa z oliwek", "kcal_per_100g": 884, "carbs_per_100g": 0, "protein_per_100g": 0, "fat_per_100g": 100},
    {"name": "miód", "kcal_per_100g": 304, "carbs_per_100g": 82, "protein_per_100g": 0.3, "fat_per_100g": 0, "fiber_per_100g": 0.2},
    {"name": "czekolada gorzka 70%", "kcal_per_100g": 598, "carbs_per_100g": 33, "protein_per_100g": 10, "fat_per_100g": 47, "fiber_per_100g": 11},
    {"name": "odżywka białkowa", "brand": "Whey Protein", "kcal_per_100g": 380, "carbs_per_100g": 5, "protein_per_100g": 80, "fat_per_100g": 5, "sodium_per_100g": 0.2},
    {"name": "kreatyna", "kcal_per_100g": 0, "carbs_per_100g": 0, "protein_per_100g": 0, "fat_per_100g": 0},
    {"name": "żel energetyczny", "brand": "SIS Go", "kcal_per_100g": 160, "carbs_per_100g": 40, "protein_per_100g": 0, "fat_per_100g": 0, "sodium_per_100g": 0.05, "default_unit": "szt"},
    {"name": "izotonik", "kcal_per_100g": 16, "carbs_per_100g": 4, "protein_per_100g": 0, "fat_per_100g": 0, "sodium_per_100g": 0.05, "default_unit": "ml"},
    {"name": "batony energetyczne", "brand": "SIS", "kcal_per_100g": 350, "carbs_per_100g": 55, "protein_per_100g": 6, "fat_per_100g": 12, "fiber_per_100g": 3, "default_unit": "szt"},
    {"name": "awokado", "kcal_per_100g": 160, "carbs_per_100g": 9, "protein_per_100g": 2, "fat_per_100g": 15, "fiber_per_100g": 7},
    {"name": "pomidor", "kcal_per_100g": 18, "carbs_per_100g": 4, "protein_per_100g": 1, "fat_per_100g": 0.2, "fiber_per_100g": 1},
    {"name": "ogórek", "kcal_per_100g": 12, "carbs_per_100g": 2, "protein_per_100g": 0.7, "fat_per_100g": 0.1, "fiber_per_100g": 0.5},
    {"name": "brokuł", "kcal_per_100g": 34, "carbs_per_100g": 7, "protein_per_100g": 3, "fat_per_100g": 0.4, "fiber_per_100g": 2.6},
    {"name": "szpinak", "kcal_per_100g": 23, "carbs_per_100g": 4, "protein_per_100g": 3, "fat_per_100g": 0.4, "fiber_per_100g": 2.2},
    {"name": "ser żółty", "kcal_per_100g": 350, "carbs_per_100g": 0, "protein_per_100g": 25, "fat_per_100g": 28, "sodium_per_100g": 0.8},
    {"name": "szynka drobiowa", "kcal_per_100g": 102, "carbs_per_100g": 1.5, "protein_per_100g": 19, "fat_per_100g": 2.5, "sodium_per_100g": 0.8},
    {"name": "kasza gryczana gotowana", "kcal_per_100g": 110, "carbs_per_100g": 21, "protein_per_100g": 4, "fat_per_100g": 1.5, "fiber_per_100g": 2},
    {"name": "ziemniaki gotowane", "kcal_per_100g": 87, "carbs_per_100g": 20, "protein_per_100g": 2, "fat_per_100g": 0.1, "fiber_per_100g": 1.8},
    {"name": "bataty gotowane", "kcal_per_100g": 90, "carbs_per_100g": 21, "protein_per_100g": 2, "fat_per_100g": 0.2, "fiber_per_100g": 3},
    {"name": "kawa czarna", "kcal_per_100g": 1, "carbs_per_100g": 0, "protein_per_100g": 0, "fat_per_100g": 0, "default_unit": "ml"},
    {"name": "sok pomarańczowy", "kcal_per_100g": 45, "carbs_per_100g": 10, "protein_per_100g": 0.7, "fat_per_100g": 0.2, "default_unit": "ml"},
    {"name": "woda", "kcal_per_100g": 0, "carbs_per_100g": 0, "protein_per_100g": 0, "fat_per_100g": 0, "default_unit": "ml"},
]

def seed():
    from qbot_nutrition_db import food_item_create
    for f in SEED_FOODS:
        try:
            food_item_create(
                name=f["name"],
                brand=f.get("brand"),
                default_unit=f.get("default_unit", "g"),
                kcal_per_100g=f.get("kcal_per_100g"),
                carbs_per_100g=f.get("carbs_per_100g"),
                sugar_per_100g=f.get("sugar_per_100g"),
                protein_per_100g=f.get("protein_per_100g"),
                fat_per_100g=f.get("fat_per_100g"),
                fiber_per_100g=f.get("fiber_per_100g"),
                sodium_per_100g=f.get("sodium_per_100g"),
                source="qbot_seed",
                verified=True,
            )
            print(f"OK   {f['name']}")
        except Exception as exc:
            print(f"FAIL {f['name']}: {exc}")

if __name__ == "__main__":
    seed()
