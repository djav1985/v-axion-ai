"""Drop-in tool for appending to text files."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec
from ._path_guard import ensure_path_allowed


class FileAppendParams(BaseModel):
    path: str = Field(min_length=1, description="Filesystem path to append")
    content: str


async def run(path: str, content: str) -> Dict[str, Any]:
    """Append UTF-8 text to the end of a file."""
    ensure_path_allowed(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(content)
    return {"path": path, "status": "appended"}


TOOL = ToolSpec(
    name="file.append",
    model=FileAppendParams,
    handler=run,
    description="Append text to file.",
    instructions="Provide 'path' and 'content'.",
)
