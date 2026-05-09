"""DeepSeek wrapper. OpenAI-compatible API."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI

log = logging.getLogger("bridge.llm")

FALLBACK_TEXT = "(NPC seems lost in thought.)"
PLAYER_APPROACH_MARKER = "(player approaches)"
HISTORY_MAX_TURNS = 10
MODEL = "deepseek-chat"
TIMEOUT_SECONDS = 8.0
MAX_TOKENS = 200


def make_client() -> AsyncOpenAI:
    """Construct a DeepSeek client. Reads DEEPSEEK_API_KEY from the environment."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def _format_state_block(state: dict | None) -> str | None:
    """Format a GameState dict into a 'Current game state:' bullet block.

    Returns None when state is None so the caller can omit the block entirely.
    Skips spouse and quests lines individually when those fields are null/empty.
    """
    if state is None:
        return None
    d = state["date"]
    lines = [
        "Current game state:",
        f"- Date: {d['season'].capitalize()} {d['day']}, year {d['year']} ({d['dayOfWeek']})",
        f"- Weather: {state['weather']}",
    ]
    if state.get("spouse"):
        lines.append(f"- Player's spouse: {state['spouse']}")
    quests = (state.get("activeQuests") or [])[:5]
    if quests:
        lines.append(f"- Active quests: {', '.join(quests)}")
    return "\n".join(lines)


def build_messages(
    npc_name: str,
    player_name: str,
    location: str,
    history: list[dict[str, str]],
    user_text: str,
    state: dict | None = None,
) -> list[dict[str, str]]:
    system = (
        f"You are {npc_name} from Stardew Valley. "
        f"The player {player_name} just talked to you in {location}. "
        f"Reply in 1-2 short sentences, in character, in English."
    )
    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]

    state_block = _format_state_block(state)
    if state_block:
        msgs.append({"role": "user", "content": state_block})

    trimmed = history[-HISTORY_MAX_TURNS:]
    for turn in trimmed:
        role = turn.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": turn.get("text", "")})

    msgs.append({"role": "user", "content": user_text or PLAYER_APPROACH_MARKER})
    return msgs


async def reply(
    client: Any,
    npc_name: str,
    player_name: str,
    location: str,
    history: list[dict[str, str]],
    user_text: str,
    state: dict | None = None,
) -> str:
    """Call DeepSeek; return reply text or FALLBACK_TEXT on any error."""
    messages = build_messages(npc_name, player_name, location, history, user_text, state=state)
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
            ),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as ex:
        log.warning("LLM call failed: %s", ex)
        return FALLBACK_TEXT

    choices = getattr(response, "choices", None) or []
    if not choices:
        log.warning("LLM returned no choices.")
        return FALLBACK_TEXT
    text = (choices[0].message.content or "").strip()
    return text or FALLBACK_TEXT
