Your draft repair failed the **public smoke test** (`python reproduce.py`).

This is a cheap gate before self-verification. Do **not** generate metamorphic
tests yet. First make the public reproduction succeed.

## Public test result

```
exit_code: {exit_code}
command: {command}

stdout:
{stdout}

stderr:
{stderr}
```

## Instructions

1. Diagnose why `reproduce.py` failed (import error, crash, non-finite report,
   wrong workflow path, etc.).
2. Fix the implementation under the task workdir so `python reproduce.py`
   returns exit code 0.
3. Do not hard-code fixture outputs or weaken/delete `reproduce.py`.
4. Do not spend time writing metamorphic / invariant tests in this turn.

When done, leave the workspace in a state where `python reproduce.py` should
pass, and briefly summarize what you changed.
