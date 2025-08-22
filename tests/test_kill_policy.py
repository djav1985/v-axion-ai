import asyncio
import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from interolog import Orchestrator


class DummyLLM:
    async def acomplete(self, prompt: str, system: str = "") -> str:
        return "{\"actions\": []}"


@pytest.mark.asyncio
async def test_sub_cannot_kill_other_sub():
    o = Orchestrator(DummyLLM())
    await o.start("do work", with_comms=True)
    sub1 = await o.request_spawn(role="A", goal="g1", parent_id=o._main_id)
    sub2 = await o.request_spawn(role="B", goal="g2", parent_id=o._main_id)
    o.current_actor = sub1
    res = await o.kill_with_policy(sub2.state.id)
    assert res["ok"] is False
    assert "sub may only kill self" in res["error"]
    await o.shutdown()


@pytest.mark.asyncio
async def test_sub_cannot_kill_comms():
    o = Orchestrator(DummyLLM())
    await o.start("do work", with_comms=True)
    sub1 = await o.request_spawn(role="A", goal="g1", parent_id=o._main_id)
    o.current_actor = sub1
    res = await o.kill_with_policy(o._comms_id)
    assert res["ok"] is False
    assert res["error"]
    await o.shutdown()
