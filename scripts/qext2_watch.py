#!/usr/bin/env python3
"""qext2_watch.py (2026-10-18, decyzje Michala) — automat: kazda zmiana w QExt2 trafia do LOGU ZMIAN i do SYMULATORA.

Uruchamiany co 10 min z qbot-web (watek qbot-qext2-watch -> ten skrypt jako osobny proces, uzytkownik qbot).
NIE uruchamiac jako root (pliki w qext2-sim/ i stan musza nalezec do qbot).

Co robi:
 1. Czyta nowe commity repo QExt2 (/opt/qbot/qext2_deploy, tylko odczyt git) od ostatnio widzianego. Start logu = commit
    biezacy w chwili wlaczenia (wczesniejszych nie dociaga).
 2. Kazdy commit -> wpis logu: data, sha, numer buildu (tag build-N, gdy serwer go zna — QBot nie pobiera tagow z GitHuba),
    zmienione pliki, opis po polsku (AI na podstawie tematu i fragmentu roznicy; zapas: temat commitu).
 3. WYGLAD: commit zmienia rysowanie pol (Kokpit2.kt -> qext2-kokpit2.js, StatsV2Renderer.kt -> qext2-stats.js) -> AI przenosi
    roznice do portu JS (edycje "zamien dokladny tekst").
 4. DANE (decyzja 18.10): commit dodaje nowe pola do danych pola (KokpitNavData, KokpitInstData, StatsV2Data, DynItem, InfoWx,
    WxItem) -> AI dopisuje je do symulacji jazdy (qext2-makieta.js) z PRZYKLADOWYM zachowaniem (oznaczone w kodzie).
 5. Test: node --check + test dymny (wszystkie scenariusze, trzy ekrany) + kazde nowe pole ma wartosc w symulacji.
    OK -> nowa wersja symulatora dla commitu. Blad -> wpis "wyglad z poprzedniego buildu" + powiadomienie (dzwonek + Telegram).
    Commit bez zmian wygladu i danych -> ten sam symulator co poprzedni.
Wyniki: /opt/qbot/web/public/qext2-sim/builds.json (log), /opt/qbot/web/public/qext2-sim/<sha7>/ (qext2-kokpit2.js,
qext2-stats.js, qext2-makieta.js). Stan: /opt/qbot/app/data/qext2_watch_state.json. Dok.: docs/QEXT2_SYMULATOR.md.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = "/opt/qbot/qext2_deploy"
PUB = Path("/opt/qbot/web/public")
SIM = PUB / "qext2-sim"
STATE = Path("/opt/qbot/app/data/qext2_watch_state.json")
LOCK = Path("/opt/qbot/app/data/qext2_watch.lock")
KT = "app/src/main/kotlin/com/qext2/primary/"
RENDER = {  # plik Kotlin rysujacy pola -> plik portu JS
    KT + "kokpit/Kokpit2.kt": "qext2-kokpit2.js",
    KT + "statsv2/StatsV2Renderer.kt": "qext2-stats.js",
}
JS_FILES = ["qext2-kokpit2.js", "qext2-stats.js"]
SIM_JS = "qext2-makieta.js"
# klasa danych pola -> (plik Kotlin, gdzie w symulacji: funkcja/obiekt w qext2-makieta.js)
DATA = {
    "KokpitNavData": (KT + "kokpit/KokpitNavRenderer.kt", "navData"),
    "DynItem": (KT + "kokpit/KokpitNavRenderer.kt", "dyn"),
    "KokpitInstData": (KT + "kokpit/KokpitInstRenderer.kt", "instrData"),
    "StatsV2Data": (KT + "statsv2/StatsV2Renderer.kt", "statsData"),
    "InfoWx": (KT + "info/InfoWeather.kt", "wx"),
    "WxItem": (KT + "info/InfoWeather.kt", "wxItem"),
}
DATA_FILES = {v[0] for v in DATA.values()}
sys.path.insert(0, "/opt/qbot/app")


def git(*a: str) -> str:
    r = subprocess.run(["git", "-c", "safe.directory=" + REPO, "-C", REPO] + list(a), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(a[:2]), r.stderr.strip()[:300]))
    return r.stdout


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(p: Path, obj) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def build_no(sha: str) -> int | None:
    try:
        tags = git("tag", "--points-at", sha).split()
    except Exception:
        return None
    nums = [int(t[6:]) for t in tags if re.fullmatch(r"build-\d+", t)]
    return max(nums) if nums else None


def commit_info(sha: str) -> dict:
    head = git("show", "-s", "--date=format:%Y-%m-%d %H:%M", "--format=%H%n%ad%n%s%n%b", sha).split("\n", 3)
    files = [f for f in git("show", "--name-only", "--format=", sha).splitlines() if f.strip()]
    try:
        diff = git("show", "--format=", "--unified=1", sha)[:3000]
    except Exception:
        diff = ""
    return {"sha": head[0], "sha7": head[0][:7], "date": head[1], "subject": head[2], "body": (head[3] if len(head) > 3 else "").strip()[:1500],
            "files": files, "diff": diff}


# ---------------------------------------------------------------- pola danych (klasy danych Kotlin)
def data_fields(sha: str, path: str, cls: str) -> dict | None:
    """{nazwa_pola: deklaracja} z `data class Cls(...)` w pliku na danym commicie; None = brak pliku/klasy."""
    try:
        src = git("show", "%s:%s" % (sha, path))
    except Exception:
        return None
    i = src.find("data class %s(" % cls)
    if i < 0:
        return None
    j = src.index("(", i); depth = 0; k = j
    while k < len(src):
        if src[k] == "(":
            depth += 1
        elif src[k] == ")":
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = re.sub(r"/\*.*?\*/", "", src[j + 1:k], flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return {m.group(1): m.group(0).strip().rstrip(",") for m in re.finditer(r"\bval\s+(\w+)\s*:\s*[^,\n]+", body)}


def added_fields(a: str, b: str) -> dict:
    """Nowe pola klas danych miedzy commitami a -> b: {klasa: {"where": ..., "fields": {nazwa: deklaracja}}}."""
    out = {}
    for cls, (path, where) in DATA.items():
        fa, fb = data_fields(a, path, cls), data_fields(b, path, cls)
        if fa is None or fb is None:
            continue
        new = {n: d for n, d in fb.items() if n not in fa}
        if new:
            out[cls] = {"where": where, "fields": new}
    return out


# ---------------------------------------------------------------- AI
def _llm(prompt: str, system: str, max_tokens: int) -> str:
    import qgpt_client as Q
    if getattr(Q, "ANTHROPIC_API_KEY", None):
        try:
            return Q._anthropic_text([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens, temperature=0)
        except Exception as e:  # noqa
            print("anthropic:", e)
    return Q.qgpt_text(prompt, system=system, max_tokens=max_tokens, temperature=0)


def summarize(ci: dict) -> str:
    try:
        txt = _llm(
            "Commit w aplikacji QExt2 (pola danych na liczniku rowerowym Karoo). Napisz po polsku, prostym jezykiem dla hobbysty"
            " (nie programisty), CO zmienilo sie dla jezdzca: 1-3 krotkie zdania, bez nazw plikow i funkcji. Gdy zmiana jest tylko"
            " techniczna/wewnetrzna, napisz to jednym zdaniem. Nie zgaduj: opieraj sie na temacie i fragmencie roznicy; gdy cos"
            " jest niejasne, opisz to ogolniej zamiast dopowiadac.\n\nTemat: %s\nOpis: %s\nZmienione pliki:\n%s\n\nFragment roznicy:\n%s"
            % (ci["subject"], ci["body"], "\n".join(ci["files"][:30]), ci.get("diff", "")),
            "Piszesz zwiezle notatki do dziennika zmian. Tylko tresc, bez wstepu.", 400)
        return re.sub(r"\s+", " ", txt).strip()[:600]
    except Exception as e:  # noqa
        print("opis AI:", e)
        return ci["subject"]


def _apply(path: Path, raw: str, label: str) -> tuple[bool, str]:
    o, dec = None, json.JSONDecoder()
    for i in [k for k, ch in enumerate(raw) if ch == "{"][:200]:   # pierwszy poprawny obiekt JSON z kluczem "edits"
        try:
            cand, _ = dec.raw_decode(raw[i:])
        except Exception:
            continue
        if isinstance(cand, dict) and "edits" in cand:
            o = cand
            break
    if o is None:
        return False, "AI nie zwrocilo poprawnego JSON (%s): %r" % (label, raw[:160])
    cur = path.read_text(encoding="utf-8")
    for ed in o.get("edits") or []:
        if ed.get("file") not in (None, path.name):
            continue
        old, new = ed.get("old") or "", ed.get("new") or ""
        if old and cur.count(old) == 1:
            cur = cur.replace(old, new)
            continue
        # 2026-10-19: AI czesto myli wciecia/odstepy -- szukaj tego samego tekstu z dowolnymi bialymi znakami (dokladnie 1 miejsce)
        hits = list(re.finditer(r"\s+".join(re.escape(t) for t in old.split()), cur)) if old.strip() else []
        if len(hits) != 1:
            return False, "edycja nie pasuje do %s (wystapien: %d): %r" % (path.name, len(hits) if old else 0, old[:80])
        cur = cur[:hits[0].start()] + new + cur[hits[0].end():]
    path.write_text(cur, encoding="utf-8")
    return True, str(o.get("uwagi") or "")[:300]


PORT_SYS = ("Przenosisz zmiany z kodu Kotlin (Android Canvas) rysujacego pola licznika Karoo do istniejacego portu JavaScript"
            " (HTML canvas, ta sama geometria 1:1). Zwracasz TYLKO JSON: {\"edits\":[{\"file\":\"...\",\"old\":\"...\",\"new\":\"...\"}],"
            "\"uwagi\":\"...\"}. 'old' musi wystepowac w pliku JS DOKLADNIE raz (skopiuj znak w znak, z wcieciami). Zmieniaj tylko to,"
            " co wynika z roznicy Kotlina. Gdy zmiana Kotlina nie wplywa na wyglad (np. tylko wydajnosc, komentarze) - pusta lista edits.")

SIM_SYS = ("Dopisujesz do symulatora jazdy (plik qext2-makieta.js, przegladarka) NOWE POLA DANYCH, ktore aplikacja QExt2 dodala do"
           " danych pola licznika Karoo. Symulator buduje dane funkcjami: navData() (KokpitNavData), instrData() (KokpitInstData),"
           " statsData() (StatsV2Data), dynItem() (DynItem, pole 'dyn' w navData), buildInfoWx() (InfoWx; jego 'items' to WxItem)."
           " Stan jazdy jest w obiekcie S (S.km, S.total, S.t [s], S.moving, S.P [W], S.v [m/s], S.hr, S.w [J W'], S.gr [%], S.hs [m/s],"
           " S.sc = scenariusz z polami temp, ws, wx...). Dla KAZDEGO nowego pola dodaj klucz o tej samej nazwie do obiektu zwracanego"
           " przez wlasciwa funkcje, z wiarygodna wartoscia PRZYKLADOWA zgodna z typem z deklaracji Kotlin (Int -> Math.round, Float ->"
           " liczba, String, Boolean, List -> tablica) i zmieniajaca sie sensownie w trakcie jazdy, gdy to ma sens. Przy kazdym dodanym"
           " kluczu komentarz /* przykladowe (auto) */. Nie zmieniaj niczego innego. Zwracasz TYLKO JSON:"
           " {\"edits\":[{\"old\":\"...\",\"new\":\"...\"}],\"uwagi\":\"...\"}; 'old' wystepuje w pliku DOKLADNIE raz.")


def port(prev_dir: Path, new_dir: Path, sha_from: str, sha_to: str, changed: list[str], added: dict) -> tuple[bool, str]:
    """Nowa wersja symulatora w new_dir (kopia prev_dir): AI przenosi wyglad (changed) i dopisuje nowe dane (added); test."""
    new_dir.mkdir(parents=True, exist_ok=True)
    for f in JS_FILES:
        shutil.copy2(prev_dir / f, new_dir / f)
    shutil.copy2(prev_dir / SIM_JS if (prev_dir / SIM_JS).exists() else PUB / SIM_JS, new_dir / SIM_JS)
    notes = []
    for kt in changed:
        js = RENDER[kt]
        diff = git("diff", sha_from, sha_to, "--", kt)
        if len(diff) > 60000:
            return False, "roznica %s za duza do automatycznego przeniesienia (%d znakow)" % (kt.rsplit("/", 1)[-1], len(diff))
        err = ""
        for _try in range(3):   # 2026-10-19: do 3 prob; kolejna dostaje blad poprzedniej
            cur = (new_dir / js).read_text(encoding="utf-8")
            ok, msg = _apply(new_dir / js, _llm("PLIK JS: %s\n-----\n%s\n-----\nROZNICA KOTLIN (%s):\n%s%s" % (js, cur, kt.rsplit("/", 1)[-1], diff,
                ("\n-----\nPOPRZEDNIA PROBA NIEUDANA: %s\nPlik JS moze sie roznic od Kotlina (wczesniejsze reczne poprawki) -- znajdz w PLIKU JS"
                 " miejsce odpowiadajace zmienianemu fragmentowi i skopiuj 'old' znak w znak z pliku JS powyzej." % err) if err else ""),
                PORT_SYS, 8000), js)
            if ok:
                break
            err = msg
        if not ok:
            return False, msg
        if msg:
            notes.append("wyglad: " + msg)
    if added:
        cur = (new_dir / SIM_JS).read_text(encoding="utf-8")
        spec = json.dumps(added, ensure_ascii=False, indent=1)
        ok, msg = _apply(new_dir / SIM_JS, _llm("NOWE POLA (klasa Kotlin -> gdzie w symulatorze -> deklaracje):\n%s\n-----\nPLIK %s:\n%s"
                                                % (spec, SIM_JS, cur), SIM_SYS, 6000), SIM_JS)
        if not ok:
            return False, "dane: " + msg
        notes.append("nowe dane (wartosci przykladowe): " + ", ".join("%s.%s" % (c, n) for c, v in added.items() for n in v["fields"])
                     + ((" — " + msg) if msg else ""))
    ok, msg = smoke(new_dir, added)
    return ok, ("; ".join(notes) + (" | " if notes else "") + msg)


SMOKE_JS = r'''
const fs=require("fs"), DIR=process.argv[1], REQ=JSON.parse(process.argv[2]||"{}");
function ctx(){const c={font:"",calls:0,measureText:(s)=>({width:(parseFloat((c.font.match(/(\d+(\.\d+)?)px/)||[0,10])[1]))*0.5*s.length}),createLinearGradient:()=>({addColorStop(){}})};
 ["save","restore","scale","translate","rotate","fillRect","fillText","beginPath","moveTo","lineTo","closePath","fill","stroke","arc","ellipse","bezierCurveTo","quadraticCurveTo","rect","roundRect","setTransform","setLineDash","strokeRect"].forEach(m=>c[m]=function(){c.calls++;});return c;}
function el(id){return {id,style:{},children:[],parentNode:{clientWidth:1500},classList:{toggle(){},add(){}},appendChild(ch){this.children.push(ch);},getContext(){return this._c||(this._c=ctx());},textContent:"",value:"",getAttribute(k){return this._a?this._a[k]:undefined;},querySelectorAll(){return this.children.filter(x=>x._a&&x._a["data-x"]);}};}
const els={}; global.window=global; global.parent=global; global.devicePixelRatio=2; global.Path2D=function(d){}; global.location={origin:"x",search:""};
global.addEventListener=()=>{}; global.fetch=()=>new Promise(()=>{});
global.document={getElementById:(id)=>els[id]||(els[id]=el(id)),createElement:(t)=>el(t),fonts:{add(){}},querySelectorAll:()=>[],documentElement:{scrollHeight:900},body:el("body")};
let iv=null; global.setInterval=(f)=>{iv=f;return 0;};
const sim=els["sim"]=el("sim"); [1,5,20].forEach(x=>{const b=el("b");b._a={"data-x":String(x)};sim.children.push(b);});
eval(fs.readFileSync(DIR+"/qext2-kokpit2.js","utf8")); eval(fs.readFileSync(DIR+"/qext2-stats.js","utf8"));
eval(fs.readFileSync(fs.existsSync(DIR+"/qext2-makieta.js")?DIR+"/qext2-makieta.js":"/opt/qbot/web/public/qext2-makieta.js","utf8"));
setTimeout(()=>{ sim.children[2].onclick(); let n=0; const seen={};
  for(const b of els["scen"].children){ b.onclick(); for(let k=0;k<8;k++){ if(iv) iv(); } els["cvInfo"].onclick(); n++;
    const H=global.__QEXT2_SIM; if(!H) continue;
    const src={navData:H.navData(), instrData:H.instrData(), statsData:H.statsData(), wx:H.wx()};
    src.dyn=src.navData&&src.navData.dyn; src.wxItem=src.wx&&src.wx.items&&src.wx.items[0];
    for(const c in REQ){ const o=src[REQ[c].where]; if(!o) continue; for(const f in REQ[c].fields){ if(o[f]!==undefined&&o[f]!==null) seen[c+"."+f]=1; } } }
  if(n<5 || !els["cvNav"]._c || !els["cvStats"]._c || !els["cvInfo"]._c) { console.log("ZA_MALO "+n); process.exit(2); }
  const miss=[]; for(const c in REQ) for(const f in REQ[c].fields) if(!seen[c+"."+f]) miss.push(c+"."+f);
  if(miss.length){ console.log("BRAK_DANYCH "+miss.join(",")); process.exit(3); }
  console.log("OK "+n); },50);
'''


def smoke(d: Path, req: dict | None = None) -> tuple[bool, str]:
    node = shutil.which("node") or "/usr/bin/node"
    for f in JS_FILES + ([SIM_JS] if (d / SIM_JS).exists() else []):
        r = subprocess.run([node, "--check", str(d / f)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, "skladnia %s: %s" % (f, r.stderr.strip()[:300])
    r = subprocess.run([node, "-e", SMOKE_JS, str(d), json.dumps(req or {})], capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or "OK" not in r.stdout:
        return False, "test symulatora: %s" % ((r.stdout + r.stderr).strip()[-400:])
    return True, "test symulatora: " + r.stdout.strip()


def notify(title: str, body: str, key: str) -> None:
    try:
        import qbot_notif as N
        from fitmodel.api import _db_connect
        conn = _db_connect()
        try:
            cur = conn.cursor(); N.push(cur, key, "qext2", title, body, "/garaz.html#qext2"); conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa
        print("powiadomienie:", e)
    try:
        import qbot_trener_notify as TN
        TN.send("🛠 " + title + "\n" + body)
    except Exception as e:  # noqa
        print("telegram:", e)


# ---------------------------------------------------------------- przebieg
def run() -> dict:
    os.environ.setdefault("QBOT3_ENABLED", "1")
    SIM.mkdir(parents=True, exist_ok=True)
    st = load_state()
    builds = st.get("builds") or []
    head = git("rev-parse", "HEAD").strip()
    if not st.get("last"):
        ci = commit_info(head)
        d = SIM / ci["sha7"]; d.mkdir(parents=True, exist_ok=True)
        for f in JS_FILES + [SIM_JS]:
            shutil.copy2(PUB / f, d / f)
        ok, msg = smoke(d)
        builds = [dict({k: ci[k] for k in ("sha", "sha7", "date", "subject", "files")}, build=build_no(head), opis=summarize(ci),
                       render=False, sim="start", sim_id=ci["sha7"], uwagi="start logu; " + msg)]
        st = {"last": head, "builds": builds, "started": datetime.now().isoformat(timespec="seconds")}
    else:
        new = [s for s in git("rev-list", "--reverse", st["last"] + ".." + head).split() if s]
        for sha in new[:20]:
            ci = commit_info(sha)
            prev = builds[-1]
            changed = [f for f in ci["files"] if f in RENDER]
            added = added_fields(prev["sha"], sha) if any(f in DATA_FILES for f in ci["files"]) else {}
            e = dict({k: ci[k] for k in ("sha", "sha7", "date", "subject", "files")}, build=build_no(sha), opis=summarize(ci),
                     render=bool(changed), nowe_dane=["%s.%s" % (c, n) for c, v in added.items() for n in v["fields"]])
            if not changed and not added:
                e.update(sim="bez_zmian", sim_id=prev["sim_id"], uwagi="")
            else:
                ok, msg = port(SIM / prev["sim_id"], SIM / ci["sha7"], prev["sha"], sha, changed, added)
                if ok:
                    e.update(sim="ok", sim_id=ci["sha7"], uwagi=msg)
                else:
                    shutil.rmtree(SIM / ci["sha7"], ignore_errors=True)
                    e.update(sim="poprzedni", sim_id=prev["sim_id"], uwagi=msg)
                    e["_powiadom"] = True   # 2026-10-19: Telegram dopiero gdy ponowienie (nizej) tez sie nie uda
            builds.append(e)
            st["last"] = sha
    # 2026-10-19: ostatni nieudany build ponawiany raz (od ostatniej dzialajacej wersji symulatora); po sukcesie
    # nastepne buildy bez zmian wygladu wskazuja nowa wersje. Powiadomienie tylko, gdy i to sie nie uda.
    fails = [i for i, b in enumerate(builds) if b.get("sim") == "poprzedni" and not b.get("ponowiono")]
    if fails:
        i = fails[-1]; fb = builds[i]; fb["ponowiono"] = datetime.now().isoformat(timespec="seconds")
        base = next((b for b in builds if b.get("sha7") == fb["sim_id"]), None)
        if base:
            files = [f for f in git("diff", "--name-only", base["sha"], fb["sha"]).split() if f in RENDER]
            added = added_fields(base["sha"], fb["sha"]) if any(f in DATA_FILES for f in git("diff", "--name-only", base["sha"], fb["sha"]).split()) else {}
            ok, msg = port(SIM / base["sim_id"], SIM / fb["sha7"], base["sha"], fb["sha"], files, added) if (files or added) else (False, "brak zmian do przeniesienia")
            if ok:
                old_id = fb["sim_id"]
                fb.update(sim="ok", sim_id=fb["sha7"], uwagi="ponowione automatycznie: " + msg)
                for b in builds[i + 1:]:
                    if b.get("sim") == "bez_zmian" and b.get("sim_id") == old_id:
                        b["sim_id"] = fb["sha7"]
                notify("QExt2 %s: symulator nadrobiony" % fb["sha7"], "Zmiana wyglądu jest już w symulatorze (ponowienie automatyczne).", "qext2:simok:" + fb["sha7"])
            else:
                shutil.rmtree(SIM / fb["sha7"], ignore_errors=True)
                fb["uwagi"] = (fb.get("uwagi") or "") + " | ponowienie: " + msg[:200]
                notify("QExt2 %s: symulator bez nowego wyglądu" % ((("build %d" % fb["build"]) if fb.get("build") else fb["sha7"])),
                       "Automat nie przeniósł zmiany do symulatora nawet po ponowieniu: %s. Symulator pokazuje poprzedni wygląd." % msg[:300],
                       "qext2:sim:" + fb["sha7"])
    for b in builds:
        b.pop("_powiadom", None)
    for b in builds:
        if not b.get("build"):
            b["build"] = build_no(b["sha"])
    st["builds"] = builds
    st["checked"] = datetime.now().isoformat(timespec="seconds")
    save_json(STATE, st)
    save_json(SIM / "builds.json", {"checked": st["checked"], "started": st.get("started"), "builds": list(reversed(builds))})
    return {"ok": True, "builds": len(builds), "last": st["last"][:7]}


if __name__ == "__main__":
    if os.geteuid() == 0:
        print(json.dumps({"ok": False, "why": "nie uruchamiaj jako root (pliki musza nalezec do qbot)"}))
        sys.exit(1)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(json.dumps({"ok": False, "why": "juz dziala"}))
            sys.exit(0)
        print(json.dumps(run(), ensure_ascii=False))
