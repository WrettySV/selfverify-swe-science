"""Scientist→Engineer generation-time role split for SWE-bench Science."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SWE_SCIENCE_ROOT = Path(
    os.environ.get(
        "SWE_SCIENCE_ROOT",
        "/home/lukina/SWE-bench-Science/huggingface",
    )
)

SELECTIONS_DIR = PROJECT_ROOT / "selections"
WORK_DIR = PROJECT_ROOT / "work"
RESULTS_DIR = PROJECT_ROOT / "results"


def swe_science_root() -> Path:
    root = Path(os.environ.get("SWE_SCIENCE_ROOT", DEFAULT_SWE_SCIENCE_ROOT))
    if not root.is_dir():
        raise FileNotFoundError(
            f"SWE-bench Science HF snapshot not found: {root}. "
            "Set SWE_SCIENCE_ROOT or download the dataset."
        )
    return root
