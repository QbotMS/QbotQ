#!/usr/bin/env python3
"""Cotygodniowa kopia offsite serwera olga181 -> Cloudflare R2 (restic).

Uruchamiane jako root przez qbot-offsite-r2.timer (niedziela 04:30, Persistent).
Nie zalezy od Maca ani od ChatGPT/Codex. Pelna dokumentacja: docs/BACKUP_OFFSITE_R2.md.

Zakres = whitelist (tylko to, czego nie da sie pobrac/odbudowac):
  bazy PostgreSQL (eksport custom) + role, spojne kopie SQLite, kod i konfiguracja,
  /etc, crony, /root (bez cache), WWW, pliki FIT/cwiczenia, listy wersji bibliotek.
Pominiete (do odbudowy, opis w dok.): mapy OSM .pbf + roads.sqlite, .venv,
  przegladarki Playwright, cache pip/npm, WorldCover, stare zrzuty, historia Codex.

Sekrety: /root/.config/qbot-offsite/r2.env (klucz R2 tylko do 1 bucketu)
         /root/.config/qbot-offsite/restic-password (klucz szyfrowania repozytorium)
Alert: Telegram TYLKO przy bledzie (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID z /opt/qbot/app/.env).
Status: /var/lib/qbot-offsite-backup/r2-status.json

Uzycie: offsite_backup_r2.py            pelny przebieg (eksport, backup, retencja, check)
        offsite_backup_r2.py --status   pokaz status ostatniego przebiegu
"""
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

RESTIC = '/opt/qbot-offsite-backup/restic'
CONF = Path('/root/.config/qbot-offsite')
BASE = Path('/var/lib/qbot-offsite-backup')
STAGE = BASE / 'staging-r2'
CACHE = BASE / 'cache-r2'
STATUS = BASE / 'r2-status.json'
HOST = 'olga181'

INCLUDE = [
    '/etc', '/root', '/usr/local', '/var/spool/cron', '/var/www',
    '/opt/qbot', '/opt/q365', '/opt/qext2', '/opt/q', '/opt/noobs',
    '/opt/qbot-offsite-backup', str(STAGE),
]
EXCLUDE = [
    # do pobrania / odbudowy
    '/opt/qbot/data/osm/*.pbf', '/opt/qbot/data/osm/roads.sqlite',
    '/opt/qbot/artifacts/worldcover', '/opt/qbot/artifacts/old',
    '/opt/qbot/app/.venv', '/opt/qbot/app/.ms-playwright', '/opt/qbot/cronometer-venv',
    '/opt/q365/app/.venv', '/root/qbot-mcp/venv',
    '/opt/qbot/backups', '/opt/qbot/_archiwum', '/opt/qbot/.cache',
    '/root/.cache', '/root/.npm', '/root/.codex',
    '/root/.local/share/pipx', '/root/.local/share/opencode',
    '__pycache__', '*.pyc',
]
SQLITE = ['/opt/qbot/app/data/garage.db', '/opt/qbot/app/qbot_mcp_auth.db']
VENVS = {'qbot-app': '/opt/qbot/app/.venv', 'qbot-mcp': '/root/qbot-mcp/venv',
         'q365': '/opt/q365/app/.venv', 'cronometer': '/opt/qbot/cronometer-venv'}
RETENTION = ['--keep-weekly', '8', '--keep-monthly', '6']


def load_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def restic_env():
    env = os.environ.copy()
    env.update(load_env(CONF / 'r2.env'))
    env.update(RESTIC_PASSWORD_FILE=str(CONF / 'restic-password'),
               RESTIC_CACHE_DIR=str(CACHE), GOMAXPROCS='2')
    return env


def restic(args, env, capture=False):
    cmd = [RESTIC] + args
    if capture:
        return subprocess.run(cmd, env=env, check=True, capture_output=True, text=True).stdout
    subprocess.run(cmd, env=env, check=True)


def capture_to(path, command):
    partial = path.with_name(path.name + '.partial')
    with partial.open('wb') as out:
        subprocess.run(command, stdout=out, check=True)
    os.replace(partial, path)


def prepare():
    """Swieze eksporty baz i lista wersji (trafiaja do kopii z STAGE)."""
    if shutil.disk_usage(BASE).free < 3 * 1024**3:
        raise RuntimeError('Mniej niz 3 GiB wolnego miejsca na eksport bazy')
    for old in STAGE.glob('*'):
        old.unlink()
    pg = ['runuser', '-u', 'postgres', '--']
    dbs = json.loads(subprocess.check_output(pg + ['psql', '-X', '-Atc',
        "SELECT coalesce(json_agg(datname),'[]') FROM pg_database "
        "WHERE NOT datistemplate AND datallowconn;"]))
    for db in dbs:
        out = STAGE / f'postgres-{db}.dump'
        capture_to(out, pg + ['pg_dump', '-Fc', '-Z0', '--dbname', db])
        subprocess.run(['pg_restore', '--file=/dev/null', str(out)], check=True)
    capture_to(STAGE / 'postgres-roles.sql', pg + ['pg_dumpall', '--roles-only'])
    for src in SQLITE:
        name = 'sqlite-' + src.strip('/').replace('/', '_')
        part = STAGE / (name + '.partial')
        with sqlite3.connect('file:' + src + '?mode=ro', uri=True) as s, sqlite3.connect(part) as d:
            s.backup(d)
            if d.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RuntimeError('SQLite integrity_check nie przeszedl: ' + src)
        os.replace(part, STAGE / name)
    for name, venv in VENVS.items():
        pip = Path(venv) / 'bin' / 'pip'
        if pip.exists():
            capture_to(STAGE / f'pip-freeze-{name}.txt', [str(pip), 'freeze'])
    capture_to(STAGE / 'packages-dpkg.txt', ['dpkg-query', '-W'])
    capture_to(STAGE / 'systemd-units.txt', ['systemctl', 'list-unit-files', '--no-pager'])
    (STAGE / 'manifest.json').write_text(json.dumps({
        'created': datetime.now().astimezone().isoformat(), 'databases': dbs,
        'sqlite': SQLITE, 'include': INCLUDE, 'exclude': EXCLUDE,
        'note': 'Kopia plikowa + eksporty nie sa jednym punktem w czasie. Odtwarzanie: docs/BACKUP_OFFSITE_R2.md',
    }, indent=2, ensure_ascii=False))


