from __future__ import annotations

import asyncio
import json
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web, WSMsgType

from models.injections import InjectionModel
from models.state import MonologueStateModel


@dataclass
class ChatEntry:
    source: str
    content: str
    timestamp: str


class WebDashboard:
    """Minimal realtime web interface for the orchestrator."""

    def __init__(
        self,
        orchestrator,
        *,
        host: str = "0.0.0.0",
        port: int = 8000,
        refresh: float = 0.5,
        history_limit: int = 200,
    ) -> None:
        self.orch = orchestrator
        self.host = host
        self.port = port
        self.refresh = max(refresh, 0.1)
        self.history_limit = history_limit
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._site: web.BaseSite | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._chat_history: list[ChatEntry] = []
        self._history_lock = asyncio.Lock()
        self._orig_injection: Optional[
            Callable[[InjectionModel, MonologueStateModel], Awaitable[None]]
        ] = None
        self._orig_question: Optional[
            Callable[[str, str, list[str]], Awaitable[None]]
        ] = None
        self._build_routes()

    # ------------------------------------------------------------------
    # Lifecycle
    async def start(self) -> None:
        self._orig_injection = getattr(self.orch, "on_injection", None)
        self.orch.on_injection = self._handle_injection  # type: ignore[assignment]
        self._orig_question = getattr(self.orch, "on_question", None)
        self.orch.on_question = self._handle_question  # type: ignore[assignment]

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def stop(self) -> None:
        if self._snapshot_task:
            self._snapshot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._snapshot_task
            self._snapshot_task = None
        for ws in list(self._clients):
            await ws.close()
        self._clients.clear()
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._orig_injection:
            self.orch.on_injection = self._orig_injection  # type: ignore[assignment]
        if self._orig_question:
            self.orch.on_question = self._orig_question  # type: ignore[assignment]

    # ------------------------------------------------------------------
    def _build_routes(self) -> None:
        self._app.router.add_get("/", self._index)
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/api/chat", self._chat_api)
        self._app.router.add_get("/api/snapshot", self._snapshot_api)
        self._app.router.add_get("/api/monologue/{mono_id}", self._monologue_detail)
        self._app.router.add_post("/api/message", self._post_message)

    # ------------------------------------------------------------------
    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(text=self._render_index(), content_type="text/html")

    async def _websocket_handler(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        try:
            await ws.send_json({"type": "snapshot", "payload": self.orch.snapshot()})
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "user_message":
                        content = (data.get("content") or "").strip()
                        reply_to = data.get("reply_to") or None
                        if content:
                            await self._handle_user_message(content, reply_to)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._clients.discard(ws)
            await ws.close()
        return ws

    async def _chat_api(self, request: web.Request) -> web.Response:
        async with self._history_lock:
            payload = [entry.__dict__ for entry in self._chat_history]
        return web.json_response({"entries": payload})

    async def _snapshot_api(self, request: web.Request) -> web.Response:
        return web.json_response(self.orch.snapshot())

    async def _monologue_detail(self, request: web.Request) -> web.Response:
        mono_id = request.match_info.get("mono_id")
        actor = self.orch._actors.get(mono_id)  # type: ignore[attr-defined]
        if not actor:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "unknown id"}),
                content_type="application/json",
            )
        state = actor.state
        payload = {
            "id": state.id,
            "role": state.role,
            "goal": state.goal,
            "step": state.step,
            "running": state.running,
            "last_action": state.last_action,
            "last_error": state.last_error,
            "tool_calls": state.tool_calls,
            "parent_id": state.parent_id,
            "children": list(actor.children),
            "recent_context": actor.context_buffer[-20:],
            "inbox_size": actor.inbox.qsize(),
            "memory_recent": [
                entry.as_dict() for entry in actor.memory.recent(limit=20)
            ],
            "memory_graph": actor.memory.graph_summary(limit=10),
        }
        return web.json_response(payload)

    async def _post_message(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            raise web.HTTPBadRequest(text="invalid json")
        content = (data.get("content") or "").strip()
        reply_to = data.get("reply_to") or None
        if not content:
            raise web.HTTPBadRequest(text="missing content")
        await self._handle_user_message(content, reply_to)
        return web.json_response({"status": "ok"})

    # ------------------------------------------------------------------
    async def _handle_injection(
        self, inj: InjectionModel, state: MonologueStateModel
    ) -> None:
        await self._record_chat(state.role or inj.from_id, inj.content)
        if self._orig_injection:
            await self._orig_injection(inj, state)

    async def _handle_question(
        self, correlation_id: str, question: str, choices: list[str]
    ) -> None:
        entry = f"[QUESTION {correlation_id}] {question} choices={choices or []}"
        await self._record_chat("question", entry)
        await self._broadcast(
            {
                "type": "question",
                "payload": {
                    "id": correlation_id,
                    "question": question,
                    "choices": choices or [],
                },
            }
        )
        if self._orig_question:
            await self._orig_question(correlation_id, question, choices)

    async def _handle_user_message(self, content: str, reply_to: str | None) -> None:
        if reply_to:
            await self.orch.on_user_message(content, reply_to)
            label = f"user->reply:{reply_to}"
        else:
            comms = getattr(self.orch, "comms", None)
            if comms:
                await self.orch.comms_send(content)
            else:
                await self.orch.on_user_message(content, None)
            label = "user"
        await self._record_chat(label, content)

    async def _record_chat(self, source: str, content: str) -> None:
        iso_ts = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        entry = ChatEntry(source=source, content=content, timestamp=iso_ts)
        async with self._history_lock:
            self._chat_history.append(entry)
            if len(self._chat_history) > self.history_limit:
                self._chat_history = self._chat_history[-self.history_limit :]
        await self._broadcast({"type": "chat", "payload": entry.__dict__})

    async def _snapshot_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.refresh)
                await self._broadcast(
                    {"type": "snapshot", "payload": self.orch.snapshot()}
                )
        except asyncio.CancelledError:
            pass

    async def _broadcast(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        data = json.dumps(message)
        stale: list[web.WebSocketResponse] = []
        for ws in list(self._clients):
            if ws.closed:
                stale.append(ws)
                continue
            try:
                await ws.send_str(data)
            except ConnectionResetError:
                stale.append(ws)
            except RuntimeError:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)

    # ------------------------------------------------------------------
    def _render_index(self) -> str:
        return """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<title>Interolog Web UI</title>
<style>
body { margin:0; font-family: 'Inter', system-ui, -apple-system, sans-serif; background:#0e1011; color:#f3f4f6; display:flex; height:100vh; }
#left { flex:2; display:flex; flex-direction:column; padding:1.5rem; gap:1rem; border-right:1px solid #1f2937; }
#right { width:32%; max-width:420px; padding:1.5rem; background:#111827; overflow-y:auto; }
#chat-log { flex:1; background:#111827; border:1px solid #1f2937; border-radius:12px; padding:1rem; overflow-y:auto; }
.chat-entry { margin-bottom:0.75rem; }
.chat-entry .meta { font-size:0.75rem; color:#9ca3af; }
.chat-entry .content { margin-top:0.25rem; white-space:pre-wrap; word-break:break-word; }
form { display:flex; gap:0.75rem; }
input[type=text] { flex:1; padding:0.75rem; border-radius:10px; border:1px solid #374151; background:#0f172a; color:#f9fafb; }
button { padding:0.75rem 1.25rem; border-radius:10px; border:none; background:#3b82f6; color:white; font-weight:600; cursor:pointer; }
button:hover { background:#2563eb; }
#monologues { display:flex; flex-direction:column; gap:0.75rem; }
.monologue { padding:0.75rem 1rem; border-radius:10px; border:1px solid #1f2937; background:#0f172a; cursor:pointer; transition:transform 0.1s ease, border 0.2s ease; }
.monologue:hover { transform:translateY(-2px); border-color:#3b82f6; }
.monologue.running { border-color:#10b981; }
.monologue .id { font-size:0.75rem; color:#9ca3af; }
.monologue .role { font-weight:600; }
#modal { position:fixed; inset:0; background:rgba(15, 23, 42, 0.8); display:none; align-items:center; justify-content:center; padding:2rem; }
#modal.active { display:flex; }
#modal .card { background:#0f172a; border-radius:12px; padding:1.5rem; width: min(720px, 90%); max-height:80vh; overflow-y:auto; border:1px solid #1f2937; }
#modal .card h3 { margin-top:0; }
#modalClose { background:transparent; border:none; color:#9ca3af; font-size:0.9rem; cursor:pointer; float:right; }
#modal pre { background:#111827; padding:0.75rem; border-radius:8px; border:1px solid #1f2937; max-height:220px; overflow:auto; }
.question-bar { display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.5rem; }
.question-card { background:#1f2937; padding:0.75rem; border-radius:8px; border:1px solid #374151; }
.question-card h4 { margin:0 0 0.5rem 0; }
.question-card button { background:#10b981; }
@media (max-width: 960px) {
  body { flex-direction:column; }
  #left, #right { width:100%; max-width:none; }
  #right { border-top:1px solid #1f2937; border-left:none; }
}
</style>
</head>
<body>
<div id=\"left\">
  <div style=\"display:flex; justify-content:space-between; align-items:center;\">
    <h1 style=\"margin:0; font-size:1.5rem;\">Interolog Chat</h1>
    <span id=\"status\" style=\"font-size:0.85rem; color:#9ca3af;\">connecting...</span>
  </div>
  <div id=\"chat-log\"></div>
  <div id=\"questions\"></div>
  <form id=\"input-form\">
    <input id=\"message\" type=\"text\" autocomplete=\"off\" placeholder=\"Type a message to the agents...\" />
    <button type=\"submit\">Send</button>
  </form>
</div>
<div id=\"right\">
  <h2 style=\"margin-top:0;\">Monologues</h2>
  <div id=\"monologues\"></div>
</div>
<div id=\"modal\">
  <div class=\"card\">
    <button id=\"modalClose\">Close</button>
    <h3 id=\"modalTitle\"></h3>
    <div id=\"modalBody\"></div>
  </div>
</div>
<script>
const chatLog = document.getElementById('chat-log');
const statusEl = document.getElementById('status');
const monologueList = document.getElementById('monologues');
const inputForm = document.getElementById('input-form');
const messageInput = document.getElementById('message');
const modal = document.getElementById('modal');
const modalTitle = document.getElementById('modalTitle');
const modalBody = document.getElementById('modalBody');
const modalClose = document.getElementById('modalClose');
const questions = document.getElementById('questions');
let modalInterval = null;
let activeModalId = null;

function appendChat(entry) {
  const wrapper = document.createElement('div');
  wrapper.className = 'chat-entry';
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = `[${entry.timestamp}] ${entry.source}`;
  const content = document.createElement('div');
  content.className = 'content';
  content.textContent = entry.content;
  wrapper.appendChild(meta);
  wrapper.appendChild(content);
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderMonologues(snapshot) {
  monologueList.innerHTML = '';
  (snapshot.actors || []).forEach(actor => {
    const item = document.createElement('div');
    item.className = 'monologue' + (actor.running ? ' running' : '');
    item.innerHTML = `<div class=\"role\">${actor.role} <span class=\"id\">(${actor.id})</span></div>` +
      `<div style=\"font-size:0.8rem; color:#9ca3af; margin-top:0.25rem;\">step ${actor.step} · inbox ${actor.inbox_size} · last ${actor.last_action || 'n/a'}</div>`;
    item.addEventListener('click', () => openModal(actor.id, actor.role));
    monologueList.appendChild(item);
  });
}

async function openModal(id, role) {
  activeModalId = id;
  modalTitle.textContent = `${role} (${id})`;
  await loadModalContent();
  modal.classList.add('active');
  modalInterval = setInterval(loadModalContent, 1000);
}

async function loadModalContent() {
  if (!activeModalId) return;
  try {
    const res = await fetch(`/api/monologue/${activeModalId}`);
    if (!res.ok) {
      modalBody.innerHTML = '<p>Monologue ended.</p>';
      return;
    }
    const data = await res.json();
    modalBody.innerHTML = `
      <p><strong>Goal:</strong> ${data.goal || '—'}</p>
      <p><strong>Status:</strong> ${data.running ? 'running' : 'stopped'} · step ${data.step} · tool calls ${data.tool_calls}</p>
      <p><strong>Last action:</strong> ${data.last_action || '—'}</p>
      <p><strong>Error:</strong> ${data.last_error || '—'}</p>
      <p><strong>Parent:</strong> ${data.parent_id || '—'}</p>
      <p><strong>Children:</strong> ${(data.children || []).join(', ') || '—'}</p>
      <p><strong>Inbox size:</strong> ${data.inbox_size}</p>
      <p><strong>Recent context:</strong></p>
      <pre>${(data.recent_context || []).join('\n')}</pre>
    `;
  } catch (err) {
    modalBody.innerHTML = '<p>Unable to load.</p>';
  }
}

function closeModal() {
  modal.classList.remove('active');
  modalBody.innerHTML = '';
  modalTitle.textContent = '';
  activeModalId = null;
  if (modalInterval) {
    clearInterval(modalInterval);
    modalInterval = null;
  }
}

modalClose.addEventListener('click', closeModal);
modal.addEventListener('click', (ev) => { if (ev.target === modal) closeModal(); });

function renderQuestion(payload) {
  const card = document.createElement('div');
  card.className = 'question-card';
  card.dataset.qid = payload.id;
  card.innerHTML = `<h4>${payload.question}</h4>`;
  const actions = document.createElement('div');
  actions.className = 'question-bar';
  if ((payload.choices || []).length) {
    payload.choices.forEach(choice => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = choice;
      btn.addEventListener('click', () => submitReply(payload.id, choice));
      actions.appendChild(btn);
    });
  }
  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'Custom reply';
  input.style.flex = '1';
  const submit = document.createElement('button');
  submit.type = 'button';
  submit.textContent = 'Send';
  submit.addEventListener('click', () => submitReply(payload.id, input.value));
  actions.appendChild(input);
  actions.appendChild(submit);
  card.appendChild(actions);
  questions.appendChild(card);
}

async function submitReply(id, content) {
  const value = (content || '').trim();
  if (!value) return;
  await fetch('/api/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: value, reply_to: id })
  });
  const card = document.querySelector(`.question-card[data-qid=\"${id}\"]`);
  if (card) {
    card.remove();
  }
}

inputForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const value = messageInput.value.trim();
  if (!value) return;
  await fetch('/api/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: value })
  });
  messageInput.value = '';
});

async function bootstrap() {
  const chatRes = await fetch('/api/chat');
  const history = await chatRes.json();
  history.entries.forEach(appendChat);
  const snapRes = await fetch('/api/snapshot');
  const snapshot = await snapRes.json();
  renderMonologues(snapshot);
}

function setupSocket() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.addEventListener('open', () => {
    statusEl.textContent = 'connected';
  });
  ws.addEventListener('close', () => {
    statusEl.textContent = 'disconnected';
    setTimeout(setupSocket, 2000);
  });
  ws.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'chat') {
        appendChat(data.payload);
      } else if (data.type === 'snapshot') {
        renderMonologues(data.payload);
      } else if (data.type === 'question') {
        renderQuestion(data.payload);
      }
    } catch (err) {
      console.error('bad message', err);
    }
  });
}

bootstrap();
setupSocket();
</script>
</body>
</html>"""
