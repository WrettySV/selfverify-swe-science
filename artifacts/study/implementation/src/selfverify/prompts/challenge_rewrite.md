Your metamorphic suite **passed** the first discriminator gate (fail@pre ∧ pass@post).
That is **not** enough to accept the patch yet.

The harness requires a **second, independent** invariant set before acceptance.
Many first-wave tests only restate the public smoke (`reproduce.py`) and false-accept
patches that later fail the private oracle.

## Your task

Replace `selfverify/invariants/` with a **new** suite of 3–5 tests that:

1. Use **different inputs / regimes** than both the public reproduction and your
   previous suite (new parameters, geometries, units, boundary cases, scales).
2. Still **FAIL on pre-fix** and **PASS on a correct post-fix** (harness will
   re-check).
3. Do **not** import, exec, subprocess, or otherwise call `reproduce.py`.
4. Do **not** hard-code public fixture paths, filenames, or golden numbers copied
   from the public smoke.
5. Prefer scientific invariants (conservation, symmetry, representation
   equivalence, units, boundaries, scaling) that would catch an incomplete fix.

Update `selfverify/invariants/manifest.json`.

## Output

```json
{
  "diagnosis": "why the first suite might false-accept",
  "actions": ["what the new suite probes instead"],
  "confidence": 0.0
}
```
