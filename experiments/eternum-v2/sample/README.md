# Eternum v2 TTS Experiment Packet

This packet is generated from script text only. It is ready for review and
live/offline TTS generation, but no line is approved until a human reviews the
audio.

The Kokoro baseline, when generated, is a control group. It validates routing,
voice selection, coarse speed, manifests, and review flow; it is not the
emotional v2 result. Richer `emotion`, `intensity`, and `delivery` fields are
inputs for the expressive real-time compiler and optional bake worker.

## Files

- `lines.jsonl`: compact line records for workers.
- `performance.json`: full emotion and delivery sidecars.
- `voice_profiles.template.json`: voice profile stubs to fill with owned or licensed prompt clips.
- `bake_manifest.template.json`: manifest shape the Ren'Py playback layer should consume.
- `realtime_policy.template.json`: live synthesis route order, latency budgets, and fallbacks.
- `review.csv`: spreadsheet-friendly review queue.

## Emotion Counts

- afraid: 5
- hurt: 3
- relieved: 2
- sad: 1
- teasing: 4

## Speaker Counts

- Alex: 2
- Annie: 2
- Dalia: 2
- Luna: 3
- Nancy: 2
- Nova: 2
- Penelope: 2

## Next Commands

Run this same script against real game scripts:

```bash
python3 scripts/eternum_v2_experiment.py /path/to/game --out experiments/eternum-v2/real-run
```

Then fill `voice_profiles.template.json`, generate WAVs with the chosen
expressive backend, and update `bake_manifest.template.json` statuses to
`approved` only after review.

To generate the Kokoro baseline once the local SDK/runtime environment is
available:

```bash
python3 scripts/eternum_v2_generate_kokoro_baseline.py experiments/eternum-v2/sample
```
