# Stardew Valley AI NPC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace native Stardew Valley NPC dialogue with AI-generated replies via a SMAPI mod (C#) that talks over WebSocket to a Python bridge, which calls DeepSeek. Phases 1–3 from the spec are in scope; Phase 4 (MCP) is a placeholder file only.

**Architecture:** Out-of-process bridge: a SMAPI mod uses Harmony to intercept `NPC.checkAction` and forwards the click via a long-lived WebSocket to a Python `asyncio` server. The bridge produces a reply (echo → DeepSeek across phases) and the mod renders it via `Game1.activeClickableMenu = new DialogueBox(text)`. When the bridge is unreachable, the mod returns control to the native dialogue path.

**Tech Stack:**
- C# .NET 6, SMAPI 4.5.2, HarmonyLib (bundled by SMAPI), `System.Net.WebSockets.ClientWebSocket`
- Python 3.11+, `websockets`, `pydantic` v2, `openai` SDK (DeepSeek-compatible), `python-dotenv`, `pytest`
- Stardew Valley 1.6.15 on macOS, install path `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/`

**Reference spec:** `docs/superpowers/specs/2026-05-09-stardew-ai-npc-design.md`

---

## File Structure

```
stardew_valley_with_ai/
├── .gitignore                                    # already created
├── README.md                                     # Task 1
├── docs/superpowers/
│   ├── specs/2026-05-09-stardew-ai-npc-design.md # already exists
│   └── plans/2026-05-09-stardew-ai-npc.md        # this file
├── mod/
│   ├── StardewAiMod.csproj                       # Task 2
│   ├── manifest.json                             # Task 2
│   ├── ModEntry.cs                               # Task 3
│   ├── Patches/NpcCheckActionPatch.cs            # Task 5, extended in Task 14
│   └── Net/
│       ├── BridgeClient.cs                       # Tasks 10–12
│       └── Messages.cs                           # Task 10
├── bridge/
│   ├── pyproject.toml                            # Task 6
│   ├── .env.example                              # Task 6
│   ├── bridge/
│   │   ├── __init__.py                           # Task 6
│   │   ├── protocol.py                           # Task 7
│   │   ├── server.py                             # Task 8, extended in Tasks 15, 18
│   │   ├── llm.py                                # Task 17
│   │   └── mcp_client.py                         # Task 21 (stub)
│   └── tests/
│       ├── __init__.py                           # Task 6
│       ├── test_protocol.py                      # Task 7
│       ├── test_echo_roundtrip.py                # Task 8, retargeted in Task 19
│       └── test_llm.py                           # Task 17
└── scripts/
    ├── install_mod.sh                            # Task 2
    └── run_bridge.sh                             # Task 6
```

---

## Task 0: Verify .NET 6 SDK is available

**Files:** none (environment check)

- [ ] **Step 1: List installed SDKs**

Run:
```bash
dotnet --list-sdks
```

Expected: at least one `6.0.x` line. Example: `6.0.428 [/usr/local/share/dotnet/sdk]`.

- [ ] **Step 2: If no 6.0 SDK, install it**

If step 1 showed no 6.0 entry, install via Homebrew:
```bash
brew install --cask dotnet-sdk6
```

Or download the macOS arm64 / x64 installer from `https://dotnet.microsoft.com/download/dotnet/6.0`. Re-run `dotnet --list-sdks` to confirm.

> **Why:** Stardew Valley 1.6 runs on .NET 6.0.32 (we verified `Stardew Valley.runtimeconfig.json` shows `tfm: net6.0`). The mod must target `net6.0`, and building that target with only an SDK 10 install will fail when restoring the targeting pack offline.

---

## Task 1: Scaffold project root (README + docs)

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# Stardew Valley AI NPC

Replaces native Stardew Valley NPC dialogue with AI-generated replies via DeepSeek.

