import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

Q = [
 ("ostatnie 15 turnow (dowolna data)", """
 SELECT id, created_at, chat_id, direction, intent, left(message_text,120) AS msg
 FROM telegram_conversation_turns ORDER BY id DESC LIMIT 15"""),
 ("konwersacje", """
 SELECT chat_id, state, pending_action_id, last_intent, updated_at, left(coalesce(context_json::text,''),200) AS ctx
 FROM telegram_conversations ORDER BY updated_at DESC LIMIT 5"""),
]
with _db_connect() as conn:
    cur = conn.cursor()
    for title, sql in Q:
        print("==", title, "==")
        try:
            cur.execute(sql)
            for r in cur.fetchall():
                print(json.dumps(r, default=str, ensure_ascii=False))
        except Exception as e:
            conn.rollback()
            print("ERR", e)
