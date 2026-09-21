p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

# 1) promptFeel: kind="feel", feel=liczba -2..2
old='''function promptFeel(){
  var opts=["świetnie","dobrze","neutralnie","słabo","źle"];
  var pick=prompt("Samopoczucie "+selDay+":\\n"+opts.map(function(o,i){return(i+1)+". "+o;}).join("\\n")+"\\n\\nWpisz numer (1-5):");
  if(!pick)return;var idx=parseInt(pick)-1;if(idx<0||idx>=opts.length)return;
  fetch("/api/calendar",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({action:"add",day:selDay,type:"feel",value:opts[idx]})
  }).then(function(){render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
new='''function promptFeel(){
  var opts=["świetnie","dobrze","neutralnie","słabo","źle"];
  var vals=[2,1,0,-1,-2];
  var pick=prompt("Samopoczucie "+selDay+":\\n"+opts.map(function(o,i){return(i+1)+". "+o;}).join("\\n")+"\\n\\nWpisz numer (1-5):");
  if(!pick)return;var idx=parseInt(pick)-1;if(idx<0||idx>=opts.length)return;
  fetch("/api/calendar/entry",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({day:selDay,kind:"feel",feel:vals[idx],title:opts[idx]})
  }).then(function(r){if(!r.ok)return r.text().then(function(t){throw new Error(t);});render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
assert s.count(old)==1
s=s.replace(old,new)

# 2) promptIllness
old2='''function promptIllness(){
  var note=prompt("Choroba "+selDay+" — opis (np. katar, gorączka):");
  if(!note)return;
  fetch("/api/calendar",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({action:"add",day:selDay,type:"illness",value:note})
  }).then(function(){render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
new2='''function promptIllness(){
  var note=prompt("Choroba "+selDay+" — opis (np. katar, gorączka):");
  if(!note)return;
  fetch("/api/calendar/entry",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({day:selDay,kind:"illness",title:note})
  }).then(function(r){if(!r.ok)return r.text().then(function(t){throw new Error(t);});render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
assert s.count(old2)==1
s=s.replace(old2,new2)

# 3) promptEvent
old3='''function promptEvent(){
  var note=prompt("Wydarzenie "+selDay+" — tytuł:");
  if(!note)return;
  fetch("/api/calendar",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({action:"add",day:selDay,type:"event",value:note})
  }).then(function(){render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
new3='''function promptEvent(){
  var note=prompt("Wydarzenie "+selDay+" — tytuł:");
  if(!note)return;
  fetch("/api/calendar/entry",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
    body:JSON.stringify({day:selDay,kind:"event",title:note})
  }).then(function(r){if(!r.ok)return r.text().then(function(t){throw new Error(t);});render();}).catch(function(e){alert("Błąd: "+e.message);});
}'''
assert s.count(old3)==1
s=s.replace(old3,new3)

open(p,"w").write(s)
print("fixed: POST /api/calendar/entry, kind+title zamiast type+value")
