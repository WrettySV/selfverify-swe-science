# Task selection: verification-python-9

## Decision

Use **001, 007, 008, 017, 024, 039, 053, 094, 107** as the main nine-task panel. These cover nine distinct repositories and nine catalog domain labels. Task 004 is a supplementary native-language case pending a validated clean rebuild before each cross-evaluation. Tasks 014 and 033 are excluded for the reasons below. This file fixes the task list; it does not launch experiments.

## Sampling frame and motivation

The local benchmark catalog contains 119 tasks, of which 96 have license_gate=none. The parent main-12 panel was itself a convenience/purposive selection from an earlier 16-task multi-domain pilot. Its stated motivations included chemistry, biology, plasma, medicine and mathematics, accessible task images, and reuse across experiments. We do not retrospectively describe this as stratified random sampling from all 119 tasks.

The main study uses the current Python test execution path. Merely applying a C++ source diff does not guarantee that a test invokes a rebuilt binary; supporting 004 correctly requires a separate explicit build step. Restricting the primary result to Python makes candidate application and verification consistent across tasks.

To reduce correlated coverage, keep one task per repository. Tasks 008 and 014 both use DESC at the same base commit. Select 008 using observed baseline execution cost: median about 29 minutes, versus 90 minutes for 014. The two tasks both have zero scored baseline successes; success was not used to decide which to retain.

Task 033 is excluded by the user-declared resource constraint. Both baseline attempts reached about 90 minutes of agent execution; verifier execution then took about 10 and 13.5 minutes. In a cross matrix this repeated evaluation cost matters separately from model generation cost. This is a documented task-specific exclusion, not a fabricated universal 90-minute threshold.

Tasks 053 and 107 also have long baseline executions, but their verifier runtimes are about 0.4 minutes and they remain distinct medical-geometry and symbolic-algebra cases. Task 039 is retained for earth-surface transport coverage despite slower agent execution and zero recorded successes. Task 094 is retained despite zero recorded successes; baseline agent runs took only about 9 minutes. Old selfverify stalls (such as 172 minutes in invariant generation) are not a reliable intrinsic task-cost measure.

## Audit table

Agent times below are historical Qwen3.8 baseline medians. They include time-limited agent executions; they are not predictions for the new protocol. Missing rewards remain missing rather than being silently counted as success or failure.

| Task | Domain | Agent median, min | Agent timeouts / recorded trials | Scored successes | Decision |
|---|---|---:|---:|---:|---|
| 001 | computational-reaction-chemistry | 27.6 | 0/2 | 0/2 | included |
| 004 | rna-seq-genomic-interval-semantics | 46.3 | 0/2 | 2/2 | supplementary_native |
| 007 | magnetic-resonance-spectroscopy | 33.2 | 0/2 | 1/2 | included |
| 008 | plasma-stability | 29.0 | 0/2 | 0/2 | included |
| 014 | plasma-stability | 90.0 | 3/3 | 0/2 | excluded_duplicate_repository |
| 017 | gamma-ray-astronomy-dark-matter | 32.6 | 0/2 | 2/2 | included |
| 024 | probabilistic-scientific-computing | 46.9 | 0/2 | 2/2 | included |
| 033 | periodic-electronic-structure | 90.1 | 2/2 | 0/2 | excluded |
| 039 | earth-surface-dynamics-and-river-sediment-transport | 72.4 | 0/2 | 0/2 | included |
| 053 | medical-image-segmentation-geometry | 81.6 | 1/2 | 2/2 | included |
| 094 | condensed-matter-magnetism-and-magnetic-symmetry | 9.3 | 0/3 | 0/3 | included |
| 107 | computer-algebra | 90.0 | 2/2 | 2/2 | included |

## Why retain both zero-solve and all-solve tasks?

The selector cannot recover a correct solution when its candidate pool contains none. Removing such tasks would conceal this generation ceiling. All-correct pools measure unnecessary rejection or damage from refinement. Mixed pools measure discrimination directly. Report these slices diagnostically, but calculate the primary macro-average over the full fixed panel. Historical outcomes are not eligibility requirements.

## Development exposure and model comparison

Outcomes and traces from this panel have already informed development; 017 was used for paired-pilot debugging, 008 for generation recovery, and 053 for repeated materialization diagnostics. New runs must use a frozen protocol and fresh attempts for an end-to-end comparison, but fresh attempts do not turn these tasks into an unseen-task holdout. Report the nine-task aggregate plus a predeclared aggregate excluding 017, and disclose that the latter still contains development-exposed tasks. A broader generalisation claim would need additional tasks selected from the remaining catalog before observing their results.

The supplied Qwen3.6 table is external contextual evidence. Its overlap with this panel is 001, 008, 017, 053 and 107. Do not combine its rewards or averages with Qwen3.8 results. A direct method comparison requires the same model, candidates/attempt policy, task IDs, harness and cost accounting.

## Report-ready wording

> We evaluate on a resource-constrained, purposively selected subset of nine Python tasks from nine scientific repositories in SWE-bench Science. Starting from an existing 12-task development panel, we retain tasks executable through a common Python verification pipeline and limit coverage to one task per repository. We exclude task 033 because of its high observed execution and repeated-verification cost; task 004 requires a native rebuild path outside the primary pipeline. Of two tasks sharing the same DESC repository and base commit, we retain the lower-cost task 008. All other eligible panel tasks are retained, including tasks with zero historical solves and tasks whose available baseline candidates all pass. The subset and protocol are fixed before the next evaluation runs. Historical development exposure is disclosed; results are exploratory and are not claimed to represent full-benchmark accuracy.

## Files and next steps

- Selection: `selections/verification-python-9.json` (compatible with materialize_tasks.py).
- Evidence, including individual trial paths/hashes and actual materialized image references: `analysis/task-selection-20260916/evidence.json`.
- Flat audit table: `analysis/task-selection-20260916/evidence.csv`.
- Apply this panel identically to A, B and continuation controls. Freeze budgets separately; a wall-clock cap is not equal inference budget.
- Reuse historical patches for inexpensive selection diagnostics, recording their provenance; charge candidate generation when making end-to-end budget claims.
- Keep unsuccessful generation, invalid tests, timeouts and missing scores visible in the final report.
