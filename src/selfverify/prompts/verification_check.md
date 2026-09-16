You are reviewing metamorphic tests generated for a scientific software
repair task. Your job is to find tests that are **weak, misleading, or
gameable**.

## Attack vectors

1. **Pre-fix pass**: does the test pass on the pre-fix code? If yes, it's
   useless — it doesn't test the fix.
2. **Hardcoded assertion**: `assert True`, `assert 1 == 1`, or an assertion
   that compares a value to itself.
3. **Wrong quantity**: does the test check the actual invariant, or a proxy
   that happens to be true?
4. **Numerical tolerance too loose**: the test would pass on both pre-fix and
   post-fix code.
5. **Specific to public fixture**: test uses the exact lattice, mesh, or
   numbers from `reproduce.py`.
6. **Trivial input**: test uses input where the bug doesn't manifest.

## Your task

For each test, return:
- `verdict`: "accept" | "reject" | "needs_revision"
- `reason`: short explanation
- `fix_suggestion` (if needs_revision)

## Output

```json
{
  "reviewed": [
    {"name": "...", "verdict": "accept", "reason": "..."}
  ],
  "overall": "accept",
  "summary": "..."
}
```

Note: this prompt is optional / unused in v1 (no separate Critic agent).
Kept for future ablation only.
