/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* garaz-fit.js — zakladka BIKE FIT: geometria ramy (katalog), ustawienia (korekty) z historia,
   wymiary ciala, rysunek roweru i sylwetki liczony na zywo z danych. Wlasny modul (IIFE),
   garaz-tabs.js woła window.QFit.render(body, BIKE, reload). */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };
async function postJSON(u,b){ const r=await fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}); if(!r.ok) throw new Error(r.status); return r.json(); }
const R=Math.PI/180;
const S={bikeId:null, fitId:null, cmpId:"", crank:null, rider:true, aero:true};
let D=null, RELOAD=null, BODY=null;

/* ---------------- pola formularzy ---------------- */
const GEO_F=[["size","Rozmiar","t"],["stack_mm","Stack","n","mm"],["reach_mm","Reach","n","mm"],
 ["head_angle_deg","Kąt główki","n","°"],["seat_angle_deg","Kąt rury podsiodłowej","n","°"],["head_tube_mm","Długość główki","n","mm"],
 ["seat_tube_mm","Rura podsiodłowa","n","mm"],["top_tube_mm","Rura górna (efektywna)","n","mm"],["chainstay_mm","Tylne widełki","n","mm"],
 ["wheelbase_mm","Rozstaw osi","n","mm"],["bb_drop_mm","Obniżenie suportu","n","mm"],["fork_offset_mm","Offset widelca","n","mm"],
 ["standover_mm","Przekrok","n","mm"],["wheel_size","Koła","t"],["tire_mm","Opona","n","mm"],
 ["bar_type","Kierownica","s",null,[["drop","baranek"],["flat","prosta"]]],["source","Źródło (link)","t"],["notes","Notatki","a"]];
const FIT_F=[["variant","Nazwa ustawienia","t"],["date_set","Data","d"],["is_current","Aktualne","c"],
 ["stem_id","Mostek","p",null,"stem"],["bar_id","Kierownica","p",null,"handlebar"],["saddle_id","Siodło","p",null,"saddle"],
 ["seatpost_id","Sztyca","p",null,"seatpost"],["crank_id","Korba","p",null,"crankset"],["aero_id","Lemondka","p",null,"aero bars"],
 ["stem_flipped","Mostek odwrócony (kąt do góry)","c"],
 ["saddle_height_mm","Wysokość siodła","n","mm"],["saddle_setback_mm","Setback siodła","n","mm"],["saddle_tilt_deg","Kąt siodła","n","°"],
 ["spacer_mm","Podkładki pod mostkiem","n","mm"],["headset_cap_mm","Czapka sterów","n","mm"],
 ["stem_length_mm","Mostek – długość (gdy brak części)","n","mm"],["stem_angle_deg","Mostek – kąt (gdy brak części)","n","°"],
 ["handlebar_width_mm","Kierownica – szerokość (gdy brak części)","n","mm"],["bar_reach_mm","Kierownica – reach (gdy brak części)","n","mm"],
 ["bar_drop_mm","Kierownica – drop (gdy brak części)","n","mm"],["crank_length_mm","Korba (gdy brak części)","n","mm"],
 ["reach_mm","Reach zmierzony (fitter)","n","mm"],["stack_mm","Stack zmierzony (fitter)","n","mm"],["drop_mm","Drop zmierzony (fitter)","n","mm"],
 ["shoe_size","Rozmiar buta","t"],["cleat_left","Blok L","t"],["cleat_right","Blok P","t"],["fitter_name","Fitter","t"],["notes","Notatki","a"]];
const PART_ROLES=[["stem_id","stem"],["bar_id","handlebar"],["saddle_id","saddle"],["seatpost_id","seatpost"],["crank_id","crankset"],["aero_id","aero bars"]];
function partById(id){ return id==null||id==="" ? null : ((D&&D.components)||[]).find(c=>String(c.id)===String(id))||null; }
function partName(c){ return c ? [c.brand,c.model].filter(Boolean).join(" ")+(c.status&&c.status!=="zamontowany"?" ("+c.status+")":"") : "—"; }
function dimsOf(c){ if(!c||!c.dims) return {}; try{ return JSON.parse(c.dims)||{}; }catch(e){ return {}; } }
function mountedParts(bikeId){ const o={}; PART_ROLES.forEach(([k,cat])=>{ const c=((D&&D.components)||[]).find(x=>x.bike_id===bikeId&&x.category===cat&&x.status==="zamontowany"); if(c) o[k]=c.id; }); return o; }
const BODY_F=[["measured_on","Data pomiaru","d"],["height_mm","Wzrost","n","mm"],["inseam_mm","Długość nogi (krok)","n","mm"],
 ["sit_bone_mm","Rozstaw kości kulszowych","n","mm"],["shoulder_mm","Szerokość barków","n","mm"],["arm_mm","Zasięg ramienia","n","mm"],
 ["torso_mm","Tułów (biodro–bark)","n","mm"],["upper_arm_mm","Ramię","n","mm"],["forearm_mm","Przedramię z dłonią","n","mm"],
 ["thigh_mm","Udo (biodro–kolano)","n","mm"],["shank_mm","Podudzie (kolano–kostka)","n","mm"],["foot_mm","Długość stopy","n","mm"],["notes","Notatki","a"]];
const BODY_HELP={inseam_mm:"boso, od podłogi do krocza",sit_bone_mm:"odcisk na tekturze",arm_mm:"od barku do zaciśniętej pięści",
 torso_mm:"od stawu biodrowego do barku",thigh_mm:"krętarz – środek kolana",shank_mm:"środek kolana – kostka"};

