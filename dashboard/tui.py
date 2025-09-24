from __future__ import annotations

import asyncio
import shutil
import sys
from .state import DashboardState
from .events import pump_events

CLEAR = "\x1b[2J\x1b[H"


def fmt_row(cols, widths):
    out = []
    for c, w in zip(cols, widths):
        s = (c if c is not None else "")[:w].ljust(w)
        out.append(s)
    return " ".join(out)


async def input_loop(orchestrator, dbstate: DashboardState):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            await asyncio.sleep(0.1)
            continue
        msg = line.decode(errors="replace").strip()
        if not msg:
            continue
        if msg.startswith("/"):
            if msg == "/quit":
                raise KeyboardInterrupt
            elif msg.startswith("/kill "):
                _, aid = msg.split(" ", 1)
                await orchestrator.stop_child(aid.strip())
                dbstate.add_chat(f"[sys] requested stop {aid}")
            else:
                dbstate.add_chat(f"[sys] unknown command: {msg}")
        else:
            if msg.startswith("@"):
                try:
                    cid, content = msg[1:].split(" ", 1)
                except ValueError:
                    dbstate.add_chat("[sys] usage: @<cid> <reply>")
                    continue
                dbstate.add_chat(f"[you->{cid}] {content}")
                await orchestrator.on_user_message(content, cid)
            else:
                dbstate.add_chat(f"[you] {msg}")
                await orchestrator.on_user_message(msg)


async def draw_loop(orchestrator, dbstate: DashboardState, refresh: float = 0.5):
    while True:
        cols = shutil.get_terminal_size((120, 40)).columns
        print(CLEAR, end="")
        print("Interolog Dashboard — Ctrl+C to exit".ljust(cols))
        print("-" * cols)
        headers = ["id", "role", "step", "run", "inbox", "tools", "last_action", "err"]
        widths = [8, 12, 4, 3, 5, 5, 28, 28]
        print(fmt_row(headers, widths))
        print("-" * cols)
        for a in dbstate.actors[:20]:
            row = [
                a.get("id", ""),
                a.get("role", ""),
                str(a.get("step", 0)),
                "Y" if a.get("running") else "N",
                str(a.get("inbox_size", 0)),
                str(a.get("tool_calls", 0)),
                a.get("last_action", "")[:28],
                a.get("last_error", "")[:28],
            ]
            print(fmt_row(row, widths))
        print("-" * cols)
        print("Events:")
        for e in dbstate.events[-10:]:
            et = e.get("type", "evt")
            s = e.get("summary", "") or str(e)
            print(f" - [{et}] {s}"[:cols])
        print("-" * cols)
        print("Chat: (type to send, @cid <msg> to reply, /kill <id>, /quit)")
        for line in dbstate.chat[-5:]:
            print(f" {line}"[:cols])
        sys.stdout.flush()
        await asyncio.sleep(refresh)


async def run_tui(orchestrator, refresh: float = 0.5):
    dbstate = DashboardState()

    async def question_handler(cid, question, choices):
        dbstate.add_chat(f"[ask {cid}] {question} choices={choices}")

    orchestrator.on_question = question_handler

    tasks = [
        asyncio.create_task(draw_loop(orchestrator, dbstate, refresh)),
        asyncio.create_task(input_loop(orchestrator, dbstate)),
        asyncio.create_task(pump_events(orchestrator, dbstate, refresh)),
    ]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        for t in tasks:
            t.cancel()
