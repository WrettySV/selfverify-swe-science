# Requirement-based self-verification

`--condition selfverify --verification-mode contract` is the new default.
This protocol is experimental: a green generated suite is evidence, not a
replacement for the official verifier. The first live pilot uses saved baseline
candidates 008 and 094; 004 and 017 are prepared regression controls.

## Lifecycle

1. Save the pristine task tree and a fallback patch. Create a separate design
   directory from the original Git root commit.
2. Give Codex the original instruction and `contract_tests.md`. It creates 1-3
   executable tests, normally 2-3, with public requirements, independent expected
   relations and inputs in a manifest. The candidate patch has not been uploaded.
3. Validate manifest and Python syntax. Reject a design turn that changed source.
   Freeze the files in host memory and save them under `agent/contract/frozen_suite`.
4. Restore the original task worktree; load a saved `task_NNN.patch`, or run a
   bounded draft. A timed-out draft is checkpointed and can still be evaluated.
5. Run the frozen suite on a disposable original tree and on a disposable copy
   with the candidate patch. Run the original public reproduction on the latter.
6. Assertion failures provide feedback only if the same test executes normally
   on the original tree (pass or assertion). Import/runtime errors, timeouts and
   source-mutating tests are classified separately. Passing original tests remain
   regression checks. A public pass alone is not semantic correctness.
7. Give Codex the original instruction plus requirement/input/expected/actual
   evidence. It changes source only. Re-evaluate using the same frozen suite.
8. Promote only if at least one check improves, all previous passes remain,
   public success is preserved, and no new unusable test appears. On no improvement,
   keep the previous checkpoint and stop. Unknown tests remain explicit in reports.
9. Restore the selected source-only patch and verify its SHA-256. Pier then
   creates `model.patch` and runs its separate official verifier.

No private test content or reward is supplied to any online stage. A generated
assertion may still be wrongly specified: a manifest is traceability, not proof.
The repair turn must explain questionable assertions instead of rewriting tests.

Every `codex exec` starts a fresh conversation; sharing CODEX_HOME only preserves
files/configuration. The harness explicitly repeats the original task instruction.

## Budgets and modes

| Setting | Default seconds |
| --- | ---: |
| Total agent budget | 4800 |
| Test design | 900 |
| Draft (omitted for saved candidates) | 1500 |
| One repair turn | 900 |
| One executable test / public reproduction | 120 in CLI |
| Finalization reserve | 180 |

Repair reserves time for re-evaluation. Container-side `timeout` terminates the
Codex process group; a separate asyncio deadline bounds the host wait. Test
subprocess groups are killed on timeout. These limits exclude external verifier
and image setup time. Very expensive native builds may exceed test budgets.

`--max-repair-rounds` defaults to 1. `--max-verify-rounds` belongs to legacy full
mode. `--verification-mode continue --initial-patches ...` is an ordinary Codex
continuation control without generated suites. Match its additional wall budget
to the contract experiment when making effectiveness claims.

`public-only` and `adaptive` retain the earlier public-check path; `full` retains
the historical discriminator/challenge/ablation loop. Legacy launch scripts name
their modes explicitly. YAML files remain documentation, not parsed runtime config.

## Reuse baseline candidates

```bash
python3 scripts/prepare_contract_pilot.py --out work/contract-pilot-new
python3 scripts/run_experiment.py \
  --condition selfverify --verification-mode contract \
  --path work/contract-pilot-new/gpu7 \
  --initial-patches work/contract-pilot-new/patches \
  --env-file ~/.config/swe-bench-science/vllm-qwen38-8001.env \
  --job-name contract-pilot-new-gpu7 --n-attempts 1 --skip-pull
```

Preparation chooses the lexicographically first completed baseline trial per
task, records exact patch and task-config hashes and image references, and rejects
patches that modify files outside source/. Rewards remain in host reporting
metadata. It does not generate a fresh baseline repair.

For the first implementation test, only `first-gpu6/task_008` and
`first-gpu7/task_094` were launched from a frozen code copy under
`work/contract-pilot-v1/implementation`. Its file hashes identify the implementation
used even if the main project changes later. The first snapshot predates the
all-session metrics override: use the report command below for its token totals.

## Reports and validation

```bash
python3 scripts/report_contract_pilot.py \
  --pilot work/contract-pilot-v1 \
  --job results/main/contract-pilot-v1-gpu6 \
  --job results/main/contract-pilot-v1-gpu7 \
  --out analysis/contract-pilot-v1.json

PYTHONPATH=src:$SWE_SCIENCE_ROOT \
  ~/.local/share/uv/tools/datacurve-pier/bin/python -m unittest discover -s tests -v
```

Report 0→1 and 1→0 transitions, actual repair turns, test failures/unknowns,
selected-patch integrity and total tokens across all Codex conversations.
Do not sum cumulative token events within a conversation. Missing usage is
reported, not interpreted as zero-cost inference. Existing private outcomes are
offline labels only; this small, already-inspected task set is a development
pilot, not held-out evidence of a general improvement.
