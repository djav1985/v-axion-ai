"""Drop-in tool for deleting files."""

from __future__ import annotations

import os
from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec
from ._path_guard import ensure_path_allowed


class FileDeleteParams(BaseModel):
    path: str = Field(min_length=1, description="Filesystem path to delete")


async def run(path: str) -> Dict[str, Any]:
    """Delete the specified file."""
    ensure_path_allowed(path)
    os.remove(path)
    return {"path": path, "status": "deleted"}


TOOL = ToolSpec(
    name="file.delete",
    model=FileDeleteParams,
    handler=run,
    description="Delete file.",
    instructions="Provide 'path'.",
)
