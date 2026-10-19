#!/usr/bin/env python3
"""Zbieranie stanu aktualizacji serwera olga181 -> state/updates.json (SETUP > Polaczenia > Aktualizacje).

Uruchamiane jako root przez qbot-updates-check.service:
  - timer qbot-updates-check.timer (codziennie ok. 05:15),
  - na zadanie ze strony: plik state/updates.request (qbot-updates-check.path).
Tylko ODCZYT: niczego nie instaluje. Dok.: docs/AKTUALIZACJE.md

Zrodla:
  System: apt (Ubuntu + nodesource + cloudflared), /var/run/reboot-required, log unattended-upgrades.
  Python: pip list (+ --outdated) w kazdym venv, znane podatnosci z OSV.dev (api.osv.dev, PyPI).
Ocena kazdej pozycji: pilne (znana luka w bibliotece sieciowej/bezpieczenstwa KEY_LIBS, poprawka bezpieczenstwa
  systemu czeka >2 dni, restart >7 dni), zalecane (luka w bibliotece pomocniczej, pakiet systemowy),
  moze_poczekac (nowsza wersja bez znanej luki).
"""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP = Path('/opt/qbot/app')
OUT = APP / 'state' / 'updates.json'
REQ = APP / 'state' / 'updates.request'
VENVS = {
    'QBot (aplikacja, strona, API)': '/opt/qbot/app/.venv',
    'Mosty MCP (Claude, DEV)': '/root/qbot-mcp/venv',
    'Q365': '/opt/q365/app/.venv',
    'Cronometer': '/opt/qbot/cronometer-venv',
}
# biblioteki, przez ktore QBot rozmawia z internetem / pilnuje dostepu -> nieaktualne = "zalecane"
KEY_LIBS = {'fastapi', 'starlette', 'uvicorn', 'mcp', 'cryptography', 'httpx', 'requests', 'urllib3',
            'certifi', 'pydantic', 'h11', 'httpcore', 'anyio', 'jinja2', 'pyjwt', 'msal', 'openai',
            'anthropic', 'garminconnect', 'psycopg', 'psycopg2-binary', 'python-multipart', 'aiohttp',
            'pillow', 'idna', 'multidict', 'yarl', 'websockets', 'sse-starlette', 'authlib', 'itsdangerous'}
OSV_BATCH = 'https://api.osv.dev/v1/querybatch'
OSV_VULN = 'https://api.osv.dev/v1/vulns/'


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def sh(cmd, timeout=600, env=None):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, r.stdout, r.stderr


def http_json(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json',
                                                          'User-Agent': 'qbot-updates-check'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------- system (apt) ----------------
def apt_section():
    env = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive')
    upd_rc, _, upd_err = sh(['apt-get', 'update', '-qq'], timeout=300, env=env)
    _, out, _ = sh(['apt', 'list', '--upgradable'], env=env)
    items = []
    for ln in out.splitlines():
        m = re.match(r'^(\S+?)/(\S+)\s+(\S+)\s+\S+\s+\[upgradable from:\s*(\S+)\]', ln)
        if not m:
            continue
        name, suites, new, old = m.groups()
        sec = '-security' in suites
        src = 'Ubuntu' if re.search(r'noble|jammy|focal|ubuntu', suites) else suites.split(',')[0]
        items.append({'name': name, 'installed': old, 'latest': new, 'suites': suites,
                      'source': src, 'security': sec})
    reboot = Path('/var/run/reboot-required')
    reboot_since = datetime.fromtimestamp(reboot.stat().st_mtime).astimezone() if reboot.exists() else None
    pkgs = []
    if Path('/var/run/reboot-required.pkgs').exists():
        pkgs = sorted(set(Path('/var/run/reboot-required.pkgs').read_text().split()))
    log = Path('/var/log/unattended-upgrades/unattended-upgrades.log')
    last_auto = datetime.fromtimestamp(log.stat().st_mtime).astimezone().isoformat(timespec='seconds') if log.exists() else None
    auto_on = False
    p = Path('/etc/apt/apt.conf.d/20auto-upgrades')
    if p.exists():
        auto_on = 'Unattended-Upgrade "1"' in p.read_text()
    return {
        'apt_update_ok': upd_rc == 0, 'apt_update_err': upd_err.strip()[-300:] if upd_rc else '',
        'pending': items,
        'reboot_required': reboot.exists(),
        'reboot_since': reboot_since.isoformat(timespec='seconds') if reboot_since else None,
        'reboot_pkgs': pkgs,
        'auto_security_updates': auto_on,
        'last_auto_run': last_auto,
    }


# ---------------- python (pip + OSV) ----------------
def pip_json(py, args, owner):
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK='1', PYTHONWARNINGS='ignore')
    cmd = [py, '-m', 'pip', 'list', '--format=json'] + args
    if owner and owner != 'root':
        cmd = ['runuser', '-u', owner, '--'] + cmd
    rc, out, err = sh(cmd, timeout=900, env=env)
    if rc != 0:
        raise RuntimeError((err or out).strip()[-300:])
    return json.loads(out or '[]')


