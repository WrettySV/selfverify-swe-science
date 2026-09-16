"""Build Codex config.toml with an explicit model_context_window."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _safe_base_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        if text.startswith("export "):
            text = text[7:].lstrip()
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def render_codex_config(
    *,
    base_url: str,
    wire_api: str = "responses",
    model_context_window: int = 262144,
) -> str:
    """Gateway block + explicit context window (must match vLLM max-model-len)."""
    wire = wire_api.strip().lower().replace("-", "_")
    if wire in {"openai_responses"}:
        wire = "responses"
    if wire in {"openai_chat"}:
        wire = "chat"
    if wire not in {"responses", "chat"}:
        raise ValueError("wire_api must be responses or chat")
    return "\n".join(
        [
            'model_provider = "science_bench_gateway"',
            f"model_context_window = {int(model_context_window)}",
            "",
            "[model_providers.science_bench_gateway]",
            'name = "SWE-bench Science Gateway"',
            f"base_url = {json.dumps(base_url)}",
            f"wire_api = {json.dumps(wire)}",
            'env_key = "OPENAI_API_KEY"',
            "",
        ]
    )


def config_from_env_file(path: Path) -> tuple[str, str, str]:
    """Return (model, config_toml, safe_base_url)."""
    env = parse_dotenv(path)
    model = (env.get("MODEL") or "Qwen3.8-27B").strip()
    base_url = (
        env.get("CODEX_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or "http://172.17.0.1:8001/v1"
    ).strip()
    wire = (env.get("CODEX_WIRE_API") or "responses").strip()
    window = int(env.get("CODEX_MODEL_CONTEXT_WINDOW") or "262144")
    toml = render_codex_config(
        base_url=base_url, wire_api=wire, model_context_window=window
    )
    return model, toml, _safe_base_url(base_url)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: provider_overlay.py <env-file>", file=sys.stderr)
        return 2
    model, toml, _ = config_from_env_file(Path(sys.argv[1]))
    print(f"# model={model}")
    print(toml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
