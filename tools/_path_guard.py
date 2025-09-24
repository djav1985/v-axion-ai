"""Shared helpers for enforcing filesystem allowlists."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


__all__ = ["ensure_path_allowed", "list_allowed_paths"]


def list_allowed_paths() -> List[str]:
    raw = os.getenv("FILES_ALLOWED", "all").strip()
    if raw.lower() == "all":
        return ["all"]
    return [p.strip() for p in raw.split(",") if p.strip()]


def ensure_path_allowed(path: str) -> None:
    allowed = list_allowed_paths()
    if "all" in allowed:
        return
    norm = Path(path).expanduser().resolve()
    for prefix in allowed:
        base = Path(prefix).expanduser().resolve()
        if norm == base or base in norm.parents:
            return
    raise PermissionError(f"File access not allowed: {path}")
