#!/usr/bin/env python3
"""Diety od Brokula - sesja (ciasteczka) i pobieranie stron panelu klienta.

Logowanie haslem NIE jest mozliwe: formularz chroni niewidoczna reCAPTCHA
(sprawdzone 12.10.2026, odpowiedz 'Cos poszlo nie tak z reCAPTCHA'). Dlatego
uzytkownik loguje sie w przegladarce i wkleja naglowek Cookie na /brokul-dostep.

Zasady (jak komoot_session_admin):
- zapis do .brokul_session WYLACZNIE po udanym tescie (panel nie przekierowuje na logowanie),
- zadna wartosc ciasteczka nie jest zwracana, wypisywana ani logowana,
- po kazdym udanym odczycie odswiezone ciasteczka (Set-Cookie) wracaja do pliku,
  wiec regularny odczyt (keepalive) przedluza zycie sesji.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

import httpx

BASE = "https://dietyodbrokula.pl"
SESSION_FILE = Path("/opt/qbot/app/.brokul_session")
STATE_FILE = Path("/opt/qbot/app/data/brokul_state.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")
NEEDED = ("PHPSESSID",)
# ciasteczka Cloudflare sa przypiete do IP/przegladarki - z serwera tylko szkodza
_DROP = ("cf_clearance", "__cf_bm", "_cfuvid")
MENU_RE = re.compile(r"/customer/diets/menu/item/(\d+)")


class SessionInputError(ValueError):
    """Wklejony tekst nie zawiera potrzebnych ciasteczek."""


class SessionExpired(RuntimeError):
    """Brokul przekierowal na strone logowania - sesja nie dziala."""


# ---------------------------------------------------------------- ciasteczka
def parse_cookie_header(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    jar = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k and k not in _DROP:
            jar[k] = v
    if not jar:
        raise SessionInputError("nie rozpoznano zadnego ciasteczka")
    brak = [k for k in NEEDED if not jar.get(k)]
    if brak:
        raise SessionInputError("brakuje ciasteczka: %s - skopiuj naglowek Cookie po zalogowaniu"
                                % ", ".join(brak))
    return jar


def _load_jar() -> dict:
    if not SESSION_FILE.exists():
        raise FileNotFoundError("brak pliku sesji")
    return json.loads(SESSION_FILE.read_text(encoding="utf-8"))


def _fix_owner(path) -> None:
    """Cron moze chodzic jako root - pliki musza nalezec do qbot (czyta je qbot-web)."""
    try:
        if os.geteuid() == 0:
            import pwd
            pw = pwd.getpwnam("qbot")
            os.chown(path, pw.pw_uid, pw.pw_gid)
    except Exception:
        pass


def _save_jar(jar: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".brokul_tmp_", dir=str(SESSION_FILE.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(jar, f)
    os.chmod(tmp, 0o600)
    _fix_owner(tmp)
    os.replace(tmp, SESSION_FILE)


def _state_update(**kw) -> None:
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except Exception:
        st = {}
    st.update(kw)
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    _fix_owner(STATE_FILE)


def state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------- pobieranie
def _client(jar: dict) -> httpx.Client:
    c = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"},
                     follow_redirects=True, timeout=15)
    for k, v in jar.items():
        c.cookies.set(k, v, domain="dietyodbrokula.pl")
    return c


def _jar_from(c: httpx.Client, old: dict) -> dict:
    new = dict(old)
    for ck in c.cookies.jar:
        if ck.name in _DROP or not ck.value:
            continue
        new[ck.name] = ck.value
    return new


def _get(jar: dict, path: str) -> tuple[str, dict]:
    """GET strony panelu. Zwraca (html, odswiezony_jar). Rzuca SessionExpired."""
    with _client(jar) as c:
        r = c.get(BASE + path)
        if "/customer/account/login" in str(r.url):
            raise SessionExpired("Brokul przekierowal na logowanie")
        r.raise_for_status()
        return r.text, _jar_from(c, jar)


def fetch(path: str) -> str:
    """Odczyt strony z zapisana sesja; odswiezone ciasteczka wracaja do pliku."""
    jar = _load_jar()
    try:
        html, jar2 = _get(jar, path)
    except SessionExpired:
        _state_update(alive=False, expired_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        raise
    _save_jar(jar2)
    _state_update(alive=True, last_ok=time.strftime("%Y-%m-%d %H:%M:%S"))
    return html


def menu_ids(html: str) -> list[str]:
    return sorted(set(MENU_RE.findall(html or "")), key=int)


# ---------------------------------------------------------------- web / status
def store_session(raw: str) -> dict:
    """Test na zywo i zapis. Zwraca {'ok': True, 'menu_ids': [...]}."""
    jar = parse_cookie_header(raw)
    html, jar2 = _get(jar, "/customer/diets/")
    _save_jar(jar2)
    ids = menu_ids(html)
    _state_update(alive=True, last_ok=time.strftime("%Y-%m-%d %H:%M:%S"),
                  stored_at=time.strftime("%Y-%m-%d %H:%M:%S"), expired_at=None,
                  expired_notified=None)
    return {"ok": True, "menu_ids": ids}


def status(live: bool = True) -> dict:
    """Stan sesji do strony. Nigdy nie rzuca, nie zwraca wartosci ciasteczek."""
    st = state()
    out = {"alive": False, "detail": "", "menu_ids": [], "stored_at": st.get("stored_at"),
           "last_ok": st.get("last_ok")}
    if not SESSION_FILE.exists():
        out["detail"] = "brak sesji - wklej ciasteczka"
        return out
    if not live:
        out["alive"] = bool(st.get("alive"))
        out["detail"] = "bez testu na zywo"
        return out
    try:
        out["menu_ids"] = menu_ids(fetch("/customer/diets/"))
        out["alive"] = True
        out["detail"] = "sesja zywa"
    except SessionExpired:
        out["detail"] = "sesja wygasla - zaloguj sie w przegladarce i wklej nowe ciasteczka"
    except Exception as e:
        out["detail"] = "blad polaczenia z Brokulem: %s" % type(e).__name__
    return out


FORM_HTML = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sesja Brokul - QBot</title>
<style>
 body{background:#14161a;color:#e8e8e8;font:16px/1.5 system-ui,sans-serif;margin:0;padding:24px}
 .box{max-width:620px;margin:0 auto}
 h1{font-size:20px;margin:0 0 4px}
 p{color:#9aa0a8;font-size:14px;margin:0 0 16px}
 textarea{width:100%;box-sizing:border-box;padding:14px;height:120px;resize:vertical;
      font:13px monospace;background:#1e2126;color:#e8e8e8;border:1px solid #333;border-radius:8px}
 button{width:100%;margin-top:12px;padding:14px;font-size:16px;font-weight:600;
       background:#4f9a3a;color:#fff;border:0;border-radius:8px}
 button:disabled{opacity:.5}
 #out{margin-top:18px;padding:14px;border-radius:8px;font-size:14px;display:none;white-space:pre-wrap}
 #stan{margin:0 0 18px;padding:12px 14px;border-radius:8px;font-size:14px;
      background:#1e2126;border:1px solid #333;white-space:pre-wrap}
 .ok{background:#14331e;border:1px solid #2c6b3f}
 .err{background:#3a1a1a;border:1px solid #7a2b2b}
 ol{color:#9aa0a8;font-size:13px;padding-left:20px}
 code{background:#1e2126;padding:1px 5px;border-radius:4px}
</style></head><body><div class="box">
<h1>Sesja Diety od Brokula</h1>
<p>QBot pobiera Twoj jadlospis z panelu klienta Brokula. Logowania nie da sie
zautomatyzowac (reCAPTCHA), wiec QBot korzysta z Twojej sesji z przegladarki.
Gdy wygasnie, dostaniesz wiadomosc na Telegramie z linkiem tutaj.</p>
<div id="stan">Sprawdzam stan sesji...</div>
<textarea id="ck" placeholder="wklej tutaj caly naglowek Cookie" autocomplete="off"
 autocapitalize="off" spellcheck="false"></textarea>
<button id="go">Sprawdz i zapisz</button>
<div id="out"></div>
<ol>
<li>Otworz <code>dietyodbrokula.pl</code> w przegladarce i zaloguj sie.</li>
<li>Wejdz w <code>Moje konto</code> - <code>Moje diety</code>.</li>
<li>Wcisnij F12 (Mac: Option+Cmd+I) - panel developerski.</li>
<li>Zakladka <code>Network</code>, potem odswiez strone (F5 / Cmd+R).</li>
<li>Kliknij pierwsze zadanie z listy (dokument strony).</li>
<li>Sekcja <code>Request Headers</code>, linia <code>Cookie:</code> - skopiuj CALA wartosc i wklej wyzej.</li>
</ol>
<p>Ciasteczka sa najpierw testowane u Brokula, zapisywane dopiero po udanym
tescie. Nic nie trafia do logow.</p>
</div><script>
const out=document.getElementById('out'),btn=document.getElementById('go'),
      inp=document.getElementById('ck'),stan=document.getElementById('stan');
const NL=String.fromCharCode(10);
function fmt(s){if(!s)return '-';const m=s.match(/^(\\d{4})-(\\d\\d)-(\\d\\d) (\\d\\d:\\d\\d)/);return m?m[3]+'.'+m[2]+'.'+m[1]+' '+m[4]:s;}
async function odswiezStan(){
  try{
    const r=await fetch('/api/brokul/session/status',{credentials:'same-origin'});
    const j=await r.json();
    const linie=[j.alive?'Sesja zywa':'Sesja NIE dziala: '+(j.detail||'?')];
    if(j.alive){linie.push('Menu w panelu: '+(j.menu_ids.length?j.menu_ids.join(', '):'nie znaleziono linku do menu'));}
    linie.push('Wklejona: '+fmt(j.stored_at)+'  |  ostatni udany odczyt: '+fmt(j.last_ok));
    stan.textContent=linie.join(NL);
    stan.className=j.alive?'ok':'err';
  }catch(e){stan.textContent='Nie udalo sie sprawdzic stanu: '+e;stan.className='err';}
}
odswiezStan();
btn.onclick=async()=>{
  const v=inp.value.trim();
  out.style.display='block';
  if(!v){out.className='err';out.textContent='Puste pole.';return;}
  btn.disabled=true;out.className='';out.textContent='Sprawdzam u Brokula...';
  try{
    const r=await fetch('/api/brokul/session',{
      method:'POST',headers:{'Content-Type':'application/json'},
      credentials:'same-origin',body:JSON.stringify({cookie:v})});
    const j=await r.json();
    if(r.ok&&j.ok){
      out.className='ok';
      out.textContent=['OK - sesja zapisana.',
        'Menu w panelu: '+(j.menu_ids.length?j.menu_ids.join(', '):'nie znaleziono linku do menu')].join(NL);
      inp.value='';
      odswiezStan();
    }else{
      out.className='err';
      out.textContent='Odrzucone: '+(j.detail||r.status);
    }
  }catch(e){out.className='err';out.textContent='Blad polaczenia: '+e;}
  btn.disabled=false;
};
</script></body></html>"""
