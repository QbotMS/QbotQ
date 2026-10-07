"""Elementy ekranu dla dostepu demo przez QR (2026-10-07). Logika i bezpieczenstwo: qbot_web_auth.py.
Dok.: docs/WEB_DEMO_AUTH.md"""


def qr_svg(data):
    """Kod QR jako SVG (biblioteka qrcode, bez PIL)."""
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string(encoding="unicode")


# Wstawiane do formularza /login (qbot_web._login_form), pod przyciskiem "Zaloguj".
LOGIN_QR_HTML = r"""<div style="margin-top:1.2rem;border-top:1px solid #333;padding-top:1rem">
<button type="button" id="qrgo" style="background:#374151;margin-top:0">Dostęp tymczasowy przez telefon</button>
<div id="qrbox" style="display:none;text-align:center;margin-top:.8rem">
<div id="qrimg" style="background:#fff;padding:6px;border-radius:8px;display:inline-block;width:190px;height:190px"></div>
<div id="qrcode" style="font-size:1.6rem;font-weight:700;letter-spacing:.15em;margin:.6rem 0;color:#fff"></div>
<div id="qrmsg" style="font-size:.82rem;color:#aaa"></div>
</div>
<style>#qrimg svg{width:100%;height:100%;display:block}</style>
</div>"""

LOGIN_QR_SCRIPT = r"""<script>
(function () {
  var go = document.getElementById('qrgo'), box = document.getElementById('qrbox'),
      img = document.getElementById('qrimg'), cd = document.getElementById('qrcode'),
      msg = document.getElementById('qrmsg'), t = null;
  if (!go || !window.fetch) return;
  function say(s) { msg.textContent = s; }
  function stop() { if (t) { clearTimeout(t); t = null; } }
  function done(s) { stop(); say(s); img.style.opacity = .2; go.disabled = false; }
  function poll() {
    fetch('/auth/device/status', {credentials: 'same-origin'}).then(function (r) {
      return r.json().then(function (j) { return [r.status, j]; });
    }).then(function (a) {
      var j = a[1];
      if (a[0] === 429) { t = setTimeout(poll, 2000); return; }
      if (a[0] !== 200) { done('Kod nieaktualny. Wygeneruj nowy.'); return; }
      if (j.status === 'APPROVED') {
        say('Zatwierdzono \u2014 loguj\u0119\u2026');
        return fetch('/auth/device/claim', {method: 'POST', credentials: 'same-origin'}).then(function (r) {
          return r.json();
        }).then(function (c) {
          if (c.ok) { location.href = c.redirect || '/'; } else { done('Nie uda\u0142o si\u0119 odebra\u0107 dost\u0119pu. Spr\u00f3buj ponownie.'); }
        });
      }
      if (j.status === 'DENIED') { done('Odrzucono na telefonie.'); return; }
      if (j.status !== 'PENDING') { done('Kod wygas\u0142. Wygeneruj nowy.'); return; }
      say('Zeskanuj telefonem i zatwierd\u017a. Sprawd\u017a, czy kod si\u0119 zgadza. Zosta\u0142o ' + j.expires_in + ' s.');
      t = setTimeout(poll, 2000);
    }).catch(function () { t = setTimeout(poll, 3000); });
  }
  go.addEventListener('click', function () {
    stop(); go.disabled = true; say('Generuj\u0119 kod\u2026');
    fetch('/auth/device/start', {method: 'POST', credentials: 'same-origin'}).then(function (r) {
      return r.json().then(function (j) { return [r.status, j]; });
    }).then(function (a) {
      var j = a[1];
      if (a[0] !== 200) { done('Za du\u017co pr\u00f3b naraz. Odczekaj chwil\u0119.'); return; }
      box.style.display = 'block'; img.style.opacity = 1;
      img.innerHTML = j.qr_svg || '';
      cd.textContent = j.code;
      go.textContent = 'Nowy kod';
      poll();
    }).catch(function () { done('B\u0142\u0105d po\u0142\u0105czenia.'); });
  });
})();
</script>"""

# Strona wlasciciela /auth/sessions: lista aktywnych dostepow demo + konczenie.
SESSIONS_BODY = r"""<h1>Dostępy tymczasowe</h1>
<p class="muted">Aktywne sesje demo (tylko podgląd). Zakończenie działa od razu.</p>
<div id="list" class="muted">Ładowanie…</div>
<button class="no" id="all" type="button">Zakończ wszystkie</button>
<p class="muted" style="margin-top:1rem"><a href="/" style="color:#9fd3ff">Wróć</a></p>
<script>
(function () {
  var csrf = '';
  function rev(id) {
    fetch('/api/auth/sessions/revoke', {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: id, csrf: csrf})}).then(load, load);
  }
  function load() {
    fetch('/api/auth/sessions', {credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (j) {
      csrf = j.csrf; var L = document.getElementById('list'); L.innerHTML = '';
      if (!j.sessions.length) { L.textContent = 'Brak aktywnych dostępów.'; return; }
      j.sessions.forEach(function (s) {
        var d = document.createElement('div'); d.style.cssText = 'border-top:1px solid #333;padding:.6rem 0';
        var t = document.createElement('div'); t.className = 'muted';
        t.textContent = 'Do ' + new Date(s.expires_at).toLocaleTimeString('pl-PL', {hour: '2-digit', minute: '2-digit'}) +
          ' · ' + (s.device || 'nieznane urządzenie');
        var b = document.createElement('button'); b.className = 'no'; b.type = 'button'; b.textContent = 'Zakończ';
        b.addEventListener('click', function () { rev(s.id); });
        d.appendChild(t); d.appendChild(b); L.appendChild(d);
      });
    });
  }
  document.getElementById('all').addEventListener('click', function () { rev('all'); });
  load();
})();
</script>"""
