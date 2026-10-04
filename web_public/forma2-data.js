/* forma2-data.js v5 — Forma z przełącznikami zakresów/grup, posiłkami, pełna funkcjonalność */
(function(){
"use strict";
var today=qToday();
var d90=qLocalISO(new Date(Date.now()-90*864e5));
var d30=qLocalISO(new Date(Date.now()-30*864e5));
var forma,rides,cal,nutri,stats,nutToday;
var RNG=90,GRP="moc",entMap={};

async function load(){
  [forma,rides,nutri,stats,nutToday]=await Promise.all([
    qJSON("/api/forma/data"),qJSON("/api/rides/ready"),
    qJSON("/api/nutrition/data?start="+qLocalISO(new Date(Date.now()-365*864e5))+"&end="+today),
    qJSON("/api/stats/rides"),
    qJSON("/api/nutrition/day-summary?day="+today)
  ]);
  cal=await qJSON("/api/calendar?start="+qLocalISO(new Date(Date.now()-365*864e5))+"&end="+today);
  entMap={};(cal.entries||[]).forEach(function(e){entMap[e.day]=entMap[e.day]||[];entMap[e.day].push(e);});
  renderDziennik();renderTrendy();renderSezon();renderOdzywianie();wireButtons();
}
/* --- SEZON (2026-09-28): gdzie jestem + tydzien po tygodniu (/api/forma/season) + status w Dzienniku --- */
function renderSezon(){
  qJSON("/api/forma/season").then(function(Z){
    var W=Z.where||{},WK=Z.weeks||[];
    function c(x,d){if(x==null)return "—";return (+x).toFixed(d||0).replace(".",",");}
    function dm(s){if(!s)return "";return (+s.slice(8,10))+"."+(+s.slice(5,7));}
    /* status Dziennika - tylko to, czego nie mowi Swiezosc */
    var ds=q$("dz-season");if(ds)ds.innerHTML=(Z.status||[]).length?'Sezon: '+Z.status.join(" · "):"";
    var sub=q$("sz-sub");if(sub)sub.textContent="od "+dm(W.season_start)+" · stan na "+dm(Z.today);
    /* ===== SEZON v5: analiza AI w 4 kolumnach + interaktywny wykres sezonu (pasy, wspolna os, zakres, podglad tygodnia) ===== */
    (function(){var F=Z.facts||{};
      /* --- analiza AI --- */
      var ab=q$("s4-ai"),aw=q$("s4-ai-when"),bt=q$("s4-ai-btn");
      function showAI(g){if(!ab)return;var R=g&&g.result;
        if(g&&g.running){ab.innerHTML='<div class="muted">Analizuję sezon… (kilkanaście sekund)</div>';return;}
        if(!R){ab.innerHTML='<div class="muted">'+((g&&g.error)?"Analiza nieudana: "+g.error:"Brak analizy — kliknij „Przelicz analizę”.")+'</div>';return;}
        function col(t,a,cls){return '<div class="s4col '+(cls||"")+'"><h4>'+t+'</h4>'+((a&&a.length)?'<ul>'+a.map(function(x){return '<li>'+x+'</li>';}).join("")+'</ul>':'<div class="muted" style="font-size:13px">brak uwag</div>')+'</div>';}
        ab.innerHTML='<div style="font-size:18px;font-weight:600;line-height:1.45">'+(R.werdykt||"")+'</div><div class="s4cols">'
          +col("Co się dzieje",R.co_sie_dzieje)+col("Jak prowadzisz sezon",R.jak_prowadzisz_sezon)+col("Na co możesz liczyć",R.na_co_mozesz_liczyc)
          +col("Uwagi do planu TRENERA",R.uwagi_do_planu,(R.uwagi_do_planu||[]).length?"warn":"")+'</div>'+((g&&g.error)?'<div class="muted" style="font-size:12px;margin-top:6px">ostatnie przeliczenie nieudane: '+g.error+'</div>':'');
        if(aw)aw.textContent=g.day?("analiza z "+dm(g.day)+(g.day!==Z.today?" — nieaktualna":"")):"";}
      function poll(n){qJSON("/api/forma/season/analyze").then(function(g){showAI(g);if(g.running&&n<40)setTimeout(function(){poll(n+1);},4000);});}
      qJSON("/api/forma/season/analyze").then(function(g){showAI(g);if(g.running)poll(0);else if(!g.result||g.day!==Z.today){fetch("/api/forma/season/analyze",{method:"POST"}).then(function(){poll(0);});}});
      if(bt&&!bt._w){bt._w=1;bt.addEventListener("click",function(){fetch("/api/forma/season/analyze",{method:"POST"}).then(function(){showAI({running:true});poll(0);});});}
      var el=q$("s4-chart");if(!el)return;
      if(F.error){el.innerHTML='<div class="muted">Dane sezonu niedostępne: '+F.error+'</div>';return;}
      var ALL=F.weeks||[];if(!ALL.length)return;
      var cur=0;ALL.forEach(function(w,i){if(w.current)cur=i;});
      var PHC={bz:"#5b8def",bd:"#3fa06a",sz:"#7a8b99",tp:"#d9a441",ev:"#9b6bd6",rg:"#58b3a8",rt:"#c9895a",lz:"#8a8f98"};
      var MC=["#3fa06a","#5b8def","#d9a441","#c9895a","#9b6bd6","#58b3a8"],mcol={},mi=0;
      ALL.forEach(function(w){if(w.p_meter&&mcol[w.p_meter]==null){mcol[w.p_meter]=MC[mi%MC.length];mi++;}});
      function mname(m){return m==="nieznany"?"miernik nieopisany":m&&m.indexOf("ant:18383")===0?"nowy pająk (Grizl)":m&&m.indexOf("ant:29525")===0?"oś AHP29525 (przed okresem wady)":m&&m.indexOf("ant:30604")===0?"miernik ant:30604":m||"";}
      var T=F.trends||{},EV=F.events||[],t0=new Date(ALL[0].week+"T12:00:00");
      function wi(d){return Math.floor((new Date(d+"T12:00:00")-t0)/(7*864e5));}
      var RNG="all",PIN=null;
      function draw(){
        var a=0,b=ALL.length-1;if(RNG==="q"){a=Math.max(0,cur-13);}else if(RNG==="f"){a=cur;}
        var WK=ALL.slice(a,b+1),N=WK.length,ci=cur-a,W0=1000,G=150,pr=12,cw=(W0-G-pr)/N;
        function X(i){return G+i*cw;}function XC(i){return X(i)+cw/2;}
        var y=4,s="",P={};
        function panel(key,h,title,val){P[key]={y0:y,y1:y+h};s+='<text x="6" y="'+(y+13)+'" font-size="11.5" font-weight="700" fill="var(--ink)">'+title+'</text>'+(val?'<text x="6" y="'+(y+28)+'" font-size="11" fill="var(--ink2)">'+val+'</text>':'')+'<line x1="'+G+'" x2="'+(W0-pr)+'" y1="'+(y+h)+'" y2="'+(y+h)+'" stroke="var(--line)"/>';y+=h+10;return P[key];}
        function scale(vals,p,padk){vals=vals.filter(function(v){return v!=null;});if(!vals.length)return null;var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),pd=Math.max(padk||0.5,(hi-lo)*0.12);lo-=pd;hi+=pd;return {lo:lo,hi:hi,f:function(v){return p.y1-4-(v-lo)/(hi-lo)*(p.y1-p.y0-10);}};}
        function line(key,sc,col,dash,filt){var d="",pen=false,prev=null;WK.forEach(function(w,i){var v=w[key];if(v==null||(filt&&!filt(w,prev))){pen=false;prev=w;return;}d+=(pen?" L":"M")+XC(i).toFixed(1)+" "+sc.f(v).toFixed(1);pen=true;prev=w;});return d?'<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="2"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/>':"";}
        function axis(sc,dec,p){if(!sc)return;[sc.lo+(sc.hi-sc.lo)*0.2,sc.lo+(sc.hi-sc.lo)*0.8].forEach(function(v){s+='<text x="'+(G-4)+'" y="'+(sc.f(v)+3).toFixed(1)+'" text-anchor="end" font-size="9.5" fill="var(--muted)">'+c(v,dec||0)+'</text>';});}
        var cw0=ALL[cur];
        /* 1. fazy */
        var p0=panel("ph",26,"Faza (TRENER)",cw0.phase_name||"");var segs=[];
        WK.forEach(function(w,i){var k=w.phase_name||"";if(segs.length&&segs[segs.length-1].k===k)segs[segs.length-1].b=i;else segs.push({k:k,ph:w.phase,a:i,b:i});});
        segs.forEach(function(g){var x=X(g.a),wd=(g.b-g.a+1)*cw;s+='<rect x="'+x.toFixed(1)+'" y="'+(p0.y0+4)+'" width="'+Math.max(1,wd-1).toFixed(1)+'" height="18" rx="3" fill="'+(PHC[g.ph]||"#888")+'" opacity=".55"/>'+(wd>60?'<text x="'+(x+wd/2).toFixed(1)+'" y="'+(p0.y0+17)+'" text-anchor="middle" font-size="10.5" font-weight="600" fill="var(--ink)">'+g.k+'</text>':'');});
        /* 2. zdarzenia */
        var pe=panel("ev",16,"Wyjazdy · infekcje","");
        EV.forEach(function(e){if(e.kind==="dluga")return;var i1=wi(e.from)-a,i2=wi(e.to)-a;if(i2<0||i1>=N)return;i1=Math.max(0,i1);i2=Math.min(N-1,i2);
          s+='<rect x="'+X(i1).toFixed(1)+'" y="'+(pe.y0+3)+'" width="'+((i2-i1+1)*cw-1).toFixed(1)+'" height="10" rx="2" fill="'+(e.kind==="wyjazd"?"var(--purple)":"var(--bad)")+'"/>';});
        /* 3. godziny */
        var p1=panel("h",80,"Jazda h/tydz.","ten tydz.: "+c(cw0.hours,1)+" z "+c(cw0.plan_h,1)+" h planu");
        var hm=Math.max(4,Math.max.apply(null,WK.map(function(w){return Math.max(w.hours||0,w.plan_h||0);})))*1.1;function YH(v){return p1.y1-(v/hm)*(p1.y1-p1.y0-6);}
        if(T.typical_hours){s+='<line x1="'+G+'" x2="'+(W0-pr)+'" y1="'+YH(T.typical_hours).toFixed(1)+'" y2="'+YH(T.typical_hours).toFixed(1)+'" stroke="var(--ink2)" stroke-dasharray="4 3" opacity=".5"/><text x="'+(G-4)+'" y="'+(YH(T.typical_hours)+3).toFixed(1)+'" text-anchor="end" font-size="9.5" fill="var(--ink2)">typowo '+c(T.typical_hours,1)+'</text>';}
        WK.forEach(function(w,i){var x=X(i)+cw*0.15,bw=cw*0.7;
          if(w.hours){var yy=YH(w.hours);s+='<rect x="'+x.toFixed(1)+'" y="'+yy.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(p1.y1-yy).toFixed(1)+'" rx="1.5" fill="'+(w.ill_days>=2?"var(--bad)":w.light?"var(--muted)":"var(--blue)")+'"/>';}
          if(w.plan_h!=null&&!w.past){var yp=YH(w.plan_h);s+='<rect x="'+x.toFixed(1)+'" y="'+yp.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+Math.max(0,p1.y1-yp).toFixed(1)+'" rx="1.5" fill="none" stroke="var(--blue)" stroke-dasharray="3 2"/>';}});
        /* 4. forma */
        var W1=(F.windows||[])[1]||{};var p2=panel("f",64,"Forma","dziś "+c(W1.ctl,0));
        var sf=scale(WK.map(function(w){return w.ctl!=null?w.ctl:w.ctl_proj;}),p2,2);
        if(sf){s+=line("ctl",sf,"var(--blue)");var lp=null;WK.forEach(function(w,i){if(w.ctl!=null)lp=i;});
          if(WK.some(function(w){return w.ctl_proj!=null;})){var d=lp!=null?"M"+XC(lp).toFixed(1)+" "+sf.f(WK[lp].ctl).toFixed(1):"";WK.forEach(function(w,i){if(w.ctl_proj!=null)d+=(d?" L":"M")+XC(i).toFixed(1)+" "+sf.f(w.ctl_proj).toFixed(1);});s+='<path d="'+d+'" fill="none" stroke="var(--blue)" stroke-width="2" stroke-dasharray="5 4" opacity=".75"/>';}
          axis(sf,0);}
        /* 5. wydolnosc - caly sezon, kolor = miernik */
        var p3=panel("p",70,"Wydolność W","moc przy tym samym tętnie");
        WK.forEach(function(w,i){if(w.meter_bad)s+='<rect x="'+X(i).toFixed(1)+'" y="'+p3.y0+'" width="'+cw.toFixed(1)+'" height="'+(p3.y1-p3.y0)+'" fill="var(--muted)" opacity=".2"/>';});
        var mb=WK.map(function(w,i){return w.meter_bad?i:null;}).filter(function(v){return v!=null;});
        if(mb.length)s+='<text x="'+((X(mb[0])+X(mb[mb.length-1]+1))/2).toFixed(1)+'" y="'+(p3.y0+13)+'" text-anchor="middle" font-size="9.5" fill="var(--ink2)">wadliwy miernik — estymacja z fizyki ±10%</text>';
        var sp=scale(WK.map(function(w){return w.p_week;}).concat(WK.map(function(w){return w.p_at_hr_other_meter;})).concat(WK.map(function(w){return w.p_est_lo;})).concat(WK.map(function(w){return w.p_est_hi;})),p3,6);
        if(sp){s+=line("p_week",sp,"var(--good)");
          WK.forEach(function(w,i){if(w.p_week!=null)s+='<circle cx="'+XC(i).toFixed(1)+'" cy="'+sp.f(w.p_week).toFixed(1)+'" r="3.6" fill="var(--good)"/>';
            if(w.p_at_hr_other_meter!=null)s+='<circle cx="'+XC(i).toFixed(1)+'" cy="'+sp.f(w.p_at_hr_other_meter).toFixed(1)+'" r="3.4" fill="none" stroke="var(--ink2)" stroke-width="1.3"/>';});
          /* estymacja z fizyki w okresie wady: romb + slupek bledu +-10% */
          WK.forEach(function(w,i){var x=XC(i);
            (w.p_est_weak||[]).forEach(function(k){s+='<circle cx="'+(x+3).toFixed(1)+'" cy="'+sp.f(k.p).toFixed(1)+'" r="2.8" fill="none" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="1.5 1.5"/>';});
            if(w.p_est==null)return;var y=sp.f(w.p_est),cf=w.p_est_conf;
            s+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+sp.f(w.p_est_hi).toFixed(1)+'" y2="'+sp.f(w.p_est_lo).toFixed(1)+'" stroke="var(--good)" stroke-width="1.2" opacity="'+(cf?".7":".35")+'"/>'
              +'<path d="M'+x.toFixed(1)+' '+(y-4.5).toFixed(1)+' L'+(x+4.5).toFixed(1)+' '+y.toFixed(1)+' L'+x.toFixed(1)+' '+(y+4.5).toFixed(1)+' L'+(x-4.5).toFixed(1)+' '+y.toFixed(1)+' Z" fill="'+(cf?"var(--good)":"var(--card)")+'" stroke="var(--good)" stroke-width="1.6"'+(cf?'':' stroke-dasharray="2 1.5"')+'/>';});
          /* upal: maly znacznik nad pasem */
          WK.forEach(function(w,i){var ic=(w.hot_rides?"🌡️":"")+(w.series_days&&w.series_days.length?"⛓":"");if(ic)s+='<text x="'+XC(i).toFixed(1)+'" y="'+(p3.y0+24)+'" text-anchor="middle" font-size="9">'+ic+'</text>';});
          var spc=T.spider_change;if(spc){var si=wi(spc)-a;if(si>=0&&si<N){var sx=X(si)+cw*(((new Date(spc+"T12:00:00").getDay()+6)%7)+0.5)/7;
            s+='<line x1="'+sx.toFixed(1)+'" x2="'+sx.toFixed(1)+'" y1="'+p3.y0+'" y2="'+p3.y1+'" stroke="var(--ink2)" stroke-dasharray="2 3"/><text x="'+(sx+3).toFixed(1)+'" y="'+(p3.y1-5)+'" font-size="9.5" fill="var(--ink2)">nowy pająk</text>';}}
          axis(sp,0);}
        /* 6. tetno */
        var rn=T.rhr_norm,p4=panel("r",60,"Tętno spocz.","7 dni: "+c(W1.rhr7,1)+" · norma do "+c(rn,1));
        var sr=scale(WK.map(function(w){return w.rhr;}).concat([rn]),p4,0.6);
        if(sr){if(rn)s+='<rect x="'+G+'" y="'+sr.f(rn).toFixed(1)+'" width="'+(W0-G-pr)+'" height="'+Math.max(0,p4.y1-sr.f(rn)).toFixed(1)+'" fill="var(--good)" opacity=".08"/><text x="'+(G-4)+'" y="'+(sr.f(rn)+3).toFixed(1)+'" text-anchor="end" font-size="9.5" fill="var(--good)">norma '+c(rn,1)+'</text>';
          s+=line("rhr",sr,"var(--bad)");}
        /* 7. waga */
        var p5=panel("w",60,"Waga kg","ostatnio "+c(T.weight_last,1));
        var sw=scale(WK.map(function(w){return w.weight;}).concat(WK.map(function(w){return w.weight_path;})),p5,0.5);
        if(sw){s+=line("weight",sw,"var(--purple)");WK.forEach(function(w,i){if(w.weight!=null)s+='<circle cx="'+XC(i).toFixed(1)+'" cy="'+sw.f(w.weight).toFixed(1)+'" r="2.6" fill="var(--purple)"/>';});
          s+=line("weight_path",sw,"var(--purple)","4 3");axis(sw,0);
          if(T.weight_goal)s+='<text x="'+(W0-pr)+'" y="'+(p5.y1-6)+'" text-anchor="end" font-size="9.5" fill="var(--purple)">ścieżka do '+c(T.weight_goal.kg,0)+' kg ('+dm(T.weight_goal.by)+')</text>';}
        /* os czasu + dzis */
        var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"],lm=-1;
        WK.forEach(function(w,i){var d=new Date(w.week+"T12:00:00"),m=new Date(d.getTime()+3*864e5).getMonth();if(m!==lm){lm=m;s+='<line x1="'+X(i).toFixed(1)+'" x2="'+X(i).toFixed(1)+'" y1="4" y2="'+(y-6)+'" stroke="var(--line)" opacity=".5"/><text x="'+(X(i)+3).toFixed(1)+'" y="'+(y+8)+'" font-size="10" fill="var(--muted)">'+MN[m]+'</text>';}});
        if(ci>=0&&ci<N){var tx=X(ci)+cw*(((new Date(Z.today+"T12:00:00").getDay()+6)%7)+0.5)/7;s+='<line x1="'+tx.toFixed(1)+'" x2="'+tx.toFixed(1)+'" y1="2" y2="'+(y-6)+'" stroke="var(--accent)" stroke-width="2"/><text x="'+(tx+4).toFixed(1)+'" y="'+(y+8)+'" font-size="10.5" font-weight="700" fill="var(--accent-ink,var(--accent))">dziś</text>';}
        var H0=y+14;
        s+='<line id="s4-x" x1="0" x2="0" y1="2" y2="'+(y-6)+'" stroke="var(--ink)" stroke-width="1" opacity="0"/><rect id="s4-hit" x="'+G+'" y="0" width="'+(W0-G-pr)+'" height="'+(y-4)+'" fill="transparent" style="cursor:crosshair"/>';
        var leg='';Object.keys(mcol).forEach(function(m){leg+='<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px"><span style="width:9px;height:9px;border-radius:50%;background:'+mcol[m]+';display:inline-block"></span>'+mname(m)+'</span>';});
        el.innerHTML='<svg id="s4-svg" viewBox="0 0 '+W0+' '+H0+'" style="width:100%;height:auto;display:block;touch-action:pan-y" role="img" aria-label="Sezon tydzień po tygodniu">'+s+'</svg><div id="s4-tip"></div>'
          +'<div class="muted" style="font-size:12px;margin:6px 2px 0;line-height:1.5">Najedź na wykres = podgląd tygodnia, kliknij = przypnij pod wykresem. Słupki pełne = wykonanie (czerwone = infekcja, szare = tydzień lżejszy), obrys = plan TRENERA; przerywana forma = prognoza z planu, przerywana waga = ścieżka do celu.<br>Wydolność: zielona linia = Grizl (jeden miernik do końca sierpnia, od 23.08 nowy pająk Quarq na tym samym rowerze); puste kółka = inny rower/trenażer. Szare tło = okres wady miernika: pomiar pominięty; romb pełny = estymacja z fizyki (średnia ważona podjazdami, ±10%), romb pusty = niska pewność (&lt;20 podjazdów w tygodniu), mała kropka = pojedyncza jazda z 3–4 podjazdami (poza średnią). 🌡️ = jazdy w upale ≥30°C, ⛓ = 3. i dalszy dzień z rzędu z jazdą ≥3 h — w obu przypadkach moc przy tętnie bywa niższa (warunki, nie forma).</div>';
        /* interakcja */
        var svg=q$("s4-svg"),hit=q$("s4-hit"),xl=q$("s4-x"),tip=q$("s4-tip");
        function info(w){var ev2=EV.filter(function(e){return e.kind!=="dluga"&&wi(e.from)<=wi(w.week)&&wi(e.to)>=wi(w.week);}).map(function(e){return e.label;});
          var we=new Date(new Date(w.week+"T12:00:00").getTime()+6*864e5);
          return '<b>'+dm(w.week)+' – '+we.getDate()+'.'+(we.getMonth()+1)+'</b>'+(w.current?' · <span style="color:var(--accent)">ten tydzień</span>':'')+'<br>'+(w.phase_name||"")+(w.light?" (lżejszy)":"")
            +(w.hours!=null?'<br>jazda: <b>'+c(w.hours,1)+' h</b>':'')+(w.plan_h!=null?' · plan '+c(w.plan_h,1)+' h':'')
            +(w.ctl!=null?'<br>forma: '+c(w.ctl,0):w.ctl_proj!=null?'<br>forma (prognoza): '+c(w.ctl_proj,0):'')
            +(w.p_week!=null?'<br>wydolność: '+w.p_week+' W <span class="muted">('+(w.p_meter||"Grizl")+')</span>':'')
            +(w.p_est!=null?'<br>estymacja z fizyki: ~'+w.p_est+' W <span class="muted">('+w.p_est_lo+'–'+w.p_est_hi+' W, '+w.p_est_windows+' podjazdów'+(w.p_est_conf?'':', <b>niska pewność</b>')+')</span>'
              +(w.p_est_rides&&w.p_est_rides.length?'<br><span class="muted">&nbsp;&nbsp;'+w.p_est_rides.map(function(k){return dm(k.d)+': '+k.p+' W ('+k.n+' podj.'+(k.tmax!=null?', max '+Math.round(k.tmax)+'°C':'')+')';}).join('; ')+'</span>':''):(w.meter_bad&&w.p_week==null?'<br>wydolność: <span class="muted">wadliwy miernik, brak podjazdów do estymacji</span>':''))
            +(w.p_est_weak&&w.p_est_weak.length?'<br><span class="muted">&nbsp;&nbsp;słaba pewność (poza średnią): '+w.p_est_weak.map(function(k){return dm(k.d)+': ~'+k.p+' W ('+k.n+' podj.)';}).join('; ')+'</span>':'')
            +(w.temp_max!=null?'<br>temperatura jazd: śr. '+w.temp_avg+'°C, max '+w.temp_max+'°C'+(w.hot_rides?' · <b style="color:var(--bad)">upał: '+w.hot_rides+' jazd ≥30°C</b>':''):'')
            +(w.hot_rides?'<br><span class="muted">w upale (&gt;24°C) moc przy tętnie bywa u Ciebie o 5–10% niższa — to warunki, nie forma</span>':'')
            +(w.series_days&&w.series_days.length?'<br><b style="color:var(--accent-ink,var(--accent))">seria długich dni</b> <span class="muted">('+w.series_days.map(dm).join(", ")+' = '+(w.series_max>=3?w.series_max+'. dzień z rzędu ≥3 h':'')+') — moc przy tętnie bywa wtedy wyraźnie niższa</span>':'')+(w.p_at_hr_other_meter!=null?' <span class="muted">· inny rower '+w.p_at_hr_other_meter+' W</span>':'')
            +(w.rhr!=null?'<br>tętno spocz.: '+c(w.rhr,1):'')+(w.readiness!=null?' · gotowość '+c(w.readiness,2):'')
            +(w.weight!=null?'<br>waga: '+c(w.weight,1)+' kg':w.weight_path!=null?'<br>ścieżka wagi: '+c(w.weight_path,1)+' kg':'')
            +(ev2.length?'<br><span style="color:var(--bad)">'+ev2.join(", ")+'</span>':'');}
        function idxAt(evt){var r=svg.getBoundingClientRect(),k=(W0/r.width),xv=(evt.clientX-r.left)*k;var i=Math.floor((xv-G)/cw);return (i<0||i>=N)?null:i;}
        function show(evt){var i=idxAt(evt);if(i==null){tip.style.display="none";xl.setAttribute("opacity","0");return;}
          var x=XC(i);xl.setAttribute("x1",x);xl.setAttribute("x2",x);xl.setAttribute("opacity",".5");
          tip.innerHTML=info(WK[i]);tip.style.display="block";var r=svg.getBoundingClientRect(),px=(x/W0)*r.width;
          var left=px+14;if(left+220>r.width)left=px-230;tip.style.left=Math.max(0,left)+"px";tip.style.top="10px";}
        hit.addEventListener("mousemove",show);hit.addEventListener("mouseleave",function(){tip.style.display="none";xl.setAttribute("opacity","0");});
        hit.addEventListener("click",function(evt){var i=idxAt(evt);var pn=q$("s4-pin");if(!pn||i==null)return;PIN=WK[i].week;
          pn.innerHTML='<div style="border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:13.5px;line-height:1.5">'+info(WK[i])+'<div class="muted" style="font-size:12px;margin-top:4px">przypięty tydzień · kliknij inny, żeby zmienić</div></div>';});
        hit.addEventListener("touchstart",function(evt){if(evt.touches&&evt.touches[0])show(evt.touches[0]);},{passive:true});
        var cs=q$("s4-chart-sub");if(cs)cs.textContent=dm(WK[0].week)+" – "+dm(WK[N-1].week);
      }
      draw();
      var rg=q$("s4-rng");if(rg&&!rg._w){rg._w=1;rg.querySelectorAll("button").forEach(function(bb){bb.addEventListener("click",function(){rg.querySelectorAll("button").forEach(function(x){x.classList.remove("active");});bb.classList.add("active");RNG=bb.dataset.r;draw();});});}
    })();
    /* ===== SEZON v3: co sie ze mna dzieje / jak prowadze sezon / na co moge liczyc ===== */
    (function(){var I=Z.insight||{};var hd=q$("s3-head");if(!hd)return;
      if(I.error){hd.textContent="Analiza sezonu niedostępna: "+I.error;return;}
      hd.textContent=I.head||"";var sb=q$("s3-sub");if(sb)sb.textContent="stan na "+dm(Z.today)+" · przeliczane codziennie z Twoich danych";
      var nw=q$("s3-now");if(nw)nw.innerHTML=(I.now||[]).map(function(it){return '<div class="s3it '+(it.level||"")+'"><div class="t">'+it.title+'</div><div class="s">'+it.status+'</div><div class="x">'+it.text+'</div>'+(it.note?'<div class="n">'+it.note+'</div>':'')+'</div>';}).join("");
      var pr=q$("s3-pre");if(pr)pr.innerHTML=I.pre_signal?"🔎 "+I.pre_signal:"";
      function icon(l){return l==="good"?"✓":l==="bad"?"✗":"·";}
      var mg=q$("s3-manage");if(mg)mg.innerHTML=(I.manage||[]).map(function(m){return '<div class="s3row '+m.level+'"><span class="i">'+icon(m.level)+'</span><span><b>'+m.title+'.</b> '+m.text+'</span></div>';}).join("");
      var ex=q$("s3-expect");if(ex)ex.innerHTML=(I.expect||[]).map(function(e){return '<div class="s3row info"><span class="i">→</span><span>'+e+'</span></div>';}).join("");
      /* male wykresy: 120 dni */
      var S=I.series||{},ch=q$("s3-charts");if(!ch)return;
      var t1=new Date(Z.today+"T12:00:00"),t0=new Date(t1.getTime()-120*864e5);
      function xd(s){var d=new Date(s+"T12:00:00");return (d-t0)/(t1-t0);}
      function mini(title,pts,opt){if(!pts||pts.length<2)return "";var W0=800,H0=110,pl=34,pr=10,T0=8,T1=90;
        var vs=pts.map(function(p){return p.v;}).concat((opt.refs||[]).map(function(r){return r.v;}).filter(function(v){return v!=null;}));
        var lo=Math.min.apply(null,vs),hi=Math.max.apply(null,vs),pad=Math.max(0.5,(hi-lo)*0.15);lo-=pad;hi+=pad;
        function X(f){return pl+f*(W0-pl-pr);}function Y(v){return T1-(v-lo)/(hi-lo)*(T1-T0);}
        var s='<svg viewBox="0 0 '+W0+' '+H0+'" style="width:100%;height:auto;display:block;max-height:140px">';
        (S.ill||[]).forEach(function(r){var a=Math.max(0,xd(r[0])),b=Math.min(1,xd(r[1])+1/120);if(b<=0)return;s+='<rect x="'+X(a).toFixed(1)+'" y="'+T0+'" width="'+Math.max(3,X(b)-X(a)).toFixed(1)+'" height="'+(T1-T0)+'" fill="var(--bad)" opacity=".13"/><text x="'+((X(a)+X(b))/2).toFixed(1)+'" y="'+(T0+10)+'" text-anchor="middle" font-size="9.5" fill="var(--bad)">infekcja</text>';});
        (opt.refs||[]).forEach(function(r){if(r.v==null)return;var y=Y(r.v);s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+y.toFixed(1)+'" y2="'+y.toFixed(1)+'" stroke="'+(r.c||"var(--muted)")+'" stroke-dasharray="4 3" opacity=".8"/><text x="'+(W0-pr)+'" y="'+(y-3).toFixed(1)+'" text-anchor="end" font-size="9.5" fill="'+(r.c||"var(--muted)")+'">'+r.l+'</text>';});
        [lo+pad,hi-pad].forEach(function(v){s+='<text x="'+(pl-4)+'" y="'+(Y(v)+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+c(v,opt.dec||0)+'</text>';});
        if(opt.dots){pts.forEach(function(p){s+='<circle cx="'+X(xd(p.day)).toFixed(1)+'" cy="'+Y(p.v).toFixed(1)+'" r="3.2" fill="'+opt.col+'"><title>'+dm(p.day)+': '+c(p.v,opt.dec||0)+' '+(opt.u||"")+'</title></circle>';});}
        else{var d="";pts.forEach(function(p,i){d+=(i?" L":"M")+X(xd(p.day)).toFixed(1)+" "+Y(p.v).toFixed(1);});s+='<path d="'+d+'" fill="none" stroke="'+opt.col+'" stroke-width="2"/>';}
        var L=pts[pts.length-1];s+='<circle cx="'+X(xd(L.day)).toFixed(1)+'" cy="'+Y(L.v).toFixed(1)+'" r="4.5" fill="'+opt.col+'" stroke="var(--card)" stroke-width="1.5"/>';
        var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
        for(var k=0;k<=120;k++){var dd=new Date(t0.getTime()+k*864e5);if(dd.getDate()===1)s+='<text x="'+X(k/120).toFixed(1)+'" y="'+(H0-4)+'" font-size="9.5" fill="var(--muted)">'+MN[dd.getMonth()]+'</text>';}
        s+='</svg>';return '<div class="s3ch"><div class="h">'+title+'</div>'+s+'</div>';}
      var h=mini("Moc przy tym samym tętnie (W) — wydolność; kropka = jazda",S.p_at_hr,{col:"var(--blue)",dots:true,u:"W",refs:[{v:S.p_ref,l:"przed infekcją "+(S.p_ref||"")+" W"}]});
      h+=mini("Tętno spoczynkowe (średnia 7 dni) — regeneracja",S.rhr7,{col:"var(--bad)",dec:1,refs:[{v:S.rhr_ref,l:"start sezonu "+c(S.rhr_ref,1)},{v:S.rhr_goal,l:"norma do "+c(S.rhr_goal,1),c:"var(--good)"}]});
      h+=mini("Waga (średnia 7 dni, kg)",S.weight7,{col:"var(--purple)",dec:1,refs:[]});
      ch.innerHTML=h;
    })();
    /* ===== WIDOK SEZONU v2: naglowek, wykres formy ze zdarzeniami, plan powrotu, wyjazd, lekcje ===== */
    (function(){var V=Z.view||{};if(V.error){var e0=q$("sv-head");if(e0)e0.textContent="Widok sezonu niedostępny: "+V.error;return;}
      var hd=q$("sv-head");if(hd)hd.textContent=V.headline||"";
      var hs=q$("sv-head-sub");if(hs)hs.textContent="stan na "+dm(Z.today)+" · przeliczane codziennie z Twoich danych";
      /* wykres formy */
      var F=V.form||[],el=q$("sv-chart");
      if(el&&F.length>1){var N=F.length,W0=800,pl=30,pr=12,T0=22,T1=160,H0=182,cw=(W0-pl-pr)/(N-1);
        var idx={};F.forEach(function(p,i){idx[p.day]=i;});
        var vmax=Math.max.apply(null,F.map(function(p){return p.v;}))*1.12,vmin=0;
        function X(i){return pl+i*cw;}function Y(v){return T1-(v-vmin)/(vmax-vmin)*(T1-T0);}
        function ix(d){if(idx[d]!=null)return idx[d];var best=0;F.forEach(function(p,i){if(p.day<=d)best=i;});return best;}
        var s='<svg viewBox="0 0 '+W0+' '+H0+'" style="width:100%;height:auto;display:block;max-height:260px" role="img" aria-label="Forma w sezonie">';
        (V.events||[]).forEach(function(e){if(e.kind==="dluga")return;var a=ix(e.from),b=ix(e.to);var col=e.kind==="wyjazd"?"var(--purple)":"var(--bad)";
          s+='<rect x="'+(X(a)-2).toFixed(1)+'" y="'+T0+'" width="'+Math.max(4,X(b)-X(a)+4).toFixed(1)+'" height="'+(T1-T0)+'" fill="'+col+'" opacity=".16"><title>'+e.label+'</title></rect>'
            +'<text x="'+((X(a)+X(b))/2).toFixed(1)+'" y="'+(T0-6)+'" text-anchor="middle" font-size="10.5" font-weight="600" fill="'+col+'">'+(e.kind==="wyjazd"?"wyjazd":"infekcja")+'</text>';});
        [20,40,60,80].forEach(function(v){if(v>=vmax)return;var y=Y(v);s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+y.toFixed(1)+'" y2="'+y.toFixed(1)+'" stroke="var(--line)" opacity=".45"/><text x="'+(pl-4)+'" y="'+(y+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+v+'</text>';});
        var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
        F.forEach(function(p,i){if(p.day.slice(8,10)==="01"){s+='<text x="'+(X(i)+2).toFixed(1)+'" y="'+(H0-4)+'" font-size="10" fill="var(--muted)">'+MN[+p.day.slice(5,7)-1]+'</text><line x1="'+X(i).toFixed(1)+'" x2="'+X(i).toFixed(1)+'" y1="'+T1+'" y2="'+(T1+4)+'" stroke="var(--muted)"/>';}});
        var d="";F.forEach(function(p,i){d+=(i?" L":"M")+X(i).toFixed(1)+" "+Y(p.v).toFixed(1);});
        s+='<path d="'+d+' L'+X(N-1).toFixed(1)+' '+T1+' L'+X(0).toFixed(1)+' '+T1+' Z" fill="var(--blue)" opacity=".12"/><path d="'+d+'" fill="none" stroke="var(--blue)" stroke-width="2.4"/>';
        (V.events||[]).forEach(function(e){if(e.kind!=="dluga")return;var i=ix(e.from);s+='<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(F[i].v).toFixed(1)+'" r="3" fill="var(--accent)"><title>'+e.label+'</title></circle>';});
        var pk=V.form_peak||{};if(pk.day&&idx[pk.day]!=null){var ip=idx[pk.day];s+='<text x="'+X(ip).toFixed(1)+'" y="'+(Y(pk.v)-7).toFixed(1)+'" text-anchor="middle" font-size="10.5" fill="var(--ink2)">szczyt '+Math.round(pk.v)+'</text>';}
        var now=F[N-1].v,same=-1;for(var i=N-30;i>=0;i--){if(F[i].v<=now+0.5){same=i;break;}}
        if(same>=0){var ys=Y(now);s+='<line x1="'+X(same).toFixed(1)+'" x2="'+X(N-1).toFixed(1)+'" y1="'+ys.toFixed(1)+'" y2="'+ys.toFixed(1)+'" stroke="var(--ink2)" stroke-dasharray="4 4" opacity=".8"/><circle cx="'+X(same).toFixed(1)+'" cy="'+ys.toFixed(1)+'" r="3.5" fill="none" stroke="var(--ink2)" stroke-width="1.5"/>'
          +'<text x="'+(X(same)+6).toFixed(1)+'" y="'+(ys+14).toFixed(1)+'" font-size="10.5" fill="var(--ink2)">ten sam poziom: '+dm(F[same].day)+'</text>';}
        s+='<circle cx="'+X(N-1).toFixed(1)+'" cy="'+Y(now).toFixed(1)+'" r="5.5" fill="var(--accent)" stroke="var(--card)" stroke-width="2"/><text x="'+(X(N-1)-8).toFixed(1)+'" y="'+(Y(now)-10).toFixed(1)+'" text-anchor="end" font-size="11.5" font-weight="700" fill="var(--accent-ink,var(--accent))">tu jesteś · '+Math.round(now)+'</text>';
        s+='</svg>';el.innerHTML=s;
        var cs=q$("sv-chart-sub");if(cs)cs.textContent="forma teraz "+Math.round(now)+" · szczyt "+Math.round((V.form_peak||{}).v||0)+" · ≈ "+c(V.form_hours,1)+" h tygodniowo";}
      /* plan powrotu */
      var PL=V.plan||[],pe=q$("sv-plan");
      if(pe){var rows=PL.map(function(p){var a=dm(p.week),b=dm(p.to);
          return '<tr style="'+(p.current?'background:var(--accent-bg);':'')+'"><td style="padding:8px;border-bottom:1px solid var(--line);white-space:nowrap;font-weight:'+(p.current?'700':'500')+'">'+(p.current?'ten tydzień':a+' – '+b)+'</td>'
            +'<td style="padding:8px;border-bottom:1px solid var(--line);text-align:right;font-weight:700;white-space:nowrap">'+c(p.hours,1)+' h</td>'
            +'<td style="padding:8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap">'+c(p.long_h,1)+' h</td>'
            +'<td style="padding:8px;border-bottom:1px solid var(--line);color:var(--ink2);font-size:13px">'+(p.typical?'<b style="color:var(--good)">typowy tydzień ✓</b>':(p.rule.indexOf("po infekcji")===0?p.rule:'jeśli regeneracja w normie'))+'</td></tr>';}).join("");
        pe.innerHTML='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums"><tr style="color:var(--muted);font-size:11px;text-transform:uppercase"><th style="text-align:left;padding:4px 8px">tydzień</th><th style="text-align:right;padding:4px 8px">razem</th><th style="text-align:right;padding:4px 8px">najdłuższa jazda</th><th style="text-align:left;padding:4px 8px"></th></tr>'+rows+'</table></div>'
          +'<p class="muted" style="font-size:12.5px;margin:8px 2px 0">Do kolejnego tygodnia przechodzisz tylko, gdy regeneracja jest w normie (gotowość ≥ −0,4 i tętno spoczynkowe w normie). Jeśli nie — powtórz tydzień. Jazdy spokojne; mocniejsze akcenty dopiero po powrocie do typowego tygodnia.</p>';
        var ps=q$("sv-plan-sub");if(ps)ps.textContent="typowy tydzień "+c(V.typical_hours,1)+" h · typowa najdłuższa jazda "+c(V.typical_long_h,1)+" h";}
      /* wyjazd */
      var TR=V.trip,te=q$("sv-trip");
      if(te){if(!TR){te.innerHTML='<div class="muted">brak wyjazdu w sezonie do porównania</div>';}else{
        var tile=(Z.tiles||[]).filter(function(t){return t.id==="wyjazd";})[0];
        var chk=tile?(tile.more||[]).filter(function(x){return x.charAt(0)==="✓"||x.charAt(0)==="✗";}):[];
        te.innerHTML='<div style="font-size:16px;margin:0 0 6px">Wyjazd taki jak <b>'+TR.ref+'</b> ('+c(TR.ref_hours,0)+' h jazdy): najwcześniej od <b>'+TR.earliest_txt+'</b>, jeśli plan pójdzie bez powtórek.</div>'
          +(chk.length?'<div style="font-size:13.5px;color:var(--ink2)">Stan dziś:</div><ul style="margin:2px 0 0;padding-left:18px;font-size:13.5px;line-height:1.5">'+chk.map(function(x){var ok=x.charAt(0)==="✓";return '<li style="color:'+(ok?"var(--good)":"var(--bad)")+'"><span style="color:var(--ink)">'+x.slice(2)+'</span> '+(ok?"✓":"✗")+'</li>';}).join("")+'</ul>':'')
          +'<p class="muted" style="font-size:12.5px;margin:8px 0 0">Przed samym startem: 2–3 luźniejsze dni.</p>';}}
      /* lekcje */
      var le=q$("sv-lessons");if(le){var L=V.lessons||[];le.innerHTML=L.length?'<ul style="margin:0;padding-left:18px">'+L.map(function(x){return '<li style="margin:4px 0">'+x+'</li>';}).join("")+'</ul>':'<div class="muted">na razie brak powtarzających się wzorów</div>';}
    })();
    /* kafle statusu (fitmodel/season.py tiles) */
    var tl=q$("sz-tiles");if(tl){tl.innerHTML=(Z.tiles||[]).map(function(t){
      return '<div class="sztile '+(t.level||"")+'" role="button" tabindex="0"><div class="t">'+t.title+'</div><div class="s">'+t.status+'</div><div class="l">'+t.line+'</div>'
        +'<ul class="m">'+(t.more||[]).map(function(x){return '<li>'+x+'</li>';}).join("")+'</ul></div>';}).join("");
      tl.querySelectorAll(".sztile").forEach(function(el){function tg(){el.classList.toggle("open");}el.addEventListener("click",tg);
        el.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();tg();}});});}
    var tsub=q$("sz-tiles-sub");if(tsub)tsub.textContent="stan na "+dm(Z.today);
    /* opis slowny (fitmodel/season.py story) */
    var ST=Z.story||{},se=q$("sz-story");
    if(se){if(ST.error){se.innerHTML='<div class="muted">opis niedostępny: '+ST.error+'</div>';}else{
      function blk(t,arr,cls){if(!arr||!arr.length)return "";return '<p style="margin:12px 0 4px;font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:.03em;color:var(--ink2)">'+t+'</p><ul style="margin:0;padding-left:18px">'+arr.map(function(x){return '<li style="margin:3px 0"'+(cls?' class="'+cls+'"':'')+'>'+x+'</li>';}).join("")+'</ul>';}
      var hw=(ST.wnioski||[]).length?'<div style="border:1px solid var(--accent);background:var(--accent-bg);border-radius:10px;padding:10px 12px;margin:2px 0 6px"><p style="margin:0 0 4px;font-weight:700">Co z tego wynika</p><ul style="margin:0;padding-left:18px">'+ST.wnioski.map(function(x){return '<li style="margin:3px 0">'+x+'</li>';}).join("")+'</ul></div>':"";
      se.innerHTML=hw+blk("Gdzie jesteś teraz",ST.gdzie)+blk("Pod planowanie wyjazdów i obciążeń",ST.plan)+blk("Co się działo w sezonie — obserwacje",ST.obserwacje)+blk("Przebieg sezonu",ST.przebieg)
        +'<p class="muted" style="font-size:12px;margin:12px 0 0">'+(ST.zasady||"")+' Szczegóły w tabeli i na wykresach poniżej.</p>';}}
    var ss=q$("sz-story-sub");if(ss)ss.textContent="od "+dm(W.season_start)+" · stan na "+dm(Z.today);
    var C=W.ctl||{},HW=W.hours_week||{},LR=W.longest_ride_h||{},RH=W.rhr||{},HV=W.hrv||{};
    function row(lab,now,ref,note,cls){return '<tr><td style="padding:6px 8px;border-bottom:1px solid var(--line)">'+lab+'</td><td style="padding:6px 8px;border-bottom:1px solid var(--line);font-weight:700;text-align:right;white-space:nowrap" class="'+(cls||"")+'">'+now+'</td><td style="padding:6px 8px;border-bottom:1px solid var(--line);color:var(--ink2)">'+ref+'</td><td style="padding:6px 8px;border-bottom:1px solid var(--line);color:var(--ink2);font-size:12.5px">'+(note||"")+'</td></tr>';}
    var pctC=(C.now!=null&&C.max)?Math.round(100*C.now/C.max):null;
    var h='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums"><tr style="color:var(--muted);font-size:11px;text-transform:uppercase"><th style="text-align:left;padding:4px 8px"></th><th style="text-align:right;padding:4px 8px">teraz</th><th style="text-align:left;padding:4px 8px">sezon</th><th style="text-align:left;padding:4px 8px"></th></tr>';
    h+=row("Forma (CTL)",c(C.now),"szczyt "+c(C.max)+" ("+dm(C.max_day)+") · średnio "+c(C.avg),pctC!=null?pctC+"% szczytu":"",pctC!=null&&pctC<75?"":"");
    h+=row("Godziny / tydzień (4 tyg.)",c(HW.now_4w,1)+" h","typowo "+c(HW.typical,1)+" h · najwięcej "+c(HW.max,1)+" h ("+dm(HW.max_week)+")",HW.now_4w!=null&&HW.typical?Math.round(100*HW.now_4w/HW.typical)+"% typowego":"");
    h+=row("Najdłuższa jazda (28 dni)",c(LR.last_28d,1)+" h","w sezonie "+c(LR.season,1)+" h ("+dm(LR.season_day)+")","");
    h+=row("Tętno spoczynkowe (14 dni)",c(RH.now_14d,1),"start sezonu "+c(RH.start_28d,1),RH.delta!=null?(RH.delta>0?"+":"")+c(RH.delta,1)+" ud./min":"");
    h+=row("HRV (14 dni)",c(HV.now_14d),"start sezonu "+c(HV.start_28d),HV.delta!=null?(HV.delta>0?"+":"")+c(HV.delta)+" ms":"");
    h+=row("Gotowość (14 dni)",(W.readiness_14d>0?"+":"")+c(W.readiness_14d,2),"0 = Twoja norma","");
    if(W.days_after_illness!=null&&W.days_after_illness<=30)h+=row("Po infekcji",W.days_after_illness+" dni","koniec objawów "+dm(W.illness_last_end),W.days_after_illness<=14?"pierwsze ~2 tyg. spokojnie":"");
    h+='</table></div>';
    var we=q$("sz-where");if(we)we.innerHTML=h;
    /* wykres tygodni */
    var el=q$("sz-weeks");if(!el||!WK.length)return;
    var COL={budowa:"var(--blue)",mocny:"var(--accent)",lzejszy:"var(--muted)",wyjazd:"var(--purple)",infekcja:"var(--bad)",biezacy:"var(--line)"};
    var LAB={budowa:"budowa",mocny:"mocny",lzejszy:"lżejszy",wyjazd:"wyjazd",infekcja:"infekcja",biezacy:"bieżący"};
    var N=WK.length,W0=800,pl=30,pr=8,T0=14,T1=110,G0=124,G1=154,R0=166,R1=196,H0=214,cw=(W0-pl-pr)/N;
    var hmax=Math.max(4,Math.max.apply(null,WK.map(function(w){return w.hours||0;})))*1.1;
    function X(i){return pl+i*cw;}function YH(v){return T1-(v/hmax)*(T1-T0);}
    var s='<svg viewBox="0 0 '+W0+' '+H0+'" style="width:100%;height:auto;display:block;max-height:280px" role="img" aria-label="Sezon tydzień po tygodniu">';
    [0.5,1].forEach(function(f){var v=Math.round(hmax*f/1.1);var y=YH(v);s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+y.toFixed(1)+'" y2="'+y.toFixed(1)+'" stroke="var(--line)" opacity=".5"/><text x="'+(pl-4)+'" y="'+(y+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+v+' h</text>';});
    if(Z.typical_hours){var yt=YH(Z.typical_hours);s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+yt.toFixed(1)+'" y2="'+yt.toFixed(1)+'" stroke="var(--ink2)" stroke-dasharray="4 3" opacity=".6"/><text x="'+(W0-pr)+'" y="'+(yt-3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--ink2)">typowy tydzień '+c(Z.typical_hours,1)+' h</text>';}
    var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"],lastM=-1;
    WK.forEach(function(w,i){var x=X(i),bw=cw*0.72,y=YH(w.hours||0),col=COL[w.type]||"var(--blue)";
      var tip=dm(w.week)+" · "+LAB[w.type]+" · "+c(w.hours,1)+" h · "+w.km+" km · obciążenie "+w.xss+" · najdłuższa "+c(w.longest_h,1)+" h"+(w.ill_days?" · infekcja "+w.ill_days+" dni":"")+(w.readiness!=null?" · gotowość "+c(w.readiness,2):"")+(w.rhr!=null?" · tętno "+c(w.rhr,1):"");
      s+='<rect x="'+(x+cw*0.14).toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+Math.max(0,T1-y).toFixed(1)+'" rx="2" fill="'+col+'"'+(w.type==="biezacy"?' stroke="var(--ink2)" stroke-dasharray="3 2" fill-opacity=".4"':'')+'><title>'+tip+'</title></rect>';
      if(w.type==="wyjazd"||w.type==="infekcja")s+='<text x="'+(x+cw/2).toFixed(1)+'" y="'+(y-3).toFixed(1)+'" text-anchor="middle" font-size="9" fill="'+col+'">'+(w.type==="wyjazd"?"wyjazd":"inf.")+'</text>';
      var r=w.readiness;if(r!=null){var mid=(G0+G1)/2,hh=Math.min(1.5,Math.abs(r))/1.5*((G1-G0)/2);
        s+='<rect x="'+(x+cw*0.2).toFixed(1)+'" y="'+(r>=0?mid-hh:mid).toFixed(1)+'" width="'+(cw*0.6).toFixed(1)+'" height="'+Math.max(0.5,hh).toFixed(1)+'" fill="'+(r>=0.4?"var(--good)":r<=-0.4?"var(--bad)":"var(--muted)")+'"><title>'+dm(w.week)+': gotowość '+c(r,2)+'</title></rect>';}
      var dd=new Date(w.week+"T12:00:00");var m=new Date(dd.getTime()+3*864e5).getMonth();
      if(m!==lastM){lastM=m;s+='<text x="'+(x+2).toFixed(1)+'" y="'+(H0-3)+'" font-size="10" fill="var(--muted)">'+MN[m]+'</text>';}});
    var mid=(G0+G1)/2;s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+mid+'" y2="'+mid+'" stroke="var(--line)"/><text x="'+(pl-4)+'" y="'+(mid+3)+'" text-anchor="end" font-size="9" fill="var(--muted)">got.</text>';
    var rv=WK.map(function(w){return w.rhr;}).filter(function(v){return v!=null;});
    if(rv.length){var lo=Math.min.apply(null,rv)-0.5,hi=Math.max.apply(null,rv)+0.5;function YR(v){return R1-(v-lo)/(hi-lo)*(R1-R0);}
      var d="",pen=false;WK.forEach(function(w,i){if(w.rhr==null){pen=false;return;}d+=(pen?" L":"M")+(X(i)+cw/2).toFixed(1)+" "+YR(w.rhr).toFixed(1);pen=true;});
      if(RH.start_28d!=null){var y0=YR(RH.start_28d);s+='<line x1="'+pl+'" x2="'+(W0-pr)+'" y1="'+y0.toFixed(1)+'" y2="'+y0.toFixed(1)+'" stroke="var(--muted)" stroke-dasharray="3 3" opacity=".7"/>';}
      s+='<path d="'+d+'" fill="none" stroke="var(--bad)" stroke-width="1.6"/><text x="'+(pl-4)+'" y="'+(R0+8)+'" text-anchor="end" font-size="9" fill="var(--muted)">tętno</text>';}
    s+='</svg>';
    var lg='';["budowa","mocny","lzejszy","wyjazd","infekcja"].forEach(function(k){lg+='<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;font-size:12px"><span style="width:10px;height:10px;border-radius:2px;background:'+COL[k]+';display:inline-block"></span>'+LAB[k]+'</span>';});
    el.innerHTML='<div style="margin:0 0 4px">'+lg+'<span style="font-size:12px;color:var(--ink2)">· pasek środkowy: gotowość · linia czerwona: tętno spocz. (przerywana = start sezonu)</span></div>'+s;
  }).catch(function(){var e=q$("sz-where");if(e)e.innerHTML='<div class="muted">nie udało się pobrać danych sezonu</div>';});
}
/* --- DZIENNIK --- */
function renderDziennik(){
  var S=forma.series||[];var T=S.length?S[S.length-1]:{};
  var days=cal.days||{};var rmap={},seen={};
  (rides.rides||[]).forEach(function(r){if(seen[r.ride_key])return;seen[r.ride_key]=1;rmap[r.date]=rmap[r.date]||[];rmap[r.date].push(r);});
  var dz=q$("p-dziennik");if(!dz)return;
  /* ===== DZIENNIK (2026-09-28 v3): gora = Dzis + ostatnia jazda; liczniki gotowosc + swiezosc; 2x2 moc/W/kg/waga/jedzenie; wykres z dwiema skalami ===== */
  var DN=["niedziela","poniedziałek","wtorek","środa","czwartek","piątek","sobota"];var dd0=new Date(today+"T12:00:00");
  var de=q$("dz-date");if(de)de.textContent="Dziś · "+DN[dd0.getDay()]+" "+dd0.getDate()+"."+(dd0.getMonth()+1);
  var rd2=T.readiness_effective!=null?T.readiness_effective:T.readiness_score;
  /* kanon 2026-09-28: Swiezosc/zmeczenie Z KOREKTA (tsb_plus/atl_plus: gotowosc, samopoczucie, choroba); surowe tylko gdy brak */
  /* 2026-09-29: licznik Swiezosci = FAKTYCZNA swiezosc (fitmodel/real_load.py): treningi + cialo + samopoczucie */
  var tsb=T.tsb_real!=null?+T.tsb_real:(T.tsb_plus!=null?+T.tsb_plus:(T.tsb_raw!=null?+T.tsb_raw:(T.tsb!=null?+T.tsb:null)));
  var atlK=T.atl_plus!=null?+T.atl_plus:(T.atl_raw!=null?+T.atl_raw:T.atl);
  var ramp=T.load_ramp!=null?+T.load_ramp:null;
  /* liczniki ze SKALA NA LUKU (koniec lewy/prawy + 0). Gotowosc = srednia wazona z-score (HRV/RHR/sen wobec normy 60 dni),
     progi jak w modelu fitmodel/readiness.py: >= +0.4 swiezy, <= -0.4 zmeczony. Swiezosc (TSB): progi w stylu TrainingPeaks. */
  function gauge(id,v,lo,hi,col,val,word,sub,ticks,prev,dec){var pct=Math.max(0.001,Math.min(1,(v-lo)/(hi-lo)));var ang=Math.PI+pct*Math.PI,gx=60+50*Math.cos(ang),gy=65+50*Math.sin(ang);
    var a=q$(id+"-arc");if(!a)return;a.setAttribute("d","M10 65 A50 50 0 0 1 "+gx.toFixed(2)+" "+gy.toFixed(2));a.setAttribute("stroke",col);
    var sv=a.ownerSVGElement;sv.setAttribute("viewBox","0 0 120 80");sv.querySelectorAll(".gt").forEach(function(x){x.remove();});
    var ns="http://www.w3.org/2000/svg";(ticks||[]).forEach(function(t){var p=(t-lo)/(hi-lo),an=Math.PI+p*Math.PI,cx=Math.cos(an),cy=Math.sin(an);
      var ln=document.createElementNS(ns,"line");ln.setAttribute("class","gt");ln.setAttribute("x1",(60+43*cx).toFixed(1));ln.setAttribute("y1",(65+43*cy).toFixed(1));ln.setAttribute("x2",(60+57*cx).toFixed(1));ln.setAttribute("y2",(65+57*cy).toFixed(1));ln.setAttribute("stroke","var(--muted)");ln.setAttribute("stroke-width","1");ln.setAttribute("opacity",".7");sv.appendChild(ln);
      if(t===lo||t===hi){var tx=document.createElementNS(ns,"text");tx.setAttribute("class","gt");tx.setAttribute("x",t===lo?"10":"110");tx.setAttribute("y","78");tx.setAttribute("text-anchor","middle");tx.setAttribute("font-size","8");tx.setAttribute("fill","var(--muted)");tx.textContent=(t>0?"+":"")+t;sv.appendChild(tx);}});
    /* zmiana wzgledem wczoraj (2026-09-29): spadek = cien od dzis do wczoraj (zanika), wzrost = podswietlony przyrost */
    var dl="";
    if(prev!=null&&isFinite(prev)){
      var pp=Math.max(0.001,Math.min(1,(prev-lo)/(hi-lo))),pa=Math.PI+pp*Math.PI,px=60+50*Math.cos(pa),py=65+50*Math.sin(pa);
      var sw=parseFloat(a.getAttribute("stroke-width")||getComputedStyle(a).strokeWidth||"10")||10;
      function arcP(p1,p2){var a1=Math.PI+p1*Math.PI,a2=Math.PI+p2*Math.PI;return "M"+(60+50*Math.cos(a1)).toFixed(2)+" "+(65+50*Math.sin(a1)).toFixed(2)+" A50 50 0 0 1 "+(60+50*Math.cos(a2)).toFixed(2)+" "+(65+50*Math.sin(a2)).toFixed(2);}
      function seg(d,stroke,w,op,dash,cap){var e=document.createElementNS(ns,"path");e.setAttribute("class","gt");e.setAttribute("d",d);e.setAttribute("fill","none");e.setAttribute("stroke",stroke);
        e.setAttribute("stroke-width",w);e.setAttribute("opacity",op);if(dash)e.setAttribute("stroke-dasharray",dash);e.setAttribute("stroke-linecap",cap||"butt");sv.appendChild(e);return e;}
      if(Math.abs(pp-pct)>0.004){
        if(v>=prev){
          /* wzrost: to, co bylo wczoraj - przygaszone; przyrost - pelny kolor + jasna linia srodkiem */
          seg(arcP(0.001,pp),"var(--card)",sw+0.5,"0.55");
          seg(arcP(pp,pct),"#ffffff",Math.max(1.6,sw*0.22),"0.9",null,"round");
        }else{
          /* spadek: utracony odcinek kreskowany w kolorze licznika na pustym torze */
          seg(arcP(pct,pp),col,sw,"0.55","2.6 1.6");
          seg(arcP(pct,pp),col,Math.max(1.2,sw*0.16),"0.95");
        }}
      var mk=document.createElementNS(ns,"line");mk.setAttribute("class","gt");mk.setAttribute("x1",(60+39*Math.cos(pa)).toFixed(2));mk.setAttribute("y1",(65+39*Math.sin(pa)).toFixed(2));
      mk.setAttribute("x2",(60+61*Math.cos(pa)).toFixed(2));mk.setAttribute("y2",(65+61*Math.sin(pa)).toFixed(2));mk.setAttribute("stroke","var(--ink)");mk.setAttribute("stroke-width","2.2");mk.setAttribute("stroke-linecap","round");
      var tt=document.createElementNS(ns,"title");tt.textContent="wczoraj: "+(prev>0?"+":"")+qN(prev,dec||0);mk.appendChild(tt);sv.appendChild(mk);
      var tw2=document.createElementNS(ns,"text");tw2.setAttribute("class","gt");tw2.setAttribute("x",(60+68*Math.cos(pa)).toFixed(2));tw2.setAttribute("y",(65+68*Math.sin(pa)+2).toFixed(2));
      tw2.setAttribute("text-anchor",Math.cos(pa)<-0.3?"end":Math.cos(pa)>0.3?"start":"middle");tw2.setAttribute("font-size","6.5");tw2.setAttribute("fill","var(--ink2)");tw2.textContent="wczoraj";sv.appendChild(tw2);
      var dv=v-prev,dd=dec||0,z=Math.abs(dv)<Math.pow(10,-dd)/2;
      dl='<div style="margin-top:4px;font-size:13px">'+(z?'<span class="muted">bez zmiany vs wczoraj</span>':'<b style="color:'+(dv>0?"var(--good)":"var(--bad)")+'">'+(dv>0?"▲ +":"▼ ")+qN(dv,dd)+'</b> <span class="muted">vs wczoraj ('+(prev>0?"+":"")+qN(prev,dd)+')</span>')+'</div>';}
    q$(id+"-val").textContent=val;var w=q$(id+"-word");w.textContent=word;w.style.color=col;var s=q$(id+"-sub");if(s)s.innerHTML=(sub||"")+dl;}
  var Y=S.length>1?S[S.length-2]:null;
  if(typeof rd2==="number"){
    var word=rd2>=0.4?"świeży":rd2<=-0.4?"zmęczony":"neutralny",cls=rd2>=0.4?"good":rd2<=-0.4?"bad":"";
    /* status dnia (fitmodel/day_status.py): pigulka i werdykt = wspolny werdykt (3 dni + tetno + infekcja + obciazenie) */
    var DS=T.day_status,DSL={przeciazenie:"przeciążenie",zmeczony:"zmęczony",uwaga:"uwaga",w_normie:"w normie"},DSC={przeciazenie:"bad",zmeczony:"bad",uwaga:"",w_normie:"good"};
    var pl=q$("dz-pill");if(pl){pl.textContent=DS?DSL[DS]||DS:word;pl.className="pill "+(DS?DSC[DS]:cls);}
    /* licznik = gotowosc z 3 dni (ta, ktora wchodzi do statusu dnia); ostatnia noc tylko jako dopisek.
       Slowo zgodne z histereza statusu: "zmeczony" dopoki status liczy zmeczenie z 3 dni. */
    var g3=(T.readiness_3d!=null)?+T.readiness_3d:rd2;
    var t3=T.day_status_note&&T.day_status_note.indexOf("gotowość z 3 dni")>=0;
    var gw=t3||g3<=-0.4?"zmęczony":g3>=0.4?"świeży":"neutralny";
    var gc=gw==="zmęczony"?"var(--bad)":gw==="świeży"?"var(--good)":"var(--accent)";
    var odch=Math.abs(g3)<0.4&&!t3?"w granicach Twojej normy":(g3<0?"poniżej":"powyżej")+" Twojej normy"+(Math.abs(g3)>=1?" — wyraźnie":"");
    gauge("dz-g",g3,-2,2,gc,(g3>0?"+":"")+qN(g3,1),gw,
      odch+' <span class="muted">(średnia z 3 dni — do decyzji)</span><br>'
      +'<span class="tip" tabindex="0" data-tip="Jedna noc bywa myląca: HRV potrafi skakać o ±15 z dnia na dzień. Dlatego licznik pokazuje średnią z 3 dni, a pojedyncza noc jest tylko dopiskiem.">ostatnia noc: <b>'+(rd2>0?"+":"")+qN(rd2,1)+'</b></span>'
      +' · HRV '+qN(T.hrv_night||T.hrv,0)+' · tętno spocz. '+qN(T.rhr,0)+' · sen '+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+" h"),[-2,-0.4,0.4,2],
      Y?(Y.readiness_3d!=null?+Y.readiness_3d:(Y.readiness_effective!=null?+Y.readiness_effective:null)):null,2);
  }
  if(tsb!=null){var tw=tsb>25?"roztrenowanie":tsb>5?"świeży":tsb>=-10?"neutralnie":tsb>=-30?"trening budujący":"przeciążenie";
    var tc=tsb>25?"var(--accent)":tsb>5?"var(--good)":tsb>=-10?"var(--accent)":tsb>=-30?"var(--blue)":"var(--bad)";
    gauge("dz-t",tsb,-40,30,tc,(tsb>0?"+":"")+qN(tsb,0),tw,(T.atl_real!=null?"forma "+qN(T.ctl_xss,0)+" − zmęczenie "+qN(T.atl_real,0)+'<br><span class="tip" tabindex="0" data-tip="Faktyczne zmęczenie = zmęczenie z treningów + stan ciała (gotowość z 3 dni, tętno spocz., Body Battery, infekcja) + Twoje wpisy samopoczucia (gdy inne niż 0). Działa w obie strony: wypoczęte ciało obniża zmęczenie.">zmęczenie: z treningów '+qN(T.atl_raw,0)+(T.atl_real-T.atl_raw>=0?" + ":" − ")+"ciało "+qN(Math.abs(T.atl_real-T.atl_raw),0)+'</span>':"bilans: forma "+qN(T.ctl_xss||T.ctl,0)+" − zmęczenie "+qN(atlK,0)+" (z korektą na regenerację i chorobę)")+(ramp!=null?'<br><span class="tip" tabindex="0" data-tip="Średnie obciążenie ostatnich 7 dni podzielone przez średnie z 4 tygodni. 1,0 = norma, powyżej 1,3 = nagły skok, powyżej 1,5 = strefa ryzyka.">skok obciążenia ×'+qN(ramp,2)+'</span>'+(ramp>=1.5?' <b style="color:var(--bad)">— strefa ryzyka</b>':ramp>=1.3?' <b style="color:var(--accent)">— nagły wzrost</b>':''):''),[-40,-30,-10,5,25,30],Y?(Y.tsb_real!=null?+Y.tsb_real:(Y.tsb_plus!=null?+Y.tsb_plus:(Y.tsb_raw!=null?+Y.tsb_raw:null))):null,0);}
  if(typeof rd2==="number"){var t2=tsb!=null?tsb:0;
    var DSA={przeciazenie:"Przeciążenie — dziś wolne albo bardzo lekko (do ~1 h spokojnie).",zmeczony:"Organizm zmęczony — lekko albo wolne.",uwaga:"Uwaga — jedź spokojnie, bez akcentów.",w_normie:"W normie — trening wg planu."};
    if(T.day_status){q$("dz-verdict").innerHTML=qEsc(DSA[T.day_status]||"")+(T.day_status_note?'<div class="muted" style="font-size:13px;font-weight:400;margin-top:4px">'+qEsc(T.day_status_note)+'</div>':'');}
    else q$("dz-verdict").textContent=(ramp!=null&&ramp>=1.3&&rd2<=-0.4)?"Nagły skok obciążenia przy słabej regeneracji — ryzyko przeciążenia. Dziś wolne albo bardzo lekko.":rd2<=-0.4?(t2>-10?"Obciążenia w normie, ale organizm poniżej normy — lekko albo wolne.":"Zmęczony i obciążony — dzień regeneracji."):rd2>=0.4?(t2>5?"Świeży i wypoczęty — dobry dzień na mocny trening.":"Organizm gotowy — normalny trening."):"Dzień bez skrajności — spokojna jazda.";}
  /* strzalki trendu: dzis vs 7 dni wczesniej */
  function lastV(k,maxIdx){for(var i=maxIdx;i>=0;i--){var v=S[i]&&S[i][k];if(v!=null&&v!=="")return +v;}return null;}
  function trend(k,eps,unit,dec,upGood){var n=lastV(k,S.length-1),p=lastV(k,S.length-8);if(n==null)return {v:null,h:""};if(p==null)return {v:n,h:'<span class="muted" style="font-size:12px">brak danych sprzed 7 dni</span>'};
    var d=n-p,up=d>eps,dn=d<-eps,good=up?upGood:dn?!upGood:null;var c=good===null?"var(--muted)":good?"var(--good)":"var(--bad)";
    return {v:n,h:'<span class="tr" style="color:'+c+'">'+(up?"▲":dn?"▼":"▶")+' '+(d>0?"+":"")+qN(d,dec)+(unit?" "+unit:"")+'</span> <small>7 dni</small>'};}
  function mcard(id,lbl,t,valTxt,sub){var el=q$(id);if(!el)return;el.innerHTML='<p class="lbl">'+lbl+'</p><div class="v">'+(t.v==null?"—":valTxt)+'</div><div>'+t.h+'</div>'+(sub?'<div class="muted" style="font-size:12px">'+sub+'</div>':'');}
  var tf=trend("ftp_est_w",0.5,"W",0,true),tk=trend("w_per_kg",0.005,"",2,true),tm=trend("weight_kg",0.1,"kg",1,false);
  mcard("dz-m-ftp",'<span class="tip" tabindex="0" data-tip="Moc progowa (FTP): ile watów utrzymasz około godzinę.">Moc progowa <span class="abbr">FTP</span></span>',tf,qN(tf.v,0)+' <small>W</small>',"zapas W′ "+qN(T.wprime_modelq_kj||T.wprime,1)+" kJ");
  mcard("dz-m-wkg",'<span class="tip" tabindex="0" data-tip="Moc progowa na kilogram masy. Kluczowa pod górę.">Moc na kilogram</span>',tk,qN(tk.v,2)+' <small>W/kg</small>',"");
  mcard("dz-m-kg","Waga",tm,qN(tm.v,1)+' <small>kg</small>',"");
  /* jedzenie dzis - kompaktowo w siatce 2x2 */
  var fe=q$("dz-food");
  if(fe){var nk=nutToday||{},tgt=2100,kc=+nk.kcal||0,pr=+nk.protein_g||0,cb=+nk.carbs_g||0,ft=+nk.fat_g||0;var kP=pr*4,kC=cb*4,kF=ft*9;
    var fh='<p class="lbl">Jedzenie dziś</p><div class="v">'+qN(kc,0)+' <small class="muted" style="font-size:13px;font-weight:400">/ '+tgt+' kcal</small></div>';
    fh+='<div style="height:8px;border-radius:4px;background:var(--well);overflow:hidden"><div style="width:'+Math.min(100,Math.round(kc/tgt*100))+'%;height:100%;display:flex">'+(kc?'<div style="flex:'+kP+';background:var(--blue)"></div><div style="flex:'+kC+';background:var(--accent)"></div><div style="flex:'+kF+';background:var(--purple)"></div>':'')+'</div></div>';
    fh+='<div class="muted" style="font-size:12px">'+(kc?'<span style="color:var(--blue)">■</span> B '+qN(pr,0)+'/160 · <span style="color:var(--accent)">■</span> W '+qN(cb,0)+' · <span style="color:var(--purple)">■</span> T '+qN(ft,0)+' g · ':'brak wpisów · ')+'<a class="link" href="#odzywianie" id="dz-addfood">dodaj →</a></div>';
    fe.innerHTML=fh;
    var af=q$("dz-addfood");if(af)af.onclick=function(e){e.preventDefault();var tb=document.querySelector('#tabs button[data-t="odzywianie"]');if(tb)tb.click();};}
  /* ostatnia jazda - obok karty Dzis */
  var le=q$("dz-last");
  if(le){var uq=[],sq={};(rides.rides||[]).forEach(function(r){if(!sq[r.ride_key]){sq[r.ride_key]=1;uq.push(r);}});var LR=uq[0];
    if(LR){var ago=Math.round((new Date(today+"T12:00:00")-new Date(LR.date+"T12:00:00"))/864e5);
      le.innerHTML='<div class="cardhead"><span style="font-size:16px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+qEsc(LR.name||LR.ride_key)+'</span><span class="pill">'+(ago===0?"dziś":ago===1?"wczoraj":ago+" dni temu")+'</span></div>'
        +'<div style="display:flex;gap:22px;flex-wrap:wrap;align-items:baseline">'
        +(LR.dist_km?'<span><span class="mid">'+qN(LR.dist_km,0)+'</span> <span class="muted" style="font-size:12px">km</span></span>':'')
        +(LR.duration_s?'<span><span class="mid">'+qHM(LR.duration_s)+'</span> <span class="muted" style="font-size:12px">czas</span></span>':'')
        +(LR.xss?'<span><span class="mid" style="color:var(--accent)">'+LR.xss+'</span> <span class="muted" style="font-size:12px">XSS</span></span>':'')
        +'<a class="link" style="margin-left:auto" href="/raport-jazdy.html?ride='+encodeURIComponent(LR.ride_key)+'">Raport z jazdy →</a></div>';}
    else le.innerHTML='<div class="muted">brak jazd</div>';}
  /* obciazenie i forma 28 dni (v4): niski, gladkie linie, forma z polem, dwie skale (forma lewa / zmeczenie prawa), slupki XSS cienkim pasem */
  (function(){var el=q$("dz-load");if(!el)return;var N=28,dl=[];for(var i=N-1;i>=0;i--)dl.push(qLocalISO(new Date(Date.now()-i*864e5)));
    var sm={};S.forEach(function(x){sm[x.day]=x;});
    var xs=dl.map(function(d){var t=0;(rmap[d]||[]).forEach(function(r){t+=(+r.xss||0);});return t;});
    var ctl=dl.map(function(d){return sm[d]&&sm[d].ctl_xss!=null?+sm[d].ctl_xss:null;}),atl=dl.map(function(d){var o=sm[d];if(!o)return null;var v=o.atl_plus!=null?o.atl_plus:o.atl_raw;return v!=null?+v:null;});
    function rng(v){var p=v.filter(function(x){return x!=null;});if(!p.length)return null;var lo=Math.min.apply(null,p),hi=Math.max.apply(null,p),sp=Math.max(4,hi-lo),pd=sp*0.12;return {lo:lo-pd,hi:hi+pd,min:lo,max:hi};}
    var RC=rng(ctl),RA=rng(atl);if(!RC||!RA){el.innerHTML='<div class="muted">brak danych</div>';return;}
    var bx=Math.max(80,Math.max.apply(null,xs));
    var W=800,pl=8,pr=8,L0=6,L1=58,B1=84,B0=66,H=98,cw=(W-pl-pr)/N;
    function X(i){return pl+i*cw+cw/2;}function Y(v,R){return L1-(v-R.lo)/(R.hi-R.lo)*(L1-L0);}
    function path(v,R){var pts=[];v.forEach(function(x,i){if(x!=null)pts.push([X(i),Y(x,R)]);});if(pts.length<2)return "";
      var d="M"+pts[0][0].toFixed(1)+" "+pts[0][1].toFixed(1);for(var k=1;k<pts.length;k++){var p0=pts[k-1],p1=pts[k],mx=(p0[0]+p1[0])/2;d+=" C"+mx.toFixed(1)+" "+p0[1].toFixed(1)+" "+mx.toFixed(1)+" "+p1[1].toFixed(1)+" "+p1[0].toFixed(1)+" "+p1[1].toFixed(1);}return {d:d,first:pts[0],last:pts[pts.length-1]};}
    var pc=path(ctl,RC),pa=path(atl,RA);
    var h='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block;max-height:150px" role="img" aria-label="Obciążenie i forma"><defs><linearGradient id="dzfg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".28"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs>';
    dl.forEach(function(d,i){var dn2=new Date(d+"T12:00:00");if(dn2.getDay()===1&&i>0)h+='<line x1="'+(pl+i*cw).toFixed(1)+'" x2="'+(pl+i*cw).toFixed(1)+'" y1="'+L0+'" y2="'+B1+'" stroke="var(--line)" stroke-width="1" opacity=".6"/>';
      if(d===today)h+='<rect x="'+(pl+i*cw).toFixed(1)+'" y="'+(L0-2)+'" width="'+cw.toFixed(1)+'" height="'+(B1-L0+2)+'" rx="4" fill="var(--accent-bg)" opacity=".6"/>';});
    if(pc)h+='<path d="'+pc.d+' L'+pc.last[0].toFixed(1)+' '+L1+' L'+pc.first[0].toFixed(1)+' '+L1+' Z" fill="url(#dzfg)"/>';
    if(pa)h+='<path d="'+pa.d+'" fill="none" stroke="var(--purple)" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round" opacity=".9"/>';
    if(pc)h+='<path d="'+pc.d+'" fill="none" stroke="var(--blue)" stroke-width="2.6" stroke-linecap="round"/>';
    function dot(p,c){return p?'<circle cx="'+p.last[0].toFixed(1)+'" cy="'+p.last[1].toFixed(1)+'" r="3.4" fill="'+c+'" stroke="var(--card)" stroke-width="1.5"/>':"";}
    h+=dot(pa,"var(--purple)")+dot(pc,"var(--blue)");
    h+='<line x1="'+pl+'" x2="'+(W-pr)+'" y1="'+B1+'" y2="'+B1+'" stroke="var(--line)" stroke-width="1"/>';
    var imax=xs.indexOf(Math.max.apply(null,xs));
    xs.forEach(function(v,i){if(v<=0)return;var y=B1-(v/bx)*(B1-B0),x=pl+i*cw+cw*0.3;
      h+='<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+(cw*0.4).toFixed(1)+'" height="'+(B1-y).toFixed(1)+'" rx="1.5" fill="var(--accent)"><title>'+dl[i]+': XSS '+Math.round(v)+'</title></rect>';
      if(i===imax)h+='<text x="'+(X(i)).toFixed(1)+'" y="'+(y-3).toFixed(1)+'" text-anchor="middle" font-size="10" font-weight="600" fill="var(--ink2)">'+Math.round(v)+'</text>';});
    dl.forEach(function(d,i){var dn2=new Date(d+"T12:00:00");if(d===today||(dn2.getDay()===1&&i<N-2))h+='<text x="'+X(i).toFixed(1)+'" y="'+(H-2)+'" text-anchor="middle" font-size="10" fill="'+(d===today?"var(--accent-ink)":"var(--muted)")+'"'+(d===today?' font-weight="700"':'')+'>'+(d===today?"dziś":dn2.getDate()+"."+(dn2.getMonth()+1))+'</text>';});
    h+='</svg>';
    function pill(c,lab,now,R){return '<span style="display:inline-flex;align-items:baseline;gap:5px;margin-right:14px"><span style="width:10px;height:3px;border-radius:2px;background:'+c+';display:inline-block;align-self:center"></span>'+lab+' <b style="color:'+c+';font-size:15px">'+Math.round(now)+'</b><span class="muted" style="font-size:11.5px">('+Math.round(R.min)+'–'+Math.round(R.max)+')</span></span>';}
    var cN=ctl.filter(function(v){return v!=null;}).pop(),aN=atl.filter(function(v){return v!=null;}).pop();
    el.innerHTML='<div style="font-size:13px;margin:0 0 4px">'+pill("var(--blue)","forma",cN,RC)+pill("var(--purple)","zmęczenie",aN,RA)+'<span style="display:inline-flex;align-items:baseline;gap:5px"><span style="width:8px;height:10px;border-radius:1.5px;background:var(--accent);display:inline-block;align-self:center"></span>XSS jazd</span></div>'+h;
    var lg=q$("dz-load-leg");if(lg)lg.innerHTML='każda linia na własnej skali (w nawiasie zakres z 28 dni)';
  })();
  /* ===== OBCIAZENIE DLUGOTERMINOWE · 6 mies. (2026-09-28): srednie XSS 7/28 dni + forma (CTL) na JEDNEJ skali (XSS/dzien),
     panel skoku obciazenia 7/28 z progami 1,3/1,5, tlo = dni choroby; ponizej korekty modelu (atl_plus_note) prostym jezykiem ===== */
  (function(){var el=q$("dz-long");if(!el)return;
    function korTxt(p){p=String(p).trim();var m;
      if(/^choroba bez jazdy/.test(p))return "choroba bez jazdy — zmęczenie nie spadło (choroba to nie odpoczynek)";
      m=p.match(/^gotowosc ([+-]?[\d.]+) -> koszt x([\d.]+) \(([+-]?\d+) xss(, limit tyg\. 25%)?\)/);
      if(m){var k=+m[2];
        if(k>1)return "słaba gotowość ("+m[1].replace(".",",")+") — jazda kosztowała ×"+m[2].replace(".",",")+" (+"+Math.abs(+m[3])+")"+(m[4]?", przycięte limitem tygodniowym":"");
        return "dobra gotowość — jazda kosztowała mniej (×"+m[2].replace(".",",")+")";}
      if(/choroba, jazda/.test(p)||/^feel/.test(p)){var t=[];if(/feel -/.test(p))t.push("gorsze samopoczucie");if(/choroba/.test(p))t.push("jazda w chorobie");
        var pm=p.match(/\+(\d+)% ->/);return t.join(", ")+" — koszt jazdy +"+(pm?pm[1]:"?")+"%";}
      return "";}
    var st=qLocalISO(new Date(Date.now()-182*864e5));
    qJSON("/api/forma/data?start="+st).then(function(F){
      var L=(F.series||[]).filter(function(x){return x.day;});if(!L.length){el.innerHTML='<div class="muted">brak danych</div>';return;}
      var N=L.length,ill={};
      ((cal&&cal.entries)||[]).forEach(function(e){if(e.kind!=="illness")return;var a=new Date(e.day+"T12:00:00"),b=new Date((e.end_day||e.day)+"T12:00:00");
        for(var t=a;t<=b;t=new Date(t.getTime()+864e5))ill[qLocalISO(t)]=1;});
      function num(x,k){var v=x[k];return v!=null&&v!==""?+v:null;}
      var c28=L.map(function(x){return num(x,"load_28d");}),c7=L.map(function(x){return num(x,"load_7d");}),
          ctl=L.map(function(x){return num(x,"ctl_xss");}),rp=L.map(function(x){return num(x,"load_ramp");});
      var all=[].concat(c28,c7,ctl).filter(function(v){return v!=null;});var mx=Math.max(20,all.length?Math.max.apply(null,all):20)*1.08;
      var W=800,pl=30,pr=8,T0=8,T1=108,R0=124,R1=164,H=180,cw=(W-pl-pr)/N;
      function X(i){return pl+i*cw+cw/2;}function Y(v){return T1-(v/mx)*(T1-T0);}
      var RLO=0.4,RHI=2.0;function YR(v){v=Math.max(RLO,Math.min(RHI,v));return R1-(v-RLO)/(RHI-RLO)*(R1-R0);}
      function path(v,f){var d="",pen=false;v.forEach(function(x,i){if(x==null){pen=false;return;}d+=(pen?" L":"M")+X(i).toFixed(1)+" "+f(x).toFixed(1);pen=true;});return d;}
      var h='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block;max-height:240px" role="img" aria-label="Obciążenie długoterminowe">';
      L.forEach(function(x,i){if(ill[x.day])h+='<rect x="'+(pl+i*cw).toFixed(1)+'" y="'+T0+'" width="'+Math.max(1,cw).toFixed(1)+'" height="'+(R1-T0)+'" fill="var(--bad)" opacity=".13"/>';});
      [0.25,0.5,0.75].forEach(function(f){var v=Math.round(mx*f/10)*10;if(v<=0)return;var y=Y(v);
        h+='<line x1="'+pl+'" x2="'+(W-pr)+'" y1="'+y.toFixed(1)+'" y2="'+y.toFixed(1)+'" stroke="var(--line)" stroke-width="1" opacity=".5"/><text x="'+(pl-4)+'" y="'+(y+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+v+'</text>';});
      var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
      L.forEach(function(x,i){var dd=new Date(x.day+"T12:00:00");if(dd.getDate()===1){var xx=pl+i*cw;
        h+='<line x1="'+xx.toFixed(1)+'" x2="'+xx.toFixed(1)+'" y1="'+T0+'" y2="'+R1+'" stroke="var(--line)" stroke-width="1"/><text x="'+(xx+3).toFixed(1)+'" y="'+(H-3)+'" font-size="10" fill="var(--muted)">'+MN[dd.getMonth()]+'</text>';}});
      var p28=path(c28,Y);if(p28){var fi=0;while(fi<N&&c28[fi]==null)fi++;var la=N-1;while(la>0&&c28[la]==null)la--;
        h+='<path d="'+p28+' L'+X(la).toFixed(1)+' '+T1+' L'+X(fi).toFixed(1)+' '+T1+' Z" fill="var(--blue)" opacity=".18"/><path d="'+p28+'" fill="none" stroke="var(--blue)" stroke-width="2.2"/>';}
      var p7=path(c7,Y);if(p7)h+='<path d="'+p7+'" fill="none" stroke="var(--accent)" stroke-width="1.4" opacity=".9"/>';
      var pc=path(ctl,Y);if(pc)h+='<path d="'+pc+'" fill="none" stroke="var(--purple)" stroke-width="2" stroke-dasharray="5 4"/>';
      h+='<line x1="'+pl+'" x2="'+(W-pr)+'" y1="'+T1+'" y2="'+T1+'" stroke="var(--line)"/>';
      h+='<rect x="'+pl+'" y="'+YR(RHI).toFixed(1)+'" width="'+(W-pl-pr)+'" height="'+(YR(1.5)-YR(RHI)).toFixed(1)+'" fill="var(--bad)" opacity=".10"/>';
      h+='<rect x="'+pl+'" y="'+YR(1.5).toFixed(1)+'" width="'+(W-pl-pr)+'" height="'+(YR(1.3)-YR(1.5)).toFixed(1)+'" fill="var(--accent)" opacity=".14"/>';
      h+='<line x1="'+pl+'" x2="'+(W-pr)+'" y1="'+YR(1).toFixed(1)+'" y2="'+YR(1).toFixed(1)+'" stroke="var(--muted)" stroke-dasharray="3 3" opacity=".7"/>';
      [1.0,1.5].forEach(function(v){h+='<text x="'+(pl-4)+'" y="'+(YR(v)+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="var(--muted)">×'+v.toFixed(1).replace(".",",")+'</text>';});
      var pr2=path(rp,YR);if(pr2)h+='<path d="'+pr2+'" fill="none" stroke="var(--ink2)" stroke-width="1.6"/>';
      function dot(v,f,c){for(var i=N-1;i>=0;i--)if(v[i]!=null)return '<circle cx="'+X(i).toFixed(1)+'" cy="'+f(v[i]).toFixed(1)+'" r="3.4" fill="'+c+'" stroke="var(--card)" stroke-width="1.5"/>';return "";}
      h+=dot(c28,Y,"var(--blue)")+dot(c7,Y,"var(--accent)")+dot(ctl,Y,"var(--purple)")+dot(rp,YR,"var(--ink2)");
      L.forEach(function(x,i){var t=(+x.day.slice(8,10))+"."+(+x.day.slice(5,7))+" · tydzień "+(c7[i]!=null?Math.round(c7[i]):"—")+" · 4 tyg. "+(c28[i]!=null?Math.round(c28[i]):"—")+" · forma "+(ctl[i]!=null?Math.round(ctl[i]):"—")+" · skok "+(rp[i]!=null?"×"+rp[i].toFixed(2).replace(".",","):"—")+(ill[x.day]?" · choroba":"");
        h+='<rect x="'+(pl+i*cw).toFixed(1)+'" y="'+T0+'" width="'+Math.max(1,cw).toFixed(1)+'" height="'+(R1-T0)+'" fill="transparent"><title>'+t+'</title></rect>';});
      h+='</svg>';
      function last(v){for(var i=v.length-1;i>=0;i--)if(v[i]!=null)return v[i];return null;}
      var pk=-1,pkD=null;c28.forEach(function(v,i){if(v!=null&&v>pk){pk=v;pkD=L[i].day;}});
      var r=last(rp),l7=last(c7),l28=last(c28),lc=last(ctl);
      function pill(c,lab,v,sub){return '<span style="display:inline-flex;align-items:baseline;gap:5px;margin-right:14px"><span style="width:10px;height:3px;border-radius:2px;background:'+c+';display:inline-block;align-self:center"></span>'+lab+' <b style="color:'+c+';font-size:15px">'+v+'</b>'+(sub?'<span class="muted" style="font-size:11.5px">'+sub+'</span>':'')+'</span>';}
      var pkTxt=pkD?(", szczyt "+Math.round(pk)+" · "+(+pkD.slice(8,10))+"."+(+pkD.slice(5,7))):"";
      el.innerHTML='<div style="font-size:13px;margin:0 0 4px">'
        +pill("var(--accent)","ostatni tydzień",l7!=null?Math.round(l7):"—","/dzień")
        +pill("var(--blue)","ostatnie 4 tyg.",l28!=null?Math.round(l28):"—","/dzień"+pkTxt)
        +pill("var(--purple)","forma 6 tyg.",lc!=null?Math.round(lc):"—","")
        +pill("var(--ink2)","skok",r!=null?"×"+r.toFixed(2).replace(".",","):"—",r!=null?(r>=1.5?" strefa ryzyka":r>=1.3?" nagły wzrost":" norma"):"")
        +'</div>'+h;
      var lg=q$("dz-long-leg");if(lg)lg.innerHTML='obciążenie XSS na dzień · czerwone tło = choroba';
      var ko=q$("dz-korekty");if(ko){var rows=[],lim=qLocalISO(new Date(Date.now()-14*864e5));
        for(var i=N-1;i>=0&&rows.length<10;i--){var x=L[i];if(!x.atl_plus_note||x.day<lim)continue;
          var parts=String(x.atl_plus_note).split(" || ").map(korTxt).filter(Boolean);
          if(parts.length)rows.push('<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid var(--line);font-size:13px"><span class="muted" style="min-width:44px">'+(+x.day.slice(8,10))+"."+(+x.day.slice(5,7))+'</span><span>'+parts.join(" · ")+'</span></div>');}
        ko.innerHTML='<p class="lbl" style="margin:0 0 4px"><span class="tip" tabindex="0" data-tip="Dni, w których model zmienił koszt jazdy albo spadek zmęczenia: słaba lub dobra gotowość, samopoczucie, choroba, limit tygodniowy. Przez nie Świeżość różni się od samego bilansu treningów.">Dlaczego taka świeżość · korekty modelu z 14 dni</span></p>'
          +(rows.length?rows.join(""):'<div class="muted" style="font-size:13px">brak korekt — świeżość to sam bilans treningów</div>');}
    }).catch(function(){el.innerHTML='<div class="muted">nie udało się pobrać danych</div>';});
  })();
  /* statystyki jazd (ze START) */
  var dd=new Date(today+"T12:00:00");
  (function(){
    var g=q$("stats-grid");if(!g)return;
    var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
    var Y=dd.getFullYear();
    var dow=(dd.getDay()+6)%7;var mon=new Date(dd);mon.setDate(dd.getDate()-dow);
    var doy=Math.round((new Date(Y,dd.getMonth(),dd.getDate())-new Date(Y,0,1))/864e5)+1;
    var pyEnd=(Y-1)+"-"+qPad2(dd.getMonth()+1)+"-"+qPad2(Math.min(dd.getDate(),new Date(Y-1,dd.getMonth()+1,0).getDate()));
    var Q=[
      ["week",qLocalISO(mon),today],
      ["month",Y+"-"+qPad2(dd.getMonth()+1)+"-01",today],
      ["ytd",Y+"-01-01",today],
      ["pytd",(Y-1)+"-01-01",pyEnd],
      ["py",(Y-1)+"-01-01",(Y-1)+"-12-31"]
    ];
    function hm(s){s=Math.round(s||0);var h=Math.floor(s/3600),m=Math.round((s%3600)/60);if(m===60){h++;m=0;}return h+":"+qPad2(m);}
    function n0(x){return Math.round(x||0).toLocaleString("pl-PL");}
    function n1(x){return x>=100?n0(x):(Math.round(x*10)/10).toLocaleString("pl-PL");}
    function V(t){t=t||{};return {km:(t.distance_m||0)/1000,cnt:t.count||0,mv:t.moving_s||0,el:t.elevation_m||0};}
    function scale(v,f){return {km:v.km*f,cnt:v.cnt*f,mv:v.mv*f,el:v.el*f};}
    function pct(c,r){if(!r)return '<span class="muted">—</span>';var p=Math.round((c/r-1)*100);var col=p>=0?"var(--good)":"var(--bad)";return '<b style="color:'+col+'">'+(p>0?"+":"")+p+'%</b>';}
    var ST='border:1px solid var(--line);border-radius:12px;background:var(--well);padding:12px 14px;display:flex;flex-direction:column;gap:9px';
    function bar(c,r){
      if(!r)return "";
      var ratio=c/r,w=Math.min(ratio,1.5)/1.5*100,mark=100/1.5;
      var col=ratio>=1?"var(--good)":"var(--accent)";
      return '<div style="position:relative;height:8px;border-radius:4px;background:var(--line)"><div style="position:absolute;left:0;top:0;bottom:0;width:'+w.toFixed(1)+'%;border-radius:4px;background:'+col+'"></div><div style="position:absolute;top:-3px;bottom:-3px;left:'+mark.toFixed(1)+'%;width:2px;background:var(--ink)" title="poziom odniesienia"></div></div>';
    }
    function card(title,sub,cur,ref,refLbl,extra){
      var h='<div style="'+ST+'">';
      h+='<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px"><b style="font-size:14px">'+title+'</b><span class="muted" style="font-size:11px">'+sub+'</span></div>';
      h+='<div style="display:flex;align-items:baseline;gap:8px"><span style="font-size:30px;font-weight:800;line-height:1;color:var(--accent)">'+n0(cur.km)+'</span><span class="muted" style="font-size:13px;font-weight:600">km</span><span style="margin-left:auto;font-size:14px">'+pct(cur.km,ref&&ref.km)+'</span></div>';
      h+=bar(cur.km,ref&&ref.km);
      h+='<div style="display:grid;grid-template-columns:auto 1fr 1fr auto;gap:3px 10px;font-size:12.5px;align-items:baseline">';
      h+='<span></span><span class="muted" style="font-size:10.5px;text-align:right">teraz</span><span class="muted" style="font-size:10.5px;text-align:right">'+refLbl+'</span><span></span>';
      function row(l,c,r,f,u){h+='<span class="muted">'+l+'</span><b style="text-align:right">'+f(c)+(u?' <span class="muted" style="font-weight:400">'+u+'</span>':'')+'</b><span style="text-align:right;color:var(--ink2)">'+(ref?f(r)+(u?' '+u:''):'—')+'</span><span style="text-align:right;font-size:11.5px">'+pct(c,r)+'</span>';}
      row("km",cur.km,ref&&ref.km,n0,"");
      row("jazdy",cur.cnt,ref&&ref.cnt,function(x){return n1(x);},"");
      row("czas",cur.mv,ref&&ref.mv,hm,"h");
      row("w górę",cur.el,ref&&ref.el,n0,"m");
      h+='</div>';
      if(extra)h+='<div class="muted" style="font-size:11.5px;border-top:1px dashed var(--line);padding-top:6px">'+extra+'</div>';
      return h+'</div>';
    }
    g.innerHTML=["Tydzień","Miesiąc","Rok"].map(function(n){return '<div style="'+ST+';opacity:.5"><b style="font-size:14px">'+n+'</b><span class="muted" style="font-size:12px">ładuję…</span></div>';}).join("");
    Promise.all(Q.map(function(q){return qJSON("/api/stats/rides?start="+q[1]+"&end="+q[2]).catch(function(){return null;});})).then(function(r){
      var wk=V(r[0]&&r[0].totals),mo=V(r[1]&&r[1].totals),ytd=V(r[2]&&r[2].totals);
      var pytd=r[3]?V(r[3].totals):null,py=r[4]?V(r[4].totals):null;
      var weeksY=doy/7,monthsY=doy/(365.25/12);
      var refW=r[2]?scale(ytd,1/weeksY):null,refM=r[2]?scale(ytd,1/monthsY):null;
      var out="";
      out+=card("Tydzień",mon.getDate()+"."+(mon.getMonth()+1)+"–"+dd.getDate()+"."+(dd.getMonth()+1)+" · dzień "+(dow+1)+"/7",wk,refW,"śr. tyg. "+Y,"średnia tygodniowa od 1 stycznia "+Y);
      out+=card("Miesiąc",MN[dd.getMonth()]+" · dzień "+dd.getDate(),mo,refM,"śr. mies. "+Y,"średnia miesięczna od 1 stycznia "+Y);
      out+=card("Rok",Y+" do "+dd.getDate()+"."+(dd.getMonth()+1),ytd,pytd,(Y-1)+" do "+dd.getDate()+"."+(dd.getMonth()+1),py?("cały "+(Y-1)+": <b style=\"color:var(--ink)\">"+n0(py.km)+" km</b> · "+py.cnt+" jazd · "+hm(py.mv)+" h · "+n0(py.el)+" m"):"");
      g.innerHTML=out;
    });
  })();
  /* kalendarz miesiaca (2026-09-28): siatka 7 kolumn, wybor miesiaca, szczegoly dnia po kliknieciu.
     Jazdy z /api/calendar (bez limitu 50 z /api/rides/ready). Starsze niz zaladowany rok -> dociagane z /api/calendar. */
  (function(){var rows=q$("days");if(!rows)return;rows.className="";
  var KD={},KR={},KE={},loaded={};
  function absorb(C){var d=C.days||{},r=C.rides||{};Object.keys(d).forEach(function(k){KD[k]=d[k];});Object.keys(r).forEach(function(k){KR[k]=r[k];});
    (C.entries||[]).forEach(function(e){var a0=new Date(e.day+"T12:00:00"),b0=new Date((e.end_day||e.day)+"T12:00:00");
      for(var t=a0;t<=b0;t=new Date(t.getTime()+864e5)){var k=qLocalISO(t);KE[k]=KE[k]||[];if(KE[k].indexOf(e)<0)KE[k].push(e);}});}
  absorb(cal);
  (function(){var t=new Date();for(var i=0;i<12;i++){var m=new Date(t.getFullYear(),t.getMonth()-i,1);loaded[m.getFullYear()+"-"+("0"+(m.getMonth()+1)).slice(-2)]=1;}})();
  var MNF=["styczeń","luty","marzec","kwiecień","maj","czerwiec","lipiec","sierpień","wrzesień","październik","listopad","grudzień"];
  var ym=today.slice(0,7),sel=null;
  function sp(s){s=(s||"").toLowerCase();return s.indexOf("cycl")>=0||s.indexOf("bik")>=0||s.indexOf("gravel")>=0?"🚴🏻":s.indexOf("strength")>=0||s.indexOf("train")>=0?"🏋️":s.indexOf("walk")>=0||s.indexOf("hik")>=0?"🚶":s.indexOf("run")>=0?"🏃":s.indexOf("yoga")>=0?"🧘":s.indexOf("swim")>=0?"🏊":"•";}
  function isBike(r){return sp(r.sport)==="🚴🏻";}
  function rcls(d){if(!d||typeof d.readiness!=="number")return "";return d.readiness>0.3?"good":d.readiness>-0.3?"":"bad";}
  function mdays(y,m){return new Date(y,m+1,0).getDate();}
  function monthData(key){if(loaded[key])return Promise.resolve();var y=+key.slice(0,4),m=+key.slice(5,7)-1;
    var s=key+"-01",e=key+"-"+("0"+mdays(y,m)).slice(-2);
    return qJSON("/api/calendar?start="+s+"&end="+e).then(function(C){absorb(C);loaded[key]=1;}).catch(function(){loaded[key]=1;});}
  function detail(ds){var d=KD[ds]||{},rr=KR[ds]||[],ee=KE[ds]||[];
    var h='<div class="kd-h"><b>'+qDayName(ds)+' '+(+ds.slice(8))+' '+MNF[+ds.slice(5,7)-1]+'</b>'+(d.readiness_label?' <span class="pill small '+rcls(d)+'">'+qEsc(d.readiness_label)+'</span>':'')+'</div>';
    h+='<div class="g4" style="margin-top:8px"><div class="mini"><p class="lbl">Gotowość</p><div class="v">'+(typeof d.readiness==="number"?(d.readiness>0?"+":"")+qN(d.readiness,2):"—")+'</div></div>'
      +'<div class="mini"><p class="lbl">Sen · HRV · tętno</p><div class="v" style="font-size:15px">'+(d.sleep_score?d.sleep_score:qN(d.sleep,1)+" h")+' · '+qN(d.hrv,0)+' · '+qN(d.rhr,0)+'</div></div>'
      +'<div class="mini"><p class="lbl">Forma / zmęczenie</p><div class="v">'+qN(d.ctl,0)+' / '+qN(d.atl,0)+'</div></div>'
      +'<div class="mini"><p class="lbl">Świeżość · waga</p><div class="v" style="font-size:15px">'+(d.tsb>0?"+":"")+qN(d.tsb,1)+(d.weight_kg?' · '+qN(d.weight_kg,1)+' kg':'')+'</div></div></div>';
    if(rr.length)h+='<div style="margin-top:10px">'+rr.map(function(r){return '<div class="kd-r">'+sp(r.sport)+' <b>'+qEsc(r.name||"")+'</b> · '+(r.dist_km?qN(r.dist_km,0)+" km · ":"")+(r.duration_s?qHM(r.duration_s):"")+(r.xss?' · obciążenie '+r.xss:'')+(isBike(r)?' · <a class="link" href="/raport-jazdy.html?ride='+encodeURIComponent(r.ride_key)+'">raport →</a>':'')+'</div>';}).join("")+'</div>';
    if(ee.length)h+='<div style="margin-top:8px">'+ee.map(function(e){var ic=e.kind==="illness"?"🤕":e.kind==="feel"?"😊":"📌";return '<div class="kd-r">'+ic+' '+qEsc(e.title||(e.kind==="illness"?"choroba":""))+(e.note?' <span class="muted">— '+qEsc(e.note)+'</span>':'')+'</div>';}).join("")+'</div>';
    if(!rr.length&&!ee.length)h+='<div class="muted" style="margin-top:8px">bez jazdy i bez wpisów</div>';
    return h;}
  function draw(){var y=+ym.slice(0,4),m=+ym.slice(5,7)-1,n=mdays(y,m),first=(new Date(y,m,1).getDay()+6)%7;
    var km=0,hh=0,cnt=0,ill=0,tired=0,sl=[],hv=[];
    for(var i=1;i<=n;i++){var ds=ym+"-"+("0"+i).slice(-2),d=KD[ds]||{},rr=KR[ds]||[];
      rr.forEach(function(r){if(isBike(r)){km+=r.dist_km||0;hh+=(r.duration_s||0)/3600;cnt++;}});
      if((KE[ds]||[]).some(function(e){return e.kind==="illness";}))ill++;
      if(typeof d.readiness==="number"&&d.readiness<=-0.3)tired++;if(d.sleep_score)sl.push(d.sleep_score);if(d.hrv)hv.push(d.hrv);}
    function av(a){return a.length?Math.round(a.reduce(function(s,x){return s+x;},0)/a.length):"—";}
    var h='<div class="kal-top"><div class="kal-nav"><button type="button" data-k="-1" aria-label="poprzedni miesiąc">‹</button><b>'+MNF[m]+' '+y+'</b><button type="button" data-k="1" aria-label="następny miesiąc">›</button>'
      +(ym!==today.slice(0,7)?'<button type="button" data-k="0" class="kal-now">bieżący</button>':'')+'</div>'
      +'<div class="kal-sum"><span><b>'+cnt+'</b> jazd</span><span><b>'+qN(km,0)+'</b> km</span><span><b>'+qN(hh,1)+'</b> h</span><span>zmęczony <b>'+tired+'</b> dni</span>'+(ill?'<span style="color:var(--bad)">infekcja <b>'+ill+'</b> dni</span>':'')+'<span>śr. sen <b>'+av(sl)+'</b> · HRV <b>'+av(hv)+'</b></span></div></div>';
    h+='<div class="kal">';["pon","wt","śr","czw","pt","sob","ndz"].forEach(function(w){h+='<div class="kal-wd">'+w+'</div>';});
    for(var k=0;k<first;k++)h+='<div class="kal-c empty"></div>';
    for(var i=1;i<=n;i++){var ds=ym+"-"+("0"+i).slice(-2),d=KD[ds]||{},rr=KR[ds]||[],ee=KE[ds]||[],fut=ds>today;
      var bikes=rr.filter(isBike),other=rr.filter(function(r){return !isBike(r);});
      var bk=0,bs=0;bikes.forEach(function(r){bk+=r.dist_km||0;bs+=r.duration_s||0;});
      var illE=ee.filter(function(e){return e.kind==="illness";})[0],feelE=ee.filter(function(e){return e.kind==="feel";})[0];
      var note=(illE&&illE.title)||(feelE&&feelE.title)||"";
      h+='<div class="kal-c '+(fut?"fut ":"")+(ds===today?"today ":"")+(ds===sel?"sel ":"")+(illE?"ill ":"")+'" data-d="'+ds+'" role="button" tabindex="0">'
        +'<div class="kal-h"><span class="kal-n">'+i+'</span>'+(d.readiness_label&&!fut?'<span class="kal-r '+rcls(d)+'">'+qEsc(d.readiness_label)+'</span>':'')+'</div>'
        +(bikes.length?'<div class="kal-ride">🚴🏻 '+qN(bk,0)+' km · '+qHM(bs)+(bikes.length>1?' <span class="muted">('+bikes.length+')</span>':'')+'</div>':(!fut?'<div class="kal-rest">odpoczynek</div>':''))
        +(other.length?'<div class="kal-oth">'+other.map(function(r){return sp(r.sport)+(r.duration_s?' '+qHM(r.duration_s):'');}).join(" ")+'</div>':'')
        +(!fut&&(d.sleep_score||d.hrv)?'<div class="kal-w">sen '+(d.sleep_score||qN(d.sleep,1))+' · HRV '+qN(d.hrv,0)+'</div>':'')
        +(note?'<div class="kal-note" title="'+qEsc(note)+'">'+(illE?"🤕 ":"😊 ")+qEsc(note)+'</div>':'')
        +'</div>';}
    h+='</div><div id="kal-det" class="kal-det">'+(sel&&sel.slice(0,7)===ym?detail(sel):'<span class="muted">Kliknij dzień, żeby zobaczyć szczegóły.</span>')+'</div>';
    rows.innerHTML=h;
    rows.querySelectorAll(".kal-nav button").forEach(function(bt){bt.addEventListener("click",function(){var k=+bt.dataset.k;
      if(k===0){ym=today.slice(0,7);}else{var dt0=new Date(+ym.slice(0,4),+ym.slice(5,7)-1+k,1);ym=dt0.getFullYear()+"-"+("0"+(dt0.getMonth()+1)).slice(-2);}
      rows.querySelector(".kal").style.opacity=".5";monthData(ym).then(draw);});});
    rows.querySelectorAll(".kal-c[data-d]").forEach(function(c){function pick(){sel=c.dataset.d;draw();var dd=q$("kal-det");if(dd&&dd.scrollIntoView)dd.scrollIntoView({block:"nearest",behavior:"smooth"});}
      c.addEventListener("click",pick);c.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();pick();}});});
  }
  sel=today;draw();
  })();
}
/* --- TRENDY (z przełącznikami) --- */
var GROUPS={moc:{series:["ftp_est_w","ltp_modelq_w"],label:["Moc progowa","Próg spokojny"],color:["var(--blue)","var(--purple)"],unit:"W"},
  obc:{series:["ctl_xss","atl_raw"],label:["Forma (CTL)","Zmęczenie (ATL)"],color:["var(--blue)","var(--accent)"],unit:""},
  well:{series:["sleep_h","hrv_night","rhr"],label:["Sen (h)","HRV","RHR"],color:["var(--blue)","var(--purple)","var(--accent)"],unit:""},
  cialo:{series:["weight_kg"],label:["Waga"],color:["var(--purple)"],unit:"kg"}};
function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=SN[SN.length-1]||{};var N=SN.length;if(N<2)return;
  var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[],ltpD=[];
  var MON=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paz","lis","gru"];
  SN.forEach(function(s2){
    var d=s2.day.slice(8);var m=parseInt(s2.day.slice(5,7))-1;
    labels.push(d==="01"||d==="15"?MON[m]:"");
    ctlD.push(s2.ctl_xss!=null?Math.round(s2.ctl_xss*10)/10:null);
    var _a2=s2.atl_plus!=null?s2.atl_plus:s2.atl_raw,_t2=s2.tsb_plus!=null?s2.tsb_plus:s2.tsb_raw;
    atlD.push(_a2!=null?Math.round(_a2*10)/10:null);
    tsbD.push(_t2!=null?Math.round(_t2*10)/10:null);
    var _xd=0;var _cr=(cal&&cal.rides&&cal.rides[s2.day])||null;
    if(_cr){_cr.forEach(function(r){_xd+=(+r.xss||0);});}else{(rides.rides||[]).forEach(function(r){if(r.date===s2.day)_xd+=(r.xss||0);});}
    xssD.push(Math.round(_xd));
    cpD.push(s2.ftp_est_w||s2.ftp||null);
    ltpD.push(s2.ltp_modelq_w||null);
  });
  var isDark=document.documentElement.classList.contains("theme-dark");
  var gridCol=isDark?"rgba(255,255,255,0.06)":"rgba(0,0,0,0.06)";
  var txtCol=isDark?"#888":"#999";
  /* choroby */
  /* 2026-09-29: infekcje jako pole na caly okres (Kalendarz: day..end_day, sasiednie dni sklejane) */
  var illIdx={};(cal.entries||[]).forEach(function(e){if(e.kind!=="illness")return;var a0=e.day,b0=e.end_day||e.day;
    for(var j=0;j<N;j++){if(SN[j].day>=a0&&SN[j].day<=b0)illIdx[j]=1;}});
  var illR=[];Object.keys(illIdx).map(Number).sort(function(x,y){return x-y;}).forEach(function(i){var L=illR[illR.length-1];if(L&&i===L.b+1)L.b=i;else illR.push({a:i,b:i});});
  illR.forEach(function(r){r.label="infekcja "+(+SN[r.a].day.slice(8))+"."+(+SN[r.a].day.slice(5,7))+"–"+(+SN[r.b].day.slice(8))+"."+(+SN[r.b].day.slice(5,7));});
  var vertPlugin={id:"illBands",beforeDatasetsDraw:function(chart){var ctx=chart.ctx,xA=chart.scales.x,yA=chart.scales.y,w=(xA.right-xA.left)/Math.max(1,N);
      illR.forEach(function(r){var x0=xA.getPixelForValue(r.a)-w/2,x1=xA.getPixelForValue(r.b)+w/2;ctx.save();
        ctx.fillStyle="rgba(229,83,75,0.22)";ctx.fillRect(x0,yA.top,x1-x0,yA.bottom-yA.top);
        ctx.strokeStyle="rgba(229,83,75,0.9)";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x0,yA.top);ctx.lineTo(x0,yA.bottom);ctx.moveTo(x1,yA.top);ctx.lineTo(x1,yA.bottom);ctx.stroke();ctx.restore();});},
    afterDraw:function(chart){var ctx=chart.ctx,xA=chart.scales.x,yA=chart.scales.y,w=(xA.right-xA.left)/Math.max(1,N);
      illR.forEach(function(r){var x0=xA.getPixelForValue(r.a)-w/2,x1=xA.getPixelForValue(r.b)+w/2,xm=(x0+x1)/2;ctx.save();
        ctx.font="600 11px sans-serif";var tw=ctx.measureText(r.label).width+12;
        ctx.fillStyle="rgba(229,83,75,0.95)";ctx.beginPath();if(ctx.roundRect)ctx.roundRect(xm-tw/2,yA.top+4,tw,18,9);else ctx.rect(xm-tw/2,yA.top+4,tw,18);ctx.fill();
        ctx.fillStyle="#fff";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(r.label,xm,yA.top+13);ctx.restore();});}};
  /* GORNY WYKRES */
  /* 2026-09-29: GORNY WYKRES z przelacznikami - forma, zmeczenie/swiezosc FAKTYCZNE, gotowosc 3 dni, stan ciala,
     skok obciazenia, wersje treningowe do porownania, tlo statusu dnia. Wybor zapamietany (localStorage). */
  if(window._trendyChart){window._trendyChart.destroy();}
  var canvas=q$("trendy-canvas");if(!canvas)return;
  function col(k){return SN.map(function(s2){var v=s2[k];return v!=null&&v!==""?Math.round(+v*100)/100:null;});}
  var DEFS=[
    {k:"ctl",lab:"forma",data:ctlD,c:"#e67e22",w:3,ax:"y",on:1,tip:"średnie obciążenie ~6 tygodni"},
    {k:"atlf",lab:"zmęczenie faktyczne",data:col("atl_real"),c:isDark?"#c9c9c9":"#666",w:2,ax:"y",on:1,fill:true,tip:"treningi + stan ciała + samopoczucie"},
    {k:"tsbf",lab:"świeżość faktyczna",data:col("tsb_real"),c:"#1a9a6a",w:2.2,ax:"y2",on:1,tip:"forma − zmęczenie faktyczne"},
    {k:"r3",lab:"gotowość (3 dni)",data:col("readiness_3d"),c:"#8b7cf6",w:2,ax:"yR",on:1,tip:"HRV, tętno, sen — średnia 3 dni"},
    {k:"body",lab:"stan ciała",data:col("body_load"),c:"#e5534b",w:1.6,ax:"yR",on:0,dash:[3,3],tip:"> 0 zmęczone ciało, < 0 wypoczęte"},
    {k:"r1",lab:"gotowość (1 noc)",data:col("readiness_effective"),c:"#b9a8ff",w:1,ax:"yR",on:0,dash:[2,2],tip:"pojedyncza noc — szybki, ale nerwowy sygnał"},
    {k:"ramp",lab:"skok obciążenia",data:col("load_ramp"),c:"#d9a441",w:1.6,ax:"yK",on:0,tip:"tydzień / 4 tygodnie; ≥1,3 nagły wzrost"},
    {k:"atl",lab:"zmęczenie z treningów",data:atlD,c:isDark?"#6a6a6a":"#aaa",w:1.2,ax:"y",on:0,dash:[5,3],tip:"ATL+ — sam trening"},
    {k:"tsb",lab:"świeżość z treningów",data:tsbD,c:"#1a7a5a",w:1.2,ax:"y2",on:0,dash:[6,3],tip:"TSB+ — sam trening"},
    {k:"xss",lab:"obciążenie dnia",data:xssD,c:isDark?"rgba(255,255,255,0.14)":"rgba(0,0,0,0.12)",bar:true,ax:"y3",on:1,tip:"wysiłek z jazd tego dnia"},
    {k:"stat",lab:"tło: status dnia",status:true,c:"rgba(229,83,75,.5)",on:1,tip:"czerwone = przeciążenie, pomarańczowe = zmęczony, żółte = uwaga"}
  ];
  var ON={};try{ON=JSON.parse(localStorage.getItem("trendy_on")||"{}");}catch(e){ON={};}
  function isOn(d){return ON[d.k]!=null?!!ON[d.k]:!!d.on;}
  var stat=SN.map(function(s2){return s2.day_status||null;});
  var statPlugin={id:"statBg",beforeDatasetsDraw:function(ch){var dd=DEFS.filter(function(x){return x.status;})[0];if(!isOn(dd))return;
    var c2=ch.ctx,xA=ch.scales.x,yA=ch.scales.y,w=(xA.right-xA.left)/Math.max(1,N);
    var CL={przeciazenie:"rgba(229,83,75,0.20)",zmeczony:"rgba(232,116,42,0.14)",uwaga:"rgba(217,164,65,0.10)"};
    c2.save();stat.forEach(function(s0,i){if(!CL[s0])return;var x=xA.getPixelForValue(i);c2.fillStyle=CL[s0];c2.fillRect(x-w/2,yA.top,w,yA.bottom-yA.top);});c2.restore();}};
  var datasets=DEFS.filter(function(d){return !d.status;}).map(function(d){
    var o={label:d.lab,data:d.data,borderColor:d.c,borderWidth:d.w||1.5,pointRadius:0,pointHoverRadius:4,tension:0.35,fill:false,yAxisID:d.ax,hidden:!isOn(d),_k:d.k,spanGaps:true};
    if(d.dash)o.borderDash=d.dash;
    if(d.fill){o.fill=true;o.backgroundColor=isDark?"rgba(200,200,200,0.08)":"rgba(100,100,100,0.08)";}
    if(d.bar){o.type="bar";o.backgroundColor=d.c;o.borderWidth=0;o.barPercentage=0.8;o.categoryPercentage=1;o.order=9;}
    return o;});
  window._trendyChart=new Chart(canvas,{type:"line",data:{labels:labels,datasets:datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
    plugins:{legend:{display:false},
      tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,
        callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;var s0=SN[i]||{};var L={przeciazenie:"przeciążenie",zmeczony:"zmęczony",uwaga:"uwaga",w_normie:"w normie"};return (s0.day||"")+(s0.day_status?"  ·  "+(L[s0.day_status]||s0.day_status):"");},
          label:function(ctx){if(ctx.dataset._k==="xss"&&!ctx.parsed.y)return null;var v=ctx.parsed.y;if(v==null)return null;var d=["r3","r1","body","ramp"].indexOf(ctx.dataset._k)>=0?2:0;return ctx.dataset.label+": "+(Math.round(v*Math.pow(10,d))/Math.pow(10,d));},
          afterBody:function(items){if(!items.length)return "";var i=items[0].dataIndex;var s0=SN[i]||{};var out=[];if(s0.day_status_note)out.push(s0.day_status_note);return out;}}}},
    scales:{x:{ticks:{color:txtCol,font:{size:11},maxRotation:0,autoSkip:true,maxTicksLimit:10},grid:{display:false}},
      y:{position:"left",ticks:{color:"#e67e22",font:{size:11}},grid:{color:gridCol},title:{display:true,text:"forma / zmęczenie",color:txtCol,font:{size:11}}},
      y2:{position:"right",ticks:{color:"#1a9a6a",font:{size:11}},grid:{drawOnChartArea:false},title:{display:true,text:"świeżość",color:"#1a9a6a",font:{size:11}}},
      yR:{position:"right",min:-2.5,max:2.5,display:"auto",ticks:{color:"#8b7cf6",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"gotowość / ciało",color:"#8b7cf6",font:{size:10}}},
      yK:{position:"right",min:0.4,max:2,display:"auto",ticks:{color:"#d9a441",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"skok",color:"#d9a441",font:{size:10}}},
      y3:{display:false,beginAtZero:true}}
  },plugins:[vertPlugin,statPlugin]});
  /* przelaczniki (chipy) */
  var tg=q$("trendy-toggles");
  if(tg){tg.innerHTML=DEFS.map(function(d){var on=isOn(d);
      return '<button type="button" class="tchip'+(on?" on":"")+'" data-k="'+d.k+'" data-desc="'+qEsc(d.tip||"")+'" aria-label="'+qEsc(d.lab+": "+(d.tip||""))+'"><span class="tdot" style="background:'+(d.status?"linear-gradient(90deg,rgba(229,83,75,.6),rgba(232,116,42,.5),rgba(217,164,65,.45))":d.c)+(d.dash?';opacity:.75':'')+'"></span>'+d.lab+'</button>';}).join("");
    /* opis po najechaniu (nie po kliknieciu - klik wlacza/wylacza serie) */
    var tt=document.getElementById("tchip-tt");if(!tt){tt=document.createElement("div");tt.id="tchip-tt";tt.className="tchip-tt";document.body.appendChild(tt);}
    function showTT(bt){var r=bt.getBoundingClientRect();tt.innerHTML="<b>"+qEsc(bt.textContent)+"</b><br>"+qEsc(bt.getAttribute("data-desc")||"")+"<div class='tchip-tt-h'>kliknij, żeby "+(bt.classList.contains("on")?"ukryć":"pokazać")+"</div>";
      tt.style.display="block";var x=Math.min(window.innerWidth-tt.offsetWidth-8,Math.max(8,r.left+r.width/2-tt.offsetWidth/2));
      tt.style.left=(x+window.scrollX)+"px";tt.style.top=(r.bottom+window.scrollY+6)+"px";}
    function hideTT(){tt.style.display="none";}
    tg.querySelectorAll(".tchip").forEach(function(bt){bt.addEventListener("mouseenter",function(){showTT(bt);});bt.addEventListener("mouseleave",hideTT);
      bt.addEventListener("focus",function(){showTT(bt);});bt.addEventListener("blur",hideTT);});
    tg.querySelectorAll(".tchip").forEach(function(bt){bt.addEventListener("click",function(){var k=bt.dataset.k,d=DEFS.filter(function(x){return x.k===k;})[0];
      ON[k]=!isOn(d);try{localStorage.setItem("trendy_on",JSON.stringify(ON));}catch(e){}
      bt.classList.toggle("on",ON[k]);if(tt.style.display==="block")showTT(bt);var ch=window._trendyChart;
      ch.data.datasets.forEach(function(ds){if(ds._k===k)ds.hidden=!ON[k];});ch.update("none");});});}
  /* DOLNY WYKRES (moc) */
  var PWRMODE="cp";
  function buildPwr(){
    if(window._pwrChart){window._pwrChart.destroy();}
    var pwrCanvas=q$("trendy-pwr-canvas");if(!pwrCanvas)return;
    var ds=[];
    if(PWRMODE==="cp"||PWRMODE==="oba")ds.push({label:"CP",data:cpD,borderColor:"#3b82f6",borderWidth:2.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false});
    if(PWRMODE==="ltp"||PWRMODE==="oba")ds.push({label:"LTP",data:ltpD,borderColor:"#9b59b6",borderWidth:2,borderDash:[4,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false});
    window._pwrChart=new Chart(pwrCanvas,{type:"line",data:{labels:labels,datasets:ds},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:ds.length>1,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:20,padding:10,color:txtCol,font:{size:11}}},
        tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";}}}},
      scales:{x:{display:false},y:{position:"left",ticks:{color:txtCol,font:{size:10}},grid:{color:gridCol}}}}});
    /* sync hover */
    canvas.addEventListener("mousemove",function(evt){syncHover(window._trendyChart,window._pwrChart,evt);});
    canvas.addEventListener("mouseleave",function(){clearSync(window._pwrChart);});
    pwrCanvas.addEventListener("mousemove",function(evt){syncHover(window._pwrChart,window._trendyChart,evt);});
    pwrCanvas.addEventListener("mouseleave",function(){clearSync(window._trendyChart);});
    var pl=q$("pwr-label");if(pl){var cpNow=cpD[N-1],ltpNow=ltpD[N-1];pl.textContent=(cpNow?"CP "+Math.round(cpNow)+" W":"")+(cpNow&&ltpNow?" / ":"")+(ltpNow?"LTP "+Math.round(ltpNow)+" W":"");}
  }
  function syncHover(src,dst,evt){
    var pts=src.getElementsAtEventForMode(evt,"index",{intersect:false},true);
    if(pts.length){var idx=pts[0].index;var els=[];dst.data.datasets.forEach(function(_,di){els.push({datasetIndex:di,index:idx});});
      dst.setActiveElements(els);dst.update("none");}
  }
  function clearSync(dst){dst.setActiveElements([]);dst.update("none");}
  /* wspolny tooltip */
  function showTip(topCtx,botCtx){
    var tip=document.getElementById("trendy-tip");if(!tip)return;
    var ctx=topCtx||botCtx;if(!ctx||!ctx.tooltip||!ctx.tooltip.dataPoints||!ctx.tooltip.dataPoints.length){tip.style.display="none";return;}
    var idx=ctx.tooltip.dataPoints[0].dataIndex;
    var day=SN[idx]?SN[idx].day:"";
    var html='<b>'+day+'</b><br>';
    html+='<span style="color:#e67e22">forma: '+(ctlD[idx]!=null?Math.round(ctlD[idx]):"—")+'</span><br>';
    html+='<span style="color:'+(isDark?"#777":"#aaa")+'">zmeczenie: '+(atlD[idx]!=null?Math.round(atlD[idx]):"—")+'</span><br>';
    html+='<span style="color:#1a7a5a">swiezosc: '+(tsbD[idx]!=null?Math.round(tsbD[idx]):"—")+'</span><br>';
    if(xssD[idx])html+='obc. dnia: '+Math.round(xssD[idx])+'<br>';
    html+='<span style="color:#3b82f6">CP: '+(cpD[idx]!=null?Math.round(cpD[idx])+" W":"—")+'</span>';
    if(ltpD[idx]!=null)html+=' <span style="color:#9b59b6">LTP: '+Math.round(ltpD[idx])+' W</span>';
    tip.innerHTML=html;tip.style.display="block";
    var ev=ctx.tooltip.caretX!=null?ctx.tooltip:ctx.tooltip;
    var rect=(topCtx?q$("trendy-canvas"):q$("trendy-pwr-canvas")).getBoundingClientRect();
    tip.style.left=Math.min(rect.left+(ctx.tooltip.caretX||0)+12,window.innerWidth-200)+"px";
    tip.style.top=(rect.top+(ctx.tooltip.caretY||0)-10)+"px";
  }
  canvas.addEventListener("mouseleave",function(){var tip=document.getElementById("trendy-tip");if(tip)tip.style.display="none";});
  q$("trendy-pwr-canvas").addEventListener("mouseleave",function(){var tip=document.getElementById("trendy-tip");if(tip)tip.style.display="none";});
  buildPwr();
  /* przelacznik CP/LTP */
  q$("pwr-seg").querySelectorAll("button").forEach(function(b){b.addEventListener("click",function(){
    q$("pwr-seg").querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");PWRMODE=b.dataset.p;buildPwr();});});
  /* WELLNESS CHART */
  var sleepD=[],hrvD=[],rhrD=[],wtD=[],rdyD=[];
  SN.forEach(function(s2){sleepD.push(s2.sleep_score||null);hrvD.push(s2.hrv_night||null);rhrD.push(s2.rhr||null);wtD.push(s2.weight_kg||null);rdyD.push(s2.readiness_effective!=null?s2.readiness_effective:(s2.readiness_score!=null?s2.readiness_score:null));});
  function buildWellness(){
    if(window._wellChart){window._wellChart.destroy();}
    var wc=q$("trendy-well-canvas");if(!wc)return;
    var checks=q$("well-checks");var show={sleep:true,hrv:true,rhr:true,wt:false,rdy:false};
    if(checks)checks.querySelectorAll("input").forEach(function(cb){show[cb.dataset.w]=cb.checked;});
    var ds=[],hasRight=show.wt;
    if(show.sleep)ds.push({label:"sen (score)",data:sleepD,borderColor:"#3b82f6",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.hrv)ds.push({label:"HRV",data:hrvD,borderColor:"#9b59b6",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.rhr)ds.push({label:"RHR",data:rhrD,borderColor:"#e74c3c",borderWidth:1.5,borderDash:[4,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.wt)ds.push({label:"waga (kg)",data:wtD,borderColor:"#e67e22",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw2"});
    if(show.rdy)ds.push({label:"gotowość",data:rdyD,borderColor:"#22c55e",borderWidth:2,borderDash:[6,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"ywr"});
    var scalesW={x:{display:false},yw:{position:"left",ticks:{color:txtCol,font:{size:10}},grid:{color:gridCol}}};
    if(hasRight)scalesW.yw2={position:"right",ticks:{color:"#e67e22",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"kg",color:"#e67e22",font:{size:10}}};
    if(show.rdy)scalesW.ywr={position:"right",ticks:{color:"#22c55e",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"gotowość",color:"#22c55e",font:{size:10}}};
    window._wellChart=new Chart(wc,{type:"line",data:{labels:labels,datasets:ds},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:20,padding:10,color:txtCol,font:{size:11}}},
        tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";}}}},
      scales:scalesW}});
  }
  buildWellness();
  q$("well-checks").querySelectorAll("input").forEach(function(cb){cb.addEventListener("change",buildWellness);});
  
  /* komentarz */
  var cEl=q$("trendy-comment");if(cEl){
    var ctlNow=ctlD[N-1]||0,ctlPrev=ctlD[0]||0,tsbNow=tsbD[N-1]||0;
    var parts=[];
    if(ctlNow>ctlPrev+3)parts.push("forma rosnie ("+Math.round(ctlPrev)+" \u2192 "+Math.round(ctlNow)+")");
    else if(ctlNow<ctlPrev-3)parts.push("forma spada ("+Math.round(ctlPrev)+" \u2192 "+Math.round(ctlNow)+")");
    else parts.push("forma stabilna (~"+Math.round(ctlNow)+")");
    if(tsbNow>15)parts.push("duza swiezosc (+"+Math.round(tsbNow)+")");
    else if(tsbNow>0)parts.push("lekka swiezosc (+"+Math.round(tsbNow)+")");
    else if(tsbNow>-10)parts.push("swiezosc blisko zera");
    else parts.push("zmeczony (TSB "+Math.round(tsbNow)+")");
    cEl.textContent=parts.join(" \u00b7 ");
  }
  /* statystyki */
  var sg=q$("trendy-stats");
  if(sg){var days2=SN.map(function(s2){return s2.day;});var rideCnt=0,rideKm=0,seen2={};(rides.rides||[]).forEach(function(r){if(seen2[r.ride_key])return;seen2[r.ride_key]=1;if(r.date>=days2[0]&&r.date<=days2[N-1]){rideCnt++;rideKm+=(r.dist_km||0);}});
    sg.innerHTML='<div class="mini"><p class="lbl">jazdy</p><div class="v">'+rideCnt+'</div></div><div class="mini"><p class="lbl">dystans</p><div class="v">'+Math.round(rideKm)+' km</div></div><div class="mini"><p class="lbl">CP</p><div class="v">'+Math.round(cpD[N-1]||0)+' W</div></div><div class="mini"><p class="lbl">W/kg</p><div class="v">'+qN(T.w_per_kg||T.wkg,2)+'</div></div>';}
}
/* --- ODZYWIANIE --- */
function renderOdzywianie(){
  var ns=(nutri&&nutri.series)||[];
  var n30=ns.slice(-30);var intN=0,intS=0,protS=0,wtLast=null;
  n30.forEach(function(d){if(d.intake_kcal){intN++;intS+=d.intake_kcal;protS+=(d.protein_g||0);}if(d.weight_kg)wtLast=d.weight_kg;});
  var avgKcal=intN?Math.round(intS/intN):0;var avgProt=intN?Math.round(protS/intN):0;
  var g3=document.querySelector("#p-odzywianie .g3");
  if(g3){var totN=0,totS=0;n30.forEach(function(d){totN++;totS+=(d.kcal_total||0);});var avgBurn=totN?Math.round(totS/totN):0;var bal=avgKcal-avgBurn;
    g3.innerHTML='<div class="card tight"><p class="lbl">Bilans dzienny</p><div class="big" style="margin-top:4px">'+(bal>0?"+":"")+bal+'<span class="u">kcal</span></div><div class="delta">'+avgKcal+' zjedzone · '+avgBurn+' spalone</div></div><div class="card tight"><p class="lbl">Białko (średnio)</p><div class="big" style="margin-top:4px">'+avgProt+'<span class="u">g</span></div><div class="delta '+(avgProt>=150?"up":"warn")+'">cel 160 g'+(avgProt<160?" · brakuje "+(160-avgProt):"")+'</div></div><div class="card tight"><p class="lbl">Waga</p><div class="big" style="margin-top:4px">'+(wtLast?qN(wtLast,1):"—")+'<span class="u">kg</span></div><div class="delta">cel 100 do 30.09</div></div>';}
  /* Dziś: posilki z nutToday */
  var todayCard=document.querySelector("#p-odzywianie .card:nth-child(2)");
  if(todayCard&&nutToday){var nt=nutToday;
    var hdr=todayCard.querySelector(".cardhead");if(hdr)hdr.innerHTML='<h2>Dziś</h2><span class="sub">'+(nt.kcal||0)+' / 2 100 kcal</span>';
    var items=nt.items||[];var rowsEl=todayCard.querySelector(".rows");
    if(rowsEl){rowsEl.innerHTML="";items.forEach(function(it){
      var div=document.createElement("div");div.className="r";
      div.innerHTML='<span class="w">'+(it.time||"")+'</span><span class="s">'+qEsc(it.name||it.label||"")+'</span><span class="chev"></span>';
      rowsEl.appendChild(div);});
      if(!items.length)rowsEl.innerHTML='<div class="r"><span class="w">brak wpisów</span></div>';
    }
    var sub=todayCard.querySelector(".sub:last-of-type");
    if(sub)sub.innerHTML='<span>'+Math.round(nt.kcal/21)+'% celu</span>';
  }
  /* wykres wagi */
  var wch=document.querySelector("#p-odzywianie .chart");if(!wch)return;
  var wpts=n30.filter(function(d){return d.weight_kg;});
  if(wpts.length<2){wch.innerHTML='<text x="320" y="55" text-anchor="middle" font-size="14" fill="var(--muted)">za mało pomiarów wagi</text>';return;}
  var W=640,H=110,ml=40,mr=10,mt=10,mb=15,pw=W-ml-mr,ph=H-mt-mb;
  var wmin=1e9,wmax=-1e9;wpts.forEach(function(d){wmin=Math.min(wmin,d.weight_kg);wmax=Math.max(wmax,d.weight_kg);});wmin-=0.5;wmax+=0.5;
  var svg='<line class="grid" x1="'+ml+'" y1="'+mt+'" x2="'+W+'" y2="'+mt+'"/><line class="grid" x1="'+ml+'" y1="'+(mt+ph)+'" x2="'+W+'" y2="'+(mt+ph)+'"/>';
  svg+='<text class="ax" x="'+(ml-4)+'" y="'+(mt+4)+'" text-anchor="end">'+qN(wmax,1)+'</text><text class="ax" x="'+(ml-4)+'" y="'+(mt+ph+4)+'" text-anchor="end">'+qN(wmin,1)+'</text>';
  var pts="";wpts.forEach(function(d,i){pts+=(ml+i/(wpts.length-1)*pw).toFixed(1)+","+(mt+(1-(d.weight_kg-wmin)/(wmax-wmin))*ph).toFixed(1)+" ";});
  svg+='<polyline points="'+pts.trim()+'" fill="none" stroke="var(--purple)" stroke-width="2.5"/>';
  wch.innerHTML=svg;
}
/* --- PRZEŁĄCZNIKI --- */
function wireButtons(){
  /* zakres: 7/30/90/rok */
  var rng=q$("rng");if(rng)rng.querySelectorAll("button").forEach(function(b){b.addEventListener("click",function(){
    rng.querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");
    var t=b.textContent.trim();RNG=t==="7 dni"?7:t==="30 dni"?30:t==="90 dni"?90:365;
    /* 2026-09-29: Forma laduje ~90 dni; dla "rok" doczytaj brakujace dane (seria konczy sie dzis, wiec podmiana jest bezpieczna) */
    var have=(forma.series||[]).length;
    if(RNG>have-1&&!window._formaLong){window._formaLong=1;var st0=qLocalISO(new Date(Date.now()-(RNG+1)*864e5));
      var cv=q$("trendy-canvas");if(cv&&cv.parentNode)cv.parentNode.style.opacity=".5";
      qJSON("/api/forma/data?start="+st0).then(function(F){if(F&&F.series&&F.series.length>have)forma.series=F.series;
        if(cv&&cv.parentNode)cv.parentNode.style.opacity="";renderTrendy();}).catch(function(){if(cv&&cv.parentNode)cv.parentNode.style.opacity="";renderTrendy();});}
    else renderTrendy();});});
  /* grupa: Moc/Obc/Well/Cialo */
  var grp=q$("grp");if(grp)grp.querySelectorAll("button").forEach(function(b){b.addEventListener("click",function(){
    grp.querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");
    GRP=b.dataset.g||"moc";renderTrendy();});});
}
load().catch(function(e){console.error("forma2:",e);});
})();
