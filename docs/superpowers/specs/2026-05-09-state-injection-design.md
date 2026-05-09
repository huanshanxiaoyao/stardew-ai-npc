# Stardew Valley AI NPC — State Injection Design Spec

- **Date**: 2026-05-09 (second spec of the day)
- **Status**: Approved (pending user spec review)
- **Author**: Brainstorming session (Claude + user)
- **Builds on**: `2026-05-09-stardew-ai-npc-design.md` (Phases 1–3 already implemented)

## 1. Goal & Non-goals

### Goal
Make NPC replies feel grounded in the player's current playthrough by injecting current game state into each LLM call. Today the LLM only knows a hardcoded persona; after this change, the LLM also sees the in-game date, weather, the player's spouse, and the player's active quests on each click. Same change pass also fixes a Phase 3 prompt-quality bug: every "user turn" in conversation history was an empty string, which made the LLM lose conversational continuity.

### Non-goals (this spec)
- NPC-side state (NPC's current map location, mood, friendship score, gift preference table). Reserved for a "rich" tier that builds on this one.
- Player free-text input (a chat box where the player types something to the NPC). Important next step but a separate UI feature.
- Conversation history persistence to disk. Today history is in-memory per WebSocket connection; this spec keeps it that way. **See §9 — flagged for future work.**
- Conversation summarization. Outside this scope.
- Integration of the wiki/schema MCP server (`mcp-stardewvalley`). Originally planned as Phase 4 but deprioritized in favor of live state injection per the user's redirection.

## 2. Architecture

The Phase 3 architecture is unchanged. Mod still talks to bridge over WebSocket; bridge still calls DeepSeek. The only structural change: the `npc_interact` payload grows an optional `state` field, and a new `mod/Game/StateCollector.cs` class produces it on the main thread before each send.

```
NPC click in game
   ↓
NpcCheckActionPatch.Prefix
   ├─ Context.IsWorldReady & bridge connected?  (Phase 3 logic)
   ├─ NEW: var state = StateCollector.Collect();
   ├─ bridge.SendNpcInteract(npc, player, location, state)
   └─ register inflight, show placeholder

Bridge handle_client
   ├─ parse_message → NpcInteract (now with optional .state)
   ├─ append synthetic "(player approaches)" + assistant turns to history
   ├─ trim history to last 10 turns
   └─ llm.reply(... state=msg.state)
        ├─ build_messages: system + state block + history + user
        └─ DeepSeek → reply text
```

**Two invariants preserved from Phase 3:**
1. State collection is best-effort. If `StateCollector.Collect()` throws or returns null, the bridge sees `state=None` and falls back to the same prompt shape as Phase 3. NPC dialogue continues to work. **State is a flavor enhancer, never a blocker.**
2. Bridge unreachable → mod falls back to native dialogue (unchanged).

## 3. Wire Protocol Change

### `npc_interact` gets one new optional field

```json
{ "type": "npc_interact", "v": 1, "id": "...", "npc": "Robin",
  "player": "Alex", "location": "Town", "ts": 1234,
  "state": {
    "date": { "year": 2, "season": "fall", "day": 12, "dayOfWeek": "Mon" },
    "weather": "rainy",
    "spouse": "Sebastian",
    "activeQuests": ["Bouncer", "Robin's Lost Axe"]
  }
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `state` | object \| absent | Whole block is optional. Old mod / new bridge: bridge ignores absence. New mod / old bridge: old bridge ignores unknown field. |
| `state.date.year` | int | `Game1.year` (1-indexed in SDV). |
| `state.date.season` | string | One of `"spring"`, `"summer"`, `"fall"`, `"winter"`. Lowercase. |
| `state.date.day` | int | 1–28. |
| `state.date.dayOfWeek` | string | `"Mon"` / `"Tue"` / ... / `"Sun"`. SDV's day-of-month modulo 7 mapped to weekdays starting with Mon=1. |
| `state.weather` | string | One of `"sunny"`, `"rainy"`, `"snowy"`, `"stormy"`. Windy/debris weather is folded into `sunny`. Festivals also report `sunny` unless a precipitation flag overrides. |
| `state.spouse` | string \| null | NPC name (`"Sebastian"`) when married; `null` otherwise. |
| `state.activeQuests` | string[] | Up to 5 quest titles in the order returned by `Game1.player.questLog` (which is the order they were accepted). Bridge re-trims to 5 defensively. |

### No version bump
`v` stays `1`. Adding optional fields is non-breaking; either side ignores what it doesn't understand. This matches the protocol rule already established in §5 of the Phase 3 spec ("Unknown `type`: log and ignore on both sides; **do not** close the connection").

### Weather mapping (mod-side)
Reading SDV flags in this priority:
```csharp
if (Game1.isLightning)  return "stormy";
if (Game1.isRaining)    return "rainy";
if (Game1.isSnowing)    return "snowy";
return "sunny";   // includes debris weather, festivals, indoor scenes
```

## 4. Mod Side

### New file: `mod/Game/StateCollector.cs`

A new top-level directory `Game/` keeps state-collection separate from `Net/` (network) and `Patches/` (Harmony). The class is static, side-effect free, called only from the Harmony prefix on the main thread.

```csharp
namespace StardewAiMod.Game
{
    public static class StateCollector
    {
        public static GameState? Collect();   // returns null if IsWorldReady is false or anything throws
    }
}
```

Internal logic:
- Guard: `if (!Context.IsWorldReady) return null;`
- Wrap the whole body in `try/catch (Exception ex)` → log Trace → return null. SDV API can throw at scene boundaries (saving, festival transitions); we never want NPC dialogue to break because of it.
- Build `GameDate { Year, Season, Day, DayOfWeek }` from `Game1.year`, `Game1.currentSeason`, `Game1.dayOfMonth`. Day-of-week from `(Game1.dayOfMonth - 1) % 7` mapped to a string.
- Build weather string per the priority table in §3.
- Read `Game1.player.spouse` (string, may be null/empty → return null in JSON).
- Take up to 5 entries from `Game1.player.questLog`, project to `quest.questTitle`, build `string[]`.

### Modified file: `mod/Net/Messages.cs`

Add two records and one optional member:

```csharp
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
```

`NpcInteract` gains a trailing optional member:
```csharp
public record NpcInteract(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("npc")] string Npc,
    [property: JsonPropertyName("player")] string Player,
    [property: JsonPropertyName("location")] string Location,
    [property: JsonPropertyName("ts")] long Ts,
    [property: JsonPropertyName("state")] GameState? State        // ← new
)
{ ... }
```

`System.Text.Json` will omit `null` GameState by default (when configured with `DefaultIgnoreCondition = WhenWritingNull`); to keep behavior simple we explicitly serialize without that option, so `state: null` will appear on the wire when collection fails. The bridge accepts both shapes (absent or null), so no compatibility concern.

### Modified file: `mod/Net/BridgeClient.cs`

`SendNpcInteract` gains a parameter:
```csharp
public string? SendNpcInteract(string npcName, string playerName, string location, GameState? state)
```
Body change is one line — pass `state` to the `NpcInteract` constructor.

### Modified file: `mod/Patches/NpcCheckActionPatch.cs`

Two-line change inside `Prefix`, before calling `bridge.SendNpcInteract`:
```csharp
var state = StateCollector.Collect();   // null on failure
var id = bridge.SendNpcInteract(__instance.Name, who.Name, l?.Name ?? "Unknown", state);
```

The patch does NOT log on `state == null` — that path is the silent-fallback contract. `StateCollector.Collect` itself logs at Trace if it caught an exception.

### Estimated change size (mod)

| File | Operation | Lines |
|---|---|---|
| `mod/Game/StateCollector.cs` | New | ~50 |
| `mod/Net/Messages.cs` | Add 2 records + extend 1 | ~15 |
| `mod/Net/BridgeClient.cs` | Extend signature + pass-through | ~3 |
| `mod/Patches/NpcCheckActionPatch.cs` | Add 1 line | ~2 |
| **Total** | | **~70** |

## 5. Bridge Side

### Modified file: `bridge/bridge/protocol.py`

Add two pydantic models and extend `NpcInteract`:

```python
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
    state: Optional[GameState] = None     # ← new, optional
