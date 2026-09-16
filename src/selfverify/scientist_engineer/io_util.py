from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from . import SELECTIONS_DIR


def load_prompt(name: str) -> str:
    """Load a prompt shipped under selfverify.prompts.scientist_engineer."""
    return (
        resources.files("selfverify")
        .joinpath("prompts", "scientist_engineer", name)
        .read_text(encoding="utf-8")
    )


def load_selection(name: str = "scientist-engineer-9.json") -> dict:
    path = SELECTIONS_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def render_template(template: str, **fields: str) -> str:
    out = template
    for key, value in fields.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def task_instruction(task_dir: Path) -> str:
    return (task_dir / "instruction.md").read_text(encoding="utf-8")
