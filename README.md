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
