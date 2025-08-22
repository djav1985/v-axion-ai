
# v-axion-ai/models/actions.py
# Purpose: Pydantic action schemas and registry metadata for the agent runtime.

from __future__ import annotations
from typing import Optional, List, Dict, Any, Annotated
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ValidationError, TypeAdapter

class OpenMonologue(BaseModel):
    """Open a new sub-monologue. Defaults to local Gemma; OpenAI optional if key present."""
    role: str = Field(default="Worker", min_length=1)
    goal: str = Field(default="Do the next useful thing.", min_length=1)
    provider: Optional[str] = Field(default=None, description="hf_gemma | openai")
    model_id: Optional[str] = Field(default=None, description="e.g., google/gemma-3-270m or gpt-4o-mini")
    system_prompt: Optional[str] = Field(default=None, description="Optional system prompt for the child")

class AskUser(BaseModel):
    """Main asks the human via the Communication monologue; reply routed back to Main."""
    question: str = Field(min_length=1)
    choices: Optional[List[str]] = None
    correlation_id: Optional[str] = None

class Sleep(BaseModel):
    """Pause execution; wakes early if a message arrives for the target."""
    seconds: float = Field(ge=0, description="duration in seconds")
    target_id: Optional[str] = Field(default=None, description="main may specify sub id; subs must omit (self only)")

class MessageMonologue(BaseModel):
    """Send a message to another monologue; can wait for reply or fire-and-forget.
    Replies should include 'reply_to' set to the request_id.
    """
    request_id: Optional[str] = None
    from_id: Optional[str] = None
    to_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    wait_for_reply: bool = True

class ListMonologue(BaseModel):
    """List active monologues (main only)."""
    pass

class KillMonologue(BaseModel):
    """Terminate monologues. Main: any sub except Communication. Sub: self only."""
    target_id: Optional[str] = None

ACTION_DEFS: Dict[str, Dict[str, Any]] = {
    "open_monologue": {"description": "Open a new sub‑monologue. Default local Gemma; OpenAI optional.", "model": OpenMonologue},
    "ask_user": {"description": "Main asks the human via Communication; reply routes back to Main.", "model": AskUser},
    "sleep": {"description": "Sleep with early‑wake on incoming message. Subs self-only.", "model": Sleep},
    "message_monologue": {"description": "Message another monologue; optional wait; correlated with request_id.", "model": MessageMonologue},
    "list_monologue": {"description": "List active monologues (main only).", "model": ListMonologue},
    "kill_monologue": {"description": "Kill policy (main any sub except Comms; sub self-only).", "model": KillMonologue},
}

# ---------------------------------------------------------------------------
# Orchestrator action models
# ---------------------------------------------------------------------------

class ActionName(str, Enum):
    """Canonical action names emitted by the controller."""

    INJECT = "inject"
    SPAWN = "spawn"
    STOP_SELF = "stop_self"
    STOP_CHILD = "stop_child"
    SLEEP = "sleep"
    IDLE = "idle"
    TOOL = "tool"
    REPORT_STATUS = "report_status"
    ROUTE_MESSAGE = "route_message"
    ASK_USER = "ask_user"
    USER_REPLY = "user_reply"


class InjectAction(BaseModel):
    type: Literal[ActionName.INJECT] = ActionName.INJECT
    content: str


class SpawnAction(BaseModel):
    type: Literal[ActionName.SPAWN] = ActionName.SPAWN
    role: str
    goal: str


class StopSelfAction(BaseModel):
    type: Literal[ActionName.STOP_SELF] = ActionName.STOP_SELF


class StopChildAction(BaseModel):
    type: Literal[ActionName.STOP_CHILD] = ActionName.STOP_CHILD
    id: str


class SleepAction(BaseModel):
    type: Literal[ActionName.SLEEP] = ActionName.SLEEP
    seconds: float


class IdleAction(BaseModel):
    type: Literal[ActionName.IDLE] = ActionName.IDLE
    seconds: float


class ToolAction(BaseModel):
    type: Literal[ActionName.TOOL] = ActionName.TOOL
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ReportStatusAction(BaseModel):
    type: Literal[ActionName.REPORT_STATUS] = ActionName.REPORT_STATUS


class RouteMessageAction(BaseModel):
    type: Literal[ActionName.ROUTE_MESSAGE] = ActionName.ROUTE_MESSAGE
    to: str
    content: str


class AskUserAction(BaseModel):
    type: Literal[ActionName.ASK_USER] = ActionName.ASK_USER
    id: str
    content: str
    choices: Optional[List[str]] = None


class UserReplyAction(BaseModel):
    type: Literal[ActionName.USER_REPLY] = ActionName.USER_REPLY
    in_reply_to: str
    content: str


ActionType = Annotated[
    InjectAction
    | SpawnAction
    | StopSelfAction
    | StopChildAction
    | SleepAction
    | IdleAction
    | ToolAction
    | ReportStatusAction
    | RouteMessageAction
    | AskUserAction
    | UserReplyAction,
    Field(discriminator="type"),
]

_ACTION_ADAPTER = TypeAdapter(List[ActionType])


def parse_actions(actions: List[dict]) -> List[ActionType]:
    """Validate and convert raw action dicts to ActionType models.

    Any invalid entries are skipped.
    """

    try:
        return _ACTION_ADAPTER.validate_python(actions)
    except ValidationError:
        valid: List[ActionType] = []
        for a in actions:
            try:
                valid.append(_ACTION_ADAPTER.validate_python([a])[0])
            except ValidationError:
                continue
        return valid
