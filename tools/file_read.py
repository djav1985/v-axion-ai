"""Drop-in tool for reading UTF-8 text files."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec
from ._path_guard import ensure_path_allowed


class FileReadParams(BaseModel):
    path: str = Field(min_length=1, description="Filesystem path to read")


async def run(path: str) -> Dict[str, Any]:
    """Read the entire file as UTF-8 text."""
    ensure_path_allowed(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return {"path": path, "content": handle.read()}


TOOL = ToolSpec(
    name="file.read",
    model=FileReadParams,
    handler=run,
    description="Read text file.",
    instructions="Provide 'path'; returns {'path','content'}",
)
