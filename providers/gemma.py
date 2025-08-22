# v-axion-ai/providers/gemma.py
# Purpose: Local Gemma provider using HuggingFace Transformers; singleton per model.
from __future__ import annotations
from typing import Optional, Any
import asyncio
import threading
from dataclasses import dataclass

# Lazy imports to avoid heavy startup
def _lazy_imports():
    global AutoModelForCausalLM, AutoTokenizer, pipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline  # type: ignore

_singletons = {}
_singletons_lock = threading.Lock()

@dataclass
class _Runner:
    pipe: Any

class LocalGemma:
    """Singleton-backed local Gemma provider.
    Downloads model on first use into HF cache. Subsequent runs reuse it.
    """
    model_id: str
    runner: _Runner

    def __init__(self, model_id: str, runner: _Runner):
        self.model_id = model_id
        self.runner = runner

    @classmethod
    def get(cls, model_id: str = "google/gemma-3-270m") -> "LocalGemma":
        with _singletons_lock:
            if model_id in _singletons:
                return _singletons[model_id]
            _lazy_imports()
            tok = AutoTokenizer.from_pretrained(model_id)
            mdl = AutoModelForCausalLM.from_pretrained(model_id)
            pipe = pipeline("text-generation", model=mdl, tokenizer=tok)
            inst = cls(model_id, _Runner(pipe=pipe))
            _singletons[model_id] = inst
            return inst

    async def acomplete(self, prompt: str, *, system: str = "", max_tokens: int = 512) -> str:
        """Return model text output given a prompt and optional system message.

        Offloads the blocking pipeline call to a thread to avoid blocking the
        event loop.
        """
        system_text = f"{system.strip()}\n" if system else ""
        text = system_text + f"user: {prompt}"
        out = await asyncio.to_thread(
            self.runner.pipe, text, max_new_tokens=max_tokens, do_sample=False
        )
        return out[0]["generated_text"]
