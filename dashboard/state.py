
from __future__ import annotations
from typing import List, Dict, Any

class DashboardState:
    def __init__(self):
        self.actors: List[Dict[str,Any]] = []
        self.events: List[Dict[str,Any]] = []
        self.chat: List[str] = []

    def set_snapshot(self, actors: List[Dict[str,Any]]):
        self.actors = actors

    def add_event(self, e: Dict[str,Any], max_events: int = 500):
        self.events.append(e)
        if len(self.events) > max_events:
            self.events.pop(0)

    def add_chat(self, line: str, max_lines: int = 200):
        self.chat.append(line)
        if len(self.chat) > max_lines:
            self.chat.pop(0)
