p="/opt/qbot/web/public/start2.js"
s=open(p).read()

# 1) Napraw emoji — zamień kody na prawdziwe znaki
s=s.replace("\\U0001F6B4\\U0001F3FB","\U0001F6B4\U0001F3FB")
s=s.replace("\\U0001F915","\U0001F915")
s=s.replace("\\U0001F60A","\U0001F60A")
s=s.replace("\\u2014","\u2014")
s=s.replace("\\u2193","\u2193")

# 2) Zmien kolejnosc kolumn: dzień | gotowość | aktywność | sen/HRV | choroba
old="div.innerHTML='<span class=\"dc\">'+lbl+'</span><span class=\"da\">'+actHtml+'</span><span class=\"dw\">'+sleepLbl+' · HRV '+qN(dd3.hrv,0)+'</span><span class=\"de\">'+entHtml+'</span><span class=\"pill small '+rdyCls+'\">'+qEsc(readLbl)+'</span>';"
assert s.count(old)==1
new="div.innerHTML='<span class=\"dc\">'+lbl+'</span><span class=\"pill small '+rdyCls+'\">'+qEsc(readLbl)+'</span><span class=\"da\">'+actHtml+'</span><span class=\"dw\">'+sleepLbl+' \u00b7 HRV '+qN(dd3.hrv,0)+'</span><span class=\"de\">'+entHtml+'</span>';"
s=s.replace(old,new)

open(p,"w").write(s)
print("fixed emoji + column order")
