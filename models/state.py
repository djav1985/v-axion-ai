
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
import time

class MonologueStateModel(BaseModel):
    id: str
    role: str
    goal: str
    parent_id: Optional[str] = None
    step: int = 0
    running: bool = True
    created: float = Field(default_factory=time.time)
    last_action: str = ""
    inbox_size: int = 0
    tool_calls: int = 0
    last_error: str = ""
