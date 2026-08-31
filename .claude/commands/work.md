---
description: Implement the next task(s) from a plan, test-first
argument-hint: <feature-name>
---

Implement the plan for: **$ARGUMENTS**

1. Open `.claude/plans/$ARGUMENTS.md` and find the next unchecked task.
2. Follow `.claude/skills/test-driven-development/SKILL.md`: RED (failing test) →
   verify RED → GREEN (minimal code) → verify GREEN → REFACTOR.
3. Honor coding conventions: `snake_case` functions, no leading underscore,
   type hints, English only.
4. After each task: run the fast checks (`ruff`, `mypy`, `pytest -m "not integration"`),
   then tick the task in the plan.
5. Stop and report if you hit an open question or a decision that needs the user.
