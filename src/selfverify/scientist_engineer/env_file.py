from __future__ import annotations

import os
from pathlib import Path


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[7:].lstrip()
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            values[key] = value
    return values


def apply_env_file(path: Path | None, *, overwrite: bool = False) -> dict[str, str]:
    """Load provider env into os.environ for Scientist + proxy.

    Pier still receives --env-file separately; this makes the same file work for
    the host-side Scientist OpenAI client.
    """
    if path is None:
        return {}
    values = parse_dotenv(path)

    # OpenRouter often uses OPENROUTER_API_KEY; Pier/Codex expect OPENAI_API_KEY.
    or_key = values.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if or_key and not values.get("OPENAI_API_KEY"):
        values["OPENAI_API_KEY"] = or_key
    if values.get("OPENAI_API_KEY") and not values.get("OPENROUTER_API_KEY"):
        values["OPENROUTER_API_KEY"] = values["OPENAI_API_KEY"]

    if not values.get("SCIENTIST_BASE_URL"):
        values["SCIENTIST_BASE_URL"] = (
            values.get("CODEX_BASE_URL")
            or values.get("OPENAI_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )
    if not values.get("CODEX_BASE_URL"):
        values["CODEX_BASE_URL"] = values.get("SCIENTIST_BASE_URL", "https://openrouter.ai/api/v1")

    # Keep proxy vars consistent if only one is set.
    proxy = (
        values.get("HTTPS_PROXY")
        or values.get("https_proxy")
        or values.get("HTTP_PROXY")
        or values.get("http_proxy")
    )
    if proxy:
        for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            values.setdefault(key, proxy)

    for key, value in values.items():
        if not value:
            continue
        if overwrite or key not in os.environ or not os.environ.get(key):
            os.environ[key] = value
    return values