/* ---------------- model geometrii ---------------- */
const num=(v,d)=>{ const x=parseFloat(v); return isFinite(x)?x:d; };
function model(geo, fit, body, crankDeg){
  const as=[];
  const need=(v,d,msg)=>{ const x=parseFloat(v); if(isFinite(x)) return x; if(msg) as.push(msg); return d; };
  const F={stack:need(geo.stack_mm,560,"stack ramy"),reach:need(geo.reach_mm,390,"reach ramy"),
    ha:need(geo.head_angle_deg,71,"kąt główki"),sa:need(geo.seat_angle_deg,73.5,"kąt podsiodłowej"),
    ht:num(geo.head_tube_mm,120),stl:num(geo.seat_tube_mm,480),cs:num(geo.chainstay_mm,435),
    wb:num(geo.wheelbase_mm,1040),drop:num(geo.bb_drop_mm,70),tire:num(geo.tire_mm,45)};
  F.rim=/650|27/.test(String(geo.wheel_size||""))?292:311;
  F.flat=(geo.bar_type==="flat");
  const pc=k=>partById(fit[k]), pd=k=>dimsOf(pc(k));
  const dS=pd("stem_id"), dB=pd("bar_id"), dK=pd("crank_id"), dSd=pd("saddle_id");
  const pick=(a,b,d,msg)=>{ const x=parseFloat(a); if(isFinite(x)) return x; return need(b,d,msg); };
  if(dB.bar_type) F.flat=(dB.bar_type==="flat");
  let sa=pick(dS.angle_deg,fit.stem_angle_deg,-6,"kąt mostka (przyjęto −6°)");
  const sc=pc("stem_id"); if(sc&&sc.notes&&/PRZYJ/i.test(sc.notes)&&isFinite(parseFloat(dS.angle_deg))) as.push("kąt mostka "+dS.angle_deg+"° przyjęty w danych części");
  if(fit.stem_flipped) sa=-sa;
  const u={sh:need(fit.saddle_height_mm,740,"wysokość siodła"),sb:need(fit.saddle_setback_mm,60,"setback"),
    sp:need(fit.spacer_mm,0,"podkładki (przyjęto 0)"),cap:num(fit.headset_cap_mm,10),
    st:pick(dS.length_mm,fit.stem_length_mm,90,"długość mostka"),sa,
    crank:pick(dK.crank_mm,fit.crank_length_mm,170),br:pick(dB.reach_mm,fit.bar_reach_mm,F.flat?0:80),
    bd:pick(dB.drop_mm,fit.bar_drop_mm,120),rise:num(dB.rise_mm,0),width:pick(dB.width_mm,fit.handlebar_width_mm,420),
    slen:num(dSd.length_mm,270)};
  u.sweep=0.25*u.width*Math.sin(num(dB.backsweep_deg,0)*R);
  const add=(a,b,k)=>[a[0]+b[0]*(k??1),a[1]+b[1]*(k??1)];
  const top=[F.reach,F.stack], d=[-Math.cos(F.ha*R),Math.sin(F.ha*R)];
  const stemBase=add(top,d,u.sp+u.cap+18), a=(90-F.ha+u.sa)*R;
  const cl=add(stemBase,[Math.cos(a),Math.sin(a)],u.st);
  const post=[-u.sh*Math.cos(F.sa*R),u.sh*Math.sin(F.sa*R)];
  const nose=[-u.sb,post[1]];
  const tops=[cl[0],cl[1]+u.rise];
  const hood=F.flat?[cl[0]+10-u.sweep,tops[1]+20]:[cl[0]+u.br+15-u.sweep,tops[1]+18];
  const ac=pc("aero_id"), dA=dimsOf(ac);
  let aero=null;
  if(ac){ const pad=[cl[0]+num(dA.pad_setback_mm,0),tops[1]+num(dA.pad_stack_mm,50)];
    aero={pad,angle:num(dA.pad_angle_deg,20)*R,elbow:[pad[0],pad[1]+35],ext:num(dA.extension_mm,350)};
    if(dA.pad_stack_mm==null) as.push("wysokość podłokietników (przyjęto 50 mm)"); }
  const H=num(body&&body.height_mm,1755), ins=num(body&&body.inseam_mm,0.47*H), ls=ins/(0.47*H);
  const Bd={thigh:num(body&&body.thigh_mm,0.245*H*ls),shank:num(body&&body.shank_mm,0.246*H*ls),
    torso:num(body&&body.torso_mm,0.295*H),up:num(body&&body.upper_arm_mm,0.186*H),fore:num(body&&body.forearm_mm,0.16*H)};
  return {F,u,top,stemBase,cl,tops,post,nose,hood,aero,useAero:true,Bd,as,crankDeg:(crankDeg==null?360-F.sa:crankDeg)};
}
function ik0(a,b,l1,l2,up){const dx=b[0]-a[0],dy=b[1]-a[1],dd=Math.min(Math.hypot(dx,dy),l1+l2-1);const t=Math.atan2(dy,dx),c=Math.acos(Math.max(-1,Math.min(1,(l1*l1+dd*dd-l2*l2)/(2*l1*dd))))*(up?1:-1);return [a[0]+l1*Math.cos(t+c),a[1]+l1*Math.sin(t+c)];}
function ik(a,b,l1,l2,mode){const s1=ik0(a,b,l1,l2,true),s2=ik0(a,b,l1,l2,false);if(mode==="fwd")return s1[0]>s2[0]?s1:s2;if(mode==="down")return s1[1]<s2[1]?s1:s2;return s1;}
function ang(p,q,r){const a=Math.atan2(p[1]-q[1],p[0]-q[0]),b=Math.atan2(r[1]-q[1],r[0]-q[0]);let x=Math.abs(a-b)/R;return x>180?360-x:x;}
function footPose(ped,cang){const dr=(15+12*Math.sin(cang))*R, ball=[ped[0],ped[1]+18];
  return {ball,ank:[ball[0]-130*Math.cos(dr),ball[1]+130*Math.sin(dr)+45],toe:[ball[0]+55*Math.cos(dr),ball[1]-55*Math.sin(dr)],heel:[ball[0]-175*Math.cos(dr),ball[1]+175*Math.sin(dr)-5]};}
