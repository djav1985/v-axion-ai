
from __future__ import annotations
import asyncio, json, os, re, uuid
from typing import Any, Dict, List, Optional, Callable, Awaitable

from models.actions import parse_actions, ActionType
from models.injections import InjectionModel
from models.state import MonologueStateModel
from tool_registry import registry as TOOL_REGISTRY, autodiscover_tools, get_tool_descriptions
# tools autodiscovered
# tools autodiscovered
# Autodiscover drop-in tools at import time
try:
    autodiscover_tools('tools')
except Exception:
    pass

CONTROL_SYSTEM = """You are an internal monologue actor.
Output ONLY JSON with this schema, no prose:

{
  "actions": [
    {"type":"inject","content": "<short message to main>"},
    {"type":"spawn","role":"<role name>","goal":"<goal for child>"},
    {"type":"stop_self"},
    {"type":"stop_child","id":"<child_id>"},
    {"type":"sleep","seconds": <int>},
    {"type":"idle","seconds": <int>},
    {"type":"tool","name":"<tool name>","args":{}},
    {"type":"report_status"},
    {"type":"route_message","to":"<actor_id>","content":"..."},
    {"type":"ask_user","id":"q1","content":"...","choices":["y","n"]},
    {"type":"user_reply","in_reply_to":"q1","content":"..."}
  ]
}

Rules:
- JSON only. No thoughts, no prose.
- Keep 'inject' concise.
- Tools default to dry-run unless explicitly set otherwise.
- Prefer: read/plan -> confirm -> act.
- If idle, emit a short sleep/idle.
"""

def extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {"actions":[{"type":"idle","seconds":1}]}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {"actions":[{"type":"idle","seconds":1}]}

