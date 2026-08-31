---
description: Turn a spec into a bite-sized implementation plan
argument-hint: <feature-name>
---

Create an implementation plan for the feature: **$ARGUMENTS**

1. Read the spec at `.claude/specs/$ARGUMENTS.md` (ask for it if missing).
2. Follow `.claude/skills/write-plan/SKILL.md`.
3. Write the plan to `.claude/plans/$ARGUMENTS.md`: numbered tasks of 2-5 min each,
   each with exact file paths and a verify command, ordered Red-Green-Refactor,
   plus risks / open questions and a "Done when" checklist.
4. Do NOT write code yet. Output the plan, then stop for review.
