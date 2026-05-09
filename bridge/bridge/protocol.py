"""Wire protocol for the SMAPI mod ↔ bridge WebSocket connection.

Single source of truth. The C# mod hand-codes matching records.
"""
from __future__ import annotations

import json
from typing import Literal, Optional, Union

from pydantic import BaseModel, ValidationError


class NpcInteract(BaseModel):
    type: Literal["npc_interact"] = "npc_interact"
    v: Literal[1] = 1
    id: str
    npc: str
    player: str
    location: str
    ts: int


class NpcReply(BaseModel):
    type: Literal["npc_reply"] = "npc_reply"
    v: Literal[1] = 1
    id: str
    npc: str
    text: str
    done: bool = True


class SessionReset(BaseModel):
    type: Literal["session_reset"] = "session_reset"
    v: Literal[1] = 1
    reason: str


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    v: Literal[1] = 1
    id: Optional[str] = None
    code: str
    message: str


Message = Union[NpcInteract, NpcReply, SessionReset, ErrorMsg]

_TYPES: dict[str, type[BaseModel]] = {
    "npc_interact": NpcInteract,
    "npc_reply": NpcReply,
    "session_reset": SessionReset,
    "error": ErrorMsg,
}


def parse_message(raw: str) -> Optional[Message]:
    """Parse a JSON frame. Returns None on malformed input or unknown type.

    Soft-fail by design: protocol §5 says unknown types are logged and ignored,
    not treated as fatal.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    cls = _TYPES.get(obj.get("type"))
    if cls is None:
        return None
    try:
        return cls.model_validate(obj)
    except ValidationError:
        return None
