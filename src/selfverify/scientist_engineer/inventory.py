from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

from .io_util import task_instruction


def _parse_task_toml(task_dir: Path) -> dict:
    path = task_dir / "task.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def docker_image_ref(task_dir: Path) -> str | None:
    env = _parse_task_toml(task_dir).get("environment") or {}
    image = env.get("docker_image")
    if not isinstance(image, str) or not image.strip():
        return None
    # Prefer tag without digest for local docker run compatibility.
    return image.split("@", 1)[0]


def workdir_in_image(task_dir: Path) -> str:
    env = _parse_task_toml(task_dir).get("environment") or {}
    workdir = env.get("workdir")
    if isinstance(workdir, str) and workdir.strip():
        return workdir
    task_id = task_dir.name.removeprefix("task_")
    return f"/app/task_{task_id}"


# Runs *inside* the task image. Produces a JSON document with:
#   - ranked source paths (import reachability from reproduce.py + term hits)
#   - directory histogram
#   - snippets: reproduce.py, paper/reproduction excerpts
#   - AST outlines of the top-ranked modules, with bodies of term-matching defs
_IN_IMAGE_SCRIPT = r'''
import ast, json, os, re, sys
cfg = json.loads(os.environ["INV_CFG"])
WORKDIR = cfg["workdir"]; INSTR = cfg["instruction"]
MAX_FILES = cfg.get("max_files", 4000)
CODE_EXT = (".py", ".pyi", ".c", ".cc", ".cpp", ".h", ".hpp", ".f", ".f90", ".F90", ".jl", ".rs", ".R")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache", "outputs"}

def rel(p): return os.path.relpath(p, WORKDIR)

files = []
for root, dirs, names in os.walk(WORKDIR):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
    for n in names:
        if n.endswith(CODE_EXT) or n in ("reproduce.py", "paper.md", "reproduction.md", "README.md"):
            files.append(os.path.join(root, n))
    if len(files) > MAX_FILES: break
files.sort()

def read(p, limit=400_000):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f: return f.read(limit)
    except Exception: return ""

# ---- terms from instruction (+ paper/reproduction if present)
extra = ""
for n in ("paper.md", "reproduction.md"):
    p = os.path.join(WORKDIR, n)
    if os.path.isfile(p): extra += "\n" + read(p, 60_000)
text = INSTR + "\n" + extra
STOP = set("""the and for with that this from into over under between while should must
which their there these those than then when where what will would could about after before
public private report reports script scripts workflow repair repairs repaired inspect source code
function functions method methods module modules file files value values result results output outputs
input inputs data test tests case cases current correct incorrect behavior behaviour general generic
implementation implement implements repository documented reproduction reproduce fixture fixtures
hard-code hardcode hard-coded fixed number numbers point points same different other another
""".split())
backticked = re.findall(r"`([^`\n]{2,60})`", text)
idents = set()
for b in backticked:
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]*", b):
        idents.add(tok.split("(")[0])
words = re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", text)
snake_or_camel = {w for w in words if ("_" in w or re.search(r"[a-z][A-Z]", w))}
freq = {}
for w in words:
    lw = w.lower()
    if lw in STOP or len(lw) < 5: continue
    freq[lw] = freq.get(lw, 0) + 1
common = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:60]]
strong = [t for t in idents | snake_or_camel if t.lower() not in STOP and len(t) >= 4]
strong = sorted(set(strong))[:80]

# ---- import graph from reproduce.py (and other top-level scripts)
def module_candidates(modname):
    parts = modname.split(".")
    outs = []
    for base in ("", "source", "src"):
        root = os.path.join(WORKDIR, base) if base else WORKDIR
        outs.append(os.path.join(root, *parts) + ".py")
        outs.append(os.path.join(root, *parts, "__init__.py"))
    # also search any dir whose name equals first part
    for f in files:
        if f.endswith(os.sep + os.path.join(*parts) + ".py") or f.endswith(os.sep + os.path.join(*parts, "__init__.py")):
            outs.append(f)
    return [o for o in outs if os.path.isfile(o)]

def imports_of(path):
    src = read(path, 200_000)
    try: tree = ast.parse(src)
    except Exception: return []
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: mods.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
            for a in node.names: mods.append(node.module + "." + a.name)
        elif isinstance(node, ast.ImportFrom) and node.level and node.module:
            # relative import: resolve against file's package dir
            pkg = os.path.dirname(path)
            for _ in range(node.level - 1): pkg = os.path.dirname(pkg)
            cand = os.path.join(pkg, *node.module.split("."))
            for c in (cand + ".py", os.path.join(cand, "__init__.py")):
                if os.path.isfile(c): mods.append("__abs__:" + c)
            for a in node.names:
                c2 = os.path.join(cand, a.name + ".py")
                if os.path.isfile(c2): mods.append("__abs__:" + c2)
    # dynamic loading hints: importlib / spec_from_file_location / open(".../x.py")
    for m in re.findall(r"""['"]([\w/\.-]+\.py)['"]""", src):
        for f in files:
            if f.endswith(m.lstrip("./")): mods.append("__abs__:" + f)
    return mods

reach = {}  # path -> depth
roots = [os.path.join(WORKDIR, "reproduce.py")]
roots += [f for f in files if os.path.dirname(f) == WORKDIR and f.endswith(".py") and f not in roots]
frontier = [(r, 0) for r in roots if os.path.isfile(r)]
seen = set()
while frontier:
    path, depth = frontier.pop(0)
    if path in seen or depth > 3: continue
    seen.add(path)
    for m in imports_of(path):
        cands = [m[len("__abs__:"):]] if m.startswith("__abs__:") else module_candidates(m)
        for c in cands:
            if c.startswith(WORKDIR) and (c not in reach or reach[c] > depth + 1):
                reach[c] = depth + 1
                frontier.append((c, depth + 1))

# ---- score files
scored = []
strong_re = [re.compile(r"\b" + re.escape(t) + r"\b") for t in strong]
common_re = [re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in common[:40]]
for f in files:
    r = rel(f)
    if r in ("reproduce.py", "paper.md", "reproduction.md", "README.md"): continue
    body = read(f, 300_000)
    if not body: continue
    s = 0.0
    hits_strong = [t for t, rx in zip(strong, strong_re) if rx.search(body)]
    s += 3.0 * len(hits_strong)
    s += 0.5 * sum(1 for rx in common_re if rx.search(body))
    # path-level hints
    low = r.lower()
    s += 4.0 * sum(1 for t in strong if t.lower() in low)
    if f in reach: s += {1: 12.0, 2: 6.0, 3: 3.0}.get(reach[f], 1.0)
    if "/tests/" in low or low.startswith("tests/") or os.path.basename(low).startswith("test_"): s *= 0.25
    if low.endswith("__init__.py"): s *= 0.6
    scored.append((s, r, f, hits_strong[:8]))
scored.sort(key=lambda x: (-x[0], x[1]))

dirs = {}
for f in files:
    d = os.path.dirname(rel(f)); dirs[d] = dirs.get(d, 0) + 1

# ---- outlines for top modules
def outline(path, term_set, body_budget=6000):
    src = read(path, 400_000)
    try: tree = ast.parse(src)
    except Exception: return {"outline": ["(parse failed)"], "bodies": []}
    lines = src.splitlines()
    out, bodies, spent = [], [], 0
    def sig(node):
        try: args = ast.unparse(node.args)
        except Exception: args = "..."
        return f"def {node.name}({args})"
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"L{node.lineno}: {sig(node)}")
            if any(t in node.name for t in term_set) and spent < body_budget:
                seg = "\n".join(lines[node.lineno - 1: node.end_lineno])[:2500]
                bodies.append({"symbol": node.name, "lineno": node.lineno, "code": seg}); spent += len(seg)
        elif isinstance(node, ast.ClassDef):
            out.append(f"L{node.lineno}: class {node.name}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(f"  L{sub.lineno}: {sig(sub)}")
                    if any(t in sub.name or t in node.name for t in term_set) and spent < body_budget:
                        seg = "\n".join(lines[sub.lineno - 1: sub.end_lineno])[:2500]
                        bodies.append({"symbol": f"{node.name}.{sub.name}", "lineno": sub.lineno, "code": seg}); spent += len(seg)
    return {"outline": out[:120], "bodies": bodies}

term_set = set(t.lower() for t in strong) | set(common[:25])
top = scored[:8]
outlines = {}
for s, r, f, hits in top:
    if f.endswith(".py"):
        outlines[r] = outline(f, {t for t in term_set if len(t) >= 4})

snippets = {}
for n in ("reproduce.py", "reproduction.md", "paper.md"):
    p = os.path.join(WORKDIR, n)
    if os.path.isfile(p): snippets[n] = read(p, 7000 if n == "reproduce.py" else 3500)

print(json.dumps({
    "n_files": len(files),
    "dirs": sorted(dirs.items(), key=lambda x: -x[1])[:40],
    "terms_strong": strong[:40],
    "terms_common": common[:25],
    "reach": sorted([(rel(p), d) for p, d in reach.items()], key=lambda x: (x[1], x[0]))[:40],
    "ranked": [(round(s, 1), r, hits) for s, r, f, hits in scored[:60]],
    "outlines": outlines,
    "snippets": snippets,
}))
'''


