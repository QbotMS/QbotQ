import httpx
url="https://tile.openstreetmap.org/12/2308/1361.png"
try:
    r=httpx.get(url,headers={"User-Agent":"QBot/3.0 route-report map"},timeout=20.0)
    print("status",r.status_code,"bytes",len(r.content),"ctype",r.headers.get("content-type"))
except Exception as e:
    print("ERR",repr(e))
