# Development Workflow & Discipline

Stack for this project: **Python + FastAPI** (microservices).

> **Git is manual.** The user runs `git commit` / `git push` herself and owns them.
> Claude does NOT commit, push, open PRs, or install git hooks.

## Workflow

**ALWAYS** follow this workflow for feature development:

```text
/write-spec -> /write-plan -> /review-spec -> /work   (then the user commits & pushes)
```

| Phase     | Command                    | Output                     |
|-----------|----------------------------|----------------------------|
| Spec      | `/write-spec`              | `.claude/specs/<feature>.md` |
| Plan      | `/write-plan`              | `.claude/plans/<feature>.md` |
| Implement | `/work`                    | Code changes               |
| Worktree  | `claude --worktree <name>` | Isolated workspace         |

### Before Writing Code

1. Read the spec in `.claude/specs/` (or create one with `/write-spec`).
2. Read relevant skills in `.claude/skills/` (see `SKILLS.md` index).
3. Create a plan with `/write-plan`.
4. Review the plan / spec with `/review-spec`.

## Development Discipline Skills

### When Planning Implementation
**`/write-plan`** — Break work into bite-sized tasks (2-5 min each), include exact
file paths and commands, follow the Red-Green-Refactor cycle.

### When Writing Code
**`/test-driven-development`** — RED: write a failing test. Verify RED. GREEN:
minimal code to pass. Verify GREEN. REFACTOR. **No production code without a
failing test first.**

- **Typing / contracts:** use type hints everywhere and let `mypy` check them.
  Prefer explicit Pydantic models / Protocols over `Any` or unchecked casts.
  Prefer runtime invariant checks and explicit contracts.

### When Encountering Bugs
**`/systematic-debugging`** — Phase 1: root-cause investigation (NO fixes yet).
Phase 2: pattern analysis. Phase 3: hypothesis testing (one change at a time).
Phase 4: implementation with a failing test.

## Rules Are Directives

Files in `.claude/skills/` contain **DO NOT** and **ALWAYS** rules. These are not
suggestions.

**Development Discipline:**
- `skills/test-driven-development/SKILL.md`
- `skills/systematic-debugging/SKILL.md`
- `skills/write-plan/SKILL.md`
- `skills/code-simplifier/SKILL.md`

Full index: `.claude/skills/SKILLS.md`.

## Checks (run manually)

There are no automated git hooks. Before you commit, run the fast checks yourself:

```bash
ruff format --check .
ruff check .
mypy .
pytest -m "not integration"
```

Keep slow/integration tests for a fuller local run or CI.

## Key Resources

| Resource                      | Purpose                                       |
|-------------------------------|-----------------------------------------------|
| `.claude/skills/SKILLS.md`    | Categorized skill index                       |
| `.claude/specs/`              | Feature specs                                 |
| `.claude/plans/`              | Implementation plans                          |
| `.claude/WORKFLOW.md`         | This file                                     |
