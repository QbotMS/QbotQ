# Qbot LLM Planner + Policy Engine

## Architecture
```
User query -> LLM Planner (proposes plan) -> Policy Engine (validates) -> Plan Executor (executes approved) -> Answer Synthesizer (summarizes)
```

## Core rule
**LLM proposes, Qbot disposes.** The LLM suggests which tools to use, but Qbot's Policy Engine validates every step before execution.

## Safety classes
| Class | Auto-execute | LLM plan | Description |
|---|---|---|---|
| READ_ONLY | Yes | Yes | Status, logs, reports — safe to auto-run |
| WRITE_SAFE | Yes | Yes | Controlled writes (artifacts to DB) |
| CONTROLLED_ACTION | No | Yes | Backup, restart, cutover — needs approval |
| BLOCKED | No | No | Shell, SQL, file ops, secrets — never allowed |

## Policy validation flow
1. Planner proposes steps (from LLM or rule fallback)
2. Each step checked against tool registry + safety metadata
3. Unknown tools → BLOCKED
4. CONTROLLED_ACTION → REQUIRES_APPROVAL
5. READ_ONLY/WRITE_SAFE → APPROVED_READ_ONLY

## Artifact storage
- Postgres `qbot_artifacts` table
- Max 100 KB per artifact
- Content validated for secrets
- No file system writes in v1

## Workspace write
- PREVIEW_ONLY in v1
- Path validated (no absolute, no `..`, no blocked dirs)
- Content checked for secrets
- Real file writes planned for v2

## Tables
- `qbot_plans` — plan proposals and execution history
- `qbot_artifacts` — artifact storage
- `qbot_memory` — key-value memory

## Example curls
```bash
# Plan a query
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_llm_plan_query","args":{"query":"sprawdź stan qbot i backup"}}'

# Validate a plan
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_policy_validate_plan","args":{"plan":{"steps":[{"tool":"qbot_readiness_report","args":{}}]}}}'

# Execute safe query
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_llm_run_query","args":{"query":"sprawdź stan qbot i backup","execute":true}}'

# Create artifact
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_artifact_create","args":{"title":"Smoke report","content":"All checks passed","artifact_type":"report"}}'
```

## LLM integration
- Real LLM requires `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` env
- Without API key: rule-based fallback planner
- LLM role: answer_synthesizer_only
- LLM NEVER: executes, restarts, edits files, accesses secrets
