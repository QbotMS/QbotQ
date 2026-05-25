# Qbot Telegram Bot Restore Pack v1

## Architektura

```
Telegram Cloud -> public HTTPS endpoint -> /telegram/webhook/<secret> -> Qbot policy/query -> odpowiedz
```

- Bez ngrok — własny HTTPS endpoint (Cloudflare + nginx reverse proxy)
- Publiczny jest tylko webhook Telegram z sekretną ścieżką
- API /q pozostaje lokalne (127.0.0.1:8001)
- Wszystkie zapytania przez Qbot policy engine

## Dlaczego bez ngrok

Ngrok był używany w starym Qbocie jako tunnel do lokalnego serwera.
Nowa architektura używa własnego public endpointu HTTPS (Cloudflare) z nginx jako reverse proxy.
To eliminuje zależność od zewnętrznego serwisu i zwiększa bezpieczeństwo.

## Wymagane zmienne środowiskowe

Umieść w `/opt/qbot/app/.env.local` (nigdy nie commituj):

```
TELEGRAM_BOT_TOKEN=<bot-token-od-BotFather>
TELEGRAM_ALLOWED_CHAT_IDS=<chat_id_1>,<chat_id_2>
TELEGRAM_WEBHOOK_SECRET=<losowy-długi-sekret>
QBOT_PUBLIC_BASE_URL=https://twoja-domena
TELEGRAM_ENABLED=true
```

Opcjonalne:
```
TELEGRAM_ALLOW_ALL_CHATS=true   # tylko do testów — NIE używaj na produkcji
```

## Jak ustawić public HTTPS endpoint

1. Domena musi wskazywać na serwer (DNS A record → IP serwera)
2. Cloudflare obsługuje HTTPS (certyfikat, proxy)
3. Nginx reverse proxy na serwerze:

```nginx
location /telegram/webhook/ {
    proxy_pass http://127.0.0.1:8001/telegram/webhook/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

4. Ustaw `QBOT_PUBLIC_BASE_URL=https://twoja-domena` w `.env.local`
5. Zrestartuj qbot-api: `systemctl restart qbot-api.service`

## Jak ustawić webhook

1. Sprawdź plan:
```
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_telegram_webhook_plan","args":{}}' | jq
```

2. Ustaw webhook:
```
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_telegram_set_webhook","args":{"execute":true}}' | jq
```

LUB ręcznie:
```
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://twoja-domena/telegram/webhook/<WEBHOOK_SECRET>","secret_token":"<WEBHOOK_SECRET>"}'
```

## Jak sprawdzić webhook info

Usługowo:
```
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_telegram_status","args":{}}' | jq
```

Ręcznie:
```
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

## Komendy Telegram

| Komenda | Opis |
|---------|------|
| /start | Powitanie i lista komend |
| /help | Lista komend |
| /status | Szybki status Qbot |
| /ready | Raport gotowości |
| /smoke | Finalny smoke test |
| /backup | Status backupów |
| /errors | Ostatnie błędy |
| /takeover | Status przejęcia legacy Q |
| /ask <query> | Zapytanie przez Qbot policy engine |

## Security model

1. **Sekretna ścieżka webhook** — tylko znający `/telegram/webhook/<secret>` mogą wywołać endpoint
2. **Secret token header** — opcjonalnie weryfikowany `X-Telegram-Bot-Api-Secret-Token`
3. **Allowed chat IDs** — tylko skonfigurowane chat_id mogą korzystać z bota
4. **Brak CONTROLLED_ACTION** — Telegram nie może wykonać żadnej kontrolowanej akcji
5. **Bez dowolnych komend** — tylko dozwolone komendy i /ask przez policy engine
6. **Brak publicznego /q** — API /q pozostaje na localhost
7. **Tokeny w .env.local** — nigdy nie commituj .env.local, tokeny tylko z env

## Rollback: deleteWebhook

```
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_telegram_delete_webhook","args":{"execute":true}}' | jq
```

LUB ręcznie:
```
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```

## Czego NIE robić

- NIE wystawiaj całego /q publicznie
- NIE używaj ngrok
- NIE commituj .env.local
- NIE loguj tokenów
- NIE używaj TELEGRAM_ALLOW_ALL_CHATS=true na produkcji
- NIE wystawiaj publicznie /docs FastAPI
- NIE zezwalaj na CONTROLLED_ACTION przez Telegram
- NIE dodawaj Gate/HikConnect do Telegram bota

## Jak nie wyciekać tokenów

- Token tylko z env/.env.local, nigdy w kodzie
- Webhook URL nigdy nie logowany z pełnym tokenem
- `qbot_telegram_legacy_audit` pokazuje tylko obecność, nie wartości
- `qbot_telegram_config_status` pokazuje tylko bool-e obecności
- `qbot_telegram_set_webhook` zastępuje secret placeholderem w preview
- `_sanitize` w `qbot_telegram_answer_context` redaguje pola sekretne
- Git: .env.local jest w .gitignore

## Dostępne narzędzia operatorskie

| Narzędzie | Opis |
|-----------|------|
| qbot_telegram_legacy_audit | Audyt starej konfiguracji Telegram/ngrok |
| qbot_telegram_config_status | Status zmiennych TELEGRAM_* |
| qbot_public_endpoint_status | Status publicznego endpointu |
| qbot_telegram_status | Zbiorczy status Telegram bota |
| qbot_telegram_webhook_plan | Plan webhooka |
| qbot_telegram_set_webhook | Ustawienie webhooka (preview/execute) |
| qbot_telegram_delete_webhook | Usunięcie webhooka |
| qbot_telegram_send_test | Testowa wiadomość |
| qbot_telegram_command_help | Lista komend |
| qbot_telegram_answer_context | Bezpieczny kontekst dla LLM |

## Runbooki

- `telegram_restore_review`: audyt + config + endpoint + webhook plan + help
- `telegram_activation_check`: status + endpoint + webhook plan + smoke test