def _run_in_image(image: str, workdir: str, instruction: str, *, timeout: int = 420) -> dict | None:
    cfg = json.dumps({"workdir": workdir, "instruction": instruction[:60_000]})
    cmd = [
        "docker", "run", "--rm", "-i", "-e", f"INV_CFG={cfg}", "--entrypoint", "bash",
        image, "-c",
        "cat > /tmp/_inv.py; (command -v python >/dev/null && python /tmp/_inv.py) "
        "|| python3 /tmp/_inv.py",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=_IN_IMAGE_SCRIPT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout or "").strip()[-800:]}
    try:
        last = proc.stdout.strip().splitlines()[-1]
        return json.loads(last)
    except Exception:
        return {"error": (proc.stdout or "")[-800:]}


def build_repo_inventory(task_dir: Path, *, max_files: int = 4000) -> str:
    """Read-only, ranked inventory of the pinned environment image.

    Ranks source files by (a) import reachability from reproduce.py and
    (b) hits of instruction/paper terms; emits AST outlines of the top modules
    with bodies of term-matching functions, plus reproduce.py / docs excerpts.
    """
    image = docker_image_ref(task_dir)
    workdir = workdir_in_image(task_dir)
    parts: list[str] = [f"workdir: {workdir}", f"image: {image or '(missing)'}"]
    if not image:
        parts.append("(no docker_image in task.toml; inventory unavailable)")
        return "\n".join(parts) + "\n"

    instruction = task_instruction(task_dir)
    data = _run_in_image(image, workdir, instruction)
    if not data or "error" in (data or {}):
        parts.append(f"(inventory failed: {(data or {}).get('error', 'no output')})")
        return "\n".join(parts) + "\n"

    parts.append(f"code_files_total: {data['n_files']}")
    parts.append("## directories (file counts)")
    parts.extend(f"{d or '.'}: {n}" for d, n in data["dirs"])
    parts.append("## terms_from_instruction")
    parts.append("strong: " + ", ".join(data["terms_strong"]))
    parts.append("common: " + ", ".join(data["terms_common"]))
    parts.append("## import_reach_from_reproduce.py (path, depth)")
    parts.extend(f"{p}  (depth {d})" for p, d in data["reach"])
    parts.append("## ranked_source_paths (score, path, matched_terms)")
    parts.extend(f"{s:>6}  {p}  {hits}" for s, p, hits in data["ranked"])

    parts.append("## snippets")
    for name, body in data["snippets"].items():
        parts.append(f"### {name}")
        parts.append(body.strip())

    parts.append("## outlines_of_top_modules")
    budget = 70_000
    for path, ol in data["outlines"].items():
        parts.append(f"### {path}")
        parts.extend(ol["outline"])
        for b in ol["bodies"]:
            parts.append(f"#### {path}::{b['symbol']} (L{b['lineno']})")
            parts.append(b["code"])
        if len("\n".join(parts)) > budget:
            parts.append("(inventory truncated)")
            break
    return "\n".join(parts) + "\n"
