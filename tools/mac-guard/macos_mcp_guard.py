#!/usr/bin/env python3
"""Straznik MacOS-MCP (QBot, 2026-10-20, sesja devmcp-2010).

Stoi miedzy aplikacja Claude a rozszerzeniem MacOS-MCP (MCP po stdio, JSON w liniach):
- loguje kazde wywolanie narzedzia do ~/Library/Logs/qbot-guard/macos-mcp.jsonl,
- przy Shell i przy akcjach w aplikacjach wrazliwych pyta Michala okienkiem
  (Odmow / Raz / Zezwol na N min) z podgladem, CO ma sie stac,
- powiadomienia macOS przy nietypowym zachowaniu (odmowa, praca gdy Michala nie ma,
  tekst podobny do hasla, nowa domena w Scrape, przekroczony limit tempa).
Konfiguracja: ~/.qbot-guard/config.json. Uruchamiany przez Claude (claude_desktop_config.json).
"""
import json, os, re, subprocess, sys, threading, time
from datetime import datetime
from urllib.parse import urlparse

HOME = os.path.expanduser("~")
GDIR = os.path.join(HOME, ".qbot-guard")
LOGDIR = os.path.join(HOME, "Library", "Logs", "qbot-guard")
LOG = os.path.join(LOGDIR, "macos-mcp.jsonl")
CFG_PATH = os.path.join(GDIR, "config.json")
DOMAINS = os.path.join(GDIR, "seen_domains.json")
EXT = os.path.join(HOME, "Library", "Application Support", "Claude", "Claude Extensions",
                   "ant.dir.gh.cursortouch.macos-mcp")

DEFAULT_CFG = {
    "window_min": 15, "rate_per_min": 30, "idle_alert_s": 600, "dialog_timeout_s": 60,
    "always_ask_tools": ["Shell"],
    "app_tools": ["Click", "Type", "Scroll", "Move", "Shortcut", "Snapshot", "App"],
    "sensitive_apps": [
        "System Settings", "Ustawienia systemowe", "Keychain Access", "Pęk kluczy", "Secretive",
        "Terminal", "iTerm2", "Postico 2", "Microsoft Outlook", "Microsoft Word", "Microsoft Excel",
        "Microsoft PowerPoint", "Microsoft Teams", "OneDrive", "Messages", "Wiadomości", "WhatsApp",
        "Telegram", "Mail", "Hik-Connect", "SmartPSSLite", "ControllerForHomeKit", "AdGuard Mini"],
    "browsers": ["Google Chrome", "Safari"],
    "sensitive_title_patterns": ["bank", "pko", "mbank", "ing ", "santander", "millennium", "pekao",
                                 "outlook", "sharepoint", "kbr", "atlas ward", "onedrive", "teams"],
}

_lock = threading.Lock()
_out_lock = threading.Lock()
_allow_until = {}
_calls = []
_pending = {}


def cfg():
    c = dict(DEFAULT_CFG)
    try:
        with open(CFG_PATH, encoding="utf-8") as fh:
            c.update(json.load(fh))
    except Exception:
        pass
    return c


def log(ev):
    ev = dict(ev)
    ev["ts"] = datetime.now().isoformat(timespec="seconds")
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _osa(script, timeout=5):
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip()
    except Exception:
        return 1, ""


def _q(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def notify(title, text):
    _osa('display notification "%s" with title "%s" sound name "Basso"' % (_q(text[:220]), _q(title)))


def frontmost():
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=3).stdout.strip()
        out = subprocess.run(["lsappinfo", "info", "-only", "name", asn], capture_output=True,
                             text=True, timeout=3).stdout
        m = (re.search(r'"(?:LSDisplayName|name)"\s*=\s*"([^"]*)"', out)
             or re.search(r'^"([^"]+)"', out.strip()))
        return m.group(1) if m else ""
    except Exception:
        return ""


def browser_title(app):
    if app == "Google Chrome":
        rc, t = _osa('tell application "Google Chrome" to if (count of windows) > 0 then get title of active tab of front window')
    elif app == "Safari":
        rc, t = _osa('tell application "Safari" to if (count of windows) > 0 then get name of current tab of front window')
    else:
        return None
    return t if rc == 0 else None


def idle_s():
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"HIDIdleTime" = (\d+)', out)
        return int(m.group(1)) // 1_000_000_000 if m else 0
    except Exception:
        return 0


SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{12,}|eyJ[A-Za-z0-9_-]{20,}\.|-----BEGIN)")


def looks_secret(text):
    if not text or not isinstance(text, str):
        return False
    if SECRET_RE.search(text):
        return True
    t = text.strip()
    return (" " not in t and 10 <= len(t) <= 64 and re.search(r"[a-z]", t) and re.search(r"[A-Z]", t)
            and re.search(r"\d", t) and re.search(r"[^A-Za-z0-9]", t)) is not None


def ask(key, what, detail, c, window_min=None):
    now = time.time()
    if _allow_until.get(key, 0) > now:
        return True, "okno"
    mins = int(window_min if window_min is not None else c["window_min"])
    body = "MacOS-MCP chce: %s\n\n%s" % (what, detail[:400])
    script = ('display dialog "%s" with title "Straznik MacOS-MCP" buttons {"Odmów", "Raz", "Zezwól na %d min"} '
              'default button "Odmów" cancel button "Odmów" with icon caution giving up after %d'
              % (_q(body), mins, int(c["dialog_timeout_s"])))
    rc, out = _osa(script, timeout=int(c["dialog_timeout_s"]) + 10)
    if rc != 0:
        return False, "odmowa"
    if "gave up:true" in out:
        return False, "brak_odpowiedzi"
    if "Zezwól" in out:
        _allow_until[key] = now + mins * 60
        return True, "okno_%dmin" % mins
    if "Raz" in out:
        return True, "raz"
    return False, "odmowa"


