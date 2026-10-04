/* Raport z jazdy v2 -- odtwarzanie + wykres w pasach + odcinki + sekcje po ludzku. Dane: /api/ride-report/data. */
(function(){
"use strict";
var $=function(id){return document.getElementById(id);};
var V=function(x){return (x&&typeof x==="object"&&"value" in x)?x.value:x;};
var isNum=function(v){return typeof v==="number"&&isFinite(v);};
function n(v,d){return isNum(v)?v.toFixed(d==null?0:d):"—";}
function fmtT(t){if(!isNum(t))return "—";t=Math.round(t);var h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;return h+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");}
function fmtHM(t){if(!isNum(t))return "—";var m=Math.round(t/60);return Math.floor(m/60)+":"+String(m%60).padStart(2,"0");}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
async function getJSON(u){var r=await fetch(u+(u.indexOf("?")>=0?"&":"?")+"_="+Date.now(),{credentials:"same-origin",cache:"no-store"});if(!r.ok)throw new Error(r.status+" "+u);return r.json();}
function zoneCol(pw,ftp){if(!isNum(pw)||!ftp)return "#9a9a9a";var f=pw/ftp;return f<0.55?"#85b7eb":f<0.75?"#97c459":f<0.9?"#fac775":f<1.05?"#f09595":"#e24b4a";}
function hrCol(hr){if(!isNum(hr))return "#9a9a9a";return hr<107?"#85b7eb":hr<119?"#97c459":hr<125?"#fac775":hr<140?"#f09595":"#e24b4a";}
function wbCol(w){if(!isNum(w))return "#9a9a9a";return w>75?"#85b7eb":w>50?"#97c459":w>30?"#fac775":w>15?"#f09595":"#e24b4a";}
function tempCol(t,lo,hi){if(!isNum(t))return "#9a9a9a";var f=(t-lo)/((hi-lo)||1);return f<0.25?"#85b7eb":f<0.5?"#97c459":f<0.75?"#fac775":"#e24b4a";}
function windCol(tail){if(!isNum(tail))return "#9a9a9a";return tail<-2?"#e24b4a":tail<-0.7?"#f09595":tail<0.7?"#9a9a9a":tail<2?"#97c459":"#639922";}
var LEG={pw:[["#85b7eb","spokojnie"],["#97c459","wytrzymałość"],["#fac775","tempo"],["#f09595","próg"],["#e24b4a","na maksa"]],hr:[["#85b7eb","Z1"],["#97c459","Z2"],["#fac775","Z3"],["#f09595","Z4"],["#e24b4a","Z5"]],wb:[["#85b7eb",">75%"],["#97c459","50–75%"],["#fac775","30–50%"],["#f09595","15–30%"],["#e24b4a","<15%"]],temp:[["#85b7eb","chłodno"],["#97c459",""],["#fac775",""],["#e24b4a","gorąco"]],wind:[["#e24b4a","mocno w twarz"],["#f09595","w twarz"],["#9a9a9a","bok / cisza"],["#97c459","w plecy"],["#639922","mocno w plecy"]]};

var D=null,TR=null,N=0,FTP=null,RKEY=null,map=null,segs=[],casing=null,dot=null,halo=null,mode="pw",bw=true,idx=0,playing=false,speed=30,last=null,raf=null,MOM=[],SPD=[],GR=[],PWS=[];
var LANES={alt:true,pw:true,wb:true,spd:false,cad:false,temp:false,wind:false},XM="km",SEL=null,CMP=[];

/* ---------- lista jazd ---------- */
async function loadRides(){
  var sel=$("ridesel");
  try{
    var j=await getJSON("/api/rides/ready");var rides=j.rides||j||[];
    sel.innerHTML="";
    rides.forEach(function(r){var o=document.createElement("option");o.value=r.ride_key;o.textContent=(r.date||"")+" "+(r.time||"")+" · "+(r.name||r.ride_key)+(r.has_report?"":" (bez raportu)");o.dataset.name=r.name||"";o.dataset.date=r.date||"";o.dataset.time=r.time||"";o.dataset.sport=r.sport||"";sel.appendChild(o);});
    var q=new URLSearchParams(location.search).get("ride");
    if(q&&rides.some(function(r){return String(r.ride_key)===q;}))sel.value=q;
    sel.onchange=function(){history.replaceState(null,"","?ride="+encodeURIComponent(sel.value));loadRide(sel.value);};
    if(sel.value)loadRide(sel.value);
  }catch(e){sel.innerHTML="<option>błąd listy jazd: "+esc(e.message)+"</option>";}
}
async function loadRide(key){
  $("loading").textContent="ładuję dane…";$("report").style.display="none";pause();SEL=null;
  try{D=await getJSON("/api/ride-report/data?ride="+encodeURIComponent(key));RKEY=key;$("loading").textContent="";render();}
  catch(e){$("loading").textContent="błąd: "+e.message;}
}

/* ---------- render ---------- */
function render(){
  var sel=$("ridesel"),opt=sel.options[sel.selectedIndex]||{dataset:{}};
  var L=D.load||{},ride=D.ride||{},ph=D.physio||{},en=D.energy||{},mq=D.modelq||{};
  FTP=V(L.ftp_w)||(mq.current&&mq.current.ftp_w)||null;
  TR=D.trace||{};N=(TR.km||[]).length;
  var dist=V(L.dist_km)||ride.dist_km;
  $("h-date").textContent=(ride.date||opt.dataset.date||"")+(ride.time?" · "+ride.time:"")+(opt.dataset.sport?" · "+opt.dataset.sport:"")+(FTP?" · próg "+FTP+" W":"");
  $("h-title").textContent=opt.dataset.name||D.ride_key;
  var xss=V(L.xss),iff=V(L.if);var word=!isNum(iff)?"":iff>0.9?"Bardzo mocna jazda":iff>0.8?"Mocna jazda":iff>0.7?"Solidna jazda":"Spokojna jazda";
  var pill=$("h-pill");pill.style.display="";pill.className="pill "+(iff>0.8?"good":"");pill.textContent=word+(isNum(xss)?" · obciążenie "+Math.round(xss):"");
  var asc=ascent(TR.alt||[]);
  var np=V(L.np_w),avg=V(L.avg_p_w),hra=V(ph.hr_avg),hrm=V(ph.hr_max),zh=V(L.zones_hr_pct)||[],z23=(zh[1]||0)+(zh[2]||0);
  var kj=V(en.work_kj)||V(L.kj);
  $("k5").innerHTML=[
    card5("Dystans",isNum(dist)?n(dist,1)+" km":"—",isNum(asc)?Math.round(asc)+" m w górę":""),
    card5("Czas",fmtHM(V(L.dur_moving_s)),isNum(V(L.dur_elapsed_s))?fmtHM(V(L.dur_elapsed_s))+" z postojami":""),
    card5("Moc",isNum(avg)?Math.round(avg)+" W":"—",(isNum(np)?"znormalizowana "+Math.round(np):"")+(isNum(np)&&FTP?" · "+Math.round(np/FTP*100)+"% progu":"")),
    card5("Tętno",isNum(hra)?Math.round(hra):"—",(isNum(hrm)?"max "+Math.round(hrm):"")+(z23?" · "+Math.round(z23)+"% w strefie 2–3":"")),
    card5("Energia",isNum(kj)?Math.round(kj)+" kJ":"—",isNum(kj)?"≈ "+Math.round(kj)+" kcal spalone":"")
  ].join("");
  $("report").style.display="";
  derive();buildMap();buildMoments();drawChart();buildInsights();buildSections();
  var dis=D.disabled||[];$("disabled").innerHTML=dis.length?'<div class="warnbox">Bez danych w tej jeździe: '+dis.map(function(x){return esc(x.blok)+(x.powod?" ("+esc(x.powod)+")":"");}).join(" · ")+"</div>":"";
  if(map)setTimeout(function(){map.invalidateSize();},50);
  seek(0);
}
function card5(l,v,s){return '<div class="card tight"><p class="lbl">'+l+'</p><div class="mid" style="margin-top:4px">'+v+'</div><div class="delta">'+(s||"&nbsp;")+'</div></div>';}
function ascent(A){var a=0;for(var i=1;i<A.length;i++){if(isNum(A[i])&&isNum(A[i-1])){var d=A[i]-A[i-1];if(d>0.3)a+=d;}}return A.length?a:null;}
function derive(){
  var km=TR.km||[],t=TR.t||[],A=TR.alt||[],P=TR.power||[];SPD=[];GR=[];PWS=[];
  for(var i=0;i<N;i++){
    var dk=i?(km[i]-km[i-1]):0,dtm=i?((t[i]-t[i-1])||TR.window_s||10):1;
    SPD.push(isNum(dk)&&dtm>0?Math.max(0,dk/dtm*3600):null);
    var da=i&&isNum(A[i])&&isNum(A[i-1])?A[i]-A[i-1]:0;
    GR.push(isNum(dk)&&dk>0.005?Math.max(-20,Math.min(25,da/(dk*1000)*100)):0);
    var s=0,c=0;for(var j=Math.max(0,i-1);j<=Math.min(N-1,i+1);j++){if(isNum(P[j])){s+=P[j];c++;}}PWS.push(c?s/c:null);
  }
}

/* ---------- mapa ---------- */
function buildMap(){
  var lat=TR.lat||[],lon=TR.lon||[];
  if(!map){map=L.map("map",{zoomControl:true,attributionControl:false});L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19}).addTo(map);applyBW();
    $("bwbtn").onclick=function(){bw=!bw;applyBW();};}
  segs.forEach(function(s){map.removeLayer(s);});segs=[];if(casing){map.removeLayer(casing);casing=null;}if(dot){map.removeLayer(dot);map.removeLayer(halo);dot=null;}
  var pts=[];for(var i=0;i<N;i++)if(isNum(lat[i])&&isNum(lon[i]))pts.push([lat[i],lon[i]]);
  if(!pts.length)return;
  casing=L.polyline(pts,{color:"#111",weight:9,opacity:.8}).addTo(map);
  drawTrack();
  map.fitBounds(L.polyline(pts).getBounds(),{padding:[16,16]});
  halo=L.circleMarker(pts[0],{radius:15,color:"#e8742a",weight:0,fillOpacity:.3}).addTo(map);
  dot=L.circleMarker(pts[0],{radius:8,color:"#fff",weight:2.5,fillColor:"#e8742a",fillOpacity:1}).addTo(map);
}
function applyBW(){var tp=map.getPane("tilePane");if(tp)tp.style.filter=bw?"grayscale(1) contrast(.95) brightness(1.05)":"";$("bwbtn").textContent=bw?"Mapa: kolor":"Mapa: B/W";}
function drawTrack(){
  segs.forEach(function(s){map.removeLayer(s);});segs=[];
  var lat=TR.lat,lon=TR.lon,tmin=Infinity,tmax=-Infinity;(TR.temp||[]).forEach(function(v){if(isNum(v)){tmin=Math.min(tmin,v);tmax=Math.max(tmax,v);}});
  var colAt=function(i){return mode==="pw"?zoneCol(PWS[i],FTP):mode==="hr"?hrCol(TR.hr[i]):mode==="wb"?wbCol(TR.wbal_pct&&TR.wbal_pct[i]):mode==="temp"?tempCol(TR.temp&&TR.temp[i],tmin,tmax):windCol(TR.tail&&TR.tail[i]);};
  var cur=null,pts=[],col=null;
  var flush=function(){if(pts.length>1)segs.push(L.polyline(pts,{color:col,weight:5,opacity:1}).addTo(map));};
  for(var i=0;i<N;i++){if(!isNum(lat[i])||!isNum(lon[i]))continue;var c=colAt(i);if(c!==col){flush();pts=cur?[cur]:[];col=c;}cur=[lat[i],lon[i]];pts.push(cur);}
  flush();if(dot){dot.bringToFront();}
  var lg=LEG[mode]||[];$("tracklegend").innerHTML='<span class="muted">ślad:</span>'+lg.map(function(x){return '<span><i class="sw" style="background:'+x[0]+'"></i>'+x[1]+'</span>';}).join("")+(mode==="temp"&&isFinite(tmin)?'<span class="muted">'+n(tmin,0)+'–'+n(tmax,0)+' °C</span>':"");
}

/* ---------- odtwarzanie ---------- */
function seek(i){
  if(!N)return;idx=Math.max(0,Math.min(N-1,i));var k=Math.round(idx);
  var la=TR.lat[k],lo=TR.lon[k];
  if(isNum(la)&&isNum(lo)&&dot){dot.setLatLng([la,lo]);halo.setLatLng([la,lo]);if(!map.getBounds().pad(-0.15).contains([la,lo]))map.panTo([la,lo]);}
  var pw=PWS[k],hr=TR.hr[k],wb=TR.wbal_pct?TR.wbal_pct[k]:null,cad=TR.cad?TR.cad[k]:null,tp=TR.temp?TR.temp[k]:null,tl=TR.tail?TR.tail[k]:null;
  $("d-pw").innerHTML=n(pw)+" <small>W</small>";$("d-pw").style.color=zoneCol(pw,FTP);
  $("d-hr").innerHTML=n(hr)+" <small>bpm</small>";
  $("d-wb").innerHTML=n(wb)+"<small>%</small>";$("d-wbb").style.width=(isNum(wb)?wb:100)+"%";$("d-wbb").style.background=isNum(wb)&&wb<30?"#e24b4a":"var(--accent)";
  $("d-gr").textContent=(GR[k]>0?"+":"")+n(GR[k],1)+"% · "+n(SPD[k])+" km/h";
  $("d-cad").textContent=n(cad)+" · "+n(tp)+"° · "+(isNum(tl)?(tl>0?"+":"")+n(tl,1)+" m/s":"—");
  $("clock").textContent=fmtT(TR.t[k]-TR.t[0])+" / "+fmtT(TR.t[N-1]-TR.t[0])+" · km "+n(TR.km[k],1);
  var cur=$("chart").querySelector("#ccur");if(cur){var x=CX(k);cur.setAttribute("x1",x);cur.setAttribute("x2",x);}
  MOM.forEach(function(m){var on=Math.abs(m.i-idx)<Math.max(6,N*0.012);m.el.classList.toggle("on",on);m.card.classList.toggle("on",on);});
}
function tick(ts){if(!playing)return;if(last!=null){var dtw=TR.window_s||10;idx+=(ts-last)/1000*speed/dtw;if(idx>=N-1){idx=N-1;pause();}}last=ts;seek(idx);if(playing)raf=requestAnimationFrame(tick);}
function play(){if(!N)return;playing=true;last=null;$("play").textContent="❚❚";raf=requestAnimationFrame(tick);}
function pause(){playing=false;var b=$("play");if(b)b.textContent="▶";if(raf)cancelAnimationFrame(raf);}
$("play").onclick=function(){if(playing)pause();else{if(idx>=N-1)idx=0;play();}};
document.querySelectorAll(".spd").forEach(function(b){b.onclick=function(){speed=+b.dataset.s;document.querySelectorAll(".spd").forEach(function(x){x.classList.toggle("on",x===b);});};});
$("trackmode").onchange=function(e){mode=e.target.value;if(map)drawTrack();};

/* ---------- momenty ---------- */
function buildMoments(){
  MOM=[];var mks=$("mks"),moms=$("moms");mks.innerHTML="";moms.innerHTML="";if(!N)return;
  var win=TR.window_s||10,w5=Math.max(1,Math.round(300/win)),P=TR.power,km=TR.km,A=TR.alt;
  var best=null,run=0;for(var i=0;i<N;i++){if(isNum(SPD[i])&&SPD[i]<1.5)run++;else{if(run*win>=60&&(!best||run>best.len))best={len:run,i:i-run};run=0;}}
  if(best)MOM.push({i:best.i,j:best.i+best.len,lab:"⏸ postój "+Math.round(best.len*win/60)+" min",t:"Najdłuższy postój",s:"km "+n(km[best.i],0)+" · "+Math.round(best.len*win/60)+" min"});
  var bs=-1,bi=0;for(i=0;i+w5<=N;i++){var s=0,c=0;for(var j=0;j<w5;j++){if(isNum(P[i+j])){s+=P[i+j];c++;}}if(c===w5&&s>bs){bs=s;bi=i;}}
  if(bs>0)MOM.push({i:bi+w5/2,a:bi,b:bi+w5,lab:"⚡ 5 min "+Math.round(bs/w5)+" W",t:"Najmocniejsze 5 min",s:"km "+n(km[bi],0)+"–"+n(km[Math.min(N-1,bi+w5)],0)+" · "+Math.round(bs/w5)+" W"+(FTP?" · "+Math.round(bs/w5/FTP*100)+"% progu":"")});
  if(TR.wbal_pct){var mi=-1;for(i=0;i<N;i++)if(isNum(TR.wbal_pct[i])&&(mi<0||TR.wbal_pct[i]<TR.wbal_pct[mi]))mi=i;
    if(mi>=0){var rec=null;for(j=mi;j<N;j++)if(TR.wbal_pct[j]>=50){rec=(TR.t[j]-TR.t[mi])/60;break;}
    MOM.push({i:mi,lab:"▼ zapas "+Math.round(TR.wbal_pct[mi])+"%",t:"Najgłębszy zapas na zrywy",s:"km "+n(km[mi],0)+" · "+Math.round(TR.wbal_pct[mi])+"%"+(rec!=null?" · do 50% po "+Math.round(rec)+" min":"")});}}
  var wC=Math.round(900/win),bg=0,bgi=0,bgj=0;for(i=0;i<N;i++){for(j=i+1;j<Math.min(N,i+wC);j++){if(isNum(A[j])&&isNum(A[i])){var g=A[j]-A[i];if(g>bg){bg=g;bgi=i;bgj=j;}}}}
  if(bg>30){var dk=km[bgj]-km[bgi];MOM.push({i:(bgi+bgj)/2,a:bgi,b:bgj,lab:"⛰ +"+Math.round(bg)+" m",t:"Największy podjazd",s:"km "+n(km[bgi],0)+" · "+n(dk,1)+" km · "+n(bg/(dk*1000)*100,1)+"% · "+Math.round(bg)+" m"});}
  var ms=0;for(i=0;i<N;i++)if(isNum(SPD[i])&&SPD[i]>SPD[ms])ms=i;
  if(SPD[ms]>25)MOM.push({i:ms,lab:"↓ "+Math.round(SPD[ms])+" km/h",t:"Najszybszy moment",s:"km "+n(km[ms],0)+" · "+Math.round(SPD[ms])+" km/h"});
  MOM.sort(function(a,b){return a.i-b.i;});
  moms.style.gridTemplateColumns="repeat("+Math.min(4,Math.max(1,MOM.length))+",minmax(0,1fr))";
  MOM.forEach(function(m){var a=document.createElement("span");a.className="mk";a.textContent=m.lab;a.style.left=(m.i/(N-1)*100)+"%";
    a.onclick=function(){pause();seek(m.i);if(m.a!=null){SEL={a:m.a,b:m.b};drawChart();showSeg();}};mks.appendChild(a);m.el=a;
    var c=document.createElement("div");c.className="card tight mo";c.innerHTML="<b>"+esc(m.t)+"</b><span class='sub'>"+esc(m.s)+"</span>";c.onclick=a.onclick;moms.appendChild(c);m.card=c;});
}

/* ---------- wykres w pasach ---------- */
var CW=1000,ML=46,MR=46,PW=CW-ML-MR,CH=300,LANE_H={alt:90,pw:120,wb:60,spd:60,cad:60,temp:60,wind:60},LANE_Y={};
function xval(i){return XM==="km"?TR.km[i]:(TR.t[i]-TR.t[0]);}
function CX(i){var x0=xval(0),x1=xval(N-1);return ML+((xval(i)-x0)/((x1-x0)||1))*PW;}
function iAtX(px){var x0=xval(0),x1=xval(N-1),v=x0+(px-ML)/PW*(x1-x0);var lo=0,hi=N-1;while(lo<hi){var m=(lo+hi)>>1;if(xval(m)<v)lo=m+1;else hi=m;}return Math.max(0,Math.min(N-1,lo));}
function drawChart(){
  var svg=$("chart");if(!N){svg.innerHTML="";return;}
  var lanes=Object.keys(LANES).filter(function(k){return LANES[k];});var y=8;LANE_Y={};
  lanes.forEach(function(k){LANE_Y[k]=y;y+=LANE_H[k]+10;});CH=y+16;svg.setAttribute("viewBox","0 0 "+CW+" "+CH);
  var P=[],i;
  /* siatka x */
  var x0=xval(0),x1=xval(N-1),span=x1-x0,steps=XM==="km"?[1,2,5,10,20,25,50]:[300,600,900,1800,3600,7200],st=steps.find(function(s){return span/s<=10;})||steps[steps.length-1];
  for(var v=Math.ceil(x0/st)*st;v<=x1;v+=st){var gx=ML+((v-x0)/(span||1))*PW;P.push('<line x1="'+gx.toFixed(1)+'" y1="4" x2="'+gx.toFixed(1)+'" y2="'+(CH-14)+'" stroke="var(--line)" stroke-width="1"/><text x="'+gx.toFixed(1)+'" y="'+(CH-3)+'" font-size="11" fill="var(--muted)" text-anchor="middle">'+(XM==="km"?v:fmtHM(v))+'</text>');}
  var lab=function(k,txt){P.push('<text x="4" y="'+(LANE_Y[k]+11)+'" font-size="11" fill="var(--muted)">'+txt+'</text>');};
  var mm=function(arr){var lo=Infinity,hi=-Infinity;for(var q=0;q<N;q++){var z=arr[q];if(isNum(z)){if(z<lo)lo=z;if(z>hi)hi=z;}}if(!isFinite(lo)){lo=0;hi=1;}if(hi===lo)hi=lo+1;return [lo,hi];};
  var line=function(arr,k,lo,hi,col,w){var d="",pen=false;for(var q=0;q<N;q++){var z=arr[q];if(!isNum(z)){pen=false;continue;}var yy=LANE_Y[k]+LANE_H[k]-((z-lo)/(hi-lo))*LANE_H[k];d+=(pen?" L":" M")+CX(q).toFixed(1)+" "+yy.toFixed(1);pen=true;}P.push('<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="'+(w||1.6)+'"/>');};
  var area=function(arr,k,lo,hi,fill,op){var base=LANE_Y[k]+LANE_H[k],d="M"+CX(0).toFixed(1)+" "+base;for(var q=0;q<N;q++){var z=arr[q];if(!isNum(z))z=lo;var yy=base-((z-lo)/(hi-lo))*LANE_H[k];d+=" L"+CX(q).toFixed(1)+" "+yy.toFixed(1);}d+=" L"+CX(N-1).toFixed(1)+" "+base+" Z";P.push('<path d="'+d+'" fill="'+fill+'" opacity="'+(op||1)+'"/>');};
  var axr=function(k,lo,hi,col){P.push('<text x="'+(CW-4)+'" y="'+(LANE_Y[k]+11)+'" font-size="10" fill="'+col+'" text-anchor="end">'+Math.round(hi)+'</text><text x="'+(CW-4)+'" y="'+(LANE_Y[k]+LANE_H[k])+'" font-size="10" fill="'+col+'" text-anchor="end">'+Math.round(lo)+'</text>');};
  var axl=function(k,lo,hi,col){P.push('<text x="'+(ML-4)+'" y="'+(LANE_Y[k]+LANE_H[k])+'" font-size="10" fill="'+col+'" text-anchor="end">'+Math.round(lo)+'</text><text x="'+(ML-4)+'" y="'+(LANE_Y[k]+LANE_H[k]/2+4)+'" font-size="10" fill="'+col+'" text-anchor="end">'+Math.round((lo+hi)/2)+'</text>');};
  lanes.forEach(function(k){
    P.push('<line x1="'+ML+'" y1="'+(LANE_Y[k]+LANE_H[k])+'" x2="'+(CW-MR)+'" y2="'+(LANE_Y[k]+LANE_H[k])+'" stroke="var(--line2)" stroke-width="1"/>');
    if(k==="alt"){var r=mm(TR.alt);area(TR.alt,k,r[0],r[1],"var(--well)");line(TR.alt,k,r[0],r[1],"var(--ink2)",1.2);lab(k,"wysokość m");axl(k,r[0],r[1],"var(--muted)");}
    if(k==="pw"){var pr=mm(PWS);pr[0]=0;pr[1]=Math.max(pr[1],FTP?FTP*1.3:300);var base=LANE_Y[k]+LANE_H[k];
      for(i=0;i<N-1;i++){var z=PWS[i];if(!isNum(z))continue;var hh=(z/pr[1])*LANE_H[k],xa=CX(i),xb=CX(i+1);P.push('<rect x="'+xa.toFixed(1)+'" y="'+(base-hh).toFixed(1)+'" width="'+Math.max(0.6,xb-xa).toFixed(1)+'" height="'+hh.toFixed(1)+'" fill="'+zoneCol(z,FTP)+'"/>');}
      if(FTP){var fy=base-(FTP/pr[1])*LANE_H[k];P.push('<line x1="'+ML+'" y1="'+fy.toFixed(1)+'" x2="'+(CW-MR)+'" y2="'+fy.toFixed(1)+'" stroke="var(--ink)" stroke-width="1" stroke-dasharray="4 3" opacity=".6"/><text x="'+(ML+3)+'" y="'+(fy-3).toFixed(1)+'" font-size="10" fill="var(--ink2)">próg '+FTP+' W</text>');}
      var hr=mm(TR.hr);hr[0]=Math.min(hr[0],90);hr[1]=Math.max(hr[1],170);line(TR.hr,k,hr[0],hr[1],"#a32d2d",1.8);lab(k,"moc W  ·  tętno");axl(k,0,pr[1],"var(--muted)");axr(k,hr[0],hr[1],"#a32d2d");}
    if(k==="wb"&&TR.wbal_pct){area(TR.wbal_pct,k,0,100,"#afa9ec",.55);line(TR.wbal_pct,k,0,100,"#534ab7",1.5);lab(k,"zapas na zrywy %");axl(k,0,100,"#534ab7");}
    if(k==="spd"){var sr=mm(SPD);sr[0]=0;area(SPD,k,sr[0],sr[1],"#85b7eb",.35);line(SPD,k,sr[0],sr[1],"#185fa5",1.4);lab(k,"prędkość km/h");axl(k,sr[0],sr[1],"#185fa5");}
    if(k==="cad"&&TR.cad){line(TR.cad,k,40,120,"#0f6e56",1.4);lab(k,"kadencja");axl(k,40,120,"#0f6e56");}
    if(k==="temp"&&TR.temp){var tr=mm(TR.temp);tr[0]=Math.floor(tr[0]-1);tr[1]=Math.ceil(tr[1]+1);line(TR.temp,k,tr[0],tr[1],"#ba7517",1.6);lab(k,"temperatura °C");axl(k,tr[0],tr[1],"#ba7517");}
    if(k==="wind"&&TR.tail){var wr=mm(TR.tail),wm=Math.max(0.5,Math.abs(wr[0]),Math.abs(wr[1])),mid=LANE_Y[k]+LANE_H[k]/2;
      for(i=0;i<N-1;i++){var tl=TR.tail[i];if(!isNum(tl))continue;var h2=Math.abs(tl)/wm*LANE_H[k]/2,xa2=CX(i),xb2=CX(i+1);P.push('<rect x="'+xa2.toFixed(1)+'" y="'+(tl>0?mid-h2:mid).toFixed(1)+'" width="'+Math.max(0.6,xb2-xa2).toFixed(1)+'" height="'+h2.toFixed(1)+'" fill="'+(tl>0?"#639922":"#e24b4a")+'"/>');}
      P.push('<line x1="'+ML+'" y1="'+mid+'" x2="'+(CW-MR)+'" y2="'+mid+'" stroke="var(--muted)" stroke-width="1"/>');lab(k,"wiatr: w plecy ▲ / w twarz ▼  m/s");axl(k,-wm,wm,"var(--muted)");}
  });
  if(SEL){var sa=CX(SEL.a),sb=CX(SEL.b);P.push('<rect x="'+Math.min(sa,sb).toFixed(1)+'" y="2" width="'+Math.abs(sb-sa).toFixed(1)+'" height="'+(CH-16)+'" fill="var(--accent)" opacity=".16"/><line x1="'+sa+'" y1="2" x2="'+sa+'" y2="'+(CH-16)+'" stroke="var(--accent)" stroke-width="1.5"/><line x1="'+sb+'" y1="2" x2="'+sb+'" y2="'+(CH-16)+'" stroke="var(--accent)" stroke-width="1.5"/>');}
  P.push('<line id="ccur" x1="'+CX(Math.round(idx))+'" y1="2" x2="'+CX(Math.round(idx))+'" y2="'+(CH-14)+'" stroke="var(--accent)" stroke-width="2"/>');
  P.push('<line id="hcur" x1="0" y1="2" x2="0" y2="'+(CH-14)+'" stroke="var(--ink)" stroke-width="1" opacity="0"/>');
  svg.innerHTML=P.join("");
}
(function wireChart(){
  var svg=$("chart"),tip=$("tip"),down=null,moved=false;
  var px=function(e){var r=svg.getBoundingClientRect();return (e.clientX-r.left)/r.width*CW;};
  svg.addEventListener("pointerdown",function(e){if(!N)return;down=px(e);moved=false;svg.setPointerCapture(e.pointerId);});
  svg.addEventListener("pointermove",function(e){if(!N)return;var x=px(e),k=iAtX(x);
    var h=svg.querySelector("#hcur");if(h){h.setAttribute("x1",CX(k));h.setAttribute("x2",CX(k));h.setAttribute("opacity",".5");}
    tip.style.display="block";var r=svg.getBoundingClientRect();var lx=(CX(k)/CW)*r.width;tip.style.left=(lx+(lx>r.width*0.6?-12:12))+"px";tip.style.transform=lx>r.width*0.6?"translateX(-100%)":"";tip.style.top="8px";
    tip.innerHTML="km "+n(TR.km[k],1)+" · "+fmtT(TR.t[k]-TR.t[0])+"<br>moc <b>"+n(PWS[k])+" W</b> · tętno <b>"+n(TR.hr[k])+"</b><br>"+(TR.wbal_pct?"zapas "+n(TR.wbal_pct[k])+"% · ":"")+"wys. "+n(TR.alt[k])+" m · "+(GR[k]>0?"+":"")+n(GR[k],1)+"%<br>"+n(SPD[k])+" km/h · kad. "+n(TR.cad&&TR.cad[k])+(TR.temp?" · "+n(TR.temp[k])+"°":"")+(TR.tail?" · wiatr "+(TR.tail[k]>0?"+":"")+n(TR.tail[k],1):"");
    if(down!=null){if(Math.abs(x-down)>6){moved=true;SEL={a:iAtX(Math.min(down,x)),b:iAtX(Math.max(down,x))};drawChart();}}
  });
  svg.addEventListener("pointerup",function(e){if(!N)return;var x=px(e);if(down!=null&&!moved){pause();seek(iAtX(x));}else if(moved){showSeg();}down=null;moved=false;});
  svg.addEventListener("pointerleave",function(){tip.style.display="none";var h=svg.querySelector("#hcur");if(h)h.setAttribute("opacity","0");});
  document.querySelectorAll(".lanechk input").forEach(function(c){c.onchange=function(){LANES[c.dataset.lane]=c.checked;drawChart();};});
  document.querySelectorAll("#chartcard .seg button").forEach(function(b){b.onclick=function(){XM=b.dataset.x;document.querySelectorAll("#chartcard .seg button").forEach(function(x){x.classList.toggle("on",x===b);});drawChart();};});
})();

/* ---------- odcinek ---------- */
function segStats(a,b){
  var st=function(arr){var s=0,c=0,mn=Infinity,mx=-Infinity;for(var i=a;i<=b;i++){var v=arr&&arr[i];if(!isNum(v))continue;s+=v;c++;if(v<mn)mn=v;if(v>mx)mx=v;}return c?{avg:s/c,min:mn,max:mx}:null;};
  var asc=0;for(var i=a+1;i<=b;i++){if(isNum(TR.alt[i])&&isNum(TR.alt[i-1])){var d=TR.alt[i]-TR.alt[i-1];if(d>0.3)asc+=d;}}
  return {km:TR.km[b]-TR.km[a],t:TR.t[b]-TR.t[a],pw:st(TR.power),hr:st(TR.hr),wb:st(TR.wbal_pct),spd:st(SPD),cad:st(TR.cad),temp:st(TR.temp),tail:st(TR.tail),asc:asc,gr:TR.km[b]>TR.km[a]?(TR.alt[b]-TR.alt[a])/((TR.km[b]-TR.km[a])*1000)*100:0};
}
function segDesc(a,b,S){var L=["Zakres: km "+n(TR.km[a],1)+"–"+n(TR.km[b],1)+" ("+fmtHM(S.t)+", "+n(S.km,1)+" km, +"+Math.round(S.asc)+" m)"];
  if(S.pw)L.push("moc: śr "+Math.round(S.pw.avg)+" W (max "+Math.round(S.pw.max)+")"+(FTP?", próg "+FTP:""));if(S.hr)L.push("HR: śr "+Math.round(S.hr.avg)+" (max "+Math.round(S.hr.max)+")");if(S.cad)L.push("kadencja: śr "+Math.round(S.cad.avg));if(S.wb)L.push("W'bal: min "+Math.round(S.wb.min)+"%");if(S.spd)L.push("prędkość: śr "+n(S.spd.avg,1)+" km/h");if(S.temp)L.push("temperatura: "+Math.round(S.temp.min)+"–"+Math.round(S.temp.max)+" °C");if(S.tail)L.push("wiatr wzdłuż: śr "+n(S.tail.avg,1)+" m/s ("+(S.tail.avg<0?"pod wiatr":"z plecami")+")");return L.join("; ");}
function showSeg(){
  var p=$("segpanel");if(!SEL){p.style.display="none";return;}var a=SEL.a,b=SEL.b,S=segStats(a,b);
  var g=function(l,v){return '<div><p class="lbl">'+l+'</p><div class="v">'+v+'</div></div>';};
  p.style.display="";p.className="segpanel";
  p.innerHTML='<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap"><b style="font-size:16px">Odcinek km '+n(TR.km[a],1)+' – '+n(TR.km[b],1)+'</b><span class="sub">'+fmtHM(S.t)+' · '+n(S.km,1)+' km · +'+Math.round(S.asc)+' m · śr. nachylenie '+n(S.gr,1)+'%</span></div>'
   +'<div class="sg">'+g("moc śr. / maks.",(S.pw?Math.round(S.pw.avg)+" / "+Math.round(S.pw.max)+" W":"—"))+g("% progu",(S.pw&&FTP?Math.round(S.pw.avg/FTP*100)+"%":"—"))+g("tętno śr. / maks.",(S.hr?Math.round(S.hr.avg)+" / "+Math.round(S.hr.max):"—"))+g("zapas min.",(S.wb?Math.round(S.wb.min)+"%":"—"))+g("prędkość śr.",(S.spd?n(S.spd.avg,1)+" km/h":"—"))+g("kadencja śr.",(S.cad?Math.round(S.cad.avg):"—"))+(S.tail?g("wiatr wzdłuż",(S.tail.avg>0?"+":"")+n(S.tail.avg,1)+" m/s"):"")+'</div>'
   +'<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn pri" id="segai" type="button">Komentarz AI o odcinku</button><button class="btn" id="segcmp" type="button">Dodaj do porównania</button><button class="btn" id="segclr" type="button">Wyczyść</button></div><div id="segaiout"></div>';
  $("segclr").onclick=function(){SEL=null;drawChart();showSeg();};
  $("segcmp").onclick=function(){CMP.push({a:a,b:b,S:S,name:$("h-title").textContent});showCmp();};
  $("segai").onclick=function(){var out=$("segaiout");out.innerHTML='<div class="ai">Analizuję odcinek…</div>';var desc=segDesc(a,b,S);
    fetch("/api/ride-report/correlate",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({live:desc,ride:RKEY})}).then(function(r){return r.json().catch(function(){return null;}).then(function(j){return {r:r,j:j};});}).then(function(o){out.innerHTML='<div class="ai">'+esc((o.j&&o.j.text)?o.j.text:"(błąd: "+((o.j&&o.j.detail)||o.r.status)+")")+'</div>';}).catch(function(){out.innerHTML='<div class="ai">Błąd połączenia z AI.</div>';});};
}
function showCmp(){var p=$("cmppanel");if(!CMP.length){p.style.display="none";return;}p.style.display="";p.className="segpanel";
  var rows=[["odcinek",function(c){return esc(c.name.slice(0,18))+" km "+n(TR.km[c.a],0)+"–"+n(TR.km[c.b],0);}],["czas",function(c){return fmtHM(c.S.t);}],["dystans",function(c){return n(c.S.km,1)+" km";}],["w górę",function(c){return Math.round(c.S.asc)+" m";}],["moc śr.",function(c){return c.S.pw?Math.round(c.S.pw.avg)+" W":"—";}],["tętno śr.",function(c){return c.S.hr?Math.round(c.S.hr.avg):"—";}],["moc / tętno",function(c){return c.S.pw&&c.S.hr?n(c.S.pw.avg/c.S.hr.avg,2):"—";}],["prędkość",function(c){return c.S.spd?n(c.S.spd.avg,1)+" km/h":"—";}],["zapas min.",function(c){return c.S.wb?Math.round(c.S.wb.min)+"%":"—";}]];
  p.innerHTML='<div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:16px">Porównanie odcinków</b><button class="btn" id="cmpclr" type="button">Wyczyść</button></div><div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:14px;margin-top:8px;min-width:100%">'+rows.map(function(r,ri){return '<tr style="border-top:1px solid var(--line)"><td style="padding:5px 10px 5px 0;color:var(--ink2)">'+r[0]+'</td>'+CMP.map(function(c){return '<td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;'+(ri===0?'font-weight:600':'')+'">'+r[1](c)+'</td>';}).join("")+'</tr>';}).join("")+'</table></div><div class="sub" style="margin-top:6px;font-size:13px">Odcinki z tej jazdy; porównanie między jazdami — w następnym kroku.</div>';
  $("cmpclr").onclick=function(){CMP=[];showCmp();};}

