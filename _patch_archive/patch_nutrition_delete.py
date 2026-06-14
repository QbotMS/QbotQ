#!/usr/bin/env python3
"""Dodaj nutrition_log_delete do action_execute enum i dispatch."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
MA = '/opt/qbot/app/qbot_mcp_adapter.py'
with open(MA, encoding='utf-8') as f:
    ma = f.read()
shutil.copy(MA, f'{MA}.bak.nutdel.{ts}')

# 1. Dodaj do enum
old_enum = '"nutrition_log_add", "qcal_reminder_add",'
new_enum = '"nutrition_log_add", "nutrition_log_delete", "nutrition_log_correct", "qcal_reminder_add",'
if old_enum in ma:
    ma = ma.replace(old_enum, new_enum, 1)
    print("OK: enum extended")
else:
    print("FAIL: enum not found")

# 2. Dodaj do dispatch
old_dispatch = (
    '    if action_type == "nutrition_log_add":\n'
    '        return _action_exec_nutrition(payload, idem_key, source)'
)
new_dispatch = (
    '    if action_type == "nutrition_log_delete":\n'
    '        return _action_exec_nutrition_delete(payload, idem_key)\n'
    '    elif action_type == "nutrition_log_correct":\n'
    '        return _action_exec_nutrition_correct(payload, idem_key)\n'
    '    elif action_type == "nutrition_log_add":\n'
    '        return _action_exec_nutrition(payload, idem_key, source)'
)
if old_dispatch in ma:
    ma = ma.replace(old_dispatch, new_dispatch, 1)
    print("OK: dispatch extended")
else:
    print("FAIL: dispatch not found")

# 3. Dodaj funkcje handlery przed _action_exec_nutrition
old_nutrition_fn = 'def _action_exec_nutrition(payload'
new_handlers = (
    'def _action_exec_nutrition_delete(payload: dict, idem_key: str) -> dict:\n'
    '    """Usuń wpis intake_log. Wymaga meal_log_id w payload."""\n'
    '    import os, psycopg\n'
    '    from psycopg.rows import dict_row\n'
    '    meal_log_id = payload.get("meal_log_id") or payload.get("intake_log_id")\n'
    '    if not meal_log_id:\n'
    '        return {"tool":"qbot.action_execute","status":"ERROR","error":"meal_log_id required in payload"}\n'
    '    try:\n'
    '        conn = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),\n'
    '            port=os.getenv("PGPORT","5432"), dbname=os.getenv("PGDATABASE","qbot"),\n'
    '            user=os.getenv("PGUSER","qbot"), password=os.getenv("PGPASSWORD",""),\n'
    '            row_factory=dict_row, connect_timeout=5,\n'
    '            options="-c search_path=qbot_v2")\n'
    '        with conn:\n'
    '            row = conn.execute("SELECT date FROM qbot_v2.intake_logs WHERE id=%s", (meal_log_id,)).fetchone()\n'
    '            if not row:\n'
    '                return {"tool":"qbot.action_execute","status":"NOT_FOUND","error":f"intake_log {meal_log_id} not found"}\n'
    '            date_str = str(row["date"])\n'
    '            conn.execute("DELETE FROM qbot_v2.intake_items WHERE intake_log_id=%s", (meal_log_id,))\n'
    '            conn.execute("DELETE FROM qbot_v2.intake_logs WHERE id=%s", (meal_log_id,))\n'
    '            # Przelicz summary\n'
    '            conn.execute("""\n'
    '                UPDATE qbot_v2.nutrition_daily_summary\n'
    '                SET kcal_total=(SELECT COALESCE(SUM(ii.kcal),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                    protein_total=(SELECT COALESCE(SUM(ii.protein_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                    carbs_total=(SELECT COALESCE(SUM(ii.carbs_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                    fat_total=(SELECT COALESCE(SUM(ii.fat_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                    computed_at=NOW()\n'
    '                WHERE date=%s\n'
    '            """, (date_str,date_str,date_str,date_str,date_str))\n'
    '        conn.close()\n'
    '        return {"tool":"qbot.action_execute","status":"OK",\n'
    '                "message":f"intake_log {meal_log_id} usunięty, summary przeliczone dla {date_str}",\n'
    '                "meal_log_id":meal_log_id, "date":date_str}\n'
    '    except Exception as e:\n'
    '        return {"tool":"qbot.action_execute","status":"ERROR","error":str(e)[:200]}\n'
    '\n'
    '\n'
    'def _action_exec_nutrition_correct(payload: dict, idem_key: str) -> dict:\n'
    '    """Popraw makra wpisu intake_items. Wymaga intake_item_id lub meal_log_id."""\n'
    '    import os, psycopg\n'
    '    from psycopg.rows import dict_row\n'
    '    item_id = payload.get("intake_item_id")\n'
    '    meal_log_id = payload.get("meal_log_id") or payload.get("intake_log_id")\n'
    '    if not item_id and not meal_log_id:\n'
    '        return {"tool":"qbot.action_execute","status":"ERROR","error":"intake_item_id or meal_log_id required"}\n'
    '    try:\n'
    '        conn = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),\n'
    '            port=os.getenv("PGPORT","5432"), dbname=os.getenv("PGDATABASE","qbot"),\n'
    '            user=os.getenv("PGUSER","qbot"), password=os.getenv("PGPASSWORD",""),\n'
    '            row_factory=dict_row, connect_timeout=5,\n'
    '            options="-c search_path=qbot_v2")\n'
    '        updates = {}\n'
    '        for f in ("kcal","protein_g","carbs_g","fat_g","food_name"):\n'
    '            if f in payload: updates[f] = payload[f]\n'
    '        if not updates:\n'
    '            return {"tool":"qbot.action_execute","status":"ERROR","error":"No fields to update in payload"}\n'
    '        set_clause = ", ".join(f"{k}=%s" for k in updates)\n'
    '        vals = list(updates.values())\n'
    '        with conn:\n'
    '            if item_id:\n'
    '                row = conn.execute("SELECT il.date FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE ii.id=%s",(item_id,)).fetchone()\n'
    '                date_str = str(row["date"]) if row else None\n'
    '                conn.execute(f"UPDATE qbot_v2.intake_items SET {set_clause} WHERE id=%s", vals+[item_id])\n'
    '            else:\n'
    '                row = conn.execute("SELECT date FROM qbot_v2.intake_logs WHERE id=%s",(meal_log_id,)).fetchone()\n'
    '                date_str = str(row["date"]) if row else None\n'
    '                conn.execute(f"UPDATE qbot_v2.intake_items SET {set_clause} WHERE intake_log_id=%s", vals+[meal_log_id])\n'
    '            if date_str:\n'
    '                conn.execute("""\n'
    '                    UPDATE qbot_v2.nutrition_daily_summary\n'
    '                    SET kcal_total=(SELECT COALESCE(SUM(ii.kcal),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                        protein_total=(SELECT COALESCE(SUM(ii.protein_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                        carbs_total=(SELECT COALESCE(SUM(ii.carbs_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                        fat_total=(SELECT COALESCE(SUM(ii.fat_g),0) FROM qbot_v2.intake_items ii JOIN qbot_v2.intake_logs il ON il.id=ii.intake_log_id WHERE il.date=%s),\n'
    '                        computed_at=NOW() WHERE date=%s\n'
    '                """, (date_str,date_str,date_str,date_str,date_str))\n'
    '        conn.close()\n'
    '        return {"tool":"qbot.action_execute","status":"OK","message":f"Makra poprawione, summary przeliczone dla {date_str}","updates":updates}\n'
    '    except Exception as e:\n'
    '        return {"tool":"qbot.action_execute","status":"ERROR","error":str(e)[:200]}\n'
    '\n'
    '\n'
    'def _action_exec_nutrition(payload'
)
if old_nutrition_fn in ma:
    ma = ma.replace(old_nutrition_fn, new_handlers, 1)
    print("OK: nutrition_delete and nutrition_correct handlers added")
else:
    print("FAIL: _action_exec_nutrition not found")

ast.parse(ma)
with open(MA, 'w', encoding='utf-8') as f:
    f.write(ma)
print("syntax OK")
