"""Instaluje oslone logow QBota (qbot_logguard) w .venv. Uruchom po przebudowie .venv. Sesja klucze-1910."""
import shutil, os
SP = "/opt/qbot/app/.venv/lib/python3.12/site-packages/"
shutil.copy2("/opt/qbot/app/config/qbot_logguard.py", SP + "qbot_logguard.py")
open(SP + "qbot_logguard.pth", "w").write("import qbot_logguard\n")
os.chmod(SP + "qbot_logguard.py", 0o644); os.chmod(SP + "qbot_logguard.pth", 0o644)
print("zainstalowano qbot_logguard")
