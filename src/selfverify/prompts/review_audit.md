Audit the existing candidate repair against the original task requirements.
This stage is a review, not a request to implement a new solution.

You are in a disposable copy of the candidate. Read candidate.patch first, then
problem_desc.txt, reproduction.md and the relevant source/documentation. Every
file in source/ already includes the candidate changes. There is no need to
solve the task from scratch or explore unrelated parts of the repository.

Check which requirements the diff actually implements, which paths it misses,
and whether new formulas, assumptions, constants and API behavior have a public
basis. A passing reproduce.py only covers its fixture. Focus on concrete defects
in this patch, not stylistic preferences or imagined requirements. Do not assume
the candidate is wrong. A clean review is an acceptable outcome.

Save selfverify/review/report.json EARLY, after the first focused inspection,
and update it as evidence improves. Do not wait until the end to write it.
Use this exact structure (1-12 requirements, at most 3 findings):
{
  "requirements": [
    {"id":"R1", "requirement":"specific required behavior",
     "basis":"public document/file and location establishing it",
     "status":"satisfied|violated|uncertain",
     "evidence":"source path/line and explanation of implementation or gap"}
  ],
  "findings": [
    {"id":"F1", "requirement_id":"R1", "claim":"specific correctness defect",
     "basis":"public requirement or documented algorithm, with location",
     "evidence_type":"code|experiment",
     "evidence":"exact code path showing the contradiction, or expected/actual observations",
     "suggested_change":"what behavior must change, without guessing unspecified semantics"}
  ]
}

Code evidence is sufficient for a finding when the contradiction is concrete.
You do not have to create a test suite. Mark unsupported suspicions as uncertain
requirements, not findings. Prioritize saving one strong finding over exploring
many possibilities. Use the stage time budget to finish a concise report.

Optional: confirm a suspected defect with a SMALL numerical experiment or
counterexample. For evidence_type="experiment", add "probe":"test_name.py" to
the finding and save an independently runnable assertion script under
selfverify/invariants/, plus manifest.json containing a tests list with path,
requirement, basis, expected and input strings. At most 3 probes total. The
harness will run them on the candidate to confirm the failure. A probe must
assert a requirement with a justified expected result; an import error is not a
counterexample. Do not call/import reproduce.py inside a new probe. Running the
public reproduction yourself and citing its specification are allowed.

Do not modify source/, task files, fixtures or reproduction. Write only under
selfverify/. Do not spend the turn constructing a broad testing framework.
