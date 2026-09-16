#!/usr/bin/env python3
"""Resume queues while adopting already-running trials; do not regenerate them."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def main(out):
    m = json.loads((out / "manifest.json").read_text())
    for name, expected in json.loads((out / "implementation_sha256.json").read_text()).items():
        assert sha256((out / "implementation" / name).read_bytes()).hexdigest() == expected, name
    amendment = m["infrastructure_amendment"]
    assert sha256(Path(amendment["adapter"]).read_bytes()).hexdigest() == amendment["sha256"]
    env = os.environ.copy()
    env["PIER_PY"] = amendment["adapter"]
    save(out / "run_status.json", {"state": "running", "resumed_at": now(), "pid": os.getpid()})

    def lane(gpu):
        for job in (j for j in m["jobs"] if j["gpu"] == gpu):
            status_file = out / "status" / (job["name"] + ".json")
            if status_file.exists():
                status = json.loads(status_file.read_text())
                if status["state"] == "finished":
                    continue
                print(json.dumps({"adopting": job["name"], "pid": status["pid"]}), flush=True)
                deadline = time.monotonic() + 3600
                while True:
                    results = list(Path(job["result_dir"]).glob("task_*/result.json"))
                    result = json.loads(results[0].read_text()) if len(results) == 1 else {}
                    proc_stat = Path(f"/proc/{status['pid']}/stat")
                    proc_done = not proc_stat.exists() or proc_stat.read_text().split(") ", 1)[1].startswith("Z ")
                    if result.get("finished_at") and proc_done:
                        rc = int(bool(result.get("exception_info")))
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError("Adopted trial did not complete: " + job["name"])
                    time.sleep(5)
            else:
                status = {"name": job["name"], "gpu": gpu, "state": "running", "started_at": now()}
                with (out / "logs" / (job["name"] + "-resumed.log")).open("wb") as log:
                    proc = subprocess.Popen(job["command"], cwd=out / "implementation", env=env,
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    status["pid"] = proc.pid
                    save(status_file, status)
                    print(json.dumps(status), flush=True)
                    try:
                        rc = proc.wait(timeout=3600)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                        rc = 124
            status.update(state="finished", finished_at=now(), returncode=rc)
            save(status_file, status)
            print(json.dumps(status), flush=True)
            traces = list(Path(job["result_dir"]).glob("task_*/agent/codex_*.txt"))
            if any('"type":"turn.failed"' in p.read_text() and "403 Forbidden" in p.read_text() for p in traces):
                raise RuntimeError("Local proxy still rejects model; stopped lane " + str(gpu))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lane, [4, 5, 6, 7]))
    save(out / "run_status.json", {"state": "generation_finished", "finished_at": now()})
    subprocess.run([sys.executable, str(out / "implementation/scripts/evaluate_cross_pilot.py"),
                    "--pilot", str(out)], check=True)
    save(out / "run_status.json", {"state": "finished", "finished_at": now()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", required=True, type=Path)
    main(parser.parse_args().pilot.resolve())
