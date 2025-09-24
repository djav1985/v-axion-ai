"""Drop-in tool for writing UTF-8 text files."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec
from ._path_guard import ensure_path_allowed


class FileWriteParams(BaseModel):
    path: str = Field(min_length=1, description="Filesystem path to write")
    content: str


async def run(path: str, content: str) -> Dict[str, Any]:
    """Overwrite a file with UTF-8 encoded content."""
    ensure_path_allowed(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return {"path": path, "status": "written"}


TOOL = ToolSpec(
    name="file.write",
    model=FileWriteParams,
    handler=run,
    description="Write/overwrite text file.",
    instructions="Provide 'path' and 'content'.",
)
