
# Interolog (Production)

Internal monologue orchestrator with:
- Pydantic-typed actions with centralized handler registry (`action_registry.py`)
- Tool registry (files, shell, HTTP) auto-discovered at runtime and surfaced directly in actor prompts
- Rich actor telemetry with functional memory (vector + graph recall), last action, tool usage, errors, and live dashboards (terminal TUI or two-column web UI)
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

When the web UI is enabled, open `http://localhost:<port>` to see a two-column view: the left panel streams chat between you and the main monologue, and the right panel lists every running monologue. Clicking an entry opens a modal that refreshes in real time with its goal, recent actions, context buffer, and the semantic memory graph powering retrieval.

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
- `FUNCTIONAL_MEMORY_MAX` (entries to retain) and `FUNCTIONAL_MEMORY_DECAY` (seconds before recall scores decay)
- `MAX_SUB_STEPS`, `MAX_CHILDREN`, `CYCLE_DELAY`, `COMMS_*` for orchestration tuning

Tools are optional: if a dependency such as `aiohttp` is missing the corresponding tool will raise a helpful runtime error instead of blocking startup.

## Tooling

All tools are auto-discovered from the `tools/` package and described to every monologue inside its working prompt. You can also
use the new `tool.list` and `tool.info` utilities to introspect capabilities at runtime.

- `tool.list` / `tool.info(tool_name=...)` &mdash; enumerate tools and fetch per-tool descriptions or schemas.
- `file.read` / `file.write` / `file.append` / `file.delete` &mdash; basic text file utilities gated by an env-driven allowlist.
- `fs.list` / `fs.stat` &mdash; inspect directory contents and metadata with recursion, filters, and allowlist enforcement.
- `shell.run` &mdash; execute allowlisted shell commands via `/bin/sh -c` and capture stdout/stderr.
- `python.exec` &mdash; run Python snippets in a subprocess with timeout control.
- `http_request` &mdash; perform HTTP(S) requests, fetch headers, or download raw source with optional custom headers and payloads.

## Functional memory

Every monologue maintains a hybrid memory that blends vector similarity with a lightweight semantic graph. Memories are inserted whenever actors handle inbox messages, tool calls, injections, or errors. Retrieval uses cosine similarity over deterministic bag-of-words vectors combined with graph proximity—no external AI embedding services are required.

Runtime tuning knobs:

- `FUNCTIONAL_MEMORY_MAX` caps the number of stored entries per actor (default 200).
- `FUNCTIONAL_MEMORY_DECAY` controls how quickly old memories lose recall weight (default 600 seconds).

The dashboard exposes both the latest memory entries and aggregated graph edges to help operators understand why the orchestrator recalls specific facts.

## Development

The test suite relies on `async def` coroutines. A lightweight `conftest.py` plugin is included so the suite runs without third-party pytest extensions. To exercise the checks locally:

```bash
# Basic syntax/lint gate
python -m py_compile $(git ls-files '*.py')

# Run the async-enabled tests
pytest
```
