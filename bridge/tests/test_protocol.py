import json

import pytest

from bridge.protocol import (
    NpcInteract,
    NpcReply,
    SessionReset,
    parse_message,
)


def test_npc_interact_roundtrip():
    msg = NpcInteract(
        id="abc-123",
        npc="Robin",
        player="Alex",
        location="Town",
        ts=1715251200,
    )
    raw = msg.model_dump_json()
    parsed = json.loads(raw)
    assert parsed == {
        "type": "npc_interact",
        "v": 1,
        "id": "abc-123",
        "npc": "Robin",
        "player": "Alex",
        "location": "Town",
        "ts": 1715251200,
    }
    back = parse_message(raw)
    assert isinstance(back, NpcInteract)
    assert back.npc == "Robin"


def test_npc_reply_roundtrip():
    msg = NpcReply(id="abc-123", npc="Robin", text="Hi Alex!", done=True)
    raw = msg.model_dump_json()
    assert json.loads(raw)["type"] == "npc_reply"
    back = parse_message(raw)
    assert isinstance(back, NpcReply)
    assert back.text == "Hi Alex!"


def test_session_reset_roundtrip():
    msg = SessionReset(reason="returned_to_title")
    raw = msg.model_dump_json()
    assert json.loads(raw) == {
        "type": "session_reset",
        "v": 1,
        "reason": "returned_to_title",
    }


def test_unknown_type_returns_none():
    raw = json.dumps({"type": "mystery", "v": 1})
    assert parse_message(raw) is None


def test_malformed_json_returns_none():
    assert parse_message("{not json") is None


def test_missing_required_field_returns_none():
    raw = json.dumps({"type": "npc_interact", "v": 1, "id": "x"})
    # missing npc/player/location/ts
    assert parse_message(raw) is None
