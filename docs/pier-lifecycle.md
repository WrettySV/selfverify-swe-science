> Historical modes are described below. The current default is documented in
> [contract-verification.md](contract-verification.md).

# Pier Codex lifecycle — where self-verify hooks in

Read from `datacurve-pier==0.3.0`:
`pier/agents/installed/codex.py` and `scripts/pier_adapters.py`.

## Stock `Codex.run()`

1. Create `$CODEX_HOME` (`/tmp/codex-home`) and auth/config.
2. Append `config.toml` (gateway + optional overrides).
3. Run **one** `codex exec … -- <instruction>`.
4. Copy `$CODEX_HOME/sessions` → agent logs.
5. **Delete** `$CODEX_HOME` in `finally`.

`model.patch` is **not** created inside `run()`. Pier’s task hook
`pre_artifacts.sh` runs after the agent exits and writes
`artifacts/model.patch` as a git diff against the image baseline.

`ScienceBenchCodex` only patches `install_spec()` (npm `--include=optional`).
It does not change `run()`.

## Real public helpers we use

From `BaseInstalledAgent` / `Codex` (not invented):

- `exec_as_agent(environment, command=…, env=…)`
- `exec_as_root(…)`
- `build_process_env(…)`
- `build_cli_flags()`
- `_resolve_auth_json_path()`
- `populate_context_post_run(context)` (unchanged; reads session JSONL)

There is **no** `_emit_patch` API.

## `SelfVerifyCodex` strategy

We **override `run()`** (do not call `super().run()`, because it nukes
`$CODEX_HOME` after the first exec). Inside one Pier trial:

1. Setup Codex home (same as stock).
2. **draft** — `codex exec` with the task instruction.
3. Loop up to `max_verify_rounds`:
   - **invariant_gen** — `codex exec` with `prompts/invariant_generation.md`
   - **verify** — Pier runs `selfverify/invariants/invariant_*.py` via
     `environment.exec` (non-zero exit allowed)
   - if all pass → break
   - **feedback** — `codex exec` with `prompts/feedback.md`
     (stage name: feedback / revise-in-session — **not** a separate agent)
4. Persist sessions, cleanup Codex home.
5. Return; Pier collects `model.patch` from the final workspace.

Same container, same worktree, same Pier trial. Multiple `codex exec`
turns share one `$CODEX_HOME` for the duration of `run()`.
