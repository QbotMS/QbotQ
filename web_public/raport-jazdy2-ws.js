/* Raport z jazdy v2 -- przestrzen robocza: mapa-okno + wykres C zadokowany u dolu, kursor/zaznaczenie sprzezone z mapa. */
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
function zoneCol(pw,ftp){if(!isNum(pw)||!ftp)return "#9a9a9a";var f=pw/ftp;return f<0.55?"#6fa8dc":f<0.75?"#7fb24a":f<0.9?"#f3b53c":f<1.05?"#ef6e4a":"#c81e1e";}
function hrCol(hr){if(!isNum(hr))return "#9a9a9a";return hr<107?"#85b7eb":hr<119?"#97c459":hr<125?"#fac775":hr<140?"#f09595":"#e24b4a";}
function wbCol(w){if(!isNum(w))return "#9a9a9a";return w>75?"#85b7eb":w>50?"#97c459":w>30?"#fac775":w>15?"#f09595":"#e24b4a";}
function tempCol(t,lo,hi){if(!isNum(t))return "#9a9a9a";var f=(t-lo)/((hi-lo)||1);return f<0.25?"#85b7eb":f<0.5?"#97c459":f<0.75?"#fac775":"#e24b4a";}
function windCol(tail){if(!isNum(tail))return "#9a9a9a";return tail<-2?"#e24b4a":tail<-0.7?"#f09595":tail<0.7?"#9a9a9a":tail<2?"#97c459":"#639922";}
var LEG={pw:[["#85b7eb","spokojnie"],["#97c459","wytrzymałość"],["#fac775","tempo"],["#f09595","próg"],["#e24b4a","na maksa"]],hr:[["#85b7eb","Z1"],["#97c459","Z2"],["#fac775","Z3"],["#f09595","Z4"],["#e24b4a","Z5"]],wb:[["#85b7eb",">75%"],["#97c459","50–75"],["#fac775","30–50"],["#f09595","15–30"],["#e24b4a","<15%"]],temp:[["#85b7eb","chłodno"],["#e24b4a","gorąco"]],wind:[["#e24b4a","w twarz"],["#9a9a9a","bok"],["#639922","w plecy"]],surf:[["#1565c0","twarda"],["#2e7d32","dobry gravel"],["#8bc34a","zwykły gravel"],["#e07b1a","trudny"],["#c2452f","ryzyko"]],none:[["#e8742a","ślad"]]};

var D=null,TR=null,N=0,FTP=null,RKEY=null,map=null,segs=[],casing=null,hl=null,hlc=null,mk=null,mode="pw",bw=!document.documentElement.classList.contains("theme-dark"),SPD=[],GR=[],PWS=[];


/* ---------- lista i dane ---------- */
async function loadRides(){
  var sel=$("ridesel");
  try{var j=await getJSON("/api/rides/ready");var rides=j.rides||j||[];sel.innerHTML="";
    rides.forEach(function(r){var o=document.createElement("option");o.value=r.ride_key;o.textContent=(r.date||"")+" "+(r.time||"")+" · "+(r.name||r.ride_key);o.dataset.name=r.name||"";o.dataset.date=r.date||"";o.dataset.time=r.time||"";o.dataset.sport=r.sport||"";sel.appendChild(o);});
    var q=new URLSearchParams(location.search).get("ride");if(q&&rides.some(function(r){return String(r.ride_key)===q;}))sel.value=q;
    sel.onchange=function(){history.replaceState(null,"","?ride="+encodeURIComponent(sel.value));loadRide(sel.value);};
    if(sel.value)loadRide(sel.value);
  }catch(e){sel.innerHTML="<option>błąd listy: "+esc(e.message)+"</option>";$("empty").textContent="Nie mogę pobrać listy jazd.";}
}
async function loadRide(key){
  $("empty").style.display="";$("empty").textContent="ładuję jazdę…";SEL=null;VIEW=null;closeSeg();if(typeof anClose==="function")anClose();
  try{D=await getJSON("/api/ride-report/data?ride="+encodeURIComponent(key));RKEY=key;render();$("empty").style.display="none";}
  catch(e){$("empty").textContent="Błąd: "+e.message;}
}
function render(){
  var sel=$("ridesel"),opt=sel.options[sel.selectedIndex]||{dataset:{}};
  var L=D.load||{},ride=D.ride||{},ph=D.physio||{},mq=D.modelq||{},wp=D.wprime||{};
  FTP=V(L.ftp_w)||(mq.current&&mq.current.ftp_w)||null;LTHR=V(L.lthr_bpm)||LTHR;TR=D.trace||{};N=(TR.km||[]).length;
  $("h-title").textContent=opt.dataset.name||D.ride_key;
  $("h-date").textContent=(ride.date||opt.dataset.date||"")+(ride.time?" · "+ride.time:"")+(opt.dataset.sport?" · "+opt.dataset.sport:"")+(FTP?" · próg "+FTP+" W":"");
  var dist=V(L.dist_km)||ride.dist_km,asc=ascent(TR.alt||[]),np=V(L.np_w),avg=V(L.avg_p_w),hra=V(ph.hr_avg),xss=V(L.xss),iff=V(L.if),wmin=V(wp.wbal_min_pct);
  $("k5").innerHTML=k("dystans",n(dist,1)+" km",isNum(asc)?"+"+Math.round(asc)+" m":"")+k("czas",fmtHM(V(L.dur_moving_s)),isNum(V(L.dur_elapsed_s))?fmtHM(V(L.dur_elapsed_s))+" całk.":"")+(function(){var s=V(D.speed)||{};return k("prędkość",isNum(s.netto_kmh)?n(s.netto_kmh,1)+" km/h":"—",isNum(s.brutto_kmh)?"brutto "+n(s.brutto_kmh,1):"");})()+k("moc",n(avg)+" W",isNum(np)?"znorm. "+Math.round(np)+(FTP?" · "+Math.round(np/FTP*100)+"%":""):"")+k("tętno",n(hra),isNum(V(ph.hr_max))?"max "+V(ph.hr_max):"")+k("obciążenie",n(xss),isNum(iff)?"intens. "+n(iff,2):"")+k("zapas min.",isNum(wmin)?Math.round(wmin)+"%":"—",isNum(V(wp.time_lt25_min))&&V(wp.time_lt25_min)>0?"<25%: "+Math.round(V(wp.time_lt25_min))+" min":"");
  derive();SPDS=smooth(SPD,5);CADS=smooth(TR.cad||[],5);DEV=[];for(var q=0;q<N;q++){var c=TR.cad?TR.cad[q]:null,v=SPD[q];DEV.push(isNum(c)&&c>40&&isNum(v)&&v>3?v*1000/60/c:null);}DEV=smooth(DEV,3);buildMap();drawChart();buildMoments();if(VIEWM==="dane"||window.__RJ3)daneRender();loadSurface().then(function(){var has=SURF.some(function(x){return x;});$("surfchip").style.display=has?"":"none";var o=$("trackmode").querySelector('option[value="surf"]');if(o)o.disabled=!has;if(has){RIB.surf=true;$("surfchip").classList.add("on");drawChart();if(mode==="surf")drawTrack();}});
}
function k(l,v,s){return '<div><p class="lbl">'+l+'</p><div class="v">'+v+'</div><div class="s">'+(s||"&nbsp;")+'</div></div>';}
function ascent(A){var a=0;for(var i=1;i<A.length;i++){if(isNum(A[i])&&isNum(A[i-1])){var d=A[i]-A[i-1];if(d>0.3)a+=d;}}return A.length?a:null;}
function derive(){var km=TR.km||[],t=TR.t||[],A=TR.alt||[],P=TR.power||[];SPD=[];GR=[];PWS=[];
  for(var i=0;i<N;i++){var dk=i?(km[i]-km[i-1]):0,dtm=i?((t[i]-t[i-1])||TR.window_s||10):1;SPD.push(isNum(dk)&&dtm>0?Math.max(0,dk/dtm*3600):null);
    var da=i&&isNum(A[i])&&isNum(A[i-1])?A[i]-A[i-1]:0;GR.push(isNum(dk)&&dk>0.005?Math.max(-20,Math.min(25,da/(dk*1000)*100)):0);
    var s=0,c=0;for(var j=Math.max(0,i-1);j<=Math.min(N-1,i+1);j++){if(isNum(P[j])){s+=P[j];c++;}}PWS.push(c?s/c:null);}}

