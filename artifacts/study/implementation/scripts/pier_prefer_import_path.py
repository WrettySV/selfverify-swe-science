#!/usr/bin/env python3
"""Pier CLI wrapper that prefers ``agent.import_path`` over builtin ``name``.

Stock Pier AgentFactory does:

    if name in builtin_agents:
        return builtin  # ignores import_path
    elif import_path:
        return custom

So ``--agent codex --agent-import-path selfverify.agent:SelfVerifyCodex``
silently runs stock Codex. This wrapper flips the priority when import_path
is set, then delegates to the normal Pier CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pier.agents.factory import AgentFactory
from pier.models.trial.config import AgentConfig
from pier.utils.env import resolve_env_vars


def _patched_create_agent_from_config(
    cls,
    config: AgentConfig,
    logs_dir: Path,
    **kwargs,
):
    extra_env = resolve_env_vars(config.env)
    # Prefer custom import_path whenever present.
    if config.import_path is not None:
        return cls.create_agent_from_import_path(
            config.import_path,
            logs_dir=logs_dir,
            model_name=config.model_name,
            extra_env=extra_env,
            **config.kwargs,
            **kwargs,
        )
    if config.name is not None:
        from pier.models.agent.name import AgentName

        if config.name in AgentName.values():
            return cls.create_agent_from_name(
                AgentName(config.name),
                logs_dir=logs_dir,
                model_name=config.model_name,
                extra_env=extra_env,
                **config.kwargs,
                **kwargs,
            )
        raise ValueError(
            f"Agent name {config.name} is not valid. Valid agent names: "
            f"{AgentName.values()}"
        )
    raise ValueError(
        "At least one of agent_name or agent_import_path must be set. "
        + f"Valid agent names: {__import__('pier.models.agent.name', fromlist=['AgentName']).AgentName.values()}"
    )


AgentFactory.create_agent_from_config = classmethod(_patched_create_agent_from_config)

from pier.cli.main import app  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(app())
