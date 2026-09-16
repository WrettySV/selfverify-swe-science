from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .inventory import build_repo_inventory
from .io_util import load_prompt, task_instruction
from .schema import public_oriented_checks, validate_brief


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the last JSON object in a model reply (fenced or bare)."""
    text = text.strip()
    # Strip a leaked <think> block if the server did not separate reasoning.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = list(reversed(fenced))
    if text.startswith("{"):
        candidates.append(text)
    start = text.rfind("\n{")
    if start != -1:
        candidates.append(text[start + 1 :])
    first = text.find("{")
    if first != -1:
        candidates.append(text[first:])
    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception as exc:  # try the next candidate
            last_err = exc
            # attempt to trim trailing garbage after the final brace
            end = cand.rfind("}")
            if end != -1:
                try:
                    return json.loads(cand[: end + 1])
                except Exception as exc2:
                    last_err = exc2
    raise ValueError(f"no JSON object found in reply: {last_err}")


def _client(api_key: str | None, base_url: str | None):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install openai") from exc

    resolved_key = (
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    resolved_base = (
        base_url
        or os.environ.get("SCIENTIST_BASE_URL")
        or os.environ.get("CODEX_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or None
    )
    return OpenAI(api_key=resolved_key, base_url=resolved_base)


def _chat(
    *,
    model: str,
    system: str,
    user: str,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    thinking: bool | None = None,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """One chat call.

    The Scientist is the *reasoning* role, so thinking is on by default
    (``SCIENTIST_THINKING=0`` disables).  The vLLM server runs with a reasoning
    parser, so ``message.content`` holds only the final answer; we give a large
    completion budget so the answer is not starved by reasoning.
    """
    if thinking is None:
        thinking = os.environ.get("SCIENTIST_THINKING", "1") != "0"
    if temperature is None:
        temperature = 0.6 if thinking else 0.2
    if max_tokens is None:
        max_tokens = int(os.environ.get("SCIENTIST_MAX_TOKENS", "40000" if thinking else "16000"))
    client = _client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        top_p=0.95 if thinking else 1.0,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": thinking}},
    )
    msg = response.choices[0].message
    content = msg.content or ""
    reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
        "completion_tokens": getattr(response.usage, "completion_tokens", None),
        "total_tokens": getattr(response.usage, "total_tokens", None),
        "model": model,
        "thinking": thinking,
        "finish_reason": response.choices[0].finish_reason,
        "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
    }
    return content, usage


def _chat_json(
    *,
    model: str,
    system: str,
    user: str,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Chat and parse JSON; fall back to non-thinking mode if the reply is unusable."""
    content, usage = _chat(
        model=model, system=system, user=user, api_key=api_key, base_url=base_url,
        temperature=temperature,
    )
    try:
        return _extract_json(content), content, usage
    except Exception as exc:
        if not usage.get("thinking"):
            raise
        content2, usage2 = _chat(
            model=model, system=system, user=user, api_key=api_key, base_url=base_url,
            temperature=0.2, thinking=False,
        )
        usage2["fallback_from_thinking"] = str(exc)[:200]
        usage2["prompt_tokens"] = (usage.get("prompt_tokens") or 0) + (usage2.get("prompt_tokens") or 0)
        usage2["completion_tokens"] = (usage.get("completion_tokens") or 0) + (usage2.get("completion_tokens") or 0)
        usage2["total_tokens"] = (usage.get("total_tokens") or 0) + (usage2.get("total_tokens") or 0)
        return _extract_json(content2), content2, usage2


def _sum_usage(a: dict[str, Any], b: dict[str, Any], model: str) -> dict[str, Any]:
    out = {
        "prompt_tokens": (a.get("prompt_tokens") or 0) + (b.get("prompt_tokens") or 0),
        "completion_tokens": (a.get("completion_tokens") or 0) + (b.get("completion_tokens") or 0),
        "total_tokens": (a.get("total_tokens") or 0) + (b.get("total_tokens") or 0),
        "model": model,
    }
    return out


