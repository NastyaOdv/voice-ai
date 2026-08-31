---
description: Draft a feature spec in .claude/specs/
argument-hint: <feature-name> [short description]
---

Write a feature specification for: **$ARGUMENTS**

Steps:
1. Ask any clarifying questions ONLY if the request is ambiguous on scope or behavior.
2. Write the spec to `.claude/specs/<feature-name>.md` with these sections:
   - **Problem** — what user need this serves (tie back to the English-tutor goal).
   - **Scope** — in / out of scope. Respect the locked decisions in CLAUDE.md
     (Level 1, grammar-only, Python + FastAPI).
   - **Behavior** — inputs, outputs, and the key rules (esp. the pipeline contract:
     `spoken_reply` vs `corrections`).
   - **Contracts** — API shape / data models (Pydantic) touched.
   - **Acceptance criteria** — concrete, testable checks.
   - **Open questions** — anything needing the user's decision.
3. Do NOT write code. Output only the spec file, then summarize it.
