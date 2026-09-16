"""Dependency-free worker copied into a task container by the contract agent.

All evaluations use disposable copies of the pristine tree. Only finalization
replaces the agent worktree, using an already saved, source-only patch.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback


def execute(argv, *, cwd=None, timeout=180):
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=max(0.1, timeout))
        return {"exit_code": proc.returncode, "output": output.decode(errors="replace")[-8000:]}
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
        return {"exit_code": 124, "output": output.decode(errors="replace")[-8000:], "timeout": True}


def checked(argv, **kwargs):
    result = execute(argv, **kwargs)
    if result["exit_code"]:
        raise RuntimeError(f"{argv[0]} failed: {result}")
    return result["output"].strip()


def digest_tree(root):
    digest = hashlib.sha256()
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            data = os.readlink(path).encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        digest.update(str(path.relative_to(root)).encode() + b"\0" + data + b"\0")
    return digest.hexdigest()


def source_patch(workdir, baseline, dest):
    # Include untracked source files without staging unrelated logs/fixtures.
    checked(["git", "add", "-A", "--", "source"], cwd=workdir)
    with open(dest, "wb") as stream:
        subprocess.run(["git", "diff", "--cached", "--binary", baseline, "--", "source"],
                       cwd=workdir, stdout=stream, check=True, timeout=120)
    data = Path(dest).read_bytes()
    return {"ok": True, "path": str(dest), "baseline": baseline,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def install_suite(root, files):
    target = Path(root) / "selfverify/invariants"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, content in files.items():
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("suite filenames must be flat")
        (target / name).write_text(content)
    return target


def apply_patch(root, path):
    if Path(path).stat().st_size:
        checked(["git", "apply", "--binary", "--whitespace=nowarn", str(path)], cwd=root)


def test_main(script, result_path):
    result = {"status": "pass"}
    sys.path.insert(0, str(Path(script).parent))
    sys.path.insert(0, str(Path.cwd() / "source"))
    try:
        runpy.run_path(script, run_name="__main__")
    except AssertionError as exc:
        result = {"status": "assertion", "error": str(exc)}
        traceback.print_exc()
    except SystemExit as exc:
        if exc.code not in (0, None):
            result = {"status": "runtime_error", "error": f"SystemExit({exc.code!r})"}
    except BaseException as exc:
        result = {"status": "runtime_error", "error": f"{type(exc).__name__}: {exc}"}
        traceback.print_exc()
    Path(result_path).write_text(json.dumps(result))


def operate(c):
    action = c["action"]
    workdir = Path(c["workdir"])
    if action == "prepare":
        base = Path(c["base"])
        base.mkdir(parents=True, exist_ok=False)
        baseline = checked(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=workdir)
        if len(baseline.splitlines()) != 1:
            raise ValueError("expected one baseline root")
        archive = base.parent / "baseline.tar"
        checked(["git", "archive", "--format=tar", f"--output={archive}", baseline], cwd=workdir)
        checked(["tar", "-xf", str(archive), "-C", str(base)])
        shutil.copytree(base, c["design"])
        return {"baseline": baseline, "source_sha256": digest_tree(base / "source")}
    if action == "review_prepare":
        dest = Path(c["dest"])
        shutil.copytree(c["base"], dest)
        apply_patch(dest, c["patch"])
        shutil.copyfile(c["patch"], dest / "candidate.patch")
        return {"source_sha256": digest_tree(dest / "source")}
    if action == "review_collect":
        report = workdir / "selfverify/review/report.json"
        if report.is_symlink() or (report.exists() and report.stat().st_size > 64_000):
            raise ValueError("review report must be a regular file under 64 KB")
        return {"report": report.read_text() if report.exists() else None,
                "source_sha256": digest_tree(workdir / "source"),
                "suite": operate({"action": "suite", "workdir": str(workdir)})}
    if action == "suite":
        root = workdir / "selfverify/invariants"
        files = {}
        if root.exists():
            for p in root.iterdir():
                if p.is_file() and not p.is_symlink() and p.suffix in {".py", ".json"}:
                    if p.stat().st_size > 128_000:
                        raise ValueError("test file too large")
                    files[p.name] = p.read_text()
        return {"files": files, "source_sha256": digest_tree(workdir / "source")}
    if action == "snapshot":
        return source_patch(workdir, c["baseline"], c["dest"])
    if action == "apply":
        apply_patch(workdir, c["patch"])
        return {"ok": True}
    if action == "finalize":
        # Called only with a completed immutable checkpoint. Empty patches also
        # restore correctly, unlike the legacy nonempty-patch recovery guard.
        checked(["git", "reset", "--hard", c["baseline"]], cwd=workdir)
        checked(["git", "clean", "-fd"], cwd=workdir)
        apply_patch(workdir, c["patch"])
        result = source_patch(workdir, c["baseline"], c["check_path"])
        expected = hashlib.sha256(Path(c["patch"]).read_bytes()).hexdigest()
        if result["sha256"] != expected:
            raise RuntimeError("final patch does not match selected checkpoint")
        return {"ok": True, "sha256": expected}
    if action != "evaluate":
        raise ValueError(action)

    deadline = time.monotonic() + c["budget_seconds"]
    timeout = c["test_timeout_sec"]
    def remaining():
        return min(timeout, max(0.1, deadline - time.monotonic()))

    with tempfile.TemporaryDirectory(prefix="contract-eval-", dir=c["scratch"]) as tmp:
        root = Path(tmp) / "task"
        shutil.copytree(c["base"], root)
        if c.get("patch"):
            apply_patch(root, c["patch"])
        suite_dir = install_suite(root, c["files"])
        public = {"status": "not_run"}
        if c.get("public", True):
            entry = root / "reproduce.py"
            if not entry.exists():
                entry = root / "reproduce/reproduce.py"
            if entry.exists():
                result = execute([sys.executable, str(entry)], cwd=entry.parent, timeout=remaining())
                public = {**result, "status": "pass" if result["exit_code"] == 0 else "fail"}
            else:
                public = {"status": "missing"}
        results = []
        for test in c["tests"]:
            if time.monotonic() >= deadline:
                results.append({"path": test["path"], "status": "timeout", "output": "evaluation budget exhausted"})
                continue
            # Reinstall frozen files before every test. Code modifications by a
            # test are detected; their result is not a semantic assertion.
            install_suite(root, c["files"])
            before = digest_tree(root / "source")
            outcome = Path(tmp) / "outcome.json"
            outcome.unlink(missing_ok=True)
            result = execute([sys.executable, str(Path(__file__).resolve()), "--test",
                              str(suite_dir / test["path"]), str(outcome)],
                             cwd=root, timeout=remaining())
            if result.get("timeout"):
                status = {"status": "timeout"}
            elif outcome.exists() and result["exit_code"] == 0:
                status = json.loads(outcome.read_text())
            else:
                status = {"status": "runtime_error"}
            if digest_tree(root / "source") != before:
                status = {"status": "invalid_test", "error": "test modified source"}
            results.append({**test, **result, **status})
            if status["status"] == "invalid_test":
                # No subsequent test should inherit modified source.
                shutil.rmtree(root)
                shutil.copytree(c["base"], root)
                if c.get("patch"):
                    apply_patch(root, c["patch"])
                suite_dir = install_suite(root, c["files"])
        return {"public": public, "results": results}


if __name__ == "__main__":
    if sys.argv[1] == "--test":
        test_main(sys.argv[2], sys.argv[3])
    else:
        try:
            response = {"ok": True, "value": operate(json.loads(Path(sys.argv[1]).read_text()))}
        except Exception as exc:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(response))
