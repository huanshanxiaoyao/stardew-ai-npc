# State Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject current game state (date, weather, spouse, active quests) into each LLM call, plus fix the Phase 3 empty-user-turn artifact and add a 10-turn history cap.

**Architecture:** Mod gathers structured state on the main thread (new `StateCollector` class) and adds it as an optional `state` field on `npc_interact`. Bridge formats it into a "Current game state:" block placed between the system prompt and conversation history. Same change pass replaces empty user turns with a synthetic `(player approaches)` marker (write-time canonicalization in `server.py`) and trims the LLM-bound history slice to the last 10 turns.

**Tech Stack:** C# .NET 6 (mod side), Python 3.11 / pydantic 2 / openai SDK (bridge side). No new dependencies. .NET 6 SDK at `/opt/homebrew/opt/dotnet@6/bin/dotnet` (keg-only — prepend to PATH).

**Reference spec:** `docs/superpowers/specs/2026-05-09-state-injection-design.md`

---

## File Structure

Files this plan touches, with the responsibility each one carries after the change:

```
mod/
├── Game/                                        # NEW directory
│   └── StateCollector.cs                        # NEW: reads Game1 → GameState DTO
├── Net/
│   ├── Messages.cs                              # MOD: + GameDate, GameState records; NpcInteract gains optional State
│   └── BridgeClient.cs                          # MOD: SendNpcInteract gains state parameter
└── Patches/
    └── NpcCheckActionPatch.cs                   # MOD: 1-line call to StateCollector.Collect()

bridge/
├── bridge/
│   ├── protocol.py                              # MOD: + GameDate, GameState models; NpcInteract gains optional state
│   ├── llm.py                                   # MOD: + state-block formatter, HISTORY_MAX_TURNS, PLAYER_APPROACH_MARKER, build_messages and reply gain state param
│   └── server.py                                # MOD: pass state through to llm.reply; record marker (not "") on history append
└── tests/
    ├── test_protocol.py                         # MOD: + state round-trip cases
    └── test_llm.py                              # MOD: + state injection / history / marker tests
```

Order of work: **bridge first, then mod**. Bridge changes are TDD-able in isolation; once the protocol shape is locked in tests, the mod can be implemented against it without surprises.

---

## Task 1: Bridge — extend `protocol.py` with optional `state` field (TDD)

**Files:**
- Modify: `bridge/bridge/protocol.py`
- Modify: `bridge/tests/test_protocol.py`

- [ ] **Step 1: Write failing tests**

Append the following to `bridge/tests/test_protocol.py`:

```python
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
```

- [ ] **Step 2: Run; confirm failures**

Run from project root:
```bash
cd bridge && ./.venv/bin/pytest tests/test_protocol.py -v
```
Expected: 3 new tests fail with `ImportError: cannot import name 'GameState'` (or similar) once you add `from bridge.protocol import GameState`. Actually they will fail before even importing — they reference `msg.state` which doesn't yet exist on `NpcInteract`. Look for `AttributeError: 'NpcInteract' object has no attribute 'state'` or pydantic rejecting the unknown `state` field with `extra_forbidden`.

- [ ] **Step 3: Implement**

Edit `bridge/bridge/protocol.py`. Add `GameDate` and `GameState` model classes, then add an optional `state` field on `NpcInteract`. The full final file looks like:

```python
"""Wire protocol for the SMAPI mod ↔ bridge WebSocket connection.

Single source of truth. The C# mod hand-codes matching records.
"""
from __future__ import annotations

import json
from typing import Literal, Optional, Union

from pydantic import BaseModel, ValidationError


class GameDate(BaseModel):
    year: int
    season: str         # spring | summer | fall | winter
    day: int
    dayOfWeek: str      # Mon..Sun


class GameState(BaseModel):
    date: GameDate
    weather: str        # sunny | rainy | snowy | stormy
    spouse: Optional[str] = None
    activeQuests: list[str] = []


class NpcInteract(BaseModel):
    type: Literal["npc_interact"] = "npc_interact"
    v: Literal[1] = 1
    id: str
    npc: str
    player: str
    location: str
    ts: int
    state: Optional[GameState] = None


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

    Soft-fail by design: unknown types are logged and ignored, not fatal.
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
```

