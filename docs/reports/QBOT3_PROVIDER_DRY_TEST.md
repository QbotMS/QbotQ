# QBot3 Provider Dry Test — 2026-05-28

## Purpose

Test that QBot3 can work with real OpenAI/DeepSeek providers without making expensive API calls.

## Prerequisites

```bash
# Check if OpenAI key exists
if [ -n "$OPENAI_API_KEY" ] || [ -n "$QGPT_API_KEY" ]; then
    echo "OpenAI provider available"
else
    echo "AUTH_MISSING: No OpenAI API key found"
    echo "Set OPENAI_API_KEY or QGPT_API_KEY in environment"
fi

# Check DeepSeek
if [ -n "$DEEPSEEK_API_KEY" ]; then
    echo "DeepSeek provider available"
else
    echo "AUTH_MISSING: No DeepSeek API key found"
    echo "Set DEEPSEEK_API_KEY in environment"
fi
```

## Dry Test Procedure

### 1. Mock Provider (no API cost)

```bash
export ALBERT_LLM_PROVIDER=mock
python3 -c "
from qbot3.agent_runtime import orchestrate_query
result = orchestrate_query('status qbot')
print(f'Status: {result.get(\"status\")}')
print(f'Orchestrator: {result.get(\"orchestrator\", {})}')
print(f'Fallback: {result.get(\"orchestrator\", {}).get(\"fallback_used\")}')
print(f'Request ID: {result.get(\"request_id\")}')
"
```

**Expected**: status=ok, orchestrator.name=Albert, fallback_used=false, request_id present

### 2. OpenAI Provider (if key exists)

```bash
if [ -n "$OPENAI_API_KEY" ] || [ -n "$QGPT_API_KEY" ]; then
    export ALBERT_LLM_PROVIDER=openai
    python3 -c "
from qbot3.agent_runtime import orchestrate_query
result = orchestrate_query('status qbot')
print(f'Status: {result.get(\"status\")}')
print(f'Confidence: {result.get(\"confidence\")}')
print(f'Plan intent: {result.get(\"plan\", {}).get(\"intent\")}')
print(f'No fallback: {not result.get(\"orchestrator\", {}).get(\"fallback_used\")}')
"
fi
```

**Expected**: status=ok, no hallucinated tools, no legacy references

### 3. DeepSeek Provider (if key exists)

```bash
if [ -n "$DEEPSEEK_API_KEY" ]; then
    export ALBERT_LLM_PROVIDER=deepseek
    python3 -c "
from qbot3.agent_runtime import orchestrate_query
result = orchestrate_query('status qbot')
print(f'Status: {result.get(\"status\")}')
print(f'Provider works: {result.get(\"status\") in (\"ok\", \"partial\")}')
"
fi
```

**Expected**: status=ok or partial

## Safety Rules for Provider Tests

1. **Never expose API keys** in output
2. **Only read_only queries** — no write operations
3. **Never exceed 5 test queries per provider session** to avoid excessive token usage
4. **Use mock provider for development** — real providers only for acceptance testing

## Results

| Provider | Status | Notes |
|---|---|---|
| mock | ✅ Working | Deterministic, no API cost |
| openai | ⏳ Test if OPENAI_API_KEY set | Wraps qgpt_client |
| deepseek | ⏳ Test if DEEPSEEK_API_KEY set | Direct API call |