/* ---------- mapa ---------- */
function buildMap(){
  var lat=TR.lat||[],lon=TR.lon||[];
  if(!map){map=L.map("map",{zoomControl:false,attributionControl:false});L.control.zoom({position:"bottomright"}).addTo(map);var _qtl=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19}).addTo(map);if(window.qTilesAttach)window.qTilesAttach(map,_qtl);applyBW();
    $("bwbtn").onclick=function(){var dk=document.documentElement.classList.contains("theme-dark");if(!dk){bw=!bw;}else{var nc=window.qTilesIsNightColor&&window.qTilesIsNightColor();/* noc: kolor -> szara -> ciemna -> czarna -> kolor */var st=nc?(bw?2:3):(bw?1:0);st=({3:2,2:0,0:1,1:3})[st];bw=(st===1||st===2);nc=(st>=2);if(window.qTilesNightColor)window.qTilesNightColor(nc);}applyBW();};document.addEventListener("qmapchange",function(){if(map)applyBW();});$("fitbtn").onclick=function(){fitAll();if(typeof resetView==="function")resetView();};
    map.on("click",function(e){var i=nearest(e.latlng.lat,e.latlng.lng);if(i>=0)setCursor(i,true);});}
  [casing,hl,hlc,mk].concat(segs).forEach(function(x){if(x)map.removeLayer(x);});segs=[];casing=hl=hlc=mk=null;
  var pts=[];for(var i=0;i<N;i++)if(isNum(lat[i])&&isNum(lon[i]))pts.push([lat[i],lon[i]]);
  if(!pts.length){$("empty").textContent="Brak śladu GPS.";return;}
  casing=L.polyline(pts,{color:"#111",weight:10,opacity:.8}).addTo(map);drawTrack();
  mk=L.circleMarker(pts[0],{radius:7,color:"#fff",weight:2.5,fillColor:"#e8742a",fillOpacity:1,opacity:0}).addTo(map);mk.setStyle({opacity:0,fillOpacity:0});
  fitAll();
}
function fitPad(){if(window.__RJ3&&typeof window.__RJ3.pad==="function")window.__RJ3.pad();/* 2026-10-08: margines liczony w chwili dopasowania (otwarte okno sekcji) *//* 2026-10-08: margines liczony w chwili dopasowania (otwarte okna) */return {paddingTopLeft:[(window.__RJ3&&window.__RJ3.padL)||80,70],paddingBottomRight:[40,$("dock").offsetHeight+30]};}
function fitAll(){var pts=[];for(var i=0;i<N;i++)if(isNum(TR.lat[i]))pts.push([TR.lat[i],TR.lon[i]]);if(pts.length)map.fitBounds(L.polyline(pts).getBounds(),window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches?{padding:[20,20]}:fitPad());}
function applyBW(){var tp=map.getPane("tilePane");if(tp)tp.style.filter=bw?"grayscale(1) contrast(.95) brightness(1.05)":"";var dk=document.documentElement.classList.contains("theme-dark"),nc=window.qTilesIsNightColor&&window.qTilesIsNightColor();$("bwbtn").textContent=dk?["Mapa: ciemna","Mapa: czarna","Mapa: szara","Mapa: kolor"][nc?(bw?2:3):(bw?1:0)]:(bw?"Mapa: kolor":"Mapa: B/W");}
function drawTrack(){
  segs.forEach(function(s){map.removeLayer(s);});segs=[];
  var lat=TR.lat,lon=TR.lon,tmin=Infinity,tmax=-Infinity;(TR.temp||[]).forEach(function(v){if(isNum(v)){tmin=Math.min(tmin,v);tmax=Math.max(tmax,v);}});
  var colAt=function(i){return mode==="pw"?zoneCol(PWS[i],FTP):mode==="hr"?hrCol(TR.hr[i]):mode==="wb"?wbCol(TR.wbal_pct&&TR.wbal_pct[i]):mode==="temp"?tempCol(TR.temp&&TR.temp[i],tmin,tmax):mode==="wind"?windCol(TR.tail&&TR.tail[i]):mode==="surf"?surfCol(i):"#e8742a";};
  var cur=null,pts=[],col=null,flush=function(){if(pts.length>1)segs.push(L.polyline(pts,{color:col,weight:6,opacity:1}).addTo(map));};
  for(var i=0;i<N;i++){if(!isNum(lat[i])||!isNum(lon[i]))continue;var c=colAt(i);if(c!==col){flush();pts=cur?[cur]:[];col=c;}cur=[lat[i],lon[i]];pts.push(cur);}
  flush();if(hl){hl.bringToFront();}if(mk)mk.bringToFront();
  $("tracklegend").innerHTML=(LEG[mode]||[]).map(function(x){return '<span><i class="sw" style="background:'+x[0]+'"></i>'+x[1]+'</span>';}).join(" ")+(mode==="temp"&&isFinite(tmin)?' <span class="muted">'+n(tmin,0)+'–'+n(tmax,0)+'°</span>':"");
}
function nearest(la,lo){var best=-1,bd=Infinity;for(var i=0;i<N;i++){var a=TR.lat[i],b=TR.lon[i];if(!isNum(a))continue;var d=(a-la)*(a-la)+((b-lo)*Math.cos(la*Math.PI/180))*((b-lo)*Math.cos(la*Math.PI/180));if(d<bd){bd=d;best=i;}}return bd<1e-5?best:-1;}
function highlightSel(){
  if(hl){map.removeLayer(hl);map.removeLayer(hlc);hl=hlc=null;}
  if(!SEL)return;var pts=[];for(var i=SEL.a;i<=SEL.b;i++)if(isNum(TR.lat[i]))pts.push([TR.lat[i],TR.lon[i]]);if(pts.length<2)return;
  hlc=L.polyline(pts,{color:"#fff",weight:13,opacity:.95}).addTo(map);hl=L.polyline(pts,{color:"#e8742a",weight:7,opacity:1}).addTo(map);if(mk)mk.bringToFront();
  map.fitBounds(hl.getBounds(),window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches?{padding:[20,20]}:fitPad());
}