function rider(m, crankDeg){
  const c=crankDeg*R, ped=[m.u.crank*Math.cos(c),m.u.crank*Math.sin(c)], pb=[-ped[0],-ped[1]];
  const fp=footPose(ped,c), fp2=footPose(pb,c+Math.PI);
  const sit=[m.nose[0]-175,m.post[1]], hip=[sit[0]+30,sit[1]+15];
  const knee=ik(hip,fp.ank,m.Bd.thigh,m.Bd.shank,"fwd"), knee2=ik(hip,fp2.ank,m.Bd.thigh,m.Bd.shank,"fwd");
  const ua=m.Bd.up, fa=m.Bd.fore, Ae=Math.sqrt(ua*ua+fa*fa-2*ua*fa*Math.cos(155*R));
  let sh, elb, hand;
  if(m.aero&&m.useAero){ elb=m.aero.elbow; hand=[elb[0]+fa*Math.cos(m.aero.angle),elb[1]+fa*Math.sin(m.aero.angle)]; sh=ik(hip,elb,m.Bd.torso,ua,"up"); }
  else { hand=m.hood; sh=ik(hip,m.hood,m.Bd.torso,Ae,"up"); elb=ik(sh,m.hood,ua,fa,"down"); }
  const bt=Math.atan2(sh[1]-hip[1],sh[0]-hip[0]);
  return {ped,pb,fp,fp2,hip,knee,knee2,sh,elb,hand,bt,head:[sh[0]+125*Math.cos(bt+0.45),sh[1]+125*Math.sin(bt+0.45)]};
}
const TIPS={
 "Stack zacisku":"Pionowa odległość od osi suportu do środka zacisku kierownicy w mostku. Zmieniają ją podkładki, długość i kąt mostka. Wyżej = pozycja bardziej wyprostowana.",
 "Reach zacisku":"Pozioma odległość od osi suportu do zacisku kierownicy. Zmienia ją głównie długość mostka; każde 10 mm podkładek cofa kierownicę o ok. 3 mm.",
 "Stack chwytów":"Wysokość klamkomanetek nad osią suportu – tam realnie opierasz dłonie. Uwzględnia wznios i kształt kierownicy.",
 "Reach chwytów":"Jak daleko przed suportem są klamkomanetki. Za dużo → wyciągnięte ramiona i obciążony kark; za mało → ciasno, kolana blisko łokci.",
 "Drop siodło–góra kier.":"O ile siodło jest wyżej od góry kierownicy. Gravel i turystyka zwykle 0–60 mm. Więcej = sportowo, większe obciążenie dłoni, karku i lędźwi.",
 "Siodło–chwyty":"Odległość od czubka siodła do klamkomanetek – ogólna miara rozciągnięcia pozycji. Najlepiej porównywać między ustawieniami.",
 "Kolano (dół)":"Kąt w kolanie przy korbie w dole (180° = noga prosta). Typowo 140–150°. Mniej → siodło za nisko (przeciążenie przodu kolana). Więcej → siodło za wysoko (kołysanie biodrami, ból z tyłu kolana).",
 "Biodro (góra korby)":"Najmniejszy kąt między tułowiem a udem – przy korbie u góry. Typowo 45–60°. Za mały → ściśnięte biodro, trudniej oddychać i generować moc; pomaga wyższa lub bliższa kierownica.",
 "Plecy":"Nachylenie tułowia (biodro–bark) do poziomu. Gravel na klamkomanetkach typowo 30–45°, na lemondce 20–35°. Mniej = bardziej aero, ale większe obciążenie karku i lędźwi.",
 "Bark":"Kąt między tułowiem a ramieniem. Typowo 80–95° (lemondka 80–100°). Więcej → ramiona wyciągnięte (za długi reach); mniej → ramiona pod sobą, ciasno."};
const escA=t=>String(t).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;");
function judge(v,lo,hi,lowMsg,highMsg){
  if(v<lo) return {cls:"warn",d:`${Math.round(lo-v)}° poniżej ${lo}–${hi}° – ${lowMsg}`};
  if(v>hi) return {cls:"warn",d:`${Math.round(v-hi)}° powyżej ${lo}–${hi}° – ${highMsg}`};
  return {cls:"ok",d:`w zakresie ${lo}–${hi}°`};
}
function angles(m){
  const r=rider(m,360-m.F.sa), t=rider(m,180-m.F.sa);
  return {knee:ang(r.hip,r.knee,r.fp.ank),hip:ang(r.sh,r.hip,r.knee),hipTop:ang(t.sh,t.hip,t.knee),back:r.bt/R,shoulder:ang(r.hip,r.sh,r.elb)};
}

/* ---------------- SVG ---------------- */
const X=p=>p[0].toFixed(1), Y=p=>(-p[1]).toFixed(1), PT=p=>X(p)+","+Y(p);
const LN=(a,b,st,w,dash)=>`<line x1="${X(a)}" y1="${Y(a)}" x2="${X(b)}" y2="${Y(b)}" stroke="${st}" stroke-width="${w}" stroke-linecap="round"${dash?' stroke-dasharray="14 10"':''}/>`;
function CAP(a,b,w,col,op){const dx=b[0]-a[0],dy=b[1]-a[1],l=Math.hypot(dx,dy)||1,nx=-dy/l*w/2,ny=dx/l*w/2,r=w/2;
  const p1=[a[0]+nx,a[1]+ny],p2=[b[0]+nx,b[1]+ny],p3=[b[0]-nx,b[1]-ny],p4=[a[0]-nx,a[1]-ny];
  return `<path d="M${PT(p1)} L${PT(p2)} A${r},${r} 0 0 1 ${PT(p3)} L${PT(p4)} A${r},${r} 0 0 1 ${PT(p1)} Z" fill="${col}" opacity="${op??1}"/>`;}
