# Cross-Candidate Verification for Scientific Software Repair

**Report v2 — evidence snapshot, 2026-09-16.** This is a separate report; [REPORT.md](REPORT.md) remains unchanged. Experiment 1 is complete. Experiment 2 is ongoing: **25/27 branches scored**, using the saved result update **2026-09-16T16:20:18.148171+00:00**. This document is a static snapshot, not the live dashboard.

## Abstract

Generated tests can agree with an incorrect scientific-software patch. We study whether applying tests across different repair candidates adds useful selection evidence, and whether own-generated tests provide actionable feedback for refinement. We distinguish three research stages: retrospective selection analysis, new verifier generation on a fixed candidate pool, and a planned end-to-end evaluation.

In the retrospective eight-task analysis, foreign-only voting achieves **41.15% task-macro expected reward**, versus **30.68%** for uniform selection among public-passing candidates. This historical variant counts every unsuccessful test execution as a rejection; an additional gated assertion-only sensitivity analysis achieves **36.98%**. These numbers do not describe the same policy as the current runtime-abstaining implementation.

In the ongoing nine-task diagnostic, cross-selection improves mixed-pool expected reward on tasks 007 (33.33% to 50.00%) and 053 (66.67% to 100.00%). However, these values equal the empirical quality of the original baseline candidates on those tasks: 50.00% and 100.00%, respectively. The gains recover quality lost by adding an incorrect historical selfverify candidate; they do **not** establish superiority over the baseline solver. No own-suite refinement call has been triggered in the recorded snapshot. Full, matched-budget end-to-end superiority remains untested.

## 1. Research question and method

The question is whether verification generated around different candidate patches can improve the choice of a final patch, and how this differs from using verification to repair the same candidate.

For task t, let p_i denote candidate i and S_j the suite generated while inspecting donor p_j. After generation, the suite is saved and frozen. The harness executes S_j against p_i to construct a matrix M[i,j]. **Frozen means immutable during evaluation, not that tests were written manually or generated before the experiment.** Experiment 2 generates new suites now.

- **Self-conditioned refinement (A):** use the diagonal M[i,i] to provide own-suite feedback and optionally repair p_i. Recheck the revised patch with exactly the same tests. Keep the revision only after observable improvement without losing prior passes or public success.
- **Cross-candidate selection (B):** use foreign entries, i != j, to select among the original candidate patches. Do not vote using the donor's own suite. B in these experiments selects; it does not synthesize a new patch or select among refined outputs.

Suites are donor-conditioned, not independent patch-blind verifiers. Separate sessions do not imply statistically independent errors. Private benchmark rewards are used to score selected candidates after label-free decisions, never as selector or repair inputs.

### Current execution architecture

An outer controller schedules three branches per task through Pier. Each branch has a separate Docker task environment and uses Qwen3.8-27B. Four model endpoints on GPU 4–7 serve up to four branches concurrently. Frozen test execution uses CPU and fresh repository copies inside each branch's container. There is no LLM judge in the selector.

The current selector admits a suite only when execution on unfixed source has at least one assertion failure and no nonsemantic failures. On a candidate, all-pass gives an accept vote, assertion failures give a reject vote, and nonsemantic failures make that suite/candidate cell unknown. Each suite contributes at most one vote per candidate. Public-passing candidates are preferred; mean available foreign votes rank candidates with votes. If no eligible candidate has a usable vote, the selector falls back to public-random selection, or all candidates if none pass public. Ties are evaluated uniformly.

Expected reward averages hidden labels over tied candidates and then equally over tasks. It is not a realised count of submitted solves. A's reported value is the mean of donor refinement outcomes; B's is selection from a pool. Their costs differ, so they are not a matched-budget A/B comparison.

## 2. Experiment 1: retrospective cross-selection

### Data and purpose

The existing matrix contains **8 tasks, 76 candidates, 21 suites and 280 suite/candidate executions**. Tasks: `001, 004, 007, 008, 017, 024, 039, 094`. Candidates and suites came from heterogeneous historical runs, including archived artifacts. This is an availability-based development set, not a prospective random sample. It establishes whether the stored tests contain selection information; it is not a uniformly generated end-to-end benchmark.

