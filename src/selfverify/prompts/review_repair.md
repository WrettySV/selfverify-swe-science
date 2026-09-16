Review the reported defects, then repair the existing candidate implementation.
The original task is supplied separately, along with the review and observed
checks. A review finding is a claim to investigate, not an infallible oracle.

For each finding, verify its public basis and cited code path. Fix supported
correctness defects in source/. If a claim is mistaken, explain the contradiction
with concrete public evidence instead of changing correct behavior to satisfy
it. Preserve already passing checks and the public workflow. The harness will
re-run frozen checks and conduct a fresh review of the original findings.

Optional frozen counterexample scripts are in selfverify/invariants/. You may
execute them, but editing their copies will not alter the harness's checks.
Only change source/. Do not change public reproduction, task fixtures, task
instructions or evaluation infrastructure. Save a runnable patch early and
finish within the stated time budget. Explain the changes and any remaining
uncertainty briefly.
