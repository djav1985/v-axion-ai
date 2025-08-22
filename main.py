
from __future__ import annotations
import argparse, asyncio, os, sys

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

async def run(goal: str, dash: bool):
    llm = get_provider("hf_gemma")
    orch = Orchestrator(llm, on_injection=printer)
    await orch.start(main_goal=goal, with_comms=True)
    if dash and os.getenv("DASH_ENABLED","true").lower() == "true":
        from dashboard.tui import run_tui
        await run_tui(orch, refresh=float(os.getenv("DASH_REFRESH","0.5")))
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
    await orch.shutdown()

def main():
    p = argparse.ArgumentParser(description="Interolog Orchestrator (OpenAI provider)")
    p.add_argument("goal", help="Initial main-goal prompt.")
    p.add_argument("--no-dash", action="store_true", help="Run headless (no TUI).")
    args = p.parse_args()
    asyncio.run(run(args.goal, dash=not args.no_dash))

if __name__ == "__main__":
    main()
