
# Interolog (Production)

Internal monologue orchestrator with:
- Pydantic-typed actions with centralized handler registry (`action_registry.py`)
- Tool registry (files, shell, HTTP) auto-discovered at runtime and surfaced directly in actor prompts
- Rich actor telemetry (context buffer, last action, tool usage, errors) and live terminal dashboard (actors table, event feed, chat)
- Graceful shutdown semantics for clean embedding in other services
- Env-driven configuration and CLI overrides for choosing LLM provider/model (local Gemma or OpenAI)

## Quickstart

```bash
pip install -r requirements.txt

# Example: run with local Gemma (default)
python main.py "Coordinate subs to research and report"

# Example: target OpenAI
OPENAI_API_KEY=sk-... python main.py --provider openai --model gpt-4o-mini "Coordinate subs to research and report"
```

Use the terminal to type messages to the Comms monologue. Commands:
- `/kill <actor_id>` stop a worker
- `/quit` exit the dashboard

Configuration options can be supplied via environment variables or flags:
- `INTEROLOG_PROVIDER` / `--provider`
- `INTEROLOG_MODEL` / `--model`
- `MAX_SUB_STEPS`, `MAX_CHILDREN`, `CYCLE_DELAY`, `COMMS_*` for orchestration tuning

Tools are optional: if a dependency such as `aiohttp` is missing the corresponding tool will raise a helpful runtime error instead of blocking startup.
