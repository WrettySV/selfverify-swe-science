You are designing executable checks from the task's public requirements BEFORE
seeing a candidate repair. The current directory is a disposable copy of the
ORIGINAL source. No candidate patch is available in this stage.

Read the original instruction and relevant public method/source documentation.
Write 2-3 focused Python checks in selfverify/invariants/test_*.py. Include both
the requested behavior and one behavior that must remain unchanged. A test that
passes on the original code is a useful regression check; do not discard it.

For every check, derive its expected result from a quoted public requirement,
an independently evaluated formula, or an analytically tractable example.
Changing an input and merely checking that the output changes is insufficient
when the task requires a particular mathematical operation. Do not use outputs
of the code under test as the expected values. Do not assume generic physics
laws without checking their applicability to this task.

Save your first test and manifest early, then add coverage incrementally. Use
deterministic small inputs; do not spend the entire stage surveying the code.

Create selfverify/invariants/manifest.json with this exact shape:
{"tests": [{"path": "test_example.py", "requirement": "specific behavior",
"basis": "public file/section or independent derivation", "expected": "asserted
relation and justified tolerance", "input": "small counterexample description"}]}

Each file must run with python3 from the task root; use Path.cwd()/source for
imports and relative fixture paths. Use a plain `assert` for a violated
requirement, with expected AND observed values in the message. Import failures,
syntax errors, crashes and timeouts are NOT evidence of a violated requirement.
Run your checks on the ORIGINAL code to verify imports and fixtures. Expected
assertion failures are fine. Helpers may live in the same invariants directory.

Only write selfverify/invariants/. Do not repair source, modify public fixtures,
call reproduce.py from a test, or access evaluation/private tests. The suite
will be frozen after this stage; later repair turns cannot weaken its asserts.
If a requirement cannot be justified from public materials, leave it explicitly
untested rather than inventing an expected result. Keep the suite small.
