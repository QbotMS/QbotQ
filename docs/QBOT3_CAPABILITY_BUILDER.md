# QBot3 Capability Builder — Internal Capabilities

## Public MCP Tools vs Internal Capabilities

| | Public MCP Tools | Internal Capabilities |
|---|---|---|
| Exposed to ChatGPT/UI | `qbot.query`, `qbot.action_execute` | Never exposed directly |
| Entry point | MCP `tools/list` | `qbot.query` → Albert → capability registry |
| Definition | In `qbot3/tool_registry.py` | In `qbot3/capabilities/*/` |
| Safety | READ_ONLY + WRITE (with confirm) | READ_ONLY only (WRITE = proposal only) |
| When to use | User-facing read/write operations | Internal diagnostics, file reads, DB queries, report status |

## Capability Lifecycle

```
missing ──→ draft ──→ tested ──→ active ──→ disabled
                ↑                        ↓
           (proposal)              (disabled)
```

### States

| State | Allowed | Can be used by qbot.query | Requires |
|---|---|---|---|
| `draft` | READ_ONLY_FILE, READ_ONLY_DB | Only `plan_only`/debug | Manifest |
| `tested` | READ_ONLY_FILE, READ_ONLY_DB | Only `plan_only`/debug | Manifest + tests |
| `active` | READ_ONLY_FILE, READ_ONLY_DB, READ_ONLY_API | ✅ Yes | Manifest + tests + validated |
| `disabled` | None | ❌ No | — |

### Auto-buildable types

Albert może automatycznie zbudować tylko:
- `READ_ONLY_FILE` — czyta plik(i) i zwraca dane
- `READ_ONLY_DB` — wykonuje zapytanie SELECT i zwraca wyniki

`WRITE` capabilities mogą być tylko `draft`/proposal i wymagają ręcznej akceptacji.
Destructive operations (DELETE, UPDATE, raw SQL) są blokowane bez osobnej jawnej zgody.

## Capability Contract

```python
class MyCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="my_capability",
            description="What this capability does",
            safety_class="READ_ONLY",
            capability_type="READ_ONLY_FILE",
            data_sources=["file1.json", "file2.log"],
            promotion_state="draft",  # draft → tested → active
            inputs_schema={},         # optional
            output_schema={           # expected output shape
                "type": "object",
                "properties": {"status": {"type": "string"}},
            },
            reason_existing_insufficient="Why existing capabilities can't handle this",
        )

    def run(self, context: dict) -> dict:
        # No side effects for READ_ONLY
        return {"status": "OK", "data": {}}
```

## Directory Structure

```
qbot3/capabilities/
├── __init__.py           # Registry loader
├── base.py               # CapabilityDef, Capability ABC
├── manifest.py           # Manifest validation, promotion checks
├── test_harness.py       # Test harness
├── system/
│   ├── __init__.py
│   └── daily_report_status.py  # Example active capability
├── nutrition/
│   ├── __init__.py
├── calendar/
│   ├── __init__.py
└── routes/
    ├── __init__.py
```

## How CAPABILITY_MISSING Works

1. Albert/LLM planuje intent, ale `tools_to_call=[]`
2. `plan_validator` wykrywa `mode=read_only` i brak tooli
3. Sprawdza capability registry:
   - Jeśli capability istnieje i jest `active`: wykonuje capability
   - Jeśli capability istnieje ale nie jest `active`: zwraca `CAPABILITY_MISSING` z info
   - Jeśli capability nie istnieje: zwraca `CAPABILITY_MISSING` z propozycją
4. Runtime odpowiada: "Brak capability dla X. Propozycja: utwórz X_status."

## Adding a New Capability

```bash
# 1. Create the capability file
cat > qbot3/capabilities/system/my_status.py << 'EOF'
from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY

class MyStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(name="my_status", ...)
    def run(self, context):
        return {"status": "OK", "data": {}}
EOF

# 2. Create tests
cat > tests/test_capability_my_status.py << 'EOF'
# Test that manifest is valid, run has no side effects, etc.
EOF

# 3. Run test harness
python3 -m qbot3.capabilities.test_harness --capability my_status

# 4. Promote to active
# In manifest, change promotion_state to "tested" after tests pass
# Change to "active" after validation
```

## Test Harness

```bash
# Test all capabilities
python3 -m qbot3.capabilities.test_harness

# Test specific capability
python3 -m qbot3.capabilities.test_harness --capability daily_report_status
```

The harness validates:
- Import works
- Manifest is valid (name, description, safety_class, etc.)
- `run()` returns dict with no side effects (for READ_ONLY)
- No secrets in output
- Promotion state is valid
