/* pogoda-punkt-viz-test.js (21.10 TEST: granice dni + etykiety bez nachodzenia; baza v15) (2026-10-16: wiersz droga = ciagle paski zagrozen; v10: opcje wxPointViz(G,{W:szerokosc viewBox, compact:bez kafelkow, dt:godzin na punkt}) dla dolnego paska; v9: rodzaj opadu window.wxOpadTyp; v8: pigulki wl./wyl. linii (window.wxHid, klasy h-*), ciemniejsze pory dnia; v6: wiatr na wspolnym wykresie z temperatura, ciemniejsze pory dnia; v4: bloki swit/zmierzch/noc w tle (window.wxSunFor), wykres wiatru: predkosc + pasmo porywow + kierunek; v3 2026-10-14: odczuwalna, UTCI w jezdzie, 'na rowerze', WBGT -- jak w silniku tras) — „Warunki godzina po godzinie” dla PUNKTU (strona Pogoda), w jezyku wizualnym Analizy trasy
   (raport-pogoda-viz.js: kafelki, ikony nieba, temperatura na tle stref ubioru, slupki deszczu, wiatr). Wspolne elementy z window.wxVizKit.
   wxPointViz(godziny): godziny = /api/pogoda/warunki .godziny bez przeszlosci (t, iso, temp, odcz, wiatr, kier, skad, porywy, opad, szansa,
   chmury, dzien, mgla, lod, nawierzchnia, widocznosc, grunt). Wiatr: strzalka = dokad wieje; kolor wg porywow (progi Trenera 8 / 13 m/s). */
