p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# zamieniam sekcje FTP sparkline na zsynchronizowany chart
old_ftp_start=s.index("/* FTP sparkline */")
old_ftp_end=s.index("/* statystyki */")

new_ftp='''/* FTP chart (zsynchronizowany z glownym) */
  if(window._ftpChart){window._ftpChart.destroy();window._ftpChart=null;}
  var ftpCanvas=q$("trendy-ftp-canvas");
  var ftpArr=SN.map(function(s2){return s2.ftp_est_w||s2.ftp||null;});
  var ftpNow=ftpArr[N-1]||0,ftpPrev=ftpArr[0]||0,ftpD=ftpNow-ftpPrev;
  var fEl=q$("trendy-ftp-val2");
  if(fEl)fEl.textContent=Math.round(ftpNow)+" W ("+(ftpD>0?"+":"")+Math.round(ftpD)+" / "+RNG+" dni)";
  if(ftpCanvas){
    window._ftpChart=new Chart(ftpCanvas,{type:"line",data:{labels:labels,datasets:[
      {data:ftpArr,borderColor:"#e67e22",borderWidth:2.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false}
    ]},options:{responsive:true,maintainAspectRatio:false,
      interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:false},tooltip:{enabled:false}},
      scales:{x:{display:false},y:{position:"left",ticks:{color:txtCol,font:{size:10}},grid:{color:gridCol}}}}});
    /* synchronizacja: hover na glownym -> crosshair na FTP i odwrotnie */
    var sync=function(src,dst,srcCanvas,dstCanvas){
      srcCanvas.addEventListener("mousemove",function(evt){
        var pts=src.getElementsAtEventForMode(evt,"index",{intersect:false},true);
        if(pts.length){var idx=pts[0].index;
          dst.setActiveElements([{datasetIndex:0,index:idx}]);dst.tooltip.setActiveElements([{datasetIndex:0,index:idx}],{x:0,y:0});dst.update("none");
          if(src===window._trendyChart){var fv=ftpArr[idx];var fe=q$("trendy-ftp-val2");if(fe&&typeof fv==="number")fe.textContent=Math.round(fv)+" W · "+SN[idx].day;}
        }
      });
      srcCanvas.addEventListener("mouseleave",function(){dst.setActiveElements([]);dst.tooltip.setActiveElements([],{x:0,y:0});dst.update("none");
        var fe=q$("trendy-ftp-val2");if(fe)fe.textContent=Math.round(ftpNow)+" W ("+(ftpD>0?"+":"")+Math.round(ftpD)+" / "+RNG+" dni)";});
    };
    sync(window._trendyChart,window._ftpChart,canvas,ftpCanvas);
    sync(window._ftpChart,window._trendyChart,ftpCanvas,canvas);
  }
  '''
s=s[:old_ftp_start]+new_ftp+s[old_ftp_end:]

# usuwam stary fEl (trendy-ftp-val)
s=s.replace('var fEl=q$("trendy-ftp-val");\n  if(fEl)fEl.innerHTML=Math.round(ftpNow)+\' W <span style="font-size:14px;color:\'+(ftpD>=0?"var(--good)":"var(--bad)")+\'">\'+((ftpD>0?"+":"")+Math.round(ftpD))+\' W / \'+RNG+\' dni</span>\';','')

open(p,"w").write(s)
print("FTP synced chart done")
