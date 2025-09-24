from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from interolog import Orchestrator
from providers import get_provider
from models.injections import InjectionModel
from models.state import MonologueStateModel


async def printer(inj: InjectionModel, main_state: MonologueStateModel):
    print(f"[MAIN<-{inj.from_id}] {inj.content}", flush=True)


async def run(
    goal: str,
    ui: str,
    provider: str,
    model_id: str | None,
    *,
    refresh: float,
    web_host: str,
    web_port: int,
):
    llm = get_provider(provider, model_id=model_id)
    orch = Orchestrator(llm, on_injection=printer)

    async def cli_question(cid: str, question: str, choices: list[str]):
        print(f"[QUESTION {cid}] {question} choices={choices}")
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, lambda: input("> "))
        await orch.on_user_message(reply, cid)

    orch.on_question = cli_question

    web_dash = None
    stdin_task: asyncio.Task[None] | None = None
    try:
        await orch.start(main_goal=goal, with_comms=True)
        if ui == "web" and os.getenv("DASH_ENABLED", "true").lower() == "true":
            from dashboard.web import WebDashboard

            web_dash = WebDashboard(
                orch,
                host=web_host,
                port=web_port,
                refresh=refresh,
            )
            await web_dash.start()
            stopper = asyncio.Event()
            try:
                await stopper.wait()
            except asyncio.CancelledError:
                pass
        elif ui == "tui" and os.getenv("DASH_ENABLED", "true").lower() == "true":
            from dashboard.tui import run_tui

            await run_tui(orch, refresh=refresh)
        else:

            async def forward_stdin():
                loop = asyncio.get_running_loop()
                while True:
                    line = await loop.run_in_executor(None, sys.stdin.readline)
                    if not line:
                        continue
                    line = line.rstrip("\n")
                    if line.strip() == "/quit":
                        break
                    await orch.comms_send(line)

            stdin_task = asyncio.create_task(forward_stdin())
            await stdin_task
    except asyncio.CancelledError:
        pass
    finally:
        if stdin_task:
            stdin_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stdin_task
        if web_dash:
            await web_dash.stop()
        await orch.shutdown()


def main():
    default_provider = os.getenv("INTEROLOG_PROVIDER", "hf_gemma")
    default_model = os.getenv("INTEROLOG_MODEL")
    default_ui = os.getenv("INTEROLOG_UI", "tui")
    default_refresh = float(os.getenv("DASH_REFRESH", "0.5"))
    default_host = os.getenv("INTEROLOG_WEB_HOST", "0.0.0.0")
    default_port = int(os.getenv("INTEROLOG_WEB_PORT", "8000"))
    p = argparse.ArgumentParser(description="Interolog Orchestrator")
    p.add_argument("goal", help="Initial main-goal prompt.")
    p.add_argument("--no-dash", action="store_true", help="Run headless (no dashboard).")
    p.add_argument(
        "--provider",
        default=default_provider,
        help="LLM provider to use (e.g., hf_gemma, openai).",
    )
    p.add_argument(
        "--model",
        default=default_model,
        help="Override model identifier for the selected provider.",
    )
    p.add_argument(
        "--ui",
        choices=["tui", "web", "none"],
        default=default_ui,
        help="Dashboard mode to launch (tui, web, none).",
    )
    p.add_argument(
        "--ui-refresh",
        type=float,
        default=default_refresh,
        help="Refresh interval for dashboards (seconds).",
    )
    p.add_argument(
        "--web-host",
        default=default_host,
        help="Host interface for the web UI.",
    )
    p.add_argument(
        "--web-port",
        type=int,
        default=default_port,
        help="Port for the web UI.",
    )
    args = p.parse_args()
    ui_mode = args.ui
    if args.no_dash:
        ui_mode = "none"
    asyncio.run(
        run(
            args.goal,
            ui=ui_mode,
            provider=args.provider,
            model_id=args.model,
            refresh=args.ui_refresh,
            web_host=args.web_host,
            web_port=args.web_port,
        )
    )


if __name__ == "__main__":
    main()
