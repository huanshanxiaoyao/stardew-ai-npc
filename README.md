# Stardew Valley AI NPC

Replaces native Stardew Valley NPC dialogue with AI-generated replies. NPCs answer in character, with awareness of the current in-game date, weather, your spouse, and your active quests.

## Status

**v1 shipped.** A SMAPI mod intercepts NPC interactions and forwards them over WebSocket to a local Python bridge. The bridge calls DeepSeek (OpenAI-compatible API) and returns a 1–2 sentence in-character reply. The mod renders the reply in Stardew's native dialogue UI.

If the bridge isn't running, the mod silently falls back to vanilla dialogue — AI being offline never breaks the game.

## Tested with

- macOS 14.6+ on Apple Silicon
- Stardew Valley 1.6.15 + SMAPI 4.5.2 + .NET 6.0.32 runtime
- Python 3.11

Windows and Linux are not yet supported (pull requests welcome).

## Quick start (developers)

Assumes you already have SMAPI, .NET 6 SDK, Python 3.11, and a DeepSeek API key.

```bash
# 1. install dependencies
brew install dotnet@6 python@3.11

# 2. set up bridge
cd bridge
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# edit .env and set DEEPSEEK_API_KEY=...

# 3. build and install the mod (auto-deploys to your SMAPI Mods folder)
cd ..
./scripts/install_mod.sh

# 4. each time you play
./scripts/run_bridge.sh   # leave this terminal running
# then launch Stardew Valley via Steam
```

## For Stardew Valley fans (non-coders)

See **[docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md)** — a step-by-step guide written for players who haven't used Terminal or Git before.

## Architecture

```
Stardew Valley + SMAPI
        │
        │  Harmony patch on NPC.checkAction
        ▼
  AI Mod (C#)  ────WebSocket────▶  Python Bridge  ────HTTPS────▶  DeepSeek API
                JSON / port 8765      asyncio                    deepseek-chat
```

- **Mod** collects current game state (date, weather, spouse, active quests) on each NPC click and forwards via the bridge.
- **Bridge** assembles a system prompt + state block + conversation history (last 10 turns), calls DeepSeek, returns the reply.
- **Mod** displays the reply in a `DialogueBox`.

## Project layout

```
stardew_valley_with_ai/
├── mod/                       # SMAPI mod (C#)
│   ├── ModEntry.cs            # SMAPI entry; UpdateTicked drains reply queue
│   ├── Patches/               # Harmony patches (intercepts NPC.checkAction)
│   ├── Net/                   # WebSocket client + wire-protocol records
│   └── Game/                  # Reads SDV global state into JSON-friendly DTOs
├── bridge/                    # Python bridge
│   └── bridge/
│       ├── server.py          # asyncio websockets server
│       ├── protocol.py        # pydantic models, single source of truth for the wire
│       ├── llm.py             # DeepSeek wrapper, prompt assembly, history trim
│       └── mcp_client.py      # placeholder for future MCP integration
├── scripts/
│   ├── install_mod.sh         # build mod and copy to SMAPI Mods folder
│   └── run_bridge.sh          # start the bridge with .env loaded
└── docs/
    ├── SETUP-GUIDE.md         # non-coder setup guide
    └── superpowers/
        ├── specs/             # design specs
        └── plans/             # implementation plans
```

## Tech stack

- **Mod**: C# .NET 6, SMAPI 4, HarmonyLib, `System.Net.WebSockets`, `System.Text.Json`
- **Bridge**: Python 3.11, `websockets`, `pydantic` v2, `openai` SDK
- **LLM**: DeepSeek (`deepseek-chat`), via OpenAI-compatible base URL

## Design docs

- Phase 1–3 (chat foundation): [`docs/superpowers/specs/2026-05-09-stardew-ai-npc-design.md`](docs/superpowers/specs/2026-05-09-stardew-ai-npc-design.md)
- State injection: [`docs/superpowers/specs/2026-05-09-state-injection-design.md`](docs/superpowers/specs/2026-05-09-state-injection-design.md)
- Implementation plans: [`docs/superpowers/plans/`](docs/superpowers/plans/)

## What's not in v1

- Player free-text input (you can't type to the NPC; the LLM reacts to your approach + state)
- Conversation history persistence to disk (cleared on bridge restart or return-to-title)
- NPC-side state (NPC's mood, friendship score, current location)
- Wiki / lore lookup via MCP
- Windows / Linux support

These are tracked in the design specs' "future work" sections.