```

`parse_message` is unchanged — pydantic's existing validation handles the new field automatically; if `state` is malformed, the whole `NpcInteract` fails to validate and the message is soft-ignored, exactly like Phase 3.

### Modified file: `bridge/bridge/llm.py`

#### 5.1 New: state-block formatter
```python
def _format_state_block(state: dict | None) -> str | None:
    if state is None:
        return None
    lines = ["Current game state:"]
    d = state["date"]
    lines.append(f"- Date: {d['season'].capitalize()} {d['day']}, year {d['year']} ({d['dayOfWeek']})")
    lines.append(f"- Weather: {state['weather']}")
    if state.get("spouse"):
        lines.append(f"- Player's spouse: {state['spouse']}")
    quests = state.get("activeQuests") or []
    quests = quests[:5]                   # defensive: re-trim in case mod sent more
    if quests:
        lines.append(f"- Active quests: {', '.join(quests)}")
    return "\n".join(lines)
```
- Spouse and quests lines are **omitted entirely** when null/empty (avoids feeding the model "Player's spouse: None" or "Active quests: ").
- Returns `None` when no state — caller skips the whole block.

#### 5.2 Modified: `build_messages`
```python
HISTORY_MAX_TURNS = 10            # 5 exchanges
PLAYER_APPROACH_MARKER = "(player approaches)"

