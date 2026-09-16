You have just produced a patch that is supposed to repair a scientific
software bug. Your patch may pass the public reproduction. But the public
reproduction is a smoke test — it does not prove that your fix generalizes.

Your task now is to **stress-test your own patch** by generating 3–5
metamorphic tests based on scientific invariants from the problem statement.

## Critical: discriminator requirement (enforced by harness)

The harness will **revert your patch**, run your tests on the **pre-fix**
tree, then restore the patch.

A test counts as **valid** only if it **FAILS on pre-fix** and later **PASSES
on post-fix**.

- PASS on pre-fix → **rejected** (does not detect the bug; often a vacuous
  guard).
- FAIL on pre-fix → kept as a discriminator for judging the patch.

If **zero** tests fail on pre-fix, you will be asked to rewrite the suite.
Do **not** write tests that you know pass on the buggy code.

## What is a metamorphic test

A metamorphic test is a property that must hold for the *general* case,
not just the observed example. Examples:

- **Conservation**: total energy / mass / charge must be conserved.
- **Symmetry**: rotating / translating / permuting inputs must not change
  the physical observable.
- **Representation equivalence**: two mathematically equivalent
  representations must give the same result.
- **Unit consistency**: changing units (Angstrom ↔ Bohr, eV ↔ Hartree)
  must not change the physical conclusion.
- **Boundary behavior**: at zero / infinity / degenerate parameters, the
  result must be finite and match the known limit.
- **Scaling**: changing system size / grid / cutoff must not change the
  answer beyond numerical tolerance.

## Your task

1. Read the original problem statement carefully.
2. Identify the scientific invariant that your patch is supposed to restore.
3. Generate 3–5 metamorphic tests that would **fail on the pre-fix code**
   and **pass on a correct fix**.
4. For each test, write:
   - `name`: short identifier (snake_case)
   - `invariant`: which scientific principle it checks
   - `rationale`: why this test distinguishes correct from incorrect fix
     (explicitly: what fails pre-fix vs post-fix)
   - `code`: a self-contained Python snippet (≤ 30 lines) that:
     - imports from the repo under test
     - runs the relevant computation on **a new input** (not the public fixture)
     - asserts the invariant holds
     - prints "PASS" or raises AssertionError with a clear message

## Constraints (enforced by harness — violations → reject / rewrite)

- Do **NOT** import, exec, subprocess, or otherwise call `reproduce.py`.
- Do **NOT** hard-code the public fixture, its numbers, or its file paths.
- Do **NOT** use private tests (you don't have access anyway).
- Do **NOT** add “guard” tests that pass on both pre-fix and post-fix.
- Each test must use a **different input / regime** than the public smoke
  (new parameters, geometries, units, boundaries, scales).
- Each test must be independently runnable: `python invariant_<i>_<name>.py`.
- Prefer tests that probe **generalization** — new lattice constants,
  new meshes, new unit systems, new boundary conditions.
- If you cannot think of a meaningful discriminating test, say so explicitly —
  do not fabricate a weak always-pass test.
- After a first green wave the harness will demand a **second independent**
  suite and may **ablate** part of your patch; tests that still pass under
  ablation are rejected.

## Output (required)

1. Write each test script under `selfverify/invariants/` in the task workdir
   using the filename pattern `invariant_<i>_<name>.py`.
2. Also write `selfverify/invariants/manifest.json` with this schema:

```json
{
  "invariants": [
    {
      "name": "energy_per_cell_invariance",
      "invariant": "total energy per primitive cell is independent of supercell construction",
      "rationale": "the bug produces a discrepancy; a correct fix must remove it",
      "path": "selfverify/invariants/invariant_0_energy_per_cell_invariance.py"
    }
  ],
  "confidence": 0.8,
  "notes": "I could not test X because Y"
}
```

Print the same JSON object as your final message.