The matrix hash is `701f1a8f9d2504d6f20d23515ff3c36972d1e68d7722d8254b452689bf0141b9`. The analysis makes no new model calls. Selector decisions use an allowlist of execution observations; hidden labels are joined afterwards. Historical generation should not be attributed to one uniform configuration without a per-artifact provenance audit.

### Selection results

| Policy | Task-macro expected reward |
| --- | ---: |
| Uniform candidate | 29.85% |
| Public random | 30.68% |
| First public (stored order) | 37.50% |
| Voting including self | 39.58% |
| Foreign-only voting; nonzero = reject | 41.15% |
| Foreign-only + baseline/split gate | 41.15% |
| Gated assertion-only sensitivity | 36.98% |
| Oracle pool ceiling (uses hidden labels) | 50.00% |

Foreign-only voting improves over public random by **10.47 percentage points** and over voting including self by **1.56 percentage points** using unrounded values. These are within-pool comparisons, not sequential gains from successively trained or improved solvers.

| Task | Correct / candidates | Public random | Foreign-only voting |
| --- | ---: | ---: | ---: |
| 001 | 0/12 | 0.00% | 0.00% |
| 004 | 6/10 | 66.67% | 62.50% |
| 007 | 2/6 | 33.33% | 66.67% |
| 008 | 0/12 | 0.00% | 0.00% |
| 017 | 5/11 | 45.45% | 100.00% |
| 024 | 5/5 | 100.00% | 100.00% |
| 039 | 0/5 | 0.00% | 0.00% |
| 094 | 0/15 | 0.00% | 0.00% |

The aggregate improvement comes from 007 and 017; 004 deteriorates. Four tasks have no correct candidate and cannot benefit from selection. Task 024 has only correct candidates. Improvements are therefore concentrated in a small number of mixed pools.

### Distinguish the failure policies

The **41.15%** `cross_vote` policy rejects a candidate on any unsuccessful test execution; failed patch application and empty observations are unknown. It does **not** implement general runtime-error abstention.

`cross_baseline_split` additionally requires the suite to reject unfixed source and to both accept and reject foreign candidates; it also achieves 41.15% here. `cross_baseline_split_assertion_only` applies that gate plus a rule making a suite/candidate outcome unknown when a failing test is not an assertion; it achieves 36.98%. The latter is a gated sensitivity analysis, not an isolated error-policy ablation against ungated `cross_vote`, and not exactly Experiment 2's selector. The policies differ on task 007 in this dataset. A runtime exception may indicate either a real defect or an invalid generated test; this result does not settle which classification is scientifically correct.

## 3. Experiment 2: new suites on a fixed nine-task pool

### Subset and candidate provenance

Tasks: **`001, 007, 008, 017, 024, 039, 053, 094, 107`** — nine Python repositories covering nine catalog scientific-domain labels. Starting from the existing 12-task panel, we exclude 033 for high observed execution/repeated-verification cost, 004 because the primary pipeline lacks a validated native rebuild path, and 014 because it shares DESC and the same base commit with 008, which has lower observed execution cost. All remaining eligible tasks are retained, including all-fail pools. See [selection rationale](docs/task-selection-verification-python-9.md).

There are three distinct source patches per task. Selection uses current-project nonarchive artifacts, baseline first, then lexicographic trial order, deduplicating source hashes without reward-based selection. All recorded candidate models are Qwen3.8-27B. Eight tasks contain two baseline candidates and one historical selfverify candidate; 094 contains three baseline candidates. Patches were saved on September 13–15. Historical harnesses and costs differ. No historical suite is supplied to the new test generators.

This is **one pool per task**, not three independent full-experiment repetitions. The subset was fixed before this run but after historical outcomes were seen. It is not unseen-task evaluation.

### Protocol and budgets

