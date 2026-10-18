#!/usr/bin/env python3
"""WIKI -- indeks wyszukiwania + odswiezenie podgladu.

1) Czyta metaznaczniki (YAML front matter) kazdego hasla docs/wiki/**/*.md i buduje docs/wiki/_indeks.json:
   sciezka, tytul, dzial, typ, opis, tagi, synonimy, skroty, gdzie_widac, zalezy_od, wplywa_na, naglowki, tekst (bez znacznikow).
2) Kopiuje wiki do /opt/qbot/web/public/wiki-podglad/ i zapisuje czytnik index.html (tymczasowy PODGLAD do przegladu,
   nie docelowa strona /wiki.html -- ta idzie najpierw przez makiete na kanwie Design).
Uzycie: .venv/bin/python3 scripts/wiki_bg/build_index.py
"""
import json, os, re, shutil, time

SRC = "/opt/qbot/app/docs/wiki"
DST = "/opt/qbot/web/public/wiki-dane"  # dane dla /wiki.html (md + _indeks.json + img); stary podglad: wiki-podglad
LIST_KEYS = ("tagi", "synonimy", "skroty", "gdzie_widac", "zalezy_od", "wplywa_na", "liczby", "zrodla_kodu")


def parse_fm(txt):
    """Prosty parser front matter (klucz: wartosc / klucz: [a, b] / lista '- x'). Bez zaleznosci od PyYAML."""
    if not txt.startswith("---\n"):
        return {}, txt
    end = txt.find("\n---", 4)
    if end < 0:
        return {}, txt
    fm, body = txt[4:end], txt[end + 4:].lstrip("\n")
    meta, key = {}, None
    for ln in fm.splitlines():
        if re.match(r"^\s+-\s+", ln) and key:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(ln.split("-", 1)[1].strip().strip("'\""))
            continue
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", ln)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        elif val == "":
            meta[key] = []
        else:
            meta[key] = val.strip("'\"")
    return meta, body


def plain(md):
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"[#>*_`|<>-]", " ", md)
    return re.sub(r"\s+", " ", md).strip()


