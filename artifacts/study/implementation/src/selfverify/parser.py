"""JSON extraction helpers for Codex stdout / markdown fences."""

from __future__ import annotations

import json
import re
from typing import Any


class ParseError(ValueError):
    """Raised when no JSON object can be recovered from model output."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _balanced_object(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_json_from_output(raw: str) -> dict[str, Any]:
    """Parse a JSON object from Codex output (raw, fenced, or embedded)."""
    text = (raw or "").strip()
    if not text:
        raise ParseError("empty model output")

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = _FENCE_RE.search(text)
    if match:
        try:
            value = json.loads(match.group(1))
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    while start != -1:
        blob = _balanced_object(text, start)
        if blob is not None:
            try:
                value = json.loads(blob)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
        start = text.find("{", start + 1)

    raise ParseError(f"could not parse JSON from output ({len(text)} chars)")
