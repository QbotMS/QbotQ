/* raport-pogoda-viz.js v3 — graficzny przebieg dnia w zakladce Pogoda (Analiza trasy).
   wxDayViz(weather, chart): weather = details.weather (windows co 30 min), chart = DATA.chart (ele: [[km, m], ...]).
   Uklad: kafelki podsumowania | niebo (ikony) | temperatura do ubioru na tle stref ubioru + zapas + delikatny
   profil wysokosci | deszcz (zwiniety, gdy sucho) | wiatr wzgledem jazdy + ochrona od wiatru | czas + km. */
(function(){
"use strict";
function f(v,d){ v=Number(v); return isFinite(v)? v.toFixed(d==null?0:d).replace(".",",") : "—"; }
function num(v){ v=Number(v); return (v===null||v===undefined||!isFinite(v))? null : v; }
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
var ZONES=[[-30,5,"#7F77DD","zimowo"],[5,10,"#378ADD","ocieplenie + kurtka"],[10,15,"#1D9E75","długi rękaw + kamizelka"],
           [15,18,"#639922","umiarkowanie: merino, rękawki"],[18,22,"#EF9F27","krótki + rękawki na start"],[22,45,"#D85A30","letnio"]];
function zoneOf(t){ for(var i=0;i<ZONES.length;i++){ if(t<ZONES[i][1]) return ZONES[i]; } return ZONES[ZONES.length-1]; }

function sunIcon(cx,cy){ var r=7,o='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" style="fill:#EF9F27"/>';
  for(var k=0;k<8;k++){ var a=k*Math.PI/4, x1=cx+Math.cos(a)*(r+3), y1=cy+Math.sin(a)*(r+3), x2=cx+Math.cos(a)*(r+6), y2=cy+Math.sin(a)*(r+6);
    o+='<line x1="'+x1.toFixed(1)+'" y1="'+y1.toFixed(1)+'" x2="'+x2.toFixed(1)+'" y2="'+y2.toFixed(1)+'" style="stroke:#EF9F27;stroke-width:2;stroke-linecap:round"/>'; }
  return o; }
function cloudIcon(cx,cy,sun){ var o=sun?'<circle cx="'+(cx-6)+'" cy="'+(cy-5)+'" r="6" style="fill:#EF9F27"/>':'';
  return o+'<circle cx="'+(cx-5)+'" cy="'+(cy+1)+'" r="6" style="fill:var(--muted)"/><circle cx="'+(cx+3)+'" cy="'+(cy-2)+'" r="7.5" style="fill:var(--muted)"/>'+
    '<rect x="'+(cx-11)+'" y="'+(cy+1)+'" width="21" height="6" rx="3" style="fill:var(--muted)"/>'; }
function rainIcon(cx,cy){ var o=cloudIcon(cx,cy-4,false);
  for(var k=-1;k<=1;k++) o+='<line x1="'+(cx+k*6)+'" y1="'+(cy+6)+'" x2="'+(cx+k*6-2)+'" y2="'+(cy+12)+'" style="stroke:var(--blue);stroke-width:2;stroke-linecap:round"/>';
  return o; }

window.wxDayViz = function(w, chart){
  var W=(w&&w.windows)||[];
  if(W.length<2) return "";
  var key=W.some(function(v){ return num(v.na_rowerze)!=null; })?"na_rowerze":"temp";
  var tk=w.termika||{}, lo80=num((tk.niepewnosc_80proc||[])[0]);
  var n=W.length, X0=86, X1=958, st=(X1-X0)/(n-1), x=function(i){ return X0+i*st; };
  // --- podsumowanie ---
  var bs=W.map(function(v){ return num(v[key]); }).filter(function(v){ return v!=null; });
  var bmin=Math.min.apply(null,bs), bmax=Math.max.apply(null,bs), b0=num(W[0][key]), bN=num(W[n-1][key]);
  var cc=W.map(function(v){ return num(v.chmury_pct)||0; }), ccAvg=cc.reduce(function(a,b){return a+b;},0)/n;
  var pmax=Math.max.apply(null,W.map(function(v){ return num(v.opad_prob)||0; })), mmSum=W.reduce(function(a,v){ return a+(num(v.opad_mm)||0); },0);
  var wmax=Math.max.apply(null,W.map(function(v){ return num(v.wiatr_10m)!=null?num(v.wiatr_10m):Math.abs(num(v.wiatr_ms)||0); }));
  var gmax=Math.max.apply(null,W.map(function(v){ return num(v.porywy_max)||0; }));
  var onW=W.filter(function(v){ return v.wiatr_ochrona==="na_sobie"; }).length, handW=W.filter(function(v){ return v.wiatr_ochrona==="pod_reka"; }).length;
  var sl=w.slonce||{};
  var tile=function(ic,lab,val,sub){ return '<div style="background:var(--well);border-radius:10px;padding:9px 12px;min-width:0">'+
    '<div style="font-size:12px;color:var(--ink2)">'+ic+' '+lab+'</div><div style="font-size:19px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+val+'</div>'+
    '<div style="font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+sub+'</div></div>'; };
  var sky=ccAvg<20?"bezchmurnie":(ccAvg<50?"przejaśnienia":(ccAvg<80?"pochmurno":"zachmurzenie"));
  var wsub=onW?("kamizelka na sobie: "+onW*30+" min"):(handW?"kamizelka pod ręką":"kamizelka niepotrzebna");
  var head='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:2px 0 12px">'+
    tile("&#128085;","Do ubioru",f(b0)+" → "+f(bmax)+(Math.round(bN)!==Math.round(bmax)?" → "+f(bN):"")+"°C",zoneOf(bmin)[3]+(zoneOf(bmin)!==zoneOf(bmax)?" → "+zoneOf(bmax)[3]:""))+
    tile("&#9728;&#65039;","Niebo",sky,"UV "+f(sl.uv_max,1)+(sl.zachod?" · zachód "+esc(sl.zachod):""))+
    tile("&#127788;&#65039;","Wiatr","do "+f(wmax,1)+" m/s",wsub+(gmax>=8?" · porywy "+f(gmax):""))+
    tile("&#9748;","Deszcz",(pmax<10&&mmSum<0.1)?"sucho":(f(mmSum,1)+" mm"),"maks. "+f(pmax)+"% szansy")+'</div>';
  // --- skala temperatury ---
  var tv=[]; W.forEach(function(v){ [v.temp,v[key]].forEach(function(t){ t=num(t); if(t!=null) tv.push(t); }); });
  var tmin=Math.floor(Math.min.apply(null,tv)+(lo80||0)-1), tmax=Math.ceil(Math.max.apply(null,tv)+1);
  if(tmax-tmin<8){ var m=(tmax+tmin)/2; tmin=Math.floor(m-4); tmax=Math.ceil(m+4); }
  var TY0=58, TY1=246, ty=function(t){ return TY1-(t-tmin)/(tmax-tmin)*(TY1-TY0); };
  var o=[], T=function(s){ o.push(s); };
  var mut='style="fill:var(--muted);font-size:12px"', ink='style="fill:var(--ink);font-size:14px;font-weight:600"';
  T('<svg viewBox="0 0 1000 412" width="100%" role="img" aria-label="Przebieg pogody w czasie jazdy" style="display:block">');
  // niebo
  T('<text x="0" y="30" '+mut+'>niebo</text>');
  W.forEach(function(v,i){ var c=num(v.chmury_pct)||0, p=num(v.opad_prob)||0, cx=x(i), cy=26;
    T((p>=40||(num(v.opad_mm)||0)>=0.2)?rainIcon(cx,cy):(c<25?sunIcon(cx,cy):cloudIcon(cx,cy,c<70)));
    T('<rect x="'+(cx-st/2)+'" y="8" width="'+st+'" height="38" style="fill:transparent"><title>'+esc(v.okno)+' · zachmurzenie '+f(c)+'% · opad '+f(p)+'%</title></rect>'); });
  // strefy ubioru
  T('<text x="0" y="'+(TY0+10)+'" '+mut+'>temp.</text>');
  ZONES.forEach(function(z){ var a=Math.max(z[0],tmin), b=Math.min(z[1],tmax); if(b<=a) return;
    T('<rect x="'+(X0-st/2)+'" y="'+ty(b)+'" width="'+(X1-X0+st)+'" height="'+(ty(a)-ty(b))+'" style="fill:'+z[2]+';fill-opacity:.09"/>');
    if(ty(a)-ty(b)>=16) T('<text x="'+(X1+st/2-6)+'" y="'+(ty(b)+14)+'" text-anchor="end" style="fill:'+z[2]+';font-size:12px;opacity:.9">'+z[3]+'</text>');
    if(z[0]>tmin) T('<text x="'+(X0-st/2-6)+'" y="'+(ty(z[0])+4)+'" text-anchor="end" '+mut+'>'+z[0]+'°</text>'); });
  // delikatny profil wysokosci (dolne ~30% pola temperatury)
  var E=(chart&&chart.ele)||[], kms=W.map(function(v){ return num(v.km_od); });
  if(E.length>2 && kms.every(function(k){ return k!=null; })){
    var kx=function(km){ if(km<=kms[0]) return x(0); for(var i=1;i<n;i++){ if(km<=kms[i]) return x(i-1)+(km-kms[i-1])/((kms[i]-kms[i-1])||1)*st; }
      var last=num(W[n-1].km_do)||kms[n-1]; return Math.min(X1+st/2, x(n-1)+(km-kms[n-1])/((last-kms[n-1])||1)*st/2); };
    var eMin=num(chart.ele_min), eMax=num(chart.ele_max);
    if(eMin==null||eMax==null){ eMin=Math.min.apply(null,E.map(function(q){return q[1];})); eMax=Math.max.apply(null,E.map(function(q){return q[1];})); }
    var span=Math.max(eMax-eMin,30), EY1=TY1, EY0=TY1-(TY1-TY0)*0.3, ey=function(h){ return EY1-(h-eMin)/span*(EY1-EY0); };
    var d="M "+kx(E[0][0]).toFixed(1)+" "+EY1, stp=Math.max(1,Math.floor(E.length/300));
    for(var q=0;q<E.length;q+=stp) d+=" L "+kx(E[q][0]).toFixed(1)+" "+ey(E[q][1]).toFixed(1);
    d+=" L "+kx(E[E.length-1][0]).toFixed(1)+" "+ey(E[E.length-1][1]).toFixed(1)+" L "+kx(E[E.length-1][0]).toFixed(1)+" "+EY1+" Z";
    T('<path d="'+d+'" style="fill:var(--ink);fill-opacity:.06;stroke:var(--ink);stroke-opacity:.18;stroke-width:1"/>');
    T('<text x="'+(X0-st/2+4)+'" y="'+(EY1-4)+'" style="fill:var(--muted);font-size:11px;opacity:.8">profil '+f(eMin)+'–'+f(eMax)+' m</text>');
  }
  // zapas (chlodny wariant) + linie
  if(key==="na_rowerze" && lo80!=null){
    var up=[], dn=[]; W.forEach(function(v,i){ var t=num(v[key]); if(t!=null){ up.push(x(i)+","+ty(t)); dn.unshift(x(i)+","+ty(t+lo80)); } });
    if(up.length>1){ T('<polygon points="'+up.concat(dn).join(" ")+'" style="fill:var(--accent);fill-opacity:.13"><title>chłodny wariant: w 1 jeździe na 10 bywa o '+f(Math.abs(lo80),1)+'°C chłodniej</title></polygon>');
      T('<text x="'+(x(Math.min(1,n-1))+4)+'" y="'+(ty(num(W[Math.min(1,n-1)][key])+lo80)+15)+'" '+mut+'>chłodny wariant (1 jazda na 10)</text>'); }
  }
  var line=function(k,sty){ var pts=[]; W.forEach(function(v,i){ var t=num(v[k]); if(t!=null) pts.push(x(i)+","+ty(t)); });
    if(pts.length>1) T('<polyline points="'+pts.join(" ")+'" fill="none" '+sty+'/>'); };
  if(key==="na_rowerze") line("temp",'style="stroke:var(--muted);stroke-width:1.6;stroke-dasharray:5 4"');
  line(key,'style="stroke:var(--accent);stroke-width:3.5;stroke-linejoin:round;stroke-linecap:round"');
  var iMin=0,iMax=0; W.forEach(function(v,i){ if(num(v[key])!=null){ if(num(v[key])<num(W[iMin][key])) iMin=i; if(num(v[key])>num(W[iMax][key])) iMax=i; } });
  [0,iMin,iMax,n-1].filter(function(v,i,a){ return a.indexOf(v)===i; }).forEach(function(i){ var t=num(W[i][key]); if(t==null) return;
    T('<circle cx="'+x(i)+'" cy="'+ty(t)+'" r="5" style="fill:var(--accent)"/>');
    T('<text x="'+x(i)+'" y="'+(ty(t)-11)+'" text-anchor="middle" '+ink+'>'+f(t,1)+'°</text>'); });
  W.forEach(function(v,i){ T('<rect x="'+(x(i)-st/2)+'" y="'+TY0+'" width="'+st+'" height="'+(TY1-TY0)+'" style="fill:transparent"><title>'+esc(v.okno)+
    ' · prognoza '+f(v.temp,1)+'°'+(key==="na_rowerze"?' · do ubioru '+f(v[key],1)+'° ('+zoneOf(num(v[key])||0)[3]+')':'')+'</title></rect>'); });
  // deszcz
  var RY=290;
  T('<text x="0" y="'+(RY-6)+'" '+mut+'>deszcz</text>');
  if(pmax<10 && mmSum<0.1){
    T('<text x="'+(X0-st/2)+'" y="'+(RY-6)+'" style="fill:var(--ink2);font-size:13px">bez opadu przez całą jazdę (maks. '+f(pmax)+'% szansy)</text>');
  } else {
    T('<line x1="'+(X0-st/2)+'" x2="'+(X1+st/2)+'" y1="'+(RY+.5)+'" y2="'+(RY+.5)+'" style="stroke:var(--muted);stroke-opacity:.35"/>');
    W.forEach(function(v,i){ var p=num(v.opad_prob)||0, mm=num(v.opad_mm)||0, h=p/100*30;
      if(p>0) T('<rect x="'+(x(i)-9)+'" y="'+(RY-Math.max(h,1.5))+'" width="18" height="'+Math.max(h,1.5)+'" rx="3" style="fill:var(--blue);fill-opacity:'+(0.3+p/140).toFixed(2)+'"><title>'+esc(v.okno)+' opad '+f(p)+'% · '+f(mm,1)+' mm</title></rect>');
      if(p>=20) T('<text x="'+x(i)+'" y="'+(RY-h-4)+'" text-anchor="middle" '+mut+'>'+f(p)+'%</text>');
      if(mm>=0.1) T('<text x="'+x(i)+'" y="'+(RY+13)+'" text-anchor="middle" '+mut+'>'+f(mm,1)+'</text>'); });
  }
  // wiatr + ochrona
  var WY=334;
  T('<text x="0" y="'+(WY+4)+'" '+mut+'>wiatr</text><text x="0" y="'+(WY+22)+'" '+mut+'>m/s</text>');
  var runs=[], cur=null;
  W.forEach(function(v,i){ var q=v.wiatr_ochrona||null; if(cur&&cur.q===q) cur.b=i; else { cur={q:q,a:i,b:i}; runs.push(cur); } });
  runs.forEach(function(r){ if(!r.q) return; var c=r.q==="na_sobie"?"--bad":"--warn";
    T('<text x="'+((x(r.a)+x(r.b))/2)+'" y="'+(WY-19)+'" text-anchor="middle" style="fill:var('+c+');font-size:12px;font-weight:600">'+(r.q==="na_sobie"?"kamizelka na sobie":"kamizelka pod ręką")+'</text>'); });
  W.forEach(function(v,i){ var a=num(v.wiatr_ms); if(a==null) return;
    var sp=num(v.wiatr_10m), c=a<-0.8?"--bad":(a>0.8?"--good":"--muted"), cx=x(i), d=a<0?-1:1, L=Math.max(10,Math.min(st*0.75,Math.abs(a)*12+(sp||0)*3));
    var q=v.wiatr_ochrona, bg=q==="na_sobie"?"--bad":(q==="pod_reka"?"--warn":c);
    T('<rect x="'+(cx-st/2+1.5)+'" y="'+(WY-12)+'" width="'+(st-3)+'" height="24" rx="5" style="fill:var('+bg+');fill-opacity:'+(q?.18:.10)+'"/>');
    T('<line x1="'+(cx-d*L/2)+'" x2="'+(cx+d*L/2)+'" y1="'+WY+'" y2="'+WY+'" style="stroke:var('+c+');stroke-width:3;stroke-linecap:round"/>');
    T('<polygon points="'+(cx+d*L/2+d*7)+','+WY+' '+(cx+d*L/2)+','+(WY-6)+' '+(cx+d*L/2)+','+(WY+6)+'" style="fill:var('+c+')"/>');
    T('<text x="'+cx+'" y="'+(WY+26)+'" text-anchor="middle" '+mut+'>'+f(sp!=null?sp:Math.abs(a),1)+'</text>');
    T('<rect x="'+(cx-st/2)+'" y="'+(WY-14)+'" width="'+st+'" height="44" style="fill:transparent"><title>'+esc(v.okno)+' · '+(a<-0.8?'w twarz ':(a>0.8?'w plecy ':'boczny / słaby '))+f(Math.abs(a),1)+' m/s'+
      (sp!=null?' · wiatr '+f(sp,1)+' m/s':'')+(num(v.porywy_max)!=null?' · porywy '+f(v.porywy_max,1):'')+(q==="na_sobie"?' · KAMIZELKA NA SOBIE':(q==="pod_reka"?' · kamizelka pod ręką':''))+'</title></rect>'); });
  // os
  var every=n<=10?1:(n<=16?2:3);
  W.forEach(function(v,i){ if(i%every) return;
    T('<text x="'+x(i)+'" y="386" text-anchor="middle" style="fill:var(--ink);font-size:13px">'+esc(v.okno)+'</text>');
    if(v.km_od!=null) T('<text x="'+x(i)+'" y="404" text-anchor="middle" '+mut+'>'+f(v.km_od)+' km</text>'); });
  T('</svg>');
  var lg='<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink2);margin:0 0 2px">'+
    (key==="na_rowerze"?'<span style="display:flex;align-items:center;gap:6px"><span style="width:18px;height:3px;background:var(--accent);border-radius:2px"></span>do ubioru (Twoje Karoo)</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:14px;height:10px;background:var(--accent);opacity:.3;border-radius:2px"></span>zapas</span>':'')+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:18px;border-top:2px dashed var(--muted)"></span>prognoza</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:14px;height:10px;background:var(--ink);opacity:.15;border-radius:2px"></span>profil trasy</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="color:var(--bad)">&#9664;</span>wiatr w twarz <span style="color:var(--good);margin-left:4px">&#9654;</span>w plecy</span></div>';
  var note=(key==="na_rowerze"&&tk.kalibracja_jazd)?'<div style="font-size:12px;color:var(--muted);margin:2px 0 12px">„Do ubioru” = prognoza poprawiona wg Twojego Karoo ('+
    esc(tk.kalibracja_jazd)+' jazd). Strefy ubioru są orientacyjne — dobór konkretnych rzeczy robi doradca.</div>':'';
  return '<div class="wx-day">'+head+lg+o.join("")+note+'</div>';
};
})();
