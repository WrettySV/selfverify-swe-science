Your patch may have passed the public reproduction, and you have at least one
**valid** metamorphic test (it **failed on pre-fix**). But some valid tests
still **FAIL on the current (post-fix) tree**.

That usually means the patch is incorrect / incomplete. Less often, a valid
discriminator is overly strict — then fix or replace that test.

## Failed discriminator tests (post-fix)

{failed_test_results}

## Instructions

1. These tests already failed on pre-fix (discriminator gate). Prefer fixing
   the **patch** so they pass now.
2. Only change a test if you can show it is wrongly specified (not the bug).
3. Do not hard-code fixture values. Do not weaken/delete `reproduce.py`.
4. Leave the workspace in the state you want evaluated (final sources + tests).
5. Update `selfverify/invariants/manifest.json` if tests changed.

## Output

Return a short JSON object in your final message:

```json
{
  "diagnosis": "why valid tests still fail post-fix",
  "actions": ["what you changed"],
  "confidence": 0.0
}
```
