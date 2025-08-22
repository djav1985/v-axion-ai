# v-axion-ai/providers/__init__.py
# Purpose: Provider factory for LLM backends (local Gemma, OpenAI).
from __future__ import annotations
from typing import Any, Optional
from .openai import OpenAIChat
try:
    from .gemma import LocalGemma
except Exception:
    LocalGemma = None  # optional import

def get_provider(name: str, *, model_id: Optional[str]=None) -> Any:
    name = (name or "").lower()
    if name in ("hf_gemma","gemma","local_gemma"):
        if LocalGemma is None:
            raise RuntimeError("LocalGemma provider not available")
        return LocalGemma.get(model_id or "google/gemma-3-270m")
    if name == "openai":
        return OpenAIChat(model=model_id)
    raise ValueError(f"Unknown provider: {name}")