def norm(n):
    return re.sub(r'[-_.]+', '-', n).lower()


def osv_vulns(pkgs):
    """pkgs: {name: version} -> {name: [vuln dict]}"""
    names = list(pkgs)
    res = {}
    ids_needed = set()
    for i in range(0, len(names), 500):
        chunk = names[i:i + 500]
        q = {'queries': [{'package': {'name': n, 'ecosystem': 'PyPI'}, 'version': pkgs[n]} for n in chunk]}
        out = http_json(OSV_BATCH, q, timeout=60)
        for n, r in zip(chunk, out.get('results', [])):
            ids = [v['id'] for v in (r.get('vulns') or [])]
            if ids:
                res[n] = ids
                ids_needed.update(ids)
    details = {}
    for vid in sorted(ids_needed)[:120]:
        try:
            details[vid] = http_json(OSV_VULN + vid, timeout=30)
        except Exception:
            details[vid] = {'id': vid}
    out = {}
    for n, ids in res.items():
        lst = []
        for vid in ids:
            d = details.get(vid, {'id': vid})
            fixed = set()
            for a in d.get('affected', []) or []:
                if norm(a.get('package', {}).get('name', '')) != norm(n):
                    continue
                for rg in a.get('ranges', []) or []:
                    for ev in rg.get('events', []) or []:
                        if 'fixed' in ev:
                            fixed.add(ev['fixed'])
            aliases = [x for x in d.get('aliases', []) or [] if x.startswith(('CVE-', 'GHSA-'))]
            lst.append({'id': vid, 'aliases': aliases[:3], 'summary': (d.get('summary') or d.get('details') or '')[:220],
                        'fixed': sorted(fixed)[:4], 'url': f'https://osv.dev/vulnerability/{vid}'})
        # duplikaty (GHSA/PYSEC tej samej luki) -> zostaw unikalne po aliasach
        seen, uniq = set(), []
        for v in lst:
            key = tuple(sorted(set(v['aliases']) | {v['id']}))
            if any(k in seen for k in key):
                continue
            seen.update(key)
            uniq.append(v)
        out[n] = uniq
    return out


def python_section():
    envs = []
    for label, venv in VENVS.items():
        py = Path(venv) / 'bin' / 'python'
        if not py.exists():
            continue
        owner = pwd.getpwuid(Path(venv).stat().st_uid).pw_name
        e = {'label': label, 'venv': venv, 'error': None, 'packages': []}
        try:
            inst = {p['name']: p['version'] for p in pip_json(str(py), [], owner)}
            outd = {p['name']: p['latest_version'] for p in pip_json(str(py), ['--outdated'], owner)}
            try:
                vulns = osv_vulns(inst)
            except Exception as ex:
                vulns = {}
                e['error'] = f'OSV niedostepne: {type(ex).__name__}'
            for n in sorted(set(outd) | set(vulns), key=str.lower):
                e['packages'].append({'name': n, 'installed': inst.get(n), 'latest': outd.get(n),
                                      'key': norm(n) in KEY_LIBS, 'vulns': vulns.get(n, [])})
            e['installed_count'] = len(inst)
        except Exception as ex:
            e['error'] = f'{type(ex).__name__}: {ex}'[:300]
        envs.append(e)
    return envs


# ---------------- ocena ----------------
def age_days(iso):
    if not iso:
        return 0
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400