For each donor, generate a new suite, freeze it, execute it against all three original candidates, and optionally attempt one own-suite repair. Failed generation remains an outcome; no replacement suite is silently substituted. Up to 27 generation branches and 81 cross-evaluation cells are planned.

New inference uses Qwen3.8-27B, xhigh, Codex 0.154.0. Limits: 1800 seconds per suite-generation call, 900 seconds for one repair, 60 seconds per verification script, 6000 seconds per agent and 8400 seconds per outer job. These are time caps, not matched token budgets. The controller saves session usage and flags incomplete usage; full cost accounting must also include historical candidate generation.

Frozen code and inputs are recorded under `work/verification-python9-v1/`; the active agent class is `implementation/src/selfverify/paired.py:PairedVerification`. The generic README `--verification-mode contract` command is a different single-candidate test-design/refinement workflow and does not reproduce this three-candidate experiment.

### Interim results

| Task | Original baseline candidates | Public random, mixed pool | A: donor outcome mean | B: cross expected reward | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| 001 | 0/2 (0.00%) | 0.00% | 0.00% | 0.00% | complete |
| 007 | 1/2 (50.00%) | 33.33% | 33.33% | 50.00% | complete |
| 008 | 0/2 (0.00%) | 0.00% | 0.00% | 0.00% | complete |
| 017 | 2/2 (100.00%) | 100.00% | 100.00% | 100.00% | complete |
| 024 | 2/2 (100.00%) | 100.00% | 100.00% | 100.00% | complete |
| 039 | 0/2 (0.00%) | 0.00% | 0.00% | 0.00% | complete |
| 053 | 2/2 (100.00%) | 66.67% | 66.67% | 100.00% | complete |
| 094 | 0/3 (0.00%) | 0.00% | 0.00% | 0.00% | complete |
| 107 | 2/2 (100.00%) | 100.00% | pending | pending | in progress |

The baseline column uses only the baseline members of the selected pool and reports their observed successes/attempts. It is an empirical reference, not a same-cost competing arm. Public-random selection uses all three mixed-pool candidates.

**Critical comparison:** task 007 changes from baseline labels `[0,1]` to the mixed pool `[0,1,0]`. Cross-selection raises expected reward from 1/3 to 1/2, matching the original baseline mean. Task 053 changes from `[1,1]` to `[1,1,0]`; cross-selection restores 2/3 to 1. These observations demonstrate selection signal within the mixed pool, not a gain over the original baseline solver.

No final nine-task aggregate for A or B is reported while task outcomes are pending. In particular, Experiment 1's 41.15% must not be compared with an incomplete or differently constituted Experiment 2 aggregate as method progress.

### Verification and refinement outcomes

At this snapshot: **25/27 scored branches**, **18 saved usable suites**, **54 matrix cells**, **0 refinement attempts**. Validation errors among completed branches: `expected 1-5 invariants`: 3; `no assertion`: 4. These are recorded validator messages, not independently audited root causes; for example, `no assertion` need not mean no files were produced or that no alternative checking construct was present.

Own tests have not supplied actionable failure feedback in usable completed branches. Thus there is no measured improvement from refinement and no evidence here about the success rate of an actual repair call. The observed bottleneck is obtaining discriminative feedback. On 024, all three suites are unusable; 100% selection reward is fallback performance because all original candidates are correct.

On 017, all current candidates are correct, unlike the mixed 11-candidate pool in Experiment 1. Its 100% therefore does not replicate the earlier selection gain. Removing correct candidates from a tie also warrants checking false rejections rather than assuming all generated constraints are valid.

## 4. What the evidence supports

The retrospective matrix contains some foreign-test selection signal. New suite generation also produces such signal on 007 and 053, but the current gains are relative to degraded mixed pools and do not establish baseline superiority. Own-suite success can coexist with hidden-test failure, suppressing refinement. Suite generation and validity are separate bottlenecks from candidate generation.

The research sequence is: **retrospective evidence → new-verifier diagnostic → fresh end-to-end validation**. It is not a claim that every protocol change improves performance. The two completed/ongoing datasets should remain separate tables; observations overlap in tasks and historical artifacts, so they are not independent replications to pool into one score.

