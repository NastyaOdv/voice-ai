# Code Simplifier

Review changed code for simplicity, reuse, and clarity. Quality only — not bug hunting.

## Look for

- **Duplication** — extract shared logic; reuse existing helpers instead of new ones.
- **Dead code / unused params** — remove them.
- **Over-engineering** — no abstraction layers, config, or generality the current
  scope doesn't need. (Matches the project rule: don't over-engineer Level 1.)
- **Naming** — `snake_case` functions, no leading underscore, intention-revealing names.
- **Deep nesting** — prefer early returns / guard clauses.

## Rules

- **DO NOT** change behavior while simplifying — tests must stay green.
- **ALWAYS** run the tests after refactoring.
- Prefer deleting code over adding it.
