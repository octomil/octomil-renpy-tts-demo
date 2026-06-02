# Octomil Ren'Py Local TTS Demo

Drop-in local text-to-speech for a Ren'Py visual novel using Octomil, Kokoro
82M, and the native Octomil runtime.

This repository is a small integration template. It does not include game
assets, cached audio, proprietary scripts, or a production cast map.

## Download

- [Download the self-contained macOS arm64 demo package](https://github.com/octomil/octomil-renpy-tts-demo/releases/download/v0.1.0/octomil-renpy-tts-demo-v0.1.0-macos-arm64.zip)
- [Checksum](https://github.com/octomil/octomil-renpy-tts-demo/releases/download/v0.1.0/octomil-renpy-tts-demo-v0.1.0-macos-arm64.zip.sha256)

The screen recording is intentionally not committed to git. Attach it to the
same GitHub Release when a local copy is available.

## What It Does

- Loads the Octomil Python SDK from a Ren'Py app bundle.
- Runs local-only Kokoro TTS through the native Octomil runtime.
- Uses no cloud key and makes no server call for local inference.
- Prewarms the model on a background thread before dialogue needs audio.
- Plays generated audio into Ren'Py's configured sound channel.
- Caches generated WAVs by `voice + text`, so repeated lines play instantly.
- Prefetches upcoming dialogue and prunes stale work when the player advances.

## Files

- [game/octomil_tts.rpy](game/octomil_tts.rpy): thin drop-in Ren'Py script.
- [game/octomil_voice_map.json](game/octomil_voice_map.json): neutral example speaker/tag voice map.
- [scripts/install_macos.sh](scripts/install_macos.sh): installs the script, SDK deps, and runtime into a macOS Ren'Py app bundle.
- [scripts/verify.py](scripts/verify.py): verifies SDK/runtime/native Kokoro synthesis from an installed bundle.
- [docs/architecture.md](docs/architecture.md): integration architecture.
- [docs/performance.md](docs/performance.md): latency notes and realistic targets.

## Requirements

- Apple Silicon macOS Ren'Py app bundle.
- Host `python3` with `pip`, used only to stage target-platform wheels.
- Octomil Python SDK `v4.17.31` or newer.
- Octomil native runtime `v0.1.19` `tts` flavor or newer.

`v4.17.31` includes the reusable `octomil.integrations.local_tts` pipeline used
by this demo. Runtime `v0.1.19` includes native Kokoro support and the macOS QoS
fix needed for embedded hosts such as Ren'Py.

The GitHub Release zip is self-contained: it includes a target-platform SDK
wheelhouse, the native runtime archive, and the Kokoro model archive under
`vendor/`, so installation and first local synthesis do not need network access.

## Install Into A Local App Bundle

Download and unzip the latest release asset:

```text
octomil-renpy-tts-demo-v0.1.0-macos-arm64.zip
```

Then run:

```bash
./scripts/install_macos.sh /Applications/MyRenPyGame.app
```

The installer:

- backs up any existing `game/octomil_tts.rpy`,
- backs up any existing `game/octomil_voice_map.json`,
- installs Octomil SDK deps into `Contents/Resources/autorun/lib/octomil-deps`,
- installs the native TTS runtime into `Contents/Resources/autorun/lib/octomil-runtime/<version>/tts`,
- installs Kokoro into `Contents/Resources/autorun/lib/octomil-models/kokoro-82m`,
- copies the Ren'Py script and example voice map into the app.

If you are using a source checkout instead of the release zip, the same
installer downloads the SDK wheel and runtime release asset unless you provide a
local `vendor/` directory.

Version overrides:

```bash
OCTOMIL_SDK_VERSION=4.17.31 \
OCTOMIL_RUNTIME_VERSION=v0.1.19 \
./scripts/install_macos.sh /Applications/MyRenPyGame.app
```

Then verify:

```bash
./scripts/verify.py /Applications/MyRenPyGame.app
```

If you override the runtime version, pass the same version to the verifier:

```bash
OCTOMIL_RUNTIME_VERSION=v0.1.19 ./scripts/verify.py /Applications/MyRenPyGame.app
```

## What Lives Where

Octomil owns the reusable TTS machinery:

- client lifecycle and warmup,
- generated WAV cache,
- async synthesis worker,
- foreground vs speculative priority,
- stale-job pruning on rapid advance,
- late-play suppression.

The Ren'Py script owns only game/framework glue:

- character callback hook,
- speaker/tag to voice lookup,
- text cleanup,
- AST lookahead,
- Ren'Py sound playback.

The voice map is app content and intentionally lives in
`game/octomil_voice_map.json`, not in the Octomil SDK.

## Voice Mapping

Kokoro 82M exposes 53 voices. Most visual novels have more characters than that,
so this demo treats Kokoro voices as archetypes rather than one unique voice per
character.

The included map is intentionally tiny and neutral:

```text
Alice Beaumont -> af_bella
Ben Harper     -> bm_fable
Cora Ames      -> af_sky
Darius Quinn   -> am_michael
Elena Cross    -> bf_lily
Frank Warden   -> am_fenrir
Narrator       -> af_heart
Unknown        -> am_puck
```

Replace it with your own app's cast map. The SDK pipeline does not know about
your characters.

## Known Limits

- True process-cold Kokoro startup is multi-second because the model is large.
- The practical first-line path is background prewarm plus prefetch/cache.
- 53 voices cannot create a large cast of genuinely unique performances.
- For premium main-cast quality, use a baked/offline voice pipeline and keep
  Kokoro as the local fallback.

## Publishing Checklist

1. Upload the demo `.mov` as a GitHub Release asset.
2. Run `scripts/package_release.sh`.
3. Upload `dist/octomil-renpy-tts-demo-<version>-macos-arm64.zip` and its
   `.sha256` file as GitHub Release assets.
4. Run the installer and verifier against a clean Ren'Py app bundle.
