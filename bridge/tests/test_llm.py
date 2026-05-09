from unittest.mock import AsyncMock, MagicMock

import pytest

from bridge.llm import build_messages, reply, FALLBACK_TEXT


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
