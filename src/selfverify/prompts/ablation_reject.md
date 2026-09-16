Your metamorphic tests **still passed after a light ablation of the patch**.

The harness temporarily reverted part of your repair; the discriminator tests
kept passing. That means the suite is **too weak** — it does not depend on the
fix strongly enough (often a near-copy of the public smoke).

## Ablation details

{ablation_summary}

## Your task

Rewrite `selfverify/invariants/` (3–5 tests) so that they:

1. **FAIL** if the core repair is removed / weakened.
2. Still **FAIL on full pre-fix** and **PASS on the full post-fix** patch.
3. Use inputs different from `reproduce.py`; never call `reproduce.py`.
4. Update `manifest.json`.

## Output

```json
{
  "diagnosis": "why tests survived ablation",
  "actions": ["what you changed"],
  "confidence": 0.0
}
```
