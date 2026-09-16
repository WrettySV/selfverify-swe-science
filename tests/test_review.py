from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import time
import unittest
from unittest.mock import patch

from selfverify.agent import AgentBudgetExceeded, SelfVerifyCodex
from selfverify.contract import finalize, run_contract_loop
from selfverify.logging import RunLogger
from selfverify.review import actionable_findings, validate_review
from test_contract_integration import Environment
import test_contract as fixtures


def report():
    return {"requirements": [{"id": "R1", "requirement": "double every input",
            "basis": "task instruction", "status": "violated",
            "evidence": "source/calc.py returns a constant for every input"}],
            "findings": [{"id": "F1", "requirement_id": "R1",
            "claim": "zero maps to six", "basis": "double(0) must be zero by definition",
            "evidence_type": "code", "evidence": "source/calc.py:1 unconditionally returns 6",
            "suggested_change": "multiply the input by two"}]}


class ReviewEvidenceTests(unittest.TestCase):
    def test_runtime_failure_is_not_a_confirmed_counterexample(self):
        audit = report()
        audit["findings"][0].update(evidence_type="experiment", probe="test_zero.py")
        for status in ("runtime_error", "timeout", "pass", "invalid_test"):
            with self.subTest(status=status):
                actionable, rejected = actionable_findings(audit, {"results": [{"path": "test_zero.py", "status": status}]})
                self.assertEqual(actionable, [])
                self.assertEqual(len(rejected), 1)
        actionable, _ = actionable_findings(audit, {"results": [{"path": "test_zero.py", "status": "assertion"}]})
        self.assertEqual(len(actionable), 1)

    def test_finding_needs_a_requirement_and_specific_evidence(self):
        audit = report()
        audit["findings"][0]["basis"] = ""
        with self.assertRaises(ValueError):
            validate_review(audit)


class ReviewFlowTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    snapshot = fixtures.RuntimeTests.snapshot

    def test_code_review_repairs_even_when_every_existing_check_passes(self):
        self.run_flow("accept")

    def test_optimistic_reviewer_cannot_override_an_executable_regression(self):
        self.run_flow("regression")

    def test_no_findings_keeps_original_patch(self):
        self.run_flow("clean")

    def test_unresolved_requirement_is_not_a_clean_review(self):
        self.run_flow("uncertain")

    def test_review_cannot_modify_candidate_source(self):
        self.run_flow("mutated_review")

    def test_partial_saved_review_survives_a_stage_timeout(self):
        self.run_flow("audit_timeout")

    def test_missing_recheck_keeps_original_patch(self):
        self.run_flow("recheck_timeout")

    def run_flow(self, case):
        async def run():
            (self.work / "source/calc.py").write_text("def double(x): return 6\n")
            initial_snapshot = self.snapshot("initial.patch")
            initial = self.root / "initial"
            initial.mkdir()
            shutil.copyfile(self.root / "initial.patch", initial / (self.work.name + ".patch"))
            subprocess.run(["git", "-C", str(self.work), "reset", "--hard", self.prepared["baseline"]],
                           check=True, capture_output=True)
            guards = self.root / "guards" / self.work.name
            guards.mkdir(parents=True)
            files = fixtures.suite_files()
            manifest = json.loads(files["manifest.json"])
            manifest["tests"] = manifest["tests"][:1]  # double(3) == 6 already passes.
            (guards / "manifest.json").write_text(json.dumps(manifest))
            (guards / "test_bug.py").write_text(files["test_bug.py"])
            agent = object.__new__(SelfVerifyCodex)
            agent.logs_dir = self.root / "logs"
            agent.logs_dir.mkdir()
            agent.artifacts = {"revisions": 0}
            agent.verification_mode = "review"
            agent.initial_patches = str(initial)
            agent.regression_suites = str(guards.parent)
            agent._deadline = time.monotonic() + 300
            agent.finalize_reserve_sec = 10
            agent.review_timeout_sec = 10
            agent.review_recheck_timeout_sec = 10
            agent.repair_timeout_sec = 10
            agent.verify_timeout_sec = 2
            stages = []

            async def codex(environment, **kw):
                stage = kw["stage"]
                stages.append(stage)
                cwd = Path(kw["cwd"])
                if stage in {"review_audit", "review_recheck"}:
                    self.assertNotEqual(cwd, self.work)
                    self.assertTrue((cwd / "candidate.patch").is_file())
                    target = cwd / "selfverify/review/report.json"
                    target.parent.mkdir(parents=True)
                    if stage == "review_audit":
                        self.assertEqual((cwd / "source/calc.py").read_text(), "def double(x): return 6\n")
                        audit = report()
                        if case in {"clean", "uncertain"}:
                            audit["findings"] = []
                            audit["requirements"][0]["status"] = "satisfied" if case == "clean" else "uncertain"
                        target.write_text(json.dumps(audit))
                        if case == "mutated_review":
                            (cwd / "source/calc.py").write_text("def double(x): return 2*x\n")
                        if case == "audit_timeout":
                            raise AgentBudgetExceeded("timed out after saving a useful report")
                    else:
                        if case == "recheck_timeout":
                            raise AgentBudgetExceeded("no completed recheck")
                        target.write_text(json.dumps({"findings": [{"id": "F1", "status": "resolved",
                            "evidence": "reviewer's claimed evidence from source/calc.py"}]}))
                elif stage == "review_repair":
                    self.assertIn("zero maps to six", kw["instruction"])
                    body = "def double(x): return 0\n" if case == "regression" else "def double(x): return 2*x\n"
                    (self.work / "source/calc.py").write_text(body)
                else:
                    self.fail(f"unexpected model stage {stage}")

            agent._codex_exec = codex
            environment = Environment()
            logger = RunLogger(agent.logs_dir)
            with patch("selfverify.contract.discover_workdir", return_value=str(self.work)):
                await run_contract_loop(agent, "double every input", environment, {}, logger)
            await finalize(agent, environment, logger)
            state = agent.artifacts["contract"]
            self.addCleanup(shutil.rmtree, state["scratch"], True)
            review = state["review"]
            self.assertEqual(review["guard_before"]["public"]["status"], "pass")
            self.assertEqual(review["guard_before"]["results"][0]["status"], "pass")
            self.assertNotIn("contract_tests", stages)
            if case == "clean":
                self.assertEqual(review["stop_reason"], "clean_review")
            if case == "uncertain":
                self.assertEqual(review["stop_reason"], "inconclusive_review")
            if case == "audit_timeout":
                self.assertFalse(review["stage_completion"]["review_audit"])
            if case in {"accept", "audit_timeout"}:
                self.assertTrue(review["decision"]["accepted"])
                self.assertEqual(agent.artifacts["revisions"], 1)
                self.assertEqual((self.work / "source/calc.py").read_text(), "def double(x): return 2*x\n")
            else:
                self.assertEqual(state["selected"]["sha256"], initial_snapshot["sha256"])
                self.assertEqual((self.work / "source/calc.py").read_text(), "def double(x): return 6\n")
            self.assertEqual(state["selected"]["sha256"], agent.artifacts["final_patch_guard"]["sha256"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
