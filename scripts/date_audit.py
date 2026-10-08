#!/usr/bin/env python3
"""date_audit.py (2026-10-07) - szuka na stronach QBot Lab dat w STARYM formacie widocznych dla uzytkownika.

Format docelowy (decyzja uzytkownika): DD.MM i DD.MM.RRRR -- formatowanie w /opt/qbot/web/public/qdate.js (QD.*).
Wykrywa w WIDOCZNYM tekscie (tez napisy SVG na osiach, wybrana pozycja <select>): RRRR-MM-DD, MM-DD i daty z nazwa miesiaca (6 paź).
Pomija pola <input> (kalendarzyk systemowy) i ukryte elementy.

Uzycie (jedna strona na wywolanie - DEV MCP blokuje sie na dluzszych poleceniach):
    .venv/bin/python3 scripts/date_audit.py /forma.html
    .venv/bin/python3 scripts/date_audit.py /forma.html --click "#tabs button" --wait 1500
    --click CSS : po kolei klika KAZDY pasujacy element (np. zakladki) i audytuje po kazdym kliknieciu
    --theme dark|light (domyslnie dark)
Kod wyjscia: 0 = czysto, 1 = znaleziono stare daty.
"""
import argparse, os, sys
sys.path.insert(0, "/opt/qbot/app"); sys.path.insert(0, "/opt/qbot/app/scripts")
from dev_fetch import get_auth
from playwright.sync_api import sync_playwright

JS = r"""()=>{
 var ISO=/\b\d{4}-\d{2}-\d{2}\b/, MD=/(^|[^\d-])(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?![\d-])/,
     MN=/(^|[^\w])\d{1,2} (sty|lut|mar|kwi|maj|cze|lip|sie|wrz|paź|lis|gru)[a-ząćęłńóśźż]*\.?(?![\w])/i;
 function vis(e){ if(!e) return false; for(var x=e;x&&x.nodeType===1;x=x.parentElement){var c=getComputedStyle(x);if(c.display==='none'||c.visibility==='hidden')return false;} return e.getClientRects().length>0; }
 var out=[], w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null), n;
 while(n=w.nextNode()){ var p=n.parentElement, t=n.nodeValue; if(!p||!t||!t.trim()) continue;
   var tag=p.tagName; if(tag==='SCRIPT'||tag==='STYLE'||tag==='OPTION'||tag==='TEXTAREA') continue;
   if((ISO.test(t)||MD.test(t)||MN.test(t)) && vis(p)) out.push(tag.toLowerCase()+(p.id?'#'+p.id:'')+(p.className&&typeof p.className==='string'?'.'+p.className.split(' ')[0]:'')+': '+t.trim().slice(0,80)); }
 document.querySelectorAll('select').forEach(function(s){ if(!vis(s)) return; var o=s.options[s.selectedIndex]; if(o&&(ISO.test(o.text)||MD.test(o.text))) out.push('select#'+(s.id||'?')+': '+o.text.slice(0,80)); });
 return out; }"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url"); ap.add_argument("--click", default=None); ap.add_argument("--wait", type=int, default=1200)
    ap.add_argument("--theme", default="dark"); ap.add_argument("--width", type=int, default=1500)
    a = ap.parse_args()
    users, sv, mk = get_auth(); ck, _ = mk(sorted(users)[0], sv)
    found = 0
    with sync_playwright() as p:
        br = p.chromium.launch()
        c = br.new_context(viewport={"width": a.width, "height": 950})
        c.add_cookies([{"name": "qbot_session", "value": ck, "domain": "127.0.0.1", "path": "/"}])
        c.add_init_script("try{localStorage.setItem('qtheme','%s')}catch(e){}" % a.theme)
        pg = c.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:150]))
        pg.goto("http://127.0.0.1:30181" + a.url, wait_until="load", timeout=15000); pg.wait_for_timeout(a.wait + 1500)
        steps = [("(start)", None)]
        if a.click:
            n = pg.evaluate("s=>document.querySelectorAll(s).length", a.click)
            steps += [("klik %d" % i, i) for i in range(n)]
        for name, i in steps:
            if i is not None:
                lab = pg.evaluate("([s,i])=>{var e=document.querySelectorAll(s)[i];if(!e)return null;e.click();return (e.textContent||'').trim().slice(0,30)}", [a.click, i])
                pg.wait_for_timeout(a.wait); name = "%s [%s]" % (name, lab)
            hits = sorted(set(pg.evaluate(JS)))
            found += len(hits)
            print("== %s %s: %s" % (a.url, name, "OK" if not hits else "%d stare daty" % len(hits)))
            for h in hits[:25]: print("   ", h)
            if len(hits) > 25: print("    ... i %d wiecej" % (len(hits) - 25))
        if errs: print("BLEDY JS:", errs)
        br.close()
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
