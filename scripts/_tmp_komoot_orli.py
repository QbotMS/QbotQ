import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
import komoot_watch
res = komoot_watch.analyze_tour("3276635248")
print(json.dumps(res, ensure_ascii=False, indent=1))
