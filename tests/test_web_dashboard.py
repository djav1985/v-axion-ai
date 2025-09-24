import socket

import aiohttp
import pytest

from dashboard.web import WebDashboard
from interolog import Orchestrator
from models.injections import InjectionModel


class DummyLLM:
    async def acomplete(self, prompt: str, system: str = "") -> str:  # pragma: no cover
        return '{"actions": []}'


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _noop_injection(inj, state):  # pragma: no cover - test helper
    return None


@pytest.mark.asyncio
async def test_web_dashboard_serves_chat_and_details():
    orch = Orchestrator(DummyLLM(), on_injection=_noop_injection)
    await orch.start("monitor", with_comms=False)

    port = _unused_port()
    dash = WebDashboard(orch, host="127.0.0.1", port=port, refresh=0.1)
    await dash.start()

    try:
        main_state = orch.main.state
        inj = InjectionModel(from_id=main_state.id, content="hello from main")
        await orch.on_injection(inj, main_state)

        async with aiohttp.ClientSession() as session:
            resp = await session.get(f"http://127.0.0.1:{port}/api/chat")
            data = await resp.json()
            assert data["entries"], "expected chat history entries"
            assert any(entry["content"] == "hello from main" for entry in data["entries"])

            await session.post(
                f"http://127.0.0.1:{port}/api/message",
                json={"content": "ping web"},
            )

            resp2 = await session.get(f"http://127.0.0.1:{port}/api/chat")
            data2 = await resp2.json()
            assert any(entry["source"].startswith("user") for entry in data2["entries"])

            detail = await session.get(f"http://127.0.0.1:{port}/api/monologue/{main_state.id}")
            detail_data = await detail.json()
            assert detail_data["id"] == main_state.id
            assert "recent_context" in detail_data
    finally:
        await dash.stop()
        await orch.shutdown()
