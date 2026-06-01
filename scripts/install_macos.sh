#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/RenPyGame.app" >&2
  exit 64
fi

APP="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/game/octomil_tts.rpy"
VOICE_MAP_SOURCE="$ROOT/game/octomil_voice_map.json"
AUTORUN="$APP/Contents/Resources/autorun"
GAME_DIR="$AUTORUN/game"
TARGET="$GAME_DIR/octomil_tts.rpy"
VOICE_MAP_TARGET="$GAME_DIR/octomil_voice_map.json"

if [[ ! -d "$APP/Contents/Resources/autorun" ]]; then
  echo "Not a macOS Ren'Py app bundle: $APP" >&2
  exit 65
fi

if [[ ! -d "$GAME_DIR" ]]; then
  echo "Ren'Py game directory not found: $GAME_DIR" >&2
  exit 65
fi

if [[ ! -f "$SOURCE" ]]; then
  echo "Missing source script: $SOURCE" >&2
  exit 66
fi

if [[ -f "$TARGET" ]]; then
  BACKUP="$TARGET.backup.$(date +%Y%m%d-%H%M%S)"
  cp "$TARGET" "$BACKUP"
  echo "Backed up existing script: $BACKUP"
fi

cp "$SOURCE" "$TARGET"
echo "Installed: $TARGET"

if [[ -f "$VOICE_MAP_SOURCE" ]]; then
  cp "$VOICE_MAP_SOURCE" "$VOICE_MAP_TARGET"
  echo "Installed: $VOICE_MAP_TARGET"
fi

echo
echo "Next checks:"
echo "  1. Ensure Octomil SDK deps exist under: $AUTORUN/lib/octomil-deps"
echo "  2. Ensure native TTS dylib exists at the path configured in octomil_tts.rpy"
echo "  3. Run: $ROOT/scripts/verify.py \"$APP\""
