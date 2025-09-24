"""Drop-in tool for retrieving filesystem metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec
from ._path_guard import ensure_path_allowed


class StatParams(BaseModel):
    path: str = Field(..., description="Path to lookup")


async def run(path: str) -> Dict[str, Any]:
    """Return filesystem metadata for a given path."""
    ensure_path_allowed(path)
    target = Path(path).expanduser()
    payload: Dict[str, Any] = {"path": str(target)}
    if not target.exists():
        payload["exists"] = False
        return payload
    payload["exists"] = True
    payload["type"] = "dir" if target.is_dir() else "file"
    payload["is_symlink"] = target.is_symlink()
    try:
        stat = target.stat()
        payload.update(
            {
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "permissions": stat.st_mode,
            }
        )
    except OSError as exc:
        payload["error"] = str(exc)
    return payload


TOOL = ToolSpec(
    name="fs.stat",
    model=StatParams,
    handler=run,
    description="Inspect metadata for a file or directory",
    instructions="Provide 'path' to receive size, timestamps, and flags",
)
