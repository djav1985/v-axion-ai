
# Interolog (Production)

Internal monologue orchestrator with:
- Pydantic-typed actions with centralized handler registry (`action_registry.py`)
- Tool registry (files, shell, HTTP) auto-discovered at runtime and surfaced directly in actor prompts
- Rich actor telemetry (context buffer, last action, tool usage, errors) and live dashboards (terminal TUI or two-column web UI)
- Graceful shutdown semantics for clean embedding in other services
- Env-driven configuration and CLI overrides for choosing LLM provider/model (local Gemma or OpenAI)

## Quickstart

```bash
pip install -r requirements.txt

# Example: run with local Gemma (default TUI dashboard)
python main.py "Coordinate subs to research and report"

# Example: start the web dashboard on port 8080
python main.py --ui web --web-port 8080 "Coordinate subs to research and report"

# Example: target OpenAI
OPENAI_API_KEY=sk-... python main.py --provider openai --model gpt-4o-mini --ui web "Coordinate subs to research and report"
```

When the web UI is enabled, open `http://localhost:<port>` to see a two-column view: the left panel streams chat between you and the main monologue, and the right panel lists every running monologue. Clicking an entry opens a modal that refreshes in real time with its goal, recent actions, and context buffer.

If you prefer the terminal dashboard, use the terminal to type messages to the Comms monologue. Commands:
- `/kill <actor_id>` stop a worker
- `/quit` exit the dashboard

Configuration options can be supplied via environment variables or flags:
- `INTEROLOG_PROVIDER` / `--provider`
- `INTEROLOG_MODEL` / `--model`
- `INTEROLOG_UI` / `--ui` (`tui`, `web`, or `none`)
- `INTEROLOG_WEB_HOST` / `--web-host`
- `INTEROLOG_WEB_PORT` / `--web-port`
- `DASH_REFRESH` / `--ui-refresh`
- `MAX_SUB_STEPS`, `MAX_CHILDREN`, `CYCLE_DELAY`, `COMMS_*` for orchestration tuning

Tools are optional: if a dependency such as `aiohttp` is missing the corresponding tool will raise a helpful runtime error instead of blocking startup.

## Development

The test suite relies on `async def` coroutines. A lightweight `conftest.py` plugin is included so the suite runs without third-party pytest extensions. To exercise the checks locally:

```bash
# Basic syntax/lint gate
python -m py_compile $(git ls-files '*.py')

# Run the async-enabled tests
pytest
```