/* ---------- wykres: linie na jednym polu + wstegi ---------- */
var LTHR=150,SCALE="abs";  /* 2026-10-08: LTHR z raportu (load.lthr_bpm, dynamiczne), 150 awaryjnie */
var CW=1000,ML=56,MR=48,AXW=40,CH=230,RIB_H=9,LN={alt:true,pw:true,hr:true,wb:true,spd:false,cad:false,temp:false,dev:false},RIB={zone:false,wind:false,surf:false},XM="km",SEL=null,VIEW=null,CMP=[];
function smooth(arr,w){var o=new Array(N),hh=w>>1;for(var i=0;i<N;i++){var sm=0,c=0;for(var j=i-hh;j<=i+hh;j++){if(j>=0&&j<N&&isNum(arr[j])){sm+=arr[j];c++;}}o[i]=c?sm/c:null;}return o;}
var SPDS=[],CADS=[],DEV=[],AX={hr:true};
var MOM=[],MOMM=[],SHOWMOM=true;
var SURF=[],SCAT={1:"#1565c0",2:"#2e7d32",3:"#8bc34a",4:"#e07b1a",5:"#c2452f"},SLAB={1:"twarda szybka",2:"dobry gravel",3:"zwykły gravel",4:"trudny/wolny",5:"ryzyko/niepewne"};
async function loadSurface(){
  SURF=new Array(N).fill(null);
  var sc=TR.surface_cat;if(Array.isArray(sc)&&sc.some(function(x){return x;})){for(var q=0;q<N;q++)SURF[q]=sc[q]||null;return;}
  /* zapas dla starych raportow bez surface_cat: nawierzchnia z dopasowanej trasy po pozycji */
  var pva=V(D.plan_vs_actual)||{},rid=pva._route_id;if(!rid)return;
  try{
    var sp=await getJSON("/api/routes/"+encodeURIComponent(rid)+"/spine"),cat=await getJSON("/api/routes/"+encodeURIComponent(rid)+"/surface-categories");
    var spine=sp.spine||[],rib=cat.ribbon||[];if(!spine.length||!rib.length)return;
    var catAt=function(km){for(var q=0;q<rib.length;q++){if(km>=rib[q].km_from&&km<rib[q].km_to)return rib[q].category;}return null;};
    /* siatka przestrzenna 0.005 stopnia dla szybkiego szukania */
    var G={},key=function(la,lo){return Math.floor(la/0.005)+"_"+Math.floor(lo/0.005);};
    spine.forEach(function(pt,ix){var k=key(pt.la,pt.lo);(G[k]=G[k]||[]).push(ix);});
    var cosL=Math.cos((TR.lat[0]||52)*Math.PI/180);
    for(var i=0;i<N;i++){var la=TR.lat[i],lo=TR.lon[i];if(!isNum(la))continue;var best=-1,bd=Infinity;
      var ka=Math.floor(la/0.005),ko=Math.floor(lo/0.005);
      for(var da=-1;da<=1;da++)for(var dz=-1;dz<=1;dz++){var arr=G[(ka+da)+"_"+(ko+dz)];if(!arr)continue;for(var j=0;j<arr.length;j++){var pt=spine[arr[j]];var dx=(pt.lo-lo)*cosL,dy=pt.la-la,d=dx*dx+dy*dy;if(d<bd){bd=d;best=arr[j];}}}
      if(best>=0&&Math.sqrt(bd)*111000<60)SURF[i]=catAt(spine[best].k);}
  }catch(e){}
}
function surfCol(i){var c=SURF[i];return c?SCAT[c]:"#777";}
var SER={pw:{col:"var(--ink)",w:3.2,unit:" W",f:function(i){return PWS[i];}},hr:{col:"#e03131",w:1.1,unit:" bpm",f:function(i){return TR.hr[i];}},wb:{col:"#8f86e6",w:1.6,unit:"%",fix:[0,100],f:function(i){return TR.wbal_pct?TR.wbal_pct[i]:null;}},spd:{col:"var(--ink2)",w:1.1,op:.7,unit:" km/h",f:function(i){return SPDS[i];}},cad:{col:"#9c8aa8",w:1.1,op:.6,unit:" rpm",f:function(i){return CADS[i];}},temp:{col:"#d9a441",w:1.2,op:.7,unit:"°",f:function(i){return TR.temp?TR.temp[i]:null;}},dev:{col:"#f0c060",w:1.6,op:.9,unit:" m/obr",f:function(i){return DEV[i];}}};
function xv(i){return XM==="km"?TR.km[i]:(TR.t[i]-TR.t[0]);}
function rng(){return VIEW||{a:0,b:N-1};}
function CX(i){var r=rng(),x0=xv(r.a),x1=xv(r.b);return ML+((xv(i)-x0)/((x1-x0)||1))*(CW-ML-MR);}
function iAtX(px){var r=rng(),x0=xv(r.a),x1=xv(r.b),v=x0+(px-ML)/(CW-ML-MR)*(x1-x0);var lo=r.a,hi=r.b;while(lo<hi){var m=(lo+hi)>>1;if(xv(m)<v)lo=m+1;else hi=m;}return Math.max(r.a,Math.min(r.b,lo));}
function drawChart(){
  var svg=$("chart");if(!N){svg.innerHTML="";return;}
  CH=parseFloat(getComputedStyle($("dock")).getPropertyValue("--dh"))||230;svg.setAttribute("viewBox","0 0 "+CW+" "+CH);
  var rightAxes=["hr","wb","spd","cad","temp","dev"].filter(function(k){return LN[k]&&AX[k]&&!(SCALE==="rel"&&(k==="hr"));});MR=10+AXW*rightAxes.length+(rightAxes.length?0:14);
  var ribs=Object.keys(RIB).filter(function(k){return RIB[k];}),r=rng(),a=r.a,b=r.b,P=[],i,top=14,base=CH-16-ribs.length*(RIB_H+3),H=base-top;
  var nice=function(lo,hi,n){var span=hi-lo,raw=span/n,p=Math.pow(10,Math.floor(Math.log10(raw))),m=raw/p,st=m<1.5?1:m<3.5?2:m<7.5?5:10;return st*p;};
  var ticks=function(lo,hi,n){var st=nice(lo,hi,n),o=[];for(var v=Math.ceil(lo/st)*st;v<=hi+1e-9;v+=st)o.push(Math.round(v*1000)/1000);return o;};
  var mm=function(fn){var lo=Infinity,hi=-Infinity;for(var q=a;q<=b;q++){var z=fn(q);if(isNum(z)){if(z<lo)lo=z;if(z>hi)hi=z;}}if(!isFinite(lo)){lo=0;hi=1;}if(hi===lo)hi=lo+1;return [lo,hi];};
  var x0=xv(a),x1=xv(b),span=x1-x0,steps=XM==="km"?[0.5,1,2,5,10,20,25,50]:[60,300,600,900,1800,3600,7200],st=steps.find(function(s){return span/s<=12;})||steps[steps.length-1];
  for(var v=Math.ceil(x0/st)*st;v<=x1+1e-9;v+=st){var gx=ML+((v-x0)/(span||1))*(CW-ML-MR);P.push('<line x1="'+gx.toFixed(1)+'" y1="'+top+'" x2="'+gx.toFixed(1)+'" y2="'+(CH-14)+'" stroke="var(--line)" stroke-width="1"/><text x="'+gx.toFixed(1)+'" y="'+(CH-3)+'" font-size="11" fill="var(--muted)" text-anchor="middle">'+(XM==="km"?(Math.round(v*10)/10):fmtHM(v))+'</text>');}
  var drawAlt=function(){if(!LN.alt)return;var er=mm(function(q){return TR.alt[q];}),d="M"+CX(a).toFixed(1)+" "+base;for(i=a;i<=b;i++){var z=TR.alt[i];if(!isNum(z))z=er[0];d+=" L"+CX(i).toFixed(1)+" "+(base-((z-er[0])/(er[1]-er[0]))*H*0.8).toFixed(1);}d+=" L"+CX(b).toFixed(1)+" "+base+" Z";
    P.push('<path d="'+d+'" fill="#8a8f96" opacity=".28"/>');ALTR=[er[0],er[0]+(er[1]-er[0])/0.8];};var ALTR=null;
  var SC={};Object.keys(SER).forEach(function(k){if(!LN[k])return;var s=SER[k],rr=s.fix?s.fix.slice():mm(s.f);
    if(SCALE==="rel"&&(k==="pw"||k==="hr")){var pm=mm(function(q){return PWS[q];})[1]/(FTP||1)*100,hm=mm(function(q){return TR.hr[q];})[1]/LTHR*100;var hi=Math.max(120,Math.ceil(Math.max(pm,hm)/10)*10);SC[k]=k==="pw"?[0,hi/100*(FTP||1)]:[0,hi/100*LTHR];return;}if(k==="pw"){rr[0]=0;rr[1]=Math.max(rr[1],FTP?FTP*1.2:200);}if(k==="hr"){rr[0]=Math.min(rr[0],80);rr[1]=Math.max(rr[1],170);}if(k==="spd")rr[0]=0;if(k==="cad"){rr[0]=Math.min(rr[0],40);rr[1]=Math.max(rr[1],110);}if(k==="temp"){rr[0]-=1;rr[1]+=1;}if(k==="dev"){rr[0]=Math.max(0,Math.floor(rr[0]-0.5));rr[1]=Math.ceil(rr[1]+0.5);}SC[k]=rr;});
  if(SCALE==="abs"&&LN.pw&&FTP){var fy=base-(FTP/SC.pw[1])*H;P.push('<line x1="'+ML+'" y1="'+fy.toFixed(1)+'" x2="'+(CW-MR)+'" y2="'+fy.toFixed(1)+'" stroke="#e8742a" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/><text x="'+(ML+4)+'" y="'+(fy-3).toFixed(1)+'" font-size="10" fill="#e8742a">próg '+FTP+' W</text>');}
  ["temp","alt","wb","cad","spd","dev","hr","pw"].forEach(function(k){if(k==="alt"){drawAlt();return;}if(!LN[k])return;var s=SER[k],rr=SC[k];
    if(k==="pw"){ /* linia mocy kolorowana strefa: odcinki miedzy probkami */
      var Y=function(z){return (base-((z-rr[0])/(rr[1]-rr[0]))*H).toFixed(1);},cur=null,dd="",col=null;
      var flush=function(){if(dd)P.push('<path d="'+dd+'" fill="none" stroke="'+col+'" stroke-width="'+s.w+'" stroke-linejoin="round" stroke-linecap="round"/>');dd="";};
      for(i=a;i<=b;i++){var z=s.f(i);if(!isNum(z)){flush();cur=null;col=null;continue;}var c=zoneCol(z,FTP),pt=CX(i).toFixed(1)+" "+Y(z);
        if(c!==col){flush();col=c;dd=cur?"M"+cur+" L"+pt:"M"+pt;}else dd+=" L"+pt;cur=pt;}
      flush();return;}
    var dd2="",pen=false;for(i=a;i<=b;i++){var z2=s.f(i);if(!isNum(z2)){pen=false;continue;}dd2+=(pen?" L":" M")+CX(i).toFixed(1)+" "+(base-((z2-rr[0])/(rr[1]-rr[0]))*H).toFixed(1);pen=true;}P.push('<path d="'+dd2+'" fill="none" stroke="'+s.col+'" stroke-width="'+s.w+'" stroke-linejoin="round"'+(s.op?' opacity="'+s.op+'"':'')+'/>');});
  var YY=function(z,rr){return (base-((z-rr[0])/(rr[1]-rr[0]))*H).toFixed(1);};
  if(SCALE==="rel"&&(LN.pw||LN.hr)){var rr0=SC.pw||SC.hr,mx=SC.pw?SC.pw[1]/(FTP||1)*100:SC.hr[1]/LTHR*100;
    for(var pc=0;pc<=mx+1e-9;pc+=20){var yy=(base-(pc/mx)*H).toFixed(1);P.push('<line x1="'+ML+'" y1="'+yy+'" x2="'+(CW-MR)+'" y2="'+yy+'" stroke="var(--line)" stroke-width="1" opacity=".7"/><text x="'+(ML-6)+'" y="'+(+yy+3.5)+'" font-size="10" fill="var(--ink)" text-anchor="end">'+pc+'%</text>');}
    var y100=(base-(100/mx)*H).toFixed(1);P.push('<line x1="'+ML+'" y1="'+y100+'" x2="'+(CW-MR)+'" y2="'+y100+'" stroke="var(--accent)" stroke-width="1.2" stroke-dasharray="5 3"/><text x="'+(ML+4)+'" y="'+(+y100-3)+'" font-size="10" fill="var(--accent-ink)">100% progu = '+(FTP||"—")+' W · '+LTHR+' bpm</text>');
    P.push('<text x="'+(ML-6)+'" y="'+(top-4)+'" font-size="10" fill="var(--ink)" text-anchor="end" font-weight="600">% progu</text>');}
  else if(LN.pw){ticks(SC.pw[0],SC.pw[1],5).forEach(function(v){var yy=YY(v,SC.pw);P.push('<line x1="'+ML+'" y1="'+yy+'" x2="'+(CW-MR)+'" y2="'+yy+'" stroke="var(--line)" stroke-width="1" opacity=".7"/><text x="'+(ML-6)+'" y="'+(+yy+3.5)+'" font-size="10" fill="var(--ink)" text-anchor="end">'+v+'</text>');});
    P.push('<text x="'+(ML-6)+'" y="'+(top-4)+'" font-size="10" fill="var(--ink)" text-anchor="end" font-weight="600">W</text>');}
  if(LN.alt&&ALTR){P.push('<text x="'+(CW-MR-4)+'" y="'+(base-3)+'" font-size="9.5" fill="#9aa0a6" text-anchor="end">'+Math.round(ALTR[0])+' m</text><text x="'+(CW-MR-4)+'" y="'+(base-H*0.8+4).toFixed(1)+'" font-size="9.5" fill="#9aa0a6" text-anchor="end">'+Math.round(ALTR[0]+(ALTR[1]-ALTR[0])*0.8)+' m</text>');}
  var UN={hr:"bpm",wb:"%",spd:"km/h",cad:"rpm",temp:"°C",alt:"m",dev:"m/obr"},AXC={hr:"#e03131",wb:"#8f86e6",spd:"var(--ink2)",cad:"#9c8aa8",temp:"#d9a441",alt:"#9aa0a6",dev:"#f0c060"};
  rightAxes.forEach(function(k,ix){var rr=k==="alt"?ALTR:SC[k];if(!rr)return;var x=CW-MR+10+ix*AXW;
    P.push('<line x1="'+x+'" y1="'+top+'" x2="'+x+'" y2="'+base+'" stroke="'+AXC[k]+'" stroke-width="1" opacity=".8"/>');
    P.push('<text x="'+(x+3)+'" y="'+(top-4)+'" font-size="9.5" fill="'+AXC[k]+'" font-weight="600">'+UN[k]+'</text>');
    ticks(rr[0],rr[1],4).forEach(function(v){var yy=YY(v,rr);if(+yy<top||+yy>base)return;P.push('<line x1="'+x+'" y1="'+yy+'" x2="'+(x+4)+'" y2="'+yy+'" stroke="'+AXC[k]+'" stroke-width="1"/><text x="'+(x+6)+'" y="'+(+yy+3.5)+'" font-size="9.5" fill="'+AXC[k]+'">'+v+'</text>');});});
  P.push('<line x1="'+ML+'" y1="'+base+'" x2="'+(CW-MR)+'" y2="'+base+'" stroke="var(--line2)"/>');
  var y=base+3;ribs.forEach(function(k){var lab=k==="zone"?"strefy":k==="surf"?"nawierzch.":"wiatr";for(i=a;i<b;i++){var c=k==="zone"?zoneCol(PWS[i],FTP):k==="surf"?surfCol(i):windCol(TR.tail&&TR.tail[i]);var xa=CX(i),xb=CX(i+1);P.push('<rect x="'+xa.toFixed(1)+'" y="'+y+'" width="'+Math.max(0.7,xb-xa+0.2).toFixed(1)+'" height="'+RIB_H+'" fill="'+c+'"/>');}
    P.push('<text x="'+(ML-4)+'" y="'+(y+RIB_H-1)+'" font-size="9" fill="var(--muted)" text-anchor="end">'+lab+'</text>');y+=RIB_H+3;});
  if(SEL){var sa=CX(Math.max(a,SEL.a)),sb=CX(Math.min(b,SEL.b));if(sb>sa)P.push('<rect x="'+sa.toFixed(1)+'" y="'+top+'" width="'+(sb-sa).toFixed(1)+'" height="'+(CH-14-top)+'" fill="var(--accent)" opacity=".16"/><line x1="'+sa+'" y1="'+top+'" x2="'+sa+'" y2="'+(CH-14)+'" stroke="var(--accent)" stroke-width="1.5"/><line x1="'+sb+'" y1="'+top+'" x2="'+sb+'" y2="'+(CH-14)+'" stroke="var(--accent)" stroke-width="1.5"/>');}
  P.push('<line id="hcur" x1="0" y1="'+top+'" x2="0" y2="'+(CH-14)+'" stroke="var(--ink)" stroke-width="1.2" opacity="0"/>');
  svg.innerHTML=P.join("");
  $("viewall").style.display=VIEW?"":"none";
  if(typeof drawMomentPills==="function")drawMomentPills();
}
function chipVals(k){document.querySelectorAll("#dock .chip[data-l]").forEach(function(c){var l=c.dataset.l,cv=c.querySelector(".cv");if(!cv)return;if(k==null){cv.textContent="";return;}if(l==="alt"){cv.textContent=n(TR.alt[k])+" m";return;}var s=SER[l];var z=s.f(k);cv.textContent=isNum(z)?(l==="pw"||l==="hr"||l==="cad"?Math.round(z):l==="dev"?n(z,2):n(z,1))+s.unit:"—";});}
function setCursor(i,fromMap){
  var k=Math.round(i);if(!isNum(TR.lat[k]))return;
  mk.setLatLng([TR.lat[k],TR.lon[k]]);mk.setStyle({opacity:1,fillOpacity:1});
  var h=$("chart").querySelector("#hcur");var r=rng();if(h){if(k>=r.a&&k<=r.b){h.setAttribute("x1",CX(k));h.setAttribute("x2",CX(k));h.setAttribute("opacity",".7");}else h.setAttribute("opacity","0");}
  chipVals(k);
  var tip=$("tip"),svg=$("chart"),rr=svg.getBoundingClientRect();tip.style.display="block";var lx=(CX(k)/CW)*rr.width;tip.style.left=lx+"px";tip.style.top="6px";tip.style.transform=lx>rr.width*0.6?"translateX(-105%)":"translateX(8px)";tip.innerHTML=tipHTML(k);
}
/* 2026-10-08: dymek nad wykresem pokazuje tez LICZBY wlaczonych serii (to samo co na wykresie) */
var TIPN={alt:"wys.",pw:"moc",hr:"tętno",wb:"zapas",spd:"prędk.",cad:"kad.",temp:"temp.",dev:"rozw."};
function tipVals(k){var o=[];Object.keys(TIPN).forEach(function(l){if(!LN[l])return;var z,u;if(l==="alt"){z=TR.alt[k];u=" m";}else{var s=SER[l];if(!s)return;z=s.f(k);u=s.unit||"";}if(!isNum(z))return;o.push("<b>"+TIPN[l]+" "+(l==="pw"||l==="hr"||l==="cad"||l==="alt"||l==="wb"?Math.round(z):l==="dev"?n(z,2):n(z,1))+u+"</b>");});return o.length?"<br>"+o.join(" · "):"";}
function tipHTML(k){return tipBase(k)+tipVals(k);}
function tipBase(k){return "km "+n(TR.km[k],1)+" · "+fmtT(TR.t[k]-TR.t[0])+" · "+(GR[k]>0?"+":"")+n(GR[k],1)+"%"+(SURF[k]?" · "+SLAB[SURF[k]]:"")+(TR.tail?" · wiatr "+(TR.tail[k]>0?"+":"")+n(TR.tail[k],1)+" m/s":"");}
function resetView(){VIEW=null;drawChart();}
(function wire(){
  var svg=$("chart"),tip=$("tip"),down=null,moved=false,lastTap=0,tapT=null;
  var px=function(e){var r=svg.getBoundingClientRect();return (e.clientX-r.left)/r.width*CW;};
  svg.addEventListener("pointerdown",function(e){if(!N)return;down=px(e);moved=false;svg.setPointerCapture(e.pointerId);});
  svg.addEventListener("pointermove",function(e){if(!N)return;var x=px(e),k=iAtX(x);setCursor(k,false);
    if(down!=null&&Math.abs(x-down)>5){moved=true;SEL={a:iAtX(Math.min(down,x)),b:iAtX(Math.max(down,x))};drawChart();}});
  svg.addEventListener("pointerup",function(e){if(!N)return;var now=Date.now();
    if(moved){showSeg();highlightSel();}
    else{/* 2026-10-08: KLIK = WROC. Wykres powiekszony -> cala jazda. Zaznaczony odcinek (mapa przyblizona do odcinka) -> zdjecie
         zaznaczenia + cala trasa na mapie (po 360 ms, zeby dwuklik zdazyl). DWUKLIK na zaznaczeniu = powieksz wykres. */
      if(VIEW){clearTimeout(tapT);resetView();lastTap=0;}
      else if(now-lastTap<350&&SEL){clearTimeout(tapT);VIEW={a:SEL.a,b:SEL.b};drawChart();lastTap=0;}
      else{lastTap=now;clearTimeout(tapT);if(SEL)tapT=setTimeout(function(){if(!VIEW&&SEL){closeSeg();fitAll();}},360);}}
    down=null;moved=false;});
  svg.addEventListener("pointerleave",function(){tip.style.display="none";var h=svg.querySelector("#hcur");if(h)h.setAttribute("opacity","0");if(mk)mk.setStyle({opacity:0,fillOpacity:0});chipVals(null);});
  document.addEventListener("keydown",function(e){if(e.key==="Escape"){if(document.querySelector(".qmod.on"))return;if(VIEW)resetView();else{var had=SEL;closeSeg();if(had)fitAll();}}});
  document.querySelectorAll("#dock .chip[data-l]").forEach(function(c){c.onclick=function(e){var l=c.dataset.l;if(e.target.classList.contains("ax")){AX[l]=!AX[l];e.target.classList.toggle("on",!!AX[l]);drawChart();return;}LN[l]=!LN[l];if(l!=="alt"&&l!=="pw")AX[l]=LN[l];c.classList.toggle("on",LN[l]);var axx=c.querySelector(".ax");if(axx)axx.classList.toggle("on",!!AX[l]);drawChart();};});
  function syncChips(){document.querySelectorAll("#dock .chip[data-l]").forEach(function(c){c.classList.toggle("on",!!LN[c.dataset.l]);var ax=c.querySelector(".ax");if(ax)ax.classList.toggle("on",!!AX[c.dataset.l]);});document.querySelectorAll("#dock .chip[data-sc]").forEach(function(x){x.classList.toggle("on",x.dataset.sc===SCALE);});}
  var PRESETS={pwhr:{ln:{alt:true,pw:true,hr:true},sc:"rel",ax:{}},spdcad:{ln:{alt:true,spd:true,cad:true,dev:true},sc:"abs",ax:{spd:true,cad:true,dev:true}},pwspd:{ln:{alt:true,pw:true,spd:true},sc:"abs",ax:{spd:true},rib:{surf:true,wind:true}},hrtemp:{ln:{alt:true,hr:true,temp:true},sc:"abs",ax:{hr:true,temp:true}},wbpw:{ln:{alt:true,wb:true,pw:true},sc:"abs",ax:{wb:true}},hralt:{ln:{alt:true,hr:true},sc:"abs",ax:{hr:true}}};
  var pe=$("preset");if(pe)pe.onchange=function(){var p=PRESETS[pe.value];if(!p)return;Object.keys(LN).forEach(function(k){LN[k]=!!p.ln[k];});AX={};Object.keys(p.ax).forEach(function(k){AX[k]=true;});SCALE=p.sc;if(p.rib){Object.keys(RIB).forEach(function(k){RIB[k]=!!p.rib[k];});document.querySelectorAll("#dock .chip[data-r]").forEach(function(x){x.classList.toggle("on",!!RIB[x.dataset.r]);});}syncChips();drawChart();};
  document.querySelectorAll("#dock .chip[data-r]").forEach(function(c){c.onclick=function(){RIB[c.dataset.r]=!RIB[c.dataset.r];c.classList.toggle("on",RIB[c.dataset.r]);drawChart();};});
  document.querySelectorAll("#dock .chip[data-sc]").forEach(function(c){c.onclick=function(){SCALE=c.dataset.sc;document.querySelectorAll("#dock .chip[data-sc]").forEach(function(x){x.classList.toggle("on",x===c);});drawChart();};});
  document.querySelectorAll("#dock .chip[data-x]").forEach(function(c){c.onclick=function(){XM=c.dataset.x;document.querySelectorAll("#dock .chip[data-x]").forEach(function(x){x.classList.toggle("on",x===c);});drawChart();};});
  $("viewall").onclick=resetView;
  var mc=$("momchip");if(mc)mc.onclick=function(){SHOWMOM=!SHOWMOM;mc.classList.toggle("on",SHOWMOM);MOMM.forEach(function(x){SHOWMOM?x.addTo(map):map.removeLayer(x);});drawMomentPills();};
  $("trackmode").onchange=function(e){mode=e.target.value;if(map)drawTrack();};
  var g=$("grip"),gy=null,gh=null;g.addEventListener("pointerdown",function(e){gy=e.clientY;gh=parseFloat(getComputedStyle($("dock")).getPropertyValue("--dh"))||230;g.setPointerCapture(e.pointerId);});
  g.addEventListener("pointermove",function(e){if(gy==null)return;var h=Math.max(120,Math.min(window.innerHeight*0.7,gh+(gy-e.clientY)));$("dock").style.setProperty("--dh",h+"px");});
  g.addEventListener("pointerup",function(){gy=null;drawChart();});
  window.addEventListener("resize",function(){if(N)drawChart();});
})();

