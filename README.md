# Octomil Ren'Py Local TTS Demo

Drop-in local text-to-speech for a Ren'Py visual novel using Octomil, Kokoro
82M, and the native Octomil runtime.

This repository is a small integration template. It does not include game
assets, cached audio, proprietary scripts, or a production cast map.

## Demo

The full screen recording is intentionally not committed to git. Upload it as a
GitHub Release asset and link it here once available:

```md
[Watch the demo](https://github.com/octomil/octomil-renpy-tts-demo/releases/download/v0.1-demo/renpy-octomil-tts-demo.mov)
```

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
- Octomil native runtime `tts` flavor.

`v4.17.31` includes the reusable `octomil.integrations.local_tts` pipeline used
by this demo. The current runtime `v0.1.18` has the `tts` flavor and Kokoro
support, but predates the macOS QoS latency fix. Use `v0.1.19` or newer once
that runtime release is available.

If the runtime release is still private, export `GITHUB_TOKEN` or `GH_TOKEN`
with access to `octomil/octomil-runtime` before running the installer. For a
fully public demo, the runtime release asset must be publicly downloadable too.

## Install Into A Local App Bundle

```bash
./scripts/install_macos.sh /Applications/MyRenPyGame.app
```

The installer:

- backs up any existing `game/octomil_tts.rpy`,
- backs up any existing `game/octomil_voice_map.json`,
- installs Octomil SDK deps into `Contents/Resources/autorun/lib/octomil-deps`,
- installs the native TTS runtime into `Contents/Resources/autorun/lib/octomil-runtime/<version>/tts`,
- copies the Ren'Py script and example voice map into the app.

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

If you installed a runtime version other than `v0.1.18`, pass the same version
to the verifier:

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
2. Merge and release the runtime macOS QoS latency fix.
3. Set `OCTOMIL_RUNTIME_VERSION` in docs/examples to that released runtime.
4. Run the installer and verifier against a clean Ren'Py app bundle.
