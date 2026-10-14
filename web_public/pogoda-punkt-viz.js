/* pogoda-punkt-viz.js v3 (2026-10-14: odczuwalna, UTCI w jezdzie, 'na rowerze', WBGT -- jak w silniku tras) — „Warunki godzina po godzinie” dla PUNKTU (strona Pogoda), w jezyku wizualnym Analizy trasy
   (raport-pogoda-viz.js: kafelki, ikony nieba, temperatura na tle stref ubioru, slupki deszczu, wiatr). Wspolne elementy z window.wxVizKit.
   wxPointViz(godziny): godziny = /api/pogoda/warunki .godziny bez przeszlosci (t, iso, temp, odcz, wiatr, kier, skad, porywy, opad, szansa,
   chmury, dzien, mgla, lod, nawierzchnia, widocznosc, grunt). Wiatr: strzalka = dokad wieje; kolor wg porywow (progi Trenera 8 / 13 m/s). */
(function(){
"use strict";
window.wxPointViz = function(G){
  var K=window.wxVizKit; if(!K||!G||G.length<2) return "";
  var f=K.f, num=K.num, esc=K.esc, ZONES=K.ZONES, zoneOf=K.zoneOf;
  var n=G.length, X0=86, X1=958, st=(X1-X0)/(n-1), x=function(i){ return X0+i*st; };
  var vals=function(k){ return G.map(function(h){ return num(h[k]); }).filter(function(v){ return v!=null; }); };
  var tA=vals("temp"), oA=vals("odcz"), all=tA.concat(oA);
  var mmSum=G.reduce(function(a,h){ return a+(num(h.opad)||0); },0), pmax=Math.max.apply(null,G.map(function(h){ return (num(h.szansa)||0)*100; }));
  var wmax=Math.max.apply(null,vals("wiatr").concat([0])), gmax=Math.max.apply(null,vals("porywy").concat([0]));
  var cAvg=vals("chmury").reduce(function(a,b){return a+b;},0)/Math.max(1,vals("chmury").length);
  var hrs=function(fn){ var a=G.filter(fn); return a.length?a[0].t+(a.length>1?"–"+a[a.length-1].t:""):null; };
  var mg=hrs(function(h){return h.mgla===2;}), ld=hrs(function(h){return h.lod>=2;}), bl=hrs(function(h){return h.nawierzchnia===2;});
  var tile=function(ic,lab,val,sub,c){ return '<div style="background:'+(c?'var(--'+c+'-bg)':'var(--well)')+';border-radius:10px;padding:9px 12px;min-width:0">'+
    '<div style="font-size:12px;color:'+(c?'var(--'+c+')':'var(--ink2)')+'">'+ic+' '+lab+'</div><div style="font-size:19px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+val+'</div>'+
    '<div style="font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+sub+'</div></div>'; };
  var tmn=Math.min.apply(null,tA), tmx=Math.max.apply(null,tA), omn=Math.min.apply(null,oA.length?oA:tA);
  var risk=[mg?"mgła "+mg:null, ld?"oblodzenie "+ld:null, bl?"błoto "+bl:null].filter(Boolean);
  var head='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:2px 0 12px">'+
    (function(){ var nr=vals("na_rowerze"), nmn=nr.length?Math.min.apply(null,nr):omn, nmx=nr.length?Math.max.apply(null,nr):omn;
      return tile("&#127777;&#65039;","Temperatura",f(tmn)+" … "+f(tmx)+"°C","na rowerze "+f(nmn)+"…"+f(nmx)+"°C · "+zoneOf(nmn)[3]+" · odczuwalna od "+f(omn)+"°C"); })()+
    tile("&#9728;&#65039;","Niebo",cAvg<20?"bezchmurnie":(cAvg<50?"przejaśnienia":(cAvg<80?"pochmurno":"zachmurzenie")),"średnio "+f(cAvg)+"% chmur")+
    tile("&#127788;&#65039;","Wiatr","do "+f(wmax,1)+" m/s","porywy do "+f(gmax,1)+" m/s",gmax>=13?"bad":(gmax>=8?"warn":null))+
    tile("&#9748;","Deszcz",(pmax<10&&mmSum<0.1)?"sucho":(f(mmSum,1)+" mm"),"maks. "+f(pmax)+"% szansy",pmax>=40?"warn":null)+
    (risk.length?tile("&#9888;&#65039;","Uwaga",risk[0],risk.slice(1).join(" · ")||"na drodze","warn"):"")+'</div>';
  var tmin=Math.floor(Math.min.apply(null,all)-1), tmax=Math.ceil(Math.max.apply(null,all)+1);
  if(tmax-tmin<8){ var m=(tmax+tmin)/2; tmin=Math.floor(m-4); tmax=Math.ceil(m+4); }
  var TY0=58, TY1=226, ty=function(t){ return TY1-(t-tmin)/(tmax-tmin)*(TY1-TY0); };
  var o=[], T=function(s){ o.push(s); };
  var mut='style="fill:var(--muted);font-size:12px"', ink='style="fill:var(--ink);font-size:14px;font-weight:600"';
  T('<svg viewBox="0 0 1000 446" width="100%" role="img" aria-label="Warunki godzina po godzinie" style="display:block">');
  // niebo (noc: ksiezyc)
  T('<text x="0" y="30" '+mut+'>niebo</text>');
  G.forEach(function(h,i){ var c=num(h.chmury)||0, p=(num(h.szansa)||0)*100, cx=x(i), cy=26, s=Math.min(1,st/30);
    var ic=(p>=40||(num(h.opad)||0)>=0.2)?K.rainIcon(0,0):(h.dzien===0?(c<70?'<circle cx="-1" cy="0" r="7" style="fill:var(--muted)"/><circle cx="3" cy="-3" r="6.5" style="fill:var(--glass,var(--card))"/>':K.cloudIcon(0,0,false)):(c<25?K.sunIcon(0,0):K.cloudIcon(0,0,c<70)));
    T('<g transform="translate('+cx+','+cy+') scale('+s.toFixed(2)+')">'+ic+'</g>');
    T('<rect x="'+(cx-st/2)+'" y="8" width="'+st+'" height="38" style="fill:transparent"><title>'+esc(h.t)+' · chmury '+f(c)+'% · szansa opadu '+f(p)+'%</title></rect>'); });
  // strefy ubioru + temperatura i odczuwalna
  T('<text x="0" y="'+(TY0+10)+'" '+mut+'>temp.</text>');
  ZONES.forEach(function(z){ var a=Math.max(z[0],tmin), b=Math.min(z[1],tmax); if(b<=a) return;
    T('<rect x="'+(X0-st/2)+'" y="'+ty(b)+'" width="'+(X1-X0+st)+'" height="'+(ty(a)-ty(b))+'" style="fill:'+z[2]+';fill-opacity:.09"/>');
    if(ty(a)-ty(b)>=16) T('<text x="'+(X1+st/2-6)+'" y="'+(ty(b)+14)+'" text-anchor="end" style="fill:'+z[2]+';font-size:12px;opacity:.9">'+z[3]+'</text>');
    if(z[0]>tmin) T('<text x="'+(X0-st/2-6)+'" y="'+(ty(z[0])+4)+'" text-anchor="end" '+mut+'>'+z[0]+'°</text>'); });
  var line=function(k,sty){ var p=[]; G.forEach(function(h,i){ var t=num(h[k]); if(t!=null) p.push(x(i)+","+ty(t)); }); if(p.length>1) T('<polyline points="'+p.join(" ")+'" fill="none" '+sty+'/>'); };
  line("odcz",'style="stroke:var(--muted);stroke-width:1.6;stroke-dasharray:5 4"');
  line("temp",'style="stroke:var(--accent);stroke-width:3.5;stroke-linejoin:round;stroke-linecap:round"');
  var iMin=0,iMax=0; G.forEach(function(h,i){ if(num(h.temp)!=null){ if(h.temp<G[iMin].temp) iMin=i; if(h.temp>G[iMax].temp) iMax=i; } });
  [0,iMin,iMax,n-1].filter(function(v,i,a){ return a.indexOf(v)===i; }).forEach(function(i){ var t=num(G[i].temp); if(t==null) return;
    T('<circle cx="'+x(i)+'" cy="'+ty(t)+'" r="5" style="fill:var(--accent)"/><text x="'+x(i)+'" y="'+(ty(t)-11)+'" text-anchor="middle" '+ink+'>'+f(t,1)+'°</text>'); });
  G.forEach(function(h,i){ T('<rect x="'+(x(i)-st/2)+'" y="'+TY0+'" width="'+st+'" height="'+(TY1-TY0)+'" style="fill:transparent"><title>'+esc(h.t)+' · '+f(h.temp,1)+
    '°C, odczuwalna '+f(h.odcz,1)+'°C, w jeździe (UTCI) '+f(h.utci,1)+'°C, na rowerze '+f(h.na_rowerze,1)+'°C ('+zoneOf(num(h.na_rowerze!=null?h.na_rowerze:h.odcz)||0)[3]+')'+(num(h.wbgt)!=null&&h.wbgt>=18?' · WBGT '+f(h.wbgt,1):'')+'</title></rect>'); });
  // deszcz: slupki szansy (zespol) + mm (model)
  var RY=272;
  T('<text x="0" y="'+(RY-6)+'" '+mut+'>deszcz</text>');
  if(pmax<10 && mmSum<0.1){
    T('<text x="'+(X0-st/2)+'" y="'+(RY-6)+'" style="fill:var(--ink2);font-size:13px">bez opadu w najbliższych '+n+' h (maks. '+f(pmax)+'% szansy)</text>');
  } else {
    T('<line x1="'+(X0-st/2)+'" x2="'+(X1+st/2)+'" y1="'+(RY+.5)+'" y2="'+(RY+.5)+'" style="stroke:var(--muted);stroke-opacity:.35"/>');
    G.forEach(function(h,i){ var p=(num(h.szansa)||0)*100, mm=num(h.opad)||0, hh=p/100*30, w=Math.min(18,st*0.7);
      if(p>0) T('<rect x="'+(x(i)-w/2)+'" y="'+(RY-Math.max(hh,1.5))+'" width="'+w+'" height="'+Math.max(hh,1.5)+'" rx="3" style="fill:var(--blue);fill-opacity:'+(0.3+p/140).toFixed(2)+'"><title>'+esc(h.t)+' szansa '+f(p)+'% · '+f(mm,1)+' mm</title></rect>');
      if(p>=30 && (i%2===0||p>=60)) T('<text x="'+x(i)+'" y="'+(RY-hh-4)+'" text-anchor="middle" style="fill:var(--muted);font-size:11px">'+f(p)+'%</text>');
      if(mm>=0.1) T('<text x="'+x(i)+'" y="'+(RY+13)+'" text-anchor="middle" style="fill:var(--muted);font-size:11px">'+f(mm,1)+'</text>'); });
  }
  // wiatr: strzalka dokad wieje, kolor wg porywow
  var WY=322;
  T('<text x="0" y="'+(WY+4)+'" '+mut+'>wiatr</text><text x="0" y="'+(WY+22)+'" '+mut+'>m/s</text>');
  G.forEach(function(h,i){ var sp=num(h.wiatr), g=num(h.porywy)||0, dir=num(h.kier); if(sp==null) return;
    var cx=x(i), c=g>=13?"--bad":(g>=8?"--warn":"--muted"), L=Math.max(9,Math.min(st*0.8,6+sp*2.4)), a=dir==null?0:(dir+180)%360;
    T('<g transform="translate('+cx+','+WY+') rotate('+a+')"><line x1="0" y1="'+(L/2)+'" x2="0" y2="'+(-L/2+5)+'" style="stroke:var('+c+');stroke-width:2.6;stroke-linecap:round"/>'+
      '<polygon points="0,'+(-L/2-3)+' -5,'+(-L/2+5)+' 5,'+(-L/2+5)+'" style="fill:var('+c+')"/></g>');
    if(i%2===0) T('<text x="'+cx+'" y="'+(WY+28)+'" text-anchor="middle" '+mut+'>'+f(sp)+'</text>');
    if(g>=8 && i%2===0) T('<text x="'+cx+'" y="'+(WY-20)+'" text-anchor="middle" style="fill:var('+c+');font-size:11px;font-weight:600">'+f(g)+'</text>');
    T('<rect x="'+(cx-st/2)+'" y="'+(WY-24)+'" width="'+st+'" height="56" style="fill:transparent"><title>'+esc(h.t)+' · wiatr '+f(sp,1)+' m/s z '+esc(h.skad||"–")+' · porywy '+f(g,1)+' m/s</title></rect>'); });
  // ryzyka na drodze (tylko gdy sa)
  var RZ=378;
  T('<text x="0" y="'+(RZ+4)+'" '+mut+'>droga</text>');
  if(!risk.length) T('<text x="'+(X0-st/2)+'" y="'+(RZ+4)+'" style="fill:var(--ink2);font-size:13px">bez mgły, oblodzenia i błota</text>');
  else G.forEach(function(h,i){ var s=(h.mgla===2?"🌫":"")+(h.lod>=2?"❄️":"")+(h.nawierzchnia===2?"🟤":"");
    if(s) T('<text x="'+x(i)+'" y="'+(RZ+6)+'" text-anchor="middle" style="font-size:13px">'+s+'<title>'+esc(h.t)+(h.mgla===2?' · mgła':'')+(h.lod>=2?' · oblodzenie (grunt '+f(h.grunt,1)+'°C)':'')+(h.nawierzchnia===2?' · mokro, błoto':'')+'</title></text>'); });
  // os czasu
  var every=n<=12?1:(n<=24?3:4);
  G.forEach(function(h,i){ var nd=h.t==="00:00";
    if(i%every===0||nd) T('<text x="'+x(i)+'" y="'+(RZ+44)+'" text-anchor="middle" style="fill:var(--ink);font-size:13px'+(nd?';font-weight:700':'')+'">'+esc(h.t)+'</text>');
    if(nd) T('<text x="'+x(i)+'" y="'+(RZ+60)+'" text-anchor="middle" '+mut+'>'+esc(h.iso.slice(8,10)+"."+h.iso.slice(5,7))+'</text>'); });
  T('</svg>');
  var lg='<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink2);margin:0 0 2px">'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:18px;height:3px;background:var(--accent);border-radius:2px"></span>temperatura</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:18px;border-top:2px dashed var(--muted)"></span>odczuwalna (jak na trasie)</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="width:12px;height:10px;background:var(--blue);opacity:.6;border-radius:2px"></span>szansa deszczu (zespół)</span>'+
    '<span style="display:flex;align-items:center;gap:6px"><span style="color:var(--warn)">&#10148;</span>wiatr: dokąd wieje, liczba nad = porywy</span></div>';
  return '<div class="wx-day">'+head+lg+o.join("")+'</div>';
};
})();
