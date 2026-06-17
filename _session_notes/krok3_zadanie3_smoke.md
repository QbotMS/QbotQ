Krok 3 smoke - 2026-06-15

Endpoint: https://qbot.cytr.us/mcp/

Wynik startowy:
- `initialize` -> 200 OK, `mcp-session-id` zwrocony.

Blokada:
- `tools/call` dla `qbot.query` zwraca 403 Forbidden bez poprawnego publicznego sekretu MCP.
- Próba z lokalnym `QBOT_DEV_MCP_TOKEN` nie odblokowala `qbot.query`.
- Z tego powodu 5 zaplanowanych zapytan nie zostalo wykonanych.

Uwagi:
- Token nie zostal zapisany do repo ani do notatek.
- Kod po stronie repo pozostaje bez commit.
