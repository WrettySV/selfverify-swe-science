import asyncio
from pathlib import Path
import shlex
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from selfverify.agent import SelfVerifyCodex, AgentBudgetExceeded
from selfverify.contract_runtime import execute


class StageTests(unittest.IsolatedAsyncioTestCase):
    async def stage(self, body, limit=2):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "stub"
            stub.write_text("#!/bin/sh\n" + body)
            stub.chmod(0o755)
            commands = []
            class Env:
                async def exec(self, *, command, timeout_sec=5):
                    value = await asyncio.to_thread(execute, ["bash", "-c", command], timeout=timeout_sec)
                    return SimpleNamespace(stdout=value["output"], stderr="", return_code=value["exit_code"])
            env = Env()
            agent = object.__new__(SelfVerifyCodex)
            agent.model_name = "local-test-model"
            agent._command_model_name = None
            agent.codex_stage_timeout_sec = 30
            agent._deadline = None
            agent._original_instruction = "Original task: double the value."
            agent.build_cli_flags = lambda: ""
            async def exec_agent(environment, *, command, **kwargs):
                commands.append(command)
                # Exercise the exact timeout/pipeline/status logic, substituting
                # a local executable for the model CLI.
                command = command.split("fi; ", 1)[1].replace("codex exec ", shlex.quote(str(stub)) + " exec ", 1)
                return await environment.exec(command=command)
            agent.exec_as_agent = exec_agent
            with patch("selfverify.agent.EnvironmentPaths", SimpleNamespace(agent_dir=root)):
                await agent._codex_exec(env, instruction="Repair using evidence", env={},
                                        output_name="stage.txt", stage="repair", timeout_sec=limit)
            self.assertIn("Original task: double the value.", commands[0])
            self.assertIn("Repair using evidence", commands[0])

    async def test_original_instruction_is_included(self):
        await self.stage("exit 0\n")

    async def test_cli_failure_is_not_hidden_by_tee(self):
        with self.assertRaisesRegex(RuntimeError, "status '7'"):
            await self.stage("exit 7\n")

    async def test_process_timeout_is_reported(self):
        with self.assertRaises(AgentBudgetExceeded):
            await self.stage("sleep 20\n", limit=0.1)
