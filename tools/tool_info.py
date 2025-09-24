"""Drop-in meta-tool for inspecting a single registered tool."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from tool_registry import ToolSpec, registry


class ToolInfoParams(BaseModel):
    tool_name: str = Field(..., description="Registered tool name")
    include_schema: bool = Field(
        False, description="When true, include JSON schema for arguments"
    )


def _slim(meta: Dict[str, Any], *, include_schema: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": meta.get("name"),
        "description": meta.get("description"),
        "instructions": meta.get("instructions"),
    }
    if include_schema:
        payload["schema"] = meta.get("schema")
    return payload


async def run(tool_name: str, include_schema: bool = False) -> Dict[str, Any]:
    """Return metadata for a single tool."""
    meta = registry.describe()
    for entry in meta:
        if entry.get("name") == tool_name:
            return _slim(entry, include_schema=include_schema)
    raise ValueError(f"Unknown tool: {tool_name}")


TOOL = ToolSpec(
    name="tool.info",
    model=ToolInfoParams,
    handler=run,
    description="Fetch metadata for a specific tool",
    instructions="Provide 'tool_name'; optional include_schema",
)
