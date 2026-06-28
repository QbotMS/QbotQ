# Qbot External LLM Mode

## Architecture
- **ChatGPT Plus external** — main reasoning and answer synthesizer (no API)
- **Qbot API** — source of truth, policy engine, tool executor, artifact store
- **DeepSeek/OpenCode Go** — code implementation assistant only (NOT primary reasoning)

## Model hierarchy
| Model | Role | API enabled |
|---|---|---|
| ChatGPT Plus | Primary reasoning, answer synthesis, planning | No (external session) |
| Qbot (internal) | Source of truth, policy, execution, audit | N/A |
| DeepSeek/OpenCode | Code implementation, tests, refactor | Optional |

## Workflow
1. Generate context bundle: `qbot_external_context_bundle`
2. Generate prompt pack: `qbot_chatgpt_prompt_pack`
3. Paste into ChatGPT Plus session
4. ChatGPT suggests Qbot actions
5. Return decision to Qbot: `qbot_chatgpt_decision_record_create`

## Security
- No secrets in prompts
- No API keys exposed
- Qbot validates all tool execution
- ChatGPT never executes directly
