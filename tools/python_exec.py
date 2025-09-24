"""Python execution tool for running snippets in a subprocess."""

from __future__ import annotations

import asyncio
import sys
from typing import Dict

from pydantic import BaseModel, Field

from tool_registry import tool


class PythonExecParams(BaseModel):
    code: str = Field(..., description="Python source to run")
    timeout: float = Field(30.0, ge=1.0, le=300.0, description="Timeout in seconds")


@tool(
    "python.exec",
    model=PythonExecParams,
    description="Execute Python code in an isolated subprocess",
    instructions="Provide 'code'; stdout/stderr/returncode returned. Timeout configurable",
)
async def python_exec(code: str, timeout: float = 30.0) -> Dict[str, object]:
    """Run python code via `python -u -c` and capture output."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
        status = "ok"
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        out, err = b"", b"Timeout"
        status = "timeout"
    returncode = proc.returncode if proc.returncode is not None else -1
    return {
        "status": status,
        "returncode": returncode,
        "stdout": out.decode(errors="ignore"),
        "stderr": err.decode(errors="ignore"),
    }
