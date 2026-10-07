"""Strona startowa / wizytowka qbot-web = /login (2026-10-07, v2: styl strony Start).
Tokeny i kroje z index.html (Big Shoulders Display / Hanken Grotesk / JetBrains Mono, akcent #e8742a).
Zdjecia: /landing/*.jpg (wybrane 'liked' ze strava_photo, bez metadanych, katalog /opt/qbot/web/landing).
"Zaloguj" otwiera okno z formularzem i QR (qbot_web_auth_ui). Dok.: docs/WEB_DEMO_AUTH.md"""

_TEMPLATE = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QBot — prywatny asystent rowerowy</title>
<meta name="description" content="QBot — prywatny asystent rowerowy: forma, plan treningów, analiza trasy, wyprawy, garaż.">
<link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="alternate icon" href="/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800;900&family=Hanken+Grotesk:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap">
<link rel="preload" as="image" href="/landing/hero-poster.jpg">
<style>
:root{--bg:#f8f4ec;--card:#fffdf8;--well:#efe8da;--ink:#2a241c;--ink2:#6f6455;--mut:#9a9184;--line:#e6dfd0;
  --acc:#e8742a;--acc-ink:#b3520f;--acc-bg:#fbe5d0;--night:#14181f;
  --disp:"Big Shoulders Display","Arial Narrow","Roboto Condensed",Impact,sans-serif;
  --body:"Hanken Grotesk",-apple-system,"Segoe UI",system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#1a1f27;--card:#0d1016;--well:#1f2631;--ink:#f3efe8;--ink2:#b9c0cc;
  --mut:#8792a4;--line:#2b3340;--acc-ink:#ff9c55;--acc-bg:#4a2a0a}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit}
.disp{font-family:var(--disp);font-weight:800;text-transform:uppercase;line-height:.88;letter-spacing:.005em}
.btn{appearance:none;border:0;border-radius:999px;font:600 1rem var(--body);padding:.95rem 1.9rem;cursor:pointer;
  display:inline-flex;align-items:center;gap:.6rem;text-decoration:none;transition:transform .18s ease,background .18s ease}
.btn:hover{transform:translateY(-2px)}
.btn-acc{background:var(--acc);color:#1b1407}
.btn-acc:hover{background:#f0843d}
.btn-ghost{background:rgba(255,255,255,.12);color:#fff;box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.7);
  backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.btn-ghost:hover{background:rgba(255,255,255,.22)}
.btn:focus-visible,.tile:focus-visible,.dlg input:focus-visible,.dlg button:focus-visible{outline:3px solid var(--acc);outline-offset:3px}

/* ---- naglowek ---- */
.top{position:absolute;z-index:5;top:0;left:0;right:0;display:flex;justify-content:space-between;align-items:center;
  padding:1.4rem clamp(1.2rem,4vw,3.5rem);color:#fff}
.mark{font-family:var(--disp);font-weight:900;font-size:clamp(2.4rem,4vw,3.4rem);line-height:1;letter-spacing:.04em;display:flex;align-items:center;gap:.55rem}
.mark i{width:.62rem;height:.62rem;border-radius:50%;background:var(--acc);display:inline-block;box-shadow:0 0 0 4px rgba(232,116,42,.3)}
.top .btn{padding:.7rem 1.5rem}

/* ---- hero ---- */
.hero{position:relative;height:100vh;height:100svh;min-height:600px;overflow:hidden;background:var(--night);color:#fff}
.slide{position:absolute;inset:0;background-size:cover;background-position:center;opacity:0;
  animation:slide 21s infinite;will-change:opacity,transform}
.slide:nth-child(1){background-image:url(/landing/hero-1.jpg)}
.slide:nth-child(2){background-image:url(/landing/hero-2.jpg);animation-delay:7s}
.slide:nth-child(3){background-image:url(/landing/hero-3.jpg);animation-delay:14s}
@keyframes slide{0%{opacity:0;transform:scale(1.12)}5%{opacity:1}33%{opacity:1}39%{opacity:0;transform:scale(1.02)}100%{opacity:0;transform:scale(1.02)}}
.hero-video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:var(--night)}
.grain{position:absolute;inset:-50%;z-index:1;pointer-events:none;opacity:.16;mix-blend-mode:overlay;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");animation:grain .8s steps(5) infinite}
@keyframes grain{0%{transform:translate(0,0)}20%{transform:translate(-4%,3%)}40%{transform:translate(3%,-5%)}60%{transform:translate(-6%,-2%)}80%{transform:translate(5%,4%)}100%{transform:translate(0,0)}}
.shade{position:absolute;inset:0;background:
  linear-gradient(180deg,rgba(14,17,22,.55) 0%,rgba(14,17,22,0) 26%),
  linear-gradient(10deg,rgba(14,17,22,.88) 8%,rgba(14,17,22,.35) 48%,rgba(14,17,22,0) 72%)}
.hero-body{position:absolute;z-index:3;left:0;right:0;bottom:0;padding:0 clamp(1.2rem,4vw,3.5rem) clamp(4.5rem,9vh,6.5rem)}
.hero h1{font-size:clamp(4.4rem,15vw,13.5rem);margin:0 0 1.4rem;max-width:12ch}
.hero h1 .ln{display:block;overflow:hidden;padding-bottom:.04em}
.hero h1 .ln span{display:block;transform:translateY(105%);animation:rise .9s cubic-bezier(.2,.75,.2,1) forwards}
.hero h1 .ln:nth-child(2) span{animation-delay:.14s;color:var(--acc)}
.hero h1{max-width:none;font-size:clamp(2.8rem,8vw,7.5rem)}
.hero h1 .rot span{white-space:nowrap}
.hero h1 .rot span.go-out{animation:rotOut .45s cubic-bezier(.6,0,.8,.4) forwards}
.hero h1 .rot span.go-in{animation:rotIn .6s cubic-bezier(.2,.75,.2,1) forwards}
@keyframes rotOut{from{transform:none}to{transform:translateY(-105%)}}
@keyframes rotIn{from{transform:translateY(105%)}to{transform:none}}
@media (max-width:620px){.hero h1 .rot span{white-space:normal}}
@keyframes rise{to{transform:none}}
.hero p{font-size:clamp(1.05rem,1.6vw,1.3rem);max-width:36rem;margin:0 0 2rem;color:#f1ece3;opacity:0;animation:fade .8s .45s forwards}
.hero .acts{display:flex;flex-wrap:wrap;gap:.8rem;opacity:0;animation:fade .8s .6s forwards}
@keyframes fade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.bars{position:absolute;z-index:3;right:clamp(1.2rem,4vw,3.5rem);bottom:clamp(2rem,4vh,3rem);display:flex;gap:.45rem}
.bars i{display:block;width:3.2rem;height:3px;background:rgba(255,255,255,.3);border-radius:2px;overflow:hidden;position:relative}
.bars i::after{content:"";position:absolute;inset:0;background:#fff;transform:scaleX(0);transform-origin:left;animation:bar 21s infinite linear}
.bars i:nth-child(2)::after{animation-delay:7s}.bars i:nth-child(3)::after{animation-delay:14s}
@keyframes bar{0%{transform:scaleX(0)}33.3%{transform:scaleX(1)}33.4%{transform:scaleX(0)}100%{transform:scaleX(0)}}

/* ---- moduly ---- */
.wrap{max-width:1320px;margin:0 auto;padding:0 clamp(1.2rem,4vw,3.5rem)}
.mods{padding:clamp(4.5rem,10vw,8rem) 0 clamp(3rem,6vw,5rem)}
.sec-h{font-size:clamp(2.8rem,6.5vw,5.6rem);margin:0 0 1rem;max-width:16ch}
.sec-p{color:var(--ink2);font-size:1.15rem;max-width:40rem;margin:0 0 clamp(2.2rem,4vw,3.5rem)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:clamp(15rem,22vw,19rem);gap:clamp(.7rem,1.2vw,1.1rem)}
.tile{position:relative;border-radius:18px;overflow:hidden;color:#fff;background:var(--night);isolation:isolate;
  clip-path:inset(12% 0 0 0 round 18px);opacity:0;transition:clip-path 1s cubic-bezier(.2,.75,.2,1),opacity .6s ease}
.tile.in{clip-path:inset(0 0 0 0 round 18px);opacity:1}
.tile img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-2;transform:scale(1.04);transition:transform 1.2s cubic-bezier(.2,.75,.2,1)}
.tile:hover img{transform:scale(1.1)}
.tile::before{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(0deg,rgba(14,17,22,.86) 0%,rgba(14,17,22,.25) 52%,rgba(14,17,22,0) 75%)}
.tile .tx{position:absolute;left:0;right:0;bottom:0;padding:1.4rem 1.5rem 1.5rem}
.tile h3{font-family:var(--disp);font-weight:800;text-transform:uppercase;font-size:clamp(2rem,2.8vw,2.6rem);line-height:.9;margin:0 0 .45rem}
.tile p{margin:0;color:#ece6dc;font-size:.98rem;line-height:1.45;max-width:30rem}
.t-big{grid-column:span 2;grid-row:span 2}.t-big h3{font-size:clamp(2.6rem,4.4vw,4rem)}
.t-wide{grid-column:span 2}.t-tall{grid-row:span 2}

/* ---- trasa ---- */
.route{padding:0 0 clamp(4.5rem,9vw,7rem)}
.rcard{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:clamp(1.6rem,4vw,3.2rem);
  display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:clamp(1.5rem,4vw,3.5rem);align-items:end}
.rcard h2{font-size:clamp(2.6rem,5vw,4.4rem);margin:0 0 1rem}
.rcard .sec-p{margin-bottom:1.8rem}
.nums{display:grid;grid-template-columns:repeat(3,auto);gap:1.6rem;justify-content:start}
.nums b{display:block;font-family:var(--disp);font-weight:800;font-size:clamp(2.6rem,4.4vw,3.6rem);line-height:.9;color:var(--acc-ink);font-variant-numeric:tabular-nums}
.nums span{color:var(--ink2);font-size:.92rem}
#prof{width:100%;height:auto;display:block;overflow:visible}
#prof .grid-l{stroke:var(--line);stroke-width:1}
#prof .area{fill:var(--acc-bg)}
#prof .line{fill:none;stroke:var(--acc);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
#prof .lbl{font-family:var(--mono);font-size:11px;fill:var(--mut)}
.legend{display:flex;flex-wrap:wrap;gap:1.2rem;margin-top:.9rem;font-size:.88rem;color:var(--ink2)}
.legend i{display:inline-block;width:.9rem;height:.55rem;border-radius:2px;margin-right:.4rem;vertical-align:middle}

/* ---- koniec ---- */
.closing{position:relative;overflow:hidden;color:#fff;background:var(--night) url(/landing/hero-2.jpg) center/cover}
.closing::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(14,17,22,.88),rgba(14,17,22,.35))}
.closing .wrap{position:relative;padding-top:clamp(5rem,12vw,9rem);padding-bottom:clamp(5rem,12vw,9rem)}
.closing h2{font-size:clamp(3rem,8vw,7rem);margin:0 0 2rem;max-width:12ch}
footer{color:var(--mut);font-size:.9rem;padding:1.6rem 0 2.2rem}
footer .wrap{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}

/* ---- okno logowania ---- */
.dlg{border:0;padding:0;border-radius:22px;background:var(--card);color:var(--ink);width:min(380px,92vw);box-shadow:0 30px 80px rgba(0,0,0,.4)}
.dlg::backdrop{background:rgba(14,17,22,.6);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.dlg[open]{animation:pop .25s cubic-bezier(.2,.75,.2,1)}
@keyframes pop{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}
.dlg form{padding:2rem 2rem 1.8rem;position:relative}
.dlg h2{font-family:var(--disp);font-weight:800;text-transform:uppercase;font-size:2.6rem;line-height:.9;margin:0 0 1.2rem}
.dlg label{display:block;font-size:.85rem;color:var(--ink2);margin:.8rem 0 .3rem}
.dlg input{width:100%;padding:.75rem .85rem;border-radius:12px;border:1.5px solid var(--line);background:var(--bg);color:var(--ink);font:1rem var(--body)}
.dlg input:focus{border-color:var(--acc);outline:none}
.dlg button{margin-top:1.3rem;width:100%;padding:.85rem;border:0;border-radius:999px;background:var(--acc);color:#1b1407;font:600 1rem var(--body);cursor:pointer}
.dlg .err{color:#c2410c;font-size:.88rem;margin-top:.8rem}
.dlg.guest .login-part,.dlg:not(.guest) .guest-part{display:none}
.dlg .guest-info{color:var(--ink2);font-size:.95rem;line-height:1.45;margin:0 0 1rem}
.dlg.guest .guest-part > div{margin-top:0!important;border-top:0!important;padding-top:0!important}
.dlg.guest #qrbox{margin-top:0!important}
.dlg .x{position:absolute;top:1rem;right:1rem;width:2.3rem;height:2.3rem;margin:0;padding:0;border-radius:50%;background:var(--well);color:var(--ink);font-size:1.3rem;line-height:1}
.dlg #qrgo{background:var(--well)!important;color:var(--ink)!important;margin-top:0!important}
.dlg #qrcode{color:var(--ink)!important;font-family:var(--disp)!important;font-size:2.4rem!important}
.dlg #qrmsg{color:var(--ink2)!important}
.dlg #qrimg{box-shadow:0 0 0 1px var(--line)}
.dlg form > div[style*="border-top"]{border-top-color:var(--line)!important}

@media (max-width:980px){.grid{grid-template-columns:repeat(2,1fr)}.rcard{grid-template-columns:1fr}}
@media (max-width:620px){
  .grid{grid-template-columns:1fr;grid-auto-rows:17rem}.t-big,.t-wide{grid-column:span 1}.t-big,.t-tall{grid-row:span 1}
  .bars{display:none}.nums{grid-template-columns:repeat(3,1fr);gap:.8rem}.top .btn{padding:.6rem 1.1rem}
}
@media (prefers-reduced-motion:reduce){
  .grain{animation:none}
  .hero h1 .ln span,.hero p,.hero .acts{animation:none;transform:none;opacity:1}
  .tile{clip-path:none;opacity:1;transition:none}.tile img{transition:none}.btn{transition:none}.dlg[open]{animation:none}
}
</style>
</head>
<body>
<header class="top">
  <div class="mark"><i></i>Albert QBot</div>
</header>

<section class="hero">
  <video class="hero-video" id="hero-video" muted loop playsinline preload="auto" poster="/landing/hero-poster.jpg" aria-hidden="true"></video>
  <div class="grain" aria-hidden="true"></div>
  <div class="shade"></div>
  <div class="hero-body">
    <h1 class="disp"><span class="ln"><span>Tylko</span></span><span class="ln rot"><span id="rot">nowe kwadraty</span></span></h1>
    <p>AlbertQbot pilnuje formy, układa trening<br>i czyta trasę metr po metrze, zanim na nią wyjedziesz.</p>
    <div class="acts">
      <button class="btn btn-acc" type="button" data-login>Zaloguj</button>
      <button class="btn btn-ghost" type="button" data-guest>Wejdź jako gość</button>
    </div>
  </div>
</section>

<section class="mods">
  <div class="wrap">
    <h2 class="disp sec-h">Wszystko o jeździe w jednym miejscu</h2>
    <p class="sec-p">Dane z licznika, kalendarza, pogody i garażu składają się w jeden obraz. Bez przepisywania i bez zgadywania.</p>
    <div class="grid">
      <article class="tile t-big"><img src="/landing/m-trasa.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Analiza trasy</h3><p>Nawierzchnia co 50 metrów, podjazdy, pogoda na całej trasie i realny czas przejazdu z Twoich jazd.</p></div></article>
      <article class="tile"><img src="/landing/m-forma.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Forma</h3><p>Obciążenie, zmęczenie, sen i waga w jednym widoku.</p></div></article>
      <article class="tile t-tall"><img src="/landing/m-albert.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Albert</h3><p>Asystent AI, który odpowiada na podstawie Twoich danych, a nie zgaduje.</p></div></article>
      <article class="tile"><img src="/landing/m-trener.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Trener</h3><p>Plan tygodnia pod kalendarz, pogodę i samopoczucie.</p></div></article>
      <article class="tile t-wide"><img src="/landing/m-planer.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Planer wyprawy</h3><p>Kilka dni w siodle: etapy, noclegi, pogoda i lista rzeczy do spakowania.</p></div></article>
      <article class="tile t-wide"><img src="/landing/m-garaz.jpg" alt="" loading="lazy">
        <div class="tx"><h3>Garaż</h3><p>Rowery, koła i części z przebiegami.</p></div></article>
    </div>
  </div>
</section>

<section class="route">
  <div class="wrap">
    <div class="rcard" id="rcard">
      <div>
        <h2 class="disp">Trasa przeczytana przed wyjazdem</h2>
        <p class="sec-p">Zanim ruszysz, wiesz, gdzie kończy się asfalt, ile metrów w górę czeka i ile to realnie potrwa.</p>
        <div class="nums">
          <div><b id="n-km">0</b><span>km</span></div>
          <div><b id="n-up">0</b><span>m w górę</span></div>
          <div><b id="n-gr">0%</b><span>szutru</span></div>
        </div>
      </div>
      <div>
        <svg id="prof" viewBox="0 0 720 260" aria-hidden="true">
          <g id="pg"></g>
          <path id="p-area" class="area"></path>
          <path id="p-line" class="line"></path>
          <g id="p-surf"></g>
        </svg>
        <div class="legend"><span><i style="background:var(--ink)"></i>asfalt</span><span><i style="background:var(--acc)"></i>szuter</span><span><i style="background:var(--mut)"></i>teren</span></div>
      </div>
    </div>
  </div>
</section>

<section class="closing">
  <div class="wrap">
    <h2 class="disp">Następna trasa już czeka.</h2>
    <button class="btn btn-acc" type="button" data-login>Zaloguj</button>
  </div>
</section>
<footer><div class="wrap"><span>QBot — prywatny asystent rowerowy</span><span>Gość wchodzi kodem QR zatwierdzonym na telefonie właściciela.</span></div></footer>

<dialog class="dlg" id="login-dlg" aria-labelledby="login-title">
  <form method="post" action="/login" autocomplete="on">
    <button type="button" class="x" id="close-login" aria-label="Zamknij">&times;</button>
    <h2 id="login-title">Zaloguj</h2>
    <div class="login-part">
    <label for="u">Login</label>
    <input id="u" name="username" type="text" autocomplete="username" required>
    <label for="p">Hasło</label>
    <input id="p" name="password" type="password" autocomplete="current-password" required>
    <input type="hidden" name="next" value="%%NEXT%%">
    <button type="submit">Zaloguj</button>
    %%ERR%%
    </div>
    <div class="guest-part">
    <p class="guest-info">Pokaż ten kod właścicielowi serwisu. Zeskanuje go telefonem i zatwierdzi wejście. Dostaniesz podgląd na 1 godzinę, bez możliwości zmian.</p>
    %%QR_HTML%%
    </div>
  </form>
</dialog>

<script src="/landing/hasla.js"></script>
<script>
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* --- okno logowania --- */
  var dlg = document.getElementById('login-dlg');
  function openLogin(guest) {
    dlg.classList.toggle('guest', !!guest);
    document.getElementById('login-title').textContent = guest ? 'Wejście gościa' : 'Zaloguj';
    if (dlg.showModal) { if (!dlg.open) dlg.showModal(); } else { dlg.setAttribute('open', ''); }
    if (guest) { var q = document.getElementById('qrgo'); if (q && !q.disabled) q.click(); if (q) q.focus(); }
    else { var u = document.getElementById('u'); if (u) u.focus(); }
  }
  [].forEach.call(document.querySelectorAll('[data-login]'), function (b) { b.addEventListener('click', function () { openLogin(false); }); });
  [].forEach.call(document.querySelectorAll('[data-guest]'), function (b) { b.addEventListener('click', function () { openLogin(true); }); });
  document.getElementById('close-login').addEventListener('click', function () { dlg.close ? dlg.close() : dlg.removeAttribute('open'); });
  dlg.addEventListener('click', function (e) { if (e.target === dlg && dlg.close) dlg.close(); });
  if (%%OPEN%%) openLogin(false);

  /* --- film tla: 720p na waskich ekranach, bez filmu przy ograniczeniu ruchu (zostaje kadr) --- */
  var hv = document.getElementById('hero-video');
  if (hv && !reduce) {
    hv.src = window.matchMedia('(max-width: 820px)').matches ? '/landing/hero-m.mp4' : '/landing/hero.mp4';
    var pr = hv.play(); if (pr && pr.catch) pr.catch(function () {});
  }

  /* --- rotujace hasla --- */
  /* lista hasel: /opt/qbot/web/landing/hasla.js (wspolna z START) */
  var HASLA = (window.QBOT_HASLA && window.QBOT_HASLA.length) ? window.QBOT_HASLA : ['nowe kwadraty'];
  var rot = document.getElementById('rot'), hi = 0;
  rot.textContent = HASLA[0];
  setInterval(function () {
    hi = (hi + 1) % HASLA.length;
    if (reduce) { rot.textContent = HASLA[hi]; return; }
    rot.className = 'go-out';
    setTimeout(function () { rot.textContent = HASLA[hi]; rot.className = 'go-in'; }, 450);
  }, 3600);

  /* --- kafle: odsloniecie przy przewijaniu --- */
  var tiles = document.querySelectorAll('.tile');
  if (reduce || !('IntersectionObserver' in window)) {
    [].forEach.call(tiles, function (t) { t.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { var i = [].indexOf.call(tiles, e.target);
          setTimeout(function () { e.target.classList.add('in'); }, (i % 3) * 110); io.unobserve(e.target); }
      });
    }, {threshold: .18});
    [].forEach.call(tiles, function (t) { io.observe(t); });
  }

  /* --- profil trasy z nawierzchnia --- */
  var NS = 'http://www.w3.org/2000/svg', N = 220, W = 720, TOP = 18, BOT = 200, KM = 64.2;
  var alt = [];
  for (var n = 0; n <= N; n++) {
    var t = n / N;
    alt.push(160 + 95 * Math.sin(Math.PI * 2 * t * 1.15 - 1.2) + 55 * Math.sin(Math.PI * 2 * t * 3.3 + .7)
             + 22 * Math.sin(Math.PI * 2 * t * 8.9) + 120 * Math.exp(-Math.pow((t - .62) / .07, 2)));
  }
  var mn = Math.min.apply(null, alt), mx = Math.max.apply(null, alt), up = 0;
  for (var k = 1; k <= N; k++) up += Math.max(0, alt[k] - alt[k - 1]);
  function X(i) { return (W * i / N).toFixed(1); }
  function Y(a) { return (BOT - (BOT - TOP) * (a - mn) / (mx - mn)).toFixed(1); }
  var pg = document.getElementById('pg');
  for (var gy = 0; gy < 4; gy++) {
    var ln = document.createElementNS(NS, 'line'), yy = TOP + (BOT - TOP) * gy / 3;
    ln.setAttribute('x1', 0); ln.setAttribute('x2', W); ln.setAttribute('y1', yy); ln.setAttribute('y2', yy); ln.setAttribute('class', 'grid-l');
    pg.appendChild(ln);
    var tx = document.createElementNS(NS, 'text');
    tx.setAttribute('x', 4); tx.setAttribute('y', yy - 5); tx.setAttribute('class', 'lbl');
    tx.textContent = Math.round(mx - (mx - mn) * gy / 3) + ' m'; pg.appendChild(tx);
  }
  var d = '', a = 'M0 ' + BOT;
  for (var m = 0; m <= N; m++) { d += (m ? 'L' : 'M') + X(m) + ' ' + Y(alt[m]); a += 'L' + X(m) + ' ' + Y(alt[m]); }
  var line = document.getElementById('p-line'), area = document.getElementById('p-area');
  line.setAttribute('d', d); area.setAttribute('d', a + 'L' + W + ' ' + BOT + 'Z');
  /* nawierzchnia odcinkami: [udzial, typ] */
  var segs = [[.08, 'a'], [.14, 's'], [.05, 't'], [.12, 's'], [.09, 'a'], [.17, 's'], [.06, 't'], [.11, 's'], [.07, 'a'], [.11, 's']];
  var col = {a: 'var(--ink)', s: 'var(--acc)', t: 'var(--mut)'}, sx = 0, gravel = 0, sg = document.getElementById('p-surf'), rects = [];
  segs.forEach(function (s) {
    var r = document.createElementNS(NS, 'rect');
    r.setAttribute('x', (sx * W).toFixed(1)); r.setAttribute('y', BOT + 22); r.setAttribute('height', 14);
    r.setAttribute('width', Math.max(0, s[0] * W - 2).toFixed(1)); r.setAttribute('rx', 3);
    r.style.fill = col[s[1]]; r.style.transformOrigin = (sx * W) + 'px 0'; sg.appendChild(r); rects.push([r, sx]);
    if (s[1] === 's') gravel += s[0]; sx += s[0];
  });
  var nKm = document.getElementById('n-km'), nUp = document.getElementById('n-up'), nGr = document.getElementById('n-gr');
  var L = line.getTotalLength();
  function show(p) {
    line.style.strokeDasharray = L; line.style.strokeDashoffset = (L * (1 - p)).toFixed(1);
    area.style.clipPath = 'inset(0 ' + ((1 - p) * 100).toFixed(2) + '% 0 0)';
    rects.forEach(function (r) { r[0].style.opacity = p >= r[1] ? 1 : 0; });
    nKm.textContent = (KM * p).toFixed(1).replace('.', ',');
    nUp.textContent = Math.round(up * p);
    nGr.textContent = Math.round(gravel * 100 * p) + '%';
  }
  if (reduce || !('IntersectionObserver' in window)) { show(1); return; }
  show(0);
  var started = false, io2 = new IntersectionObserver(function (es) {
    if (started || !es[0].isIntersecting) return;
    started = true; io2.disconnect();
    var t0 = null, DUR = 2600;
    function ease(x) { return 1 - Math.pow(1 - x, 3); }
    function fr(ts) { if (t0 === null) t0 = ts; var x = Math.min(1, (ts - t0) / DUR); show(ease(x)); if (x < 1) requestAnimationFrame(fr); }
    requestAnimationFrame(fr);
  }, {threshold: .35});
  io2.observe(document.getElementById('rcard'));
})();
</script>
%%QR_SCRIPT%%
</body>
</html>"""


def render(safe_next_escaped, err_html, open_dialog):
    """safe_next_escaped: juz przefiltrowany i zakodowany do HTML parametr next."""
    import os as _os
    import qbot_web_auth_ui as _ui
    page = _TEMPLATE
    for _n in ("hero.mp4", "hero-m.mp4", "hero-poster.jpg", "hasla.js"):   # wersja = data pliku -> brak starej kopii w cache
        try:
            _v = int(_os.path.getmtime("/opt/qbot/web/landing/" + _n))
            page = page.replace("/landing/" + _n, "/landing/%s?v=%d" % (_n, _v))
        except OSError:
            pass
    return (page
            .replace("%%NEXT%%", safe_next_escaped)
            .replace("%%ERR%%", err_html)
            .replace("%%OPEN%%", "true" if open_dialog else "false")
            .replace("%%QR_HTML%%", _ui.LOGIN_QR_HTML)
            .replace("%%QR_SCRIPT%%", _ui.LOGIN_QR_SCRIPT))
