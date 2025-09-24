# Changelog

## Unreleased

- Prevent duplicate actor task scheduling and add graceful orchestrator shutdown that awaits all running tasks.
- Track last action, tool usage, inbox state, and errors on each monologue while persisting a rolling context buffer.
- Surface discovered tool and action metadata directly in actor prompts.
- Make HTTP tool imports lazy so optional dependencies no longer block startup and harden shell/file tool allowlists with real-path checks.
- Expose `--provider`/`--model` CLI flags (and matching env vars) for selecting Gemma or OpenAI backends at runtime.
- Expand async test coverage to include early-wake sleeps, message routing, and action/metadata handling.
