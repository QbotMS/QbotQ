# Straznik MacOS-MCP + okno roota + dziennik roota (2026-10-20, sesja devmcp-2010)

Kopia zrodel do odtworzenia. Na Macu pliki leza w `~/.qbot-guard/` (zywe), tu jest kopia.

## Co robi
- **Straznik** (`macos_mcp_guard.py`) stoi miedzy Claude a rozszerzeniem MacOS-MCP (proxy MCP po stdio).
  Claude uruchamia go z `claude_desktop_config.json` (`mcpServers."MacOS-MCP"` -> python3 + ten plik);
  samo rozszerzenie MacOS-MCP w Claude > Ustawienia > Rozszerzenia jest WYLACZONE (inaczej dziala podwojnie).
  - dziennik kazdej akcji: `~/Library/Logs/qbot-guard/macos-mcp.jsonl`
  - okienko macOS z podgladem CO ma sie stac (Odmow / Raz / Zezwol na 15 min) przy: `Shell` (zawsze),
    akcjach w aplikacjach wrazliwych (System, Pek kluczy, Secretive, Terminal, Office/Teams/OneDrive,
    komunikatory, kamery/dom, AdGuard) i kartach przegladarki z bankiem/Outlook/SharePoint/KBR w tytule;
    brak odpowiedzi w 60 s = odmowa
  - powiadomienia macOS: odmowa, AI dziala przy >10 min bezczynnosci, tekst podobny do hasla/tokenu,
    nowa domena w Scrape, >30 akcji/min (wstrzymanie)
  - ustawienia (nadpisanie domyslnych): `~/.qbot-guard/config.json`
- **Obserwator** (`guard_watch.py`, LaunchAgent `com.qbot.guard-watch`, co 10 min): alarm gdy MacOS-MCP
  dziala z pominieciem straznika; po 21:00 podsumowanie dnia -> `~/Library/Logs/qbot-guard/podsumowanie-DATA.txt`
  + powiadomienie. (Dzwonek QBota: etap 2 - QBot nie ma jeszcze bezpiecznego wejscia dla wpisow z Maca.)
- **Okno roota 15 min**: `~/.ssh/config`, Host q: `ControlMaster auto`, `ControlPath ~/.ssh/cm-q`,
  `ControlPersist 15m`, `LocalCommand` -> powiadomienie "Otwarto okno roota". Jeden Touch ID = 15 min bez pytan
  (dla KAZDEGO programu na Macu - swiadomy kompromis Michala). Zamkniecie okna wczesniej: `ssh -O exit q`.
- **Dziennik roota na serwerze** (`root-ssh-log`): `/usr/local/sbin/root-ssh-log`, wpiety jako
  `command="..."` przy kluczu Secretive w `/root/.ssh/authorized_keys`; zapis `/var/log/root-ssh.log`
  (CMD/SHELL/SFTP z godzina i IP), logrotate tygodniowo x8. Kopia klucza: `authorized_keys.bak-log`.

## Wycofanie
- Mac: przywroc `claude_desktop_config.json.bak-*` i `~/.ssh/config.bak-*`, wlacz rozszerzenie MacOS-MCP,
  `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.qbot.guard-watch.plist`, restart Claude.
- Serwer: `cp /root/.ssh/authorized_keys.bak-log /root/.ssh/authorized_keys`.

## Ograniczenia (uczciwie)
Hamulec, nie sejf: pliki straznika naleza do Michala, wiec AI z innym narzedziem (Desktop Commander)
moze je zmienic. Obserwator wykryje uruchomienie z pominieciem straznika, ale nie zmiane jego kodu.
Desktop Commander na Macu (start_process) czasem wisi przy dlugich/zapisujacych poleceniach -
pliki na Maca przekazywano przez /opt/qbot/web/landing (jednorazowo, potem usuniete) + curl + sha256.
