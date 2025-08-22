
from __future__ import annotations
import abc

class LLM(abc.ABC):
    @abc.abstractmethod
    async def acomplete(self, prompt: str, *, system: str = "", max_tokens: int = 400) -> str:
        """Return model text output (expected to be JSON per control protocol)."""
        raise NotImplementedError
