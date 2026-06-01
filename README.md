# Octomil Ren'Py Local TTS Demo

Drop-in local TTS for a Ren'Py visual novel using Octomil, Kokoro 82M, and the
native Octomil runtime.

This repository packages the integration work in a way another developer can
pick up without reading the original debugging thread. Eternum is used as the
worked example because it has a large cast and exposed the hard parts: embedded
Python 3.9, native runtime bundling, cold-start latency, per-line caching, and
many-character voice mapping.

This project does not include game assets, cached audio, proprietary content,
or the game itself. It is not affiliated with the game developer.

## Demo

The full screen recording is intentionally not committed to git. Upload it as a
GitHub Release asset and link it here once available:

```md
[Watch the demo](https://github.com/octomil/octomil-renpy-tts-demo/releases/download/v0.1-demo/eternum-octomil-tts-demo.mov)
```

## What It Does

- Loads the Octomil Python SDK from a Ren'Py app bundle.
- Runs local-only Kokoro TTS through the native Octomil runtime.
- Uses no cloud key and makes no server call for local inference.
- Prewarms the model on a background thread before dialogue needs audio.
- Streams generated audio into Ren'Py's voice channel.
- Caches generated WAVs by `voice + text`, so repeated lines play instantly.
- Maps VNDB's 116 Eternum characters to supported Kokoro voices and aliases.

## Files

- [game/octomil_tts.rpy](game/octomil_tts.rpy): drop-in Ren'Py script.
- [scripts/install_macos.sh](scripts/install_macos.sh): copies the script into a macOS Ren'Py app bundle.
- [scripts/verify.py](scripts/verify.py): verifies SDK/runtime/native Kokoro synthesis from an installed bundle.
- [data/voice_map_aliases.json](data/voice_map_aliases.json): generated alias-to-voice table.
- [data/vndb_voice_audit.json](data/vndb_voice_audit.json): generated VNDB character audit.
- [docs/architecture.md](docs/architecture.md): integration architecture.
- [docs/performance.md](docs/performance.md): latency notes and before/after numbers.

## Requirements

- macOS Ren'Py app bundle.
- Apple Silicon is the tested target.
- Octomil Python SDK with:
  - keyless local client support,
  - Python 3.9-safe generated types,
  - native Kokoro routing.
- Octomil native runtime with:
  - `tts` flavor,
  - Kokoro support,
  - native TTS latency/prewarm fixes.

For the current internal validation build, the app bundle uses:

```text
Contents/Resources/autorun/lib/octomil-deps/
Contents/Resources/autorun/lib/octomil-runtime/pr100/tts/lib/liboctomil-runtime.dylib
```

## Install Into A Local App Bundle

```bash
./scripts/install_macos.sh /Applications/Eternum-tts.app
```

The script backs up an existing `game/octomil_tts.rpy` and copies in the drop-in
script. It does not copy or download the SDK/runtime; those must already be
present in the app bundle or installed by your packaging flow.

Then verify:

```bash
./scripts/verify.py /Applications/Eternum-tts.app
```

## Voice Mapping

Kokoro 82M exposes 53 voices. Eternum has 116 VNDB-listed characters. The map
therefore treats Kokoro voices as archetypes rather than one unique voice per
character.

The current map:

- pins all 116 VNDB characters by full name,
- pins known Ren'Py short tags such as `mc`, `x`, `a`, `d`, `no`, `cha`, `ma`,
- normalizes punctuation and spacing for names such as `Mr. Hernandez`,
- validates that no mapped voice is unsupported,
- validates that VNDB male/female markers do not map to the opposite voice
  gender unless explicitly overridden.

Example mappings:

```text
Orion Richards          -> am_michael
Alexandra Bardot        -> af_sarah
Annie Winters           -> bf_lily
Chang Wong              -> bm_fable
Dalia Carter            -> af_sky
Luna Hernandez          -> af_nova
Nancy Carter            -> af_nicole
Nova Johnson            -> af_jessica
Penelope Paige Carter   -> af_heart
Axel Bardot             -> am_fenrir
Victor Hernandez        -> em_alex
Praetorian              -> hf_beta
```

## Known Limits

- True process-cold Kokoro startup is multi-second because the model is large.
- The practical first-line path is background prewarm plus prefetch/cache.
- 53 voices cannot create 116 genuinely unique character performances.
- For premium main-cast quality, use a baked/offline voice pipeline and keep
  Kokoro as the local fallback.

## Publishing Checklist

1. Create a public repo, preferably `octomil-renpy-tts-demo`.
2. Commit source/docs/scripts only.
3. Upload the demo `.mov` as a GitHub Release asset.
4. Replace the local demo path in this README with the release URL.
5. Confirm runtime/SDK release versions are public and installable.
6. Add a short disclaimer that the integration is unofficial and ships no game
   assets.
