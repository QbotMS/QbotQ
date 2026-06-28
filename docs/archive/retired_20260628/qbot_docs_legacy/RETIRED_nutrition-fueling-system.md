# QBot Nutrition / Fueling System

## Architektura

```
LLM / Telegram
    ↓
nutrition_intake_parser  (qbot_nutrition_parser.py)
    ↓
food lookup / resolver   (qbot_nutrition_parser.py → _lookup_food)
    ↓
PostgreSQL               (qbot_nutrition_db.py)
    ↓
daily summary            (nutrition_daily_summary)
    ↓
QBot analytics
```

## Pliki

| Plik | Rola |
|---|---|
| `/opt/qbot/app/sql/nutrition_fueling_store_v1.sql` | Schema: 6 tabel |
| `/opt/qbot/app/qbot_nutrition_db.py` | CRUD DB (psycopg 3, datetime→ISO) |
| `/opt/qbot/app/qbot_nutrition_parser.py` | NLP parser: regex, aliasy, fuzzy PL deklinacje, ILIKE fallback |
| `/opt/qbot/app/qbot_nutrition_tools.py` | 10 tool functions |
| `/opt/qbot/app/scripts/seed_nutrition_foods.py` | 38 seedowanych produktów |
| `/opt/qbot/app/qbot_api.py` (linie ~712-830) | FastAPI endpointy /nutrition/* |
| `/opt/qbot/app/qbot_mcp_adapter.py` (linie ~708-835) | 10 MCP tools w _MCP_TOOL_MAP |
| `/opt/qbot/app/qbot_tool_registry.py` (linie ~290, ~1540, ~1880) | Rejestracja tools |

## Tabele PostgreSQL (qbot)

| Tabela | Opis |
|---|---|
| `food_items` | Produkty spożywcze (38 seed) — name UNIQUE |
| `meal_logs` | Posiłki (eaten_at, meal_type, note) |
| `meal_log_items` | Składniki posiłków (FK → meal_logs + food_items) |
| `hydration_events` | Picie (fluid_ml, sodium_mg) |
| `fueling_events` | Carbs na trasie (carbs_g, context) |
| `nutrition_daily_summary` | Agregat dzienny (kcal, carbs, protein, fat, fluids...) |

## Narzędzia MCP (port 8002)

```jsonc
// ALL READ_ONLY:
"qbot.nutrition_status"          — liczba rekordów we wszystkich tabelach
"qbot.nutrition_food_search"     — wyszukaj produkt (ILIKE)
"qbot.nutrition_food_list"       — lista produktów

// WRITE_SAFE:
"qbot.nutrition_food_create"     — dodaj produkt (name, kcal_per_100g, ...)
"qbot.nutrition_intake_parse"    — parsuj tekst NL bez zapisu (READ_ONLY)
"qbot.nutrition_intake_log"      — parsuj + zapisz do DB (WRITE_SAFE)
"qbot.nutrition_hydration_log"   — zapisz picie (WRITE_SAFE)
"qbot.nutrition_fueling_log"     — zapisz fueling (WRITE_SAFE)
"qbot.nutrition_day_summary"     — podsumowanie dnia (READ_ONLY)
"qbot.nutrition_meal_list"       — lista posiłków z dnia (READ_ONLY)
```

## FastAPI endpointy (port 8002)

```
POST /nutrition/intake/text           — log meal/hydration/fueling z NL
POST /nutrition/intake/telegram       — to samo dla Telegram
POST /nutrition/foods                 — dodaj produkt
GET  /nutrition/foods/search?query=   — wyszukaj produkt
POST /nutrition/meals                 — dodaj posiłek (explicit items)
POST /nutrition/hydration             — dodaj picie
GET  /nutrition/day/{date}?recompute= — podsumowanie dnia
POST /nutrition/import/cronometer/servings-csv — import CSV Cronometer
```

## Przykład użycia

MCP tools/call:
```json
{
  "name": "qbot.nutrition_intake_log",
  "arguments": {
    "text": "śniadanie: 200 g skyru naturalnego, banan, 40 g płatków owsianych, 300 ml kawy",
    "meal_type": "breakfast"
  }
}
```

FastAPI:
```bash
curl -X POST http://127.0.0.1:8002/nutrition/intake/text \
  -H "Content-Type: application/json" \
  -d '{"text":"200 g skyru, banan, 40 g płatków","meal_type":"breakfast"}'
```

## Cronometer

- NIE jest wymagany do działania systemu
- Opcjonalny import historii: `POST /nutrition/import/cronometer/servings-csv`
- QBot = source-of-truth

## Seed produktów (38)

skyr naturalny, banan, jabłko, płatki owsiane, jajko, jajecznica, bułka pszenna, chleb razowy, ryż biały gotowany, makaron pełnoziarnisty gotowany, pierś z kurczaka, łosoś atlantycki, twaróg półtłusty, jogurt naturalny, mleko 2%, masło orzechowe, orzechy włoskie, oliwa z oliwek, miód, czekolada gorzka 70%, odżywka białkowa, kreatyna, żel energetyczny, izotonik, batony energetyczne, awokado, pomidor, ogórek, brokuł, szpinak, ser żółty, szynka drobiowa, kasza gryczana gotowana, ziemniaki gotowane, bataty gotowane, kawa czarna, sok pomarańczowy, woda

Ponowne seedowanie: `cd /opt/qbot/app && source .env.local && export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=qbot PGUSER=qbot PGPASSWORD=qbot_dev_password && .venv/bin/python scripts/seed_nutrition_foods.py`

## Restart serwisu

```bash
systemctl restart qbot-api
```

## Stan z 2026-05-26

- Wszystkie testy przeszły pomyślnie
- Parser poprawnie obsługuje polskie deklinacje (skyru→skyr, płatków→płatki, kawy→kawa)
- 41 produktów w bazie (38 seed + 3 testowe)
- 7 posiłków, 6 napojów, 1 fueling w bazie testowej
