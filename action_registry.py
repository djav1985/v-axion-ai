
# v-axion-ai/action_registry.py
# Purpose: Role-scoped action exposure with model options in Open Monologue docs.

from __future__ import annotations
import os
from typing import List, Dict, Any
from models.actions import ACTION_DEFS

def _available_models() -> List[Dict[str, Any]]:
    models = [{"provider":"hf_gemma","id":"google/gemma-3-270m","local":True}]
    if os.getenv("OPENAI_API_KEY"):
        models += [
            {"provider":"openai","id":"gpt-4o-mini","local":False},
            {"provider":"openai","id":"gpt-4o","local":False},
            {"provider":"openai","id":"gpt-4.1-mini","local":False},
        ]
    extra = os.getenv("AVAILABLE_MODELS", "").strip()
    if extra:
        for tok in [t for t in extra.split(",") if "/" in t]:
            p, mid = tok.split("/", 1)
            models.append({"provider": p.strip(), "id": mid.strip(), "local": (p.strip()=="hf_gemma")})
    return models

ROLE_ACTIONS = {
    "main": ["open_monologue", "ask_user", "sleep", "message_monologue", "list_monologue", "kill_monologue"],
    "sub":  ["sleep", "message_monologue", "kill_monologue"],
    "comms": [],
}

def get_actions_for(role: str) -> List[Dict[str, Any]]:
    role = (role or "").lower()
    allowed = ROLE_ACTIONS.get(role, ROLE_ACTIONS["sub"])
    avail = _available_models()
    out: List[Dict[str, Any]] = []
    for name in allowed:
        meta = ACTION_DEFS[name]
        Model = meta["model"]
        desc = meta["description"]
        if name == "open_monologue":
            desc += " Available models: " + ", ".join(f"{m['provider']}/{m['id']}" for m in avail) + "."
        out.append({"action": name, "description": desc, "schema": Model.model_json_schema()})
    return out
