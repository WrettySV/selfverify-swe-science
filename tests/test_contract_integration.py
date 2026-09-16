from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from selfverify.agent import SelfVerifyCodex, AgentBudgetExceeded
from selfverify.contract import run_contract_loop, finalize
from selfverify.contract_runtime import execute
from selfverify.logging import RunLogger
import test_contract as fixtures


class Environment:
    async def exec(self, *, command, cwd=None, timeout_sec=None, env=None):
        result = await asyncio.to_thread(execute, ["bash", "-c", command], cwd=cwd, timeout=timeout_sec or 180)
        return SimpleNamespace(return_code=result["exit_code"], stdout=result["output"], stderr="")

    async def download_file(self, remote, local):
        shutil.copyfile(remote, local)


class FlowTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    snapshot = fixtures.RuntimeTests.snapshot
    def test_generation_cannot_see_candidate_and_repair_is_promoted(self):
        self.run_flow(saved=True)

    def test_timed_out_draft_is_checkpointed_and_repaired(self):
        self.run_flow(saved=False)

    def test_candidate_design_sees_only_its_donor_and_refines_it(self):
        self.run_flow(saved=True, context="candidate")

    def test_zero_rounds_freezes_suite_without_changing_candidate(self):
        self.run_flow(saved=True, rounds=0)

    def test_timed_out_design_gets_a_materialization_turn(self):
        self.run_flow(saved=True, rounds=0, materialize=True)

    def run_flow(self, saved, context="blind", rounds=1, materialize=False):
        async def run():
            import time
            (self.work / "source/calc.py").write_text("def double(x): return 6\n")
            self.snapshot("initial.patch")
            initial = self.root / "initial"
            initial.mkdir()
            shutil.copyfile(self.root / "initial.patch", initial / (self.work.name + ".patch"))
            subprocess.run(["git", "-C", str(self.work), "reset", "--hard", self.prepared["baseline"]],
                           check=True, capture_output=True)
            agent = object.__new__(SelfVerifyCodex)
            agent.logs_dir = self.root / "logs"
            agent.logs_dir.mkdir()
            agent.artifacts = {"revisions": 0}
            agent.verification_mode = "contract"
            agent.initial_patches = str(initial) if saved else None
            agent._deadline = time.monotonic() + 300
            agent.finalize_reserve_sec = 10
            agent.test_design_timeout_sec = 10
            agent.draft_timeout_sec = 10
            agent.repair_timeout_sec = 10
            agent.verify_timeout_sec = 2
            agent.max_repair_rounds = rounds
            agent.suite_context = context
            agent.test_design_focus = "analytic"
            stages = []

            async def codex(environment, **kw):
                stages.append(kw["stage"])
                if kw["stage"] == "contract_tests":
                    expected = "def double(x): return 6\n" if context == "candidate" else "def double(x): return x\n"
                    self.assertEqual((Path(kw["cwd"]) / "source/calc.py").read_text(), expected)
                    self.assertEqual((Path(kw["cwd"]) / "candidate.patch").exists(), context == "candidate")
                    self.assertEqual((self.work / "source/calc.py").read_text(), "def double(x): return x\n")
                    if materialize:
                        raise AgentBudgetExceeded("research ended before writing files")
                    target = Path(kw["cwd"]) / "selfverify/invariants"
                    target.mkdir(parents=True)
                    for name, content in fixtures.suite_files().items():
                        (target / name).write_text(content)
                elif kw["stage"] == "contract_materialize":
                    self.assertTrue(materialize)
                    target = Path(kw["cwd"]) / "selfverify/invariants"
                    target.mkdir(parents=True)
                    for name, content in fixtures.suite_files().items():
                        (target / name).write_text(content)
                elif kw["stage"] == "draft":
                    (self.work / "source/calc.py").write_text("def double(x): return 6\n")
                    raise AgentBudgetExceeded("bounded draft timed out after writing a partial patch")
                elif kw["stage"] == "contract_repair":
                    self.assertIn("regression", kw["instruction"])
                    (self.work / "source/calc.py").write_text("def double(x): return 2*x\n")
                else:
                    self.fail(f"unexpected stage {kw['stage']}")
            agent._codex_exec = codex
            env = Environment()
            logger = RunLogger(agent.logs_dir)
            with patch("selfverify.contract.discover_workdir", return_value=str(self.work)):
                await run_contract_loop(agent, "double the input and preserve zero", env, {}, logger)
            await finalize(agent, env, logger)
            expected_stages = ["contract_tests"] + (["contract_materialize"] if materialize else []) + ([] if saved else ["draft"]) + (["contract_repair"] if rounds else [])
            self.assertEqual(stages, expected_stages)
            state = agent.artifacts["contract"]
            self.addCleanup(shutil.rmtree, state["scratch"], True)
            self.assertEqual(agent.artifacts["revisions"], int(bool(rounds)))
            if rounds:
                self.assertTrue(state["candidates"][1]["promoted"])
            expected_final = "def double(x): return 2*x\n" if rounds else "def double(x): return 6\n"
            self.assertEqual((self.work / "source/calc.py").read_text(), expected_final)
            self.assertEqual(state["selected"]["sha256"], agent.artifacts["final_patch_guard"]["sha256"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
