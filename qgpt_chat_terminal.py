#!/usr/bin/env python3
import sys
from pathlib import Path
from dotenv import load_dotenv
from qgpt_client import QGPT_MODEL, qgpt_chat

load_dotenv(Path("/opt/qbot/app/.env"))

history = []

SYSTEM = """Jesteś asystentem Michała. Masz dostęp do kontekstu jego systemu Q-bot
na Orange Pi. Odpowiadasz po polsku, zwięźle i konkretnie."""

print(f"\033[1;36m╔══════════════════════════════════╗")
print(f"║    QGPT Chat — Q-bot terminal    ║")
print(f"║   Model: {QGPT_MODEL:<24}║")
print(f"╚══════════════════════════════════╝\033[0m")
print("\033[90mWpisz 'exit' lub Ctrl+C żeby wyjść. 'clear' czyści historię.\033[0m\n")

while True:
    try:
        user_input = input("\033[1;32mTy:\033[0m ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\033[90mDo zobaczenia!\033[0m")
        sys.exit(0)

    if not user_input:
        continue
    if user_input.lower() == "exit":
        print("\033[90mDo zobaczenia!\033[0m")
        sys.exit(0)
    if user_input.lower() == "clear":
        history = []
        print("\033[90m[Historia wyczyszczona]\033[0m")
        continue

    history.append({"role": "user", "content": user_input})

    try:
        reply = qgpt_chat(history, system=SYSTEM, max_tokens=2048)
        history.append({"role": "assistant", "content": reply})
        print(f"\n\033[1;34mQGPT:\033[0m {reply}\n")
    except Exception as e:
        print(f"\033[1;31mBłąd:\033[0m {e}\n")
        history.pop()
