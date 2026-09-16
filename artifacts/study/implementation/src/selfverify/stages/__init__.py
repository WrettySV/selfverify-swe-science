"""Stage helpers for self-verification (prompt load + test execution)."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from selfverify.parser import ParseError, parse_json_from_output


def load_prompt(name: str) -> str:
    """Load a prompt markdown shipped with the package."""
    return (
        resources.files("selfverify")
        .joinpath("prompts", name)
        .read_text(encoding="utf-8")
    )


def render_prompt(name: str, **fields: str) -> str:
    text = load_prompt(name)
    for key, value in fields.items():
        text = text.replace("{" + key + "}", value)
    return text


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_\-]+")


def safe_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name.strip()) or "unnamed"
    return cleaned[:80]


async def read_remote_text(environment: Any, path: str) -> str | None:
    result = await environment.exec(
        command=f"if [ -f {path!s} ]; then cat {path!s}; fi"
    )
    if result.return_code != 0:
        return None
    text = result.stdout or ""
    return text if text.strip() else None


async def write_remote_text(environment: Any, path: str, content: str) -> None:
    parent = str(Path(path).parent)
    # Use base64 to avoid shell-escaping pitfalls for arbitrary content.
    import base64

    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    command = (
        f"mkdir -p {parent} && "
        f"python3 -c \"import base64, pathlib; "
        f"pathlib.Path({path!r}).write_bytes(base64.b64decode({encoded!r}))\""
    )
    result = await environment.exec(command=command)
    if result.return_code != 0:
        raise RuntimeError(
            f"failed to write {path}: rc={result.return_code} "
            f"stderr={(result.stderr or '')[:500]}"
        )


async def discover_workdir(environment: Any) -> str:
    """Locate /app/task_NNN (SWE-bench Science environment layout)."""
    result = await environment.exec(
        command=(
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "app = Path('/app')\n"
            "cands = sorted(app.glob('task_*')) if app.is_dir() else []\n"
            "for p in cands:\n"
            "    if p.is_dir():\n"
            "        print(p)\n"
            "        break\n"
            "else:\n"
            "    print('/app')\n"
            "PY"
        )
    )
    path = (result.stdout or "").strip().splitlines()
    return path[0] if path else "/app"


async def load_manifest(environment: Any, workdir: str) -> dict[str, Any]:
    raw = await read_remote_text(environment, f"{workdir}/selfverify/invariants/manifest.json")
    if not raw:
        return {"invariants": [], "notes": "missing manifest.json"}
    try:
        return parse_json_from_output(raw)
    except ParseError:
        return {"invariants": [], "notes": "unparseable manifest.json", "raw": raw[:2000]}


async def list_invariant_scripts(environment: Any, workdir: str) -> list[str]:
    result = await environment.exec(
        command=(
            f"ls -1 {workdir}/selfverify/invariants/invariant_*.py 2>/dev/null || true"
        )
    )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return lines


async def run_verification(
    environment: Any,
    workdir: str,
    *,
    timeout_sec: int = 180,
    scripts: list[str] | None = None,
) -> dict[str, Any]:
    """Run invariant scripts; allow non-zero exits (do not raise).

    If ``scripts`` is provided, only those paths are executed (post-filter for
    discriminator-valid tests). Otherwise every ``invariant_*.py`` is run.
    """
    if scripts is None:
        scripts = await list_invariant_scripts(environment, workdir)
    manifest = await load_manifest(environment, workdir)

    results: list[dict[str, Any]] = []
    for script in scripts:
        name = Path(script).stem
        result = await environment.exec(
            command=f"cd {workdir} && python3 {script} 2>&1",
            timeout_sec=timeout_sec,
        )
        stdout = (result.stdout or "")[-4000:]
        stderr = (result.stderr or "")[-2000:]
        meta: dict[str, Any] = {}
        # Prefer filename / path match from manifest.
        for item in manifest.get("invariants", []) if isinstance(manifest.get("invariants"), list) else []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if path and Path(path).name == Path(script).name:
                meta = item
                break
        results.append(
            {
                "name": meta.get("name") or name,
                "invariant": meta.get("invariant"),
                "path": script,
                "passed": result.return_code == 0,
                "exit_code": result.return_code,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    n_passed = sum(1 for item in results if item["passed"])
    n_failed = len(results) - n_passed
    if not results:
        status = "no_tests_generated"
        all_passed = False
    elif n_failed == 0:
        status = "all_passed"
        all_passed = True
    else:
        status = "failed"
        all_passed = False
    return {
        "results": results,
        "status": status,
        "all_passed": all_passed,
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_total": len(results),
        "manifest": manifest,
    }


async def _restore_is_intact(
    environment: Any, workdir: str, baseline: str, patch_path: str
) -> dict[str, Any]:
    """Confirm the worktree carries exactly the code patch the gate saved."""
    result = await environment.exec(
        command=(
            f"cd {workdir}\n"
            "git add -A\n"
            "now=/tmp/selfverify_restore_check.patch\n"
            f"git diff --cached --binary {baseline} -- . ':(exclude)selfverify' > \"$now\"\n"
            f"saved_sha=$(sha256sum {patch_path} | awk '{{print $1}}')\n"
            "now_sha=$(sha256sum \"$now\" | awk '{print $1}')\n"
            f'saved_bytes=$(wc -c < {patch_path})\n'
            'now_bytes=$(wc -c < "$now")\n'
            'echo "NOW_SHA=$now_sha SAVED_SHA=$saved_sha '
            'NOW_BYTES=$now_bytes SAVED_BYTES=$saved_bytes"\n'
        ),
        timeout_sec=180,
    )
    values: dict[str, str] = {}
    for token in (result.stdout or "").split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    now_bytes = int(values["NOW_BYTES"]) if values.get("NOW_BYTES", "").isdigit() else None
    saved_bytes = (
        int(values["SAVED_BYTES"]) if values.get("SAVED_BYTES", "").isdigit() else None
    )
    intact = (
        result.return_code == 0
        and values.get("NOW_SHA") is not None
        and values.get("NOW_SHA") == values.get("SAVED_SHA")
    )
    return {
        "intact": intact,
        "now_bytes": now_bytes,
        "saved_bytes": saved_bytes,
        "now_sha256": values.get("NOW_SHA"),
        "saved_sha256": values.get("SAVED_SHA"),
    }


async def snapshot_worktree_patch(
    environment: Any, workdir: str, dest: str
) -> dict[str, Any]:
    """Save the current worktree as a patch against the baseline root.

    ``pre_artifacts.sh`` builds ``model.patch`` the same way after the agent
    returns, so this is a checkpoint of exactly what would be graded.
    """
    baseline = await _git_baseline_root(environment, workdir)
    if not baseline:
        return {"ok": False, "error": "no_baseline_root", "bytes": 0}
    result = await environment.exec(
        command=(
            "set -e\n"
            f"mkdir -p $(dirname {dest})\n"
            f"cd {workdir}\n"
            "git add -A\n"
            f"git diff --cached --binary {baseline} -- . ':(exclude)selfverify' > {dest}\n"
            f"bytes=$(wc -c < {dest})\n"
            f"sha=$(sha256sum {dest} | awk '{{print $1}}')\n"
            'echo "BYTES=$bytes SHA256=$sha"\n'
        ),
        timeout_sec=180,
    )
    values: dict[str, str] = {}
    for token in (result.stdout or "").split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    size = int(values["BYTES"]) if values.get("BYTES", "").isdigit() else 0
    return {
        "ok": result.return_code == 0,
        "error": None if result.return_code == 0 else (result.stderr or "")[-500:],
        "path": dest,
        "bytes": size,
        "sha256": values.get("SHA256"),
        "baseline": baseline,
    }


async def restore_snapshot_if_lost(
    environment: Any, workdir: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Put the checkpointed patch back when the worktree lost it.

    Gate stages reset the tree and re-apply a patch; when that apply fails the
    tree silently stays at the baseline and an empty ``model.patch`` is graded
    even though a real repair existed.
    """
    baseline = snapshot.get("baseline")
    saved_bytes = int(snapshot.get("bytes") or 0)
    if not baseline or saved_bytes <= 0:
        return {"action": "none", "reason": "no_snapshot"}
    check = await _restore_is_intact(environment, workdir, baseline, snapshot["path"])
    if check["intact"]:
        return {"action": "none", **check}
    applied = await environment.exec(
        command=(
            f"cd {workdir}\n"
            f"git reset --hard {baseline} >/dev/null 2>&1\n"
            "git clean -fd >/dev/null 2>&1\n"
            f"git apply --binary --whitespace=nowarn {snapshot['path']} || "
            f"git apply --binary --3way --whitespace=nowarn {snapshot['path']}\n"
        ),
        timeout_sec=180,
    )
    post_check = await _restore_is_intact(
        environment, workdir, baseline, snapshot["path"]
    )
    return {
        "action": "restored_snapshot",
        "ok": applied.return_code == 0 and post_check["intact"],
        "saved_bytes": saved_bytes,
        "before": check,
        "after": post_check,
        "stderr": ((applied.stderr or "") + (applied.stdout or ""))[-500:],
    }


