p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
# szukam bloku FTP
for needle in ["/* FTP","FTP spark","_ftpChart","ftpCanvas","trendy-ftp"]:
    i=s.find(needle)
    if i>=0: print(needle,"at",i,repr(s[i:i+40]))
    else: print(needle,"NOT FOUND")
