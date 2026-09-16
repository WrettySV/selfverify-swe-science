# Adaptive Cross-Candidate Verification for Scientific Software Repair

## Abstract

Scientific software patches can pass a public reproduction without restoring
the underlying scientific behavior. This project investigates whether
model-generated scientific tests can improve **selection among multiple repair
candidates**. We implement a label-free cross-candidate verifier that freezes
generated test suites, runs them on other candidates, excludes self-votes,
abstains on unusable failures, and falls back to public-test selection when
there is no reliable signal.

On a motivated eight-task subset of SWE-bench Science containing 76 candidate
patches, 21 generated suites and 280 suite-candidate executions, the proposed
foreign-suite selector obtains 41.15% task-macro expected reward, compared with
30.68% for uniform selection among public-passing candidates. The result is a
10.47 percentage-point improvement on the fixed candidate pool. Because the
study is retrospective and does not match total candidate-generation cost, it
supports a selection result rather than a claim about end-to-end Pass@1.

## 1. Research question

Scientific repair is difficult to verify from a single public example.
Scientific correctness often depends on invariance under equivalent
representations, conservation laws, unit changes, boundary behavior or scaling.
At the same time, a test generated while inspecting one candidate may inherit
that candidate's assumptions.

We therefore ask:

> Can label-free tests generated across independent repair attempts improve
> selection among candidate patches relative to public-test-only selection, and
> can explicit abstention make this selection robust to unusable verifier
> outcomes?

The goal is not to treat generated tests as proof of correctness. The goal is
to extract additional observable evidence before choosing one candidate for
final submission.

## 2. Method

### 2.1 Candidate and verifier pool

For each benchmark task, the method receives multiple candidate patches for the
same original repository and problem statement. A repair attempt also produces
a small suite of scientific or metamorphic checks. Each suite and source patch
is identified by a content hash.

### 2.2 Frozen cross-evaluation

After generation, a suite is frozen and executed against candidates in fresh
environments. Tests are not allowed to modify the source being evaluated.
Outcomes are represented as pass, semantic failure or unknown. Infrastructure
errors and ambiguous runtime failures abstain instead of voting against a
candidate.

### 2.3 Foreign-only voting

A suite never votes for the candidate that conditioned its generation. This
removes the direct diagonal self-consistency advantage. The selector:

1. prefers candidates that pass the public reproduction;
2. aggregates valid votes from foreign suites;
3. ignores unknown outcomes;
4. breaks ties uniformly; and
5. falls back to uniform public selection when no usable foreign evidence is
   available.

No private-test reward is available to generation, execution or selection.
Hidden rewards are joined only after all choices are frozen.

### 2.4 Implementation

The method is implemented as a custom `ScienceBenchCodex` pipeline for Pier:

- `src/selfverify/agent.py` — orchestration and verification modes;
- `src/selfverify/contract.py` — frozen tests, repair feedback and promotion;
- `src/selfverify/contract_runtime.py` — isolated execution and restoration;
- `scripts/cross_candidate_audit.py` — label-free foreign-suite selector;
- `scripts/crosscheck_suites.py` — candidate/suite matrix construction;
- `tests/` — lifecycle, isolation, abstention and diagonal-exclusion tests.

The implementation preserves immutable verifier inputs, restores candidate
source after each execution, records missing and timed-out suites, and keeps
official private tests inside the benchmark verifier.

## 3. Baselines and ablations

We compare on exactly the same frozen candidate pool:

- **Uniform candidate** — choose uniformly from all candidates.
- **Public random** — choose uniformly from public-passing candidates. This is
  the primary baseline.
- **First public** — choose the first public-passing candidate in stored order;
  this measures sensitivity to candidate ordering.
- **Voting including self** — generated-test voting without diagonal exclusion.
- **Foreign-only voting** — the proposed method.
- **Oracle pool ceiling** — whether the pool contains any correct candidate;
  this is an upper bound, not a deployable method.

Uniform ties are scored by expected reward. Consequently, percentages are
expected selection accuracy rather than realised integer solve counts.

## 4. Experimental setup

### 4.1 Benchmark and subset

We evaluate on eight SWE-bench Science tasks:

`001, 004, 007, 008, 017, 024, 039, 094`

This resource-constrained subset contains tasks from distinct scientific
domains and includes all-fail, mixed and all-correct candidate pools. Keeping
all-fail pools is important: it exposes the ceiling imposed by candidate
generation instead of evaluating selection only where a correct answer already
exists.

The experiment contains:

- 8 tasks;
- 76 candidate trials;
- 21 generated suites;
- 280 recorded suite-candidate executions.

### 4.2 Model and harness

- Model: Qwen3.8-27B
- Model weights: `/data/datasets/Qwen/Qwen3.8-27B`
- Serving: vLLM 0.28.0
- Precision: BF16 weights, FP8 KV cache
- Context window: 262,144 tokens
- Agent runtime: Codex through Pier
- Reasoning effort: `xhigh`
- Final metric: official SWE-bench Science binary reward

The selection analysis itself is deterministic and makes no new model calls.
Its input matrix is frozen with SHA256:
`701f1a8f9d2504d6f20d23515ff3c36972d1e68d7722d8254b452689bf0141b9`.