async def persist_invariants(environment: Any, workdir: str, dest_dir: str) -> bool:
    """Copy the generated suite into the trial log directory.

    The suite has to survive for later analysis, but it must not survive in the
    worktree, because everything left there is folded into ``model.patch``.
    """
    result = await environment.exec(
        command=(
            f"if [ -d {workdir}/selfverify ]; then\n"
            f"  mkdir -p {dest_dir}\n"
            f"  cp -a {workdir}/selfverify/. {dest_dir}/ 2>/dev/null || true\n"
            "fi\n"
        ),
        timeout_sec=120,
    )
    return result.return_code == 0


async def clear_worktree_selfverify(environment: Any, workdir: str) -> dict[str, Any]:
    """Drop ``selfverify/`` from the worktree before the patch is collected."""
    result = await environment.exec(
        command=(
            f"cd {workdir} && "
            "git rm -r --cached --quiet selfverify 2>/dev/null || true; "
            "rm -rf selfverify; "
            "git status --porcelain -- selfverify | wc -l"
        ),
        timeout_sec=120,
    )
    text = (result.stdout or "").strip().splitlines()
    return {
        "ok": result.return_code == 0,
        "remaining_entries": int(text[-1]) if text and text[-1].strip().isdigit() else None,
    }


async def _git_baseline_root(environment: Any, workdir: str) -> str | None:
    result = await environment.exec(
        command=(
            f"cd {workdir} && git rev-list --max-parents=0 --reverse HEAD 2>/dev/null | head -1"
        )
    )
    text = (result.stdout or "").strip().splitlines()
    return text[-1].strip() if text else None


