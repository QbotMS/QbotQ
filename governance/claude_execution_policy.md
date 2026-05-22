# Claude Execution Policy

This document defines what Claude (via OpenCode) is allowed and not allowed to do
when executing a QBot task spec.

## Claude may

- Inspect files and directories in the QBot workspace.
- Propose changes or implementation plans for review.
- Implement changes explicitly requested in a QBot task spec.
- Report missing data, missing modules, or missing configuration.
- Run tests and verification commands listed in the task spec.
- Produce a final report matching the format required by the task spec.

## Claude may not

- Invent architecture outside the task spec.
- Silently create new data locations or storage backends.
- Migrate data without an explicit migration step in the task spec.
- Store non-garage data in Garage (see data_routing.md).
- Assume missing values; state when data is unavailable.
- Use fake data unless the task explicitly allows fixtures.
- Change public behavior (APIs, MCP tools, user-facing output) without
  matching acceptance criteria in the task spec.
- Commit, push, or deploy unless the task spec explicitly requests it.
- Change runtime behavior unless the task spec includes acceptance criteria
  that require it.
- Invent a storage path, schema, or module when the registry does not define
  one.

## Before any write operation

1. Confirm the target module and data routing rule.
2. If the target module does not exist yet, stop and report.
3. Do not write to Garage unless the data is bike hardware, parts, service,
   wear tracking, or mechanical setup as defined in data_routing.md.

## Task spec as source of truth

Every Claude session working on QBot must reference a QBot task spec.
If a generated task spec exists for the work, use it.
If no task spec exists, Claude must report that and wait for one to be created
before implementing changes.