def build():
    items, missing = [], []
    for d, _, fs in os.walk(SRC):
        if "/_work" in d or "/img" in d:
            continue
        for f in sorted(fs):
            if not f.endswith(".md") or f.startswith("_"):
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, SRC)
            meta, body = parse_fm(open(p, encoding="utf-8").read())
            if not meta:
                missing.append(rel)
            h1 = re.search(r"^#\s+(.+)$", body, re.M)
            it = {
                "p": rel,
                "tytul": meta.get("tytul") or (h1.group(1).strip() if h1 else rel),
                "dzial": meta.get("dzial") or (rel.split("/")[0] if "/" in rel else "ogolne"),
                "typ": meta.get("typ", ""),
                "opis": meta.get("opis", ""),
                "naglowki": re.findall(r"^##+\s+(.+)$", body, re.M),
                "tekst": plain(body)[:6000],
            }
            for k in LIST_KEYS:
                v = meta.get(k, [])
                it[k] = v if isinstance(v, list) else [v]
            items.append(it)
    idx = {"zbudowano": time.strftime("%d.%m.%Y %H:%M"), "hasel": len(items), "bez_metaznacznikow": missing, "hasla": items}
    with open(os.path.join(SRC, "_indeks.json"), "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False)
    return idx


VIEWER = r"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wiki QBot — podgląd szkicu</title>
<style>
:root{--bg:#fff;--fg:#1d2329;--mut:#6b7480;--line:#e3e6ea;--acc:#2f6fd6;--code:#f4f6f8}
@media (prefers-color-scheme:dark){:root{--bg:#14181c;--fg:#e6e9ec;--mut:#9aa3ad;--line:#2a3138;--acc:#6ea2ff;--code:#1d2328}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}
.bar{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;z-index:5}
.bar a{color:var(--acc);text-decoration:none}.bar span{color:var(--mut);font-size:13px}
#q{flex:1;min-width:180px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font-size:15px}
#res{max-width:860px;margin:0 auto;padding:0 18px}#res a{display:block;padding:8px 0;border-bottom:1px solid var(--line);text-decoration:none;color:var(--fg)}
#res b{color:var(--acc)}#res small{color:var(--mut)}
.meta{color:var(--mut);font-size:13px;margin:-6px 0 12px}.meta span{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 8px;margin:2px 4px 2px 0}
main{max-width:860px;margin:0 auto;padding:16px 18px 80px}
a{color:var(--acc)}img{max-width:100%;border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;display:block;overflow-x:auto}td,th{border:1px solid var(--line);padding:4px 8px}
code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:.9em}pre{background:var(--code);padding:10px;overflow-x:auto}
blockquote{border-left:4px solid #e0a020;margin:0;padding:4px 12px;background:var(--code)}
.mermaid{background:#fff;border-radius:6px;padding:8px;overflow-x:auto}
</style></head><body>
<div class="bar"><a href="?p=README.md">🏠 Wiki</a><a href="?p=mapa-serwisu.md">Mapa</a><a href="?p=zaleznosci.md">Zależności</a><a href="?p=slowniczek.md">Słowniczek</a>
<input id="q" type="search" placeholder="Szukaj: np. świeżość, W'bal, wiatr, opony…" autocomplete="off"><span id="cur"></span></div>
<div id="res"></div><main id="c">Ładowanie…</main>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({startOnLoad:false,theme:'default'});
let IDX=[];fetch('_indeks.json?t='+Date.now()).then(r=>r.json()).then(j=>{IDX=j.hasla||[]});
const fold=s=>(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ł/g,'l');
function search(q){const t=fold(q).split(/\s+/).filter(Boolean);if(!t.length)return[];
  return IDX.map(h=>{let s=0;const T=fold(h.tytul),M=fold([...h.synonimy,...h.skroty,...h.tagi].join(' ')),O=fold(h.opis),X=fold(h.naglowki.join(' ')+' '+h.tekst);
    for(const w of t){let ok=0;if(T.includes(w)){s+=10;ok=1}if(M.includes(w)){s+=8;ok=1}if(O.includes(w)){s+=4;ok=1}if(X.includes(w)){s+=1;ok=1}if(!ok)return null}
    return{h,s}}).filter(Boolean).sort((a,b)=>b.s-a.s).slice(0,25)}
document.getElementById('q').addEventListener('input',e=>{const r=search(e.target.value),el=document.getElementById('res');
  el.innerHTML=r.map(({h})=>`<a href="?p=${encodeURIComponent(h.p)}"><b>${h.tytul}</b> <small>· ${h.dzial}${h.typ?' · '+h.typ:''}</small><br><small>${h.opis||''}</small></a>`).join('')||(e.target.value?'<small>Brak wyników</small>':'')});
function norm(base,rel){const a=base.split('/');a.pop();for(const s of rel.split('/')){if(s==='..')a.pop();else if(s&&s!=='.')a.push(s)}return a.join('/')}
function stripFm(t){if(!t.startsWith('---\n'))return[t,''];const e=t.indexOf('\n---',4);return e<0?[t,'']:[t.slice(e+4),t.slice(4,e)]}
async function show(p){
  document.getElementById('cur').textContent=p;document.getElementById('res').innerHTML='';document.getElementById('q').value='';
  const r=await fetch(p+'?t='+Date.now());const c=document.getElementById('c');
  if(!r.ok){c.textContent='Brak pliku: '+p;return}
  const [body]=stripFm(await r.text());c.innerHTML=marked.parse(body);
  const h=IDX.find(x=>x.p===p);if(h){const m=document.createElement('div');m.className='meta';
    m.innerHTML=[...h.tagi,...h.synonimy].map(x=>`<span>${x}</span>`).join('');const h1=c.querySelector('h1');if(h1)h1.after(m)}
  c.querySelectorAll('code.language-mermaid').forEach(e=>{const d=document.createElement('div');d.className='mermaid';d.textContent=e.textContent;e.parentElement.replaceWith(d)});
  c.querySelectorAll('img').forEach(i=>{const s=i.getAttribute('src');if(s&&!/^(https?:|data:|\/)/.test(s))i.src=norm(p,s)});
  c.querySelectorAll('a').forEach(a=>{const h=a.getAttribute('href');if(!h||/^(https?:|#|mailto:)/.test(h))return;const t=norm(p,h.split('#')[0]);
    if(t.endsWith('.md')){a.href='?p='+encodeURIComponent(t)}else a.href=t});
  try{await mermaid.run({querySelector:'.mermaid'})}catch(e){}
  window.scrollTo(0,0);
}
setTimeout(()=>show(new URLSearchParams(location.search).get('p')||'README.md'),150);
</script></body></html>"""


def publish():
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("_work"))
    with open(os.path.join(DST, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(VIEWER)


if __name__ == "__main__":
    i = build()
    publish()
    print(f"hasel {i['hasel']}, bez metaznacznikow {len(i['bez_metaznacznikow'])}")
