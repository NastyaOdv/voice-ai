# Test-Driven Development

**ALWAYS** write code test-first. No production code without a failing test first.

## The cycle

1. **RED** — write the smallest failing test for the next bit of behavior.
   Run it. **Verify it fails** for the expected reason.
2. **GREEN** — write the minimal code to make it pass. Run it. **Verify it passes.**
3. **REFACTOR** — clean up while keeping tests green.

## Rules

- **DO NOT** write production code before a failing test exists.
- **DO NOT** write more of a test than needed to fail; more code than needed to pass.
- **ALWAYS** run the test between RED and GREEN — an unobserved failure is not RED.
- One behavior per test; name tests after the behavior (`test_<behavior>`).

## This project (Python + FastAPI)

- Framework: `pytest`. Mark slow/cross-service tests with `@pytest.mark.integration`
  so the commit hook skips them (it runs `-m "not integration"`).
- Test FastAPI routes with `httpx.AsyncClient` / `TestClient`.
- Mock the STT/LLM/TTS service boundaries behind their interfaces — don't hit real
  models in unit tests.