## 5. Results

### 5.1 Aggregate selection quality

| Selection policy | Task-macro expected reward |
| --- | ---: |
| Uniform candidate | 29.85% |
| Public random | 30.68% |
| First public | 37.50% |
| Voting including self | 39.58% |
| **Foreign-only voting (ours)** | **41.15%** |
| Oracle pool ceiling | 50.00% |

The final method improves over:

- uniform candidate selection by 11.30 percentage points;
- the primary public-random baseline by 10.47 points;
- the order-sensitive first-public baseline by 3.65 points; and
- voting including self by 1.57 points.

This progression supports both parts of the design: generated verifier evidence
adds signal beyond public filtering, while removing diagonal self-votes does
not reduce aggregate selection quality and slightly improves it.

### 5.2 Per-task results

| Task | Correct / candidates | Public random | Foreign-only voting |
| --- | ---: | ---: | ---: |
| 001 | 0 / 12 | 0.00% | 0.00% |
| 004 | 6 / 10 | 66.67% | 62.50% |
| 007 | 2 / 6 | 33.33% | 66.67% |
| 008 | 0 / 12 | 0.00% | 0.00% |
| 017 | 5 / 11 | 45.45% | 100.00% |
| 024 | 5 / 5 | 100.00% | 100.00% |
| 039 | 0 / 5 | 0.00% | 0.00% |
| 094 | 0 / 15 | 0.00% | 0.00% |

The aggregate improvement comes from the mixed candidate pools, especially
tasks 007 and 017. Tasks with no correct candidate remain at zero under every
selector, while task 024 is already saturated because every candidate is
correct. Task 004 shows that generated votes are not uniformly beneficial on
every task.

### 5.3 Sensitivity analysis

When a stricter policy discards an entire suite after any non-assertion failure,
foreign voting obtains 36.98%. The difference is isolated to task 007, where
runtime exceptions occur inside the scientific library and may themselves
express the target defect. This motivates explicit failure classification and
abstention rather than treating every nonzero exit identically.

## 6. Critical analysis

The main result answers the fixed-pool research question: generated foreign
tests contain selection information beyond public-test status on this subset.
It does not show that every generated test is scientifically valid, nor that
producing the entire candidate/verifier pool is always the best use of compute.

The pool oracle is 50.00%, so the proposed 41.15% recovers a substantial part
of the selectable reward but cannot overcome missing correct candidates. This
separates two bottlenecks: candidate generation determines the ceiling, while
verification determines how much of that ceiling can be recovered.

## 7. Limitations

1. **Retrospective data.** The eight tasks and stored artifacts were available
   during method development; this is not an unseen holdout.
2. **Fixed-pool scope.** Candidate generation used heterogeneous historical
   runs. The experiment compares selectors on a common pool but does not compare
   equal end-to-end inference budgets.
3. **Small purposive subset.** Eight tasks cannot estimate performance on all
   119 benchmark tasks.
4. **Candidate ceiling.** Four tasks have no correct candidate, and one has only
   correct candidates; only mixed pools directly measure discrimination.
5. **Correlated observations.** The 280 cells reuse candidates and suites and
   are not independent samples.
6. **Verifier ambiguity.** A runtime exception can expose a real defect or an
   invalid generated input. Results depend on the predeclared failure taxonomy.
7. **Expected ties.** Uniform tie-breaking yields expected rewards rather than
   an observed count of selected solves.

A stronger generalisation claim requires fresh tasks selected before observing
their outcomes and a matched total inference budget that charges candidate,
suite and repair generation.

## 8. Conclusion

We proposed and implemented adaptive cross-candidate verification for
scientific software repair. The method combines generated scientific checks
across repair attempts, removes direct self-votes, abstains on unusable
evidence and safely falls back to public selection.

On the fixed eight-task SWE-bench Science pool, foreign-only voting reaches
41.15% expected reward versus 30.68% for public-random selection. The result
shows that generated tests can improve patch selection when treated as noisy
cross-candidate evidence rather than as proof of correctness. The principal
next step is prospective, equal-budget validation on unseen tasks.

## 9. Reproduction and artifacts

The short reproduction guide is in `README.md`.

- Input matrix: `analysis/crosscheck/matrix.json`
- Machine-readable result: `analysis/crosscheck/label_free_audit.json`
- Human-readable result: `analysis/crosscheck/label_free_audit.md`
- Evaluated task list and per-task results: the files above and this report
- Selection implementation: `scripts/cross_candidate_audit.py`
- Tests: `tests/test_cross_candidate_audit.py`

## 10. AI and model disclosure

- Evaluated model: Qwen3.8-27B through local vLLM
- Agent runtime: Codex through Pier
- Cursor was used for implementation assistance and report drafting
- Numerical claims are read from frozen JSON artifacts

## References

1. OpenMOSS. *SWE-bench Science*. arXiv:2608.19799, 2026.
2. Chen et al. *CodeT: Code Generation with Generated Tests*. 2022.
3. *CodeMonkeys: Scaling Test-Time Compute for Software Engineering*. 2025.
4. Salesforce AI Research. *TEX: Test-Time Scaling for Code*. 2026.
