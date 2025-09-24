"""Drop-in meta-tool for listing registered tools."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from tool_registry import ToolSpec, registry


class ToolListParams(BaseModel):
    detailed: bool = Field(
        False, description="Include descriptions and instructions for each tool"
    )
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


async def run(detailed: bool = False, include_schema: bool = False) -> Dict[str, Any]:
    """Return available tool names with optional metadata."""
    meta = registry.describe()
    if not detailed and not include_schema:
        return {"tools": [entry.get("name") for entry in meta]}
    tools: List[Dict[str, Any]] = []
    for entry in meta:
        tools.append(_slim(entry, include_schema=include_schema))
    return {"tools": tools}


TOOL = ToolSpec(
    name="tool.list",
    model=ToolListParams,
    handler=run,
    description="Enumerate registered tools",
    instructions="Set detailed=true for descriptions; include_schema adds JSON schema",
)
