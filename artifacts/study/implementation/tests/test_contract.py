from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from selfverify.contract import assess, freeze_suite, improves, research_handoff
from selfverify.contract_runtime import operate


def suite_files():
    tests = [
        {"path": "test_bug.py", "requirement": "double the input", "basis": "fixture specification",
         "expected": "double(3) == 6", "input": "3"},
        {"path": "test_regression.py", "requirement": "retain zero", "basis": "fixture specification",
         "expected": "double(0) == 0", "input": "0"},
    ]
    return {"manifest.json": json.dumps({"tests": tests}),
            "test_bug.py": "from calc import double\nassert double(3) == 6, f'expected 6, got {double(3)}'\n",
            "test_regression.py": "from calc import double\nassert double(0) == 0\n"}


class TraceTests(unittest.TestCase):
    def test_handoff_keeps_recent_completed_evidence(self):
        rows = [
            {"type": "item.completed", "item": {"type": "agent_message", "text": "derived case A"}},
            {"type": "item.started", "item": {"type": "command_execution", "command": "ignored"}},
            {"type": "item.completed", "item": {"type": "command_execution", "command": "python oracle.py", "aggregated_output": "expected=0.5 observed=0.8"}},
        ]
        handoff = research_handoff("\n".join(json.dumps(row) for row in rows))
        self.assertIn("derived case A", handoff)
        self.assertIn("expected=0.5", handoff)
        self.assertNotIn("ignored", handoff)

    def test_handoff_is_bounded_and_tolerates_invalid_json(self):
        row = {"type": "item.completed", "item": {"type": "agent_message", "text": "x" * 5000}}
        handoff = research_handoff("bad json\n" + json.dumps(row), limit=100)
        self.assertLessEqual(len(handoff), 3020)
        self.assertEqual(research_handoff(None), "No research trace was available.")


