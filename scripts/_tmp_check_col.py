import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
old='"ts.xss "'
new='"ts.xss_total AS xss "'
# sprawdz czy xss_total istnieje
# z logu: HINT: Perhaps you meant to reference the column "ts.tss" - szukam xss w training_sessions
# Moze to tss? Sprawdze nazwe kolumny
print("xss count:", s.count("ts.xss"))
print("tss count:", s.count("ts.tss"))
# Sprawdzmy actual column