The only change vs the current file is the two new model classes (`GameDate`, `GameState`) and the new `state: Optional[GameState] = None` field on `NpcInteract`. All other code is preserved verbatim.

- [ ] **Step 4: Run all bridge tests; confirm 16 passing**

Run:
```bash
cd bridge && ./.venv/bin/pytest -v
```
Expected: 16 passed (13 from before + 3 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/protocol.py bridge/tests/test_protocol.py
git commit -m "feat(bridge): add optional GameState to npc_interact protocol"
```

---

## Task 2: Bridge — `llm.py` state block, history trim, marker (TDD)

**Files:**
- Modify: `bridge/bridge/llm.py`
- Modify: `bridge/tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

Append the following to `bridge/tests/test_llm.py` (you'll need new imports — add them at the top of the file after the existing ones):

```python
from bridge.llm import (
    HISTORY_MAX_TURNS,
    PLAYER_APPROACH_MARKER,
)
```

Then append these test functions:

```python
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
    # find the historical user turn
    user_turns = [m for m in msgs if m["role"] == "user"]
    # first is the historical marker; last is current click marker
    assert user_turns[0]["content"] == PLAYER_APPROACH_MARKER


def test_build_messages_trims_history_to_last_10():
    history = []
    for i in range(20):
        history.append({"role": "user", "text": PLAYER_APPROACH_MARKER})
        history.append({"role": "assistant", "text": f"reply-{i}"})
    # 40 turns total
    msgs = build_messages(
        npc_name="Robin", player_name="Alex", location="Town",
        history=history, user_text="", state=None,
    )
    # msgs = system + (last HISTORY_MAX_TURNS history entries) + current user
    assert len(msgs) == 1 + HISTORY_MAX_TURNS + 1
    assistant_replies = [m["content"] for m in msgs if m["role"] == "assistant"]
    # should be the LAST assistant replies, not the earliest
    assert assistant_replies[-1] == "reply-19"
    assert "reply-0" not in assistant_replies
```

- [ ] **Step 2: Run; confirm failures**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_llm.py -v
```
Expected: 7 new tests fail with `ImportError: cannot import name 'HISTORY_MAX_TURNS' from 'bridge.llm'` (or `PLAYER_APPROACH_MARKER`, depending on import order).

- [ ] **Step 3: Implement**

Replace the contents of `bridge/bridge/llm.py` with:

```python
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
    quests = (state.get("activeQuests") or [])[:5]   # defensive re-trim
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
```

Changes vs the previous file:
- New constants: `PLAYER_APPROACH_MARKER`, `HISTORY_MAX_TURNS`.
- New helper: `_format_state_block`.
- `build_messages` gets `state=None` parameter, inserts the state block as a user-role message between system and history, trims history to last `HISTORY_MAX_TURNS`, and the final current user message uses the marker when `user_text` is empty.
- `reply` gets `state=None` parameter and forwards it.
- Existing tests that called `reply(...)` without state still pass because the parameter is optional.

- [ ] **Step 4: Run all bridge tests; confirm 23 passing**

Run:
```bash
cd bridge && ./.venv/bin/pytest -v
```
Expected: 23 passed (16 from after Task 1 + 7 new).

If `test_reply_returns_string_from_client` or other Phase 3 tests fail, the state-block insertion may have shifted indices the older tests assumed. Re-read their assertions and check whether they reference message positions; the new behavior is system + (state if any) + history + final user, and Phase 3 tests passed `state=None` implicitly so positions should be unchanged.

- [ ] **Step 5: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/llm.py bridge/tests/test_llm.py
git commit -m "feat(bridge): state block, history trim, player marker"
```

---

## Task 3: Bridge — `server.py` plumbing

**Files:**
- Modify: `bridge/bridge/server.py`

This task has no automated tests of its own — the changes are pure plumbing already covered by Task 2's unit tests for the wire / format. The end-to-end behavior is exercised by manual acceptance (Task 8).

- [ ] **Step 1: Modify `bridge/bridge/server.py`**

Two surgical edits inside `_make_handler`'s inner `handler` function, in the file's current shape:

Edit 1 — find this block (the LLM call):
```python
            user_text = ""  # phase 3: no free-text input from the player yet
            text = await llm_mod.reply(
                client=client,
                npc_name=msg.npc,
                player_name=msg.player,
                location=msg.location,
                history=history.get(msg.npc, []),
                user_text=user_text,
            )
```
Replace with:
```python
            user_text = ""  # phase 3: no free-text input from the player yet
            text = await llm_mod.reply(
                client=client,
                npc_name=msg.npc,
                player_name=msg.player,
                location=msg.location,
                history=history.get(msg.npc, []),
                user_text=user_text,
                state=msg.state.model_dump() if msg.state else None,
            )
```

Edit 2 — find this line (recording the user turn in history):
```python
        history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
```
Replace with:
```python
        history.setdefault(msg.npc, []).append(
            {"role": "user", "text": llm_mod.PLAYER_APPROACH_MARKER}
        )
```

- [ ] **Step 2: Run all bridge tests; confirm still 23 passing**

Run:
```bash
cd bridge && ./.venv/bin/pytest -v
```
Expected: 23 passed. The existing `test_echo_roundtrip.py` tests don't go through `_make_handler`'s LLM branch (they use `client_factory=None`), so they're unaffected.

- [ ] **Step 3: Smoke test the server can still start**

Run from project root, with no `--echo` so the LLM path is selected (it'll try to construct a DeepSeek client; we won't actually click anything, just verify it boots without import errors):
```bash
./scripts/run_bridge.sh --debug
```
Expected: log line `listening on ws://127.0.0.1:8765 (llm=True)`. Press `Ctrl+C` to stop.

- [ ] **Step 4: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/server.py
git commit -m "feat(bridge): pass state to llm and use marker on history append"
```

---

## Task 4: Mod — extend `Messages.cs` with state records

**Files:**
- Modify: `mod/Net/Messages.cs`

- [ ] **Step 1: Replace `mod/Net/Messages.cs`**

The full new file content:

```csharp
using System;
using System.Text.Json.Serialization;

namespace StardewAiMod.Net
{
    public record GameDate(
        [property: JsonPropertyName("year")] int Year,
        [property: JsonPropertyName("season")] string Season,
        [property: JsonPropertyName("day")] int Day,
        [property: JsonPropertyName("dayOfWeek")] string DayOfWeek);

    public record GameState(
        [property: JsonPropertyName("date")] GameDate Date,
        [property: JsonPropertyName("weather")] string Weather,
        [property: JsonPropertyName("spouse")] string? Spouse,
        [property: JsonPropertyName("activeQuests")] string[] ActiveQuests);

    public record NpcInteract(
        [property: JsonPropertyName("id")] string Id,
        [property: JsonPropertyName("npc")] string Npc,
        [property: JsonPropertyName("player")] string Player,
        [property: JsonPropertyName("location")] string Location,
        [property: JsonPropertyName("ts")] long Ts,
        [property: JsonPropertyName("state")] GameState? State
    )
    {
        [JsonPropertyName("type")]
        public string Type => "npc_interact";

        [JsonPropertyName("v")]
        public int V => 1;
    }

    public record NpcReply(
        [property: JsonPropertyName("id")] string Id,
        [property: JsonPropertyName("npc")] string Npc,
        [property: JsonPropertyName("text")] string Text,
        [property: JsonPropertyName("done")] bool Done
    )
    {
        [JsonPropertyName("type")]
        public string Type => "npc_reply";

        [JsonPropertyName("v")]
        public int V => 1;
    }

    public record SessionReset(
        [property: JsonPropertyName("reason")] string Reason
    )
    {
        [JsonPropertyName("type")]
        public string Type => "session_reset";

        [JsonPropertyName("v")]
        public int V => 1;
    }
}
```

The only changes vs the existing file: two new records (`GameDate`, `GameState`) and one new positional parameter on `NpcInteract` (`GameState? State`).

- [ ] **Step 2: Build**

Run from project root:
```bash
PATH="/opt/homebrew/opt/dotnet@6/bin:$PATH" dotnet build mod/StardewAiMod.csproj -c Debug
```
Expected: `Build succeeded.` 0 errors. (2 CS8032 analyzer warnings are normal — they appear on every build.)

A build error here usually means the existing call to `new NpcInteract(...)` in `BridgeClient.cs` is now missing its trailing `State` argument — but that's actually fine for this task because `BridgeClient` will be updated in Task 6, and an extra argument is required, so the build will fail at this point. That's expected. **If the build fails with `CS7036: There is no argument given that corresponds to the required parameter 'State'`, that confirms the new positional record parameter is in place; proceed to commit and Task 5 will resolve the chain.**

To keep the build green between tasks, you can apply Task 6's edit early (one-line change) before committing this task — but it adds a small ordering coupling. Either approach is fine; the simpler thing is to commit a known-broken-build state since both Task 5 and Task 6 are fast. Choose:

- **Option A (recommended)**: commit this task with build temporarily broken, finish Tasks 5–7 in sequence, build green again at end of Task 7.
- **Option B**: also apply Task 6's `BridgeClient.SendNpcInteract` signature update now to keep the build green, and skip Step 1 of Task 6 when you get there.

- [ ] **Step 3: Commit**

```bash
git add mod/Net/Messages.cs
git commit -m "feat(mod): add GameDate, GameState records; NpcInteract gains optional State"
```

---

## Task 5: Mod — create `StateCollector.cs`

**Files:**
- Create: `mod/Game/StateCollector.cs`

- [ ] **Step 1: Create directory**

```bash
mkdir -p mod/Game
```

- [ ] **Step 2: Write `mod/Game/StateCollector.cs`**

```csharp
using System;
using System.Linq;
using StardewAiMod.Net;
using StardewModdingAPI;
using StardewValley;

namespace StardewAiMod.Game
{
    /// <summary>
    /// Reads SDV global state into a JSON-friendly snapshot.
    /// Best-effort: returns null if the world is not ready or any read throws,
    /// so a Stardew API hiccup never breaks NPC dialogue.
    /// </summary>
    public static class StateCollector
    {
        private static IMonitor? Monitor;
        private static readonly string[] DayNames = { "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" };
        private const int MaxQuests = 5;

        public static void Initialize(IMonitor monitor)
        {
            Monitor = monitor;
        }

        public static GameState? Collect()
        {
            if (!Context.IsWorldReady) return null;

            try
            {
                var date = new GameDate(
                    Year: StardewValley.Game1.year,
                    Season: StardewValley.Game1.currentSeason ?? "spring",
                    Day: StardewValley.Game1.dayOfMonth,
                    DayOfWeek: DayNames[(StardewValley.Game1.dayOfMonth - 1) % 7]
                );

                var weather = ReadWeather();

                var spouse = StardewValley.Game1.player?.spouse;
                if (string.IsNullOrEmpty(spouse)) spouse = null;

                var quests = StardewValley.Game1.player?.questLog
                    ?.Take(MaxQuests)
                    .Select(q => q?.questTitle?.Value ?? "")
                    .Where(t => !string.IsNullOrEmpty(t))
                    .ToArray()
                    ?? Array.Empty<string>();

                return new GameState(date, weather, spouse, quests);
            }
            catch (Exception ex)
            {
                Monitor?.Log($"StateCollector failed: {ex.Message}", LogLevel.Trace);
                return null;
            }
        }

        private static string ReadWeather()
        {
            if (StardewValley.Game1.isLightning) return "stormy";
            if (StardewValley.Game1.isRaining) return "rainy";
            if (StardewValley.Game1.isSnowing) return "snowy";
            return "sunny";
        }
    }
}
```

Notes for the implementer:
- The fully-qualified `StardewValley.Game1` is used because `Game1` is a SDV class but the namespace `StardewAiMod.Game` we created collides with it as a simple `Game1` reference. Using the fully-qualified form avoids needing a `using` alias.
- `quest.questTitle.Value` — `questTitle` is a `NetString` in SDV 1.6; `.Value` unwraps it. If the build fails with `'questTitle' does not contain a definition for 'Value'`, change `q?.questTitle?.Value` to `q?.questTitle?.ToString()` (older SDV versions used a plain string).
- `(dayOfMonth - 1) % 7` mapping: SDV days 1, 8, 15, 22 → index 0 (Mon). 2, 9, 16, 23 → index 1 (Tue). And so on. That matches the in-game weekday ordering (Mon..Sun).

- [ ] **Step 3: Build**

Run:
```bash
PATH="/opt/homebrew/opt/dotnet@6/bin:$PATH" dotnet build mod/StardewAiMod.csproj -c Debug
```
Expected outcomes:
- If you went with **Option A** in Task 4: build still fails on `CS7036` for the missing `State` arg in `BridgeClient.SendNpcInteract`'s constructor call. That's expected; proceed.
- If you went with **Option B**: build succeeds (0 errors, 2 CS8032 warnings).

Either way, the new `StateCollector.cs` itself should compile cleanly — no errors should mention `Game/StateCollector.cs`.

- [ ] **Step 4: Commit**

```bash
git add mod/Game/StateCollector.cs
git commit -m "feat(mod): add StateCollector to snapshot SDV game state"
```

---

## Task 6: Mod — extend `BridgeClient.SendNpcInteract` signature

**Files:**
- Modify: `mod/Net/BridgeClient.cs`

- [ ] **Step 1: Replace `SendNpcInteract` method**

Find this method:
```csharp
        public string? SendNpcInteract(string npcName, string playerName, string location)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return null;
            var id = Guid.NewGuid().ToString("N");
            var msg = new NpcInteract(id, npcName, playerName, location, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
            return id;
        }
```

Replace with:
```csharp
        public string? SendNpcInteract(string npcName, string playerName, string location, GameState? state)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return null;
            var id = Guid.NewGuid().ToString("N");
            var msg = new NpcInteract(id, npcName, playerName, location, DateTimeOffset.UtcNow.ToUnixTimeSeconds(), state);
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
            return id;
        }
```

Two changes: new `GameState? state` parameter, and the `NpcInteract` constructor call now passes `state`.

- [ ] **Step 2: Build**

```bash
PATH="/opt/homebrew/opt/dotnet@6/bin:$PATH" dotnet build mod/StardewAiMod.csproj -c Debug
```
Expected: now the build fails on `NpcCheckActionPatch.cs` because the patch still calls the old 3-arg `SendNpcInteract`. Look for `CS1501: No overload for method 'SendNpcInteract' takes 3 arguments`. **That's expected; Task 7 fixes it.**

- [ ] **Step 3: Commit**

```bash
git add mod/Net/BridgeClient.cs
git commit -m "feat(mod): BridgeClient.SendNpcInteract takes GameState"
```

---

## Task 7: Mod — wire `StateCollector` into the patch

**Files:**
- Modify: `mod/Patches/NpcCheckActionPatch.cs`
- Modify: `mod/ModEntry.cs` (initialize the StateCollector's monitor)

- [ ] **Step 1: Update `mod/Patches/NpcCheckActionPatch.cs`**

Find this block in the `Prefix` method:
```csharp
            var placeholder = new DialogueBox("…");
            Game1.activeClickableMenu = placeholder;

            var id = bridge.SendNpcInteract(__instance.Name, who.Name, l?.Name ?? "Unknown");
```

Replace with:
```csharp
            var placeholder = new DialogueBox("…");
            Game1.activeClickableMenu = placeholder;

            var state = StardewAiMod.Game.StateCollector.Collect();
            var id = bridge.SendNpcInteract(__instance.Name, who.Name, l?.Name ?? "Unknown", state);
```

The fully-qualified `StardewAiMod.Game.StateCollector` again avoids the `Game1` name collision. Alternatively, add `using StardewAiMod.Game;` at the top of the file and call `StateCollector.Collect()` directly — either works.

- [ ] **Step 2: Update `mod/ModEntry.cs`**

Find this block in `Entry`:
```csharp
            NpcCheckActionPatch.Initialize(this.Monitor, this);

            var harmony = new Harmony(this.ModManifest.UniqueID);
```

Replace with:
```csharp
            NpcCheckActionPatch.Initialize(this.Monitor, this);
            StardewAiMod.Game.StateCollector.Initialize(this.Monitor);

            var harmony = new Harmony(this.ModManifest.UniqueID);
```

- [ ] **Step 3: Build**

```bash
PATH="/opt/homebrew/opt/dotnet@6/bin:$PATH" dotnet build mod/StardewAiMod.csproj -c Debug
```
Expected: `Build succeeded.` with 0 errors and 2 CS8032 warnings.

If you see `'StardewAiMod.Game' does not contain a type or namespace name 'StateCollector'`, the file from Task 5 wasn't added to the project — check `mod/Game/StateCollector.cs` exists and the path resolves.

- [ ] **Step 4: Install via the script**

```bash
./scripts/install_mod.sh
```
Expected: `Installed to: /Users/suchong/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/StardewAiMod`.

- [ ] **Step 5: Commit**

```bash
git add mod/Patches/NpcCheckActionPatch.cs mod/ModEntry.cs
git commit -m "feat(mod): patch collects state and passes it to bridge"
```

---

## Task 8: Manual acceptance (USER)

**Files:** none (manual verification)

The implementer cannot do this; it must be run by the user. The implementer should mark this task as deferred and report DONE for the implementation portion.

The user should perform these checks against the spec §7 manual list:

1. Run `./scripts/run_bridge.sh --debug` from project root. Bridge log shows `listening on ws://127.0.0.1:8765 (llm=True)`. Leave running.
2. Launch Stardew Valley via Steam. Bridge terminal logs `client connected: …`. Game's SMAPI console logs `Bridge: connected.`
3. Click any NPC. Bridge `--debug` log includes the full `npc_interact` JSON; verify it contains a `"state": {...}` object with `date`, `weather`, `spouse`, `activeQuests` populated for your save state.
4. **Weather check**: if it's currently raining in your save, the NPC reply mentions rain in some natural way (not generic).
5. **Spouse check**: if you're married (e.g., to Sebastian), some replies acknowledge that.
6. **Quest check**: if you have an active quest in your log, replies may reference it by name.
7. **Continuity check (the marker fix)**: click the same NPC three times in a row. The third reply should reference earlier turns ("As I was saying...", or thematic continuation), not start over with "Hi there!" each time.
8. **No-state regression**: stop the bridge, restart it, and click any NPC — first reply works (no history yet), state is still injected, no errors in either log.
9. **Native fallback**: stop the bridge entirely (Ctrl+C). Click an NPC. Native dialogue appears (Phase 3 fallback unchanged).
10. **State-collect failure resilience** (optional, requires editing code): temporarily put `throw new Exception("test");` at the top of `StateCollector.Collect()`, rebuild, click an NPC. NPC still replies (using Phase 3 path); SMAPI console at Trace level shows `StateCollector failed: test`. **Revert the throw and rebuild before continuing.**

If checks 3, 4, 5, 6, 7, 9 all pass, the implementation is shipped.

---

## Done

After Task 7's commit, the code is complete; manual acceptance (Task 8) is the user's pass/fail gate. Total estimated change: ~170 lines of new/changed code across mod and bridge, plus ~120 lines of new tests.
