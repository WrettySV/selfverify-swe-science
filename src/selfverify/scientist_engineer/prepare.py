from __future__ import annotations

import json
import shutil
from pathlib import Path

from .io_util import load_prompt, render_template, task_instruction


def render_brief_for_engineer(brief: dict) -> str:
    """JSON for the diagnosis, fenced Python for the probes (readable in a prompt)."""
    probes = brief.get("metamorphic_probes") or []
    head = {k: v for k, v in brief.items() if k != "metamorphic_probes"}
    parts = ["```json", json.dumps(head, indent=2), "```"]
    if probes:
        parts.append("")
        parts.append("### metamorphic_probes (optional diagnostic only — do not treat as the spec; do not rewrite)")
        for i, probe in enumerate(probes, 1):
            parts.append(f"\n**Probe {i}: `{probe.get('name', f'probe_{i}')}`** — {probe.get('relation', '')}")
            code = (probe.get("code") or "").strip()
            if code:
                parts.extend(["```python", code, "```"])
    if brief.get("unverified_hypotheses"):
        parts.append(
            "\n_Note: the critic rejected this brief's localization; the loci above are "
            "listed as `unverified_hypotheses`. Localize from `reproduce.py` imports "
            "yourself and treat them only as places to check._"
        )
    return "\n".join(parts)


def prepare_condition_tree(
    *,
    source_tasks: Path,
    dest_tasks: Path,
    condition: str,
    briefs_dir: Path | None = None,
    only_task_ids: set[str] | None = None,
) -> Path:
    """Copy materialized tasks and rewrite instruction.md for B1 / SE."""
    if dest_tasks.exists():
        shutil.rmtree(dest_tasks)
    if only_task_ids is None:
        shutil.copytree(source_tasks, dest_tasks)
    else:
        dest_tasks.mkdir(parents=True, exist_ok=True)
        for task_id in sorted(only_task_ids):
            src = source_tasks / f"task_{task_id}"
            if not src.is_dir():
                raise FileNotFoundError(src)
            shutil.copytree(src, dest_tasks / f"task_{task_id}")

    for task_dir in sorted(dest_tasks.glob("task_*")):
        if not (task_dir / "instruction.md").is_file():
            continue
        task_id = task_dir.name.removeprefix("task_")
        if only_task_ids is not None and task_id not in only_task_ids:
            continue
        original = task_instruction(task_dir)

        if condition == "b0":
            continue
        if condition == "b1":
            text = render_template(
                load_prompt("baseline_science_first.md"),
                ORIGINAL_INSTRUCTION=original,
            )
        elif condition == "se":
            if briefs_dir is None:
                raise ValueError("briefs_dir required for condition=se")
            brief_path = briefs_dir / task_id / "scientist_brief.json"
            if not brief_path.is_file():
                raise FileNotFoundError(f"missing scientist brief: {brief_path}")
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            verify_path = briefs_dir / task_id / "scientist_verify.json"
            accepted = True
            if verify_path.is_file():
                try:
                    accepted = bool(json.loads(verify_path.read_text(encoding="utf-8")).get("accepted", True))
                except json.JSONDecodeError:
                    accepted = False
            # A rejected brief's probes are a false exam (see se2 task 017).
            # Fall back to a B0-like Engineer with a keep-going finish gate.
            if not accepted or brief.get("unverified_hypotheses"):
                text = render_template(
                    load_prompt("engineer_fallback.md"),
                    ORIGINAL_INSTRUCTION=original,
                )
            else:
                brief_text = render_brief_for_engineer(brief)
                text = render_template(
                    load_prompt("engineer_wrapper.md"),
                    SCIENTIST_BRIEF=brief_text,
                    ORIGINAL_INSTRUCTION=original,
                )
        else:
            raise ValueError(f"unknown condition: {condition}")

        (task_dir / "instruction.original.md").write_text(original, encoding="utf-8")
        (task_dir / "instruction.md").write_text(text.strip() + "\n", encoding="utf-8")

    return dest_tasks