(function(){
"use strict";
window.wxHid=window.wxHid||{};
/* rodzaj opadu (16.10): kod WMO z modelu (kod), snieg cm/h, opad mm/h, temp. -> {n: nazwa, z: "wrn"|"bad", marz: 1 gdy marznacy} albo null */
window.wxOpadTyp=function(h){ var k=+h.kod||0, o=+h.opad||0, s=+h.snieg||0, t=h.temp==null?null:+h.temp;
  if(k>=96) return {n:"burza z gradem",z:"bad"}; if(k===95) return {n:"burza",z:"bad"};
  if(k===56||k===57) return {n:"marznąca mżawka",z:"bad",marz:1}; if(k===66||k===67) return {n:"marznący deszcz",z:"bad",marz:1};
  if(s>0.05&&((k>=51&&k<=67)||(k>=80&&k<=82))) return {n:"deszcz ze śniegiem",z:"bad"};
  if(s>0.05||(k>=71&&k<=77)||k===85||k===86) return {n:(k===85||k===86)?"przelotny śnieg":"śnieg",z:s>=1?"bad":"wrn"};
  if(o<0.1&&k<51) return null;
  if(t!=null&&t<=0&&o>=0.1) return {n:"marznący opad",z:"bad",marz:1};
  if(k>=51&&k<=55) return {n:"mżawka",z:"wrn"};
  if(k===82) return {n:"ulewa",z:"bad"}; if(k>=80&&k<=81) return {n:"przelotny deszcz",z:"wrn"};
  if(o>=0.1||(k>=61&&k<=65)) return {n:"deszcz",z:o>=1?"bad":"wrn"};
  return null; };
window.wxTog=function(el,k){ var H=window.wxHid; H[k]=!H[k]; var d=el.closest(".wx-day"); if(d)d.classList.toggle("h-"+k,H[k]); el.classList.toggle("off",H[k]); };
(function(){ if(document.getElementById("wxpcss"))return; var c=document.createElement("style"); c.id="wxpcss";
  c.textContent=".wx-day.h-temp [data-l=temp],.wx-day.h-odcz [data-l=odcz],.wx-day.h-wiatr [data-l=wiatr],.wx-day.h-por [data-l=por]{display:none}"+
   ".wx-pills{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 6px}.wx-pills .chip{cursor:pointer;user-select:none}.wx-pills .chip.off{opacity:.4;text-decoration:line-through}"+
   ".wx-leg{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--ink2);margin-left:6px}.wx-leg b{width:12px;height:10px;border-radius:2px;display:inline-block}";
  document.head.appendChild(c); })();
window.wxPointViz = function(G,opt){
  opt=opt||{}; var W=opt.W||1000, DT=opt.dt||1;
  var K=window.wxVizKit; if(!K||!G||G.length<2) return "";
  var f=K.f, num=K.num, esc=K.esc, ZONES=K.ZONES, zoneOf=K.zoneOf;
  var n=G.length, X0=86, X1=W-(opt.padR||42), st=(X1-X0)/(n-1), x=function(i){ return X0+i*st; };
  var vals=function(k){ return G.map(function(h){ return num(h[k]); }).filter(function(v){ return v!=null; }); };
  var tA=vals("temp"), oA=vals("odcz"), all=tA.concat(oA);
  var mmSum=G.reduce(function(a,h){ return a+(num(h.opad)||0); },0), pmax=Math.max.apply(null,G.map(function(h){ return (num(h.szansa)||0)*100; }));
  var wmax=Math.max.apply(null,vals("wiatr").concat([0])), gmax=Math.max.apply(null,vals("porywy").concat([0]));
  var cAvg=vals("chmury").reduce(function(a,b){return a+b;},0)/Math.max(1,vals("chmury").length);
  var hrs=function(fn){ var a=G.filter(fn); return a.length?a[0].t+(a.length>1?"–"+a[a.length-1].t:""):null; };
  var mz=hrs(function(h){var q=window.wxOpadTyp(h);return !!(q&&q.marz);}), mg=hrs(function(h){return h.mgla===2;}), ld=hrs(function(h){return h.lod>=2;}), bl=hrs(function(h){return h.nawierzchnia===2;});
  var tile=function(ic,lab,val,sub,c){ return '<div style="background:'+(c?'var(--'+c+'-bg)':'var(--well)')+';border-radius:10px;padding:9px 12px;min-width:0">'+
    '<div style="font-size:12px;color:'+(c?'var(--'+c+')':'var(--ink2)')+'">'+ic+' '+lab+'</div><div style="font-size:19px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+val+'</div>'+
    '<div style="font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+sub+'</div></div>'; };
  var tmn=Math.min.apply(null,tA), tmx=Math.max.apply(null,tA), omn=Math.min.apply(null,oA.length?oA:tA);
  var risk=[mz?"marznący opad "+mz:null, mg?"mgła "+mg:null, ld?"oblodzenie "+ld:null, bl?"błoto "+bl:null].filter(Boolean);
  var head=opt.compact?'':'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:2px 0 12px">'+
    (function(){ var nr=vals("na_rowerze"), nmn=nr.length?Math.min.apply(null,nr):omn, nmx=nr.length?Math.max.apply(null,nr):omn;
      return tile("&#127777;&#65039;","Temperatura",f(tmn)+" … "+f(tmx)+"°C","na rowerze "+f(nmn)+"…"+f(nmx)+"°C · "+zoneOf(nmn)[3]+" · odczuwalna od "+f(omn)+"°C"); })()+
    tile("&#9728;&#65039;","Niebo",cAvg<20?"bezchmurnie":(cAvg<50?"przejaśnienia":(cAvg<80?"pochmurno":"zachmurzenie")),"średnio "+f(cAvg)+"% chmur")+
    tile("&#127788;&#65039;","Wiatr","do "+f(wmax,1)+" m/s","porywy do "+f(gmax,1)+" m/s",gmax>=13?"bad":(gmax>=8?"warn":null))+
    tile("&#9748;","Deszcz",(pmax<10&&mmSum<0.1)?"sucho":(f(mmSum,1)+" mm"),"maks. "+f(pmax)+"% szansy",pmax>=40?"warn":null)+
    (risk.length?tile("&#9888;&#65039;","Uwaga",risk[0],risk.slice(1).join(" · ")||"na drodze","warn"):"")+'</div>';
  var tmin=Math.floor(Math.min.apply(null,all)-1), tmax=Math.ceil(Math.max.apply(null,all)+1);
  if(tmax-tmin<8){ var m=(tmax+tmin)/2; tmin=Math.floor(m-4); tmax=Math.ceil(m+4); }
  var MINI=!!opt.mini, VH=opt.VH||(MINI?250:400), TY0=MINI?44:58, TY1=MINI?150:226, FSq=opt.fs||1, AXq=MINI?206+50*FSq:374, ty=function(t){ return TY1-(t-tmin)/(tmax-tmin)*(TY1-TY0); };
  var o=[], T=function(s){ o.push(s); };
  var mut='style="fill:var(--muted);font-size:12px"', ink='style="fill:var(--ink);font-size:14px;font-weight:600"';
  T('<svg data-w="'+W+'" data-x0="'+X0+'" data-x1="'+X1+'" data-n="'+n+'" viewBox="0 0 '+W+' '+VH+'" width="100%" role="img" aria-label="Warunki godzina po godzinie" style="display:block">');
  // tlo: swit / zmierzch / noc (bloki pod cala wysokoscia wykresu); pora dnia ze slonca w punkcie (window.wxSunFor) albo z flagi dzien
  var SUN=window.wxSunFor, PH={swit:"#C98A1E",zmierzch:"#B8522A",noc:"#000"}, PO={swit:.16,zmierzch:.16,noc:.30};
  var NQ=4*DT;
  G.forEach(function(h,i){ var d=new Date(h.iso).getTime(), s2=SUN?SUN(new Date(h.iso)):null, x0=x(i)-st/2;
    for(var q=0;q<NQ;q++){ var t=d-DT*1800e3+(q+0.5)*900e3, ph=null;   /* komorka godziny = h-30..h+30 min, 4 cwiartki po 15 min */
      if(s2){ var sr=s2[0].getTime(), ss=s2[1].getTime(); ph=(t>=sr-1800e3&&t<sr+3600e3)?"swit":((t>=ss-3600e3&&t<ss+1800e3)?"zmierzch":((t<sr||t>=ss)?"noc":null)); }
      else if(h.dzien===0) ph="noc";
      if(ph) T('<rect x="'+(x0+q*st/NQ)+'" y="4" width="'+(st/NQ+1.2)+'" height="'+(MINI?AXq-15*FSq-4:348)+'" style="fill:'+PH[ph]+';fill-opacity:'+PO[ph]+'"><title>'+esc(h.t)+' · '+ph+'</title></rect>'); } });
  // 21.10: granica dni = pionowa linia o polnocy (bez przechodzenia przez podpisy godzin)
  var NDS=G.map(function(h,i){ return i>0&&h.iso.slice(0,10)!==G[i-1].iso.slice(0,10); }), sepX=function(i){ return DT>1?x(i)-st/2:x(i); };
  NDS.forEach(function(v2,i){ if(!v2) return; var sx=sepX(i);
    T('<line x1="'+sx+'" x2="'+sx+'" y1="4" y2="'+(AXq-15*FSq)+'" style="stroke:var(--ink2);stroke-opacity:.65;stroke-width:1.6"><title>północ</title></line>'+
      '<line x1="'+sx+'" x2="'+sx+'" y1="'+(AXq+4*FSq)+'" y2="'+(AXq+20*FSq)+'" style="stroke:var(--ink2);stroke-opacity:.65;stroke-width:1.6"/>'); });
  // 21.10: etykiety bez nachodzenia -- kazdy podpis zajmuje prostokat; kolejny wchodzi tylko na wolne miejsce
  var LB=[], bx=function(xc,yb,txt,fz,an){ var w=String(txt).length*fz*0.62*FSq, hh=fz*FSq, xa=an==="start"?xc:(an==="end"?xc-w:xc-w/2); return [xa-3,yb-hh,xa+w+3,yb+3]; },
    free=function(b){ for(var k=0;k<LB.length;k++){ var c=LB[k]; if(b[0]<c[2]&&c[0]<b[2]&&b[1]<c[3]&&c[1]<b[3]) return false; } return true; },
    tryL=function(b){ if(!free(b)) return false; LB.push(b); return true; };
  (function(){ var a=0,b=0; G.forEach(function(h,i){ if(num(h.temp)!=null){ if(h.temp<G[a].temp) a=i; if(h.temp>G[b].temp) b=i; } });
    [0,a,b,n-1].filter(function(v2,i,q){ return q.indexOf(v2)===i; }).forEach(function(i){ var t=num(G[i].temp); if(t==null) return;
      LB.push(bx(x(i),ty(t)-11,f(t,1)+"°",14,"middle")); LB.push([x(i)-7,ty(t)-7,x(i)+7,ty(t)+7]); }); })();   /* temperatury maja pierwszenstwo */
  // niebo (noc: ksiezyc)
  T('<text x="0" y="30" '+mut+'>niebo</text>');
  G.forEach(function(h,i){ var c=num(h.chmury)||0, p=(num(h.szansa)||0)*100, cx=x(i), cy=26, s=Math.min(1,st/30);
    var ic=h.mgla===2?'<g style="stroke:#c3c9d0;stroke-width:2.4;stroke-linecap:round"><line x1="-9" y1="-5" x2="9" y2="-5"/><line x1="-7" y1="0" x2="10" y2="0"/><line x1="-10" y1="5" x2="7" y2="5"/></g>':(p>=40||(num(h.opad)||0)>=0.2)?K.rainIcon(0,0):(h.dzien===0?(c<70?'<circle cx="-1" cy="0" r="7" style="fill:var(--muted)"/><circle cx="3" cy="-3" r="6.5" style="fill:var(--glass,var(--card))"/>':K.cloudIcon(0,0,false)):(c<25?K.sunIcon(0,0):K.cloudIcon(0,0,c<70)));
    T('<g transform="translate('+cx+','+cy+') scale('+s.toFixed(2)+')">'+ic+'</g>');
    T('<rect x="'+(cx-st/2)+'" y="8" width="'+st+'" height="38" style="fill:transparent"><title>'+esc(h.t)+' · chmury '+f(c)+'% · szansa opadu '+f(p)+'%</title></rect>'); });
  // 18.10: mgla -- szara poswiata na wykresie temperatury + podpis (gesta mgla = widocznosc < 1 km)
  (function(){ var i0=-1; G.forEach(function(h,i){ var on=h.mgla===2||(num(h.widocznosc)!=null&&num(h.widocznosc)<1000);
      if(on&&i0<0) i0=i; if((!on||i===n-1)&&i0>=0){ var i1=on?i:i-1, xa=x(i0)-st/2, xb=x(i1)+st/2,
        vmin=Math.min.apply(null,G.slice(i0,i1+1).map(function(y){return num(y.widocznosc)||50000;}));
        T('<rect x="'+xa+'" y="'+TY0+'" width="'+(xb-xa)+'" height="'+(TY1-TY0)+'" style="fill:#c3c9d0;fill-opacity:.16"><title>mgła '+esc(G[i0].t)+'–'+esc(i1+1<n?G[i1+1].t:G[i1].t)+' · widoczność do '+(vmin<1000?Math.round(vmin/50)*50+' m':f(vmin/1000,1)+' km')+'</title></rect>'+
          '<text x="'+(xa+3)+'" y="'+(TY0+13)+'" style="fill:#c3c9d0;font-size:11px;font-weight:700">mgła</text>'); i0=-1; } }); })();
  // strefy ubioru + temperatura i odczuwalna
  T('<text x="0" y="'+(TY0+10)+'" '+mut+'>temp.</text><text x="0" y="'+(TY0+26)+'" style="fill:var(--blue);font-size:12px">+ wiatr</text>');
  if(opt.padR) T('<rect x="'+(X1+st/2+2)+'" y="'+TY0+'" width="'+(W-X1-st/2-4)+'" height="'+(TY1-TY0)+'" rx="6" style="fill:var(--card);fill-opacity:.92"/>');   /* tlo pod opisy stref */
  ZONES.forEach(function(z){ var a=Math.max(z[0],tmin), b=Math.min(z[1],tmax); if(b<=a) return;
    T('<rect x="'+(X0-st/2)+'" y="'+ty(b)+'" width="'+(X1-X0+st)+'" height="'+(ty(a)-ty(b))+'" style="fill:'+z[2]+';fill-opacity:.09"/>');
    if(opt.padR) T('<rect x="'+(X1+st/2+2)+'" y="'+(ty(b)+1)+'" width="'+(W-X1-st/2-4)+'" height="'+Math.max(0,ty(a)-ty(b)-2)+'" rx="4" style="fill:'+z[2]+';fill-opacity:.22"/>');
    if(ty(a)-ty(b)>=16) T('<text x="'+(opt.padR?X1+st/2+10:X1+st/2-6)+'" y="'+(ty(b)+14)+'" text-anchor="'+(opt.padR?'start':'end')+'" style="fill:'+z[2]+';font-size:12px;font-weight:600;opacity:1">'+z[3]+'</text>');
    if(z[0]>tmin) T('<text x="'+(X0-st/2-6)+'" y="'+(ty(z[0])+4)+'" text-anchor="end" '+mut+'>'+z[0]+'°</text>'); });
  var line=function(k,sty){ var p=[]; G.forEach(function(h,i){ var t=num(h[k]); if(t!=null) p.push(x(i)+","+ty(t)); }); if(p.length>1) T('<polyline points="'+p.join(" ")+'" fill="none" '+sty+'/>'); };
  // wiatr na wspolnym wykresie (16.10): skala 0..WMX m/s na tej samej wysokosci, pasmo do porywow, linia predkosci; progi Trenera 8 / 13 m/s
  var WMX=Math.max(10,Math.ceil(gmax+1)), wy=function(v){ return TY1-(Math.min(v,WMX)/WMX)*(TY1-TY0); };
  [8,13].forEach(function(th){ if(th<WMX) T('<line x1="'+(X0-st/2)+'" x2="'+(X1+st/2)+'" y1="'+wy(th)+'" y2="'+wy(th)+'" style="stroke:var('+(th>=13?'--bad':'--warn')+');stroke-opacity:.5;stroke-dasharray:3 5"/>'); var tc=th>=13?'--bad':'--warn', tt='wiatr '+th+' m/s', yb=wy(th)-4;   /* 21.10: podpis progu z lewej, a gdy zajete -- z prawej */
    [[X0-st/2+4,"start"],[X1+st/2-4,"end"]].some(function(p){ if(!tryL(bx(p[0],yb,tt,11,p[1]))) return false;
      T('<text x="'+p[0]+'" y="'+yb+'" text-anchor="'+p[1]+'" style="fill:var('+tc+');font-size:11px">'+tt+'</text>'); return true; }); });
  var up=[], dn=[], wl=[];
  G.forEach(function(h,i){ var sp=num(h.wiatr), g=num(h.porywy); if(sp==null) return; if(g==null) g=sp; up.push(x(i)+","+wy(g)); dn.unshift(x(i)+","+wy(sp)); wl.push(x(i)+","+wy(sp)); });
  if(up.length>1){ T('<polygon data-l="por" points="'+up.concat(dn).join(" ")+'" style="fill:var(--'+(gmax>=13?'bad':(gmax>=8?'warn':'blue'))+');fill-opacity:.16"/>');
    T('<polyline data-l="wiatr" points="'+wl.join(" ")+'" fill="none" style="stroke:var(--blue);stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round;stroke-opacity:.9"/>'); }
  var lEvery=n<=12?2:3, gI=0; G.forEach(function(h,i){ if((num(h.porywy)||0)>(num(G[gI].porywy)||0)) gI=i; });
  var gOK=num(G[gI].wiatr)!=null&&(num(G[gI].porywy)||0)>0&&tryL(bx(x(gI),wy(num(G[gI].porywy))-5,"porywy "+f(num(G[gI].porywy)),11,"middle"));
  G.forEach(function(h,i){ var sp=num(h.wiatr), g=num(h.porywy)||0; if(sp==null) return;
    if(i%lEvery===1&&tryL(bx(x(i),wy(sp)+14,f(sp),11,"middle"))) T('<text data-l="wiatr" x="'+x(i)+'" y="'+(wy(sp)+14)+'" text-anchor="middle" style="fill:var(--blue);font-size:11px;font-weight:600">'+f(sp)+'</text>');
    if(i===gI&&g>0&&gOK) T('<text data-l="por" x="'+x(i)+'" y="'+(wy(g)-5)+'" text-anchor="middle" style="fill:var('+(g>=13?'--bad':(g>=8?'--warn':'--blue'))+');font-size:11px;font-weight:600">porywy '+f(g)+'</text>'); });
  line("odcz",'data-l="odcz" style="stroke:#F5A55A;stroke-width:2.8;stroke-dasharray:7 4;stroke-linecap:round"');
  line("temp",'data-l="temp" style="stroke:var(--accent);stroke-width:3.5;stroke-linejoin:round;stroke-linecap:round"');
  var iMin=0,iMax=0; G.forEach(function(h,i){ if(num(h.temp)!=null){ if(h.temp<G[iMin].temp) iMin=i; if(h.temp>G[iMax].temp) iMax=i; } });
  [0,iMin,iMax,n-1].filter(function(v,i,a){ return a.indexOf(v)===i; }).forEach(function(i){ var t=num(G[i].temp); if(t==null) return;
    T('<circle data-l="temp" cx="'+x(i)+'" cy="'+ty(t)+'" r="5" style="fill:var(--accent)"/><text data-l="temp" x="'+x(i)+'" y="'+(ty(t)-11)+'" text-anchor="middle" '+ink+'>'+f(t,1)+'°</text>'); });
  G.forEach(function(h,i){ T('<rect x="'+(x(i)-st/2)+'" y="'+TY0+'" width="'+st+'" height="'+(TY1-TY0)+'" style="fill:transparent"><title>'+esc(h.t)+' · '+f(h.temp,1)+
    '°C, odczuwalna '+f(h.odcz,1)+'°C, w jeździe (UTCI) '+f(h.utci,1)+'°C, na rowerze '+f(h.na_rowerze,1)+'°C ('+zoneOf(num(h.na_rowerze!=null?h.na_rowerze:h.odcz)||0)[3]+')'+(num(h.wbgt)!=null&&h.wbgt>=18?' · WBGT '+f(h.wbgt,1):'')+' · wiatr '+f(h.wiatr,1)+' m/s z '+esc(h.skad||'–')+', porywy '+f(h.porywy,1)+' m/s</title></rect>'); });
  var AY=TY1+17, aEvery=st>=16?1:2;
  T('<text x="0" y="'+(AY+4)+'" '+mut+'>wiatr</text>');
  G.forEach(function(h,i){ var g=num(h.porywy)||0, dir=num(h.kier); if(num(h.wiatr)==null||i%aEvery) return;
    var c=g>=13?"--bad":(g>=8?"--warn":"--blue"), a=dir==null?0:(dir+180)%360;
    T('<g transform="translate('+x(i)+','+AY+') rotate('+a+')"><line x1="0" y1="7" x2="0" y2="-3" style="stroke:var('+c+');stroke-width:2.6;stroke-linecap:round"/><polygon points="0,-9 -5.5,-1 5.5,-1" style="fill:var('+c+')"/></g>'); });
  // deszcz: slupki szansy (zespol) + mm (model)
  var RY=MINI?206:290;
  T('<text x="0" y="'+(RY-6)+'" '+mut+'>deszcz</text>');
  if(pmax<10 && mmSum<0.1){
    T('<text x="'+(X0-st/2)+'" y="'+(RY-6)+'" style="fill:var(--ink2);font-size:13px">bez opadu w najbliższych '+(n*DT)+' h (maks. '+f(pmax)+'% szansy)</text>');
  } else {
    T('<line x1="'+(X0-st/2)+'" x2="'+(X1+st/2)+'" y1="'+(RY+.5)+'" y2="'+(RY+.5)+'" style="stroke:var(--muted);stroke-opacity:.35"/>');
    var FSr=opt.fs||1, lastT=-1e9, lastP=-1e9, lastM=-1e9;   /* 18.10: opisy tylko gdy jest miejsce (bez nachodzenia) */
    G.forEach(function(h,i){ var p=(num(h.szansa)||0)*100, mm=num(h.opad)||0, hh=p/100*30, w=Math.min(18,st*0.7);
      if(p>0) T('<rect x="'+(x(i)-w/2)+'" y="'+(RY-Math.max(hh,1.5))+'" width="'+w+'" height="'+Math.max(hh,1.5)+'" rx="3" style="fill:var(--blue);fill-opacity:'+(0.3+p/140).toFixed(2)+'"><title>'+esc(h.t)+' szansa '+f(p)+'% · '+f(mm,1)+' mm'+(window.wxOpadTyp(h)?' · '+window.wxOpadTyp(h).n:'')+'</title></rect>');
      var ot=window.wxOpadTyp(h), op=i>0?window.wxOpadTyp(G[i-1]):null; if(ot&&(!op||op.n!==ot.n)&&x(i)-st/2-lastT>=0){ lastT=x(i)-st/2+(ot.n.length+(ot.marz?2:0))*6.6*FSr+8; T('<text x="'+(x(i)-st/2+2)+'" y="'+(RY+(MINI?27*FSr:26))+'" style="fill:var(--'+(ot.z==="bad"?'bad':'warn')+');font-size:11px;font-weight:600">'+(ot.marz?'⚠ ':'')+ot.n+'</text>'); }
      if(p>=30 && x(i)-lastP>=34*FSr && (lastP=x(i))) T('<text x="'+x(i)+'" y="'+(RY-hh-4)+'" text-anchor="middle" style="fill:var(--muted);font-size:11px">'+f(p)+'%</text>');
      if(mm>=0.1 && x(i)-lastM>=30*FSr && (lastM=x(i))) T('<text x="'+x(i)+'" y="'+(RY+(MINI?12*FSr:13))+'" text-anchor="middle" style="fill:var(--muted);font-size:11px">'+f(mm,1)+'</text>'); });
  }
  // ryzyka na drodze (tylko gdy sa)
  var RZ=330, AXY=AXq;
  if(!MINI){ T('<text x="0" y="'+(RZ+4)+'" '+mut+'>droga</text>');
  if(!risk.length) T('<text x="'+(X0-st/2)+'" y="'+(RZ+4)+'" style="fill:var(--ink2);font-size:13px">bez mgły, oblodzenia i błota</text>');
  else { var HZ=[{n:"marznący opad",c:"var(--bad)",t:function(h){ var q=window.wxOpadTyp(h); return !!(q&&q.marz); }},
      {n:"mgła",c:"#9aa3ad",t:function(h){ return h.mgla===2; }}, {n:"oblodzenie",c:"#5aa9e6",t:function(h){ return h.lod>=2; }},
      {n:"błoto",c:"#a0703c",t:function(h){ return h.nawierzchnia===2; }}], lane=0;
    var hhE=function(i){ var v=(parseInt(G[i].t,10)+DT)%24; return ("0"+v).slice(-2)+":00"; };
    HZ.forEach(function(z){ var runs=[], i0=-1; G.forEach(function(h,i){ var on=z.t(h); if(on&&i0<0) i0=i; if((!on||i===n-1)&&i0>=0){ runs.push([i0,on?i:i-1]); i0=-1; } });
      if(!runs.length||lane>2) return; var yb=RZ-12+lane*17;
      runs.forEach(function(rn){ var xa=x(rn[0])-st/2, xb=x(rn[1])+st/2, lab=z.n+" "+G[rn[0]].t.slice(0,2)+"–"+hhE(rn[1]).slice(0,2);
        T('<rect x="'+xa+'" y="'+(yb+5)+'" width="'+Math.max(4,xb-xa)+'" height="7" rx="3.5" style="fill:'+z.c+';fill-opacity:.9"><title>'+esc(z.n+" "+G[rn[0]].t+"–"+hhE(rn[1]))+'</title></rect>'+
          '<text x="'+(xa+2)+'" y="'+(yb+1)+'" style="fill:'+z.c+';font-size:11px;font-weight:600">'+esc(lab)+'</text>'); });
      lane++; }); }
  }
  // os czasu
  var FS=opt.fs||1, every=Math.max(1,Math.ceil(46*FS/st)), DNm=["nd","pn","wt","śr","czw","pt","sob"];
  /* 21.10: godziny bez wyrozniania polnocy; dzien = podpis na srodku SWOJEGO odcinka (miedzy liniami polnocy) */
  G.forEach(function(h,i){ if(i%every) return; T('<text x="'+x(i)+'" y="'+AXY+'" text-anchor="middle" style="fill:var(--ink);font-size:13px">'+esc(h.t)+'</text>'); });
  var cuts=[0]; NDS.forEach(function(v2,i){ if(v2) cuts.push(i); }); cuts.push(n);
  for(var c=0;c<cuts.length-1;c++){ var ia=cuts[c], ib=cuts[c+1]; if(ib<=ia) continue;
    var xa=c?sepX(ia):X0-st/2, xb=(c+2<cuts.length)?sepX(ib):X1+st/2, wd=xb-xa, dd=new Date(G[ia].iso), DN=DNm[dd.getDay()],
      lb=DN+' '+G[ia].iso.slice(8,10)+'.'+G[ia].iso.slice(5,7), lb2=wd>=lb.length*7.4*FS+8?lb:(wd>=DN.length*7.4*FS+6?DN:'');
    if(lb2) T('<text x="'+((xa+xb)/2)+'" y="'+(AXY+17*FS)+'" text-anchor="middle" style="fill:var(--ink2);font-size:12px;font-weight:700">'+esc(lb2)+'</text>'); }
  T('</svg>');
  var H=window.wxHid, pill=function(k,col,lab){ return '<span class="chip'+(H[k]?" off":"")+'" onclick="wxTog(this,\''+k+'\')"><i style="background:'+col+'"></i>'+lab+'</span>'; };
  var lg=opt.noLegend?'':'<div class="wx-pills">'+pill("temp","var(--accent)","temperatura °C")+pill("odcz","#F5A55A","odczuwalna °C")+pill("wiatr","var(--blue)","wiatr m/s")+pill("por","var(--warn)","porywy m/s")+
    '<span class="wx-leg"><b style="background:#C98A1E;opacity:.55"></b>świt</span><span class="wx-leg"><b style="background:#B8522A;opacity:.55"></b>zmierzch</span><span class="wx-leg"><b style="background:#000;opacity:.5"></b>noc</span>'+
    '<span class="wx-leg" style="color:var(--muted)">strzałka = dokąd wieje · linie 8 / 13 m/s = progi wiatru</span></div>';
  return '<div class="wx-day'+Object.keys(H).filter(function(k){return H[k];}).map(function(k){return " h-"+k;}).join("")+'">'+head+lg+o.join("")+'</div>';
};
})();
