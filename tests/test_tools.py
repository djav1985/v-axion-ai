import importlib
import pkgutil
from pathlib import Path
import tempfile

import pytest

import tools
from tool_registry import ToolSpec, autodiscover_tools, registry


if "tool.list" not in registry.list():
    autodiscover_tools("tools")


@pytest.mark.asyncio
async def test_tool_list_returns_registered_names():
    payload = await registry.call("tool.list")
    tools = payload["tools"]
    assert isinstance(tools, list)
    assert "tool.list" in tools
    detailed = await registry.call("tool.list", detailed=True, include_schema=True)
    assert any(entry["name"] == "file.read" for entry in detailed["tools"])


@pytest.mark.asyncio
async def test_tool_info_fetches_single_tool():
    info = await registry.call("tool.info", tool_name="shell.run", include_schema=False)
    assert info["name"] == "shell.run"
    assert "execute" in (info.get("description") or "").lower()


@pytest.mark.asyncio
async def test_fs_tools_respect_allowlist(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        monkeypatch.setenv("FILES_ALLOWED", str(path))
        target = path / "example.txt"
        target.write_text("hello", encoding="utf-8")

        listing = await registry.call("fs.list", path=str(path))
        names = {entry["name"] for entry in listing["entries"]}
        assert "example.txt" in names

        stat = await registry.call("fs.stat", path=str(target))
        assert stat["exists"] is True
        assert stat["type"] == "file"
        assert stat["size"] == 5


@pytest.mark.asyncio
async def test_python_exec_runs_code():
    result = await registry.call(
        "python.exec",
        code="import math\nprint(math.sqrt(16))",
        timeout=5.0,
    )
    assert result["status"] == "ok"
    assert "4.0" in result["stdout"].strip()
    assert result["returncode"] == 0


def test_every_tool_module_exports_tool_spec():
    modules = pkgutil.iter_modules(tools.__path__, tools.__name__ + ".")
    for modinfo in modules:
        short_name = modinfo.name.rsplit(".", 1)[-1]
        if short_name.startswith("_"):
            continue
        module = importlib.import_module(modinfo.name)
        spec = getattr(module, "TOOL", None)
        assert isinstance(spec, ToolSpec)
