from __future__ import annotations

import asyncio
import os

from .base import LLM


class OpenAIChat(LLM):
    """OpenAI chat completions provider using the async SDK.

    Env:
      OPENAI_API_KEY (required)
      OPENAI_MODEL (default: gpt-4o-mini)
      OPENAI_TIMEOUT (default: 30 seconds)
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = float(timeout or os.getenv("OPENAI_TIMEOUT", 30))
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "openai package not installed. `pip install openai`"
            ) from e

        self.client = AsyncOpenAI(api_key=self.api_key)

    async def acomplete(
        self, prompt: str, *, system: str = "", max_tokens: int = 400
    ) -> str:
        from openai import APIConnectionError, RateLimitError  # type: ignore

        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.2,
                ),
                timeout=self.timeout,
            )
            msg = resp.choices[0].message.content or "{}"
            return msg
        except (APIConnectionError, RateLimitError) as e:
            # Bubble up as runtime error; orchestrator runtime logging will record it
            raise RuntimeError(f"OpenAI error: {e}") from e
