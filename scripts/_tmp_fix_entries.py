p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

# po pobraniu danych: zbuduj mape entries per dzien
old='  calData=cal.days||{};ridesMap={};var seen={};'
assert s.count(old)==1
new='''  calData=cal.days||{};ridesMap={};var seen={};
  /* wpisy kalendarza (samopoczucie, choroba, wydarzenie) → per dzień */
  (cal.entries||[]).forEach(function(e){var d=calData[e.day]=calData[e.day]||{};d._entries=d._entries||[];d._entries.push(e);
    if(e.end_day&&e.end_day!==e.day){var sd=new Date(e.day+"T12:00:00"),ed=new Date(e.end_day+"T12:00:00");for(var dd2=new Date(sd);dd2<=ed;dd2.setDate(dd2.getDate()+1)){var dk=localISO(dd2);calData[dk]=calData[dk]||{};calData[dk]._entries=calData[dk]._entries||[];if(dk!==e.day)calData[dk]._entries.push(e);}}
  });'''
s=s.replace(old,new)

# renderowanie wpisów w kaflach
old2='var slParts=[];if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1));if(dd.weight_kg)slParts.push(qN(dd.weight_kg,1)+" kg");'
assert s.count(old2)==1
new2='''var ents=dd._entries||[];
    ents.forEach(function(e){if(e.kind==="illness")h+='<div class="ride" style="color:var(--bad)">🤒 '+qEsc(e.title||"choroba")+'</div>';
      else if(e.kind==="feel")h+='<div class="ride">😊 '+qEsc(e.title||(e.feel>0?"dobrze":e.feel<0?"słabo":"neutralnie"))+'</div>';
      else if(e.kind==="event")h+='<div class="ride" style="color:var(--blue)">📅 '+qEsc(e.title||"wydarzenie")+'</div>';});
    var slParts=[];if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1));if(dd.weight_kg)slParts.push(qN(dd.weight_kg,1)+" kg");'''
s=s.replace(old2,new2)

# panel dnia: pokaż wpisy
old3='if(!rr.length)rows.innerHTML+=\'<div class="r" style="grid-template-columns:1fr"><span class="w">dzień bez jazdy</span></div>\';}'
assert s.count(old3)==1
new3='''if(!rr.length)rows.innerHTML+='<div class="r" style="grid-template-columns:1fr"><span class="w">dzień bez jazdy</span></div>';
    var ents2=(calData[ds]||{})._entries||[];
    ents2.forEach(function(e){rows.innerHTML+='<div class="r" style="grid-template-columns:1fr"><span class="w">'+(e.kind==="illness"?"🤒 ":e.kind==="feel"?"😊 ":"📅 ")+qEsc(e.title||e.kind)+(e.note?" — "+qEsc(e.note):"")+'</span></div>';});}'''
s=s.replace(old3,new3)

open(p,"w").write(s)
print("fixed: entries z cal.entries renderowane w kaflach i panelu dnia")
