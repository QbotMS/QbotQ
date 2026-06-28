import base64,os
p="/opt/qbot/artifacts/maps/map_55798129_land.png"
b=open(p,"rb").read()
print("PNG bytes", len(b))
open("/opt/qbot/app/data/_map_land_b64.txt","w").write(base64.b64encode(b).decode())
print("b64 chars", os.path.getsize("/opt/qbot/app/data/_map_land_b64.txt"))