class DecisionTests(unittest.TestCase):
    def test_preserves_regression_and_excludes_runtime_failure(self):
        pre = {"results": [{"path": "bug", "status": "assertion"},
                           {"path": "reg", "status": "pass"},
                           {"path": "broken", "status": "runtime_error"}]}
        post = {"public": {"status": "pass"}, "results": [
            {"path": "bug", "status": "pass"}, {"path": "reg", "status": "assertion"},
            {"path": "broken", "status": "pass"}]}
        result = assess(pre, post)
        self.assertEqual(result["transitions"], {"bug": "repaired", "reg": "regression", "broken": "unusable"})
        self.assertEqual(result["invalid"], ["broken"])

    def test_more_passes_cannot_hide_a_regression(self):
        best = {"passed": ["old"], "invalid": [], "public_pass": True}
        new = {"passed": ["new1", "new2"], "invalid": [], "public_pass": True}
        self.assertFalse(improves(best, new))
        new["passed"].append("old")
        self.assertTrue(improves(best, new))
        new["public_pass"] = False
        self.assertFalse(improves(best, new))

    def test_freeze_requires_justification_and_assertions(self):
        files = suite_files()
        one = freeze_suite(files)
        files["test_bug.py"] = "print('PASS')"
        with self.assertRaises(ValueError):
            freeze_suite(files)
        self.assertIn("assert", one["files"]["test_bug.py"])
        manifest = json.loads(one["files"]["manifest.json"])
        manifest["tests"][0]["basis"] = ""
        bad = {**one["files"], "manifest.json": json.dumps(manifest)}
        with self.assertRaises(ValueError):
            freeze_suite(bad)


    def test_public_references_in_comments_and_docstrings_are_allowed(self):
        files = suite_files()
        files["test_bug.py"] = '\n'.join([
            '"""Requirement documented in reproduce.py."""',
            '# Do not import reproduce or run reproduce.py.',
            'from calc import double',
            'class Reference:',
            '    """Scientific expectation from reproduce.py."""',
            '    def check(self):',
            '        """Transcription of the public collapse criterion in reproduce.py."""',
            '        assert double(3) == 6',
            'async def unused():',
            '    """See reproduce.py."""',
            'Reference().check()',
        ])
        frozen = freeze_suite(files)
        self.assertEqual(frozen["files"], files)
        self.assertIn("reproduce.py", frozen["files"]["test_bug.py"])

    def test_executable_public_reproduction_references_are_rejected(self):
        examples = [
            "import reproduce as public",
            "from reproduce import run_workflow",
            "from reproduce.helpers import check",
            "import subprocess\nsubprocess.run(['python3', 'reproduce.py'])",
            "import runpy\nrunpy.run_path('reproduce.py')",
            "import os\nos.system('python3 reproduce.py')",
            "exec('import reproduce')",
            'def check():\n    """See reproduce.py."""\n    import reproduce\ncheck()',
        ]
        for code in examples:
            with self.subTest(code=code):
                files = suite_files()
                files["test_bug.py"] = code + "\nassert True\n"
                with self.assertRaisesRegex(ValueError, "public reproduction"):
                    freeze_suite(files)
        files = suite_files()
        files["helper.py"] = "from reproduce import run_workflow\n"
        with self.assertRaisesRegex(ValueError, "public reproduction"):
            freeze_suite(files)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        (self.work / "source").mkdir()
        (self.work / "source/calc.py").write_text("def double(x): return x\n")
        (self.work / "reproduce.py").write_text("print('public diagnostic completed')\n")
        for cmd in (["init", "-q"], ["config", "user.email", "test@example.com"],
                    ["config", "user.name", "test"], ["add", "."], ["commit", "-qm", "original"]):
            subprocess.run(["git", "-C", str(self.work), *cmd], check=True)
        self.base = self.root / "base"
        self.prepared = operate({"action": "prepare", "workdir": str(self.work),
                                 "base": str(self.base), "design": str(self.root / "design")})
        self.suite = freeze_suite(suite_files())

    def snapshot(self, name):
        return operate({"action": "snapshot", "workdir": str(self.work),
                        "baseline": self.prepared["baseline"], "dest": str(self.root / name)})

    def evaluate(self, saved=None, suite=None, limit=5):
        suite = suite or self.suite
        return operate({"action": "evaluate", "workdir": str(self.work),
                        "base": str(self.base), "scratch": str(self.root),
                        "patch": saved["path"] if saved else None, "files": suite["files"],
                        "tests": suite["tests"], "test_timeout_sec": limit, "budget_seconds": 30})

    def test_pre_post_and_rollback_use_same_frozen_suite(self):
        pre = self.evaluate()
        self.assertEqual([r["status"] for r in pre["results"]], ["assertion", "pass"])
        (self.work / "source/calc.py").write_text("def double(x): return 2*x\n")
        good = self.snapshot("good.patch")
        # An edited copy must never affect the host-owned frozen suite.
        inv = self.work / "selfverify/invariants"
        inv.mkdir(parents=True)
        (inv / "test_bug.py").write_text("assert True")
        post = self.evaluate(good)
        self.assertEqual(assess(pre, post)["passed"], ["test_bug.py", "test_regression.py"])
        (self.work / "source/calc.py").write_text("def double(x): return 6\n")
        bad = self.snapshot("bad.patch")
        failed = self.evaluate(bad)
        self.assertFalse(improves(assess(pre, post), assess(pre, failed)))
        # Disposable evaluations do not change the candidate worktree.
        self.assertEqual((self.work / "source/calc.py").read_text(), "def double(x): return 6\n")
        result = operate({"action": "finalize", "workdir": str(self.work),
                          "baseline": self.prepared["baseline"], "patch": good["path"],
                          "check_path": str(self.root / "final.patch")})
        self.assertTrue(result["ok"])
        self.assertEqual(result["sha256"], good["sha256"])
        self.assertFalse(inv.exists())

    def test_empty_checkpoint_restores_original(self):
        original = self.snapshot("empty.patch")
        (self.work / "source/calc.py").write_text("raise RuntimeError('corrupted')\n")
        operate({"action": "finalize", "workdir": str(self.work),
                 "baseline": self.prepared["baseline"], "patch": original["path"],
                 "check_path": str(self.root / "check.patch")})
        self.assertEqual((self.work / "source/calc.py").read_text(), "def double(x): return x\n")

    def test_import_failure_and_timeout_are_not_semantic_failures(self):
        files = suite_files()
        files["test_bug.py"] = "import nonexistent_contract_test_dependency\nassert False\n"
        files["test_regression.py"] = "import time\ntime.sleep(10)\nassert False\n"
        result = self.evaluate(suite=freeze_suite(files), limit=0.2)
        self.assertEqual([r["status"] for r in result["results"]], ["runtime_error", "timeout"])

    def test_test_source_mutation_is_rejected(self):
        files = suite_files()
        files["test_bug.py"] = "from pathlib import Path\nPath('source/calc.py').write_text('def double(x): return 9')\nassert False\n"
        result = self.evaluate(suite=freeze_suite(files))
        self.assertEqual(result["results"][0]["status"], "invalid_test")
        self.assertEqual(result["results"][1]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
