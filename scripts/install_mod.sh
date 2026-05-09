#!/usr/bin/env bash
# Build the mod and copy artifacts into the SMAPI Mods folder.
set -euo pipefail

# .NET 6 SDK is keg-only via Homebrew; prepend it so `dotnet` resolves to 6.0.
export PATH="/opt/homebrew/opt/dotnet@6/bin:$PATH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODS_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/StardewAiMod"

cd "$ROOT/mod"
dotnet build -c Debug

mkdir -p "$MODS_DIR"
cp -v bin/Debug/net6.0/StardewAiMod.dll "$MODS_DIR/"
cp -v manifest.json "$MODS_DIR/"
echo "Installed to: $MODS_DIR"