def rate(data, prev):
    first_seen = (prev or {}).get('first_seen', {})
    seen_now = {}
    items = []
    sysd = data['system']
    for p in sysd['pending']:
        key = f"apt:{p['name']}:{p['latest']}"
        seen_now[key] = first_seen.get(key, data['checked_at'])
        old = age_days(seen_now[key])
        if p['security'] and old > 2:
            lvl, why = 'pilne', f'poprawka bezpieczenstwa czeka {old:.0f} dni (automat powinien ja juz zainstalowac)'
        elif p['security']:
            lvl, why = 'zalecane', 'poprawka bezpieczenstwa — automat zainstaluje ja w ciagu doby'
        else:
            lvl, why = 'zalecane', f"zwykla aktualizacja ({p['source']}) — nie instaluje sie sama"
        items.append({'kind': 'system', 'name': p['name'], 'installed': p['installed'], 'latest': p['latest'],
                      'level': lvl, 'why': why, 'where': 'system (apt)'})
    if sysd['reboot_required']:
        d = age_days(sysd['reboot_since'])
        items.append({'kind': 'reboot', 'name': 'Restart serwera', 'installed': '', 'latest': '',
                      'level': 'pilne' if d > 7 else 'zalecane',
                      'why': f"wymagany od {d:.0f} dni po aktualizacji: {', '.join(sysd['reboot_pkgs'][:6])}",
                      'where': 'system'})
    for e in data['python']:
        for p in e['packages']:
            if p['vulns']:
                ids = ', '.join((v['aliases'] or [v['id']])[0] for v in p['vulns'][:3])
                fx = sorted({f for v in p['vulns'] for f in v['fixed']})
                tail = f"znana luka ({ids})" + (f"; poprawione w {', '.join(fx[:3])}" if fx else '')
                if p['key']:  # luka w bibliotece, przez ktora QBot rozmawia z internetem / pilnuje dostepu
                    lvl, why = 'pilne', tail + ' — biblioteka sieciowa/bezpieczenstwa'
                else:
                    lvl, why = 'zalecane', tail + ' — biblioteka pomocnicza, mniejsze ryzyko'
            else:
                lvl, why = 'moze_poczekac', 'nowsza wersja, bez znanej luki'
            items.append({'kind': 'python', 'name': p['name'], 'installed': p['installed'], 'latest': p['latest'],
                          'level': lvl, 'why': why, 'where': e['label'], 'vulns': p['vulns']})
    order = {'pilne': 0, 'zalecane': 1, 'moze_poczekac': 2}
    items.sort(key=lambda x: (order[x['level']], x['kind'] != 'reboot', x['where'], x['name'].lower()))
    counts = {k: sum(1 for i in items if i['level'] == k) for k in order}
    overall = 'bad' if counts['pilne'] else ('warn' if counts['zalecane'] else 'ok')
    return items, counts, overall, seen_now


def main():
    t0 = time.time()
    try:
        REQ.unlink()
    except FileNotFoundError:
        pass
    prev = None
    try:
        prev = json.loads(OUT.read_text())
    except Exception:
        pass
    data = {'checked_at': now_iso(), 'host': 'olga181', 'errors': []}
    try:
        data['system'] = apt_section()
    except Exception as ex:
        data['system'] = {'pending': [], 'reboot_required': False, 'reboot_pkgs': []}
        data['errors'].append(f'system: {type(ex).__name__}: {ex}'[:300])
    try:
        data['python'] = python_section()
    except Exception as ex:
        data['python'] = []
        data['errors'].append(f'python: {type(ex).__name__}: {ex}'[:300])
    for e in data['python']:
        if e.get('error'):
            data['errors'].append(f"{e['label']}: {e['error']}")
    data['items'], data['counts'], data['overall'], data['first_seen'] = rate(data, prev)
    data['duration_s'] = round(time.time() - t0, 1)
    tmp = OUT.with_suffix('.json.partial')
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.chmod(tmp, 0o644)
    q = pwd.getpwnam('qbot')
    os.chown(tmp, q.pw_uid, q.pw_gid)
    os.replace(tmp, OUT)
    print(f"OK {data['counts']} w {data['duration_s']} s, bledy: {len(data['errors'])}")


if __name__ == '__main__':
    main()
