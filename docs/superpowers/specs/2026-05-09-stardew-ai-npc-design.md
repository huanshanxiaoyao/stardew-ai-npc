# Stardew Valley AI NPC — Design Spec

- **Date**: 2026-05-09
- **Status**: Approved (pending user spec review)
- **Author**: Brainstorming session (Claude + user)
- **Repo (planned)**: `~/workspace/hermes/stardew_valley_with_ai/` (separate GitHub repo, to be linked later)

## 1. Goal & Non-goals

### Goal
Replace the native dialogue of Stardew Valley NPCs with AI-generated replies. The player presses the action button on any NPC; instead of the canned in-game dialogue, the NPC answers via DeepSeek through a local Python bridge. The work is staged in four phases; this spec covers Phases 1–3 in full and reserves Phase 4 (MCP integration) for a later round of brainstorming.

### Non-goals (this spec)
- Changing NPC behavior in the world (movement, gifting, quests). The original `start.txt` lists this as an optional Phase 2 of the larger product; for engineering purposes it is **out of scope** for this spec.
- Multiplayer support.
- Persisting conversation history across game restarts.
- Running on Windows or Linux. macOS only for now (the user's environment).
- Token-by-token streaming UI inside the game's `DialogueBox`.

## 2. Architecture

```
Stardew Valley (game process)
  └─ SMAPI mod loader
       └─ AI Mod (C#)
            ├─ Harmony patch on NPC.checkAction
            ├─ BridgeClient: long-lived WebSocket client
            └─ Renders replies via Game1.activeClickableMenu = new DialogueBox(...)
                          ▲
                          │ ws://127.0.0.1:8765   JSON
                          ▼
       Python Bridge (separate process, asyncio)
            ├─ websockets server
            ├─ Per-connection conversation history (in-memory)
            ├─ Phase 2: echo
            ├─ Phase 3: DeepSeek (OpenAI-compatible API)
            └─ Phase 4 (later): MCP client → mcp-stardewvalley
```

**Process topology at runtime**

| Process | Launch | I/O |
|---|---|---|
| Stardew Valley + SMAPI + AI Mod | Steam | Outbound WebSocket to `ws://127.0.0.1:8765` |
| Python Bridge | `./scripts/run_bridge.sh` in a terminal | Listens on `127.0.0.1:8765` |
| DeepSeek API | Remote | Outbound HTTPS from bridge (Phase 3+) |
| `mcp-stardewvalley` | `dotnet run --project src/McpServer.Api` (Phase 4 only) | Local HTTP, called by bridge |

**Two load-bearing invariants**
1. The mod opens **one** long-lived WebSocket connection. On disconnect it reconnects with exponential backoff (1s, 2s, 4s, 8s, capped at 10s). The mod never blocks the game on a connection attempt.
2. When the bridge is unreachable, the mod falls back to native Stardew dialogue. AI being offline degrades gracefully to vanilla Stardew, never to a broken game.

## 3. Repository Layout

```
stardew_valley_with_ai/
├── README.md
├── .gitignore                 # bin/ obj/ __pycache__/ .env
├── mod/                       # SMAPI mod, C# project
│   ├── StardewAiMod.csproj
│   ├── ModEntry.cs
│   ├── Patches/
│   │   └── NpcCheckActionPatch.cs
│   ├── Net/
│   │   └── BridgeClient.cs
│   ├── manifest.json
│   └── README.md
├── bridge/                    # Python bridge service
│   ├── pyproject.toml         # deps: websockets, openai, pydantic, python-dotenv
│   ├── bridge/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── protocol.py
│   │   ├── llm.py             # added in Phase 3
│   │   └── mcp_client.py      # placeholder for Phase 4 (TODO)
│   ├── tests/
│   │   ├── test_protocol.py
│   │   └── test_echo_roundtrip.py
│   ├── .env.example           # DEEPSEEK_API_KEY=
│   └── README.md
├── docs/
│   └── superpowers/specs/
│       └── 2026-05-09-stardew-ai-npc-design.md   # this file
└── scripts/
    ├── install_mod.sh         # build mod, copy artifacts to SMAPI Mods folder
    └── run_bridge.sh          # load .env, start the bridge
```

**SMAPI Mods install path on this machine**:
`~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/StardewAiMod/`

## 4. Components

### 4.1 Mod side (C#)

**`ModEntry : Mod`** — SMAPI entry point.
- On `Entry`: initialize Harmony (`new Harmony("local.StardewAiMod").PatchAll()`), construct `BridgeClient`, start it.
- Subscribes to `GameLoop.UpdateTicked` and to `GameLoop.ReturnedToTitle`.
- The `UpdateTicked` handler drains a thread-safe reply queue from `BridgeClient` and renders replies on the main thread (Stardew is not thread-safe; all UI calls must run on the main thread).
- The `ReturnedToTitle` handler clears in-flight state and sends `session_reset` to the bridge.

**`NpcCheckActionPatch`** — Harmony **Prefix** on `NPC.checkAction(Farmer who, GameLocation l)`.
- Guards: only intervene when `Context.IsWorldReady` is true.
- If `BridgeClient.IsConnected` is false → return `true` (let native dialogue run).
- If true → set `Game1.activeClickableMenu = new DialogueBox("...")` as an immediate placeholder, send `npc_interact`, register the request id as in-flight, and return `false` to suppress native dialogue.
- Debounce: if the same NPC has an in-flight request, ignore the second click for 1 second.

**`BridgeClient`** — WebSocket connection manager.
- Public surface (kept minimal):
  - `bool IsConnected { get; }`
  - `void Start()` — start the connect/reconnect loop on a background `Task`.
  - `Guid SendNpcInteract(string npcName, string playerName, string location)` — returns the request id.
  - `void SendSessionReset(string reason)`
  - `event Action<NpcReply> OnReply` — fired from the receive loop; `OnReply` handlers must enqueue, not touch `Game1` directly.
- Internals: `System.Net.WebSockets.ClientWebSocket` (no third-party dependency), exponential reconnect, per-message JSON parse, log-and-ignore on unknown `type`.
- All logs go through SMAPI's `Monitor.Log`.

### 4.2 Bridge side (Python)

**`bridge.server`** — process entry (`python -m bridge.server`).
- Starts `websockets.serve("127.0.0.1", 8765)`.
- Per connection runs `handle_client(ws)`: a `recv → dispatch → send` coroutine.
- Holds `history: dict[npc_name, list[turn]]` scoped to the connection. Connection closed → history dropped.
- Dispatch table:
  - `npc_interact` → Phase 2: echo `"You clicked {npc}"`. Phase 3: `await llm.reply(...)`. Phase 4: optionally pre-call `mcp_client`.
  - `session_reset` → clear `history`.
  - Unknown `type` → `log + ignore` (do not close the socket).

**`bridge.protocol`** — single source of truth for the wire format.
- Pydantic v2 models for each message type (`NpcInteract`, `NpcReply`, `SessionReset`, `ErrorMsg`).
- Unknown `type` parses to `None` (or raises a specific exception caught by the dispatcher).
- The C# mod hand-codes matching records; no schema generator is used (keeps the moving parts small).

**`bridge.llm`** (Phase 3+) — DeepSeek call wrapper.
- `async def reply(npc_name: str, history: list[dict], player_name: str, location: str) -> str`
- Uses the `openai` SDK with `base_url="https://api.deepseek.com"`, `model="deepseek-chat"`, `api_key=os.getenv("DEEPSEEK_API_KEY")`, request timeout 8 seconds.
- System prompt v1:
  > `You are {npc_name} from Stardew Valley. The player {player_name} just talked to you in {location}. Reply in 1-2 short sentences, in character, in English.`
- On error or timeout, returns the fallback string `"(NPC seems lost in thought.)"`. Errors are logged but not propagated to the client as exceptions; the client receives a normal `npc_reply` with the fallback text. This keeps the protocol single-shape per click.

**`bridge.mcp_client`** (Phase 4 placeholder) — empty module with a `# TODO: phase 4` comment. Not implemented in this spec.

## 5. Wire Protocol (JSON over WebSocket, v1)

All messages are UTF-8 JSON text frames.

**Client → Server: `npc_interact`**
```json
{ "type": "npc_interact",
  "v": 1,
  "id": "uuid-string",
  "npc": "Robin",
  "player": "Alex",
  "location": "Town",
  "ts": 1715251200 }
```

**Server → Client: `npc_reply`**
```json
{ "type": "npc_reply",
  "v": 1,
  "id": "uuid-string",
  "npc": "Robin",
  "text": "Hey Alex, ...",
  "done": true }
```
Today `done` is always `true` (no streaming). The field is reserved so a later version can ship partial chunks without a v2 bump.

**Client → Server: `session_reset`**
```json
{ "type": "session_reset", "v": 1, "reason": "returned_to_title" }
```
Sent when the player returns to the title menu. The bridge clears the connection's history. (Note: this message has no `id` field — it is fire-and-forget and does not produce a reply.)

**Either direction: `error`**
```json
{ "type": "error",
  "v": 1,
  "id": "uuid-string|null",
  "code": "llm_timeout | bad_request | internal",
  "message": "human-readable" }
```

**Hard rules**
- The `id` of a `npc_reply` must equal the `id` of the originating `npc_interact`.
- Unknown `type`: log and ignore on both sides; **do not** close the connection.
- Version field `v` is `1` today. A breaking change increments to `2`; old clients receiving `v=2` log and discard.

## 6. Data Flow

A successful click → reply round-trip:

1. Player presses the action button on an NPC.
2. `NPC.checkAction` runs; the Harmony prefix fires.
3. The prefix checks `Context.IsWorldReady` and `BridgeClient.IsConnected`. Both true → it sets a `"..."` placeholder dialogue, calls `BridgeClient.SendNpcInteract`, marks the id as in-flight, returns `false`.
4. `BridgeClient` serializes `npc_interact` to JSON and sends it on the WebSocket.
5. The bridge `handle_client` coroutine receives the message, parses it, appends a user turn to `history[npc]`, calls the active reply strategy (echo / LLM / LLM+MCP), appends an assistant turn to history, sends `npc_reply`.
6. `BridgeClient` receives `npc_reply` on its receive task and enqueues an `NpcReply` object.
7. On the next `UpdateTicked` (main thread), `ModEntry` drains the queue. For each reply: if the id is still in-flight (not cancelled, not timed out), it replaces the active `DialogueBox` with one containing `text`. If the id was cancelled or already timed out, the reply is discarded.

## 7. Lifecycle & Error Handling

### Startup ordering
The components may start in any order. Recommended order is `bridge → game` (so the first NPC click already goes through AI), but the mod tolerates either.

### Failure scenarios

| Scenario | Player sees | Mod | Bridge |
|---|---|---|---|
| Bridge not running at game start | Native dialogue (vanilla) | Background reconnect, 1→2→4→8→10s cap | — |
| Bridge crashes mid-game | Next click → native dialogue | `IsConnected=false`; in-flight ids hit the 12s timeout fallback | — |
| Single LLM call times out (>8s in `llm.reply`, or >12s end-to-end on mod side) | `"…(NPC didn't speak)"` placeholder closes after 12s | Drops late replies for that id | Logs `llm_timeout` |
| LLM returns 4xx/5xx | Fallback line `"(NPC seems lost in thought.)"` | Same | Logs the error |
| Player dismisses the placeholder while waiting (closes dialogue, returns to title, etc.) | Placeholder closes; late reply discarded | Watches `Game1.activeClickableMenu`; if it is no longer our placeholder, mark the id in `cancelledIds` | — |
| Same NPC clicked again while in-flight | Second click ignored for 1s | `inflightNpc` set | — |
| Malformed JSON over the socket | — | Log + ignore | Log + ignore |
| Action button pressed at title screen | Native game behavior | Patch's `IsWorldReady` guard short-circuits | — |

### Resource lifecycle
- **Mod `Entry`**: starts Harmony, starts `BridgeClient` background task.
- **`ReturnedToTitle`**: clears in-flight id sets, sends `session_reset`.
- **Game exit**: SMAPI unloads the mod; `BridgeClient`'s cancellation token closes the socket cleanly.
- **Bridge SIGINT/SIGTERM**: closes the server, closes all connections, exits. No graceful drain — history is ephemeral.
- **Bridge connection close (single client)**: history for that connection is dropped.

### Logging
- **Mod**: `Monitor.Log` at `Trace/Debug/Info/Warn/Error`. Default `Info`. All log lines that correspond to a request include the request `id`.
- **Bridge**: Python `logging`, default `INFO`, `--debug` flag bumps to `DEBUG`, output to stdout. Same id convention.

## 8. Phases & Acceptance Criteria

Each phase has criteria that are **observable in the running game or terminal**, not "code merged".

### Phase 1 — Game-internal Hello World (C# only)
**Goal**: pressing the action button on any NPC opens a custom dialogue with `"Hello from AI Mod!"` instead of native dialogue.

**Implementation**
- Create `mod/StardewAiMod.csproj` (target `net6.0`), reference `Pathoschild.Stardew.ModBuildConfig` via NuGet (handles SMAPI assembly resolution automatically).
- `manifest.json` with `UniqueID=local.StardewAiMod`, minimum SMAPI version.
- `ModEntry.Entry` calls `new Harmony("local.StardewAiMod").PatchAll()`.
- `NpcCheckActionPatch` is a Prefix on `NPC.checkAction(Farmer, GameLocation)`; gate with `Context.IsWorldReady`; set `Game1.activeClickableMenu = new DialogueBox("Hello from AI Mod!")`; return `false`.
- `scripts/install_mod.sh`: `dotnet build`, then copy `bin/Debug/net6.0/StardewAiMod.dll` and `manifest.json` to the SMAPI `Mods/StardewAiMod/` folder.

**Acceptance**
1. SMAPI console at game start shows `Loaded mod StardewAiMod`.
2. In-game, pressing the action button on Robin opens a dialogue with `"Hello from AI Mod!"`.
3. Closing the dialogue does **not** trigger a native dialogue afterwards (confirms prefix suppression works).
4. Pressing the action button on the title screen does not throw (confirms `IsWorldReady` guard works).

### Phase 2 — Cross-process IPC (C# ⇄ Python)
**Goal**: clicking an NPC prints the `npc_interact` JSON in the bridge terminal; the bridge echoes back, and the echo appears as the in-game NPC dialogue.

**Implementation**
- Mod adds `Net/BridgeClient.cs` (`ClientWebSocket` + reconnect task + thread-safe reply queue); `ModEntry` subscribes to `UpdateTicked` to drain the queue and render replies on the main thread.
- Patch logic now: send `npc_interact` → show `"..."` placeholder → on reply, replace the placeholder with the reply text.
- `bridge/bridge/server.py`: `websockets.serve` + `handle_client` echo loop.
- `bridge/bridge/protocol.py`: pydantic models matching §5.
- `bridge/tests/test_protocol.py`: round-trip serialization tests (the only mandatory unit test).

**Acceptance**
1. Game running, bridge **not** started → click NPC → native dialogue (graceful degradation).
2. Bridge started → terminal prints `Player clicked Robin` (with id, location).
3. Click NPC → `"..."` shown first, then replaced within ~1s by `"You clicked Robin"`.
4. `Ctrl+C` the bridge mid-session → next click goes to native dialogue; restart bridge → AI path resumes without restarting the game.
5. Player dismisses the placeholder while waiting → placeholder closes; the late reply is discarded (verify in SMAPI log).

### Phase 3 — DeepSeek integration (today: optional, after Phase 1+2)
**Goal**: NPC replies are produced by DeepSeek with a hardcoded system prompt.

**Implementation**
- `bridge/bridge/llm.py` per §4.2.
- `handle_client` replaces echo with `await llm.reply(...)`; per-NPC history kept in memory for the connection.
- `.env.example` → `DEEPSEEK_API_KEY=`. `.env` is gitignored.

**Acceptance**
1. Click Robin → an English, in-character, 1–2-sentence reply (not the echo).
2. Continued conversation has context (e.g., follow-up references the previous turn).
3. Set the API key to garbage → `"(NPC seems lost in thought.)"` appears, game does not crash.
4. Disconnect from network → after the timeout, the timeout fallback line appears.

### Phase 4 — MCP integration (out of scope for today)
A `mcp_client.py` placeholder file is created with a `# TODO: phase 4` comment. The full design will be done in a separate brainstorming session after Phase 3 is running.

### Today's "done" definition

| Floor (must) | Target | Stretch |
|---|---|---|
| Phase 1 + Phase 2 acceptance criteria all green | + Phase 3 acceptance #1 green | Phase 3 all green |

If Phase 1 stalls in Harmony for >90 minutes, **fork the work**: get the bridge running standalone (testable with `wscat`) so the C# side can be debugged in isolation.

## 9. Testing Strategy

| Layer | Where | What | Tools |
|---|---|---|---|
| Unit | Bridge | Protocol schema round-trip, prompt assembly | `pytest` |
| Integration | Bridge | Server + fake client, full echo / LLM path | `pytest` + `websockets` |
| End-to-end | Manual | The acceptance criteria in §8 | Human + logs |

**Bridge unit test (mandatory today)**: `bridge/tests/test_protocol.py` covers `npc_interact` and `npc_reply` JSON round-trips and unknown-`type` soft-failure.

**Bridge integration test (mandatory today)**: `bridge/tests/test_echo_roundtrip.py` starts the server on an ephemeral port, sends an `npc_interact`, asserts the echoed `npc_reply` carries the same `id`. Phase 3 will retarget this test against a mocked LLM client.

**Mod-side automated tests are deliberately omitted today.** Mocking `Game1` static state would cost more than writing the mod itself; the mod has only ~3 meaningful branches (connected / not connected / timeout) and is faster to validate by hand against the §8 acceptance lists. If the mod grows past ~500 lines, extract pure logic into `Game1`-free classes and add xUnit tests then.

**Out of scope today**: GitHub Actions CI; mypy/ruff configuration; load testing.

## 10. Decisions Made & Rationale

- **Approach A (out-of-process bridge over WebSocket)** chosen over an in-mod HTTP client (Approach B) and a stdio subprocess (Approach C). Reason: dev-loop speed during prompt iteration in Phase 3 — bridge restart (Ctrl+C) is seconds, mod restart requires a full game restart.
- **Python over Node.js** for the bridge: marginally better LLM/MCP ecosystem, user familiarity, no real downside at this scale.
- **No conversation persistence**: aligns with fast iteration; reset on bridge restart or player return-to-title.
- **No streaming UI**: Stardew's `DialogueBox` is not a streaming widget; segmenting per sentence is doable later if the latency UX warrants it.
- **No auth, no TLS**: bind to `127.0.0.1` only, single-user local environment.
- **Hand-written C# message records**, not codegen: protocol surface is tiny (4 message types); a generator is more moving parts than it saves.
- **`session_reset` is fire-and-forget** (no `id`, no reply). It is the only message in the protocol without an `id`; this is intentional to keep the request/reply correlation rule simple for messages that have one.
- **Fallback strings for LLM failure are returned as normal `npc_reply` messages**, not `error` messages. Reason: keeps the mod's main path single-shape per click; the `error` message type is reserved for protocol-level problems (malformed payload, internal server fault before any reply could be produced).

## 11. Open Questions / Future Work

- **Phase 4 (MCP)**: deferred to a later brainstorming session.
- **NPC behavior changes** (the optional second goal in `start.txt`, e.g. "go pick two red berries"): out of scope; would require a separate spec covering tool calls and game-state mutation.
- **Streaming partial replies**: the protocol has a `done` field already; revisit if reply latency makes the placeholder feel laggy.
- **Localization**: today the prompt and fallbacks are English only (matches the user's English game install).
