#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEMO_VERSION="${OCTOMIL_DEMO_VERSION:-v0.1.0}"
SDK_VERSION="${OCTOMIL_SDK_VERSION:-4.17.31}"
SDK_TAG="v${SDK_VERSION#v}"
SDK_VERSION="${SDK_TAG#v}"
RUNTIME_VERSION="${OCTOMIL_RUNTIME_VERSION:-v0.1.19}"
RUNTIME_TAG="v${RUNTIME_VERSION#v}"
RUNTIME_VERSION="$RUNTIME_TAG"

PY_VERSION_DOT="${OCTOMIL_PY_VERSION:-3.9}"
PY_ABI="${OCTOMIL_PY_ABI:-cp39}"
PY_PLATFORM="${OCTOMIL_PIP_PLATFORM:-macosx_11_0_arm64}"

RUNTIME_ASSET="liboctomil-runtime-${RUNTIME_VERSION}-tts-darwin-arm64.tar.gz"
SDK_WHEEL_URL="${OCTOMIL_SDK_WHEEL_URL:-https://github.com/octomil/octomil-python/releases/download/${SDK_TAG}/octomil-${SDK_VERSION}-py3-none-any.whl}"
RUNTIME_URL="${OCTOMIL_RUNTIME_URL:-https://github.com/octomil/octomil-runtime/releases/download/${RUNTIME_VERSION}/${RUNTIME_ASSET}}"
KOKORO_ASSET="${OCTOMIL_KOKORO_ASSET:-kokoro-multi-lang-v1_0.tar.bz2}"
KOKORO_URL="${OCTOMIL_KOKORO_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/${KOKORO_ASSET}}"

# Pinned expected sha256 of each input; required, no defaults.
SDK_WHEEL_SHA256="${OCTOMIL_SDK_WHEEL_SHA256:-}"
RUNTIME_SHA256="${OCTOMIL_RUNTIME_SHA256:-}"
KOKORO_SHA256="${OCTOMIL_KOKORO_SHA256:-}"

DIST="$ROOT/dist"
WORK="$DIST/work"
PACKAGE_NAME="octomil-renpy-tts-demo-${DEMO_VERSION}-macos-arm64"
PACKAGE_DIR="$WORK/$PACKAGE_NAME"
ZIP_PATH="$DIST/${PACKAGE_NAME}.zip"

info() {
  printf '\033[1;34m==>\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31merror:\033[0m %s\n' "$1" >&2
  exit "${2:-1}"
}

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    error "shasum or sha256sum is required." 69
  fi
}

# Fails closed: an empty expected hash is an error, never a skip.
verify_pinned() {
  local path="$1"
  local expected="$2"
  local var="$3"
  local actual

  if [[ -z "$expected" ]]; then
    error "$var is required: set it to the expected sha256 of $(basename "$path")." 66
  fi
  actual="$(sha256_of "$path")"
  expected="$(printf '%s' "$expected" | tr 'A-F' 'a-f')"
  if [[ "$actual" != "$expected" ]]; then
    error "sha256 mismatch for $(basename "$path"): expected $expected, got $actual." 66
  fi
}