## 5. Limitations and next experiment

Both studies use previously inspected tasks and correlated candidates/suites. Small purposive subsets do not estimate full-benchmark accuracy. Historical private labels score B; a standalone artifact replay should revalidate those labels against the exact frozen source patches. Current B reporting evaluates uniform ties but does not export and regrade one sampled final patch.

There is also an implementation limitation for A: foreign patches are uploaded after suite freezing but before repair, so they are accessible in the repair sandbox even though supplied feedback is own-suite-only. Before a clean self-conditioned comparison, repair must run before foreign uploads or in a fresh isolated sandbox. No repair has occurred at this snapshot, so this has not affected an observed repair outcome; it still limits the protocol as implemented.

The planned end-to-end experiment must:

1. Generate all candidate patches using one declared baseline protocol from clean repositories, avoiding the current baseline/selfverify mixture.
2. Compare public-random and cross-selection on the same fresh candidate pools; assess self-refinement in a separately defined arm.
3. Match an explicit **total inference budget**, charging all candidate, suite and repair calls. Report actual input/output tokens, wall time and missing measurements. Equal per-branch time limits are insufficient.
4. Export one final patch per method/run with a declared tie policy, then invoke hidden grading only after selection.
5. Use repeated independent runs with a prespecified task set and stopping rule; report task-level uncertainty, failures and regressions. Existing development exposure remains disclosed even with fresh generations.

This full nine-task end-to-end experiment is **not yet launched**. A contract variant that generates tests before seeing a patch is a possible separately named ablation, not an interchangeable implementation of the current donor-conditioned method.

## 6. Reproduction and evidence

The frozen evidence for this report is in [analysis/report-v2-snapshot-20260916](analysis/report-v2-snapshot-20260916/): historical audit, current report snapshot, current manifest and checksums. The original REPORT.md and README.md hashes are recorded in `snapshot.json` and were preserved when v2 was written.

**Recompute the historical selector statistics** from the saved matrix (no model calls):

```bash
python3 scripts/cross_candidate_audit.py
python3 -m unittest discover -s tests -p 'test_cross_candidate_audit.py' -v
```

This recalculates the audit; it does not regenerate patches/tests or execute tests again.

**Inspect Experiment 2:** [live report](work/verification-python9-v1/report.md), [run protocol](docs/verification-python9-v1.md), and its frozen manifest/code. Per-trial artifacts contain suites, matrix rows, private grading and session usage. After the active service finishes, its report can be rebuilt on this workstation with:

```bash
/home/lukina/.local/share/uv/tools/datacurve-pier/bin/python \
  work/verification-python9-v1/run.py --report-only
```

This updates the live report, not this v2 snapshot. Do not run it concurrently with the controller because both write the same live report paths.

**Replay versus regeneration:** replaying saved patches/tests needs clean benchmark images and the frozen artifacts; regenerating suites needs a new output directory and model calls; reproducing a complete solver needs fresh candidate generation as well. The current machine-specific controller is not yet a portable end-to-end reproduction package. Publish a parameterized runner and nonsecret artifact bundle before claiming one-command full reproduction. See [scope and reproduction notes](docs/experiment-scope-and-reproduction.md).

## 7. Conclusion

Cross-candidate verification can provide useful selection evidence beyond public-test status on the studied candidate pools. The available evidence does not yet show that it outperforms a baseline solver at equal cost. The current diagnostic exposes a concrete refinement bottleneck: own-generated tests may pass incorrect patches and therefore never trigger repair. The next test is a fresh, uniformly generated, budget-controlled comparison that separates candidate quality from verifier selection quality.

## Disclosure

New verifier inference uses local Qwen3.8-27B through Codex and Pier. Codex assisted implementation, analysis and this report. Numerical results are derived from saved machine-readable artifacts; the historical macro statistics were recomputed when this report was prepared. No claim of novelty relative to the literature is made here without a separate related-work review.
