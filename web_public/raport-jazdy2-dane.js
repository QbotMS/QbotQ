/* Kolumna "Dane" raportu v2: karty (nazwa · liczba · ocena · zdanie · km) z W1. window.__RJ2dane(D, ctx) -> HTML.
   ctx: {FTP, TR, PWS, SPD, GR, LTHR}. Pastylki: <span class="kmp" data-a data-b> (km) i <span class="kmp" data-cat> (nawierzchnia). */
(function(){
"use strict";
var V=function(x){return (x&&typeof x==="object"&&"value" in x)?x.value:x;};
var isNum=function(v){return typeof v==="number"&&isFinite(v);};
function n(v,d){return isNum(v)?v.toFixed(d==null?0:d):"—";}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function fmtHM(t){if(!isNum(t))return "—";var m=Math.round(t/60);return Math.floor(m/60)+":"+String(m%60).padStart(2,"0");}
var SCAT={1:"#1565c0",2:"#2e7d32",3:"#8bc34a",4:"#e07b1a",5:"#c2452f"};
function km(a,b){if(!isNum(a))return "";return '<span class="kmp" data-a="'+a+'" data-b="'+(isNum(b)?b:a)+'">km '+n(a,1)+(isNum(b)&&b!==a?"–"+n(b,1):"")+' ↗</span>';}
function it(t,num,rate,cls,text,pill){return '<div class="it"><div class="h"><b>'+t+'</b>'+(rate?'<span class="rate '+(cls||"")+'">'+rate+'</span>':"")+'</div>'+(num?'<div class="num">'+num+'</div>':"")+'<p>'+text+(pill||"")+'</p></div>';}
function sec(title,body,open){return '<div class="dsec'+(open?" open":"")+'"><div class="dh"><b>'+title+'</b><span class="chev">'+(open?"⌄":"›")+'</span></div><div class="db">'+body+'</div></div>';}
function bar(pcts,cols){return '<div class="zone">'+pcts.map(function(p,i){return '<div style="width:'+(p||0)+'%;background:'+cols[i%cols.length]+'"></div>';}).join("")+'</div>';}
var ZC=["#6fa8dc","#7fb24a","#f3b53c","#ef6e4a","#c81e1e","#a32d2d","#791f1f"],ZN=["spokojnie","baza","tempo","próg","mocno","b. mocno","sprint"],HN=["Z1","Z2","Z3","Z4","Z5"];

/* najlepsze okno mocy w trace -> km */
function bestWin(TR,PWS,sec){var N=(TR.km||[]).length,w=Math.max(1,Math.round(sec/(TR.window_s||10))),bs=-1,bi=0;for(var i=0;i+w<=N;i++){var s=0,c=0;for(var j=0;j<w;j++){var z=PWS[i+j];if(isNum(z)){s+=z;c++;}}if(c===w&&s>bs){bs=s;bi=i;}}return bs>0?[TR.km[bi],TR.km[Math.min(N-1,bi+w)],bs/w]:null;}

window.__RJ2dane=function(D,ctx){
  var FTP=ctx.FTP,TR=ctx.TR||{},PWS=ctx.PWS||[],LTHR=ctx.LTHR||132,N=(TR.km||[]).length;
  var L=D.load||{},ph=D.physio||{},wp=D.wprime||{},we=D.weather||{},wi=V(D.wind)||{},sf=V(D.surface)||{},dt=D.drivetrain||{},mq=D.modelq||{},pva=V(D.plan_vs_actual)||{},en=D.energy||{},nu=V(D.nutrition)||{},ti=D.terrain_impact||{},bk=V(D.bike),gr=V(D.gears),sp=V(D.splits)||{};
  var H="",c,ROWERC="",WYSC="";
  /* ===== ROWER I CZUJNIKI ===== */
  if(bk&&bk.bike!==undefined){c="";var warn=(bk.battery_warnings||[]);
    var SNAME={bike_power:"Miernik mocy",power:"Miernik mocy",bike_speed:"Czujnik prędkości",bike_cadence:"Czujnik kadencji",bike_speed_cadence:"Prędkość i kadencja",speed_cadence:"Prędkość i kadencja",heart_rate:"Czujnik tętna",environment_sensor:"Czujnik pogody"};
    var MFR={sram:"SRAM",garmin:"Garmin",quarq:"Quarq",favero:"Favero",wahoo:"Wahoo",hammerhead:"Hammerhead",shimano:"Shimano"};
    var BAT={new:["nowa","#2e7d32"],good:["dobra","#2e7d32"],ok:["OK","#e0a800"],low:["niska","#c2452f"],critical:["krytyczna","#c2452f"],charging:["ładuje","#1565c0"]};
    var snm=function(s){if(s.type==="34"||/AXS/i.test(s.component||""))return "Przerzutka elektroniczna";return SNAME[s.type]||esc((s.component||"czujnik").replace(/heart_rate/i,"tętno").replace(/predkosci/i,"prędkości"));};
    var mfr=function(s){if(s.type==="bike_power"||s.type==="power"){var m=(s.component||"").match(/Quarq|Favero|Assioma|Power2Max|Stages|4iiii/i);if(m)return m[0];}return MFR[(s.manufacturer||"").toLowerCase()]||(s.manufacturer?esc(s.manufacturer):"—");};
    var bat=function(s){var b=BAT[(s.battery||"").toLowerCase()];if(!b)return '<span style="color:var(--muted)">—</span>';return '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+b[1]+';margin-right:6px;vertical-align:1px"></span>'+b[0];};
    var rows=(bk.sensors||[]).map(function(s){return '<tr><td>'+snm(s)+'</td><td style="color:var(--ink2)">'+mfr(s)+'</td><td>'+bat(s)+'</td></tr>';}).join("");
    var drive=bk.has_axs?["elektroniczny AXS","good"]:["mechaniczny",""];
    var howT=bk.how==="serial"?"Rozpoznany po numerze seryjnym czujnika.":bk.how==="type"?"Rozpoznany po typie czujników.":bk.how==="manual"?"Ustawiony ręcznie.":"";
    c+='<div class="it"><div class="h"><b>Rower</b><span class="rate '+drive[1]+'">'+drive[0]+'</span></div><div class="num">'+esc(bk.bike||"nierozpoznany")+'</div>'+
       '<table class="tb"><tr class="h"><td>czujnik</td><td>marka</td><td>bateria</td></tr>'+rows+'</table>'+
       '<p>'+howT+(warn.length?"":" Wszystkie baterie w porządku.")+'</p></div>';
    if(warn.length)c+=it("Baterie do naładowania",warn.map(function(s){return esc(s.component);}).join(", "),"uwaga","bad","Stan z końca jazdy: "+warn.map(function(s){return esc(s.component)+" — "+esc(s.battery);}).join("; ")+". Naładuj przed następną jazdą.");
    ROWERC=c;}
  /* ===== WYSILEK ===== */
  c="";var iff=V(L.if),vi=V(L.vi),np=V(L.np_w),avg=V(L.avg_p_w),xss=V(L.xss),xph=L.xss&&L.xss.xss_per_h,ef=V(L.ef),efa=V(L.ef_anchor),wiad=V(L.wiadra)||{},zp=V(L.zones_power_pct),zh=V(L.zones_hr_pct),mmp=V(L.mmp);
  if(isNum(iff)){var ir=iff<0.65?["lekka","good"]:iff<0.8?["umiarkowana","good"]:iff<0.92?["wysoka","warn"]:["bardzo wysoka","bad"];c+=it("Intensywność",n(iff,2),ir[0],ir[1],iff<0.65?"Poniżej progu przez całą jazdę — baza tlenowa. Nie kosztuje, mało buduje mocy.":iff<0.8?"Solidne tempo: buduje wytrzymałość, regenerujesz się do jutra.":iff<0.92?"Blisko progu przez większość czasu — podnosi moc progową, kosztuje 1–2 dni odpoczynku.":"Jak wyścig. Raz na jakiś czas — super; częściej — ryzyko przetrenowania.");}
  if(isNum(xss))c+=it("Obciążenie",Math.round(xss)+(isNum(xph)?' <small>'+Math.round(xph)+"/h</small>":""),xss<40?"małe":xss<90?"średnie":xss<150?"duże":"bardzo duże",xss<90?"good":xss<150?"warn":"bad",(xss<40?"Prawie nie liczy się do formy.":xss<90?"Typowy trening — forma rośnie bez długu.":xss<150?"Mocny dzień — jutro raczej lżej.":"Bardzo ciężki dzień — 2–3 dni lżejsze.")+(isNum(wiad.low)?" Skąd: spokojnie "+n(wiad.low)+" · mocno "+n(wiad.high)+" · na maksa "+n(wiad.peak,1)+".":""));
  if(isNum(vi)){c+=it("Równość",n(vi,2),vi<1.05?"równa":vi<1.15?"szarpana":"bardzo szarpana",vi<1.05?"good":vi<1.15?"warn":"bad",vi<1.05?"Moc trzymana równo, bez skoków — najbardziej efektywna jazda.":"Moc skakała zamiast równego tempa (zrywy, podjazdy, zatrzymania). Dlatego realny koszt — moc znormalizowana "+(isNum(np)?np+" W":"")+" — jest wyższy niż średnia "+(isNum(avg)?avg+" W":"")+". Szarpana jazda męczy bardziej niż równa o tej samej średniej.");}
  var MMPC="",ZONC="",PLANC="";
  if(mmp&&typeof mmp==="object"){var ks=Object.keys(mmp),secs={"5s":5,"1min":60,"5min":300,"20min":1200,"60min":3600};MMPC='<div class="it"><div class="h"><b>Najlepsza moc w oknach</b><span class="rate">'+(FTP?"% progu":"")+'</span></div><div class="mmp">'+ks.map(function(k){var b=secs[k]?bestWin(TR,PWS,secs[k]):null;return '<div><div class="l">'+esc(k)+'</div><div class="v">'+n(mmp[k])+'</div>'+(FTP?'<div class="r">'+Math.round(mmp[k]/FTP*100)+'%</div>':"")+(b?'<div class="kmp" data-a="'+b[0]+'" data-b="'+b[1]+'" style="font-size:10px;margin:3px auto 0;padding:0 5px;display:inline-block">km '+n(b[0],1)+'</div>':"")+'</div>';}).join("")+'</div></div>';}
  if((zp&&zp.length)||(zh&&zh.length)){
    var zleg=function(arr,names){return '<div class="lg">'+arr.map(function(p,i){return p>=1?'<span><i style="background:'+ZC[i]+'"></i>'+(names[i]||"Z"+(i+1))+' '+Math.round(p)+'%</span>':"";}).join("")+'</div>';};
    ZONC='<div class="it"><div class="h"><b>Czas w strefach</b><span class="rate">LTHR '+LTHR+'</span></div>'+
       ((zp&&zp.length)?'<div style="font-size:12px;color:var(--ink2);margin:2px 0 3px">moc</div>'+bar(zp,ZC)+zleg(zp,ZN):"")+
       ((zh&&zh.length)?'<div style="font-size:12px;color:var(--ink2);margin:9px 0 3px">tętno</div>'+bar(zh,ZC)+zleg(zh,HN):"")+
       '</div>';
  }
    WYSC=c;
  /* ===== ZAPAS ===== */
  c="";
  var wmin=V(wp.wbal_min_pct),wsta=V(wp.wbal_min_static_pct),lt25=V(wp.time_lt25_min),lt50=V(wp.time_lt50_min),tau=V(wp.tau_s),
      te=V(wp.top_efforts)||[],cpw=V(wp.cp_w),cpe=V(wp.cp_eff_w),cf=V(wp.cf_avg),wj=V(wp.wprime_j),
      wser=V(wp.wbal_series)||[],cut=V(wp.cutoff)||{};
  var lvl=function(p){return p>60?["płytko","good"]:p>30?["umiarkowanie","warn"]:["głęboko","bad"];};
  if(isNum(wmin)){
    var mi=-1;if(TR.wbal_pct)for(var q=0;q<N;q++)if(isNum(TR.wbal_pct[q])&&(mi<0||TR.wbal_pct[q]<TR.wbal_pct[mi]))mi=q;
    var lv=lvl(wmin),eff=isNum(cpe)&&isNum(cpw)&&cpe<cpw-1;
    var expl="Twój „bak” na wysiłek ponad progiem — ile zostało w najgorszym momencie. ";
    if(eff)expl+="Liczone przy progu obniżonym gotowością dnia ("+Math.round(cpe)+" W zamiast "+Math.round(cpw)+" W"+(isNum(cf)?", współczynnik "+n(cf,2):"")+") — dlatego zszedł niżej niż zwykle. "+(isNum(wsta)?"Przy pełnym progu "+Math.round(cpw)+" W minimum wyniosłoby "+Math.round(wsta)+"%. ":"");
    else if(isNum(wsta)&&Math.abs(wsta-wmin)>=3)expl+="Przy pełnym progu: "+Math.round(wsta)+"%. ";
    expl+=(wmin>60?"Prawie nieruszony — jazda tlenowa.":wmin>30?"Sięgałeś do zapasu na zrywach, bez wypalenia.":"Zjechałeś do dna — moment, w którym nogi gasną.");
    var subv=Math.round(wmin)+"%"+(isNum(wsta)?' <small>na urządzeniu · pełny próg '+Math.round(wsta)+'%</small>':"");
    c+=it("Minimum zapasu",subv,lv[0],lv[1],expl,isNum(cut.km)?km(cut.km):(mi>=0?km(TR.km[mi]):""));
  }
  if(wser.length>1){
    var wmax=52,scol=function(p){return p>75?"#85b7eb":p>50?"#97c459":p>30?"#fac775":p>15?"#f09595":"#e24b4a";};
    c+='<div class="it"><div class="h"><b>Przebieg zapasu</b><span class="rate">minimum co 5 km</span></div>'+
       '<div style="display:flex;align-items:flex-end;gap:5px;height:'+wmax+'px;margin:10px 0 3px">'+
       wser.map(function(p){var v=isNum(p.min_pct)?p.min_pct:0,h=Math.max(3,Math.round(v/100*wmax));return '<div class="kmp" data-a="'+(p.km-2.5>0?p.km-2.5:0)+'" data-b="'+p.km+'" title="km '+p.km+': zapas min '+Math.round(v)+'%" style="flex:1;height:'+h+'px;background:'+scol(v)+';border-radius:3px;margin:0;padding:0"></div>';}).join("")+
       '</div><div class="lg" style="justify-content:space-between;color:var(--muted)">'+wser.map(function(p){return '<span style="font-size:11px">'+p.km+'</span>';}).join("")+'</div>'+
       '<p>Ile „baku” zostawało na każdym 5-km odcinku (wysokość słupka = min %, klik → mapa). '+(isNum(cut.km)?"Dno w km "+n(cut.km,1)+", potem odbudowa na spokojniejszych fragmentach.":"")+'</p></div>';
  }
  if(te.length){
    c+='<div class="it"><div class="h"><b>Największe zrywy</b><span class="rate">koszt z zapasu</span></div><table class="tb"><tr class="h"><td>gdzie</td><td>W</td><td>% progu</td><td>czas</td><td>koszt</td></tr>'+
       te.slice(0,5).map(function(e){var p=isNum(e.avg_w)?e.avg_w:(e.power_w||e.p);return '<tr class="kmp" data-a="'+e.km+'" data-b="'+e.km+'"><td>km '+n(e.km,1)+'</td><td>'+n(p)+'</td><td>'+(isNum(p)&&FTP?Math.round(p/FTP*100)+"%":"—")+'</td><td>'+(isNum(e.dur_s)?Math.round(e.dur_s)+" s":"—")+'</td><td>'+(isNum(e.cost_kj)?n(e.cost_kj,1)+" kJ":"—")+'</td></tr>';}).join("")+
       '</table><p>Krótkie wysiłki ponad progiem, które najwięcej ubrały z zapasu. Klik wiersz → mapa.</p></div>';
  }
  if(isNum(wj)||(isNum(lt25)&&lt25>0)||(isNum(lt50)&&lt50>0)){
    var bt=(isNum(lt25)&&lt25>0?"Poniżej 25% zapasu jechałeś "+Math.round(lt25)+" min. ":"")+(isNum(lt50)&&lt50>0?"Poniżej 50%: "+Math.round(lt50)+" min. ":"")+(isNum(tau)?"Pełna odbudowa zajmuje ~"+Math.round(tau/60)+" min spokojnej jazdy.":"");
    c+=it("Bilans zapasu",(isNum(wj)?n(wj/1000,1)+" kJ":"—")+' <small>pojemność „baku”</small>',"","",bt||"Zapas prawie nieruszony przez całą jazdę.");
  }
  if(c)H+=sec("Zapas na zrywy",'<div class="nar">'+c+'</div>');
  /* ===== CIALO ===== */
  c="";var dec=V(ph.decoupling_pct),wl=V(ph.wellness)||{},cur=mq.current||{};
  if(isNum(dec)){var half=N?TR.km[Math.floor(N/2)]:null;c+=it("Rozjazd tętno / moc",n(dec,1)+"%",Math.abs(dec)<5?"stabilnie":Math.abs(dec)<10?"umiarkowany":"duży",Math.abs(dec)<5?"good":Math.abs(dec)<10?"warn":"bad","Druga połowa vs pierwsza przy tej samej mocy. "+(Math.abs(dec)<5?"Serce trzymało tempo — dobra wytrzymałość i nawodnienie.":Math.abs(dec)<10?"Trochę — długi wysiłek, ciepło albo za mało picia.":"Wyraźnie — zmęczenie, upał, odwodnienie, infekcja lub za mało jedzenia."),isNum(half)?km(half,TR.km[N-1]):"");}
  if(isNum(ef)){var efr=isNum(efa)?(ef>=efa*1.02?["lepiej niż norma","good"]:ef<efa*0.97?["gorzej niż norma","warn"]:["w normie","good"]):["",""];c+=it("Moc na uderzenie serca",n(ef,2)+(isNum(efa)?' <small>norma '+n(efa,2)+'</small>':""),efr[0],efr[1],"Ile watów daje jedno uderzenie serca. "+(efr[0]==="lepiej niż norma"?"Serce pracuje oszczędniej — forma w górę albo chłodno i wypoczęty.":efr[0]==="gorzej niż norma"?"Serce biło szybciej niż zwykle przy tej mocy — zmęczenie, ciepło, choroba, kofeina.":"Bez odchyleń."));}
  if(isNum(wl.sleep_score)||isNum(wl.hrv)||isNum(wl.rhr)){var rr=isNum(wl.rhr)&&isNum(wl.rhr_base)?wl.rhr-wl.rhr_base:null;c+=it("Rano przed jazdą",(isNum(wl.sleep_score)?"sen "+wl.sleep_score:"")+(isNum(wl.hrv)?" · HRV "+Math.round(wl.hrv):"")+(isNum(wl.rhr)?" · RHR "+wl.rhr:""),rr==null?"":rr<=2?"wypoczęty":rr<=6?"lekki sygnał":"podniesione tętno",rr==null?"":rr<=2?"good":rr<=6?"warn":"bad",(isNum(wl.rhr_base)?"Tętno spoczynkowe "+(rr>0?"+"+rr:rr)+" vs Twoja norma "+wl.rhr_base+". ":"")+(isNum(wl.sleep_h)?"Sen "+n(wl.sleep_h,1)+" h"+(isNum(wl.deep_min)?" (głęboki "+wl.deep_min+" min)":"")+". ":"")+(isNum(wl.bb_start)?"Bateria ciała "+wl.bb_start+(isNum(wl.bb_end)?" → "+wl.bb_end+" wieczorem":"")+".":""));}
  if(isNum(cur.readiness))c+=it("Gotowość i forma",(cur.readiness>0?"+":"")+n(cur.readiness,2)+' <small>forma '+n(cur.ctl,0)+' · zmęczenie '+n(cur.atl,0)+'</small>',cur.readiness>0.3?"wysoka":cur.readiness>-0.3?"neutralna":"niska",cur.readiness>0.3?"good":cur.readiness>-0.3?"":"bad","Świeżość "+(cur.tsb>0?"+":"")+n(cur.tsb,1)+(cur.load_ramp!=null?" · skok obciążenia ×"+n(cur.load_ramp,2)+(cur.load_ramp>=1.5?" (strefa ryzyka)":cur.load_ramp>=1.3?" (nagły wzrost)":" (norma)"):"")+". "+(cur.readiness>0.3?"Organizm był gotowy na mocny dzień.":cur.readiness>-0.3?"Bez sygnałów za ani przeciw.":"Sygnał, żeby jechać lżej."));
  if(c)H+=sec("Ciało tego dnia",'<div class="nar">'+c+'</div>');
  /* ===== WARUNKI I TEREN ===== */
  c="";var wxp=V(we.precip_mm),wxw=V(we.wind_ms),tc=V(we.temp_c)||{},ap=V(we.apparent_c)||{},ta=isNum(tc.avg)?tc.avg:tc.mean,aa=isNum(ap.avg)?ap.avg:ap.mean,wbgt=V(we.wbgt_max),rh=V(we.rh_pct);
  if(isNum(ta))c+=it("Pogoda",n(ta,0)+" °C"+(isNum(aa)?' <small>odczuwalna '+n(aa,0)+(isNum(rh)?" · wilgotność "+n(rh,0)+"%":"")+'</small>':""),ta<5?"zimno":ta<14?"chłodno":ta<24?"idealnie":ta<29?"ciepło":"upał",ta<5||ta>=29?"bad":ta<14||ta>=24?"warn":"good",(isNum(tc.min)?"Od "+n(tc.min,0)+" do "+n(tc.max,0)+" °C. ":"")+(wxp&&isNum(wxp.sum)?(wxp.sum>=0.1?"Opad "+n(wxp.sum,1)+" mm ("+wxp.wet_h+" z "+wxp.hours+" h z deszczem). ":"Bez opadu. "):"")+(isNum(wbgt)&&wbgt>26?"WBGT "+n(wbgt,0)+" — organizm walczył z chłodzeniem, tętno wyżej.":ta<5?"Mięśnie pracują gorzej, moc niższa o kilka %.":ta>=24?"Ciepło podnosi tętno przy tej samej mocy.":"Bez wpływu na wyniki."));
  var wxs=wxw&&isNum(wxw.avg);if(wxs&&!isNum(wi.avg_tail_ms)){c+=it("Wiatr",n(wxw.avg,1)+" m/s"+' <small>max '+n(wxw.max,1)+'</small>',wxw.avg<3?"słaby":wxw.avg<6?"umiarkowany":wxw.avg<9?"silny":"bardzo silny",wxw.avg<6?"good":wxw.avg<9?"warn":"bad","Siła wiatru godzinowo (Open-Meteo, 10 m). Brak składowej wzdłuż trasy.");}
  if(isNum(wi.avg_tail_ms)){var a=wi.avg_tail_ms;c+=it("Wiatr",(wxs?n(wxw.avg,1)+" m/s"+' <small>max '+n(wxw.max,1)+' · wzdłuż trasy '+(a>0?"+":"")+n(a,1)+'</small>':(a>0?"+":"")+n(a,1)+" m/s"),a<-1.5?"w twarz":a<-0.5?"lekko w twarz":a<0.5?"neutralny":a<1.5?"lekko w plecy":"w plecy",a<-1.5?"bad":a<-0.5?"warn":"good",(wxs?"Wiało średnio "+n(wxw.avg,1)+", max "+n(wxw.max,1)+" m/s (godzinowo, Open-Meteo, 10 m). ":"")+"Składowa wzdłuż trasy: plus pomagał, minus przeszkadzał."+(isNum(wi.min_tail_ms)&&wi.min_tail_ms<-3?" Najsilniej czołowy "+n(-wi.min_tail_ms,1)+" m/s.":"")+(a<-1?" Kosztował kilkanaście watów przy tej samej prędkości.":a>1?" Prędkość na płaskim zawyżona względem mocy.":""));}
  var sbt=ti.surface_by_type||[],tp=sf.types_pct;
  if(sbt.length){var hard=sbt.filter(function(r){return /twarda/i.test(r.surface||"");}).reduce(function(s,r){return s+(r.pct_dist||0);},0);
    c+='<div class="it"><div class="h"><b>Ile kosztowała nawierzchnia</b><span class="rate '+(hard>85?"good":hard>50?"warn":"bad")+'">'+Math.round(hard)+'% twarda</span></div><table class="tb"><tr class="h"><td>nawierzchnia</td><td>% dyst.</td><td>W</td><td>km/h</td><td>bpm</td></tr>'+sbt.map(function(r){var cat=({"twarda szybka":1,"dobry gravel":2,"zwykly gravel":3,"zwykły gravel":3,"trudna/wolna":4,"ryzyko/niepewne":5})[r.surface]||null;return '<tr class="kmp" data-cat="'+(cat||"")+'"><td><i class="sw" style="background:'+(cat?SCAT[cat]:"#777")+'"></i>'+esc(r.surface)+'</td><td>'+n(r.pct_dist,0)+'</td><td>'+n(r.avg_power_w)+'</td><td>'+n(r.avg_speed_kmh,1)+'</td><td>'+n(r.avg_hr)+'</td></tr>';}).join("")+'</table><p>Klik w wiersz podświetla te odcinki na mapie. '+(hard<85?"Na luźnej nawierzchni ta sama prędkość kosztuje 10–25% więcej mocy.":"Jazda szosowa — porównywalna z innymi.")+(isNum(sf.unknown_pct)&&sf.unknown_pct>10?" Dla "+Math.round(sf.unknown_pct)+"% trasy brak danych.":"")+'</p></div>';}
  var wbd=ti.wind_by_dir||[];if(wbd.length>1)c+='<div class="it"><div class="h"><b>Moc i prędkość według wiatru</b></div><table class="tb"><tr class="h"><td>wiatr</td><td>% czasu</td><td>W</td><td>km/h</td><td>bpm</td></tr>'+wbd.map(function(r){return '<tr><td>'+esc(r.cat)+'</td><td>'+n(r.pct_time,0)+'</td><td>'+n(r.avg_power_w)+'</td><td>'+n(r.avg_speed_kmh,1)+'</td><td>'+n(r.avg_hr)+'</td></tr>';}).join("")+'</table></div>';
  if(c)H+=sec("Warunki i teren",'<div class="nar">'+c+'</div>');
  /* ===== TECHNIKA / BIEGI ===== */
  c="";var cbg=V(dt.cad_by_grade)||{},coast=V(dt.coasting_min),shifts=V(dt.shifts),grind=V(dt.grind_min),brake=V(dt.braking_kj),dur=V(L.dur_moving_s);
  if(isNum(cbg.plasko))c+=it("Kadencja",Math.round(cbg.plasko)+' <small>płasko · pod górę '+n(cbg.podgore)+' · stromo '+n(cbg.stromo)+' · zjazd '+n(cbg.zjazd)+'</small>',cbg.plasko<70?"niska":cbg.plasko<85?"typowa":"wysoka",cbg.plasko<70?"warn":"good",cbg.plasko<70?"Kręcisz ciężko i wolno — więcej z mięśni, mniej z krążenia. Lżejszy bieg pod górę oszczędzi nogi.":"Zdrowy zakres — moc z obrotów, nie z siły.");
  if(isNum(coast)&&isNum(dur))c+=it("Bez pedałowania",Math.round(coast)+" min"+' <small>'+Math.round(coast/(dur/60)*100)+"% czasu</small>",coast/(dur/60)<0.08?"mało":coast/(dur/60)<0.18?"normalnie":"dużo","",coast/(dur/60)>0.18?"Sporo — miasto lub bardzo górzysto; średnia moc przez to zaniżona.":"Zjazdy, skrzyżowania, odpoczynek — bez wpływu na ocenę wysiłku.");
  if(isNum(shifts)&&shifts>0)c+=it("Zmiany biegów",shifts+(isNum(dur)?' <small>'+Math.round(shifts/(dur/3600))+"/h</small>":""),"","",(isNum(grind)&&grind>3?"Mielenie na za ciężkim biegu "+Math.round(grind)+" min — kadencja poniżej 60 pod obciążeniem.":"Bez mielenia na ciężkim biegu.")+(isNum(brake)&&brake>0?" Wytracone w hamulcach: "+Math.round(brake)+" kJ.":""));
  if(gr&&Array.isArray(gr.rows)&&gr.rows.length){var est=(D.gears||{}).tier==="B",rows=gr.rows.filter(function(r){return (r.pct||0)>=1;});var top=rows.slice().sort(function(a,b){return (b.pct||0)-(a.pct||0);})[0];
    c+='<div class="it"><div class="h"><b>Biegi</b><span class="rate '+(est?"warn":"good")+'">'+(est?"szacowane z prędkości i kadencji":"z czujnika AXS")+'</span></div><div class="num">'+esc(gr.chainring_label||"")+' × '+esc(gr.cassette_code||"")+'</div>'+bar(rows.map(function(r){return r.pct;}),ZC)+'<table class="tb"><tr class="h"><td>zębatka</td><td>% czasu</td><td>W</td><td>bpm</td><td>kad.</td><td>km/h</td><td>nachyl.</td></tr>'+rows.map(function(r){return '<tr><td>'+(r.cog_t?r.cog_t+"T":"poz. "+r.pos)+(r.development_m?' <small>'+n(r.development_m,1)+" m</small>":"")+'</td><td>'+n(r.pct,0)+'</td><td>'+n(r.p)+'</td><td>'+n(r.hr)+'</td><td>'+n(r.cad)+'</td><td>'+n(r.v_kmh!=null?r.v_kmh:(r.v!=null?r.v*3.6:null),1)+'</td><td>'+n(r.grade,1)+'%</td></tr>';}).join("")+'</table><p>'+(top?"Najczęściej "+(top.cog_t?top.cog_t+"T":"poz. "+top.pos)+" ("+Math.round(top.pct)+"% czasu). ":"")+(est?"Bez czujnika biegów: bieg odczytany z rozwinięcia (prędkość ÷ kadencja), dokładność ±1 zębatka.":"")+'</p></div>';}
  if(c||ROWERC)H+=sec("Rower i napęd",'<div class="nar">'+ROWERC+c+'</div>',true);
  /* ===== ENERGIA I MODEL ===== */
  c="";var sub=V(en.substrate)||{},au=V(en.audit_pct)||{},wk=V(en.work_kj),ri=mq.ride_impact||{},f1=sp.first||{},f2=sp.second||{};
  if(isNum(wk)){var alist=[["opór powietrza",au.aero],["toczenie",au.toczenie],["przyspieszanie",au.kinetyka],["podjazdy",au.wznoszenie]].filter(function(x){return isNum(x[1]);}).sort(function(a,b){return b[1]-a[1];});c+='<div class="it"><div class="h"><b>Paliwo</b>'+(isNum(sub.cho_pct)?'<span class="rate">'+(sub.cho_pct>70?"głównie cukry":sub.cho_pct>45?"mieszane":"głównie tłuszcz")+'</span>':"")+'</div><div class="num">'+Math.round(wk)+' kJ'+'</div>'+(isNum(sub.cho_pct)?'<div style="font-size:13px;margin:0 0 6px">'+sub.cho_pct+'% węgle · ~'+n(sub.carbs_g_est,0)+' g spalonych</div>':'')+(alist.length?'<div style="font-size:13px;color:var(--ink2);margin:2px 0 4px">Na co poszła energia</div><div style="display:flex;flex-direction:column;gap:3px;font-size:13.5px">'+alist.map(function(x){return '<div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:1px 0"><span>'+x[0]+'</span><span style="font-variant-numeric:tabular-nums">'+x[1]+'%</span></div>';}).join("")+'</div>':"")+'<p>'+(isNum(sub.cho_pct)&&sub.cho_pct>70?"Jedz 60–90 g węgli/h.":"Spokojne tempo — jedzenie mniej krytyczne.")+'</p></div>';}
  if(isNum(f1.p)||isNum(f1.avg_p_w)||isNum(f1.np_w)){var P1=f1.p!=null?f1.p:(f1.avg_p_w!=null?f1.avg_p_w:f1.np_w),P2=f2.p!=null?f2.p:(f2.avg_p_w!=null?f2.avg_p_w:f2.np_w),V1=f1.v_kmh!=null?f1.v_kmh:f1.v,V2=f2.v_kmh!=null?f2.v_kmh:f2.v,H1=f1.hr!=null?f1.hr:f1.hr_avg,H2=f2.hr!=null?f2.hr:f2.hr_avg;
    c+='<div class="it nw"><div class="h"><b>Połowy jazdy</b>'+(isNum(P1)&&isNum(P2)?'<span class="rate '+(P2>=P1*0.97?"good":"warn")+'">'+(P2>=P1*0.97?"równo":"gaśnięcie")+'</span>':"")+'</div><div class="hgrid"><div class="hl"></div><div class="hr">1.</div><div class="hr">2.</div><div class="hl">moc W</div><div class="hr">'+n(P1)+'</div><div class="hr">'+n(P2)+'</div><div class="hl">tętno</div><div class="hr">'+n(H1)+'</div><div class="hr">'+n(H2)+'</div><div class="hl">pręd. km/h</div><div class="hr">'+n(V1,1)+'</div><div class="hr">'+n(V2,1)+'</div></div><p>'+(isNum(P1)&&isNum(P2)&&P2<P1*0.9?"Moc spadła o "+Math.round((1-P2/P1)*100)+"% — paliwo, upał albo zbyt mocny start.":"Rozkład sił w normie.")+'</p></div>';}
  if(isNum(ri.ftp_delta)||isNum(ri.wprime_delta)||isNum(ri.ltp_delta)||isNum(ri.pp_delta)){
    var cpNum=Math.abs(ri.ftp_delta||0)>=0.5?(ri.ftp_delta>0?"+":"")+n(ri.ftp_delta,0)+" W progu":"pr\u00f3g bez zmian";
    var extras=[];
    if(isNum(ri.ltp_delta)&&Math.abs(ri.ltp_delta)>=0.3)extras.push("LTP "+(ri.ltp_delta>0?"+":"")+n(ri.ltp_delta,0)+" W");
    if(isNum(ri.wprime_delta)&&Math.abs(ri.wprime_delta)>=0.2)extras.push("zapas W\u2032 "+(ri.wprime_delta>0?"+":"")+n(ri.wprime_delta,1)+" kJ");
    if(isNum(ri.pp_delta)&&Math.abs(ri.pp_delta)>=1)extras.push("szczyt "+(ri.pp_delta>0?"+":"")+n(ri.pp_delta,0)+" W");
    var extHtml=extras.length?'<div style="margin:6px 0 0;font-size:13px">'+extras.map(function(e){return '<div style="padding:1px 0">\u2022 '+e+'</div>';}).join("")+'</div>':"";
    var any=Math.abs(ri.ftp_delta||0)>=0.5||extras.length>0;
    c+='<div class="it"><div class="h"><b>Zmiana formy</b><span class="rate '+(any?(ri.ftp_delta>0?"good":"warn"):"")+'">'+(any?(ri.ftp_delta>0?"w g\u00f3r\u0119":"w d\u00f3\u0142"):"bez zmian")+'</span></div><div class="num">'+cpNum+'</div>'+extHtml+'<p>Aktualnie: pr\u00f3g '+n(cur.ftp_w,0)+' W \u00b7 LTP '+n(cur.ltp_w,0)+' W \u00b7 zapas '+n(cur.wprime_kj,1)+' kJ \u00b7 W/kg '+n(cur.wkg,2)+'.</p></div>';}
  var pl=pva._plan,re=pva._real;
  if(pl&&re&&isNum(pl.dist_km)){var dd=isNum(re.dist_km)?re.dist_km-pl.dist_km:null;PLANC+=it("Plan vs realny",n(re.dist_km,1)+" km <small>plan "+n(pl.dist_km,1)+"</small>",dd==null?"":Math.abs(dd)<2?"jak w planie":(dd>0?"+":"")+n(dd,1)+" km",dd==null||Math.abs(dd)<2?"good":"warn","Przewyższenie "+n(re.ascent_m,0)+" m (plan "+n(pl.ascent_m,0)+").");}
  else if(re&&pva._matched!==false){PLANC+=it("Plan vs realny",n(re.dist_km,1)+" km <small>· "+n(re.ascent_m,0)+" m</small>","bez planu","","Realne: NP "+n(re.np_w)+" W"+(re.xss!=null?" · XSS "+n(re.xss):"")+".");}
  else if(pva._matched===false)PLANC+=it("Plan vs realny","—","brak trasy","","Nie powiązana z trasą.");
  if(PLANC||MMPC||ZONC)c+='<div class="pairrow">'+PLANC+MMPC+ZONC+'</div>';
  if(c||WYSC)H+=sec("Wysiłek",'<div class="nar">'+WYSC+c+'</div>',true);
  var dl=Array.isArray(nu.daily)?nu.daily:[];
  if(dl.length){c=dl.map(function(r){var kc=r.kcal||r.kcal_in||r.intake_kcal,pr=r.protein_g||r.prot_g;return it("Jedzenie "+esc(r.day||r.date||""),(isNum(kc)?Math.round(kc)+" kcal":"—")+(isNum(pr)?' <small>białko '+Math.round(pr)+" g</small>":""),"","",Object.keys(r).filter(function(k){return !/day|date|kcal|protein|prot/.test(k)&&r[k]!=null&&typeof r[k]!=="object";}).map(function(k){return esc(k)+" "+esc(r[k]);}).join(" · "));}).join("");
    H+=sec("Jedzenie",'<div class="nar">'+c+'</div>');}
  var dis=D.disabled||[];if(dis.length)H+='<div class="sub" style="font-size:12.5px;margin-top:8px;color:var(--muted)">Bez danych w tej jeździe: '+dis.map(function(x){return esc(x.blok);}).join(", ")+'</div>';
  return H;
};
window.__RJTIPS={
"Intensywność":"Jak ciężka była jazda względem progu (IF). 1,0 = cała jazda dokładnie na progu.",
"Obciążenie":"Całkowity koszt treningowy tej jazdy (XSS). Im wyżej, tym dłuższa regeneracja.",
"Równość":"Jak bardzo moc skakała: moc znormalizowana ÷ średnia (VI). 1,0 = jazda idealnie równa.",
"Najlepsza moc w oknach":"Twoja najwyższa średnia moc w danym oknie czasu i km, na którym padła.",
"Czas w strefach":"Ile czasu spędziłeś w każdej strefie mocy (i osobno tętna).",
"Paliwo":"Ile energii spaliłeś (kJ), z czego (węgle/tłuszcz) i na co poszła.",
"Połowy jazdy":"Porównanie 1. i 2. połowy — czy gasłeś, czy trzymałeś tempo.",
"Zmiana formy":"Jak ta jazda ruszyła Twój model formy (próg i zapas W\u2032).",
"Plan vs realny":"Porównanie z planem trasy — jeśli trasa miała zapisany plan.",
"Minimum zapasu":"Najniższy poziom zapasu W\u2032 (\u201Ebaku\u201D na wysiłek ponad progiem) w czasie jazdy.",
"Przebieg zapasu":"Ile zapasu W\u2032 zostawało na kolejnych odcinkach trasy.",
"Największe zrywy":"Krótkie wysiłki ponad progiem, które najwięcej ubrały z zapasu.",
"Bilans zapasu":"Pojemność \u201Ebaku\u201D (W\u2032) i ile czasu jechałeś w rezerwie.",
"Rozjazd tętno / moc":"Czy w drugiej połowie tętno rosło przy tej samej mocy (decoupling).",
"Moc na uderzenie serca":"Ile watów przypada na jedno uderzenie serca (efektywność, EF).",
"Rano przed jazdą":"Sen, HRV i tętno spoczynkowe z poranka — gotowość organizmu.",
"Gotowość i forma":"Świeżość (forma minus zmęczenie) w dniu jazdy.",
"Pogoda":"Temperatura, odczuwalna i wilgotność oraz ich wpływ na wysiłek.",
"Wiatr":"Składowa wiatru wzdłuż trasy (w m/s): plus pomagał, minus przeszkadzał.",
"Ile kosztowała nawierzchnia":"Moc, prędkość i tętno na różnych typach nawierzchni.",
"Moc i prędkość według wiatru":"Jak wiatr (pod/z/boczny) zmieniał moc i prędkość.",
"Rower":"Wykryty rower, czujniki i stan ich baterii.",
"Kadencja":"Średnie obroty korby na płasko, pod górę, stromo i na zjeździe.",
"Bez pedałowania":"Ile czasu koła kręciły się bez pedałowania (zjazdy, postoje).",
"Zmiany biegów":"Liczba zmian biegów i czy nie mieliłeś na za ciężkim.",
"Biegi":"Które zębatki i jak długo były używane."
};
})();