class Orchestrator:
    def __init__(
        self,
        llm,
        *,
        max_sub_steps: int = int(os.getenv("MAX_SUB_STEPS", 12)),
        cycle_delay: float = float(os.getenv("CYCLE_DELAY", 0.2)),
        max_children: int = int(os.getenv("MAX_CHILDREN", 16)),
        on_injection: Optional[Callable[[InjectionModel, MonologueStateModel], Awaitable[None]]] = None,
        telemetry: Optional[Any] = None,
    ):
        self.llm = llm
        self.max_sub_steps = max_sub_steps
        self.cycle_delay = cycle_delay
        self.max_children = max_children
        self.on_injection = on_injection or (lambda inj, st: asyncio.sleep(0))  # type: ignore
        self._actors: Dict[str, Monologue] = {}
        self._main_id: Optional[str] = None
        self._comms_id: Optional[str] = None
        self._main_inbox: asyncio.Queue[InjectionModel] = asyncio.Queue()
        self._task_group: set[asyncio.Task] = set()
        self._sleep_events: dict[str, asyncio.Event] = {}
        self._pending_replies: dict[str, asyncio.Future] = {}
        self._inboxes: dict[str, asyncio.Queue] = {}
        self.tool_registry = TOOL_REGISTRY
        # The actor currently invoking orchestrator APIs. Used for permission checks.
        self.current_actor: "Monologue" | None = None

    @property
    def main(self) -> "Monologue":
        return self._actors[self._main_id]  # type: ignore

    @property
    def comms(self) -> Optional["Monologue"]:
        return self._actors.get(self._comms_id) if self._comms_id else None

    async def start(self, main_goal: str, *, with_comms: bool = True) -> str:
        main = self._spawn(role="Main", goal=main_goal, parent_id=None, immortal=True)
        self._main_id = main.state.id
        if with_comms and os.getenv("COMMS_ENABLED","true").lower() == "true":
            comms = self._spawn(role=os.getenv("COMMS_ROLE","Comms"), goal=os.getenv("COMMS_GOAL","Handle user I/O and forward to Main."), parent_id=None, immortal=True, llm=False)
            self._comms_id = comms.state.id
        self._task_group.add(asyncio.create_task(self._main_sink()))
        self._task_group.add(asyncio.create_task(main.run()))
        if self.comms:
            self._task_group.add(asyncio.create_task(self.comms.run()))
        pass
        return main.state.id

    async def shutdown(self):
        for _, actor in list(self._actors.items()):
            if actor.immortal:
                continue
            actor.state.running = False
        await asyncio.sleep(0.05)
        for t in list(self._task_group):
            t.cancel()
        pass

    async def inject_to_main(self, inj: InjectionModel):
        await self._main_inbox.put(inj)
        pass

    async def _main_sink(self):
        while True:
            inj = await self._main_inbox.get()
            await self.on_injection(inj, self.main.state)

    def _spawn(self, *, role: str, goal: str, parent_id: Optional[str], immortal: bool=False, llm: bool=True) -> "Monologue":
        if not immortal:
            subs = [a for a in self._actors.values() if not a.immortal]
            if len(subs) >= self.max_children:
                oldest = sorted(subs, key=lambda a: a.state.created)[0]
                oldest.state.running = False

        aid = uuid.uuid4().hex[:8]
        actor = Monologue(
            orchestrator=self,
            state=MonologueStateModel(id=aid, role=role, goal=goal, parent_id=parent_id),
            immortal=immortal,
            use_llm=llm
        )
        self._actors[aid] = actor
        self._task_group.add(asyncio.create_task(actor.run()))
        pass
        return actor

    async def request_spawn(self, *, role: str, goal: str, parent_id: str) -> "Monologue":
        return self._spawn(role=role, goal=goal, parent_id=parent_id, immortal=False)

    async def stop_child(self, actor_id: str):
        a = self._actors.get(actor_id)
        if a and not a.immortal:
            a.state.running = False
            pass

    async def comms_send(self, text: str):
        if not self.comms:
            return
        await self.comms.inbox.put(text)
        pass

    def snapshot(self) -> Dict[str,Any]:
        actors = []
        for aid, a in self._actors.items():
            actors.append({
                "id": aid,
                "role": a.state.role,
                "step": a.state.step,
                "running": a.state.running,
                "inbox_size": a.inbox.qsize(),
                "tool_calls": a.state.tool_calls,
                "last_action": a.state.last_action,
                "last_error": a.state.last_error,
                "parent_id": a.state.parent_id,
            })
        return {"actors": actors, "main": self._main_id, "comms": self._comms_id}

    def role_of(self, actor_id: str) -> str:
        if actor_id == self._main_id:
            return "main"
        if actor_id == self._comms_id:
            return "comms"
        return "sub"

    def is_child_of_main(self, actor_id: str) -> bool:
        a = self._actors.get(actor_id)
        try:
            return bool(a and a.state.parent_id == self._main_id)
        except Exception:
            return False

    def list_monologues(self) -> list[dict]:
        out = []
        for aid, a in self._actors.items():
            out.append({
                "id": aid,
                "role": getattr(a.state, "role", ""),
                "parent_id": getattr(a.state, "parent_id", None),
                "running": getattr(a.state, "running", False),
            })
        return out

    async def kill_with_policy(self, target_id: str | None):
        # sub: only self
        # main: any sub except comms
        # if None for sub, implies self
        # for main None means no-op
        caller = getattr(self, "current_actor", None)
        caller_id = getattr(caller.state, "id", None) if caller else self._main_id
        caller_role = self.role_of(caller_id)
        tid = target_id or caller_id
        if caller_role == "sub" and tid != caller_id:
            return {"ok": False, "error": "sub may only kill self"}
        if tid == self._comms_id:
            return {"ok": False, "error": "cannot kill Communication"}
        a = self._actors.get(tid)
        if not a:
            return {"ok": False, "error": "unknown id"}
        a.state.running = False
        return {"ok": True, "killed": tid}

    async def sleep_with_early_wake(self, target_id: str, seconds: float) -> bool:
        ev = self._sleep_events.setdefault(target_id, asyncio.Event())
        ev.clear()
        try:
            await asyncio.wait_for(ev.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def notify_actor_message(self, target_id: str):
        ev = self._sleep_events.setdefault(target_id, asyncio.Event())
        ev.set()

    async def await_reply(self, request_id: str):
        fut = self._pending_replies.get(request_id)
        if fut is None or fut.done():
            fut = asyncio.get_event_loop().create_future()
            self._pending_replies[request_id] = fut
        return await fut

    async def route_incoming(self, target_id: str, payload: dict):
        # If this is a reply with reply_to, resolve pending waiter and also push readable to inbox
        rid = payload.get("reply_to")
        if rid and (fut := self._pending_replies.pop(rid, None)):
            if not fut.done():
                fut.set_result(payload)
        # Always enqueue a human-readable line to target's inbox for LLM visibility
        line = payload.get("content")
        if payload.get("request_id"):
            line = f"[from:{payload.get('from_id')} req:{payload.get('request_id')}] " + (line or "")
        elif payload.get("reply_to"):
            line = f"[from:{payload.get('from_id')} reply_to:{payload.get('reply_to')}] " + (line or "")
        q = self._actors[target_id].inbox
        await q.put(line or "")
        await self.notify_actor_message(target_id)

    async def comms_show_question(self, correlation_id: str, question: str, choices: list[str]):
        # In real app, render via UI. Here, enqueue to comms inbox for visibility.
        if self._comms_id and self._comms_id in self._actors:
            await self._actors[self._comms_id].inbox.put(f"[ASK cid:{correlation_id}] {question} choices={choices or []}")
            await self.notify_actor_message(self._comms_id)

    async def await_user_reply(self, correlation_id: str, timeout: float | None = None):
        # Reuse reply mechanism
        try:
            if timeout is None:
                fut = self._pending_replies.get(correlation_id)
                if fut is None or fut.done():
                    fut = asyncio.get_event_loop().create_future()
                    self._pending_replies[correlation_id] = fut
                res = await fut
            else:
                fut = self._pending_replies.get(correlation_id)
                if fut is None or fut.done():
                    fut = asyncio.get_event_loop().create_future()
                    self._pending_replies[correlation_id] = fut
                res = await asyncio.wait_for(fut, timeout=timeout)
            return res.get("content") if isinstance(res, dict) else res
        except asyncio.TimeoutError:
            return None

    async def on_user_message(self, text: str, correlation_id: str | None = None):
        # If this responds to an ask, resolve it; otherwise forward to main
        if correlation_id and (fut := self._pending_replies.pop(correlation_id, None)):
            if not fut.done():
                fut.set_result({"from_id": "user", "reply_to": correlation_id, "content": text})
            if self._main_id in self._actors:
                await self._actors[self._main_id].inbox.put(f"[USER replied cid:{correlation_id}] {text}")
        else:
            if self._main_id in self._actors:
                await self._actors[self._main_id].inbox.put(f"[USER] {text}")
                await self.notify_actor_message(self._main_id)
class Monologue:
    def __init__(self, orchestrator: Orchestrator, state: MonologueStateModel, immortal: bool=False, use_llm: bool=True):
        self.o = orchestrator
        self.state = state
        self.immortal = immortal
        self.children: set[str] = set()
        self.inbox: asyncio.Queue[str] = asyncio.Queue()
        self.context_buffer: List[str] = []
        self.use_llm = use_llm

    async def run(self):
        try:
            while self.state.running and (self.immortal or self.state.step < self.o.max_sub_steps):
                await asyncio.sleep(self.o.cycle_delay)
                if self.use_llm:
                    prompt = self._build_prompt()
                    raw = await self.o.llm.acomplete(prompt, system=CONTROL_SYSTEM)
                    data = extract_json(raw)
                    actions = parse_actions(data.get("actions", []))
                    await self._dispatch_actions(actions)
                else:
                    msgs = []
                    while True:
                        try:
                            msgs.append(self.inbox.get_nowait())
                        except asyncio.QueueEmpty:
                            break
                    for m in msgs:
                        try:
                            self.o.current_actor = self
                            await self.o.inject_to_main(
                                InjectionModel(from_id=self.state.id, content=f"[user] {m}")
                            )
                        finally:
                            self.o.current_actor = None
                self.state.step += 1
                await asyncio.sleep(self.o.cycle_delay)
                pass
        except asyncio.CancelledError:
            pass
        finally:
            if not self.immortal:
                self.state.running = False

    def _build_prompt(self) -> str:
        ctx_msgs = "\n".join(self.context_buffer[-10:])
        inbox_msgs = []
        while True:
            try:
                inbox_msgs.append(self.inbox.get_nowait())
            except asyncio.QueueEmpty:
                break
        inbox = "\n".join(inbox_msgs)
        return (
            f"[INTEROLOG]\n"
            f"id={self.state.id} role={self.state.role} STEP:{self.state.step}\n"
            f"goal: {self.state.goal}\n"
            f"recent_context:\n{ctx_msgs}\n"
            f"inbox:\n{inbox}\n"
        )

    async def _dispatch_actions(self, actions: List[ActionType]):
        from actions import registry as ACTION_HANDLERS
        for act in actions:
            h = ACTION_HANDLERS.get(act.type)
            if h is None:
                continue
            try:
                self.o.current_actor = self
                await h(self, act)
            except Exception as e:
                self.state.last_error = str(e)
            finally:
                self.o.current_actor = None

    async def _sleep(self, seconds: float):
        await asyncio.sleep(seconds)