/* ---------- analiza AI (W2) ---------- */
var AN=null,ANPOLL=null;
function anOpen(){anLoad(false);}
function anClose(){if(ANPOLL){clearInterval(ANPOLL);ANPOLL=null;}}
async function anLoad(rebuild){
  var b=$("an-body");if(!b)return;b.innerHTML='<div class="sub">'+(rebuild?"generuję ponownie (do minuty)…":"ładuję…")+'</div>';
  try{var j=await getJSON("/api/ride-report/w2?ride="+encodeURIComponent(RKEY)+(rebuild?"&rebuild=1":""));
    if(j&&j.status==="empty"){b.innerHTML='<div class="sub">Dla tej jazdy nie ma jeszcze analizy.</div><button class="btn pri" id="an-gen" type="button" style="margin-top:10px">Wygeneruj analizę</button><div class="sub" style="margin-top:8px;font-size:13px">To samo, co „Tak, analizuj" na Telegramie: wynik pojawi się tu, skrót na Telegramie, szczegóły mailem (ok. minuty).</div>';
      $("an-gen").onclick=async function(){this.disabled=true;this.textContent="liczę…";await fetch("/api/ride-report/analyze?ride="+encodeURIComponent(RKEY),{method:"POST",credentials:"same-origin"});anPoll();};return;}
    AN=j;anRender(j);}
  catch(e){b.innerHTML='<div class="sub">Błąd: '+esc(e.message)+'</div>';}
}
function anPoll(){if(ANPOLL)clearInterval(ANPOLL);var n=0;ANPOLL=setInterval(async function(){n++;try{var j=await getJSON("/api/ride-report/w2?ride="+encodeURIComponent(RKEY));if(j&&j.verdict){clearInterval(ANPOLL);ANPOLL=null;AN=j;anRender(j);return;}}catch(e){}
  var st=null;try{st=await getJSON("/api/ride-report/status?ride="+encodeURIComponent(RKEY));}catch(e){}
  if(st&&st.status==="error"){clearInterval(ANPOLL);ANPOLL=null;$("an-body").innerHTML='<div class="sub">Generowanie nie powiodło się: '+esc(st.note||"")+'</div>';return;}
  if(n>40){clearInterval(ANPOLL);ANPOLL=null;$("an-body").innerHTML='<div class="sub">Trwa dłużej niż zwykle — sprawdź Telegram lub odśwież za chwilę.</div>';}},5000);}
