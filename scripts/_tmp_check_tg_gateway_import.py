import sys
sys.path.insert(0, "/opt/qbot/app")
import telegram_reply_processor as trp
print("import OK")
print("detekcja komendy:", trp._is_route_gateway_message("358008451", "przelicz trase 3180619966"))
print("detekcja zwyklej:", trp._is_route_gateway_message("358008451", "spalem 7h"))
import qbot_qcal_telegram as g
print("zrodlo 3180619966:", g._route_source_for_id("3180619966"))
print("zrodlo 55918401:", g._route_source_for_id("55918401"))
print("allowlist:", sorted(g._ALLOWED_ACTIONS))