_REPRODUCE_BAN = re.compile(
    r"("
    r"reproduce\.py"
    r"|reproduce/"
    r"|/reproduce\b"
    r"|runpy\.run_path\(\s*['\"]reproduce"
    r"|\bimport\s+reproduce\b"
    r"|from\s+reproduce\s+import"
    r"|subprocess\.[a-zA-Z_]+\([^)]*reproduce"
    r")",
    re.IGNORECASE,
)


async def scan_invariant_scripts(
    environment: Any,
    workdir: str,
    scripts: list[str] | None = None,
) -> dict[str, Any]:
    """Static harness gate: reject suites that clone / call public reproduce."""
    if scripts is None:
        scripts = await list_invariant_scripts(environment, workdir)
    banned: list[dict[str, str]] = []
    clean: list[str] = []
    for script in scripts:
        raw = await read_remote_text(environment, script)
        if raw is None:
            banned.append({"path": script, "reason": "unreadable"})
            continue
        if _REPRODUCE_BAN.search(raw):
            banned.append({"path": script, "reason": "references_reproduce"})
            continue
        # Extremely short stubs are almost never real metamorphic probes.
        if len(raw.strip()) < 40:
            banned.append({"path": script, "reason": "too_short"})
            continue
        clean.append(script)
    return {
        "ok": True,
        "scripts": scripts,
        "clean_scripts": clean,
        "banned_scripts": banned,
        "n_clean": len(clean),
        "n_banned": len(banned),
        "status": (
            "no_tests_generated"
            if not scripts
            else ("all_banned" if not clean else "has_clean_tests")
        ),
    }


