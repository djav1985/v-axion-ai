# v-axion-ai/tool_registry.py
# Purpose: Dynamic tool registry with Pydantic validation and auto-discovery.
from __future__ import annotations
import importlib, pkgutil
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, ValidationError

class ToolError(Exception): ...

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._models: Dict[str, Type[BaseModel]] = {}
        self.ctx: Dict[str, Any] = {}

    def register(self, name: str, fn: Callable[..., Awaitable[Any]], *, model: Type[BaseModel], description: str="", instructions: str="") -> None:
        if not name or not isinstance(name, str):
            raise ToolError("Tool name must be non-empty str")
        if name in self._tools:
            raise ToolError(f"Tool already registered: {name}")
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise ToolError("Tool must declare a Pydantic BaseModel via model=")
        self._tools[name] = fn
        self._models[name] = model
        self._meta[name]  = {
            "name": name,
            "description": description.strip(),
            "instructions": (instructions or (fn.__doc__ or "")).strip(),
            "schema": model.model_json_schema(),
        }

    def get(self, name: str) -> Callable[..., Awaitable[Any]]:
        try: return self._tools[name]
        except KeyError: raise ToolError(f"Unknown tool: {name}")

    def get_model(self, name: str) -> Type[BaseModel]:
        try: return self._models[name]
        except KeyError: raise ToolError(f"Unknown tool (no model): {name}")

    async def call(self, name: str, **kwargs) -> Any:
        fn = self.get(name); Model = self.get_model(name)
        try:
            payload = Model(**(kwargs or {}))
        except ValidationError as e:
            raise ToolError(f"Validation failed for {name}: {e}")
        return await fn(**payload.model_dump())

    def list(self) -> List[str]:
        return sorted(self._tools.keys())

    def describe(self) -> List[Dict[str, Any]]:
        return [ {"name": m["name"], "description": m.get("description",""),
                  "instructions": m.get("instructions",""), "schema": m.get("schema",{})}
                 for _, m in sorted(self._meta.items()) ]

registry = ToolRegistry()

def tool(name: str, *, model: Type[BaseModel], description: str="", instructions: str=""):
    def deco(fn):
        async def awrap(*args, **kwargs):
            return await fn(*args, **kwargs)
        registry.register(name, awrap, model=model, description=description, instructions=instructions or (fn.__doc__ or ""))
        return awrap
    return deco

def autodiscover_tools(package: str="tools") -> None:
    pkg = importlib.import_module(package)
    for modinfo in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(modinfo.name)

def get_tool_descriptions() -> List[Dict[str, Any]]:
    return registry.describe()
