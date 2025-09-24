# v-axion-ai/tool_registry.py
# Purpose: Dynamic tool registry with Pydantic validation and auto-discovery.
from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Type

from pydantic import BaseModel, ValidationError


class ToolError(Exception): ...


@dataclass(slots=True)
class ToolSpec:
    """Lightweight descriptor for a single tool."""

    name: str
    model: Type[BaseModel]
    handler: Callable[..., Any]
    description: str = ""
    instructions: str = ""


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._models: Dict[str, Type[BaseModel]] = {}
        self.ctx: Dict[str, Any] = {}

    def _ensure_async(self, fn: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
        if asyncio.iscoroutinefunction(fn):
            return fn  # type: ignore[return-value]

        if not callable(fn):
            raise ToolError("Tool handler must be callable")

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result  # type: ignore[no-any-return]
            return result

        return wrapper

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        model: Type[BaseModel],
        description: str = "",
        instructions: str = "",
    ) -> None:
        if not name or not isinstance(name, str):
            raise ToolError("Tool name must be non-empty str")
        if name in self._tools:
            raise ToolError(f"Tool already registered: {name}")
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise ToolError("Tool must declare a Pydantic BaseModel via model=")
        self._tools[name] = self._ensure_async(fn)
        self._models[name] = model
        self._meta[name] = {
            "name": name,
            "description": description.strip(),
            "instructions": (instructions or (fn.__doc__ or "")).strip(),
            "schema": model.model_json_schema(),
        }

    def register_spec(self, spec: ToolSpec, *, module: Optional[str] = None) -> None:
        description = spec.description
        instructions = spec.instructions or (spec.handler.__doc__ or "")
        try:
            self.register(
                spec.name,
                spec.handler,
                model=spec.model,
                description=description,
                instructions=instructions,
            )
        except ToolError as exc:
            if "already registered" in str(exc):
                return
            context = f" from {module}" if module else ""
            raise ToolError(f"Failed to register {spec.name}{context}: {exc}") from exc

    def get(self, name: str) -> Callable[..., Awaitable[Any]]:
        try:
            return self._tools[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ToolError(f"Unknown tool: {name}") from exc

    def get_model(self, name: str) -> Type[BaseModel]:
        try:
            return self._models[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ToolError(f"Unknown tool (no model): {name}") from exc

    async def call(self, name: str, **kwargs) -> Any:
        fn = self.get(name)
        model = self.get_model(name)
        try:
            payload = model(**(kwargs or {}))
        except ValidationError as e:
            raise ToolError(f"Validation failed for {name}: {e}")
        return await fn(**payload.model_dump())

    def list(self) -> List[str]:
        return sorted(self._tools.keys())

    def describe(self) -> List[Dict[str, Any]]:
        descriptions: List[Dict[str, Any]] = []
        for _, meta in sorted(self._meta.items()):
            descriptions.append(
                {
                    "name": meta["name"],
                    "description": meta.get("description", ""),
                    "instructions": meta.get("instructions", ""),
                    "schema": meta.get("schema", {}),
                }
            )
        return descriptions


registry = ToolRegistry()


def tool(
    name: str, *, model: Type[BaseModel], description: str = "", instructions: str = ""
):
    def deco(fn):
        registry.register(
            name,
            fn,
            model=model,
            description=description,
            instructions=instructions or (fn.__doc__ or ""),
        )
        return registry.get(name)

    return deco


def _extract_specs(module: Any) -> Iterable[ToolSpec]:
    tool_obj = getattr(module, "TOOL", None)
    tools_obj = getattr(module, "TOOLS", None)
    specs: List[ToolSpec] = []
    if isinstance(tool_obj, ToolSpec):
        specs.append(tool_obj)
    if tools_obj:
        if isinstance(tools_obj, ToolSpec):
            specs.append(tools_obj)
        else:
            specs.extend(spec for spec in tools_obj if isinstance(spec, ToolSpec))
    return specs


def autodiscover_tools(package: str = "tools") -> None:
    pkg = importlib.import_module(package)
    for modinfo in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        short_name = modinfo.name.rsplit(".", 1)[-1]
        if short_name.startswith("_"):
            continue
        module = importlib.import_module(modinfo.name)
        for spec in _extract_specs(module):
            registry.register_spec(spec, module=modinfo.name)


def get_tool_descriptions() -> List[Dict[str, Any]]:
    return registry.describe()
