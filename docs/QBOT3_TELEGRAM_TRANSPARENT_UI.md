# QBot3 Telegram Transparent UI Contract

## Core Principle

Telegram is NOT a parser of commands. Telegram adapter is a **transparent transport layer**:
```
Telegram message → qbot.query / Albert → response
```

## Forbidden

1. **Telegram-specific if/else parser** — no intent classification in Telegram code
2. **Telegram command router as brain** — no decision-making in Telegram adapter
3. **Nutrition fallback in Telegram** — no domain logic in Telegram layer

## Contract

- Telegram adapter adds metadata: `source: telegram`, `chat_id`, `timezone`
- Telegram adapter passes message raw to `qbot.query` — NO modification
- Telegram adapter renders `final_llm.answer` as `sendMessage`
- Telegram adapter NEVER interprets message content

## Current State (2026-05-28)

### What exists

| Component | Lines | Status |
|---|---|---|
| `qbot_telegram_client.py` | 96 | KEEP — low-level HTTP client |
| `qbot_telegram_tools.py` | 1436 | REVIEW — tools for transport config ok, but `_tool_qbot_telegram_agent_chat` (line 722) is LEGACY |
| `qbot_api.py` (webhook) | ~300 | REVIEW — routes use `_tool_qbot_query` for natural language, but also have domain-specific endpoints |
| `telegram_reply_processor.py` | 309 | LEGACY — not used |

### What to change

1. **Remove** `_tool_qbot_telegram_agent_chat` — it has its own brain logic
2. **Keep** `_tool_qbot_telegram_transport_status`, `_config_status`, `_webhook_plan` — these are transport tools
3. **Add** `qbot3/adapters/telegram_adapter.py` — thin wrapper:
   ```python
   def handle_telegram_message(chat_id, text, timezone="Europe/Warsaw"):
       return orchestrate_query(text, context={"source": "telegram", "chat_id": chat_id, "timezone": timezone})
   ```
4. **Wire** webhook to call `handle_telegram_message` instead of `_tool_qbot_telegram_agent_chat`

### Migration Safety

- Current natural language path already uses `_tool_qbot_query` (wired in earlier fix)
- Fallback to QBot2 via `QBOT3_ENABLED=0` flag
- No risk of double-write — Telegram is read-only in draft phase

## Audit Checklist

- [ ] No `if "jadłem"` in Telegram code
- [ ] No `if "Garmin"` in Telegram code
- [ ] No `if "kalendarz"` in Telegram code
- [ ] No `_parse_nutrition_draft()` call from Telegram
- [ ] No `_parse_event_draft()` call from Telegram
- [ ] All domain logic goes through `qbot.query` → Albert
