import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

SQL = """
SELECT id, created_at, direction, intent, action_id, left(message_text, 160) AS msg
FROM telegram_conversation_turns
WHERE created_at > now() - interval '6 hours'
ORDER BY id DESC
LIMIT 40
"""
SQL2 = """
SELECT id, created_at, updated_at, action_type, status, idempotency_key, left(preview_text,120) AS preview
FROM telegram_pending_actions
WHERE created_at > now() - interval '6 hours'
ORDER BY id DESC
LIMIT 20
"""
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute(SQL)
    print("== TURNS ==")
    for r in cur.fetchall():
        print(json.dumps(r, default=str, ensure_ascii=False))
    cur.execute(SQL2)
    print("== PENDING ACTIONS ==")
    for r in cur.fetchall():
        print(json.dumps(r, default=str, ensure_ascii=False))