function kmToIdx(km){var lo=0,hi=N-1;while(lo<hi){var m=(lo+hi)>>1;if(TR.km[m]<km)lo=m+1;else hi=m;}return lo;}
function anDay(d){if(!d)return "";var x=new Date(d+"T12:00:00");var dn=["nd","pn","wt","śr","cz","pt","so"];return dn[x.getDay()]+" "+d.slice(8,10)+"."+d.slice(5,7);}
function anNum(v,dd){return v==null?"—":n(v,dd||0);}
function anCls(o){o=String(o||"");return o.indexOf("w planie")>=0?"good":(o.indexOf("brak")>=0||!o)?"":"warn";}
function anRender(j){
  var b=$("an-body");if(!b)return;
  if(!j.wykonanie||!j.fakty)return anRenderV1(j);
  var F=j.fakty||{},W=F.wykonanie||{},K=j.konsekwencje_live||F.konsekwencje||{},wy=j.wykonanie||{},h="";
  var SL={"dystans km":"Dystans (km)","czas ruchu h":"Czas jazdy (h)","obciazenie":"Obciążenie"};
  if(j.verdict)h+='<div class="v">'+esc(j.verdict)+'</div>';
  /* 1. plan */
  h+='<div class="q"><div class="qh">1 · Co zaplanowałeś</div><p>'+esc(j.plan||"Brak planu dla tej jazdy.")+'</p>';
  if((W.sumy||[]).some(function(s){return s.plan!=null;})){h+='<div class="tw"><table class="at"><tr><th></th><th>plan</th><th>realnie</th><th>różnica</th></tr>'+(W.sumy||[]).map(function(s){return '<tr><td>'+esc(SL[s.co]||s.co)+'</td><td>'+anNum(s.plan,s.co==="czas ruchu h"?1:0)+'</td><td>'+anNum(s.realnie,s.co==="czas ruchu h"?1:0)+'</td><td>'+(s.roznica_pct==null?"—":(s.roznica_pct>0?"+":"")+s.roznica_pct+"%")+'</td></tr>';}).join("")+'</table></div>';}
  h+='</div>';
  /* 2. wykonanie */
  var oc=wy.ocena||"";
  h+='<div class="q"><div class="qh">2 · Jak pojechałeś'+(oc?' <span class="rate '+anCls(oc)+'">'+esc(oc)+'</span>':'')+'</div><p>'+esc(wy.tekst||"")+'</p>';
  var we=W.wejscie||{};var wl=[];if(we.gotowosc_rano!=null)wl.push("gotowość rano "+(we.gotowosc_rano>0?"+":"")+n(we.gotowosc_rano,2)+(we.gotowosc_opis?" ("+esc(we.gotowosc_opis)+")":""));if(we.swiezosc_przed!=null)wl.push("świeżość przed "+n(we.swiezosc_przed,0));if(we.sen_h!=null)wl.push("sen "+n(we.sen_h,1)+" h");if(we.tetno_spoczynkowe!=null)wl.push("tętno spocz. "+we.tetno_spoczynkowe+(we.tetno_spoczynkowe_norma?" (norma "+we.tetno_spoczynkowe_norma+")":""));
  if(wl.length)h+='<div class="small">Wejście w jazdę: '+wl.join(" · ")+'</div>';
  var OD=W.odcinki||[],OT=wy.odcinki||[];
  if(OD.length){h+='<div class="tw"><table class="at"><tr><th>odcinek</th><th>plan W</th><th>średnio / NP</th><th>w zakresie</th><th>ocena</th></tr>';
    OD.forEach(function(o,i){var t=OT.filter(function(x){return Array.isArray(x.km)&&Math.abs(+x.km[0]-o.km[0])<0.2;})[0]||OT[i]||{};
      h+='<tr><td><span class="kmp" data-a="'+o.km[0]+'" data-b="'+o.km[1]+'">km '+n(o.km[0],0)+'–'+n(o.km[1],0)+' ↗</span></td><td>'+(o.plan_w&&o.plan_w[0]?o.plan_w[0]+'–'+o.plan_w[1]:"—")+'</td><td>'+o.sr_moc_w+' / '+(o.np_w||"—")+'</td><td>'+(o.czas_w_zakresie_pct==null?"—":o.czas_w_zakresie_pct+"%")+'</td><td><span class="rate '+anCls(o.ocena)+'">'+esc(String(o.ocena||"").replace(" (za duzo mocnych zrywow)","").replace("za slabo","za słabo").replace("nierowno","nierówno"))+'</span></td></tr>';
      if(t.tekst)h+='<tr class="tx"><td colspan="5">'+esc(t.tekst)+'</td></tr>';});
    h+='</table></div><div class="small">„średnio” liczone z postojami i zjazdami; NP = moc z uwzględnieniem zrywów.</div>';}
  var PO=W.podobne||{};if(PO.ta_jazda_ef){h+='<div class="small">Moc na uderzenie serca (EF): '+n(PO.ta_jazda_ef,2)+' wobec zwykle '+n(PO.mediana_ef,2)+' w '+(PO.jazdy||[]).length+' podobnych jazdach ('+(PO.roznica_pct>0?"+":"")+PO.roznica_pct+'%, orientacyjnie).</div>';}
  h+='</div>';
  /* 3. konsekwencje */
  h+='<div class="q"><div class="qh">3 · Konsekwencje</div><p>'+esc(j.konsekwencje||"")+'</p>';
  var DN=K.dni||[];if(DN.length){h+='<div class="tw"><table class="at"><tr><th>dzień</th><th>forma</th><th>zmęczenie</th><th>świeżość</th><th>gotowość</th></tr>'+DN.map(function(d){return '<tr'+(d.dzien===F.dzien?' style="font-weight:600"':'')+'><td>'+anDay(d.dzien)+(d.dzien===F.dzien?" · jazda":"")+'</td><td>'+anNum(d.forma)+'</td><td>'+anNum(d.zmeczenie)+'</td><td>'+(d.swiezosc==null?"—":(d.swiezosc>0?"+":"")+n(d.swiezosc,0))+'</td><td>'+(d.gotowosc==null?"—":(d.gotowosc>0?"+":"")+n(d.gotowosc,2))+'</td></tr>';}).join("")+'</table></div>';}
  var NX=K.nastepne_treningi||[],PR={};(K.prognoza_wg_planu||[]).forEach(function(p){PR[p.dzien]=p.swiezosc;});
  if(NX.length){h+='<div class="small" style="margin-top:6px">Najbliższe treningi (TRENER) i prognoza świeżości:</div><div class="tw"><table class="at">'+NX.map(function(x){var ps=PR[x.dzien];return '<tr><td>'+anDay(x.dzien)+'</td><td style="text-align:left">'+esc(x.nazwa||"")+'</td><td>'+(x.obciazenie?"obc. "+n(x.obciazenie,0):"")+'</td><td>'+(ps==null?"":"świeżość "+(ps>0?"+":"")+n(ps,0))+'</td></tr>';}).join("")+'</table></div>';}
  h+='<div class="small">forma = długi trend treningu · zmęczenie = ostatnie 7 dni · świeżość = forma − zmęczenie (poniżej zera = zmęczony) · gotowość = poranny stan organizmu</div></div>';
  /* 4. uwagi */
  var UW=j.uwagi||[];if(UW.length){h+='<div class="q"><div class="qh">4 · Na co zwrócić uwagę</div>'+UW.map(function(u){return '<div class="uw"><b>'+esc(u.co||"")+'</b>'+(u.dlaczego?'<div>'+esc(u.dlaczego)+'</div>':'')+(u.zalecenie?'<div class="zal">→ '+esc(u.zalecenie)+'</div>':'')+'</div>';}).join("")+'</div>';}
  if(j.dobrze||j.jedzenie){h+='<div class="q">'+(j.dobrze?'<p><b>Co wyszło dobrze:</b> '+esc(j.dobrze)+'</p>':'')+(j.jedzenie?'<p><b>Jedzenie i picie:</b> '+esc(j.jedzenie)+'</p>':'')+'</div>';}
  b.innerHTML=h;
  b.querySelectorAll(".kmp").forEach(function(k){k.onclick=function(){var a=kmToIdx(+k.dataset.a),bb=kmToIdx(+k.dataset.b);if(bb<=a)bb=Math.min(N-1,a+Math.max(3,Math.round(60/(TR.window_s||10))));setView("map");SEL={a:a,b:bb};drawChart();showSeg();highlightSel();};});
}
function anRenderV1(j){
  var b=$("an-body"),h="";if(!b)return;
  h+='<div class="meta">wygenerowana z danych jazdy (W1) · model czyta tylko liczby z raportu</div>';
  if(j.verdict)h+='<div class="v">'+esc(j.verdict)+'</div>';
  if(Array.isArray(j.highlights)&&j.highlights.length)h+='<div class="hl">'+j.highlights.map(function(x){return '<span>'+esc(x)+'</span>';}).join("")+'</div>';
  (j.synteza||[]).forEach(function(s,i){var km=Array.isArray(s.km)&&s.km.length===2&&isNum(+s.km[0])&&isNum(+s.km[1])?s.km:null;
    h+='<div class="sc"><b>'+esc(s.tytul||"")+(km?'<span class="kmp" data-a="'+(+km[0])+'" data-b="'+(+km[1])+'">km '+n(+km[0],1)+(km[1]!=km[0]?"–"+n(+km[1],1):"")+' ↗</span>':"")+'</b><p>'+esc(s.tekst||"")+'</p></div>';});
  if(Array.isArray(j.next)&&j.next.length)h+='<div class="nx"><b>Na następny raz</b><ul style="margin:4px 0 0;padding-left:18px">'+j.next.map(function(x){return '<li>'+esc(x)+'</li>';}).join("")+'</ul></div>';
  b.innerHTML=h;
  b.querySelectorAll(".kmp").forEach(function(k){k.onclick=function(){var a=kmToIdx(+k.dataset.a),bb=kmToIdx(+k.dataset.b);if(bb<=a)bb=Math.min(N-1,a+Math.max(3,Math.round(60/(TR.window_s||10))));setView("map");SEL={a:a,b:bb};drawChart();showSeg();highlightSel();};});
}
/* 2026-09-28: prawy panel Analiza AI usuniety - analiza jest ramka w widoku Analiza (daneRender) */
/* ---------- widok Analiza (pelna szerokosc) ---------- */
var VIEWM="map",SURFHL=[];
function setView(v){if(window.__RJ3)return;VIEWM=v;document.querySelectorAll("#viewseg button").forEach(function(b){b.classList.toggle("on",b.dataset.v===v);});
  var el=$("dane"),pj=$("pj"),dh=$("dhd");if(v==="dane"){el.style.display="";if(pj&&dh&&pj.parentNode!==dh)dh.appendChild(pj);daneRender();}else{if(pj&&pj.parentNode!==$("ws"))$("ws").insertBefore(pj,el);el.style.display="none";if(map)setTimeout(function(){map.invalidateSize();},50);}
  ["tl","dock","sg"].forEach(function(id){var e=$(id);if(!e)return;if(v==="dane"){e.dataset.prev=e.style.display;e.style.display="none";}else if(e.dataset.prev!==undefined){e.style.display=e.dataset.prev;}});
}
var DORD=["Wysiłek","Prędkość","Zapas na zrywy","Ciało tego dnia","Warunki i teren","Rower i napęd","Jedzenie"];
function daneRender(){var el=$("dgrid");if(!el||!D)return;
  el.innerHTML=(window.__RJ2dane?window.__RJ2dane(D,{FTP:FTP,TR:TR,PWS:PWS,SPD:SPD,GR:GR,LTHR:LTHR}):'<div class="sub">brak modułu Dane</div>');
  el.querySelectorAll(".dsec").forEach(function(s2){s2.classList.add("open");var t=s2.querySelector(".dh b"),ix=DORD.indexOf(t?t.textContent.trim():"");s2.style.order=ix<0?99:ix;});
  el.querySelectorAll(".it").forEach(function(it){if(!it.classList.contains("nw")&&(it.querySelector("table")||it.querySelector(".mmp")||it.querySelector(".zone")||it.querySelector(".lg")))it.classList.add("wt");});
  var TIPS=window.__RJTIPS||{};el.querySelectorAll(".it .h b").forEach(function(b){var t=TIPS[b.textContent.trim()];if(t)b.setAttribute("title",t);});
  el.querySelectorAll(".kmp[data-a]").forEach(function(k){k.onclick=function(){var a=kmToIdx(+k.dataset.a),b=kmToIdx(+k.dataset.b);if(b<=a)b=Math.min(N-1,a+Math.max(3,Math.round(60/(TR.window_s||10))));setView("map");SEL={a:a,b:b};drawChart();showSeg();highlightSel();};});
  el.querySelectorAll("tr.kmp[data-cat]").forEach(function(r){r.onclick=function(){setView("map");highlightSurf(+r.dataset.cat);};});
  /* Analiza AI jako pierwsza ramka widoku Analiza (2026-09-28; zamiast prawego panelu) */
  el.insertAdjacentHTML("afterbegin",'<div class="dsec open" id="an" style="order:-1"><div class="dh"><b>Analiza AI</b><a class="link" id="an-refresh" href="#" style="font-size:13px;margin-left:auto">odśwież</a><span class="chev">⌄</span></div><div class="db"><div id="an-body" class="sub">ładuję…</div></div></div>');
  var arf=$("an-refresh");if(arf)arf.onclick=function(e){e.preventDefault();anLoad(true);};
  /* 2026-09-28: "Z kim jechalem" - imiona zapisywane przy jezdzie (START > wyprawy sezonu); podpowiedzi: zaproszenia z RSVP, liczba osob ze Stravy */
  el.insertAdjacentHTML("afterbegin",'<div class="dsec open" id="zk" style="order:-2"><div class="dh"><b>Z kim jechałem</b><span class="chev">⌄</span></div><div class="db"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><input id="zk-in" type="text" maxlength="300" placeholder="imiona po przecinku, np. Tomek, Ania" style="flex:1;min-width:220px;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--well);color:var(--ink);font:inherit"><button id="zk-ok" type="button" style="appearance:none;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:10px;padding:8px 14px;font:inherit;font-weight:600;cursor:pointer">Zapisz</button></div><div class="sub" id="zk-h" style="margin-top:6px"></div></div></div>');
  (function(){var rk=RKEY;if(!rk)return;
    fetch("/api/ride/companions?ride="+encodeURIComponent(rk),{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(j){
      var inp=$("zk-in"),h=$("zk-h");if(!inp)return;inp.value=(j.names||[]).join(", ");var hint=[];
      if(j.strava_people)hint.push(j.strava_people>1?("Strava: jechaliście w "+j.strava_people+" "+(j.strava_people<5?"osoby":"osób")):"Strava: jazda solo");
      (j.suggestions||[]).forEach(function(s){hint.push(s.src+": "+s.name);});h.textContent=hint.join(" · ");
      $("zk-ok").onclick=function(){var names=inp.value.split(",").map(function(x){return x.trim();}).filter(Boolean);
        fetch("/api/ride/companions",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({ride:rk,names:names})}).then(function(r){return r.json();}).then(function(){h.textContent="Zapisane"+(names.length?": "+names.join(", "):" (solo)");});};
    }).catch(function(){});})();
  if(ANPOLL){$("an-body").innerHTML='<div class="sub">Generuję analizę (ok. minuty)…</div>';}else anLoad(false);
  /* Wysilek: kazda ramka zwija sie po kliknieciu nazwy; stan pamietany w przegladarce */
  var WCOL={};try{WCOL=JSON.parse(localStorage.getItem("rj_wys_col")||"{}")||{};}catch(e){WCOL={};}
  el.querySelectorAll(".dsec").forEach(function(s3){var tt=s3.querySelector(".dh b");if(!tt||tt.textContent.trim()!=="Wysi\u0142ek")return;
    s3.querySelectorAll(".it").forEach(function(itc){var hb=itc.querySelector(".h b");if(!hb||hb.dataset.col)return;var nm=hb.textContent.trim();hb.dataset.col="1";
      hb.style.cursor="pointer";hb.insertAdjacentHTML("afterbegin",'<span class="colchev">▾</span> ');
      var setc=function(on){itc.classList.toggle("col",on);var cv=hb.querySelector(".colchev");if(cv)cv.textContent=on?"▸":"▾";};
      if(WCOL[nm])setc(true);
      hb.onclick=function(e){e.stopPropagation();var on=!itc.classList.contains("col");setc(on);if(on)WCOL[nm]=1;else delete WCOL[nm];try{localStorage.setItem("rj_wys_col",JSON.stringify(WCOL));}catch(e2){}};});});
  /* Sekcje widoku Analiza: klik w naglowek zwija/rozwija cala sekcje; stan pamietany w przegladarce (2026-09-28) */
  var SCOL={};try{SCOL=JSON.parse(localStorage.getItem("rj_sec_col")||"{}")||{};}catch(e){SCOL={};}
  el.querySelectorAll(".dsec").forEach(function(s4){var dh=s4.querySelector(".dh"),tb=dh&&dh.querySelector("b");if(!dh||!tb||dh.dataset.col)return;dh.dataset.col="1";var nm=tb.textContent.trim();
    var ch=dh.querySelector(".chev");if(!ch){ch=document.createElement("span");ch.className="chev";dh.appendChild(ch);}
    var setS=function(open){s4.classList.toggle("open",open);ch.textContent=open?"⌄":"›";};
    setS(!SCOL[nm]);
    dh.onclick=function(e){if(e.target.closest("a,button"))return;var open=!s4.classList.contains("open");setS(open);if(open)delete SCOL[nm];else SCOL[nm]=1;try{localStorage.setItem("rj_sec_col",JSON.stringify(SCOL));}catch(e2){}};});
  if(window.__RJ3&&typeof window.__RJ3.after==="function")window.__RJ3.after();
}
function highlightSurf(cat){SURFHL.forEach(function(l){map.removeLayer(l);});SURFHL=[];if(!cat||!SURF.length)return;var pts=[];
  var flush=function(){if(pts.length>1){SURFHL.push(L.polyline(pts,{color:"#fff",weight:12,opacity:.95}).addTo(map));SURFHL.push(L.polyline(pts,{color:SCAT[cat],weight:7,opacity:1}).addTo(map));}pts=[];};
  for(var i=0;i<N;i++){if(SURF[i]===cat&&isNum(TR.lat[i]))pts.push([TR.lat[i],TR.lon[i]]);else flush();}flush();
  if(SURFHL.length){var g=L.featureGroup(SURFHL);map.fitBounds(g.getBounds(),window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches?{padding:[20,20]}:fitPad());}
  setTimeout(function(){SURFHL.forEach(function(l){map.removeLayer(l);});SURFHL=[];},8000);}
