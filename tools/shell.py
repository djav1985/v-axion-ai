# v-axion-ai/tools/shell.py
# Purpose: Shell execution tool with env-based allowlist and Pydantic validation.
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from pathlib import Path
from typing import Any, Dict, List
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
    parts = shlex.split(command)
    if not parts:
        raise PermissionError("Shell command not allowed: <empty>")
    prog = parts[0]
    resolved: Path | None
    if os.path.sep in prog:
        resolved = Path(prog).expanduser().resolve()
    else:
        located = shutil.which(prog)
        resolved = Path(located).resolve() if located else None
    for entry in allowed:
        if os.path.sep in entry:
            target = Path(entry).expanduser().resolve()
            if resolved is None:
                continue
            if target.is_dir():
                try:
                    resolved.relative_to(target)
                    return
                except ValueError:
                    continue
            if resolved == target:
                return
        else:
            if prog == entry:
                return
    raise PermissionError(f"Shell command not allowed: {prog}")


class ShellRunParams(BaseModel):
    command: str = Field(min_length=1)


@tool(
    "shell.run",
    model=ShellRunParams,
    description="Execute a shell command.",
    instructions="Provide 'command'; returns stdout/stderr/returncode.",
)
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
