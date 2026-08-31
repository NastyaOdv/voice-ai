# Write Plan

Turn a spec into an executable plan of **bite-sized tasks (2-5 min each)**.

## Rules

- **ALWAYS** break work into tasks small enough to finish and verify in a few minutes.
- Each task states: exact file path(s), what to change, and the command to verify.
- Order tasks to follow **Red-Green-Refactor** — a test task precedes its code task.
- Call out risks, unknowns, and decisions that need the user before coding.
- **DO NOT** bundle unrelated changes into one task.

## Output

Write to `.claude/plans/<feature>.md` with:

1. **Goal** — one sentence, linked to the spec.
2. **Tasks** — numbered checklist, each with file paths + verify command.
3. **Risks / open questions.**
4. **Done when** — the acceptance checks that close the feature.
