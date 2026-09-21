p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
# Linia 8796: zapytanie kalendarza z fitmodel_daily
# Linia 8834: budowanie days dict
# Dodajemy LEFT JOIN wellness + weight_kg
i8796=s.index("\"hrv_night, rhr, sleep_h, glycogen_pct \"")
chunk=s[i8796-300:i8796+600]
print("AROUND 8796:")
print(repr(chunk[:200]))
print("---")
print(repr(chunk[200:400]))
print("---")  
print(repr(chunk[400:600]))
