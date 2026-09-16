The research turn ended without leaving a usable verifier suite. A bounded
research handoff is included at the end of this prompt.

Your FIRST tool call must create both files below. Do not run ls, find, grep,
cat, sed, git, Python diagnostics, or inspect the source before this first
write. Use the strongest defensible result in the handoff and write:

1. selfverify/invariants/test_<name>.py with at least one plain assert;
2. selfverify/invariants/manifest.json with exactly this schema:

{"tests": [{"path": "test_<name>.py", "requirement": "specific public behavior",
"basis": "public file/section or independent derivation", "expected": "asserted
relation and justified tolerance", "input": "small counterexample description"}]}

One focused test is enough. The test must run with python3 from the task root.
Use Path.cwd()/source for imports and fixture paths. Include expected and
observed values in assertion messages. Do not use the implementation output as
its own expected value. Import failures, crashes, and timeouts are not evidence
of a requirement violation. Do not call or import reproduce.py, access private
tests, modify source/, or write outside selfverify/invariants/.

After the first write, run the saved test once. You may repair only those two
files if needed. Do not broaden the investigation or improve the oracle.