function barSvg(m,col,w,dash){
  const c=m.cl, ds=dash?' stroke-dasharray="14 10"':'';
  const t=m.tops, sw=m.u.sweep||0, rs=m.u.rise||0;
  const riser=rs>0?`<line x1="${X(c)}" y1="${Y(c)}" x2="${X(t)}" y2="${Y(t)}" stroke="${col}" stroke-width="${w}" stroke-linecap="round"${ds}/>`:"";
  if(m.F.flat){ const e=[t[0]+25-sw,t[1]+12]; return riser+`<line x1="${X(t)}" y1="${Y(t)}" x2="${X(e)}" y2="${Y(e)}" stroke="${col}" stroke-width="${w*1.4}" stroke-linecap="round"${ds}/>`; }
  const br=m.u.br, bd=m.u.bd||120, f=[t[0]+br-sw,t[1]], dr=[f[0]-25,t[1]-bd], end=[f[0]-75,t[1]-bd-8];
  const lower=rs>0?`<line x1="${X(c)}" y1="${Y(c)}" x2="${(c[0]+br*0.7).toFixed(1)}" y2="${Y(c)}" stroke="${col}" stroke-width="${w*0.7}" stroke-linecap="round"${ds}/>`:"";
  return riser+lower+`<path d="M${PT(t)} L${PT(f)} C${(f[0]+45).toFixed(1)},${Y(f)} ${(f[0]+45).toFixed(1)},${(-(f[1]-bd+20)).toFixed(1)} ${PT(dr)} L${PT(end)}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round"${ds}/>`+
    `<path d="M${(f[0]-8).toFixed(1)},${Y(f)} L${(f[0]+12).toFixed(1)},${(-(f[1]+32)).toFixed(1)} L${(f[0]+34).toFixed(1)},${(-(f[1]+26)).toFixed(1)} L${(f[0]+40).toFixed(1)},${(-(f[1]-70)).toFixed(1)}" fill="none" stroke="${col}" stroke-width="${w*0.9}" stroke-linejoin="round" stroke-linecap="round"${ds}/>`;
}
function saddleSvg(m,col,dash){
  const n=m.nose[0], y=m.post[1], b=n-(m.u.slen||270);
  return `<path d="M${n},${-y+4} Q${n+8},${-y-6} ${n-40},${-y-12} L${b+70},${-y-22} Q${b+10},${-y-30} ${b},${-y-14} Q${b+20},${-y+6} ${b+80},${-y+8} Z" fill="${dash?'none':col}" stroke="${col}" stroke-width="${dash?8:4}" stroke-linejoin="round"${dash?' stroke-dasharray="14 10"':''}/>`;
}
function dim(a,b,lab,off,vert){
  const o=vert?[off,0]:[0,off], a2=[a[0]+o[0],a[1]+o[1]], b2=[b[0]+o[0],b[1]+o[1]], mm=[(a2[0]+b2[0])/2,(a2[1]+b2[1])/2];
  return `<line x1="${X(a2)}" y1="${Y(a2)}" x2="${X(b2)}" y2="${Y(b2)}" stroke="var(--muted)" stroke-width="3" marker-start="url(#qfar)" marker-end="url(#qfar)"/>`+
    `<text x="${(mm[0]+(vert?14:0)).toFixed(1)}" y="${(-mm[1]-(vert?0:14)).toFixed(1)}" text-anchor="${vert?'start':'middle'}" fill="var(--ink2)" style="font-size:38px">${lab}</text>`;
}
function bikeSvg(m, cmp, showRider, crankDeg){
  const F=m.F, csh=Math.sqrt(Math.max(1,F.cs*F.cs-F.drop*F.drop)), ra=[-csh,F.drop], fa=[F.wb-csh,F.drop];
  const gy=F.drop-F.rim-F.tire, hd=[Math.cos(F.ha*R),-Math.sin(F.ha*R)];
  const add=(a,b,k)=>[a[0]+b[0]*(k??1),a[1]+b[1]*(k??1)];
  const htb=add(m.top,hd,F.ht), crown=add(htb,hd,25);
  const sdir=[-Math.cos(F.sa*R),Math.sin(F.sa*R)], stt=add([0,0],sdir,F.stl), ttj=add([0,0],sdir,F.stl-25), ssj=add([0,0],sdir,F.stl-120);
  const fr="#378ADD", rc="#1D9E75", wc="var(--ink2)";
  const r=rider(m,crankDeg);
  const wheel=c=>{let h=`<circle cx="${X(c)}" cy="${Y(c)}" r="${F.rim+F.tire/2}" fill="none" stroke="${wc}" stroke-width="${F.tire}" opacity="0.85"/><circle cx="${X(c)}" cy="${Y(c)}" r="${F.rim-6}" fill="none" stroke="${wc}" stroke-width="18" opacity="0.6"/>`;
    for(let i=0;i<24;i++){const t=i*15*R;h+=`<line x1="${X(c)}" y1="${Y(c)}" x2="${(c[0]+(F.rim-16)*Math.cos(t)).toFixed(1)}" y2="${(-c[1]-(F.rim-16)*Math.sin(t)).toFixed(1)}" stroke="var(--line)" stroke-width="2"/>`;}
    return h+`<circle cx="${X(c)}" cy="${Y(c)}" r="22" fill="${wc}"/>`;};
  const legSvg=(knee,fp,op)=>CAP(r.hip,knee,46,rc,op)+CAP(knee,fp.ank,36,rc,op)+`<polygon points="${[fp.heel,fp.ank,fp.toe,fp.ball].map(PT).join(" ")}" fill="${rc}" opacity="${op}"/>`;
  let h=`<defs><marker id="qfar" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker></defs>`;
  h+=`<line x1="-900" y1="${(-gy).toFixed(1)}" x2="1100" y2="${(-gy).toFixed(1)}" stroke="var(--line)" stroke-width="3"/>`;
  if(showRider) h+=legSvg(r.knee2,r.fp2,0.35);
  h+=wheel(ra)+wheel(fa);
  const fm=[(crown[0]+fa[0])/2+22,(crown[1]+fa[1])/2];
  h+=`<path d="M${PT(crown)} Q${PT(fm)} ${PT(fa)}" fill="none" stroke="${fr}" stroke-width="20" stroke-linecap="round"/>`;
  h+=LN(ra,[-25,-5],fr,16)+LN(ra,ssj,fr,13)+LN([0,0],stt,fr,24)+LN(ttj,add(m.top,hd,18),fr,22)+LN([0,0],add(htb,hd,-15),fr,34)+LN(m.top,htb,fr,36);
  h+=LN(stt,add(m.post,sdir,-12),wc,16)+saddleSvg(m,wc);
  h+=`<circle cx="0" cy="0" r="90" fill="none" stroke="${wc}" stroke-width="10"/><circle cx="0" cy="0" r="26" fill="${wc}"/>`;
  h+=LN(m.top,m.stemBase,"var(--accent)",26)+LN(m.stemBase,m.cl,"var(--accent)",20)+barSvg(m,wc,16);
  if(cmp){ h+=LN(cmp.stemBase,cmp.cl,"var(--muted)",10,1)+barSvg(cmp,"var(--muted)",8,1)+saddleSvg(cmp,"var(--muted)",1); }
  if(m.aero){ const a=m.aero, p=a.pad, st=[p[0]-30,p[1]-12], L=Math.min(a.ext*0.75,380), tip=[st[0]+L*Math.cos(a.angle),st[1]+L*Math.sin(a.angle)];
    h+=LN([p[0],p[1]-15],[m.cl[0],m.tops[1]],wc,12)+LN(st,tip,wc,14)+LN([p[0]-55,p[1]],[p[0]+45,p[1]+Math.tan(a.angle)*45],wc,24); }
  h+=LN(r.pb,r.ped,wc,14)+LN([r.ped[0]-45,r.ped[1]],[r.ped[0]+45,r.ped[1]],wc,14)+LN([r.pb[0]-45,r.pb[1]],[r.pb[0]+45,r.pb[1]],wc,10);
  if(showRider){
    const w1=[r.hip[0]+560*Math.cos(30*R),r.hip[1]+560*Math.sin(30*R)], w2=[r.hip[0]+560*Math.cos(45*R),r.hip[1]+560*Math.sin(45*R)];
    h+=`<path d="M${PT(r.hip)} L${PT(w1)} A560,560 0 0 0 ${PT(w2)} Z" fill="#9FE1CB" opacity="0.3"/>`+
      `<line x1="${X(r.hip)}" y1="${Y(r.hip)}" x2="${(r.hip[0]+600).toFixed(1)}" y2="${Y(r.hip)}" stroke="var(--muted)" stroke-width="3" stroke-dasharray="12 10"/>`+
      `<text x="${(w2[0]+10).toFixed(1)}" y="${Y(w2)}" fill="var(--ink2)" style="font-size:34px">45°</text><text x="${(w1[0]+10).toFixed(1)}" y="${Y(w1)}" fill="var(--ink2)" style="font-size:34px">30°</text>`;
    h+=legSvg(r.knee,r.fp,1)+CAP(r.hip,r.sh,62,rc)+CAP(r.sh,r.elb,38,rc)+CAP(r.elb,r.hand,32,rc)+
      `<circle cx="${X(r.hand)}" cy="${Y(r.hand)}" r="30" fill="${rc}"/><circle cx="${X(r.head)}" cy="${Y(r.head)}" r="92" fill="none" stroke="${rc}" stroke-width="18"/>`+
      [r.hip,r.sh,r.elb,r.knee].map(p=>`<circle cx="${X(p)}" cy="${Y(p)}" r="15" fill="var(--card)" stroke="${rc}" stroke-width="6"/>`).join("");
  }
  h+=dim([F.reach+230,0],[F.reach+230,m.cl[1]],"stack zacisku "+Math.round(m.cl[1]),130,true);
  h+=dim([0,gy-50],[m.cl[0],gy-50],"reach zacisku "+Math.round(m.cl[0]),0,false);
  h+=dim([m.nose[0]-270,m.tops[1]],[m.nose[0]-270,m.post[1]],"drop "+Math.round(m.post[1]-m.tops[1]),-120,true);
  return `<svg viewBox="-900 -1400 2000 1760" style="width:100%;height:auto;display:block" role="img" aria-label="Rysunek roweru i sylwetki">${h}</svg>`;
}
function bodySvg(b){
  const H=num(b.height_mm,1755), ins=num(b.inseam_mm,0.47*H), rc="#1D9E75";
  const foot=[0,0], hipY=ins+60, sh=[0,H*0.818], head=[0,H*0.93];
  let h=`<defs><marker id="qfar2" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker></defs>`;
  h+=CAP([-70,hipY],[-60,40],70,rc,0.9)+CAP([70,hipY],[60,40],70,rc,0.9)+CAP([0,hipY],sh,210,rc,0.9)+
     CAP([-150,sh[1]-20],[-190,sh[1]-560],56,rc,0.75)+CAP([150,sh[1]-20],[190,sh[1]-560],56,rc,0.75)+
     `<circle cx="0" cy="${(-head[1]).toFixed(1)}" r="${(H*0.065).toFixed(1)}" fill="none" stroke="${rc}" stroke-width="20"/>`;
  const dv=(x,y1,y2,lab,left)=>`<line x1="${x}" y1="${-y1}" x2="${x}" y2="${-y2}" stroke="var(--muted)" stroke-width="4" marker-start="url(#qfar2)" marker-end="url(#qfar2)"/><text x="${x+(left?-16:16)}" y="${(-(y1+y2)/2).toFixed(1)}" text-anchor="${left?'end':'start'}" fill="var(--ink2)" style="font-size:52px">${lab}</text>`;
  h+=dv(-330,0,H,"wzrost "+Math.round(H),true)+dv(300,0,ins,"noga "+Math.round(ins),false);
  if(b.shoulder_mm) h+=`<line x1="-200" y1="${-sh[1]-70}" x2="200" y2="${-sh[1]-70}" stroke="var(--muted)" stroke-width="4" marker-start="url(#qfar2)" marker-end="url(#qfar2)"/><text x="0" y="${-sh[1]-95}" text-anchor="middle" fill="var(--ink2)" style="font-size:52px">barki ${Math.round(b.shoulder_mm)}</text>`;
  if(b.arm_mm) h+=`<text x="230" y="${(-(sh[1]-300)).toFixed(1)}" fill="var(--ink2)" style="font-size:52px">ramię ${Math.round(b.arm_mm)}</text>`;
  if(b.sit_bone_mm) h+=`<text x="0" y="${(-(hipY-140)).toFixed(1)}" text-anchor="middle" fill="var(--card)" style="font-size:44px">kulsz. ${Math.round(b.sit_bone_mm)}</text>`;
  return `<svg viewBox="-760 ${(-H-140).toFixed(0)} 1520 ${(H+220).toFixed(0)}" style="width:100%;max-width:260px;height:auto;display:block;margin:0 auto" role="img" aria-label="Wymiary ciała">${h}</svg>`;
}

