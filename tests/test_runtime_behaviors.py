import asyncio
import os
import sys

import pytest
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from interolog import Monologue, Orchestrator  # noqa: E402
from models.actions import ActionName, InjectAction, ToolAction  # noqa: E402
from models.state import MonologueStateModel  # noqa: E402
from tool_registry import ToolError, registry  # noqa: E402


class DummyLLM:
    async def acomplete(
        self, prompt: str, system: str = ""
    ) -> str:  # pragma: no cover - test double
        return '{"actions": []}'


class EchoInput(BaseModel):
    message: str


async def _echo_tool(message: str) -> dict[str, str]:
    await asyncio.sleep(0)
    return {"echo": message}


def _ensure_test_tool() -> None:
    if "test.echo" in registry.list():
        return
    try:
        registry.register(
            "test.echo", _echo_tool, model=EchoInput, description="Echo test tool"
        )
    except ToolError:
        pass


@pytest.mark.asyncio
async def test_sleep_with_early_wake():
    orch = Orchestrator(DummyLLM())
    await orch.start("stay alert", with_comms=False)
    task = asyncio.create_task(orch.sleep_with_early_wake(orch._main_id, 1.0))  # type: ignore[arg-type]
    await asyncio.sleep(0.05)
    await orch.notify_actor_message(orch._main_id)  # type: ignore[arg-type]
    woke = await asyncio.wait_for(task, 0.5)
    assert woke is True
    await orch.shutdown()


@pytest.mark.asyncio
async def test_route_incoming_sets_reply():
    orch = Orchestrator(DummyLLM())
    await orch.start("receive", with_comms=False)
    req_id = "req123"
    waiter = asyncio.create_task(orch.await_reply(req_id))
    await asyncio.sleep(0)
    payload = {"from_id": "tester", "reply_to": req_id, "content": "done"}
    await orch.route_incoming(orch._main_id, payload)  # type: ignore[arg-type]
    reply = await asyncio.wait_for(waiter, 0.5)
    assert isinstance(reply, dict)
    assert reply["content"] == "done"
    await orch.shutdown()


@pytest.mark.asyncio
async def test_dispatch_records_state_and_tool_usage():
    orch = Orchestrator(DummyLLM())
    state = MonologueStateModel(id="mono1", role="Tester", goal="exercise actions")
    mono = Monologue(orch, state, immortal=False, use_llm=True)

    _ensure_test_tool()

    inject = InjectAction(type=ActionName.INJECT, content="hello")
    await mono._dispatch_actions([inject])
    injected = await orch._main_inbox.get()
    assert injected.content == "hello"
    assert mono.state.last_action == "inject"
    assert any(entry.startswith("inject:") for entry in mono.context_buffer)

    tool = ToolAction(type=ActionName.TOOL, name="test.echo", args={"message": "ping"})
    await mono._dispatch_actions([tool])
    assert mono.state.tool_calls == 1
    assert mono.state.last_action == "tool"
    tool_msg = await mono.inbox.get()
    assert "test.echo" in tool_msg
    assert any("tool:test.echo" in entry for entry in mono.context_buffer)

    await orch.shutdown()
