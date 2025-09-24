"""Filesystem utility tools for directory listing and metadata lookup."""

from __future__ import annotations

import fnmatch
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from tool_registry import tool
from .files import _check_path


def _as_entry(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "type": "dir" if path.is_dir() else "file",
        "is_symlink": path.is_symlink(),
    }
    try:
        stat = path.stat()
    except OSError as exc:
        info["error"] = str(exc)
        return info
    info.update(
        {
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )
    return info


def _iter_dir(
    root: Path,
    *,
    recursive: bool,
    include_hidden: bool,
) -> Iterable[Path]:
    if recursive:
        for child in root.rglob("*"):
            if not include_hidden and child.name.startswith("."):
                continue
            yield child
    else:
        for child in root.iterdir():
            if not include_hidden and child.name.startswith("."):
                continue
            yield child


class DirListParams(BaseModel):
    path: str = Field(".", description="Directory path to inspect")
    recursive: bool = Field(False, description="Recurse into subdirectories")
    pattern: Optional[str] = Field(
        default=None, description="Optional fnmatch pattern for filtering entries"
    )
    include_hidden: bool = Field(
        False, description="If false, entries starting with '.' are skipped"
    )
    max_entries: int = Field(
        200,
        ge=1,
        le=5000,
        description="Limit the number of entries returned",
    )


class StatParams(BaseModel):
    path: str = Field(..., description="Path to lookup")


@tool(
    "fs.list",
    model=DirListParams,
    description="List files and directories",
    instructions="Provide 'path'; optional pattern, recursion, and include_hidden",
)
async def fs_list(
    path: str,
    recursive: bool = False,
    pattern: Optional[str] = None,
    include_hidden: bool = False,
    max_entries: int = 200,
) -> Dict[str, Any]:
    """Return directory entries matching the query."""
    _check_path(path)
    root = Path(path).expanduser()
    if not root.exists():
        return {"path": str(root), "entries": [], "error": "not found"}
    if not root.is_dir():
        return {"path": str(root), "entries": [], "error": "not a directory"}

    entries: List[Dict[str, Any]] = []
    try:
        iterator = _iter_dir(root, recursive=recursive, include_hidden=include_hidden)
        for item in iterator:
            if pattern and not fnmatch.fnmatch(item.name, pattern):
                continue
            entries.append(_as_entry(item))
            if len(entries) >= max_entries:
                break
    except OSError as exc:
        return {"path": str(root), "entries": entries, "error": str(exc)}
    return {"path": str(root), "entries": entries, "recursive": recursive}


@tool(
    "fs.stat",
    model=StatParams,
    description="Inspect metadata for a file or directory",
    instructions="Provide 'path' to receive size, timestamps, and flags",
)
async def fs_stat(path: str) -> Dict[str, Any]:
    """Return filesystem metadata for a given path."""
    _check_path(path)
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
