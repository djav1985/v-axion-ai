
from __future__ import annotations
from pydantic import BaseModel, Field
import time

class InjectionModel(BaseModel):
    from_id: str
    content: str
    ts: float = Field(default_factory=time.time)
