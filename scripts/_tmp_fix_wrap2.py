p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

# Panel dnia: wpisy z ikonką, zawijanie, linia oddzielająca
old='''    var ents2=(calData[ds]||{})._entries||[];
    ents2.forEach(function(e){rows.innerHTML+='<div class="r" style="grid-template-columns:1fr"><span class="w">'+(e.kind==="illness"?"🤒 ":e.kind==="feel"?"😊 ":"📅 ")+qEsc(e.title||e.kind)+(e.note?" — "+qEsc(e.note):"")+'</span></div>';});}'''
assert s.count(old)==1
new='''    var ents2=(calData[ds]||{})._entries||[];
    if(ents2.length)rows.innerHTML+='<hr style="border:0;border-top:1px solid var(--line);margin:8px 0">';
    ents2.forEach(function(e){rows.innerHTML+='<div style="display:flex;gap:8px;align-items:baseline;padding:4px 0;font-size:14.5px;line-height:1.5"><span style="flex-shrink:0">'+(e.kind==="illness"?"🤒":e.kind==="feel"?"😊":"📅")+'</span><span style="word-break:break-word">'+qEsc(e.title||e.kind)+(e.note?" — "+qEsc(e.note):"")+'</span></div>';});}'''
s=s.replace(old,new)

open(p,"w").write(s)
print("fixed panel entries wrap")
