# QBot Task Spec

## Task ID
TS-YYYY-MM-DD-AAA

## Context
Garage was historically used as a broader data store. Under the current routing
policy, Garage is restricted to bike hardware, parts, service, wear tracking,
and mechanical setup. This task audits current Garage usage and routing
references without migrating any data.

## Goal
Produce a read-only audit report identifying:
- Current Garage usage that should be routed elsewhere.
- Hardcoded Garage paths or references.
- Missing module support that blocks proper routing.

## Scope
- Inspect Garage usage and references in the workspace.
- Classify data against `data_registry/modules.yaml` and `governance/data_routing.md`.
- Produce a report for follow-on task specs.

## Out of scope
- Do not migrate data.
- Do not change the Garage format or schema.
- Do not move or delete files.
- Do not create module storage or runtime behavior.
- Do not modify Python runtime files.

## Files to inspect
- `AGENTS.md`
- `QBOT_INSTRUCTIONS.md`
- `QBOT_CURRENT_STATE.md`
- `governance/data_routing.md`
- `governance/claude_execution_policy.md`
- `data_registry/modules.yaml`
- `data_registry/routing_rules.yaml`

## Required data
- Current Garage usage summary, if available from existing local artifacts.
- Routing rules and module registry content.
- File search results for Garage-related references.

## Allowed changes
- Read-only inspection plus a final audit report artifact if requested.

## Forbidden changes
- Writing to runtime Python files.
- Modifying Garage data or schema.
- Changing data formats or moving files.

## Implementation steps
1. Read the routing policy, registry, and local instructions.
2. Search for Garage references and note any hardcoded data sinks.
3. Classify misrouted or ambiguous data against the registry.
4. Report missing module support and blocked assumptions.
5. Write the audit report only if the task spec explicitly requires it.

## Tests
- Verify file inspection completes without requiring network or secrets.
- Verify the report includes findings, missing modules, and next steps.

## Acceptance criteria
- [ ] Audit scope is clear and read-only.
- [ ] Missing module support is reported instead of guessed.
- [ ] Garage migration is not performed.
- [ ] The final report follows the required format.

## Final report format
1. Summary of what was audited.
2. Findings by module and by file reference.
3. Missing modules or blocked assumptions.
4. Recommended next QBot Task Spec.