/* ---------------- modal edycji ---------------- */
function ensureModal(){
  if($("#qfModal")) return;
  const m=el("div","modal"); m.id="qfModal";
  m.innerHTML='<div class="modal-head"><div class="t" id="qfTitle"></div><button type="button" class="modal-x" id="qfX" aria-label="zamknij">&times;</button></div>'+
    '<div class="mbody" style="display:block"><div class="mgrid" id="qfGrid" style="grid-template-columns:repeat(3,minmax(0,1fr))"></div></div>'+
    '<div class="mfoot"><div class="msg" id="qfMsg"></div><button type="button" class="btn danger" id="qfDel" style="display:none">Usuń</button><button type="button" class="btn sec" id="qfCancel">Anuluj</button><button type="button" class="btn" id="qfSave">Zapisz</button></div>';
  document.body.appendChild(m);
  const close=()=>{ m.classList.remove("open"); document.body.classList.remove("modal-open"); };
  $("#qfX").addEventListener("click",close); $("#qfCancel").addEventListener("click",close);
  m._close=close;
}
function openForm(title, fields, data, onSave, onDelete, help, photo){
  ensureModal();
  const m=$("#qfModal"), g=$("#qfGrid"); g.innerHTML=""; $("#qfTitle").textContent=title; $("#qfMsg").textContent="";
  if(photo&&photo.id){
    const pf=el("div","mf full qf-phbox"); pf.appendChild(el("label",null,"Zdjęcie"));
    const row=el("div","qf-phrow"); const img=el("img","qf-phprev"); img.alt="";
    if(photo.photo){ img.src=photo.photo; img.addEventListener("click",()=>window.open(photo.photo,"_blank")); } else img.style.display="none";
    const ctl=el("div","qf-phctl");
    const lab=el("label","btn sec","Dodaj / zmień zdjęcie"); const fi=el("input"); fi.type="file"; fi.accept="image/*"; fi.hidden=true; lab.appendChild(fi);
    const del=el("button","btn sec","Usuń zdjęcie"); del.type="button"; if(!photo.photo) del.style.display="none";
    const st=el("span","qf-phst");
    fi.addEventListener("change",async()=>{ const f=fi.files[0]; if(!f) return; const fd=new FormData(); fd.append("id",photo.id); fd.append("entity",photo.entity); fd.append("file",f);
      st.textContent="wysyłanie…"; try{ const r=await fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd}); if(!r.ok) throw new Error(r.status);
        const d=await r.json(); img.src=d.photo; img.style.display=""; del.style.display=""; photo.photo=d.photo; st.textContent="dodano"; RELOAD&&RELOAD(); }catch(e){ st.textContent="błąd ("+e.message+")"; } });
    del.addEventListener("click",async()=>{ try{ await postJSON("/api/garage/photo/delete",{id:Number(photo.id),entity:photo.entity}); img.style.display="none"; del.style.display="none"; st.textContent="usunięto"; RELOAD&&RELOAD(); }catch(e){ st.textContent="błąd usuwania"; } });
    ctl.appendChild(lab); ctl.appendChild(del); ctl.appendChild(st); row.appendChild(img); row.appendChild(ctl); pf.appendChild(row); g.appendChild(pf);
  }
  fields.forEach(([k,lab,t,u,opts])=>{
    const f=el("div","mf"+(t==="a"?" full":"")); const l=el("label",null,lab+(u?" ["+u+"]":"")); f.appendChild(l);
    let inp;
    if(t==="a"){ inp=el("textarea"); }
    else if(t==="s"){ inp=el("select"); (opts||[]).forEach(([v,n])=>{ const o=el("option",null,n); o.value=v; inp.appendChild(o); }); }
    else if(t==="c"){ inp=el("input"); inp.type="checkbox"; inp.style.cssText="width:auto;height:auto"; }
    else if(t==="p"){ inp=el("select"); const o0=el("option",null,"— brak —"); o0.value=""; inp.appendChild(o0);
      ((D&&D.components)||[]).filter(c=>c.bike_id===S.bikeId&&c.category===opts).forEach(c=>{ const o=el("option",null,partName(c)); o.value=String(c.id); inp.appendChild(o); }); }
    else { inp=el("input"); inp.type=(t==="n"?"number":(t==="d"?"date":"text")); if(t==="n") inp.step="any"; }
    inp.dataset.k=k; inp.dataset.t=t;
    const v=data?data[k]:null;
    if(t==="c") inp.checked=!!v; else inp.value=(v==null?"":String(v));
    if(help&&help[k]) inp.placeholder=help[k];
    f.appendChild(inp); g.appendChild(f);
  });
  const del=$("#qfDel"); del.style.display=onDelete?"":"none"; del.textContent="Usuń"; del.dataset.armed="";
  del.onclick=async()=>{ if(del.dataset.armed!=="1"){ del.dataset.armed="1"; del.textContent="Potwierdź usunięcie"; return; }
    try{ await onDelete(); m._close(); RELOAD&&RELOAD(); }catch(e){ $("#qfMsg").textContent="Błąd usuwania ("+e.message+")"; } };
  $("#qfSave").onclick=async()=>{
    const out={}; g.querySelectorAll("[data-k]").forEach(i=>{ out[i.dataset.k]= i.dataset.t==="c" ? (i.checked?1:0) : i.value; });
    $("#qfMsg").textContent="zapisuję…";
    try{ await onSave(out); m._close(); RELOAD&&RELOAD(); }catch(e){ $("#qfMsg").textContent="Błąd zapisu ("+e.message+")"; }
  };
  document.body.classList.add("modal-open"); m.classList.add("open");
}