download() {
  local url="$1"
  local dest="$2"
  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

  if [[ -n "$token" && "$url" == https://github.com/* ]]; then
    curl -fsSL -H "Authorization: Bearer $token" "$url" -o "$dest"
  else
    curl -fsSL "$url" -o "$dest"
  fi
}

runtime_source() {
  if [[ -n "${OCTOMIL_RUNTIME_ARCHIVE:-}" ]]; then
    printf '%s\n' "$OCTOMIL_RUNTIME_ARCHIVE"
    return
  fi

  local sibling="$ROOT/../octomil-runtime/$RUNTIME_ASSET"
  if [[ -f "$sibling" ]]; then
    printf '%s\n' "$sibling"
    return
  fi

  printf '%s\n' ""
}

download_runtime_archive() {
  local dest="$1"

  if command -v gh >/dev/null 2>&1; then
    gh release download "$RUNTIME_VERSION" \
      --repo octomil/octomil-runtime \
      --pattern "$RUNTIME_ASSET" \
      --dir "$(dirname "$dest")" \
      --clobber
    return
  fi

  download "$RUNTIME_URL" "$dest"
}

for _var in OCTOMIL_SDK_WHEEL_SHA256 OCTOMIL_RUNTIME_SHA256 OCTOMIL_KOKORO_SHA256; do
  [[ -n "${!_var:-}" ]] || error "$_var is required (expected sha256 of the pinned artifact)." 66
done

rm -rf "$WORK"
mkdir -p "$PACKAGE_DIR/vendor/wheelhouse" "$DIST"

info "Copying demo files..."
rsync -a \
  --exclude '.git' \
  --exclude 'dist' \
  --exclude 'vendor' \
  --exclude '__pycache__' \
  "$ROOT/" "$PACKAGE_DIR/"

info "Staging Octomil SDK wheelhouse for Ren'Py Python ${PY_VERSION_DOT} (${PY_PLATFORM}, ${PY_ABI})..."
SDK_WHEEL_DIR="$WORK/sdk-wheel"
SDK_WHEEL_PATH="$SDK_WHEEL_DIR/$(basename "${SDK_WHEEL_URL%%\?*}")"
mkdir -p "$SDK_WHEEL_DIR"
download "$SDK_WHEEL_URL" "$SDK_WHEEL_PATH"
verify_pinned "$SDK_WHEEL_PATH" "$SDK_WHEEL_SHA256" OCTOMIL_SDK_WHEEL_SHA256
python3 -m pip download \
  --disable-pip-version-check \
  --dest "$PACKAGE_DIR/vendor/wheelhouse" \
  --platform "$PY_PLATFORM" \
  --python-version "$PY_VERSION_DOT" \
  --implementation cp \
  --abi "$PY_ABI" \
  --only-binary=:all: \
  "$SDK_WHEEL_PATH" \
  cffi

source_archive="$(runtime_source)"
if [[ -n "$source_archive" ]]; then
  info "Using local runtime archive: $source_archive"
  cp "$source_archive" "$PACKAGE_DIR/vendor/$RUNTIME_ASSET"
else
  info "Downloading runtime archive: $RUNTIME_ASSET"
  download_runtime_archive "$PACKAGE_DIR/vendor/$RUNTIME_ASSET"
fi
verify_pinned "$PACKAGE_DIR/vendor/$RUNTIME_ASSET" "$RUNTIME_SHA256" OCTOMIL_RUNTIME_SHA256

if [[ -n "${OCTOMIL_KOKORO_ARCHIVE:-}" ]]; then
  info "Using local Kokoro archive: $OCTOMIL_KOKORO_ARCHIVE"
  cp "$OCTOMIL_KOKORO_ARCHIVE" "$PACKAGE_DIR/vendor/$KOKORO_ASSET"
else
  info "Downloading Kokoro model archive: $KOKORO_URL"
  download "$KOKORO_URL" "$PACKAGE_DIR/vendor/$KOKORO_ASSET"
fi
verify_pinned "$PACKAGE_DIR/vendor/$KOKORO_ASSET" "$KOKORO_SHA256" OCTOMIL_KOKORO_SHA256

(
  cd "$PACKAGE_DIR/vendor"
  shasum -a 256 "$RUNTIME_ASSET" "$KOKORO_ASSET" > SHA256SUMS
)

info "Writing package manifest..."
cat > "$PACKAGE_DIR/PACKAGE.md" <<EOF
# Octomil Ren'Py TTS Demo ${DEMO_VERSION}

This package is self-contained for Apple Silicon macOS Ren'Py bundles:

- Octomil SDK ${SDK_TAG} wheelhouse for CPython ${PY_VERSION_DOT} arm64
- Octomil runtime ${RUNTIME_VERSION} tts/darwin-arm64 dylib archive
- Kokoro 82M v1.0 model archive
- Ren'Py drop-in script and example voice map

Install:

\`\`\`bash
./scripts/install_macos.sh /Applications/MyRenPyGame.app
./scripts/verify.py /Applications/MyRenPyGame.app
\`\`\`
EOF

info "Creating $ZIP_PATH..."
rm -f "$ZIP_PATH"
(
  cd "$WORK"
  zip -qr "$ZIP_PATH" "$PACKAGE_NAME"
)

shasum -a 256 "$ZIP_PATH" > "$ZIP_PATH.sha256"
ls -lh "$ZIP_PATH" "$ZIP_PATH.sha256"
