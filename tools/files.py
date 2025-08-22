# v-axion-ai/tools/files.py
# Purpose: File I/O tools with env-based allowlist and Pydantic validation.
from __future__ import annotations
import os
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from tool_registry import tool

def _allowed_paths() -> List[str]:
    raw = os.getenv("FILES_ALLOWED", "all").strip()
    if raw.lower() == "all":
        return ["all"]
    return [p.strip() for p in raw.split(",") if p.strip()]

def _check_path(path: str) -> None:
    allowed = _allowed_paths()
    if "all" in allowed:
        return
    norm = os.path.abspath(path)
    for prefix in allowed:
        if norm.startswith(os.path.abspath(prefix)):
            return
    raise PermissionError(f"File access not allowed: {path}")

class FileReadParams(BaseModel):
    path: str = Field(min_length=1)

class FileWriteParams(BaseModel):
    path: str = Field(min_length=1)
    content: str

class FileAppendParams(BaseModel):
    path: str = Field(min_length=1)
    content: str

class FileDeleteParams(BaseModel):
    path: str = Field(min_length=1)

@tool("file.read", model=FileReadParams, description="Read text file.", instructions="Provide 'path'; returns {'path','content'}")
async def file_read(path: str) -> Dict[str, Any]:
    """Read whole file as UTF-8 text."""
    _check_path(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return {"path": path, "content": f.read()}

@tool("file.write", model=FileWriteParams, description="Write/overwrite text file.", instructions="Provide 'path' and 'content'.")
async def file_write(path: str, content: str) -> Dict[str, Any]:
    """Overwrite file contents."""
    _check_path(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"path": path, "status": "written"}

@tool("file.append", model=FileAppendParams, description="Append text to file.", instructions="Provide 'path' and 'content'.")
async def file_append(path: str, content: str) -> Dict[str, Any]:
    """Append text to file."""
    _check_path(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
    return {"path": path, "status": "appended"}

@tool("file.delete", model=FileDeleteParams, description="Delete file.", instructions="Provide 'path'.")
async def file_delete(path: str) -> Dict[str, Any]:
    """Delete target file."""
    _check_path(path)
    os.remove(path)
    return {"path": path, "status": "deleted"}