def _task_user_prefix(task_dir: Path, task_id: str, inventory: str | None) -> str:
    instruction = task_instruction(task_dir)
    meta_path = task_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    parts = [
        f"task_id: {task_id}",
        f"title: {meta.get('title', '')}",
        f"domain: {meta.get('domain', '')}",
        f"language: {meta.get('language', '')}",
        f"source_repository: {meta.get('source_repository', '')}",
        "",
        "## instruction.md",
        instruction,
    ]
    if inventory:
        parts.extend(["", "## read_only_repo_inventory", inventory])
    return "\n".join(parts)


def _write_brief_artifacts(
    out_dir: Path,
    *,
    brief: dict[str, Any],
    usage: dict[str, Any],
    raw: str,
    inventory: str | None = None,
    verify: dict[str, Any] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scientist_brief.json").write_text(
        json.dumps(brief, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "scientist_usage.json").write_text(
        json.dumps(usage, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "scientist_raw.txt").write_text(raw, encoding="utf-8")
    if inventory is not None:
        (out_dir / "repo_inventory.txt").write_text(inventory, encoding="utf-8")
    if verify is not None:
        (out_dir / "scientist_verify.json").write_text(
            json.dumps(verify, indent=2) + "\n", encoding="utf-8"
        )


def verify_brief(
    *,
    task_dir: Path,
    task_id: str,
    brief: dict[str, Any],
    model: str,
    inventory: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    system = load_prompt("scientist_verify.md")
    user = (
        _task_user_prefix(task_dir, task_id, inventory)
        + "\n\n## candidate_brief\n"
        + json.dumps(brief, indent=2)
    )
    try:
        verdict, content, usage = _chat_json(
            model=model,
            system=system,
            user=user,
            api_key=api_key,
            base_url=base_url,
        )
    except Exception as exc:
        # A critic we cannot parse is not evidence the brief is fine.
        return (
            {"accept": False, "issues": [f"verify_parse_failed: {exc}"], "suggested_fixes": []},
            {"model": model, "error": str(exc)[:200]},
        )
    if "accept" not in verdict:
        verdict["accept"] = False
        verdict.setdefault("issues", []).append("critic_omitted_accept")
    # Mechanical checks the critic may miss.
    leaks = public_oriented_checks(brief)
    if leaks:
        verdict["accept"] = False
        verdict.setdefault("issues", []).append(
            "public-oriented checks/probes: " + "; ".join(leaks)[:400]
        )
    if len(brief.get("metamorphic_probes", [])) < 3:
        verdict["accept"] = False
        verdict.setdefault("issues", []).append("fewer than 3 metamorphic_probes")
    if any(not p.get("code", "").strip() for p in brief.get("metamorphic_probes", [])):
        verdict["accept"] = False
        verdict.setdefault("issues", []).append("a probe has empty code")
    return verdict, usage


def _demote_unverified(brief: dict[str, Any], reason: str) -> dict[str, Any]:
    """A rejected brief must not anchor the Engineer on its loci."""
    loci = brief.get("suspected_loci") or []
    brief["unverified_hypotheses"] = loci
    brief["suspected_loci"] = []
    brief["confidence"] = min(float(brief.get("confidence", 0.5)), 0.4)
    brief.setdefault("evidence_notes", []).append(f"brief_rejected_by_critic: {reason[:300]}")
    brief["acceptance_checks"] = [
        c for c in brief.get("acceptance_checks", [])
        if c not in set(public_oriented_checks({"acceptance_checks": [c]}))
    ]
    return brief


def revise_scientist(
    *,
    task_dir: Path,
    task_id: str,
    model: str,
    out_dir: Path,
    prior_brief: dict[str, Any],
    public_feedback: str,
    inventory: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Amend brief after a public reproduction failure."""
    system = load_prompt("scientist_revise.md")
    inv = inventory
    if inv is None and (out_dir / "repo_inventory.txt").is_file():
        inv = (out_dir / "repo_inventory.txt").read_text(encoding="utf-8")
    user = (
        _task_user_prefix(task_dir, task_id, inv)
        + "\n\n## prior_brief\n"
        + json.dumps(prior_brief, indent=2)
        + "\n\n## public_failure_evidence\n"
        + public_feedback
    )
    data, content, usage = _chat_json(
        model=model,
        system=system,
        user=user,
        api_key=api_key,
        base_url=base_url,
    )
    brief = validate_brief(data)
    brief["task_id"] = task_id
    brief.setdefault("evidence_notes", [])
    if isinstance(brief["evidence_notes"], list):
        brief["evidence_notes"].append("revised_after_public_fail")

    revise_dir = out_dir / "revise"
    revise_dir.mkdir(parents=True, exist_ok=True)
    # Keep prior brief; overwrite active brief for next Engineer pass.
    (revise_dir / "scientist_brief.before.json").write_text(
        json.dumps(prior_brief, indent=2) + "\n", encoding="utf-8"
    )
    (revise_dir / "public_feedback.txt").write_text(public_feedback, encoding="utf-8")
    _write_brief_artifacts(
        out_dir,
        brief=brief,
        usage=usage,
        raw=content,
        inventory=inv,
    )
    (revise_dir / "scientist_brief.after.json").write_text(
        json.dumps(brief, indent=2) + "\n", encoding="utf-8"
    )
    return brief


def run_scientist(
    *,
    task_dir: Path,
    task_id: str,
    model: str,
    out_dir: Path,
    base_url: str | None = None,
    api_key: str | None = None,
    with_inventory: bool = True,
    verify: bool = True,
    max_verify_retries: int = 2,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat API to produce scientist_brief.json."""
    system = load_prompt("scientist.md")
    inventory = build_repo_inventory(task_dir) if with_inventory else None
    user = _task_user_prefix(task_dir, task_id, inventory)

    data, content, usage = _chat_json(
        model=model,
        system=system,
        user=user,
        api_key=api_key,
        base_url=base_url,
    )
    brief = validate_brief(data)
    brief["task_id"] = task_id
    brief.setdefault("evidence_notes", [])
    usage_total = dict(usage)
    usage_total["calls"] = [usage]

    verify_log: dict[str, Any] | None = None
    if verify:
        verify_log = {"attempts": []}
        for attempt in range(max_verify_retries + 1):
            verdict, v_usage = verify_brief(
                task_dir=task_dir,
                task_id=task_id,
                brief=brief,
                model=model,
                inventory=inventory,
                api_key=api_key,
                base_url=base_url,
            )
            verify_log["attempts"].append({"verdict": verdict, "usage": v_usage})
            usage_total = {**_sum_usage(usage_total, v_usage, model), "calls": usage_total["calls"] + [v_usage]}
            if verdict.get("accept", False):
                verify_log["accepted"] = True
                break
            if attempt >= max_verify_retries:
                verify_log["accepted"] = False
                brief = _demote_unverified(brief, "; ".join(verdict.get("issues", [])))
                break
            # Rewrite with critic feedback.
            fix_user = (
                user
                + "\n\n## previous_brief_rejected\n"
                + json.dumps(brief, indent=2)
                + "\n\n## critic_issues\n"
                + json.dumps(verdict, indent=2)
                + "\n\nRewrite a corrected brief JSON only. Fix every issue listed."
            )
            data, content, u2 = _chat_json(
                model=model,
                system=system,
                user=fix_user,
                api_key=api_key,
                base_url=base_url,
            )
            usage_total = {**_sum_usage(usage_total, u2, model), "calls": usage_total["calls"] + [u2]}
            brief = validate_brief(data)
            brief["task_id"] = task_id
            brief.setdefault("evidence_notes", [])
    usage = usage_total

    _write_brief_artifacts(
        out_dir,
        brief=brief,
        usage=usage,
        raw=content,
        inventory=inventory,
        verify=verify_log,
    )
    return brief
