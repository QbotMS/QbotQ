#!/usr/bin/env python3
"""
Analytical fallback używa własnych env vars dla LLM —
QGPT_ANALYTICAL_BASE_URL i QGPT_ANALYTICAL_API_KEY / MODEL.
Fallback na Gemini jeśli ustawione, inaczej używa domyślnych.
Dodaj do .env.local:
  QGPT_ANALYTICAL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
  QGPT_ANALYTICAL_API_KEY=<gemini_key>
  QGPT_ANALYTICAL_MODEL=gemini-2.5-flash-lite
"""
import ast, os

# Sprawdź aktualne QGPT_API_KEY z /etc/qbot/qbot-api.env
env_main = {}
with open('/etc/qbot/qbot-api.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, _, v = line.strip().partition('=')
            env_main[k] = v

gemini_key = env_main.get('QGPT_API_KEY', '')
gemini_url = env_main.get('QGPT_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
gemini_model = env_main.get('QGPT_MODEL', 'gemini-2.5-flash-lite')

print(f"Gemini URL: {gemini_url}")
print(f"Gemini model: {gemini_model}")
print(f"Key present: {'yes' if gemini_key else 'no'}")

# Dodaj do .env.local
env_local_path = '/opt/qbot/app/.env.local'
with open(env_local_path) as f:
    env_local = f.read()

additions = []
if 'QGPT_ANALYTICAL_BASE_URL' not in env_local:
    additions.append(f'QGPT_ANALYTICAL_BASE_URL={gemini_url}')
if 'QGPT_ANALYTICAL_API_KEY' not in env_local:
    additions.append(f'QGPT_ANALYTICAL_API_KEY={gemini_key}')
if 'QGPT_ANALYTICAL_MODEL' not in env_local:
    additions.append(f'QGPT_ANALYTICAL_MODEL={gemini_model}')

if additions:
    with open(env_local_path, 'a') as f:
        f.write('\n' + '\n'.join(additions) + '\n')
    print(f"Added to .env.local: {additions}")
else:
    print("Already present in .env.local")
