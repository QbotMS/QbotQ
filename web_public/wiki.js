/* Czytnik wiki: indeks, nawigacja i wyszukiwanie pozostają po stronie przeglądarki. */
(function () {
  'use strict';
  const INDEX_URL = '/wiki-dane/_indeks.json';
  const DATA_ROOT = '/wiki-dane/';
  const DEPTS = [
    ['modelq','ModelQ'],['forma','Forma'],['raport-jazdy','Raport jazdy'],['trener','Trener'],['trasy','Trasy'],['pogoda','Pogoda'],
    ['zdrowie','Zdrowie'],['garaz','Garaż'],['qext2','QExt2'],['albert','Albert'],['polaczenia','Połączenia'],['system','System']
  ];
  // Kanały i źródła opisano w docs/wiki/mapa-serwisu.md.
  const MAP_NODES = [
    {id:'src-fit',lane:0,name:'Jazdy i pliki FIT',desc:'Zapisane aktywności i próbki pomiarów z jazd.',dept:'polaczenia',out:['modelq','raport-jazdy','forma','qext2']},
    {id:'src-weather',lane:0,name:'Prognozy pogody',desc:'Dane pogodowe dla widoków i planowanych tras.',dept:'pogoda',out:['trasy','garaz','trener']},
    {id:'src-route',lane:0,name:'Trasy i mapy',desc:'Pliki tras, dane mapowe i punkty na trasie.',dept:'trasy',out:['raport-jazdy','trener']},
    {id:'src-health',lane:0,name:'Pomiary organizmu',desc:'Sen, tętno, HRV, jedzenie i pomiary ciała.',dept:'zdrowie',out:['forma','trener']},
    {id:'eng-modelq',lane:1,name:'ModelQ',desc:'Wylicza dzienne parametry mocy i obciążenia.',dept:'modelq',out:['forma','raport-jazdy']},
    {id:'eng-forma',lane:1,name:'Forma',desc:'Łączy obciążenie treningowe i wybrane dane organizmu.',dept:'forma',out:['trener']},
    {id:'eng-weather',lane:1,name:'Pogoda',desc:'Udostępnia prognozę, radar i warunki na trasie.',dept:'pogoda',out:['trasy','garaz']},
    {id:'eng-trasy',lane:1,name:'Analiza trasy',desc:'Zbiera informacje o przebiegu, nawierzchni i warunkach.',dept:'trasy',out:['raport-jazdy','trener']},
    {id:'eng-trener',lane:1,name:'Trener',desc:'Pokazuje plan, kalendarz i dopasowanie treningu.',dept:'trener',out:[]},
    {id:'out-report',lane:2,name:'Raport jazdy',desc:'Podsumowuje wykonaną aktywność i wyniki analizy.',dept:'raport-jazdy',out:[]},
    {id:'out-forma',lane:2,name:'Forma i ModelQ',desc:'Pokazuje historię obciążeń i dzienne parametry.',dept:'forma',out:[]},
    {id:'out-plan',lane:2,name:'Trening i wyprawy',desc:'Udostępnia plan treningowy oraz planowanie etapów.',dept:'trener',out:[]},
    {id:'out-garaz',lane:2,name:'Garaż',desc:'Pokazuje wyposażenie i informacje pomocne przed jazdą.',dept:'garaz',out:[]}
  ];
  const DEPT_NAMES = Object.fromEntries(DEPTS);
  const $ = (s, root=document) => root.querySelector(s);
  const app = $('#app'), input = $('#search-input'), results = $('#search-results');
  let index = [], current = null, activeFilter = '', searchTimer = 0;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fold = s => String(s || '').toLowerCase().replace(/ł/g,'l').normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const labelDept = d => DEPT_NAMES[d] || (d === 'ogolne' ? 'Wiki' : d);
  const byPath = p => index.find(x => x.p === p);
  const deptPage = d => byPath(d + '/index.md');
  const linkTo = p => '?p=' + encodeURIComponent(p);
  function setUrl(params, push) {
    const u = new URL(location.href);
    ['p','q'].forEach(k => u.searchParams.delete(k));
    Object.entries(params).forEach(([k,v]) => v && u.searchParams.set(k,v));
    history[push ? 'pushState' : 'replaceState']({}, '', u.pathname + u.search + u.hash);
  }
  function dateFmt(s) { const m = String(s || '').match(/^(\d{4})-(\d\d)-(\d\d)$/); return m ? `${m[3]}.${m[2]}.${m[1]}` : (s || ''); }
  function searchRows(q) {
    const words = fold(q).trim().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return index.map(h => {
      if (activeFilter && h.dzial !== activeFilter) return null;
      const fields = [
        [fold(h.tytul),10],
        [fold([...(h.synonimy||[]),...(h.skroty||[]),...(h.tagi||[])].join(' ')),8],
        [fold(h.opis),4], [fold((h.naglowki||[]).join(' ')),2], [fold(h.tekst),1]
      ];
      let score=0;
      for (const w of words) { let hit=false; for(const [text,weight] of fields) if(text.includes(w)){score+=weight;hit=true;} if(!hit)return null; }
      const meta = [...(h.synonimy||[]),...(h.skroty||[]),...(h.tagi||[])];
      const match = !fold(h.tytul).includes(words[0]) ? meta.find(x=>fold(x).includes(words[0])) : '';
      return {h,score,match};
    }).filter(Boolean).sort((a,b)=>b.score-a.score || a.h.tytul.localeCompare(b.h.tytul,'pl')).slice(0,40);
  }
  function renderSearch(q, syncUrl=true) {
    const rows = searchRows(q);
    results.hidden = !q;
    if (syncUrl) setUrl(q ? {q} : {}, false);
    results.innerHTML = q ? `<div class="filter-row"><span>Filtr działu:</span><button type="button" data-dept="" class="filter-chip ${activeFilter?'':'active'}">Wszystkie</button>${DEPTS.map(([d,n])=>`<button type="button" data-dept="${d}" class="filter-chip ${activeFilter===d?'active':''}">${esc(n)}</button>`).join('')}</div><div class="result-count">${rows.length} wyników</div>${rows.length ? rows.map(({h,match})=>`<a class="result" href="${linkTo(h.p)}"><strong>${esc(h.tytul)}</strong><span>${esc(labelDept(h.dzial))}${h.typ?' · '+esc(h.typ):''}</span><p>${esc(h.opis||'')}</p>${match?`<small>Pasuje do: ${esc(match)}</small>`:''}</a>`).join('') : '<p class="empty">Brak wyników. Spróbuj innego hasła.</p>'}` : '';
  }
  function beginSearch(q, push=true) { input.value=q; if(push) setUrl(q?{q}:{}, true); renderSearch(q,false); }
  input.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{setUrl(input.value?{q:input.value}:{},false);renderSearch(input.value,false);},80);});
  $('#search-form').addEventListener('submit',e=>{e.preventDefault();const first=searchRows(input.value)[0];if(first)navigate(first.h.p,true);else renderSearch(input.value,false);});
  $('#search-form').addEventListener('keydown',e=>{if(e.key==='Escape'){input.value='';renderSearch('',false);}});
  document.addEventListener('keydown',e=>{if(e.key==='/'&&!/input|textarea/i.test(document.activeElement.tagName)){e.preventDefault();input.focus();}});
  results.addEventListener('click',e=>{const b=e.target.closest('[data-dept]');if(b){activeFilter=b.dataset.dept;renderSearch(input.value,false);}});
  $('#themebtn').addEventListener('click',()=>{const dark=document.documentElement.classList.toggle('theme-dark');try{localStorage.setItem('qtheme',dark?'dark':'light');}catch(e){}});
  function navigate(p,push=true){setUrl({p},push);loadPage(p);}
  document.addEventListener('click',e=>{const a=e.target.closest('a[href]');if(!a)return;const u=new URL(a.href,location.href);if(u.pathname===location.pathname&&u.searchParams.has('p')){e.preventDefault();navigate(u.searchParams.get('p'),true);}});
  window.addEventListener('popstate',()=>{const u=new URL(location.href);if(u.searchParams.has('p'))loadPage(u.searchParams.get('p'));else if(u.searchParams.has('q')){input.value=u.searchParams.get('q');renderSearch(input.value,false);home(true);}else{input.value='';results.hidden=true;home(true);}});
  function home(keepSearch=false) {
    current=null; if(!keepSearch){results.hidden=true;input.value='';}
    const recent=index.filter(h=>h.aktualizacja).sort((a,b)=>String(b.aktualizacja).localeCompare(String(a.aktualizacja))).slice(0,5);
    const popular=index.filter(h=>['liczba','algorytm'].includes(fold(h.typ)) && ['modelq','forma','raport-jazdy','trasy'].includes(h.dzial)).slice(0,4);
    app.innerHTML=`<section class="hero"><p class="eyebrow">QBot Lab · przewodnik po serwisie</p><h1>Jak działa QBot — po ludzku</h1><p class="lead">Znajdź wyjaśnienie liczb, ekranów i procesów. Wiki pokazuje, skąd pochodzą dane i jak QBot zamienia je w widoczne wyniki.</p><div class="hero-hints"><span>Wpisz pytanie w wyszukiwarce</span><span>Użyj skrótu /</span><span>Wybierz dział poniżej</span></div><div class="home-popular"><strong>Często szukane</strong><div class="chip-row">${popular.map(h=>`<a class="topic-chip" href="${linkTo(h.p)}">${esc(h.tytul)} <span>↗</span></a>`).join('')||'<span class="muted">Wkrótce</span>'}</div></div></section>
      <section class="section"><div class="section-heading"><div><p class="eyebrow">POWIĄZANIA W SERWISIE</p><h2>Interaktywna mapa QBot</h2></div><span class="muted">Wybierz kafelek, by zobaczyć przepływ</span></div>${renderMap()}</section>
      <section class="section"><div class="section-heading"><div><p class="eyebrow">12 OBSZARÓW</p><h2>Działy wiki</h2></div><span class="muted">${index.length} haseł w indeksie</span></div><div class="dept-grid">${DEPTS.map(([d,n])=>{const h=deptPage(d);const count=index.filter(x=>x.dzial===d).length;return `<a class="dept-card" href="${linkTo(h?h.p:d+'/index.md')}"><span class="dept-arrow">↗</span><h3>${esc(n)}</h3><p>${esc(h?.opis||'Przejrzyj hasła i wyjaśnienia z tego obszaru.')}</p><span class="dept-count">${count} haseł</span></a>`}).join('')}</div></section>
      <section class="section"><div class="section-heading"><div><p class="eyebrow">PUNKTY ORIENTACYJNE</p><h2>Mapy i słowniczek</h2></div></div><div class="guide-grid">${[['mapa-serwisu.md','Mapa serwisu','Zobacz, gdzie QBot pokazuje dane i jak przebiegają główne przepływy.','↗'],['zaleznosci.md','Zależności','Poznaj połączenia pomiędzy elementami i silnikami QBota.','⤴'],['slowniczek.md','Słowniczek','Rozwiń skróty i pojęcia używane w dokumentacji.','Aa']].map(x=>`<a class="guide-card" href="${linkTo(x[0])}"><span>${x[3]}</span><h3>${x[1]}</h3><p>${x[2]}</p></a>`).join('')}</div></section>
      <section class="section"><div class="section-heading"><div><p class="eyebrow">Z DOKUMENTACJI</p><h2>Ostatnio zmienione</h2></div></div><div class="recent-list" id="recent-list">${recent.map(h=>`<a href="${linkTo(h.p)}"><span><strong>${esc(h.tytul)}</strong><small>${esc(labelDept(h.dzial))}</small></span><time>${esc(dateFmt(h.aktualizacja))}</time></a>`).join('')||'<span class="muted">Sprawdzam daty aktualizacji…</span>'}</div></section>`;
    wireMap();
    if (!recent.length) loadRecentDates();
  }
  async function loadRecentDates(){
    // Indeks nie zawiera pola aktualizacja; pobieramy front matter z ograniczoną równoległością.
    let cursor=0;
    const workers=Array.from({length:6},async()=>{while(cursor<index.length){const h=index[cursor++];try{const r=await fetch(DATA_ROOT+encodeURI(h.p));if(!r.ok)continue;const fm=(await r.text()).match(/^---\s*\n([\s\S]*?)\n---/);const m=fm&&fm[1].match(/^aktualizacja:\s*["']?([^\n"']+)/m);if(m)h.aktualizacja=m[1].trim();}catch(e){}}});
    await Promise.all(workers);
    const recent=index.filter(h=>h.aktualizacja).sort((a,b)=>String(b.aktualizacja).localeCompare(String(a.aktualizacja))).slice(0,5),list=$('#recent-list');
    if(list)list.innerHTML=recent.map(h=>`<a href="${linkTo(h.p)}"><span><strong>${esc(h.tytul)}</strong><small>${esc(labelDept(h.dzial))}</small></span><time>${esc(dateFmt(h.aktualizacja))}</time></a>`).join('')||'<span class="muted">Brak dat aktualizacji w dokumentach.</span>';
  }
  function renderMap(){
    const lanes=[['ŹRÓDŁA DANYCH','Dane wejściowe'],['SILNIKI QBOTA','Przetwarzanie'],['GDZIE TO WIDZISZ','Ekrany i wyniki']];
    return `<div class="map-scroll"><div class="service-map"><div class="map-arrows" aria-hidden="true"><span>→</span><span>→</span></div>${lanes.map((l,i)=>`<section class="map-lane"><h3><span>${String(i+1).padStart(2,'0')}</span>${l[0]}<small>${l[1]}</small></h3><div class="map-nodes">${MAP_NODES.filter(n=>n.lane===i).map(n=>`<button type="button" class="map-node" data-node="${n.id}"><span class="node-dot"></span><strong>${esc(n.name)}</strong><small>${esc(n.desc)}</small></button>`).join('')}</div></section>`).join('')}</div></div><div class="map-detail" id="map-detail"><span class="map-detail-icon">↗</span><div><span class="eyebrow">WYBIERZ KAFEL</span><h3>Jak płyną dane</h3><p>Mapa pokazuje najważniejsze źródła, silniki oraz miejsca, w których widać ich wynik.</p></div><div class="map-relations"><span>Korzysta z: <b>—</b></span><span>Zasila: <b>—</b></span></div><a class="button-link" href="${linkTo('mapa-serwisu.md')}">Otwórz mapę serwisu</a></div>`;
  }
  function wireMap(){
    const buttons=[...document.querySelectorAll('.map-node')];
    buttons.forEach(b=>b.addEventListener('click',()=>{
      const node=MAP_NODES.find(n=>n.id===b.dataset.node), connected=new Set([node.id,...node.out.map(d=>'eng-'+d)]);
      if(node.lane===1){node.out.forEach(d=>connected.add('out-'+(d==='raport-jazdy'?'report':d==='forma'?'forma':d==='trener'?'plan':d==='garaz'?'garaz':d)));index.forEach(h=>{if(h.dzial===node.dept)(h.zalezy_od||[]).forEach(x=>{const d=x.split('/')[0];connected.add('eng-'+d);});});}
      buttons.forEach(x=>{x.classList.toggle('selected',x===b);x.classList.toggle('dimmed',!connected.has(x.dataset.node));});
      const refs=node.lane===1?index.filter(h=>h.dzial===node.dept):index.filter(h=>h.dzial===node.dept);
      const uses=[...new Set(refs.flatMap(h=>h.zalezy_od||[]).map(x=>labelDept(x.split('/')[0])))].slice(0,4);
      const feeds=[...new Set(refs.flatMap(h=>h.wplywa_na||[]).map(x=>labelDept(x.split('/')[0])))];
      const out=node.out.map(d=>DEPT_NAMES[d]||d);
      $('#map-detail').innerHTML=`<span class="map-detail-icon">${node.lane===0?'⬡':node.lane===1?'◈':'▣'}</span><div><span class="eyebrow">${['ŹRÓDŁO DANYCH','SILNIK QBOTA','MIEJSCE W SERWISIE'][node.lane]}</span><h3>${esc(node.name)}</h3><p>${esc(node.desc)}</p></div><div class="map-relations"><span>Korzysta z: <b>${esc(uses.join(', ')||'danych wejściowych')}</b></span><span>Zasila: <b>${esc([...new Set([...out,...feeds])].join(', ')||'ekran serwisu')}</b></span></div><a class="button-link" href="${linkTo((deptPage(node.dept)||{}).p||'mapa-serwisu.md')}">Otwórz dział</a>`;
    }));
  }
  function renderTree(dept,p){return `<aside class="tree"><button type="button" class="tree-toggle" aria-expanded="false">Działy wiki <span>⌄</span></button><nav class="tree-nav" aria-label="Działy wiki">${DEPTS.map(([d,n])=>{const items=index.filter(h=>h.dzial===d).sort((a,b)=>a.p===d+'/index.md'?-1:b.p===d+'/index.md'?1:a.tytul.localeCompare(b.tytul,'pl'));return `<div class="tree-group ${d===dept?'open':''}"><a class="tree-dept ${d===dept?'current':''}" href="${linkTo((deptPage(d)||{}).p||d+'/index.md')}"><span>${esc(n)}</span><small>${items.length}</small></a>${d===dept?`<div class="tree-items">${items.map(h=>`<a class="tree-item ${h.p===p?'current':''}" href="${linkTo(h.p)}">${esc(h.tytul)}</a>`).join('')}</div>`:''}</div>`}).join('')}</nav></aside>`;}
  async function loadPage(p){
    if(!p||p.startsWith('/')||p.split('/').includes('..')){notFound();return;}
    const h=byPath(p);if(!h){notFound();return;} current=p;results.hidden=true;
    app.innerHTML=`<div class="article-layout">${renderTree(h.dzial,p)}<article class="article"><nav class="crumbs" aria-label="Okruszki"><a href="/wiki.html">Wiki</a><span>›</span><a href="${linkTo((deptPage(h.dzial)||{}).p||p)}">${esc(labelDept(h.dzial))}</a><span>›</span><span>${esc(h.tytul)}</span></nav><header class="article-head"><div class="article-kicker">${esc(labelDept(h.dzial))}</div><h1>${esc(h.tytul)}</h1>${h.opis?`<p class="article-desc">${esc(h.opis)}</p>`:''}<div class="meta-chips">${h.typ?`<span class="meta-chip">${esc(h.typ)}</span>`:''}${h.aktualizacja?`<span class="meta-chip">Aktualizacja ${esc(dateFmt(h.aktualizacja))}</span>`:''}${(h.synonimy||[]).length?`<span class="meta-chip aliases"><b>Inne nazwy:</b> ${h.synonimy.map(esc).join(' · ')}</span>`:''}</div></header><div class="article-body" id="article-body"><p class="loading">Wczytuję treść…</p></div><div class="relation-cards">${relationCard('Zależy od',h.zalezy_od||[])}${relationCard('Wpływa na',h.wplywa_na||[])}</div><details class="sources"><summary>Źródła</summary><div>${(h.zrodla_kodu||[]).map(x=>`<span>${esc(x)}</span>`).join('')||'Źródła opisano w treści hasła.'}</div></details></article><aside class="toc"><h2>Na tej stronie</h2><nav id="toc-nav" aria-label="Spis treści"></nav></aside></div>`;
    $('.tree-toggle').addEventListener('click',e=>{const n=$('.tree-nav'),open=n.classList.toggle('expanded');e.currentTarget.setAttribute('aria-expanded',String(open));});
    try{const r=await fetch(DATA_ROOT+encodeURI(p));if(!r.ok)throw new Error('HTTP '+r.status);const text=await r.text();if(current!==p)return;const body=stripFrontMatter(text);renderMarkdown(body,h);}catch(e){$('#article-body').innerHTML='<p class="error">Nie udało się wczytać treści tego hasła.</p>';}
    window.scrollTo(0,0);
  }
  function stripFrontMatter(s){if(!s.startsWith('---'))return s;const end=s.indexOf('\n---',3);return end<0?s:s.slice(end+4).replace(/^\s*\n/,'');}
  function normRelative(base,rel){const parts=base.split('/');parts.pop();for(const x of rel.split('/')){if(x==='..')parts.pop();else if(x&&x!=='.')parts.push(x);}return parts.join('/');}
  function renderMarkdown(md,h){
    if(!window.marked){$('#article-body').textContent=md;return;}
    marked.setOptions({gfm:true,breaks:false});const body=$('#article-body');body.innerHTML=marked.parse(md);
    const first=body.querySelector('h1');if(first)first.remove();
    body.querySelectorAll('a').forEach(a=>{const href=a.getAttribute('href');if(!href)return;if(href.endsWith('.md'))a.href=linkTo(normRelative(current,href.split('#')[0]))+(href.includes('#')?'#'+href.split('#')[1]:'');else if(!/^(https?:|mailto:|#|\/)/i.test(href))a.href=DATA_ROOT+normRelative(current,href);if(/^https?:/i.test(href)){a.target='_blank';a.rel='noopener noreferrer';}});
    body.querySelectorAll('img').forEach(img=>{const src=img.getAttribute('src');if(src&&!/^(https?:|data:|\/)/i.test(src))img.src=DATA_ROOT+normRelative(current,src);img.loading='lazy';img.tabIndex=0;img.addEventListener('click',()=>zoom(img));img.addEventListener('keydown',e=>{if(e.key==='Enter')zoom(img);});});
    body.querySelectorAll('blockquote').forEach(q=>{if(fold(q.textContent).includes('do sprawdzenia'))q.classList.add('check-quote');});
    body.querySelectorAll('ol').forEach(ol=>{const heading=ol.previousElementSibling;if(heading&&fold(heading.textContent).includes('jak liczone'))ol.classList.add('steps');});
    if(window.mermaid){mermaid.initialize({startOnLoad:false,theme:document.documentElement.classList.contains('theme-dark')?'dark':'default'});body.querySelectorAll('pre code.language-mermaid').forEach(code=>{const div=document.createElement('div');div.className='mermaid';div.textContent=code.textContent;code.parentElement.replaceWith(div);});mermaid.run({querySelector:'#article-body .mermaid'}).catch(()=>{});}
    const headings=[...body.querySelectorAll('h2')];const nav=$('#toc-nav');nav.innerHTML=headings.map((x,i)=>{if(!x.id)x.id='sekcja-'+i;return `<a href="#${x.id}">${esc(x.textContent)}</a>`}).join('');
    if(!headings.length){$('.toc').hidden=true;return;}
    const links=[...nav.querySelectorAll('a')],obs=new IntersectionObserver(entries=>{const visible=entries.filter(x=>x.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];if(visible){links.forEach(a=>a.classList.toggle('active',a.hash==='#'+visible.target.id));}},{rootMargin:'-12% 0px -78% 0px'});headings.forEach(x=>obs.observe(x));
  }
  function relationCard(title,refs){const found=(refs||[]).map(ref=>{const h=byPath(ref.endsWith('.md')?ref:ref+'.md')||index.find(x=>x.p.startsWith(ref+'/'));return h?`<a href="${linkTo(h.p)}">${esc(h.tytul)} ↗</a>`:''}).filter(Boolean);return found.length?`<section class="relation-card"><h3>${title}</h3><div>${[...new Set(found)].join('')}</div></section>`:'';}
  function zoom(img){const m=$('#image-modal'),i=$('img',m);i.src=img.src;i.alt=img.alt;m.hidden=false;}
  $('#image-modal').addEventListener('click',e=>{if(e.target===e.currentTarget||e.target.tagName==='BUTTON')e.currentTarget.hidden=true;});
  function notFound(){app.innerHTML='<section class="empty-page"><h1>Nie znaleziono hasła</h1><p>Sprawdź adres albo wyszukaj temat w wiki.</p><a href="/wiki.html">Wróć na stronę główną</a></section>';}
  async function init(){try{const r=await fetch(INDEX_URL);if(!r.ok)throw new Error('HTTP '+r.status);const data=await r.json();index=data.hasla||[];const u=new URL(location.href),p=u.searchParams.get('p'),q=u.searchParams.get('q');if(p)await loadPage(p);else if(q){input.value=q;renderSearch(q,false);home(true);}else home();}catch(e){app.innerHTML='<section class="empty-page"><h1>Wiki jest chwilowo niedostępne</h1><p>Nie udało się wczytać indeksu haseł.</p></section>';}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
