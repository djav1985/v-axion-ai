# v-axion-ai/tools/shell.py
# Purpose: Shell execution tool with env-based allowlist and Pydantic validation.
from __future__ import annotations
import os, asyncio, shlex
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from tool_registry import tool

def _allowed_cmds() -> List[str]:
    raw = os.getenv("SHELL_ALLOWED", "all").strip()
    if raw.lower() == "all":
        return ["all"]
    return [c.strip() for c in raw.split(",") if c.strip()]

def _check_cmd(command: str) -> None:
    allowed = _allowed_cmds()
    if "all" in allowed:
        return
    prog = shlex.split(command)[0] if command.strip() else ""
    if prog not in allowed:
        raise PermissionError(f"Shell command not allowed: {prog or '<empty>'}")

class ShellRunParams(BaseModel):
    command: str = Field(min_length=1)

@tool("shell.run", model=ShellRunParams, description="Execute a shell command.", instructions="Provide 'command'; returns stdout/stderr/returncode.")
async def shell_run(command: str) -> Dict[str, Any]:
    """Run the given shell command using /bin/sh -c and capture output."""
    _check_cmd(command)
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": out.decode(errors="ignore"),
        "stderr": err.decode(errors="ignore"),
    }
