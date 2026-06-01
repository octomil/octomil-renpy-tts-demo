# Performance Notes

These numbers came from the macOS Ren'Py/Eternum validation bundle and native
Kokoro runtime work.

## Before Runtime Fixes

Native streaming inside Ren'Py could take tens of seconds for a single fresh
line:

```text
setup=9956ms eng_ttfb=35003ms total=44960ms
```

Standalone synthesis was much faster, which pointed to embedded-host scheduling
and runtime overhead rather than raw model speed alone.

## Runtime Fixes

The native runtime fix set addressed:

- macOS QoS for TTS stream and batch worker threads,
- TTS thread count no longer pinned to one worker,
- file digest caching for the 326 MB Kokoro model,
- process-global warmed `OfflineTts` engine reuse,
- real TTS prewarm during `oct_model_warm`.

## After Runtime Fixes

Without explicit warmup:

```text
first speech.create: ~4.3s
later speech.create: ~0.9s
speech.stream: ~0.66-1.0s
```

With explicit SDK/app warmup:

```text
warmup: ~4.8s
first visible speech.create after warmup: ~0.89s
speech.stream after warmup: ~0.68-1.0s
```

## Practical Target

True process-cold sub-500ms Kokoro generation is not realistic. The useful
target is:

- warm before the first visible line,
- cache known lines,
- prefetch upcoming lines,
- keep live synthesis as the fallback path.
