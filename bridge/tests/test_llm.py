from unittest.mock import AsyncMock, MagicMock

import pytest

from bridge.llm import build_messages, reply, FALLBACK_TEXT
from bridge.llm import (
    HISTORY_MAX_TURNS,
    PLAYER_APPROACH_MARKER,
)


def test_build_messages_includes_system_and_history_and_user():
    history = [
        {"role": "user", "text": "Hello"},
        {"role": "assistant", "text": "Hi Alex!"},
    ]
    msgs = build_messages(
        npc_name="Robin",
        player_name="Alex",
        location="Town",
        history=history,
        user_text="What time is it?",
    )
    assert msgs[0]["role"] == "system"
    assert "Robin" in msgs[0]["content"]
    assert "Alex" in msgs[0]["content"]
    assert "Town" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "Hello"}
    assert msgs[2] == {"role": "assistant", "content": "Hi Alex!"}
    assert msgs[3] == {"role": "user", "content": "What time is it?"}


@pytest.mark.asyncio
async def test_reply_returns_string_from_client():
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="  Howdy!  "))]
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    text = await reply(
        client=fake_client,
        npc_name="Robin",
        player_name="Alex",
        location="Town",
        history=[],
        user_text="Hi",
    )
    assert text == "Howdy!"


@pytest.mark.asyncio
async def test_reply_fallback_on_exception():
    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))

    text = await reply(
        client=fake_client,
        npc_name="Robin",
        player_name="Alex",
        location="Town",
        history=[],
        user_text="Hi",
    )
    assert text == FALLBACK_TEXT


@pytest.mark.asyncio
async def test_reply_fallback_on_empty_choice():
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.choices = []
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    text = await reply(
        client=fake_client,
        npc_name="Robin",
        player_name="Alex",
        location="Town",
        history=[],
        user_text="Hi",
    )
    assert text == FALLBACK_TEXT


def _full_state():
    return {
        "date": {"year": 2, "season": "fall", "day": 12, "dayOfWeek": "Mon"},
        "weather": "rainy",
        "spouse": "Sebastian",
        "activeQuests": ["Bouncer", "Robin's Lost Axe"],
    }


def test_build_messages_injects_state_block():
    msgs = build_messages(
        npc_name="Robin",
        player_name="Alex",
        location="Town",
        history=[],
        user_text="",
        state=_full_state(),
    )
    # system, state-block (user role), final user (marker)
    assert len(msgs) == 3
    state_msg = msgs[1]
    assert state_msg["role"] == "user"
    content = state_msg["content"]
    assert content.startswith("Current game state:")
    assert "Fall 12, year 2" in content
    assert "Mon" in content
    assert "rainy" in content
    assert "Sebastian" in content
    assert "Bouncer" in content
    assert "Robin's Lost Axe" in content


def test_build_messages_omits_spouse_when_null():
    state = _full_state()
    state["spouse"] = None
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=[], user_text="", state=state,
    )
    state_msg_content = msgs[1]["content"]
    assert "Player's spouse" not in state_msg_content


def test_build_messages_omits_quests_when_empty():
    state = _full_state()
    state["activeQuests"] = []
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=[], user_text="", state=state,
    )
    state_msg_content = msgs[1]["content"]
    assert "Active quests" not in state_msg_content


def test_build_messages_no_state():
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=[], user_text="", state=None,
    )
    # no state block: just system + final user
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_build_messages_user_text_empty_uses_marker():
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=[], user_text="", state=None,
    )
    assert msgs[-1]["content"] == PLAYER_APPROACH_MARKER


def test_build_messages_passes_marker_user_turns_through():
    history = [
        {"role": "user", "text": PLAYER_APPROACH_MARKER},
        {"role": "assistant", "text": "Hi Alex!"},
    ]
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=history, user_text="", state=None,
    )
    user_turns = [m for m in msgs if m["role"] == "user"]
    assert user_turns[0]["content"] == PLAYER_APPROACH_MARKER


def test_build_messages_trims_history_to_last_10():
    history = []
    for i in range(20):
        history.append({"role": "user", "text": PLAYER_APPROACH_MARKER})
        history.append({"role": "assistant", "text": f"reply-{i}"})
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=history, user_text="", state=None,
    )
    # msgs = system + (last HISTORY_MAX_TURNS history entries) + current user
    assert len(msgs) == 1 + HISTORY_MAX_TURNS + 1
    assistant_replies = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert assistant_replies[-1] == "reply-19"
    assert "reply-0" not in assistant_replies
