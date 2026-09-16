Your metamorphic tests were rejected by the **discriminator gate**.

The harness temporarily **reverted your patch** (pre-fix tree), ran every
`selfverify/invariants/invariant_*.py`, then restored your patch.

A test is **valid** only if it **FAILS on pre-fix** (detects the bug).
Tests that **PASS on pre-fix** do not discriminate the bug — they are discarded.

Right now **zero** tests failed on pre-fix, so self-verify cannot judge your
patch. This is a **test-quality** problem, not a signal that the patch is done.

## Pre-fix results (all of these PASSED — weak / invalid)

{weak_test_results}

## Your task

Rewrite the metamorphic suite under `selfverify/invariants/`:

1. Delete or replace weak tests that pass on the buggy pre-fix code.
2. Write 3–5 new tests that would **fail before the fix** and **pass after a
   correct fix**.
3. Prefer scientific invariants from the problem statement (conservation,
   symmetry, representation equivalence, units, boundaries, scaling).
4. Do **not** hard-code the public fixture. Do **not** weaken `reproduce.py`.
5. Optionally stash/revert your patch yourself to confirm fail@pre before
   finishing — the harness will re-check anyway.
6. Update `selfverify/invariants/manifest.json`.

## Output

Return short JSON:

```json
{
  "diagnosis": "why prior tests passed on pre-fix",
  "actions": ["what you changed"],
  "confidence": 0.0
}
```