def telegram(text):
    try:
        e = load_env('/opt/qbot/app/.env')
        tok, chat = e.get('TELEGRAM_TOKEN'), e.get('TELEGRAM_CHAT_ID')
        if not tok or not chat:
            return
        data = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode()
        urllib.request.urlopen(f'https://api.telegram.org/bot{tok}/sendMessage', data=data, timeout=15)
    except Exception as exc:  # alert nie moze wywrocic raportu statusu
        print('telegram error:', exc, file=sys.stderr)


PUBLIC = Path('/opt/qbot/app/state/offsite_r2.json')  # podsumowanie bez sekretow dla Statusu (qbot_status_checks)


def write_status(d):
    d['updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
    if d.get('state') == 'ok':
        d['last_ok_at'] = d['updated_at']
    elif 'last_ok_at' not in d:
        try:
            d['last_ok_at'] = json.loads(PUBLIC.read_text()).get('last_ok_at')
        except Exception:
            d['last_ok_at'] = None
    STATUS.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    try:
        pub = {k: d.get(k) for k in ('state', 'phase', 'started_at', 'updated_at', 'last_ok_at', 'repo_bytes', 'warning')}
        pub['added_bytes'] = (d.get('summary') or {}).get('data_added_packed')
        pub['snapshot'] = str((d.get('summary') or {}).get('snapshot_id') or '')[:8] or None
        tmp = PUBLIC.with_suffix('.partial')
        tmp.write_text(json.dumps(pub, indent=1, ensure_ascii=False))
        os.chmod(tmp, 0o644)
        os.replace(tmp, PUBLIC)
    except Exception as exc:
        print('public status error:', exc, file=sys.stderr)


def run():
    env = restic_env()
    st = {'state': 'running', 'phase': 'init',
          'started_at': datetime.now().astimezone().isoformat(timespec='seconds')}
    write_status(st)
    try:
        if subprocess.run([RESTIC, 'cat', 'config', '--no-lock'], env=env,
                          capture_output=True).returncode != 0:
            st['phase'] = 'repo-init'
            write_status(st)
            restic(['init'], env)
        st['phase'] = 'export'
        write_status(st)
        prepare()
        st['phase'] = 'backup'
        write_status(st)
        cmd = ['backup', '--json', '--host', HOST, '--tag', 'weekly', '--one-file-system',
               '--exclude-caches', '--read-concurrency', '2']
        for x in EXCLUDE:
            cmd += ['--exclude', x]
        r = subprocess.run([RESTIC] + cmd + [p for p in INCLUDE if Path(p).exists()],
                           env=env, capture_output=True, text=True)
        if r.returncode not in (0, 3):  # 3 = kopia zapisana, ale czesc plikow nieczytelna
            raise RuntimeError(f'restic backup rc={r.returncode}: {r.stderr[-300:]}')
        if r.returncode == 3:
            st['warning'] = 'czesc plikow nieczytelna: ' + r.stderr[-300:]
        summary = next((json.loads(line) for line in r.stdout.splitlines()
                        if line.startswith('{') and '"summary"' in line), {})
        st['summary'] = summary
        st['phase'] = 'retention'
        write_status(st)
        restic(['forget', '--host', HOST, '--prune'] + RETENTION, env)
        st['phase'] = 'check'
        write_status(st)
        restic(['check', '--read-data-subset', '3%'], env)
        stats = json.loads(restic(['stats', '--mode', 'raw-data', '--json'], env, capture=True))
        st.update(state='ok', phase='done', repo_bytes=stats.get('total_size'))
        write_status(st)
        print(f"OK snapshot={str(summary.get('snapshot_id', '?'))[:8]} "
              f"dodano={summary.get('data_added_packed', 0) / 1e6:.1f} MB "
              f"repo={(stats.get('total_size') or 0) / 1e9:.2f} GB")
        return 0
    except Exception as exc:
        st.update(state='error', error=str(exc)[:500])
        write_status(st)
        telegram(f"⚠️ Kopia offsite R2 (olga181) NIEUDANA na etapie '{st.get('phase')}': "
                 f"{str(exc)[:300]}\nLog: journalctl -u qbot-offsite-r2")
        raise


def main():
    os.umask(0o077)
    if '--status' in sys.argv:
        print(STATUS.read_text() if STATUS.exists() else 'brak statusu')
        return 0
    if os.geteuid() != 0:
        sys.exit('Uruchom jako root (systemd: qbot-offsite-r2.service)')
    for d in (BASE, STAGE, CACHE):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (BASE / 'r2.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('Inny przebieg kopii trwa')
    return run()


if __name__ == '__main__':
    sys.exit(main())
