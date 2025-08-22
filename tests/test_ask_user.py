import asyncio
import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from interolog import Orchestrator
from action_registry import _handle_ask_user
from models.actions import AskUser


class DummyLLM:
    async def acomplete(self, prompt, system=None):
        return ""


@pytest.mark.asyncio
async def test_ask_user_waits_for_reply():
    asked = {}

    async def on_question(cid, question, choices):
        asked["data"] = (cid, question, choices)

    orch = Orchestrator(DummyLLM(), on_question=on_question)
    mon = orch._spawn(role="Tester", goal="g", parent_id=None, immortal=True, llm=False)
    model = AskUser(correlation_id="c1", question="Q?", choices=["y", "n"])

    task = asyncio.create_task(_handle_ask_user(mon, model))
    await asyncio.sleep(0.01)

    assert asked["data"] == ("c1", "Q?", ["y", "n"])
    assert not task.done()

    await orch.on_user_message("yes", "c1")
    await asyncio.sleep(0.01)

    assert task.done()
    assert await mon.inbox.get() == "[reply cid:c1] yes"
