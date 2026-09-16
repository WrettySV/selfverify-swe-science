from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from selfverify.agent import AgentBudgetExceeded, SelfVerifyCodex
from selfverify.stages import (
    _restore_is_intact,
    restore_snapshot_if_lost,
    snapshot_worktree_patch,
)


class LocalEnvironment:
    async def exec(self, *, command: str, timeout_sec: int | float | None = None):
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return SimpleNamespace(return_code=124, stdout="", stderr="timeout")
        return SimpleNamespace(
            return_code=proc.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test"],
            check=True,
        )
        (self.root / "source.py").write_text("value = 1\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "baseline"], check=True
        )
        self.env = LocalEnvironment()

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_snapshot_excludes_selfverify_artifacts(self) -> None:
        (self.root / "source.py").write_text("value = 2\n")
        inv = self.root / "selfverify" / "invariants"
        inv.mkdir(parents=True)
        (inv / "probe.py").write_text("assert True\n")
        snapshot = await snapshot_worktree_patch(
            self.env, str(self.root), str(self.root / ".best.patch")
        )
        self.assertTrue(snapshot["ok"])
        patch = (self.root / ".best.patch").read_text()
        self.assertIn("source.py", patch)
        self.assertNotIn("selfverify/", patch)
        self.assertTrue(snapshot["sha256"])

    async def test_nonempty_wrong_patch_is_restored_exactly(self) -> None:
        (self.root / "source.py").write_text("value = 2\n")
        snapshot = await snapshot_worktree_patch(
            self.env, str(self.root), str(self.root.parent / "best.patch")
        )
        (self.root / "source.py").write_text("value = 3\n")
        before = await _restore_is_intact(
            self.env, str(self.root), snapshot["baseline"], snapshot["path"]
        )
        self.assertFalse(before["intact"])
        self.assertGreater(before["now_bytes"], 0)

        restored = await restore_snapshot_if_lost(
            self.env, str(self.root), snapshot
        )
        self.assertEqual(restored["action"], "restored_snapshot")
        self.assertTrue(restored["ok"])
        self.assertEqual((self.root / "source.py").read_text(), "value = 2\n")


class DeadlineTests(unittest.TestCase):
    def make_agent(self) -> SelfVerifyCodex:
        agent = object.__new__(SelfVerifyCodex)
        agent.codex_stage_timeout_sec = 30
        agent.finalize_reserve_sec = 5
        agent._deadline = None
        return agent

    def test_stage_timeout_is_capped_by_global_deadline(self) -> None:
        agent = self.make_agent()
        agent._deadline = time.monotonic() + 8
        timeout = agent._stage_timeout()
        self.assertGreater(timeout, 2)
        self.assertLessEqual(timeout, 3.1)

    def test_deadline_reserves_finalize_time(self) -> None:
        agent = self.make_agent()
        agent._deadline = time.monotonic() + 4
        with self.assertRaises(AgentBudgetExceeded):
            agent._stage_timeout()


if __name__ == "__main__":
    unittest.main()
