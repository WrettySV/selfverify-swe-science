from __future__ import annotations

from typing import Any

BRIEF_REQUIRED_KEYS = (
    "task_id",
    "scientific_principle",
    "violated_invariant",
    "observable_symptom",
    "suspected_loci",
    "acceptance_checks",
    "anti_hardcoding",
    "confidence",
)


def validate_brief(data: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in BRIEF_REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"scientist brief missing keys: {missing}")
    if not isinstance(data["suspected_loci"], list):
        raise ValueError("suspected_loci must be a list")
    if not isinstance(data["acceptance_checks"], list):
        raise ValueError("acceptance_checks must be a list")
    if not isinstance(data["anti_hardcoding"], list):
        raise ValueError("anti_hardcoding must be a list")
    conf = float(data["confidence"])
    if not 0.0 <= conf <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    data["confidence"] = conf
    if "evidence_notes" in data and not isinstance(data["evidence_notes"], list):
        raise ValueError("evidence_notes must be a list when present")
    data.setdefault("evidence_notes", [])

    probes = data.get("metamorphic_probes", [])
    if not isinstance(probes, list):
        raise ValueError("metamorphic_probes must be a list")
    clean: list[dict[str, str]] = []
    for i, probe in enumerate(probes):
        if isinstance(probe, str):
            clean.append({"name": f"probe_{i+1}", "relation": probe, "code": ""})
            continue
        if not isinstance(probe, dict):
            raise ValueError("metamorphic_probes entries must be objects")
        clean.append(
            {
                "name": str(probe.get("name") or f"probe_{i+1}"),
                "relation": str(probe.get("relation") or ""),
                "code": str(probe.get("code") or ""),
            }
        )
    data["metamorphic_probes"] = clean
    return data


_PUBLIC_LEAK = (
    "reproduce.py",
    "exit code",
    "exit with code",
    "workflow_completed",
    "fixtures/",
    "outputs/",
    "reproduction_report",
)


def public_oriented_checks(data: dict[str, Any]) -> list[str]:
    """Return acceptance checks / probes that lean on the public fixture."""
    bad: list[str] = []
    for check in data.get("acceptance_checks", []):
        low = str(check).lower()
        if any(tok in low for tok in _PUBLIC_LEAK):
            bad.append(str(check))
    for probe in data.get("metamorphic_probes", []):
        low = (probe.get("code", "") + " " + probe.get("relation", "")).lower()
        if any(tok in low for tok in _PUBLIC_LEAK):
            bad.append(f"probe:{probe.get('name')}")
    return bad