/* ---------- wnioski ---------- */
function buildInsights(){
  var out=[],L=D.load||{},wp=D.wprime||{},wi=V(D.wind)||{},sf=V(D.surface)||{},dt=D.drivetrain||{},ph=D.physio||{},mq=D.modelq||{},nu=V(D.nutrition)||{};
  var iff=V(L.if),vi=V(L.vi);
  if(isNum(iff))out.push(["I",(iff>0.9?"Bardzo intensywna jazda":iff>0.8?"Intensywna jazda":iff>0.7?"Jazda w tempie":"Spokojna jazda")+" — intensywność "+n(iff,2)+(isNum(vi)?", "+(vi>1.15?"bardzo szarpana":vi>1.05?"szarpana":"równa")+" (równość "+n(vi,2)+")":"")+"."]);
  var wmin=V(wp.wbal_min_pct),lt25=V(wp.time_lt25_min);
  if(isNum(wmin))out.push(["W′","Zapas na zrywy spadł najniżej do <b>"+Math.round(wmin)+"%</b>"+(isNum(lt25)&&lt25>0?"; poniżej 25% byłeś łącznie "+Math.round(lt25)+" min":"")+"."]);
  if(isNum(wi.avg_tail_ms)){var a=wi.avg_tail_ms;out.push(["≋",a<-1?"Wiatr przeważnie w twarz — średnio "+n(-a,1)+" m/s czołowego.":a>1?"Wiatr przeważnie w plecy — średnio "+n(a,1)+" m/s pomagał.":"Wiatr bez wyraźnego kierunku względem trasy (średnio "+n(a,1)+" m/s)."]);}
  var tp=sf.types_pct;if(tp&&typeof tp==="object"){var top=Object.keys(tp).sort(function(x,y){return tp[y]-tp[x];})[0];if(top&&tp[top]>0)out.push(["▤",Math.round(tp[top])+"% dystansu: "+esc(top)+(isNum(sf.unknown_pct)&&sf.unknown_pct>20?" · "+Math.round(sf.unknown_pct)+"% nawierzchni nieznanej":"")+"."]);}
  var dec=V(ph.decoupling_pct);if(isNum(dec))out.push(["♥",Math.abs(dec)>5?"Tętno odjechało od mocy o "+n(dec,1)+"% w drugiej połowie — zmęczenie, ciepło lub odwodnienie.":"Tętno trzymało się mocy przez całą jazdę ("+n(dec,1)+"%) — dobra wytrzymałość."]);
  var cog=V(dt.cog_time_pct);if(cog&&typeof cog==="object"){var tc=Object.keys(cog).sort(function(x,y){return cog[y]-cog[x];})[0];var grind=V(dt.grind_min);if(tc&&cog[tc]>0)out.push(["⚙","Najczęstsza zębatka: "+esc(tc)+" ("+Math.round(cog[tc])+"% czasu)"+(isNum(grind)&&grind>0?" · mielenie na ciężkim biegu "+Math.round(grind)+" min":"")+"."]);}
  var ri=mq.ride_impact;if(ri&&isNum(ri.ftp_delta)&&Math.abs(ri.ftp_delta)>=1)out.push(["Δ","Ta jazda "+(ri.ftp_delta>0?"podniosła":"obniżyła")+" szacunek mocy progowej o "+n(Math.abs(ri.ftp_delta),0)+" W."]);
  var dl=nu.daily;if(Array.isArray(dl)&&dl.length){var d0=dl[dl.length-1];var kc=d0.kcal||d0.kcal_in||d0.intake_kcal,pr=d0.protein_g||d0.prot_g;if(isNum(kc)||isNum(pr))out.push(["P","Jedzenie tego dnia: "+(isNum(kc)?Math.round(kc)+" kcal":"")+(isNum(pr)?" · białko "+Math.round(pr)+" g":"")+"."]);}
  $("insights").innerHTML=out.length?out.map(function(x){return '<div class="ins"><span class="ic">'+x[0]+'</span><span>'+x[1]+'</span></div>';}).join(""):'<div class="sub">Za mało danych na wnioski.</div>';
}
function buildSections(){
  var el=$("sections");
  el.innerHTML=window.__RJ2sections?window.__RJ2sections(D,{FTP:FTP,TR:TR,SPD:SPD}):'<div class="sub">Brak modułu sekcji.</div>';
  el.querySelectorAll(".sec").forEach(function(s){s.addEventListener("click",function(){s.classList.toggle("open");s.querySelector(".chev").textContent=s.classList.contains("open")?"⌄":"›";});});
  var first=el.querySelector(".sec");if(first){first.classList.add("open");first.querySelector(".chev").textContent="⌄";}
}
window.__RJ2={get D(){return D;},V:V,isNum:isNum,n:n,esc:esc,fmtHM:fmtHM,FTP:function(){return FTP;},SPD:function(){return SPD;},TR:function(){return TR;}};
loadRides();
})();
