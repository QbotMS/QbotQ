#!/usr/bin/env python3
"""Monitor Q-bota — sprawdza usługi i wysyła powiadomienia na Telegram"""
import os, subprocess, httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/opt/qbot/app/.env')

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AUTO_RESTART = os.getenv("QBOT_MONITOR_RESTART", "").lower() in ("1", "true", "yes")

def notify(msg):
    httpx.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )

def check_service(name):
    r = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
    return r.stdout.strip() == 'active'

errors = []

# Sprawdź usługi. Unit ngrok w tej instalacji nazywa się ngrok-qbot.
SERVICES = {
    "q-bot": "q-bot",
    os.getenv("NGROK_SERVICE", "ngrok-qbot"): "ngrok",
}

for svc, label in SERVICES.items():
    if not check_service(svc):
        errors.append(f"❌ Usługa *{label}* ({svc}) nie działa!")
        if AUTO_RESTART:
            restart = subprocess.run(['systemctl', 'restart', svc], capture_output=True, text=True)
            if restart.returncode != 0:
                detail = (restart.stderr or restart.stdout or "").strip()
                errors.append(f"⚠️ Nie udało się zrestartować {svc}: `{detail[:300]}`")

# Sprawdź ostatni wynik sync żywienia.
try:
    with open('/opt/qbot/logs/nutrition_sync.log') as f:
        lines = f.readlines()[-20:]
    non_empty = [l.strip() for l in lines if l.strip()]
    errors_in_log = [
        (i, l) for i, l in enumerate(non_empty)
        if '❌' in l or 'error' in l.lower() or 'traceback' in l.lower()
    ]
    last_error_idx = errors_in_log[-1][0] if errors_in_log else -1
    has_later_success = any(
        l.startswith(("✅", "⏭")) for l in non_empty[last_error_idx + 1:]
    )
    if errors_in_log and not has_later_success:
        errors.append(f"⚠️ Błędy w sync żywienia:\n`{errors_in_log[-1][1]}`")
except:
    pass

# Sprawdź czy ngrok URL działa
try:
    r = httpx.get("http://localhost:4040/api/tunnels", timeout=5)
    tunnels = r.json().get('tunnels', [])
    if not tunnels:
        errors.append("❌ Tunel ngrok nie ma aktywnych połączeń!")
except:
    errors.append("❌ Nie można połączyć się z ngrok!")

if errors:
    msg = f"🚨 *Q-bot alert* ({datetime.now().strftime('%H:%M')})\n\n" + "\n".join(errors)
    notify(msg)
    print("⚠️ Wysłano alert:", "\n".join(errors))
else:
    print(f"✅ {datetime.now().strftime('%H:%M')} — wszystko działa")
