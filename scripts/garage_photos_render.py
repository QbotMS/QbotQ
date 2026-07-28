"""garage_photos_render.py - dobiera zdjecia dla rzeczy, ktore MAJA juz adres,
ale strona nie oddala obrazu przy zwyklym pobraniu (sklepy renderowane JavaScriptem).

Uzywa Playwright (render=True) - wolniej (~30-45 s na sztuke), ale w batchu to nie boli.
Nie szuka w sieci, wiec nie dotyka limitow wyszukiwarki.
"""
import io, os, sys, time, sqlite3
sys.path.insert(0, '/opt/qbot/app')
import requests
from PIL import Image, ImageOps
import qbot_gear_scrape as scr

DB = '/opt/qbot/app/data/garage.db'
IMG = '/opt/qbot/web/public/gear'
RAPORT = '/opt/qbot/app/docs/audit/garage_photos_%s.md' % time.strftime('%Y-%m-%d')
PREF = {'gear': '', 'equipment': 'eq', 'components': 'cmp'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

def log(t):
    os.makedirs(os.path.dirname(RAPORT), exist_ok=True)
    open(RAPORT, 'a', encoding='utf-8').write(t + chr(10))
    print(t, flush=True)

def zapisz(tabela, gid, url):
    r = requests.get(url, headers={'User-Agent': UA}, timeout=25, stream=True)
    r.raise_for_status()
    raw = b''
    for ch in r.iter_content(8192):
        raw += ch
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError('za duzy')
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    os.makedirs(IMG, exist_ok=True)
    b = '%s%d' % (PREF[tabela], gid)
    f = im.copy(); f.thumbnail((1600, 1600)); f.save(os.path.join(IMG, b + '.jpg'), 'JPEG', quality=85)
    t = im.copy(); t.thumbnail((240, 240)); t.save(os.path.join(IMG, b + '_thumb.jpg'), 'JPEG', quality=82)
    v = int(time.time())
    return '/gear/%s.jpg?v=%d' % (b, v), '/gear/%s_thumb.jpg?v=%d' % (b, v)

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 200
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    log(chr(10) + '# Dobieranie zdjec z renderowaniem - ' + time.strftime('%Y-%m-%d %H:%M'))
    for tabela in ('gear', 'equipment', 'components'):
        rows = conn.execute(
            "SELECT id, brand, model, url FROM %s WHERE active=1 AND (photo IS NULL OR photo='') "
            "AND url IS NOT NULL AND url<>'' ORDER BY id LIMIT ?" % tabela, (limit,)).fetchall()
        log(chr(10) + '## %s - z adresem, bez zdjecia: %d' % (tabela, len(rows)))
        ok = 0
        for n, r in enumerate(rows, 1):
            nazwa = ' '.join([x for x in (r['brand'], r['model']) if x])[:44]
            try:
                d = scr.scrape(r['url'], use_llm=False, render=True, pick_image=True)
                img = (d.get('fields') or {}).get('image')
                if not img:
                    log('- [%d/%d] %s -> strona nie oddaje zdjecia' % (n, len(rows), nazwa)); continue
                p, t = zapisz(tabela, r['id'], img)
                conn.execute('UPDATE %s SET photo=?, thumb=? WHERE id=?' % tabela, (p, t, r['id']))
                conn.commit(); ok += 1
                log('- [%d/%d] %s -> ZDJECIE' % (n, len(rows), nazwa))
            except Exception as e:
                log('- [%d/%d] %s -> blad: %s' % (n, len(rows), nazwa, str(e)[:60]))
        log(chr(10) + '**%s: pobrano %d z %d**' % (tabela, ok, len(rows)))
    conn.close()

if __name__ == '__main__':
    main()