(function(){document.querySelectorAll("#viewseg button").forEach(function(b){b.onclick=function(){setView(b.dataset.v);};});})();
/* ---------- kluczowe momenty ---------- */
function buildMoments(){
  MOM=[];MOMM.forEach(function(m){map.removeLayer(m);});MOMM=[];if(!N)return;
  var win=TR.window_s||10,w5=Math.max(1,Math.round(300/win)),P=TR.power,km=TR.km,A=TR.alt,i,j;
  var best=null,run=0;for(i=0;i<N;i++){if(isNum(SPD[i])&&SPD[i]<1.5)run++;else{if(run*win>=60&&(!best||run>best.len))best={len:run,i:i-run};run=0;}}
  if(best)MOM.push({a:best.i,b:Math.min(N-1,best.i+best.len),ic:"⏸",lab:"postój "+Math.round(best.len*win/60)+" min",t:"Najdłuższy postój"});
  var bs=-1,bi=0;for(i=0;i+w5<=N;i++){var sm=0,c=0;for(j=0;j<w5;j++){if(isNum(P[i+j])){sm+=P[i+j];c++;}}if(c===w5&&sm>bs){bs=sm;bi=i;}}
  if(bs>0)MOM.push({a:bi,b:Math.min(N-1,bi+w5),ic:"⚡",lab:"5 min · "+Math.round(bs/w5)+" W"+(FTP?" ("+Math.round(bs/w5/FTP*100)+"%)":""),t:"Najmocniejsze 5 minut"});
  if(TR.wbal_pct){var mi=-1;for(i=0;i<N;i++)if(isNum(TR.wbal_pct[i])&&(mi<0||TR.wbal_pct[i]<TR.wbal_pct[mi]))mi=i;if(mi>=0&&TR.wbal_pct[mi]<90)MOM.push({a:mi,b:null,ic:"▼",lab:"zapas "+Math.round(TR.wbal_pct[mi])+"%",t:"Najgłębszy zapas na zrywy"});}
  var wC=Math.round(1200/win),bg=0,bgi=0,bgj=0;for(i=0;i<N;i++){for(j=i+1;j<Math.min(N,i+wC);j++){if(isNum(A[j])&&isNum(A[i])){var g=A[j]-A[i];if(g>bg){bg=g;bgi=i;bgj=j;}}}}
  if(bg>25){var dk=km[bgj]-km[bgi];MOM.push({a:bgi,b:bgj,ic:"⛰",lab:"+"+Math.round(bg)+" m · "+n(bg/(Math.max(dk,0.01)*1000)*100,1)+"%",t:"Największy podjazd"});}
  var ms=0;for(i=0;i<N;i++)if(isNum(SPD[i])&&SPD[i]>(SPD[ms]||0))ms=i;
  if(SPD[ms]>25)MOM.push({a:ms,b:null,ic:"↓",lab:Math.round(SPD[ms])+" km/h",t:"Najszybszy moment"});
  /* najciezszy kilometr: srednia moc w oknie 1 km */
  var hk=-1,hkA=0,hkB=0;for(i=0;i<N;i++){var e=i;while(e+1<N&&km[e+1]-km[i]<1)e++;if(km[e]-km[i]<0.9)break;var s2=0,c2=0;for(j=i;j<=e;j++){if(isNum(P[j])){s2+=P[j];c2++;}}if(c2&&s2/c2>hk){hk=s2/c2;hkA=i;hkB=e;}}
  if(hk>0&&!(bi<=hkA&&hkB<=bi+w5))MOM.push({a:hkA,b:hkB,ic:"🔥",lab:"km · "+Math.round(hk)+" W",t:"Najcięższy kilometr"});
  MOM.sort(function(x,y){return x.a-y.a;});
  MOM.forEach(function(m){var k=m.b!=null?Math.round((m.a+m.b)/2):m.a;if(!isNum(TR.lat[k]))return;
    var ico=L.divIcon({className:"momico",html:'<span title="'+esc(m.t)+'">'+m.ic+'</span>',iconSize:[26,26],iconAnchor:[13,13]});
    var mk2=L.marker([TR.lat[k],TR.lon[k]],{icon:ico,zIndexOffset:900}).addTo(map);mk2.on("click",function(){gotoMoment(m);});MOMM.push(mk2);});
  drawMomentPills();
}
function gotoMoment(m){if(m.b!=null){SEL={a:m.a,b:m.b};drawChart();showSeg();highlightSel();}else{closeSeg();setCursor(m.a,false);var k=m.a;map.setView([TR.lat[k],TR.lon[k]],Math.max(map.getZoom(),14));}}
function drawMomentPills(){var box=$("mks");if(!box)return;box.innerHTML="";if(!SHOWMOM)return;var r=rng();
  MOM.forEach(function(m){var k=m.b!=null?(m.a+m.b)/2:m.a;if(k<r.a||k>r.b)return;var el=document.createElement("span");el.className="mk";el.innerHTML=m.ic+" "+esc(m.lab);el.title=m.t;el.style.left=(CX(k)/CW*100)+"%";el.onclick=function(){gotoMoment(m);};box.appendChild(el);});
  /* 2026-10-08: pigulki momentow nie nachodza na siebie: JEDEN wiersz, przy kolizji rozsuwane w bok (najblizej swojego miejsca na
     wykresie, w granicach ramki); drugi wiersz tylko gdy wszystkie sie nie mieszcza. Telefon: pasek przewijany (bez zmian). */
  if(!box.firstChild||getComputedStyle(box.firstChild).position!=="absolute"){box.style.height="";return;}
  var br=box.getBoundingClientRect(),W=br.width,G=6,its=[].map.call(box.children,function(e){var r=e.getBoundingClientRect();return {e:e,w:r.width,c:(r.left+r.right)/2-br.left};});
  its.sort(function(p,q){return p.c-q.c;});
  var tot=its.reduce(function(s,x){return s+x.w;},0)+G*(its.length-1),i,x=-1e9,lim=W;
  if(tot<=W){
    its.forEach(function(it){it.l=Math.max(it.c-it.w/2,x+G,0);x=it.l+it.w;});
    for(i=its.length-1;i>=0;i--){if(its[i].l+its[i].w>lim)its[i].l=lim-its[i].w;lim=its[i].l-G;}
    its.forEach(function(it){it.e.style.transform="none";it.e.style.left=Math.round(it.l)+"px";it.e.style.top="0";});
    box.style.height="26px";
  }else{var lanes=[];its.forEach(function(it){var l=Math.min(Math.max(it.c-it.w/2,0),W-it.w),L=0;while(lanes[L]!=null&&l<lanes[L]+G)L++;lanes[L]=l+it.w;it.e.style.transform="none";it.e.style.left=Math.round(l)+"px";it.e.style.top=(L*26)+"px";});box.style.height=(lanes.length*26)+"px";}}
