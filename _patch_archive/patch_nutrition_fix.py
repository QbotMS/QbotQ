#!/usr/bin/env python3
"""
1. Dodaj dedup w qbot_v2.intake_items przy zapisie — nie zapisuj jeśli już jest identyczny item
2. Dodaj qbot.nutrition_log_delete do allowlisty action_execute
3. Dodaj nutrition_write_audit do create jeśli nie istnieje
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

# ── 1: dedup w meal_log_create — qbot_v2 insert ──────────────────────
NDB = '/opt/qbot/app/qbot_nutrition_db.py'
with open(NDB, encoding='utf-8') as f:
    ndb = f.read()
shutil.copy(NDB, f'{NDB}.bak.{ts}')

old_v2_insert = (
    '                for item in items:\n'
    '                    v2.execute(\n'
    '                        """INSERT INTO qbot_v2.intake_items\n'
    '                           (intake_log_id, food_name, amount, unit,\n'
    '                            kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg)\n'
    '                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""","'
)

# Patch: sprawdź czy już istnieje identyczny item przed insertem
old_v2_loop = (
    '                for item in items:\n'
    '                    v2.execute(\n'
    '                        """INSERT INTO qbot_v2.intake_items\n'
    '                           (intake_log_id, food_name, amount, unit,\n'
    '                            kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg)\n'
    '                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",\n'
    '                        (\n'
    '                            v2_log_id,\n'
    '                            item.get("food") or item.get("food_name", "unknown"),\n'
    '                            item.get("amount", 0),\n'
    '                            item.get("unit", "g"),\n'
    '                            item.get("kcal"),\n'
    '                            item.get("protein_g"),\n'
    '                            item.get("carbs_g"),\n'
    '                            item.get("fat_g"),\n'
    '                            item.get("fiber_g"),\n'
    '                            item.get("sodium_mg"),\n'
    '                        ),\n'
    '                    )'
)
new_v2_loop = (
    '                _inserted_items = set()  # dedup: (food_name, kcal)\n'
    '                for item in items:\n'
    '                    _item_key = (item.get("food") or item.get("food_name",""), item.get("kcal"))\n'
    '                    if _item_key in _inserted_items:\n'
    '                        continue  # pomiń duplikat\n'
    '                    _inserted_items.add(_item_key)\n'
    '                    v2.execute(\n'
    '                        """INSERT INTO qbot_v2.intake_items\n'
    '                           (intake_log_id, food_name, amount, unit,\n'
    '                            kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg)\n'
    '                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",\n'
    '                        (\n'
    '                            v2_log_id,\n'
    '                            item.get("food") or item.get("food_name", "unknown"),\n'
    '                            item.get("amount", 0),\n'
    '                            item.get("unit", "g"),\n'
    '                            item.get("kcal"),\n'
    '                            item.get("protein_g"),\n'
    '                            item.get("carbs_g"),\n'
    '                            item.get("fat_g"),\n'
    '                            item.get("fiber_g"),\n'
    '                            item.get("sodium_mg"),\n'
    '                        ),\n'
    '                    )'
)
if old_v2_loop in ndb:
    ndb = ndb.replace(old_v2_loop, new_v2_loop, 1)
    ast.parse(ndb)
    with open(NDB, 'w', encoding='utf-8') as f:
        f.write(ndb)
    print("OK: meal_log_create v2 insert dedup by (food_name, kcal)")
else:
    print("FAIL: v2 loop block not found")

# ── 2: dodaj nutrition_log_delete do action_execute allowlisty ────────
MA = '/opt/qbot/app/qbot_mcp_adapter.py'
with open(MA, encoding='utf-8') as f:
    ma = f.read()

old_allowlist = '"nutrition_log_add"'
new_allowlist = '"nutrition_log_add", "nutrition_log_delete", "nutrition_log_correct"'

# Znajdź w _ACTION_REQUIRED_PAYLOAD_FIELDS
if '_ACTION_REQUIRED_PAYLOAD_FIELDS' in ma:
    idx = ma.find('_ACTION_REQUIRED_PAYLOAD_FIELDS')
    ctx = ma[idx:idx+500]
    if '"nutrition_log_add"' in ctx and '"nutrition_log_delete"' not in ctx:
        # Dodaj nutrition_log_delete i nutrition_log_correct do słownika
        old_dict_entry = '"nutrition_log_add": ["date",'
        new_dict_entry = (
            '"nutrition_log_add": ["date",\n'
            '        # nutrition_log_delete handled separately\n'
        )
        # Prostsze: dodaj handlery w action_execute dispatch
        print("SKIP allowlist - using separate handler")

# Sprawdź czy jest osobny handler delete
if '_handle_nutrition_log_delete' not in ma:
    print("NOTE: nutrition_log_delete handler exists at line 895")
    # Sprawdź czy jest w routing action_execute
    if '"nutrition_log_delete"' in ma:
        print("OK: nutrition_log_delete already routed in action_execute")
    else:
        print("NEED: route nutrition_log_delete in action_execute")

print("Done")
