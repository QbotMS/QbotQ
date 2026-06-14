"""modules/nutrition/manifest.py — manifest modułu nutrition (domena zamknięta)."""

MANIFEST: dict = {
    "name": "nutrition",
    "domain": "closed",          # fast-path deterministyczny, bez Plannera

    # Keywordy dla core/router (docelowo zastąpią wpisy w INTENT_KEYWORDS)
    "keywords": [
        # write — muszą być przed read żeby nie wpaść w daily_balance
        "dodaj posilek", "dodaj posiłek", "zapisz posilek", "zapisz posiłek",
        "dodaj jedzenie", "loguj posiłek", "wpisz posiłek",
        "batonik", "baton", "przekąska", "snack",
        "zjadlem", "zjadłem", "zjadłam", "spożyłem", "spożyłam",
        # read
        "bilans", "balance", "kalorii", "kalorie", "kcal",
        "jedzenie", "jadło", "posiłek", "meal", "żywność", "spożycie",
        "meal_logs", "intake_logs", "lista posiłków", "co jadłem",
        "nutrition status", "status nutrition",
    ],

    # Intenty read obsługiwane przez ten moduł
    "read_intents": [
        "daily_balance", "nutrition_day", "nutrition_range",
        "nutrition_intake_logs_list", "nutrition_status",
        "write_meal", "write_delete_unsupported",
    ],

    # Akcje write → generują allowlistę action_execute
    "write_actions": [
        "nutrition_log_add",
        "nutrition_log_delete",
        "nutrition_log_correct",
    ],

    # Testy regresyjne (smoke queries)
    "smoke_queries": [
        "ile kalorii zjadlem dzisiaj",
        "bilans kcal wczoraj",
        "co jadlem dzisiaj",
        "nutrition status",
    ],
}