/* ---------- odcinek ---------- */
function segStats(a,b){var st=function(arr){var s=0,c=0,mn=Infinity,mx=-Infinity;for(var i=a;i<=b;i++){var v=arr&&arr[i];if(!isNum(v))continue;s+=v;c++;if(v<mn)mn=v;if(v>mx)mx=v;}return c?{avg:s/c,min:mn,max:mx}:null;};
  var asc=0;for(var i=a+1;i<=b;i++){if(isNum(TR.alt[i])&&isNum(TR.alt[i-1])){var d=TR.alt[i]-TR.alt[i-1];if(d>0.3)asc+=d;}}
  return {km:TR.km[b]-TR.km[a],t:TR.t[b]-TR.t[a],pw:st(TR.power),hr:st(TR.hr),wb:st(TR.wbal_pct),spd:st(SPD),cad:st(TR.cad),temp:st(TR.temp),tail:st(TR.tail),asc:asc,gr:TR.km[b]>TR.km[a]?(TR.alt[b]-TR.alt[a])/((TR.km[b]-TR.km[a])*1000)*100:0};}
function segDesc(a,b,S){var L=["Zakres: km "+n(TR.km[a],1)+"–"+n(TR.km[b],1)+" ("+fmtHM(S.t)+", "+n(S.km,1)+" km, +"+Math.round(S.asc)+" m)"];if(S.pw)L.push("moc: śr "+Math.round(S.pw.avg)+" W (max "+Math.round(S.pw.max)+")"+(FTP?", próg "+FTP:""));if(S.hr)L.push("HR: śr "+Math.round(S.hr.avg)+" (max "+Math.round(S.hr.max)+")");if(S.cad)L.push("kadencja: śr "+Math.round(S.cad.avg));if(S.wb)L.push("W'bal: min "+Math.round(S.wb.min)+"%");if(S.spd)L.push("prędkość: śr "+n(S.spd.avg,1)+" km/h");if(S.temp)L.push("temperatura: "+Math.round(S.temp.min)+"–"+Math.round(S.temp.max)+" °C");if(S.tail)L.push("wiatr wzdłuż: śr "+n(S.tail.avg,1)+" m/s ("+(S.tail.avg<0?"pod wiatr":"z plecami")+")");/* 2026-10-08: dla oceny AI - nachylenie, nawierzchnia odcinka i srednie CALEJ jazdy do porownania */if(isNum(S.gr))L.push("nachylenie śr "+n(S.gr,1)+"%");try{var sc={},tot=0;for(var k=a;k<=b;k++){var sk=SURF[k];if(sk){sc[sk]=(sc[sk]||0)+1;tot++;}}if(tot)L.push("nawierzchnia: "+Object.keys(sc).sort(function(x,y){return sc[y]-sc[x];}).map(function(x){return (SLAB[x]||x)+" "+Math.round(sc[x]/tot*100)+"%";}).join(", "));}catch(e){}try{var W=segStats(0,N-1),C=[];if(W.pw)C.push("moc śr "+Math.round(W.pw.avg)+" W");if(W.hr)C.push("HR śr "+Math.round(W.hr.avg));if(W.cad)C.push("kadencja śr "+Math.round(W.cad.avg));if(W.spd)C.push("prędkość śr "+n(W.spd.avg,1)+" km/h");if(C.length)L.push("CAŁA JAZDA dla porównania: "+C.join(", ")+" (odcinek to km "+n(TR.km[a],1)+"–"+n(TR.km[b],1)+" z "+n(TR.km[N-1],1)+")");}catch(e){}return L.join("; ");}
function showSeg(){
  var ss0=$("sg-surf");if(ss0)ss0.remove();
  if(!SEL)return closeSeg();var a=SEL.a,b=SEL.b,S=segStats(a,b);$("sg").style.display="block";
  $("sg-t").textContent="km "+n(TR.km[a],1)+" – "+n(TR.km[b],1);
  $("sg-s").textContent=fmtHM(S.t)+" · "+n(S.km,1)+" km · +"+Math.round(S.asc)+" m · śr. "+n(S.gr,1)+"%";
  $("sg-k").innerHTML=k("moc śr / max",S.pw?Math.round(S.pw.avg)+" / "+Math.round(S.pw.max):"—",S.pw&&FTP?Math.round(S.pw.avg/FTP*100)+"% progu":"")+k("tętno śr / max",S.hr?Math.round(S.hr.avg)+" / "+Math.round(S.hr.max):"—","")+k("zapas min",S.wb?Math.round(S.wb.min)+"%":"—","")+k("prędkość",S.spd?n(S.spd.avg,1):"—","km/h")+k("kadencja",S.cad?Math.round(S.cad.avg):"—","")+k("wiatr",S.tail?(S.tail.avg>0?"+":"")+n(S.tail.avg,1):"—","m/s wzdłuż");
  var sc={},tot=0;for(var q=a;q<=b;q++){if(SURF[q]){sc[SURF[q]]=(sc[SURF[q]]||0)+1;tot++;}}
  if(tot){var ks=Object.keys(sc).sort(function(x,y){return sc[y]-sc[x];});$("sg-k").insertAdjacentHTML("afterend",'<div class="sub" id="sg-surf" style="margin-top:8px"><div style="display:flex;height:8px;border-radius:4px;overflow:hidden">'+ks.map(function(c){return '<div style="width:'+(sc[c]/tot*100)+'%;background:'+SCAT[c]+'"></div>';}).join("")+'</div><div style="margin-top:4px;font-size:13px">'+ks.map(function(c){return '<span style="color:'+SCAT[c]+'">■</span> '+SLAB[c]+' '+Math.round(sc[c]/tot*100)+'%';}).join(" · ")+'</div></div>');}
  $("sg-aiout").innerHTML="";
  $("sg-ai").onclick=function(){var out=$("sg-aiout");out.innerHTML='<div class="ai">Analizuję odcinek…</div>';
    fetch("/api/ride-report/correlate",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({live:segDesc(a,b,S),ride:RKEY})}).then(function(r){return r.json().catch(function(){return null;}).then(function(j){return {r:r,j:j};});}).then(function(o){out.innerHTML='<div class="ai">'+esc((o.j&&o.j.text)?o.j.text:"(błąd: "+((o.j&&o.j.detail)||o.r.status)+")")+'</div>';}).catch(function(){out.innerHTML='<div class="ai">Błąd połączenia z AI.</div>';});};
  $("sg-zoom").onclick=function(){VIEW={a:a,b:b};drawChart();};
  $("sg-cmp").onclick=function(){CMP.push({a:a,b:b,S:S});showCmp();};
  $("sg-x").onclick=closeSeg;
}
function closeSeg(){SEL=null;$("sg").style.display="none";var ss=$("sg-surf");if(ss)ss.remove();if(map&&hl){map.removeLayer(hl);map.removeLayer(hlc);hl=hlc=null;}if(N)drawChart();}
function showCmp(){var o=$("sg-cmpout");if(!CMP.length){o.innerHTML="";return;}var rows=[["czas",function(c){return fmtHM(c.S.t);}],["km",function(c){return n(c.S.km,1);}],["w górę",function(c){return Math.round(c.S.asc)+" m";}],["moc śr",function(c){return c.S.pw?Math.round(c.S.pw.avg)+" W":"—";}],["tętno śr",function(c){return c.S.hr?Math.round(c.S.hr.avg):"—";}],["moc/tętno",function(c){return c.S.pw&&c.S.hr?n(c.S.pw.avg/c.S.hr.avg,2):"—";}],["km/h",function(c){return c.S.spd?n(c.S.spd.avg,1):"—";}]];
  o.innerHTML='<div class="sub" style="margin-top:10px;display:flex;justify-content:space-between"><b>Porównanie</b><a class="link" id="cmpclr">wyczyść</a></div><table style="border-collapse:collapse;font-size:13px;width:100%;margin-top:4px"><tr><td></td>'+CMP.map(function(c){return '<td style="text-align:right;font-weight:600;padding:2px 4px">km '+n(TR.km[c.a],0)+'–'+n(TR.km[c.b],0)+'</td>';}).join("")+'</tr>'+rows.map(function(r){return '<tr style="border-top:1px solid var(--line)"><td style="color:var(--ink2);padding:3px 0">'+r[0]+'</td>'+CMP.map(function(c){return '<td style="text-align:right;padding:3px 4px;font-variant-numeric:tabular-nums">'+r[1](c)+'</td>';}).join("")+'</tr>';}).join("")+'</table>';
  $("cmpclr").onclick=function(){CMP=[];showCmp();};}

window.__RJapi={fit:function(){if(!N||!map)return;if(SEL)highlightSel();else fitAll();},inval:function(){if(map)map.invalidateSize();},data:function(){return D;}};
loadRides();
})();
