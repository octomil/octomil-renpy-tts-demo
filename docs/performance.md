# Performance Notes

Kokoro 82M is small enough to run locally, but it is still a real neural TTS
model. A good Ren'Py integration should hide model startup and keep live
synthesis as the fallback path.

## Targets

Ideal playback target:

- cached line: immediate,
- prefetched line: immediate,
- warmed fresh line: roughly sub-second to low-single-digit seconds depending
  on host and text length,
- true process-cold first line: multi-second.

True process-cold sub-500ms Kokoro generation is not realistic. To make the
first visible line feel fast, warm the model before gameplay and prefetch known
dialogue.

## Runtime Fixes Needed

The current public `v0.1.18` TTS runtime has the public `tts` flavor and Kokoro
support, but predates the macOS QoS latency fix. In GUI hosts, that older
runtime can be scheduled poorly under render-loop contention.

Use the first runtime release after the QoS fix once it exists, then set:

```bash
OCTOMIL_RUNTIME_VERSION=v0.1.19 ./scripts/install_macos.sh /Applications/MyRenPyGame.app
```

## Practical Pattern

1. Install the SDK/runtime into the app bundle.
2. Warm Kokoro during a splash screen, settings screen, or first idle moment.
3. Prefetch the next few dialogue lines.
4. Cancel/prune stale speculative work when the player advances quickly.
5. Let cache hits play immediately.

For premium main-cast quality, generate/bake those lines offline and keep
Kokoro as the local fallback for dynamic or unbaked text.
