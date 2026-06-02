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
REN_PYTHON="$APP/Contents/MacOS/python"

SDK_VERSION="${OCTOMIL_SDK_VERSION:-4.17.31}"
SDK_TAG="v${SDK_VERSION#v}"
SDK_VERSION="${SDK_TAG#v}"
RUNTIME_VERSION="${OCTOMIL_RUNTIME_VERSION:-v0.1.19}"
RUNTIME_TAG="v${RUNTIME_VERSION#v}"
RUNTIME_VERSION="${RUNTIME_TAG}"

VENDOR_DIR="${OCTOMIL_VENDOR_DIR:-$ROOT/vendor}"
VENDOR_WHEELHOUSE="${OCTOMIL_WHEELHOUSE:-$VENDOR_DIR/wheelhouse}"
SDK_WHEEL_URL="${OCTOMIL_SDK_WHEEL_URL:-https://github.com/octomil/octomil-python/releases/download/${SDK_TAG}/octomil-${SDK_VERSION}-py3-none-any.whl}"
RUNTIME_ASSET="liboctomil-runtime-${RUNTIME_VERSION}-tts-darwin-arm64.tar.gz"
RUNTIME_BASE_URL="${OCTOMIL_RUNTIME_BASE_URL:-https://github.com/octomil/octomil-runtime/releases/download/${RUNTIME_VERSION}}"
RUNTIME_URL="${OCTOMIL_RUNTIME_URL:-${RUNTIME_BASE_URL}/${RUNTIME_ASSET}}"
RUNTIME_SHA_URL="${OCTOMIL_RUNTIME_SHA_URL:-${RUNTIME_BASE_URL}/SHA256SUMS}"
VENDOR_RUNTIME_ARCHIVE="${OCTOMIL_RUNTIME_ARCHIVE:-$VENDOR_DIR/$RUNTIME_ASSET}"
VENDOR_RUNTIME_CHECKSUMS="${OCTOMIL_RUNTIME_CHECKSUMS:-$VENDOR_DIR/SHA256SUMS}"

DEPS_DIR="$AUTORUN/lib/octomil-deps"
RUNTIME_DIR="$AUTORUN/lib/octomil-runtime/${RUNTIME_VERSION}/tts"
RUNTIME_LIB_DIR="$RUNTIME_DIR/lib"
RUNTIME_DYLIB="$RUNTIME_LIB_DIR/liboctomil-runtime.dylib"

info() {
  printf '\033[1;34m==>\033[0m %s\n' "$1"
}

warn() {
  printf '\033[1;33mwarning:\033[0m %s\n' "$1" >&2
}

error() {
  printf '\033[1;31merror:\033[0m %s\n' "$1" >&2
  exit "${2:-1}"
}

