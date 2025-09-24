"""Pytest configuration for running asyncio tests without external plugins."""

from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Register the custom ``asyncio`` marker used throughout the test suite."""

    config.addinivalue_line(
        "markers",
        "asyncio: mark a test as running inside an asyncio event loop",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Execute ``async def`` tests by driving them with a fresh event loop."""

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_function(**pyfuncitem.funcargs))
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    return True
