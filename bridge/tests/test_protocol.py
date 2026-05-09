import json

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
        "state": None,
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


def test_npc_interact_with_state_roundtrip():
    raw = json.dumps({
        "type": "npc_interact",
        "v": 1,
        "id": "x",
        "npc": "Robin",
        "player": "Alex",
        "location": "Town",
        "ts": 1,
        "state": {
            "date": {"year": 2, "season": "fall", "day": 12, "dayOfWeek": "Mon"},
            "weather": "rainy",
            "spouse": "Sebastian",
            "activeQuests": ["Bouncer", "Robin's Lost Axe"],
        },
    })
    msg = parse_message(raw)
    assert isinstance(msg, NpcInteract)
    assert msg.state is not None
    assert msg.state.weather == "rainy"
    assert msg.state.spouse == "Sebastian"
    assert msg.state.date.season == "fall"
    assert msg.state.date.dayOfWeek == "Mon"
    assert msg.state.activeQuests == ["Bouncer", "Robin's Lost Axe"]


def test_npc_interact_no_state_roundtrip():
    raw = json.dumps({
        "type": "npc_interact",
        "v": 1,
        "id": "x",
        "npc": "Robin",
        "player": "Alex",
        "location": "Town",
        "ts": 1,
    })
    msg = parse_message(raw)
    assert isinstance(msg, NpcInteract)
    assert msg.state is None


def test_npc_interact_state_null_roundtrip():
    raw = json.dumps({
        "type": "npc_interact",
        "v": 1,
        "id": "x",
        "npc": "Robin",
        "player": "Alex",
        "location": "Town",
        "ts": 1,
        "state": None,
    })
    msg = parse_message(raw)
    assert isinstance(msg, NpcInteract)
    assert msg.state is None
