"""Meta-tools for inspecting the registry itself."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from tool_registry import registry, tool


class ToolListParams(BaseModel):
    detailed: bool = Field(
        False, description="Include descriptions and instructions for each tool"
    )
    include_schema: bool = Field(
        False, description="When true, include JSON schema for arguments"
    )


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


@tool(
    "tool.list",
    model=ToolListParams,
    description="Enumerate registered tools",
    instructions="Set detailed=true for descriptions; include_schema adds JSON schema",
)
async def tool_list(
    detailed: bool = False, include_schema: bool = False
) -> Dict[str, Any]:
    """Return available tool names with optional metadata."""
    meta = registry.describe()
    if not detailed and not include_schema:
        return {"tools": [entry.get("name") for entry in meta]}
    tools: List[Dict[str, Any]] = []
    for entry in meta:
        tools.append(_slim(entry, include_schema=include_schema))
    return {"tools": tools}


@tool(
    "tool.info",
    model=ToolInfoParams,
    description="Fetch metadata for a specific tool",
    instructions="Provide 'tool_name'; optional include_schema",
)
async def tool_info(tool_name: str, include_schema: bool = False) -> Dict[str, Any]:
    """Return metadata for a single tool."""
    meta = registry.describe()
    for entry in meta:
        if entry.get("name") == tool_name:
            return _slim(entry, include_schema=include_schema)
    raise ValueError(f"Unknown tool: {tool_name}")
