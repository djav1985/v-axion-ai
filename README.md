
# Interolog (Production)

Internal monologue orchestrator with:
- Pydantic-typed actions with centralized handler registry (`action_registry.py`)
- Tool registry (files, shell) with dry-run defaults
- Live terminal dashboard (actors table, event feed, chat)
- Telemetry queue + JSONL logging
- Env-driven config
- OpenAI async provider

## Quickstart

```bash
cd interolog_production
cp .env.example .env
# set OPENAI_API_KEY in .env
python main.py "Coordinate subs to research and report"
```

Use the terminal to type messages to the Comms monologue. Commands:
- `/kill <actor_id>` stop a worker
- `/quit` exit the dashboard

Configure via `.env`. See `.env.example` for all keys.
