---
description: Review a spec/plan before implementation
argument-hint: <feature-name>
---

Review the spec and plan for: **$ARGUMENTS**

Read `.claude/specs/$ARGUMENTS.md` and `.claude/plans/$ARGUMENTS.md` and check:

- **Consistency** with CLAUDE.md locked decisions (Level 1, grammar-only,
  Python + FastAPI, pipeline contract, no over-engineering).
- **Completeness** — are acceptance criteria concrete and testable?
- **Sizing** — is every plan task really 2-5 min with a verify command?
- **Risks** — hidden coupling, missing error handling, unstated assumptions.

Output a short verdict (ready / needs changes) with a bullet list of required fixes.
Do NOT write code.