async def run_ablation_probe(
    environment: Any,
    workdir: str,
    good_scripts: list[str],
    *,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    """Soft ablation: revert one non-invariant changed source file, re-run good tests.

    If discriminators still **all pass** after removing part of the repair, the
    suite is too weak (likely public-smoke-adjacent) → ``survived=True`` (reject).
    """
    if not good_scripts:
        return {
            "ok": False,
            "error": "no_good_scripts",
            "survived": True,
            "ablated_file": None,
            "post_ablation": None,
        }

    baseline = await _git_baseline_root(environment, workdir)
    if not baseline:
        return {
            "ok": False,
            "error": "no_baseline_root",
            "survived": True,
            "ablated_file": None,
            "post_ablation": None,
        }

    backup_root = "/tmp/selfverify_ablation"
    patch_path = f"{backup_root}/agent.patch"
    inv_dir = f"{workdir}/selfverify/invariants"
    inv_backup = f"{backup_root}/invariants"

    # List changed tracked files excluding selfverify artifacts.
    listing = await environment.exec(
        command=(
            f"cd {workdir} && git add -A && "
            f"git diff --cached --name-only {baseline} | "
            "grep -v '^selfverify/' | grep -v '/selfverify/' || true"
        )
    )
    files = [
        line.strip()
        for line in (listing.stdout or "").splitlines()
        if line.strip() and not line.strip().endswith(".pyc")
    ]
    # Prefer a source-looking file.
    preferred = [
        f
        for f in files
        if f.endswith((".py", ".f90", ".f", ".c", ".cpp", ".h", ".hpp", ".jl", ".R"))
    ]
    ablated = (preferred or files)[:1]
    if not ablated:
        return {
            "ok": True,
            "error": None,
            "survived": False,
            "ablated_file": None,
            "skipped": "no_non_invariant_files",
            "post_ablation": None,
        }

    target = ablated[0]
    prep = await environment.exec(
        command=(
            "set -e\n"
            f"mkdir -p {backup_root}\n"
            f"rm -rf {inv_backup} {patch_path}\n"
            f"cd {workdir}\n"
            "git add -A\n"
            f"git diff --cached --binary {baseline} -- . ':(exclude)selfverify' > {patch_path}\n"
            f"if [ -d {inv_dir} ]; then cp -a {inv_dir} {inv_backup}; fi\n"
            # Restore full patch first (canonical), then checkout one file from baseline.
            f"git reset --hard {baseline}\n"
            "git clean -fd\n"
            f"git apply --binary --whitespace=nowarn {patch_path}\n"
            f"if [ -d {inv_backup} ]; then mkdir -p {workdir}/selfverify && "
            f"rm -rf {inv_dir} && cp -a {inv_backup} {inv_dir}; fi\n"
            f"git checkout -f {baseline} -- {target} 2>/dev/null || "
            f"rm -f {target}\n"
            f"echo ABLATED={target}\n"
        ),
        timeout_sec=120,
    )
    if prep.return_code != 0:
        # Restore best-effort.
        await environment.exec(
            command=(
                f"cd {workdir} && git reset --hard {baseline} && git clean -fd; "
                f"if [ -s {patch_path} ]; then git apply --binary --whitespace=nowarn {patch_path} || true; fi; "
                f"if [ -d {inv_backup} ]; then mkdir -p {workdir}/selfverify && "
                f"rm -rf {inv_dir} && cp -a {inv_backup} {inv_dir}; fi"
            ),
            timeout_sec=120,
        )
        return {
            "ok": False,
            "error": "ablation_prep_failed",
            "survived": True,
            "ablated_file": target,
            "prep_stderr": ((prep.stderr or "") + (prep.stdout or ""))[-1500:],
            "post_ablation": None,
        }

    post_ablation = await run_verification(
        environment,
        workdir,
        timeout_sec=timeout_sec,
        scripts=good_scripts,
    )

    # Always restore full patch + invariants.
    restore = await environment.exec(
        command=(
            "set -e\n"
            f"cd {workdir}\n"
            f"git reset --hard {baseline}\n"
            "git clean -fd\n"
            f"if [ -s {patch_path} ]; then git apply --binary --whitespace=nowarn {patch_path}; fi\n"
            f"if [ -d {inv_backup} ]; then mkdir -p {workdir}/selfverify && "
            f"rm -rf {inv_dir} && cp -a {inv_backup} {inv_dir}; fi\n"
        ),
        timeout_sec=120,
    )
    restore_check = await _restore_is_intact(environment, workdir, baseline, patch_path)
    if restore.return_code != 0 or not restore_check["intact"]:
        return {
            "ok": False,
            "error": "ablation_restore_failed",
            "survived": True,
            "ablated_file": target,
            "restore_check": restore_check,
            "post_ablation": post_ablation,
        }

    # Survived = tests still all pass without the ablated file → too weak.
    survived = bool(post_ablation.get("all_passed")) and int(post_ablation.get("n_total") or 0) > 0
    return {
        "ok": True,
        "error": None,
        "survived": survived,
        "ablated_file": target,
        "candidate_files": files[:20],
        "post_ablation": post_ablation,
        "status": "survived_ablation" if survived else "killed_by_ablation",
    }


def format_ablation_summary(ablation: dict[str, Any]) -> str:
    post = ablation.get("post_ablation") or {}
    lines = [
        f"ablated_file: {ablation.get('ablated_file')}",
        f"status: {ablation.get('status') or ablation.get('error')}",
        f"post_ablation: passed={post.get('n_passed')}/{post.get('n_total')} "
        f"all_passed={post.get('all_passed')}",
    ]
    for item in (post.get("results") or [])[:8]:
        lines.append(
            f"- {item.get('name')}: passed={item.get('passed')} "
            f"exit={item.get('exit_code')}"
        )
    return "\n".join(lines)


async def run_discriminator_gate(
    environment: Any,
    workdir: str,
    *,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    """Validate metamorphic tests as bug discriminators.

    Procedure:
      0. Static scan (ban reproduce.py clones / empty stubs)
      1. Save current worktree patch (vs single baseline root) + invariants backup
      2. Reset to baseline (pre-fix), restore only ``selfverify/invariants/``
      3. Run clean invariant scripts on pre-fix
      4. Restore the patch (post-fix tree)
      5. ``good`` = scripts that **failed** on pre-fix (≥1 required)

    A test that passes on pre-fix does not detect the bug and is ignored for
    patch verification.
    """
    inv_dir = f"{workdir}/selfverify/invariants"
    backup_root = "/tmp/selfverify_disc_gate"
    patch_path = f"{backup_root}/agent.patch"
    inv_backup = f"{backup_root}/invariants"

    scan = await scan_invariant_scripts(environment, workdir)
    if scan.get("status") == "no_tests_generated":
        return {
            "ok": True,
            "error": None,
            "pre_result": {"status": "no_tests_generated", "results": [], "n_total": 0},
            "good_scripts": [],
            "weak_scripts": [],
            "banned_scripts": scan.get("banned_scripts") or [],
            "n_good": 0,
            "n_weak": 0,
            "status": "no_tests_generated",
            "scan": scan,
        }
    if scan.get("status") == "all_banned":
        return {
            "ok": True,
            "error": None,
            "pre_result": {"status": "all_banned", "results": [], "n_total": 0},
            "good_scripts": [],
            "weak_scripts": [],
            "banned_scripts": scan.get("banned_scripts") or [],
            "n_good": 0,
            "n_weak": 0,
            "status": "no_valid_tests",
            "scan": scan,
        }

    baseline = await _git_baseline_root(environment, workdir)
    if not baseline:
        return {
            "ok": False,
            "error": "no_baseline_root",
            "pre_result": None,
            "good_scripts": [],
            "weak_scripts": [],
            "scan": scan,
        }

    # Save patch + invariants, reset to baseline, restore invariants only.
    prep = await environment.exec(
        command=(
            "set -e\n"
            f"mkdir -p {backup_root}\n"
            f"rm -rf {inv_backup} {patch_path}\n"
            f"cd {workdir}\n"
            "git add -A\n"
            f"git diff --cached --binary {baseline} -- . ':(exclude)selfverify' > {patch_path}\n"
            f"if [ -d {inv_dir} ]; then cp -a {inv_dir} {inv_backup}; fi\n"
            f"git reset --hard {baseline}\n"
            "git clean -fd\n"
            f"mkdir -p {workdir}/selfverify\n"
            f"if [ -d {inv_backup} ]; then cp -a {inv_backup} {inv_dir}; fi\n"
            f"echo PATCH_BYTES=$(wc -c < {patch_path})\n"
        ),
        timeout_sec=120,
    )
    if prep.return_code != 0:
        # Best-effort restore if prep failed mid-way.
        await environment.exec(
            command=(
                f"cd {workdir} && git reset --hard {baseline} && git clean -fd; "
                f"if [ -s {patch_path} ]; then git apply --binary --whitespace=nowarn {patch_path} || "
                f"git apply --binary --reject --whitespace=nowarn {patch_path} || true; fi; "
                f"if [ -d {inv_backup} ]; then mkdir -p {workdir}/selfverify && cp -a {inv_backup} {inv_dir}; fi"
            ),
            timeout_sec=120,
        )
        return {
            "ok": False,
            "error": "prep_failed",
            "prep_stderr": ((prep.stderr or "") + (prep.stdout or ""))[-2000:],
            "pre_result": None,
            "good_scripts": [],
            "weak_scripts": [],
            "scan": scan,
        }

    clean_scripts = list(scan.get("clean_scripts") or [])
    pre_result = await run_verification(
        environment,
        workdir,
        timeout_sec=timeout_sec,
        scripts=clean_scripts,
    )

    # Restore post-fix patch (+ invariants from backup if apply drops them).
    restore = await environment.exec(
        command=(
            "set -e\n"
            f"cd {workdir}\n"
            f"git reset --hard {baseline}\n"
            "git clean -fd\n"
            f"if [ -s {patch_path} ]; then git apply --binary --whitespace=nowarn {patch_path}; fi\n"
            f"if [ -d {inv_backup} ]; then mkdir -p {workdir}/selfverify && rm -rf {inv_dir} && "
            f"cp -a {inv_backup} {inv_dir}; fi\n"
        ),
        timeout_sec=120,
    )
    restore_check = await _restore_is_intact(environment, workdir, baseline, patch_path)
    if restore.return_code != 0 or not restore_check["intact"]:
        return {
            "ok": False,
            "error": "restore_failed",
            "restore_stderr": ((restore.stderr or "") + (restore.stdout or ""))[-2000:],
            "restore_check": restore_check,
            "pre_result": pre_result,
            "good_scripts": [],
            "weak_scripts": [],
            "scan": scan,
        }

    good_scripts: list[str] = []
    weak_scripts: list[str] = []
    for item in pre_result.get("results") or []:
        path = str(item.get("path") or "")
        if not path:
            continue
        if item.get("passed"):
            weak_scripts.append(path)  # pass@pre → does not detect bug
        else:
            good_scripts.append(path)  # fail@pre → discriminator

    return {
        "ok": True,
        "baseline": baseline,
        "pre_result": pre_result,
        "good_scripts": good_scripts,
        "weak_scripts": weak_scripts,
        "banned_scripts": scan.get("banned_scripts") or [],
        "n_good": len(good_scripts),
        "n_weak": len(weak_scripts),
        "n_banned": scan.get("n_banned") or 0,
        "scan": scan,
        "status": (
            "no_tests_generated"
            if pre_result.get("status") == "no_tests_generated"
            else ("no_valid_tests" if not good_scripts else "has_valid_tests")
        ),
    }


async def run_public_reproduction(
    environment: Any,
    workdir: str,
    *,
    timeout_sec: int = 300,
) -> dict[str, Any]:
    """Run the task's public smoke test: ``python reproduce.py``.

    Exit code 0 = smoke completed (not the private oracle). Non-zero / missing
    script = fail for gating purposes.
    """
    probe = await environment.exec(
        command=(
            f"if [ -f {workdir}/reproduce.py ]; then echo yes; "
            f"elif [ -f {workdir}/reproduce/reproduce.py ]; then echo nested; "
            f"else echo missing; fi"
        )
    )
    kind = (probe.stdout or "").strip().splitlines()
    kind_s = kind[-1] if kind else "missing"
    if kind_s == "missing":
        return {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "reproduce.py not found",
            "command": None,
        }
    cmd = (
        f"cd {workdir} && python reproduce.py"
        if kind_s == "yes"
        else f"cd {workdir}/reproduce && python reproduce.py"
    )
    result = await environment.exec(command=f"{cmd} 2>&1", timeout_sec=timeout_sec)
    stdout = (result.stdout or "")[-4000:]
    stderr = (result.stderr or "")[-2000:]
    return {
        "passed": result.return_code == 0,
        "exit_code": result.return_code,
        "stdout": stdout,
        "stderr": stderr,
        "command": cmd,
    }


def format_failed_tests(verify_result: dict[str, Any]) -> str:
    failed = [item for item in verify_result.get("results", []) if not item.get("passed")]
    if not failed:
        return "(no failed tests)"
    blocks: list[str] = []
    for item in failed:
        blocks.append(
            "\n".join(
                [
                    f"### {item.get('name')}",
                    f"invariant: {item.get('invariant')}",
                    f"exit_code: {item.get('exit_code')}",
                    "stdout:",
                    "```",
                    str(item.get("stdout") or "")[:2000],
                    "```",
                    "stderr:",
                    "```",
                    str(item.get("stderr") or "")[:1000],
                    "```",
                ]
            )
        )
    return "\n\n".join(blocks)


def format_weak_tests(pre_result: dict[str, Any] | None) -> str:
    """Format tests that passed on pre-fix (non-discriminators)."""
    if not pre_result:
        return "(no pre-fix results)"
    weak = [item for item in pre_result.get("results", []) if item.get("passed")]
    if not weak:
        return "(none — all tests failed on pre-fix)"
    blocks: list[str] = []
    for item in weak:
        blocks.append(
            "\n".join(
                [
                    f"### {item.get('name')}  (PASS on pre-fix — NOT a discriminator)",
                    f"invariant: {item.get('invariant')}",
                    f"path: {item.get('path')}",
                    "stdout:",
                    "```",
                    str(item.get("stdout") or "")[:1500],
                    "```",
                ]
            )
        )
    return "\n\n".join(blocks)


def persist_artifacts_local(host_dir: Path, payload: dict[str, Any]) -> None:
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / "selfverify_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
