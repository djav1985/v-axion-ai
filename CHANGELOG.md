# Changelog

## Unreleased

- Prevent duplicate actor task scheduling and add graceful orchestrator shutdown that awaits all running tasks.
- Track last action, tool usage, inbox state, and errors on each monologue while persisting a rolling context buffer.
- Surface discovered tool and action metadata directly in actor prompts.
- Make HTTP tool imports lazy so optional dependencies no longer block startup and harden shell/file tool allowlists with real-path checks.
- Expose `--provider`/`--model` CLI flags (and matching env vars) for selecting Gemma or OpenAI backends at runtime.
- Expand async test coverage to include early-wake sleeps, message routing, and action/metadata handling.
- Ship a real-time web dashboard with chat, live monologue list, and modal inspector alongside new UI CLI/env configuration options.
- Add a lightweight pytest hook so coroutine-based tests run without external plugins.
- Introduce functional memory for every actor: vector-based recall, semantic graphs, dashboard introspection, and dedicated unit tests.
- Extend the built-in tool catalog with meta-inspection (`tool.list`/`tool.info`), filesystem exploration (`fs.list`/`fs.stat`),
  and a Python subprocess executor (`python.exec`).
- Rework tooling so each drop-in file under `tools/` exports `TOOL = ToolSpec(...)`, enabling automatic registration without
  manual wiring while keeping helper modules opt-in.