## Layout
- `mod/` — SMAPI mod (C#)
- `bridge/` — Python WebSocket bridge that talks to DeepSeek
- `scripts/` — install / run helpers
- `docs/superpowers/specs/` — design spec
- `docs/superpowers/plans/` — implementation plan

## Quick start
1. Build and install the mod: `./scripts/install_mod.sh`
2. Configure `bridge/.env` with `DEEPSEEK_API_KEY=...`
3. Start the bridge: `./scripts/run_bridge.sh`
4. Launch Stardew Valley via Steam.

When the bridge is unreachable the mod silently falls back to vanilla dialogue.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add project README"
```

---

## Task 2: Scaffold the C# mod project

**Files:**
- Create: `mod/StardewAiMod.csproj`
- Create: `mod/manifest.json`
- Create: `scripts/install_mod.sh`

- [ ] **Step 1: Write `mod/StardewAiMod.csproj`**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <RootNamespace>StardewAiMod</RootNamespace>
    <AssemblyName>StardewAiMod</AssemblyName>
    <LangVersion>latest</LangVersion>
    <Nullable>enable</Nullable>
    <EnableHarmony>true</EnableHarmony>
    <GamePath>/Users/suchong/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS</GamePath>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Pathoschild.Stardew.ModBuildConfig" Version="4.3.2" />
  </ItemGroup>
</Project>
```

> **Why:** `Pathoschild.Stardew.ModBuildConfig` resolves SMAPI / Stardew assemblies from `GamePath` (or `STARDEW_VALLEY_PATH` env) and pulls in HarmonyLib transitively. `EnableHarmony=true` is required; without it, the Harmony reference is excluded.

- [ ] **Step 2: Write `mod/manifest.json`**

```json
{
  "Name": "Stardew AI Mod",
  "Author": "you",
  "Version": "0.1.0",
  "Description": "Replaces NPC dialogue with AI replies via a local bridge.",
  "UniqueID": "local.StardewAiMod",
  "EntryDll": "StardewAiMod.dll",
  "MinimumApiVersion": "4.0.0",
  "UpdateKeys": []
}
```

- [ ] **Step 3: Write `scripts/install_mod.sh`**

```bash
#!/usr/bin/env bash
# Build the mod and copy artifacts into the SMAPI Mods folder.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODS_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/StardewAiMod"

cd "$ROOT/mod"
dotnet build -c Debug

mkdir -p "$MODS_DIR"
cp -v bin/Debug/net6.0/StardewAiMod.dll "$MODS_DIR/"
cp -v manifest.json "$MODS_DIR/"
echo "Installed to: $MODS_DIR"
```

- [ ] **Step 4: Make the script executable**

Run:
```bash
chmod +x scripts/install_mod.sh
```

- [ ] **Step 5: Restore packages (no build yet — ModEntry.cs missing)**

Run:
```bash
cd mod && dotnet restore
```

Expected: `Restore complete` with no errors. (`dotnet build` would fail because `ModEntry.cs` does not exist yet; that is fine.)

- [ ] **Step 6: Commit**

```bash
git add mod/StardewAiMod.csproj mod/manifest.json scripts/install_mod.sh
git commit -m "feat(mod): scaffold C# project, manifest, install script"
```

---

## Task 3: Write ModEntry skeleton (no patches yet)

**Files:**
- Create: `mod/ModEntry.cs`

- [ ] **Step 1: Write `mod/ModEntry.cs`**

```csharp
using StardewModdingAPI;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        public override void Entry(IModHelper helper)
        {
            this.Monitor.Log("StardewAiMod loaded.", LogLevel.Info);
        }
    }
}
```

- [ ] **Step 2: Build**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.` with 0 warnings, 0 errors.

- [ ] **Step 3: Install**

Run:
```bash
./scripts/install_mod.sh
```

Expected output ends with `Installed to: …/Mods/StardewAiMod`.

- [ ] **Step 4: Manually verify SMAPI loads the mod**

Launch Stardew Valley via Steam. In the SMAPI console, look for a line like:
```
[SMAPI] Loaded 1 mods:
[SMAPI]    Stardew AI Mod 0.1.0 by you | Replaces NPC dialogue ...
[Stardew AI Mod] StardewAiMod loaded.
```

Quit the game.

- [ ] **Step 5: Commit**

```bash
git add mod/ModEntry.cs
git commit -m "feat(mod): minimal ModEntry that logs on load"
```

---

## Task 4: Add Harmony patch with hardcoded "Hello from AI Mod!"

**Files:**
- Create: `mod/Patches/NpcCheckActionPatch.cs`
- Modify: `mod/ModEntry.cs`

- [ ] **Step 1: Write `mod/Patches/NpcCheckActionPatch.cs`**

```csharp
using HarmonyLib;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace StardewAiMod.Patches
{
    [HarmonyPatch(typeof(NPC), nameof(NPC.checkAction))]
    public static class NpcCheckActionPatch
    {
        private static IMonitor? Monitor;

        public static void Initialize(IMonitor monitor)
        {
            Monitor = monitor;
        }

        public static bool Prefix(NPC __instance, Farmer who, GameLocation l, ref bool __result)
        {
            if (!Context.IsWorldReady)
                return true;

            Monitor?.Log($"Intercepted checkAction on NPC '{__instance.Name}'.", LogLevel.Debug);

            Game1.activeClickableMenu = new DialogueBox("Hello from AI Mod!");
            __result = true;
            return false;
        }
    }
}
```

> **Why `__result = true` and `return false`:** A Harmony Prefix that returns `false` skips the original method. The original `NPC.checkAction` returns `bool` (whether the action was handled); we set `__result = true` so the caller behaves as if the action was consumed, and `return false` so the original body never runs (no native dialogue queued).

- [ ] **Step 2: Modify `mod/ModEntry.cs` to apply patches**

Replace the file contents with:

```csharp
using HarmonyLib;
using StardewAiMod.Patches;
using StardewModdingAPI;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        public override void Entry(IModHelper helper)
        {
            NpcCheckActionPatch.Initialize(this.Monitor);

            var harmony = new Harmony(this.ModManifest.UniqueID);
            harmony.PatchAll();

            this.Monitor.Log("StardewAiMod loaded; Harmony patches applied.", LogLevel.Info);
        }
    }
}
```

- [ ] **Step 3: Build and install**

Run:
```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
./scripts/install_mod.sh
```

Expected: build succeeds, install completes.

- [ ] **Step 4: Commit**

```bash
git add mod/Patches/NpcCheckActionPatch.cs mod/ModEntry.cs
git commit -m "feat(mod): Harmony patch on NPC.checkAction with hardcoded reply"
```

---

## Task 5: Manual acceptance for Phase 1

**Files:** none (manual verification)

- [ ] **Step 1: Run the spec's Phase 1 acceptance criteria**

Launch Stardew Valley. Verify, in order:

1. SMAPI console shows: `[Stardew AI Mod] StardewAiMod loaded; Harmony patches applied.`
2. Load the existing save game past intro. In Pelican Town, walk up to any NPC (e.g. Robin). Press the action button. A dialogue box appears showing exactly: `Hello from AI Mod!`
3. Close that dialogue. **No** native dialogue follows.
4. Return to title screen. Press the action button on the title menu — no exception in the SMAPI console.

Quit the game. If any of the four criteria failed, fix and re-run before moving on.

- [ ] **Step 2: Commit a checkpoint marker**

```bash
git commit --allow-empty -m "chore: phase 1 acceptance verified"
```

---

## Task 6: Scaffold the Python bridge project

**Files:**
- Create: `bridge/pyproject.toml`
- Create: `bridge/.env.example`
- Create: `bridge/bridge/__init__.py`
- Create: `bridge/tests/__init__.py`
- Create: `scripts/run_bridge.sh`

- [ ] **Step 1: Write `bridge/pyproject.toml`**

```toml
[project]
name = "stardew-ai-bridge"
version = "0.1.0"
description = "WebSocket bridge between SMAPI mod and DeepSeek."
requires-python = ">=3.11"
dependencies = [
    "websockets>=12.0",
    "pydantic>=2.6",
    "openai>=1.30",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["bridge*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `bridge/.env.example`**

```bash
# Copy to .env and fill in.
DEEPSEEK_API_KEY=
```

- [ ] **Step 3: Create empty package init files**

Write `bridge/bridge/__init__.py`:
```python
```

Write `bridge/tests/__init__.py`:
```python
```

- [ ] **Step 4: Write `scripts/run_bridge.sh`**

```bash
#!/usr/bin/env bash
# Start the Python bridge. Loads bridge/.env if present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/bridge"

if [ ! -d ".venv" ]; then
  python3.11 -m venv .venv
  ./.venv/bin/pip install -e ".[dev]"
fi

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

./.venv/bin/python -m bridge.server "$@"
```

- [ ] **Step 5: Make the script executable**

Run:
```bash
chmod +x scripts/run_bridge.sh
```

- [ ] **Step 6: Bootstrap the venv now (so subsequent tasks can run pytest)**

Run:
```bash
cd bridge
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Expected: `Successfully installed … websockets-… pydantic-… openai-… pytest-…`. If `python3.11` is missing, install via `brew install python@3.11` and retry.

- [ ] **Step 7: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/pyproject.toml bridge/.env.example bridge/bridge/__init__.py bridge/tests/__init__.py scripts/run_bridge.sh
git commit -m "feat(bridge): scaffold Python project, venv bootstrap script"
```

---

## Task 7: Implement the protocol module (TDD)

**Files:**
- Create: `bridge/tests/test_protocol.py`
- Create: `bridge/bridge/protocol.py`

- [ ] **Step 1: Write the failing test `bridge/tests/test_protocol.py`**

```python
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
```

- [ ] **Step 2: Run the tests; verify they fail**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_protocol.py -v
```

Expected: 6 errors, all `ModuleNotFoundError: No module named 'bridge.protocol'` or `ImportError`.

- [ ] **Step 3: Implement `bridge/bridge/protocol.py`**

```python
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
```

- [ ] **Step 4: Run the tests; verify they pass**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_protocol.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/protocol.py bridge/tests/test_protocol.py
git commit -m "feat(bridge): protocol module with pydantic schema and parse_message"
```

---

## Task 8: Implement the echo server (TDD)

**Files:**
- Create: `bridge/tests/test_echo_roundtrip.py`
- Create: `bridge/bridge/server.py`

- [ ] **Step 1: Write the failing integration test `bridge/tests/test_echo_roundtrip.py`**

```python
import asyncio
import json

import pytest
import websockets

from bridge.server import serve


@pytest.mark.asyncio
async def test_echo_roundtrip():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({
                "type": "npc_interact",
                "v": 1,
                "id": "test-1",
                "npc": "Robin",
                "player": "Alex",
                "location": "Town",
                "ts": 1715251200,
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)

    msg = json.loads(raw)
    assert msg["type"] == "npc_reply"
    assert msg["id"] == "test-1"
    assert msg["npc"] == "Robin"
    assert "Robin" in msg["text"]


@pytest.mark.asyncio
async def test_session_reset_no_reply():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({
                "type": "session_reset",
                "v": 1,
                "reason": "returned_to_title",
            }))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), timeout=0.3)


@pytest.mark.asyncio
async def test_unknown_type_ignored_no_disconnect():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({"type": "mystery", "v": 1}))
            # then a real message; if the unknown one had killed the connection,
            # this would raise ConnectionClosed.
            await ws.send(json.dumps({
                "type": "npc_interact",
                "v": 1,
                "id": "test-2",
                "npc": "Lewis",
                "player": "Alex",
                "location": "Town",
                "ts": 1,
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
    assert json.loads(raw)["id"] == "test-2"
```

- [ ] **Step 2: Run the tests; verify they fail**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_echo_roundtrip.py -v
```

Expected: import errors / `cannot import name 'serve' from 'bridge.server'`.

- [ ] **Step 3: Implement `bridge/bridge/server.py`**

```python
"""WebSocket server for the Stardew AI bridge.

Phase 2: echoes a static reply per click.
Later phases extend `_handle_npc_interact` to call the LLM / MCP client.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import websockets
from websockets.server import WebSocketServerProtocol

from bridge.protocol import (
    NpcInteract,
    NpcReply,
    SessionReset,
    parse_message,
)

log = logging.getLogger("bridge.server")


async def _handle_npc_interact(msg: NpcInteract, history: dict[str, list[dict]]) -> NpcReply:
    """Phase 2: pure echo. Phase 3 swaps the body for an LLM call."""
    text = f"You clicked {msg.npc}"
    history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
    history[msg.npc].append({"role": "assistant", "text": text})
    return NpcReply(id=msg.id, npc=msg.npc, text=text, done=True)


async def _handle_client(ws: WebSocketServerProtocol) -> None:
    history: dict[str, list[dict]] = {}
    log.info("client connected: %s", ws.remote_address)
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            msg = parse_message(raw)
            if msg is None:
                log.warning("ignoring malformed/unknown frame: %r", raw[:200])
                continue

            if isinstance(msg, NpcInteract):
                log.info("Player clicked %s id=%s loc=%s", msg.npc, msg.id, msg.location)
                reply = await _handle_npc_interact(msg, history)
                await ws.send(reply.model_dump_json())

            elif isinstance(msg, SessionReset):
                log.info("session_reset (%s); clearing history", msg.reason)
                history.clear()

            else:
                log.debug("ignoring message of type %s on server", msg.type)
    except websockets.ConnectionClosed:
        pass
    finally:
        log.info("client disconnected")


@asynccontextmanager
async def serve(host: str = "127.0.0.1", port: int = 8765) -> AsyncIterator:
    """Start the server; yield the underlying websockets.Server.

    Returning the underlying object lets tests read the bound port when port=0.
    """
    server = await websockets.serve(_handle_client, host, port)
    try:
        yield server
    finally:
        server.close()
        await server.wait_closed()


async def _amain(host: str, port: int) -> None:
    async with serve(host, port) as server:
        bound_port = server.sockets[0].getsockname()[1]
        log.info("listening on ws://%s:%s", host, bound_port)
        await asyncio.Future()  # run forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        asyncio.run(_amain(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests; verify they pass**

Run:
```bash
cd bridge && ./.venv/bin/pytest -v
```

Expected: all tests pass — `9 passed` total (6 protocol + 3 echo).

- [ ] **Step 5: Smoke test the runnable server with `wscat`**

In terminal A:
```bash
./scripts/run_bridge.sh
```
Expected: `listening on ws://127.0.0.1:8765`.

In terminal B (install wscat once if needed: `npm install -g wscat`):
```bash
wscat -c ws://127.0.0.1:8765
> {"type":"npc_interact","v":1,"id":"x1","npc":"Robin","player":"Alex","location":"Town","ts":1}
< {"type":"npc_reply","v":1,"id":"x1","npc":"Robin","text":"You clicked Robin","done":true}
```

Stop the bridge with `Ctrl+C` in terminal A.

- [ ] **Step 6: Commit**

```bash
git add bridge/bridge/server.py bridge/tests/test_echo_roundtrip.py
git commit -m "feat(bridge): asyncio websockets server with echo handler"
```

---

## Task 9: Mod-side message records

**Files:**
- Create: `mod/Net/Messages.cs`

- [ ] **Step 1: Write `mod/Net/Messages.cs`**

```csharp
using System;
using System.Text.Json.Serialization;

namespace StardewAiMod.Net
{
    public record NpcInteract(
        [property: JsonPropertyName("id")] string Id,
        [property: JsonPropertyName("npc")] string Npc,
        [property: JsonPropertyName("player")] string Player,
        [property: JsonPropertyName("location")] string Location,
        [property: JsonPropertyName("ts")] long Ts
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

- [ ] **Step 2: Build to make sure the file compiles**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.` — the records are not used yet but must compile cleanly.

- [ ] **Step 3: Commit**

```bash
git add mod/Net/Messages.cs
git commit -m "feat(mod): wire-protocol record types"
```

---

## Task 10: BridgeClient — connection + receive loop (no send yet)

**Files:**
- Create: `mod/Net/BridgeClient.cs`

- [ ] **Step 1: Write `mod/Net/BridgeClient.cs`**

```csharp
using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using StardewModdingAPI;

namespace StardewAiMod.Net
{
    /// <summary>
    /// Long-lived WebSocket client to the Python bridge.
    /// Reconnects with exponential backoff. All public callers are on the game's main thread;
    /// internal work runs on background tasks. Replies arrive on the ReplyQueue; ModEntry drains it
    /// during UpdateTicked so all UI calls happen on the main thread.
    /// </summary>
    public sealed class BridgeClient
    {
        private readonly Uri _uri;
        private readonly IMonitor _monitor;
        private readonly CancellationTokenSource _cts = new();
        private ClientWebSocket? _ws;
        private volatile bool _isConnected;

        public ConcurrentQueue<NpcReply> ReplyQueue { get; } = new();
        public bool IsConnected => _isConnected;

        public BridgeClient(string url, IMonitor monitor)
        {
            _uri = new Uri(url);
            _monitor = monitor;
        }

        public void Start()
        {
            _ = Task.Run(() => ConnectLoopAsync(_cts.Token));
        }

        public void Stop()
        {
            _cts.Cancel();
            try { _ws?.Abort(); } catch { /* best effort */ }
        }

        private async Task ConnectLoopAsync(CancellationToken ct)
        {
            int delayMs = 1000;
            while (!ct.IsCancellationRequested)
            {
                _ws = new ClientWebSocket();
                try
                {
                    _monitor.Log($"Bridge: connecting to {_uri}", LogLevel.Trace);
                    await _ws.ConnectAsync(_uri, ct);
                    _isConnected = true;
                    delayMs = 1000;
                    _monitor.Log("Bridge: connected.", LogLevel.Info);
                    await ReceiveLoopAsync(_ws, ct);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex)
                {
                    _monitor.Log($"Bridge: connect/receive error: {ex.Message}", LogLevel.Trace);
                }
                finally
                {
                    _isConnected = false;
                    try { _ws?.Dispose(); } catch { }
                }

                if (ct.IsCancellationRequested) break;
                try { await Task.Delay(delayMs, ct); } catch { break; }
                delayMs = Math.Min(delayMs * 2, 10000);
            }
        }

        private async Task ReceiveLoopAsync(ClientWebSocket ws, CancellationToken ct)
        {
            var buffer = new byte[8192];
            var sb = new StringBuilder();
            while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
            {
                sb.Clear();
                WebSocketReceiveResult result;
                do
                {
                    result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", ct);
                        return;
                    }
                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                } while (!result.EndOfMessage);

                var raw = sb.ToString();
                NpcReply? reply = null;
                try
                {
                    using var doc = JsonDocument.Parse(raw);
                    var type = doc.RootElement.GetProperty("type").GetString();
                    if (type == "npc_reply")
                        reply = JsonSerializer.Deserialize<NpcReply>(raw);
                    else
                        _monitor.Log($"Bridge: ignoring message of type '{type}'.", LogLevel.Trace);
                }
                catch (Exception ex)
                {
                    _monitor.Log($"Bridge: parse error: {ex.Message}; raw={raw}", LogLevel.Warn);
                    continue;
                }

                if (reply != null) ReplyQueue.Enqueue(reply);
            }
        }
    }
}
```

> **Why a `ConcurrentQueue` and not an `event`:** All Stardew UI calls must run on the main thread. Firing an event from the receive task would put consumers on the background thread. Instead, the queue is drained on `UpdateTicked` (Task 13).

- [ ] **Step 2: Build**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.`

- [ ] **Step 3: Commit**

```bash
git add mod/Net/BridgeClient.cs
git commit -m "feat(mod): BridgeClient with connect loop and receive→queue path"
```

---

## Task 11: BridgeClient — send methods

**Files:**
- Modify: `mod/Net/BridgeClient.cs`

- [ ] **Step 1: Add send methods to `BridgeClient`**

Insert the following members into `BridgeClient` (place them after the `Stop()` method):

```csharp
        public string? SendNpcInteract(string npcName, string playerName, string location)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return null;
            var id = Guid.NewGuid().ToString("N");
            var msg = new NpcInteract(id, npcName, playerName, location, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
            return id;
        }

        public void SendSessionReset(string reason)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return;
            var msg = new SessionReset(reason);
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
        }

        private async Task SendJsonAsync(string json)
        {
            try
            {
                var bytes = Encoding.UTF8.GetBytes(json);
                var ws = _ws;
                if (ws is null) return;
                await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            catch (Exception ex)
            {
                _monitor.Log($"Bridge: send failed: {ex.Message}", LogLevel.Warn);
            }
        }
```

- [ ] **Step 2: Build**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.`

- [ ] **Step 3: Commit**

```bash
git add mod/Net/BridgeClient.cs
git commit -m "feat(mod): BridgeClient send methods (npc_interact, session_reset)"
```

---

## Task 12: Wire BridgeClient into ModEntry, add UpdateTicked drain

**Files:**
- Modify: `mod/ModEntry.cs`

- [ ] **Step 1: Replace `mod/ModEntry.cs`**

```csharp
using System;
using System.Collections.Generic;
using HarmonyLib;
using StardewAiMod.Net;
using StardewAiMod.Patches;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewValley.Menus;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        private const string BridgeUrl = "ws://127.0.0.1:8765";
        private const double ReplyTimeoutSeconds = 12.0;

        private BridgeClient? _bridge;

        // id → (npc, deadlineUtc, placeholderMenu); accessed only on main thread.
        private readonly Dictionary<string, InflightRequest> _inflight = new();
        private readonly HashSet<string> _cancelledIds = new();

        public BridgeClient Bridge => _bridge!;
        public IReadOnlyDictionary<string, InflightRequest> Inflight => _inflight;

        public override void Entry(IModHelper helper)
        {
            _bridge = new BridgeClient(BridgeUrl, this.Monitor);
            _bridge.Start();

            // NOTE: Initialize signature is updated in Task 13 to also pass `this`.
            // Until then the patch keeps using its hardcoded "Hello from AI Mod!" reply,
            // which is fine — this task only adds the bridge plumbing on the ModEntry side.
            NpcCheckActionPatch.Initialize(this.Monitor);

            var harmony = new Harmony(this.ModManifest.UniqueID);
            harmony.PatchAll();

            helper.Events.GameLoop.UpdateTicked += this.OnUpdateTicked;
            helper.Events.GameLoop.ReturnedToTitle += this.OnReturnedToTitle;

            this.Monitor.Log("StardewAiMod loaded; Harmony + bridge active.", LogLevel.Info);
        }

        public void RegisterInflight(string id, string npc, IClickableMenu placeholder)
        {
            _inflight[id] = new InflightRequest(npc, DateTime.UtcNow.AddSeconds(ReplyTimeoutSeconds), placeholder);
        }

        public bool HasInflightForNpc(string npc)
        {
            foreach (var kv in _inflight)
                if (kv.Value.Npc == npc) return true;
            return false;
        }

        private void OnUpdateTicked(object? sender, UpdateTickedEventArgs e)
        {
            // Drain replies.
            while (_bridge!.ReplyQueue.TryDequeue(out var reply))
            {
                if (_cancelledIds.Remove(reply.Id))
                {
                    this.Monitor.Log($"Discarding reply for cancelled id={reply.Id}.", LogLevel.Trace);
                    continue;
                }
                if (!_inflight.TryGetValue(reply.Id, out var info))
                {
                    this.Monitor.Log($"Reply for unknown id={reply.Id}; dropping.", LogLevel.Trace);
                    continue;
                }
                _inflight.Remove(reply.Id);

                // Replace placeholder iff it is still our menu.
                if (Game1.activeClickableMenu == info.Placeholder)
                    Game1.activeClickableMenu = new DialogueBox(reply.Text);
                // else: player dismissed it; do nothing.
            }

            // Watch for player-dismissed placeholders → mark cancelled.
            if (_inflight.Count > 0)
            {
                List<string>? toCancel = null;
                var now = DateTime.UtcNow;
                foreach (var kv in _inflight)
                {
                    if (Game1.activeClickableMenu != kv.Value.Placeholder)
                    {
                        (toCancel ??= new()).Add(kv.Key);
                    }
                    else if (now > kv.Value.DeadlineUtc)
                    {
                        (toCancel ??= new()).Add(kv.Key);
                        Game1.activeClickableMenu = new DialogueBox("…(NPC didn't speak)");
                    }
                }
                if (toCancel != null)
                {
                    foreach (var id in toCancel)
                    {
                        _inflight.Remove(id);
                        _cancelledIds.Add(id);
                    }
                }
            }
        }

        private void OnReturnedToTitle(object? sender, ReturnedToTitleEventArgs e)
        {
            _inflight.Clear();
            _cancelledIds.Clear();
            _bridge?.SendSessionReset("returned_to_title");
        }
    }

    public record InflightRequest(string Npc, DateTime DeadlineUtc, IClickableMenu Placeholder);
}
```

> **Notes on the design:**
> - Cancellation works two ways: an explicit set (`_cancelledIds`) for replies that arrive after the placeholder was dismissed, and the per-tick scan that moves "active menu changed" or "deadline passed" entries from `_inflight` into `_cancelledIds`. This avoids any UI mutation off the main thread.
> - `_cancelledIds.Remove(id)` returns `true` if the id was present and removes it — so each cancelled id is consumed exactly once when its reply arrives.

- [ ] **Step 2: Build**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.` At this checkpoint the bridge connects but the patch still uses the hardcoded "Hello from AI Mod!" string — Task 13 wires the patch to the bridge.

- [ ] **Step 3: Commit**

```bash
git add mod/ModEntry.cs
git commit -m "feat(mod): wire BridgeClient, in-flight tracking, UpdateTicked drain"
```

---

## Task 13: Update the Harmony patch to send via the bridge

**Files:**
- Modify: `mod/Patches/NpcCheckActionPatch.cs`
- Modify: `mod/ModEntry.cs` (one-line change to the Initialize call)

- [ ] **Step 1: Replace `mod/Patches/NpcCheckActionPatch.cs`**

```csharp
using HarmonyLib;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace StardewAiMod.Patches
{
    [HarmonyPatch(typeof(NPC), nameof(NPC.checkAction))]
    public static class NpcCheckActionPatch
    {
        private static IMonitor? Monitor;
        private static ModEntry? Mod;

        public static void Initialize(IMonitor monitor, ModEntry mod)
        {
            Monitor = monitor;
            Mod = mod;
        }

        public static bool Prefix(NPC __instance, Farmer who, GameLocation l, ref bool __result)
        {
            if (!Context.IsWorldReady || Mod is null) return true;

            var bridge = Mod.Bridge;
            if (!bridge.IsConnected)
            {
                Monitor?.Log($"Bridge not connected; falling back to native dialogue for {__instance.Name}.", LogLevel.Trace);
                return true;
            }

            if (Mod.HasInflightForNpc(__instance.Name))
            {
                Monitor?.Log($"Ignoring click on {__instance.Name}: request still in flight.", LogLevel.Trace);
                __result = true;
                return false;
            }

            var placeholder = new DialogueBox("…");
            Game1.activeClickableMenu = placeholder;

            var id = bridge.SendNpcInteract(__instance.Name, who.Name, l?.Name ?? "Unknown");
            if (id is null)
            {
                // Send failed (e.g. just disconnected). Drop the placeholder and let native run next click.
                Game1.activeClickableMenu = null;
                return true;
            }

            Mod.RegisterInflight(id, __instance.Name, placeholder);
            __result = true;
            return false;
        }
    }
}
```

- [ ] **Step 2: Update the call site in `mod/ModEntry.cs`**

Find this line in `Entry`:
```csharp
            NpcCheckActionPatch.Initialize(this.Monitor);
```
Replace with:
```csharp
            NpcCheckActionPatch.Initialize(this.Monitor, this);
```
And remove the three-line `// NOTE: Initialize signature ...` comment block above it (no longer needed).

- [ ] **Step 3: Build**

Run:
```bash
cd mod && dotnet build -c Debug
```

Expected: `Build succeeded.`

- [ ] **Step 4: Install**

Run:
```bash
./scripts/install_mod.sh
```

Expected: install completes.

- [ ] **Step 5: Commit**

```bash
git add mod/Patches/NpcCheckActionPatch.cs mod/ModEntry.cs
git commit -m "feat(mod): patch routes NPC clicks through the bridge"
```

---

## Task 14: Manual acceptance for Phase 2

**Files:** none (manual verification)

- [ ] **Step 1: Run the spec's Phase 2 acceptance criteria**

Verify, in order:

1. **Bridge off, AI off**: do **not** start the bridge. Launch Stardew Valley. Click an NPC → native dialogue appears (not the AI placeholder). Quit.
2. **Bridge on, echo path**: start the bridge with `./scripts/run_bridge.sh`. Bridge terminal shows `listening on ws://127.0.0.1:8765`.
3. Launch Stardew Valley. Bridge terminal shows `client connected: …`.
4. In game, click Robin. Game shows `…` placeholder, then within ~1s replaces it with `You clicked Robin`. Bridge terminal shows `Player clicked Robin id=… loc=Town`.
5. **Mid-game bridge restart**: in the bridge terminal, `Ctrl+C` to stop. Click an NPC in game → native dialogue (graceful degradation). Restart bridge with `./scripts/run_bridge.sh`. Within ~10s the SMAPI console logs `Bridge: connected.` Click an NPC → echo path resumes.
6. **Dismiss-during-wait**: have a collaborator hold off the bridge response (or just be quick) — click NPC, then immediately press the action key to advance/close the placeholder. SMAPI console logs `Discarding reply for cancelled id=…`.
7. **Return to title**: from in-game, return to title. Bridge terminal logs `session_reset (returned_to_title); clearing history`.

Quit the game and stop the bridge.

- [ ] **Step 2: Commit a checkpoint marker**

```bash
git commit --allow-empty -m "chore: phase 2 acceptance verified"
```

---

## Task 15: LLM module (TDD on prompt assembly)

**Files:**
- Create: `bridge/tests/test_llm.py`
- Create: `bridge/bridge/llm.py`

- [ ] **Step 1: Write the failing test `bridge/tests/test_llm.py`**

```python
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
```

- [ ] **Step 2: Run the tests; verify they fail**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_llm.py -v
```

Expected: import errors / `cannot import name 'reply' from 'bridge.llm'`.

- [ ] **Step 3: Implement `bridge/bridge/llm.py`**

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
MODEL = "deepseek-chat"
TIMEOUT_SECONDS = 8.0
MAX_TOKENS = 200


def make_client() -> AsyncOpenAI:
    """Construct a DeepSeek client. Reads DEEPSEEK_API_KEY from the environment."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def build_messages(
    npc_name: str,
    player_name: str,
    location: str,
    history: list[dict[str, str]],
    user_text: str,
) -> list[dict[str, str]]:
    system = (
        f"You are {npc_name} from Stardew Valley. "
        f"The player {player_name} just talked to you in {location}. "
        f"Reply in 1-2 short sentences, in character, in English."
    )
    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in history:
        role = turn.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": turn.get("text", "")})
    msgs.append({"role": "user", "content": user_text})
    return msgs


async def reply(
    client: Any,
    npc_name: str,
    player_name: str,
    location: str,
    history: list[dict[str, str]],
    user_text: str,
) -> str:
    """Call DeepSeek; return reply text or FALLBACK_TEXT on any error."""
    messages = build_messages(npc_name, player_name, location, history, user_text)
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

- [ ] **Step 4: Run the tests; verify they pass**

Run:
```bash
cd bridge && ./.venv/bin/pytest tests/test_llm.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/llm.py bridge/tests/test_llm.py
git commit -m "feat(bridge): DeepSeek-backed reply() with fallback path"
```

---

## Task 16: Wire LLM into the server (replace echo)

**Files:**
- Modify: `bridge/bridge/server.py`
- Modify: `bridge/tests/test_echo_roundtrip.py`

- [ ] **Step 1: Add the `llm` import to the top of `bridge/bridge/server.py`**

In the imports section near the top, add:
```python
from bridge import llm as llm_mod
```
Place it next to the existing `from bridge.protocol import (...)` line.

- [ ] **Step 2: Modify `bridge/bridge/server.py`**

Replace the `_handle_npc_interact` function and add a client-factory-aware handler:

Replace this block:
```python
async def _handle_npc_interact(msg: NpcInteract, history: dict[str, list[dict]]) -> NpcReply:
    """Phase 2: pure echo. Phase 3 swaps the body for an LLM call."""
    text = f"You clicked {msg.npc}"
    history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
    history[msg.npc].append({"role": "assistant", "text": text})
    return NpcReply(id=msg.id, npc=msg.npc, text=text, done=True)
```

with:

```python
def _make_handler(client_factory):
    """Returns an _handle_npc_interact bound to a client (or None for echo mode)."""
    client = client_factory() if client_factory is not None else None

    async def handler(msg: NpcInteract, history: dict[str, list[dict]]) -> NpcReply:
        if client is None:
            text = f"You clicked {msg.npc}"
        else:
            user_text = ""  # phase 3: no free-text input from the player yet
            text = await llm_mod.reply(
                client=client,
                npc_name=msg.npc,
                player_name=msg.player,
                location=msg.location,
                history=history.get(msg.npc, []),
                user_text=user_text,
            )
        history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
        history[msg.npc].append({"role": "assistant", "text": text})
        return NpcReply(id=msg.id, npc=msg.npc, text=text, done=True)

    return handler
```

Then change `_handle_client` to take a handler, and update `serve` and `_amain` to construct one. Replace the `_handle_client`, `serve`, `_amain`, and `main` definitions with:

```python
async def _handle_client(ws: WebSocketServerProtocol, handler) -> None:
    history: dict[str, list[dict]] = {}
    log.info("client connected: %s", ws.remote_address)
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            msg = parse_message(raw)
            if msg is None:
                log.warning("ignoring malformed/unknown frame: %r", raw[:200])
                continue

            if isinstance(msg, NpcInteract):
                log.info("Player clicked %s id=%s loc=%s", msg.npc, msg.id, msg.location)
                reply_msg = await handler(msg, history)
                await ws.send(reply_msg.model_dump_json())

            elif isinstance(msg, SessionReset):
                log.info("session_reset (%s); clearing history", msg.reason)
                history.clear()

            else:
                log.debug("ignoring message of type %s on server", msg.type)
    except websockets.ConnectionClosed:
        pass
    finally:
        log.info("client disconnected")


@asynccontextmanager
async def serve(host: str = "127.0.0.1", port: int = 8765, *, client_factory=None) -> AsyncIterator:
    """Start the server. If client_factory is None, the handler echoes."""
    handler = _make_handler(client_factory)

    async def per_client(ws):
        await _handle_client(ws, handler)

    server = await websockets.serve(per_client, host, port)
    try:
        yield server
    finally:
        server.close()
        await server.wait_closed()


async def _amain(host: str, port: int, use_llm: bool) -> None:
    factory = llm_mod.make_client if use_llm else None
    async with serve(host, port, client_factory=factory) as server:
        bound_port = server.sockets[0].getsockname()[1]
        log.info("listening on ws://%s:%s (llm=%s)", host, bound_port, use_llm)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--echo", action="store_true", help="Use echo handler instead of LLM.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        asyncio.run(_amain(args.host, args.port, use_llm=not args.echo))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `bridge/tests/test_echo_roundtrip.py` to use the echo path explicitly**

Replace each `serve(host="127.0.0.1", port=0)` with `serve(host="127.0.0.1", port=0, client_factory=None)` (the echo default is the same; making it explicit documents intent).

The three calls to update are at the start of `test_echo_roundtrip`, `test_session_reset_no_reply`, and `test_unknown_type_ignored_no_disconnect`. Each becomes:
```python
async with serve(host="127.0.0.1", port=0, client_factory=None) as server:
```

- [ ] **Step 4: Run all tests; verify they pass**

Run:
```bash
cd bridge && ./.venv/bin/pytest -v
```

Expected: 13 passed (6 protocol + 3 echo + 4 llm).

- [ ] **Step 5: Commit**

```bash
cd /Users/suchong/workspace/hermes/stardew_valley_with_ai/stardew_valley_with_ai
git add bridge/bridge/server.py bridge/tests/test_echo_roundtrip.py
git commit -m "feat(bridge): server uses LLM by default, --echo flag for offline use"
```

---

## Task 17: Configure DeepSeek key and live-test Phase 3

**Files:**
- Create: `bridge/.env` (gitignored)

- [ ] **Step 1: Create `bridge/.env`**

Run:
```bash
cp bridge/.env.example bridge/.env
```

Open `bridge/.env` and set `DEEPSEEK_API_KEY=` to your real key. **Do not commit** — `.env` is in `.gitignore`.

- [ ] **Step 2: Verify the key is loaded by `run_bridge.sh`**

Run:
```bash
./scripts/run_bridge.sh --debug
```

Expected: `listening on ws://127.0.0.1:8765 (llm=True)`. Stop with `Ctrl+C`.

- [ ] **Step 3: Run Phase 3 acceptance criteria**

1. **Live LLM**: start the bridge (`./scripts/run_bridge.sh`). Launch Stardew Valley. Click Robin → an English in-character 1-2-sentence reply appears (not `You clicked Robin`). Bridge log includes the click and an INFO line; SMAPI log shows the reply.
2. **Continuity**: click Robin again — the reply may reference the previous turn (same connection means same `history[npc]`).
3. **Bad key**: stop the bridge. Edit `bridge/.env` to set `DEEPSEEK_API_KEY=invalid`. Restart the bridge. Click Robin → in-game shows `(NPC seems lost in thought.)`. Game does not crash. Bridge log warns `LLM call failed: …`.
4. **No network**: restore the key, restart the bridge, then disable network (turn off Wi-Fi). Click Robin → after ≤8s, `(NPC seems lost in thought.)` appears (LLM-side timeout). If you wait longer with the bridge crashed, the mod-side 12s timeout shows `…(NPC didn't speak)` instead. Re-enable Wi-Fi.

- [ ] **Step 4: Commit a checkpoint marker**

```bash
git commit --allow-empty -m "chore: phase 3 acceptance verified"
```

---

## Task 18: Phase 4 placeholder file

**Files:**
- Create: `bridge/bridge/mcp_client.py`

- [ ] **Step 1: Write `bridge/bridge/mcp_client.py`**

```python
"""Phase 4 placeholder: MCP client for the local mcp-stardewvalley server.

Not implemented in this spec. The full design will be done in a separate
brainstorming session after Phase 3 is stable.
"""
# TODO: phase 4 — wire to mcp-stardewvalley over its HTTP API and expose
# wiki/schema lookups as tools the LLM can call before composing a reply.
```

- [ ] **Step 2: Commit**

```bash
git add bridge/bridge/mcp_client.py
git commit -m "chore(bridge): placeholder for Phase 4 MCP client"
```

---

## Done

At this point:
- Phases 1–2 are fully verified end-to-end against the spec's acceptance criteria.
- Phase 3 is verified live against DeepSeek with fallback paths confirmed.
- Phase 4 has a parking-lot file ready for a separate plan.

Recommended next moves (out of scope for this plan):
- Push the local repo to the dedicated GitHub remote the user mentioned.
- Open a Phase 4 brainstorming session: scope MCP tool surface, decide whether the LLM calls tools or the bridge does pre-fetch RAG.
- Iterate on the system prompt in `bridge/llm.py` against actual play sessions — this is the place where the bulk of NPC personality work lives.
