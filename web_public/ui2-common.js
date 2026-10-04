/* ui2-common.js v3 — wspolne helpery */
function q$(id){return document.getElementById(id);}
function qN(v,d){return typeof v==="number"&&isFinite(v)?v.toFixed(d==null?0:d):"—";}
function qHM(s){if(typeof s!=="number"||!isFinite(s))return "—";var m=Math.round(s/60);return Math.floor(m/60)+":"+String(m%60).padStart(2,"0");}
function qEsc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c];});}
async function qJSON(u){var r=await fetch(u+(u.indexOf("?")>=0?"&":"?")+"_="+Date.now(),{credentials:"same-origin",cache:"no-store"});if(!r.ok)throw new Error(r.status);return r.json();}
function qDelta(v,prev,unit,flip){if(typeof v!=="number"||typeof prev!=="number")return "";var d=v-prev;if(Math.abs(d)<0.05)return "";var up=flip?d<0:d>0;return '<span class="delta '+(up?"up":"dn")+'">'+(d>0?"+":"")+qN(d,1)+(unit||"")+'</span>';}
function qTip(){document.querySelectorAll(".tip[data-tip]").forEach(function(e){e.addEventListener("click",function(ev){ev.stopPropagation();var t=e.getAttribute("data-tip");if(!t)return;var d=document.createElement("div");d.className="popup";d.textContent=t;e.appendChild(d);setTimeout(function(){d.remove();},4000);});});}
function qDayName(ds){var d=new Date(ds+"T12:00:00");return ["ndz","pon","wt","śr","czw","pt","sob"][d.getDay()];}
function qPad2(n){return n<10?"0"+n:""+n;}
function qLocalISO(d){return d.getFullYear()+"-"+qPad2(d.getMonth()+1)+"-"+qPad2(d.getDate());}
function qToday(){return qLocalISO(new Date());}