download() {
  local url="$1"
  local dest="$2"
  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

  if command -v curl >/dev/null 2>&1; then
    if [[ -n "$token" && "$url" == https://github.com/* ]]; then
      curl -fsSL -H "Authorization: Bearer $token" "$url" -o "$dest"
    else
      curl -fsSL "$url" -o "$dest"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [[ -n "$token" && "$url" == https://github.com/* ]]; then
      wget -q --header="Authorization: Bearer $token" -O "$dest" "$url"
    else
      wget -q -O "$dest" "$url"
    fi
  else
    error "curl or wget is required." 69
  fi
}

download_github_release_asset() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local dest="$4"
  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
  local metadata
  local asset_id

  if [[ -z "$token" ]]; then
    error "GITHUB_TOKEN or GH_TOKEN is required to download private GitHub release assets." 69
  fi

  metadata="$TMPDIR_PATH/release-${repo//\//-}-${tag}.json"
  curl -fsSL \
    -H "Authorization: Bearer $token" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${repo}/releases/tags/${tag}" \
    -o "$metadata"

  asset_id="$(python3 - "$metadata" "$asset" <<'PY'
import json
import sys

metadata, expected = sys.argv[1], sys.argv[2]
with open(metadata, "r") as f:
    release = json.load(f)
for asset in release.get("assets", []):
    if asset.get("name") == expected:
        print(asset["id"])
        break
else:
    raise SystemExit(f"asset not found: {expected}")
PY
)"

  curl -fsSL \
    -H "Authorization: Bearer $token" \
    -H "Accept: application/octet-stream" \
    "https://api.github.com/repos/${repo}/releases/assets/${asset_id}" \
    -o "$dest"
}

download_runtime_release_asset() {
  local asset="$1"
  local dest="$2"
  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

  if [[ -n "$token" ]]; then
    download_github_release_asset "octomil/octomil-runtime" "$RUNTIME_VERSION" "$asset" "$dest"
    return
  fi

  download "${RUNTIME_BASE_URL}/${asset}" "$dest"
}

verify_checksum() {
  local checksum_file="$1"
  local archive_path="$2"
  local archive_name
  local line
  archive_name="$(basename "$archive_path")"
  line="$(awk -v expected="$archive_name" '
    {
      path = $2
      sub(/^\.\//, "", path)
      if (path == expected) {
        print
        exit
      }
    }
  ' "$checksum_file")"

  if [[ -z "$line" ]]; then
    error "${archive_name} is not listed in ${checksum_file}." 66
  fi

  (
    cd "$(dirname "$archive_path")"
    if command -v shasum >/dev/null 2>&1; then
      printf '%s\n' "$line" | shasum -a 256 -c - >/dev/null
    elif command -v sha256sum >/dev/null 2>&1; then
      printf '%s\n' "$line" | sha256sum -c - >/dev/null
    else
      error "shasum or sha256sum is required." 69
    fi
  )
}

backup_path() {
  local path="$1"
  printf '%s.backup.%s\n' "$path" "$(date +%Y%m%d-%H%M%S)"
}

detect_target_python() {
  if [[ ! -x "$REN_PYTHON" ]]; then
    error "Ren'Py embedded Python not found: $REN_PYTHON" 65
  fi

  if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    error "This demo installer currently supports Apple Silicon macOS Ren'Py bundles." 70
  fi

  PY_VERSION_DOT="${OCTOMIL_TARGET_PY_VERSION:-3.9}"
  PY_ABI="${OCTOMIL_TARGET_PY_ABI:-cp${PY_VERSION_DOT/./}}"
  PY_PLATFORM="${OCTOMIL_PIP_PLATFORM:-macosx_11_0_arm64}"
}

validate_app() {
  if [[ ! -d "$AUTORUN" ]]; then
    error "Not a macOS Ren'Py app bundle: $APP" 65
  fi

  if [[ ! -d "$GAME_DIR" ]]; then
    error "Ren'Py game directory not found: $GAME_DIR" 65
  fi

  if [[ ! -f "$SOURCE" ]]; then
    error "Missing source script: $SOURCE" 66
  fi
}

install_game_files() {
  if [[ -f "$TARGET" ]]; then
    local backup
    backup="$(backup_path "$TARGET")"
    cp "$TARGET" "$backup"
    info "Backed up existing script: $backup"
  fi

  cp "$SOURCE" "$TARGET"
  info "Installed: $TARGET"

  if [[ -f "$VOICE_MAP_SOURCE" ]]; then
    if [[ -f "$VOICE_MAP_TARGET" ]]; then
      local map_backup
      map_backup="$(backup_path "$VOICE_MAP_TARGET")"
      cp "$VOICE_MAP_TARGET" "$map_backup"
      info "Backed up existing voice map: $map_backup"
    fi
    cp "$VOICE_MAP_SOURCE" "$VOICE_MAP_TARGET"
    info "Installed: $VOICE_MAP_TARGET"
  fi
}

install_sdk_deps() {
  if [[ "${OCTOMIL_SKIP_SDK_INSTALL:-0}" == "1" ]]; then
    warn "Skipping SDK dependency install because OCTOMIL_SKIP_SDK_INSTALL=1."
    return
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required to stage Octomil SDK dependencies." 69
  fi

  local tmp_deps
  tmp_deps="$TMPDIR_PATH/octomil-deps"

  info "Installing Octomil SDK ${SDK_TAG} for Ren'Py Python ${PY_VERSION_DOT} (${PY_PLATFORM}, ${PY_ABI})..."
  if [[ -d "$VENDOR_WHEELHOUSE" ]]; then
    info "Using bundled wheelhouse: $VENDOR_WHEELHOUSE"
    python3 -m pip install \
      --disable-pip-version-check \
      --upgrade \
      --target "$tmp_deps" \
      --platform "$PY_PLATFORM" \
      --python-version "$PY_VERSION_DOT" \
      --implementation cp \
      --abi "$PY_ABI" \
      --only-binary=:all: \
      --no-index \
      --find-links "$VENDOR_WHEELHOUSE" \
      "octomil==${SDK_VERSION}" \
      cffi
  else
    python3 -m pip install \
      --disable-pip-version-check \
      --upgrade \
      --target "$tmp_deps" \
      --platform "$PY_PLATFORM" \
      --python-version "$PY_VERSION_DOT" \
      --implementation cp \
      --abi "$PY_ABI" \
      --only-binary=:all: \
      "$SDK_WHEEL_URL" \
      cffi
  fi

  if [[ -d "$DEPS_DIR" ]]; then
    local backup
    backup="$(backup_path "$DEPS_DIR")"
    mv "$DEPS_DIR" "$backup"
    info "Backed up existing SDK deps: $backup"
  fi

  mkdir -p "$(dirname "$DEPS_DIR")"
  mv "$tmp_deps" "$DEPS_DIR"
  info "Installed SDK deps: $DEPS_DIR"
}

install_runtime() {
  if [[ "${OCTOMIL_SKIP_RUNTIME_INSTALL:-0}" == "1" ]]; then
    warn "Skipping runtime install because OCTOMIL_SKIP_RUNTIME_INSTALL=1."
    return
  fi

  local archive
  local checksums
  local extracted
  archive="$TMPDIR_PATH/$RUNTIME_ASSET"
  checksums="$TMPDIR_PATH/SHA256SUMS"
  extracted="$TMPDIR_PATH/runtime"

  if [[ -f "$VENDOR_RUNTIME_ARCHIVE" ]]; then
    info "Using bundled Octomil runtime: $VENDOR_RUNTIME_ARCHIVE"
    cp "$VENDOR_RUNTIME_ARCHIVE" "$archive"
    if [[ -f "$VENDOR_RUNTIME_CHECKSUMS" ]]; then
      cp "$VENDOR_RUNTIME_CHECKSUMS" "$checksums"
      verify_checksum "$checksums" "$archive"
    elif [[ -f "${VENDOR_RUNTIME_ARCHIVE}.sha256" ]]; then
      cp "${VENDOR_RUNTIME_ARCHIVE}.sha256" "$checksums"
      verify_checksum "$checksums" "$archive"
    else
      warn "Bundled runtime has no checksum file; skipping checksum verification."
    fi
  else
    info "Downloading Octomil runtime ${RUNTIME_VERSION} tts/darwin-arm64..."
    download_runtime_release_asset "$RUNTIME_ASSET" "$archive"
    download_runtime_release_asset "SHA256SUMS" "$checksums"
    verify_checksum "$checksums" "$archive"
  fi

  mkdir -p "$extracted"
  tar -xzf "$archive" -C "$extracted"

  local source_lib
  source_lib="$(find "$extracted" -type f -name 'liboctomil-runtime.dylib' -print -quit)"
  if [[ -z "$source_lib" ]]; then
    error "Runtime archive did not contain liboctomil-runtime.dylib." 66
  fi
  source_lib="$(dirname "$source_lib")"

  if [[ -d "$RUNTIME_DIR" ]]; then
    local backup
    backup="$(backup_path "$RUNTIME_DIR")"
    mv "$RUNTIME_DIR" "$backup"
    info "Backed up existing runtime: $backup"
  fi

  mkdir -p "$RUNTIME_LIB_DIR"
  cp -Rp "$source_lib/." "$RUNTIME_LIB_DIR/"
  info "Installed runtime dylib: $RUNTIME_DYLIB"
}

main() {
  TMPDIR_PATH="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR_PATH"' EXIT

  validate_app
  detect_target_python
  install_sdk_deps
  install_runtime
  install_game_files

  if [[ "$RUNTIME_VERSION" == "v0.1.18" ]]; then
    warn "v0.1.18 is the public TTS runtime but predates the macOS QoS latency fix."
    warn "Use OCTOMIL_RUNTIME_VERSION=v0.1.19 or newer for embedded Ren'Py hosts."
  fi

  echo
  echo "Installed Octomil Ren'Py local TTS."
  echo "Runtime dylib:"
  echo "  $RUNTIME_DYLIB"
  echo
  echo "Verify:"
  echo "  $ROOT/scripts/verify.py \"$APP\""
}

main "$@"