def build_messages(npc_name, player_name, location, history, user_text, state=None):
    system = (
        f"You are {npc_name} from Stardew Valley. "
        f"The player {player_name} just talked to you in {location}. "
        f"Reply in 1-2 short sentences, in character, in English."
    )
    msgs = [{"role": "system", "content": system}]

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
```

The loop trusts whatever text is stored — the substitution from empty string to the synthetic marker happens once at **write** time (in `server.py`, see 5.3) so the in-memory history is already canonical. `build_messages` does the same substitution for the **current** user turn since `user_text` is still passed by the server as `""` (Phase 3 limit; player free-text input is future work).

#### 5.3 Modified: `reply`
Adds an optional `state=None` parameter and passes it through to `build_messages`. No other change.

### Modified file: `bridge/bridge/server.py`

Two-line change in `_make_handler`'s inner `handler`:
```python
text = await llm_mod.reply(
    client=client,
    npc_name=msg.npc,
    player_name=msg.player,
    location=msg.location,
    history=history.get(msg.npc, []),
    user_text="",                                       # unchanged
    state=msg.state.model_dump() if msg.state else None,    # ← new
)
```

Also, change the recorded user turn from empty string to the synthetic marker. This makes history canonical at write-time so the read path doesn't need any conditional logic, and log dumps are immediately readable:
```python
history.setdefault(msg.npc, []).append(
    {"role": "user", "text": llm_mod.PLAYER_APPROACH_MARKER}    # was ""
)
```

History trim happens **inside `build_messages`** (read-time), not on append (write-time). This way the in-memory list grows linearly during a session and we don't lose ground-truth on what was said; only the prompt-facing slice is trimmed. Memory cost is trivial (a click is at most a few hundred bytes; even thousands would fit in MB).

### Estimated change size (bridge)

| File | Operation | Lines |
|---|---|---|
| `bridge/bridge/protocol.py` | Add 2 model + extend 1 field | ~15 |
| `bridge/bridge/llm.py` | New formatter + extend 2 funcs | ~30 |
| `bridge/bridge/server.py` | Pass-through + marker | ~3 |
| `bridge/tests/test_protocol.py` | Add state round-trip tests | ~25 |
| `bridge/tests/test_llm.py` | Add state-injection tests | ~40 |
| **Total** | | **~115** |

## 6. Lifecycle & Error Handling

This section only describes **delta from Phase 3 §7**. Everything else is unchanged.

### State collection failure path

| Scenario | Mod behavior | Bridge behavior | Player sees |
|---|---|---|---|
| `StateCollector.Collect()` throws | Catches, logs Trace, returns null | `state=None` → no state block in prompt | Phase 3-style reply (no state references), conversation works |
| `StateCollector.Collect()` returns valid object but with null spouse / empty quests | Sends as-is | Conditional formatter skips those lines | Reply free of "spouse: None" artifacts |
| Mod sends `state` with > 5 quests | Mod already trims to 5, but bridge re-trims defensively | OK | OK |
| Mod sends `state` with bogus weather string (e.g. `"freezing"`) | n/a (mod produces only the 4 enum values) | Pydantic accepts (`weather: str`); LLM sees the bogus value but won't break; could be confusing | Acceptable risk (mod is the only producer; this is a defensive note, not a needed feature) |
| Bridge sees malformed `state` (wrong type, missing required field) | n/a | `parse_message` returns None → whole `NpcInteract` is dropped via existing soft-fail path | NPC will fall back to native dialogue (since the click was never delivered to the handler). **Same shape as a malformed message in Phase 3.** |

### Conversation history lifecycle (behavior summary)

History is purely in-memory in `_handle_client`'s local `history` dict. Cleared on:
- Bridge process exit (Ctrl+C, crash, restart).
- WebSocket disconnect (game close, network blip → mod reconnects with fresh handler instance).
- `session_reset` message from mod (player returns to title).
- New WebSocket connection always starts with empty history.

This is unchanged from Phase 3 — we are not adding persistence in this spec. **Future work; see §9.**

## 7. Testing

### Bridge — automated (TDD where it pays)

`tests/test_protocol.py` adds:
- `test_npc_interact_with_state_roundtrip`: full state → JSON → back → all fields equal.
- `test_npc_interact_no_state_roundtrip`: state omitted → parses fine, `state` is `None` (regression guard for backward compat).

`tests/test_llm.py` adds:
- `test_build_messages_injects_state_block`: pass a state dict → second message has role `user` and contains "Current game state:" plus all field values.
- `test_build_messages_omits_spouse_when_null`: spouse=None → output does not contain "Player's spouse:".
- `test_build_messages_omits_quests_when_empty`: activeQuests=[] → output does not contain "Active quests:".
- `test_build_messages_no_state`: state=None → output equals Phase 3 baseline (no state block at all).
- `test_build_messages_user_text_empty_uses_marker`: pass `user_text=""` → final user message content equals `(player approaches)` (write-time canonicalization happens in server.py; read-time canonicalization for the live click happens here).
- `test_build_messages_passes_marker_user_turns_through`: history has a user turn whose text is `(player approaches)` → message content equals that string verbatim (regression guard against accidental substitution).
- `test_build_messages_trims_history_to_last_10`: history has 20 turns → emitted history (between system/state and final user) has exactly 10 turns, and they are the last 10.

### Mod — manual (no xUnit, same rationale as Phase 3)

| # | Action | Expected |
|---|---|---|
| 1 | Run bridge with `--debug`, launch game | Bridge log shows `npc_interact` JSON with a `state` object on every click |
| 2 | Click NPC during rain | Reply naturally references the rain (not generic) |
| 3 | Click NPC after marrying Sebastian | Some replies acknowledge spouse |
| 4 | Click NPC while a quest is in the log | Replies may reference an active quest by name |
| 5 | Bridge running, then game restart (without bridge restart) | New session starts with empty history (no leakage from previous game session) |
| 6 | Force-empty case: brand new save, no spouse, no quests | State block appears with only date + weather; reply is sensible |
| 7 | Click same NPC 3 times in a row | Replies reference each other ("As I was saying...") — confirms the synthetic marker fix |
| 8 | Bridge off | Native dialogue (Phase 3 fallback unchanged) |

### Out of scope for testing today

- Mod-side xUnit tests for `StateCollector` (Phase 3 reasoning still applies — mocking `Game1` static state is not worth the cost).
- A "force-throw" automated test for `Collect()` failure path. The same fallback is exercised by `state=None` in `test_build_messages_no_state`; the C# try/catch is small and inspection-clear.

## 8. Decisions & Rationale

- **Optional `state` field, no version bump.** Pure addition; clean both-direction compatibility. Matches the soft-fail philosophy already in the protocol.
- **Mod gathers structured fields; bridge formats prompt.** Prompt iteration speed is the main lever in conversational quality work; keeping the formatter in Python preserves the "restart bridge in 1 second, restart game in 30" gap that made Phase 3 development fast.
- **State block as a separate `user` role message** rather than glued onto the system prompt. Three reasons: easier to log/debug ("did the LLM actually receive today's weather?"); easier to extend with new fields without rewriting English; LLMs handle structured bullet lists more reliably than long sentences for factual context.
- **Synthetic marker `(player approaches)` instead of empty user turn.** OpenAI/DeepSeek expect `user` and `assistant` content; empty content makes the model think the user is being weird and produces repetitive openers. The marker tells the model "the player is here again, react to that."
- **History trim at read-time, not write-time.** Keeps the in-memory history complete (cheap) so we can later add summarization without losing ground truth; only the LLM-bound slice is bounded.
- **`HISTORY_MAX_TURNS = 10`.** 5 exchanges is enough for short NPC conversations; 10 turns is comfortably under any token limit. If conversational depth proves to want more, raising the cap is one number.
- **Static silent fallback on state-collect failure.** Per the user's preference: don't add Warn-level noise to SMAPI console for an internal best-effort path; it would create alert fatigue. The Trace-level log is preserved for debugging.

## 9. Open Questions / Future Work

- **History persistence to disk.** Today history dies on any disconnect. The user's gameplay assumption ("Robin remembers our conversation last week") will break across sessions. Add when prompt design has stabilized — likely 1 week of in-use iteration. Implementation sketch: write `bridge/.history.json` keyed by `(player_name, npc_name)`, load on connection, save on each turn or on `session_reset`. Estimated 30–50 lines plus 1 test. **Explicitly deferred from this spec.**
- **Conversation summarization.** When history hits N turns, summarize the oldest portion into a single "Earlier you talked about X" line, drop the raw turns. Useful only after persistence makes long conversations actually long. Adds an extra LLM call per overflow, with its own failure modes.
- **Player free-text input.** A chat UI inside the mod that captures actual player text and sends it as `user_text`. Major UX upgrade but requires a custom IClickableMenu / text input box. Separate spec.
- **NPC-side state (the "rich" tier).** NPC's current map location, mood, friendship score, gift preference table. Builds on this spec; requires reading more SDV API surface.
- **MCP wiki integration (originally Phase 4).** Not abandoned, but moved behind state injection per the user's redirection. Most useful once the structured-state pattern is in place — wiki facts can become a tool the LLM calls when it needs them, rather than always-on context.
