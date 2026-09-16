> Historical modes are described below. The current default is documented in
> [contract-verification.md](contract-verification.md).

# Pier `name` vs `import_path` gotcha

Pier’s `AgentFactory.create_agent_from_config` does:

1. If `name` is a **builtin** agent (`codex`, `claude-code`, …) → load that class.
2. Else if `import_path` is set → load the custom class.

So this combination **silently ignores** the custom agent:

```text
--agent codex --agent-import-path selfverify.agent:SelfVerifyCodex
```

Additionally, Pier’s CLI **rejects** non-builtin `--agent` values, so we cannot
pass a fake name to force branch 2.

## Fix in this repo

`scripts/pier-sv` wraps the Pier CLI and patches
`AgentFactory.create_agent_from_config` to **prefer `import_path` when set**.

`scripts/run_experiment.py` (selfverify condition) passes:

```text
--pier-bin scripts/pier-sv
--agent codex
--agent-import-path selfverify.agent:SelfVerifyCodex
```

## Smoke check after one trial

```bash
ls results/.../task_*/agent/codex_draft.txt \
   results/.../task_*/agent/codex_invariants_r0.txt \
   results/.../task_*/agent/selfverify_summary.json
```

Also expect **>1** rollout under `agent/sessions/` (draft + invariant stages).

## Pipeline gates (three small fixes)

1. **`no_tests_generated`**: empty invariant list is not success; skip feedback.
2. **Public smoke gate**: run `python reproduce.py` after draft; one public-revise
   turn if it fails; skip invariants if still failing.
3. **`max_verify_rounds: 3`** by default (see `configs/selfverify.yaml`).
4. **Discriminator gate** (fail@pre): after generating tests the harness
   reverts the patch, runs invariants on pre-fix, restores the patch.
   Only tests that **FAIL on pre-fix** count. If none do → `test_rewrite.md`.
   Patch `feedback.md` runs only when valid tests still fail on post-fix.
