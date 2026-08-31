# Systematic Debugging

**DO NOT** apply fixes before you understand the root cause.

## Phases

1. **Root-cause investigation (NO fixes yet).** Reproduce reliably. Read the actual
   error and stack trace. Gather facts: inputs, logs, state. Locate the exact line.
2. **Pattern analysis.** Is this a one-off or a class of bug? Does the same mistake
   exist elsewhere?
3. **Hypothesis testing.** Form one hypothesis. Change ONE thing. Observe. Repeat.
   Do not shotgun multiple changes at once.
4. **Implementation.** Write a failing test that reproduces the bug, then fix it,
   then confirm the test goes green.

## Rules

- **ALWAYS** reproduce before fixing.
- **ONE change at a time** during hypothesis testing.
- **ALWAYS** land a regression test with the fix.
- If you can't reproduce it, you don't understand it yet — keep investigating.
