# v-axion-ai/action_registry.py
# Purpose: Canonical registry for role-scoped actions and their handlers.

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List

from models.actions import (
    ACTION_DEFS,
    AskUser,
    KillMonologue,
    ListMonologue,
    MessageMonologue,
    OpenMonologue,
    Sleep,
)

if TYPE_CHECKING:  # pragma: no cover
    from interolog import Monologue


def _available_models() -> List[Dict[str, Any]]:
    models = [{"provider": "hf_gemma", "id": "google/gemma-3-270m", "local": True}]
    if os.getenv("OPENAI_API_KEY"):
        models += [
            {"provider": "openai", "id": "gpt-4o-mini", "local": False},
            {"provider": "openai", "id": "gpt-4o", "local": False},
            {"provider": "openai", "id": "gpt-4.1-mini", "local": False},
        ]
    extra = os.getenv("AVAILABLE_MODELS", "").strip()
    if extra:
        for tok in [t for t in extra.split(",") if "/" in t]:
            p, mid = tok.split("/", 1)
            models.append(
                {
                    "provider": p.strip(),
                    "id": mid.strip(),
                    "local": (p.strip() == "hf_gemma"),
                }
            )
    return models


ROLE_ACTIONS = {
    "main": [
        "open_monologue",
        "ask_user",
        "sleep",
        "message_monologue",
        "list_monologue",
        "kill_monologue",
    ],
    "sub": ["sleep", "message_monologue", "kill_monologue"],
    "comms": [],
}


def get_actions_for(role: str) -> List[Dict[str, Any]]:
    role = (role or "").lower()
    allowed = ROLE_ACTIONS.get(role, ROLE_ACTIONS["sub"])
    avail = _available_models()
    out: List[Dict[str, Any]] = []
    for name in allowed:
        meta = ACTION_DEFS[name]
        Model = meta["model"]
        desc = meta["description"]
        if name == "open_monologue":
            desc += (
                " Available models: "
                + ", ".join(f"{m['provider']}/{m['id']}" for m in avail)
                + "."
            )
        out.append(
            {"action": name, "description": desc, "schema": Model.model_json_schema()}
        )
    return out


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

Handler = Callable[["Monologue", Any], Awaitable[None]]


async def _handle_open_monologue(monologue: "Monologue", model: OpenMonologue) -> None:
    """Spawn a new child monologue under the caller."""
    child = await monologue.o.request_spawn(
        role=model.role, goal=model.goal, parent_id=monologue.state.id
    )
    monologue.children.add(child.state.id)


async def _handle_ask_user(monologue: "Monologue", model: AskUser) -> None:
    """Route a question through the Communication monologue and await reply."""
    cid = model.correlation_id or uuid.uuid4().hex[:8]
    await monologue.o.comms_show_question(cid, model.question, model.choices or [])
    reply = await monologue.o.await_user_reply(cid)
    if reply is not None:
        await monologue.inbox.put(f"[reply cid:{cid}] {reply}")


async def _handle_sleep(monologue: "Monologue", model: Sleep) -> None:
    """Sleep with early wake if a message arrives for the target."""
    target = model.target_id or monologue.state.id
    await monologue.o.sleep_with_early_wake(target, model.seconds)


async def _handle_message_monologue(
    monologue: "Monologue", model: MessageMonologue
) -> None:
    """Send a message to another monologue and optionally wait for reply."""
    req_id = model.request_id or uuid.uuid4().hex[:8]
    payload = {
        "from_id": monologue.state.id,
        "to_id": model.to_id,
        "content": model.content,
        "request_id": req_id,
    }
    await monologue.o.route_incoming(model.to_id, payload)
    if model.wait_for_reply:
        reply = await monologue.o.await_reply(req_id)
        if isinstance(reply, dict):
            await monologue.inbox.put(reply.get("content", ""))


async def _handle_list_monologue(monologue: "Monologue", model: ListMonologue) -> None:
    """List active monologues and enqueue the summary for the caller."""
    lst = monologue.o.list_monologues()
    await monologue.inbox.put(json.dumps(lst))


async def _handle_kill_monologue(monologue: "Monologue", model: KillMonologue) -> None:
    """Terminate monologues according to policy."""
    await monologue.o.kill_with_policy(model.target_id)


ACTION_HANDLERS: Dict[str, Handler] = {
    "open_monologue": _handle_open_monologue,
    "ask_user": _handle_ask_user,
    "sleep": _handle_sleep,
    "message_monologue": _handle_message_monologue,
    "list_monologue": _handle_list_monologue,
    "kill_monologue": _handle_kill_monologue,
}