def short_args(args):
    s = json.dumps(args, ensure_ascii=False)
    return s if len(s) <= 300 else s[:300] + "…"


def decide(tool, args, c):
    ctx = {"app": frontmost()}
    now = time.time()
    _calls[:] = [t for t in _calls if now - t < 60]
    _calls.append(now)
    if len(_calls) > int(c["rate_per_min"]):
        notify("Straznik MacOS-MCP", "Limit tempa: ponad %s akcji/min — wstrzymano." % c["rate_per_min"])
        return False, "limit_tempa", ctx
    idle = idle_s()
    ctx["idle_s"] = idle
    if idle >= int(c["idle_alert_s"]):
        ctx["anomalia_nieobecnosc"] = True
        notify("Straznik MacOS-MCP", "AI dziala, gdy Cie nie ma (%d min bezczynnosci): %s" % (idle // 60, tool))
    a = args if isinstance(args, dict) else {}
    text = a.get("text")
    if tool == "Type" and looks_secret(text):
        ctx["anomalia_haslo"] = True
        ok, why = ask("Type-secret-%s" % ctx["app"], "wpisac tekst podobny do HASLA/TOKENU w: %s" % (ctx["app"] or "?"),
                      "(tekst ukryty, %d znakow)" % len(text), c, window_min=1)
        return ok, why, ctx
    if tool == "Scrape":
        dom = urlparse(str(a.get("url", ""))).netloc.lower()
        seen = set()
        try:
            with open(DOMAINS) as fh:
                seen = set(json.load(fh))
        except Exception:
            pass
        if dom and dom not in seen:
            ctx["anomalia_nowa_domena"] = dom
            notify("Straznik MacOS-MCP", "Nowa strona otwierana przez AI: %s" % dom)
            seen.add(dom)
            try:
                with open(DOMAINS, "w") as fh:
                    json.dump(sorted(seen), fh)
            except Exception:
                pass
        return True, "scrape", ctx
    if tool in c["always_ask_tools"]:
        cmd = str(a.get("command", "")) or short_args(args)
        ok, why = ask("tool:" + tool, "wykonac polecenie (%s)" % tool, cmd, c)
        return ok, why, ctx
    if tool in c["app_tools"]:
        targets = [ctx["app"]]
        if tool == "App":
            targets.append(str(a.get("name", "") or a.get("app", "") or ""))
        sens = [x for x in targets if x and x in c["sensitive_apps"]]
        if ctx["app"] in c["browsers"]:
            title = browser_title(ctx["app"])
            ctx["title"] = title
            if title and any(p in title.lower() for p in c["sensitive_title_patterns"]):
                sens.append("%s: %s" % (ctx["app"], title[:60]))
        if sens:
            ok, why = ask("app:" + sens[0], "%s w: %s" % (tool, sens[0]), short_args(args), c)
            return ok, why, ctx
    return True, "wolne", ctx


def send(obj):
    with _out_lock:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def from_claude(child):
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            child.stdin.write(raw + "\n")
            child.stdin.flush()
            continue
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            p = msg.get("params") or {}
            tool, args = p.get("name", ""), p.get("arguments") or {}
            c = cfg()
            with _lock:
                try:
                    ok, why, ctx = decide(tool, args, c)
                except Exception as exc:
                    ok, why, ctx = False, "blad_straznika:%s" % exc, {}
            safe_args = dict(args) if isinstance(args, dict) else {"_": args}
            if tool == "Type" and looks_secret(safe_args.get("text")):
                safe_args["text"] = "(ukryte)"
            log({"ev": "call", "id": msg.get("id"), "tool": tool, "args": short_args(safe_args),
                 "decision": "OK" if ok else "BLOK", "why": why, **ctx})
            if not ok:
                if why != "limit_tempa":
                    notify("Straznik MacOS-MCP", "Zablokowano: %s (%s)" % (tool, why))
                send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {"isError": True, "content": [
                    {"type": "text", "text": "STRAZNIK: akcja %s zablokowana (%s). Popros Michala o zgode "
                                             "w okienku albo wybierz inna droge." % (tool, why)}]}})
                continue
            _pending[msg.get("id")] = (tool, time.time())
        child.stdin.write(raw + "\n")
        child.stdin.flush()
    try:
        child.stdin.close()
    except Exception:
        pass


def from_child(child):
    for line in child.stdout:
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and msg.get("id") in _pending:
                tool, t0 = _pending.pop(msg.get("id"))
                res = msg.get("result") or {}
                log({"ev": "result", "id": msg.get("id"), "tool": tool, "ms": int((time.time() - t0) * 1000),
                     "isError": bool(res.get("isError") or msg.get("error")), "bytes": len(line)})
        except Exception:
            pass
        with _out_lock:
            sys.stdout.write(line)
            sys.stdout.flush()


def main():
    os.makedirs(LOGDIR, exist_ok=True)
    env = dict(os.environ)
    env["ANONYMIZED_TELEMETRY"] = "false"
    uv = "/opt/homebrew/bin/uv" if os.path.exists("/opt/homebrew/bin/uv") else "uv"
    child = subprocess.Popen([uv, "--directory", EXT, "run", "macos-mcp", "serve"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1, env=env)
    log({"ev": "start", "pid": os.getpid(), "child": child.pid})
    threading.Thread(target=from_child, args=(child,), daemon=True).start()
    try:
        from_claude(child)
    finally:
        try:
            child.wait(timeout=10)
        except Exception:
            child.kill()
        log({"ev": "stop"})


if __name__ == "__main__":
    main()