/* ---------------- widok ---------------- */
function bikeName(b){ return b ? (b.nickname||b.model||b.name||("rower "+b.id)) : "—"; }
function fmt(v,u){ return (v==null||v==="") ? "—" : (Math.round(parseFloat(v)*10)/10)+(u?" "+u:""); }
function card(title, actions){
  const c=el("div","qf-card"), h=el("div","qf-head"); h.appendChild(el("h4",null,title));
  const a=el("div","qf-act"); (actions||[]).forEach(([t,fn,cls])=>{ const b=el("button","btn "+(cls||"sec"),t); b.type="button"; b.addEventListener("click",fn); a.appendChild(b); });
  h.appendChild(a); c.appendChild(h); return c;
}
function rows(c, fields, data, skip){
  fields.forEach(([k,lab,t,u,opts])=>{
    if(t==="a"||(skip&&skip.includes(k))) return;
    let v=data?data[k]:null; if(v==null||v==="") return;
    if(t==="s"&&opts){ const o=opts.find(x=>x[0]===v); if(o) v=o[1]; }
    if(t==="c") v=v?"tak":"nie";
    if(t==="p") v=partName(partById(v));
    const r=el("div","qf-row"); r.appendChild(el("span",null,lab)); r.appendChild(el("b",null,t==="n"?fmt(v,u):String(v))); c.appendChild(r);
  });
}
function render(body){
  BODY=body; body.innerHTML="";
  const bikes=D.bikes||[];
  if(!bikes.length){ body.appendChild(el("div","empty","Brak rowerów.")); return; }
  if(!bikes.find(b=>b.id===S.bikeId)) S.bikeId=(bikes.find(b=>b.active)||bikes[0]).id;
  const bike=bikes.find(b=>b.id===S.bikeId);
  // kafelki rowerow
  const grid=el("div","bikecards");
  bikes.forEach(b=>{
    const c=el("div","bikecard"+(b.id===S.bikeId?" sel":"")+(b.active?"":" inact"));
    const im=el("div","bkimg"); if(b.photo){ const i=el("img"); i.src=b.photo; i.alt=""; im.appendChild(i); } else im.appendChild(el("div","bkph","🚲"));
    c.appendChild(im); const t=el("div","bktxt"); t.appendChild(el("h3",null,bikeName(b)));
    const nf=(D.fitting||[]).filter(f=>f.bike_id===b.id).length; t.appendChild(el("div","meta",nf+" ustawień"));
    c.appendChild(t); c.addEventListener("click",()=>{ S.bikeId=b.id; S.fitId=null; S.cmpId=""; render(BODY); }); grid.appendChild(c);
  });
  body.appendChild(grid);

  const geo=(D.geometry||[]).find(g=>g.bike_id===bike.id)||{bike_id:bike.id};
  const fits=(D.fitting||[]).filter(f=>f.bike_id===bike.id).sort((a,b)=>(b.is_current||0)-(a.is_current||0)||String(b.date_set||"").localeCompare(String(a.date_set||""))||b.id-a.id);
  const bodyM=(D.body||[])[0]||null;
  if(!fits.find(f=>f.id===S.fitId)) S.fitId=fits.length?fits[0].id:null;
  const fit=fits.find(f=>f.id===S.fitId)||{};
  const hasGeo=geo.stack_mm!=null&&geo.reach_mm!=null&&geo.head_angle_deg!=null&&geo.seat_angle_deg!=null;

  // rysunek
  const draw=card("Rysunek — "+bikeName(bike));
  if(!hasGeo || !fits.length){
    draw.appendChild(el("div","note", !hasGeo ? "Uzupełnij geometrię ramy (stack, reach, kąty), żeby narysować rower." : "Dodaj pierwsze ustawienie roweru."));
  } else {
    const bar=el("div","qf-ctl");
    const sel=el("select"); fits.forEach(f=>{ const o=el("option",null,(f.variant||("ustawienie #"+f.id))+(f.date_set?" · "+f.date_set:"")+(f.is_current?" · aktualne":"")); o.value=f.id; sel.appendChild(o); });
    sel.value=String(S.fitId); sel.addEventListener("change",()=>{ S.fitId=+sel.value; render(BODY); });
    const cmp=el("select"); const o0=el("option",null,"porównaj: —"); o0.value=""; cmp.appendChild(o0);
    fits.filter(f=>f.id!==S.fitId).forEach(f=>{ const o=el("option",null,"porównaj: "+(f.variant||("#"+f.id))+(f.date_set?" · "+f.date_set:"")); o.value=f.id; cmp.appendChild(o); });
    cmp.value=S.cmpId; cmp.addEventListener("change",()=>{ S.cmpId=cmp.value; render(BODY); });
    const cr=el("input"); cr.type="range"; cr.min="0"; cr.max="345"; cr.step="15";
    const mm=model(geo,fit,bodyM); const bdc=360-mm.F.sa; cr.value=String(S.crank==null?Math.round(bdc/15)*15:S.crank);
    const crl=el("label",null,"korba"); crl.appendChild(cr);
    const rl=el("label"); const rcb=el("input"); rcb.type="checkbox"; rcb.checked=S.rider; rl.appendChild(rcb); rl.appendChild(document.createTextNode(" sylwetka"));
    bar.appendChild(sel); bar.appendChild(cmp); bar.appendChild(crl); bar.appendChild(rl); draw.appendChild(bar);
    if(mm.aero){ const al=el("label"); const acb=el("input"); acb.type="checkbox"; acb.checked=S.aero; al.appendChild(acb); al.appendChild(document.createTextNode(" pozycja aero")); bar.insertBefore(al,rl);
      acb.addEventListener("change",()=>{ S.aero=acb.checked; paint(); }); }
    const wrap=el("div","qf-draw"); draw.appendChild(wrap);
    const box=el("div","qf-svg"); wrap.appendChild(box);
    const mc=el("div","qf-mc"); wrap.appendChild(mc);
    if(fit.photo){ const ph=el("img","qf-photo"); ph.src=fit.photo; ph.alt="zdjęcie ustawienia"; ph.title="kliknij, aby powiększyć"; ph.addEventListener("click",()=>window.open(fit.photo,"_blank")); wrap.appendChild(ph); }
    const asn=el("div","note"); draw.appendChild(asn);
    const paint=()=>{
      const m=model(geo,fit,bodyM), cf=fits.find(f=>String(f.id)===S.cmpId), cm=cf?model(geo,cf,bodyM):null;
      m.useAero=S.aero; if(cm) cm.useAero=S.aero;
      box.innerHTML=bikeSvg(m,cm,S.rider,S.crank==null?bdc:S.crank);
      const A=angles(m), dv=(a,b)=>{ if(!cm) return ""; const x=Math.round(a-b); return x===0?"bez zmian":(x>0?"+":"")+x+" mm vs porówn."; };
      const meas=(v,l)=> v!=null&&v!=="" ? l+" (fitter): "+Math.round(v) : "";
      const rg=(x,a,b)=>x>=a&&x<=b?"ok":"warn";
      const K=(l,v,d,cls)=>`<div class="m" tabindex="0"${TIPS[l]?` data-tip="${escA(TIPS[l]+(cls==="warn"?" Uwaga: model ma dokładność ±kilka stopni.":""))}"`:""}><div class="l">${l}${TIPS[l]?" <span class=\"qf-i\">ⓘ</span>":""}</div><div class="v">${v}</div><div class="d ${cls||""}">${d||"&nbsp;"}</div></div>`;
      const drop=m.post[1]-m.cl[1], sb=Math.hypot(m.cl[0]-m.nose[0],m.cl[1]-m.post[1]);
      const gdrop=m.post[1]-m.tops[1], gsb=Math.hypot(m.hood[0]-m.nose[0],m.hood[1]-m.post[1]);
      mc.innerHTML=K("Stack zacisku",Math.round(m.cl[1])+" mm",cm?dv(m.cl[1],cm.cl[1]):"w mostku")+
        K("Reach zacisku",Math.round(m.cl[0])+" mm",cm?dv(m.cl[0],cm.cl[0]):"w mostku")+
        K("Stack chwytów",Math.round(m.hood[1])+" mm",cm?dv(m.hood[1],cm.hood[1]):"klamkomanetki")+
        K("Reach chwytów",Math.round(m.hood[0])+" mm",cm?dv(m.hood[0],cm.hood[0]):"klamkomanetki")+
        K("Drop siodło–góra kier.",Math.round(gdrop)+" mm",cm?dv(gdrop,cm.post[1]-cm.tops[1]):"")+
        K("Siodło–chwyty",Math.round(gsb)+" mm",cm?dv(gsb,Math.hypot(cm.hood[0]-cm.nose[0],cm.hood[1]-cm.post[1])):"czubek siodła – klamkomanetki")+
        (()=>{ const ae=!!(m.aero&&m.useAero);
          const jk=judge(A.knee,140,150,"siodło raczej za nisko","siodło raczej za wysoko");
          const jh=judge(A.hipTop,45,60,"biodro ściśnięte – rozważ wyższą lub bliższą kierownicę","pozycja bardzo wyprostowana");
          const jb=ae?judge(A.back,20,35,"bardzo nisko – obciążony kark","wysoko jak na lemondkę"):judge(A.back,30,45,"mocno pochylona pozycja","wyprostowana pozycja");
          const js=ae?judge(A.shoulder,80,100,"łokcie pod barkami – ciasno","ramiona wyciągnięte"):judge(A.shoulder,80,95,"kierownica blisko – ciasno","ramiona wyciągnięte, reach za długi");
          return K("Kolano (dół)",Math.round(A.knee)+"°",jk.d,jk.cls)+K("Biodro (góra korby)",Math.round(A.hipTop)+"°",jh.d,jh.cls)+
            K("Plecy",Math.round(A.back)+"°",(ae?"aero · ":"")+jb.d,jb.cls)+K("Bark",Math.round(A.shoulder)+"°",(ae?"aero · ":"")+js.d,js.cls); })();
      const fz=[fit.stack_mm!=null&&("stack "+Math.round(fit.stack_mm)),fit.reach_mm!=null&&("reach "+Math.round(fit.reach_mm)),fit.drop_mm!=null&&("drop "+Math.round(fit.drop_mm))].filter(Boolean);
      asn.textContent=(fz.length?"Fitter zmierzył: "+fz.join(", ")+" (punkt pomiaru nieopisany). ":"")+(m.as.length?"Założenia: "+m.as.join(", ")+". ":"")+"Sylwetka to model przybliżony; kąty ciała ±kilka stopni.";
    };
    cr.addEventListener("input",()=>{ S.crank=+cr.value; paint(); });
    rcb.addEventListener("change",()=>{ S.rider=rcb.checked; paint(); });
    paint();
  }
  body.appendChild(draw);

  const cols=el("div","qf-grid");
  // geometria
  const gc=card("Geometria ramy (katalog)",[["Edytuj",()=>openForm("Geometria ramy — "+bikeName(bike),GEO_F,geo,
    out=>postJSON("/api/bike/geometry/save",Object.assign(out,{bike_id:bike.id})))]]);
  rows(gc,GEO_F,geo,["source"]);
  if(geo.source){ const a=el("a",null,"źródło"); a.href=geo.source; a.target="_blank"; a.rel="noopener"; const r=el("div","qf-row"); r.appendChild(el("span",null,"Katalog")); r.appendChild(a); gc.appendChild(r); }
  if(geo.notes) gc.appendChild(el("div","note",geo.notes));
  cols.appendChild(gc);
  // ustawienia
  const today=()=>qDateLocal();
  const dupFit=src=>{ const d=Object.assign({},src); delete d.id; d.variant=(src.variant||"ustawienie")+" (kopia)"; d.date_set=today(); d.is_current=1; d._retire=src.is_current?1:0;
    openForm("Duplikat — "+(src.variant||("#"+src.id)),FIT_F.concat([["_retire","Oryginał → historia (odznacz „aktualne”)","c"]]),d,async out=>{
      const retire=out._retire; delete out._retire;
      await postJSON("/api/bike/fitting/save",Object.assign(out,{bike_id:bike.id}));
      if(retire) await postJSON("/api/bike/fitting/save",{id:src.id,bike_id:bike.id,is_current:0}); }); };
  const newFit=()=>{ const d=Object.assign({variant:"nowe ustawienie",date_set:today(),is_current:1},mountedParts(bike.id));
    openForm("Nowe ustawienie — "+bikeName(bike),FIT_F,d,out=>postJSON("/api/bike/fitting/save",Object.assign(out,{bike_id:bike.id}))); };
  const fc=card("Ustawienia (korekty)",[["+ Nowe ustawienie",newFit]]);
  if(!fits.length) fc.appendChild(el("div","note","Brak ustawień."));
  fits.forEach(f=>{
    const it=el("div","qf-item"+(f.id===S.fitId?" sel":"")+(f.thumb?" wph":""));
    if(f.thumb){ const ti=el("img","qf-it-ph"); ti.src=f.thumb; ti.alt=""; ti.addEventListener("click",e=>{ e.stopPropagation(); window.open(f.photo||f.thumb,"_blank"); }); it.appendChild(ti); }
    const t=el("div","qf-it-t"); t.appendChild(el("b",null,f.variant||("ustawienie #"+f.id)));
    if(f.is_current) t.appendChild(el("span","qf-badge","aktualne"));
    it.appendChild(t);
    it.appendChild(el("div","qf-it-m",[f.date_set,f.saddle_height_mm&&("siodło "+fmt(f.saddle_height_mm,"mm")),f.stem_length_mm&&("mostek "+fmt(f.stem_length_mm,"mm")),f.spacer_mm!=null&&("podkł. "+fmt(f.spacer_mm,"mm"))].filter(Boolean).join(" · ")));
    const eb=el("button","btn sec","Edytuj"); eb.type="button";
    eb.addEventListener("click",e=>{ e.stopPropagation(); openForm("Ustawienie — "+(f.variant||("#"+f.id)),FIT_F,f,
      out=>postJSON("/api/bike/fitting/save",Object.assign(out,{id:f.id,bike_id:bike.id})),
      ()=>postJSON("/api/bike/fitting/delete",{id:f.id,confirm:true}),null,{entity:"fitting",id:f.id,photo:f.photo}); });
    const db=el("button","btn sec","Duplikuj"); db.type="button";
    db.addEventListener("click",e=>{ e.stopPropagation(); dupFit(f); });
    const acts=el("div","qf-it-a"); acts.appendChild(db); acts.appendChild(eb); it.appendChild(acts);
    const parts=PART_ROLES.map(([k])=>partById(f[k])).filter(Boolean).map(c=>c.model||c.brand);
    if(parts.length) it.appendChild(el("div","qf-it-m",parts.join(" · ")));
    it.addEventListener("click",()=>{ S.fitId=f.id; S.cmpId=""; render(BODY); });
    fc.appendChild(it);
  });
  cols.appendChild(fc);
  // cialo
  const bc=card("Wymiary ciała",[["Edytuj",()=>bodyM?openForm("Pomiar ciała — "+(bodyM.measured_on||""),BODY_F,bodyM,
      out=>postJSON("/api/bike/body/save",Object.assign(out,{id:bodyM.id})),()=>postJSON("/api/bike/body/delete",{id:bodyM.id,confirm:true}),BODY_HELP):null],
    ["+ Nowy pomiar",()=>{ const d=Object.assign({},bodyM||{}); delete d.id; d.measured_on=qDateLocal();
      openForm("Nowy pomiar ciała",BODY_F,d,out=>postJSON("/api/bike/body/save",out),null,BODY_HELP); }]]);
  if(bodyM){
    const wrap=el("div","qf-body"); const fig=el("div"); fig.innerHTML=bodySvg(bodyM); wrap.appendChild(fig);
    const lst=el("div"); rows(lst,BODY_F,bodyM);
    if(D.weight){ const r=el("div","qf-row"); r.appendChild(el("span",null,"Waga (Garmin)")); r.appendChild(el("b",null,D.weight.kg+" kg"+(D.weight.date?" · "+D.weight.date:""))); lst.appendChild(r); }
    if((D.body||[]).length>1) lst.appendChild(el("div","note","Historia pomiarów: "+D.body.length+" (ostatni pokazany)."));
    if(bodyM.notes) lst.appendChild(el("div","note",bodyM.notes));
    wrap.appendChild(lst); bc.appendChild(wrap);
  } else bc.appendChild(el("div","note","Brak pomiarów."));
  cols.appendChild(bc);
  body.appendChild(cols);
}

window.QFit={ render(bodyEl, data, reload){ D=data; RELOAD=reload; render(bodyEl); },
  _test:{model,angles,rider,bikeSvg,bodySvg,setD:x=>{D=x;}} };
})();
