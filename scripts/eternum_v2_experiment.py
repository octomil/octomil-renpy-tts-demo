#!/usr/bin/env python3
"""Prepare an Eternum-style v2 emotional TTS experiment packet.

The script intentionally does not require proprietary game scripts. Point it at
one or more Ren'Py `.rpy` files or a directory, and it writes a small reviewable
experiment bundle:

    lines.jsonl
    performance.json
    voice_profiles.template.json
    bake_manifest.template.json
    review.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import re
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


CANONICAL_EMOTIONS = (
    "neutral",
    "teasing",
    "hurt",
    "afraid",
    "relieved",
    "angry",
    "sad",
    "warm",
    "urgent",
    "embarrassed",
)

TARGET_EXPERIMENT_EMOTIONS = ("neutral", "teasing", "hurt", "afraid", "relieved")

VOICE_FALLBACKS = {
    "alex": "af_sarah",
    "alexandra": "af_sarah",
    "annie": "bf_lily",
    "dalia": "af_sky",
    "luna": "af_nova",
    "nancy": "af_nicole",
    "nova": "af_jessica",
    "penelope": "af_heart",
    "orion": "am_michael",
    "protagonist": "am_michael",
}

SPEAKER_NORMALIZATIONS = {
    "mc": "Protagonist",
    "pov": "Protagonist",
    "narrator": "Narrator",
    "unknown": "Unknown",
    "???": "Unknown",
}

SAY_RE = re.compile(
    r"""^\s*(?P<speaker>[A-Za-z_][A-Za-z0-9_]*|\?\?\?)?\s*(?:\([^)]*\)\s*)?(?P<quote>['"])(?P<text>.*)(?P=quote)\s*(?:#.*)?$"""
)
LABEL_RE = re.compile(r"^\s*label\s+([A-Za-z_][A-Za-z0-9_.]*)\s*:")
TRANSLATE_RE = re.compile(r"^\s*translate\s+\w+\s+([A-Za-z_][A-Za-z0-9_.]*)\s*:")
RPY_TAG_RE = re.compile(r"\{[^}]*\}")
RPY_PAUSE_RE = re.compile(r"\{p(?:=[^}]*)?\}")
STAGE_RE = re.compile(r"\*([^*]+)\*")
MULTISPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z']+")


@dataclass(frozen=True)
class ScriptLine:
    line_id: str
    source: str
    source_line: int
    label: str
    speaker: str
    text: str
    text_hash: str


@dataclass(frozen=True)
class Performance:
    line_id: str
    source: str
    source_line: int
    label: str
    speaker: str
    text: str
    text_hash: str
    emotion: str
    intensity: float
    pace: str
    volume: str
    energy: str
    delivery: str
    voice_profile: str
    fallback_voice: str
    rationale: list[str]
    performance_hash: str


def main() -> int:
    repo_dir = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Build an Eternum v2 emotional TTS experiment packet from Ren'Py script text.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Ren'Py .rpy files or directories. Defaults to the bundled fixture.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for the experiment packet.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum lines to include in the experiment packet.",
    )
    parser.add_argument(
        "--min-per-emotion",
        type=int,
        default=3,
        help="Try to include at least this many lines for each target emotion.",
    )
    parser.add_argument(
        "--app-slug",
        default="eternum",
        help="Slug used in generated ids and manifest metadata.",
    )
    args = parser.parse_args()

    root = pathlib.Path.cwd()
    input_paths = [pathlib.Path(p) for p in args.inputs]
    if not input_paths:
        input_paths = [repo_dir / "fixtures" / "eternum_sample.rpy"]
    out_dir = pathlib.Path(args.out) if args.out else repo_dir / "experiments" / "eternum-v2" / "sample"

    files = list(iter_rpy_files(input_paths))
    if not files:
        print("No .rpy files found.", file=sys.stderr)
        return 65

    lines = extract_lines(files, root=root, app_slug=args.app_slug)
    if not lines:
        print("No dialogue lines found.", file=sys.stderr)
        return 66

    performances = [direct_performance(line) for line in lines]
    selected = select_experiment_lines(performances, limit=args.limit, min_per_emotion=args.min_per_emotion)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(out_dir, selected, files=files, app_slug=args.app_slug)

    print("wrote", out_dir)
    print("lines", len(selected))
    counts: dict[str, int] = {}
    for perf in selected:
        counts[perf.emotion] = counts.get(perf.emotion, 0) + 1
    for emotion in sorted(counts):
        print(f"{emotion}: {counts[emotion]}")
    return 0


def iter_rpy_files(paths: Sequence[pathlib.Path]) -> Iterable[pathlib.Path]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*.rpy")):
                if "cache" not in child.parts:
                    yield child
        elif path.suffix.lower() == ".rpy":
            yield path


def extract_lines(files: Sequence[pathlib.Path], *, root: pathlib.Path, app_slug: str) -> list[ScriptLine]:
    records: list[ScriptLine] = []
    for file_path in files:
        label = "script"
        rel = relative_for_id(file_path, root)
        try:
            raw_lines = file_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raw_lines = file_path.read_text(encoding="latin-1").splitlines()
        label_counts: dict[str, int] = {}
        for lineno, raw in enumerate(raw_lines, start=1):
            label_match = LABEL_RE.match(raw) or TRANSLATE_RE.match(raw)
            if label_match:
                label = label_match.group(1)
                continue
            match = SAY_RE.match(raw)
            if not match:
                continue
            text = clean_text(match.group("text"))
            if not text:
                continue
            speaker = normalize_speaker(match.group("speaker"))
            label_counts[label] = label_counts.get(label, 0) + 1
            line_id = make_line_id(app_slug, rel, label, label_counts[label], lineno)
            text_hash = digest_text(text)
            records.append(
                ScriptLine(
                    line_id=line_id,
                    source=rel,
                    source_line=lineno,
                    label=label,
                    speaker=speaker,
                    text=text,
                    text_hash=text_hash,
                )
            )
    return records


def clean_text(text: str) -> str:
    text = RPY_PAUSE_RE.sub(". ", text)
    text = STAGE_RE.sub(" ", text)
    text = RPY_TAG_RE.sub(" ", text)
    text = text.replace("\\\"", '"').replace("\\'", "'")
    text = text.replace("~", " ")
    return MULTISPACE_RE.sub(" ", text).strip()


def normalize_speaker(speaker: str | None) -> str:
    if not speaker:
        return "Narrator"
    key = speaker.strip().lower()
    if key in SPEAKER_NORMALIZATIONS:
        return SPEAKER_NORMALIZATIONS[key]
    return speaker.strip().replace("_", " ").title()


def relative_for_id(file_path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return file_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file_path.name


def make_line_id(app_slug: str, source: str, label: str, label_index: int, lineno: int) -> str:
    source_slug = re.sub(r"[^a-zA-Z0-9]+", "_", source).strip("_").lower()
    label_slug = re.sub(r"[^a-zA-Z0-9]+", "_", label).strip("_").lower() or "script"
    short = hashlib.sha1(f"{source}:{lineno}".encode("utf-8")).hexdigest()[:8]
    return f"{app_slug}_{label_slug}_{label_index:04d}_{short}"


def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def direct_performance(line: ScriptLine) -> Performance:
    lower = line.text.lower()
    words = [w.lower() for w in WORD_RE.findall(line.text)]
    rationale: list[str] = []

    emotion = "neutral"
    intensity = 0.25
    pace = "normal"
    volume = "normal"
    energy = "normal"

    if any(w in lower for w in ("thank god", "came back", "safe", "relieved", "finally")):
        emotion = "relieved"
        intensity = 0.55
        pace = "slow"
        volume = "soft"
        energy = "restrained"
        rationale.append("relief cue")
    if any(w in lower for w in ("scared", "afraid", "hide", "run", "danger", "please", "help", "don't move", "outside the door", "heard that too")):
        emotion = "afraid"
        intensity = max(intensity, 0.68)
        pace = "quick"
        volume = "soft"
        energy = "intense"
        rationale.append("fear cue")
    if any(w in lower for w in ("hurt", "fine", "whatever", "leave me", "don't care", "forgot", "missed you", "miss you")):
        emotion = "hurt"
        intensity = max(intensity, 0.52)
        pace = "slow"
        volume = "soft"
        energy = "restrained"
        rationale.append("hurt cue")
    if any(w in lower for w in ("idiot", "hate ", "angry", "shut up", "damn")):
        emotion = "angry"
        intensity = max(intensity, 0.7)
        pace = "quick"
        volume = "firm"
        energy = "intense"
        rationale.append("anger cue")
    if any(w in lower for w in ("haha", "tease", "cute", "blush", "pervert", "mr.", "mister", "little", "ridiculous", "oh, sure", "hero", "holding my hand")):
        emotion = "teasing"
        intensity = max(intensity, 0.48)
        pace = "normal"
        volume = "normal"
        energy = "bright"
        rationale.append("teasing cue")
    if any(w in lower for w in ("sorry", "miss you", "alone", "cry", "lost")):
        emotion = "sad"
        intensity = max(intensity, 0.58)
        pace = "slow"
        volume = "soft"
        energy = "low"
        rationale.append("sadness cue")

    if "..." in line.text:
        intensity = min(0.85, intensity + 0.1)
        if pace == "normal":
            pace = "slow"
        rationale.append("ellipsis")
    if "!" in line.text:
        intensity = min(0.95, intensity + 0.12)
        if emotion in ("afraid", "angry", "urgent"):
            volume = "raised"
        rationale.append("exclamation")
    if "?" in line.text and emotion == "neutral":
        emotion = "warm"
        intensity = 0.35
        rationale.append("question")
    if len(words) <= 4 and emotion == "neutral":
        pace = "slow"
        intensity = 0.3
        rationale.append("short line")

    delivery = delivery_text(emotion, intensity, pace, volume, energy)
    voice_profile = speaker_to_profile(line.speaker)
    fallback_voice = fallback_voice_for(line.speaker)
    body = {
        "line_id": line.line_id,
        "emotion": emotion,
        "intensity": intensity,
        "pace": pace,
        "volume": volume,
        "energy": energy,
        "delivery": delivery,
        "voice_profile": voice_profile,
    }
    performance_hash = "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not rationale:
        rationale.append("default")
    return Performance(
        line_id=line.line_id,
        source=line.source,
        source_line=line.source_line,
        label=line.label,
        speaker=line.speaker,
        text=line.text,
        text_hash=line.text_hash,
        emotion=emotion,
        intensity=round(intensity, 2),
        pace=pace,
        volume=volume,
        energy=energy,
        delivery=delivery,
        voice_profile=voice_profile,
        fallback_voice=fallback_voice,
        rationale=rationale,
        performance_hash=performance_hash,
    )


def delivery_text(emotion: str, intensity: float, pace: str, volume: str, energy: str) -> str:
    intensity_word = "restrained"
    if intensity >= 0.75:
        intensity_word = "strong"
    elif intensity >= 0.5:
        intensity_word = "clear but controlled"
    if emotion == "neutral":
        return f"{intensity_word}, conversational, {pace} pace"
    if emotion == "teasing":
        return f"{intensity_word}, playful, {energy} energy"
    if emotion == "hurt":
        return f"{intensity_word}, guarded, {volume} volume"
    if emotion == "afraid":
        return f"{intensity_word}, tense, {pace} pace"
    if emotion == "relieved":
        return f"{intensity_word}, softened, {pace} pace"
    return f"{intensity_word}, {emotion}, {pace} pace, {volume} volume"


def speaker_to_profile(speaker: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", speaker.lower()).strip("_") or "narrator"
    return f"{slug}_v2"


def fallback_voice_for(speaker: str) -> str:
    key = speaker.lower()
    return VOICE_FALLBACKS.get(key, "af_bella")


def select_experiment_lines(
    performances: Sequence[Performance],
    *,
    limit: int,
    min_per_emotion: int,
) -> list[Performance]:
    selected: list[Performance] = []
    seen: set[str] = set()

    for emotion in TARGET_EXPERIMENT_EMOTIONS:
        matches = [p for p in performances if p.emotion == emotion]
        matches.sort(key=lambda p: (-p.intensity, p.line_id))
        for perf in matches[:min_per_emotion]:
            if perf.line_id not in seen:
                selected.append(perf)
                seen.add(perf.line_id)

    remaining = [p for p in performances if p.line_id not in seen]
    remaining.sort(key=lambda p: (p.emotion not in TARGET_EXPERIMENT_EMOTIONS, -p.intensity, p.line_id))
    for perf in remaining:
        if len(selected) >= limit:
            break
        selected.append(perf)
        seen.add(perf.line_id)

    return selected[:limit]


def write_outputs(out_dir: pathlib.Path, performances: Sequence[Performance], *, files: Sequence[pathlib.Path], app_slug: str) -> None:
    lines_path = out_dir / "lines.jsonl"
    perf_path = out_dir / "performance.json"
    profiles_path = out_dir / "voice_profiles.template.json"
    manifest_path = out_dir / "bake_manifest.template.json"
    realtime_policy_path = out_dir / "realtime_policy.template.json"
    review_path = out_dir / "review.csv"
    readme_path = out_dir / "README.md"

    with lines_path.open("w", encoding="utf-8") as f:
        for perf in performances:
            f.write(json.dumps(line_record(perf), sort_keys=True) + "\n")

    perf_payload = {
        "version": 1,
        "app_slug": app_slug,
        "source_files": [str(path) for path in files],
        "canonical_emotions": list(CANONICAL_EMOTIONS),
        "lines": [asdict(perf) for perf in performances],
    }
    perf_path.write_text(json.dumps(perf_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    profiles_path.write_text(
        json.dumps({"version": 1, "profiles": build_voice_profiles(performances)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(build_manifest_template(performances), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    realtime_policy_path.write_text(
        json.dumps(build_realtime_policy_template(performances), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_review_csv(review_path, performances)
    readme_path.write_text(readme_text(performances), encoding="utf-8")


def line_record(perf: Performance) -> dict[str, object]:
    return {
        "line_id": perf.line_id,
        "source": perf.source,
        "source_line": perf.source_line,
        "label": perf.label,
        "speaker": perf.speaker,
        "text": perf.text,
        "text_hash": perf.text_hash,
        "voice_profile": perf.voice_profile,
        "fallback_voice": perf.fallback_voice,
        "emotion": perf.emotion,
        "intensity": perf.intensity,
        "performance_hash": perf.performance_hash,
    }


def build_voice_profiles(performances: Sequence[Performance]) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    for perf in performances:
        if perf.voice_profile in profiles:
            continue
        profiles[perf.voice_profile] = {
            "speaker": perf.speaker,
            "fallback_voice": perf.fallback_voice,
            "reference_prompt": f"assets/voice_prompts/{perf.voice_profile}.wav",
            "style": f"{perf.speaker}: {perf.delivery}",
            "default_pace": perf.pace,
            "default_energy": perf.energy,
        }
    return profiles


def build_manifest_template(performances: Sequence[Performance]) -> dict[str, object]:
    entries = []
    for perf in performances:
        entries.append(
            {
                "line_id": perf.line_id,
                "speaker": perf.speaker,
                "text_hash": perf.text_hash,
                "performance_hash": perf.performance_hash,
                "audio": f"voice/{perf.line_id}.wav",
                "fallback_voice": perf.fallback_voice,
                "duration_ms": None,
                "lufs": None,
                "status": "needs_generation",
            }
        )
    return {
        "version": 2,
        "engine": "unselected",
        "entries": entries,
    }


def build_realtime_policy_template(performances: Sequence[Performance]) -> dict[str, object]:
    profiles = sorted({perf.voice_profile for perf in performances})
    return {
        "version": 1,
        "routes": [
            "baked_approved",
            "live_cache",
            "expressive_realtime",
            "kokoro_realtime",
        ],
        "latency_budget_ms": {
            "cache_hit": 50,
            "prefetch": 250,
            "foreground": 1200,
            "fallback": 1800,
        },
        "fallbacks": {
            "baked_missing": "expressive_realtime",
            "expressive_realtime_unavailable": "kokoro_realtime",
            "foreground_budget_exceeded": "kokoro_realtime",
        },
        "kokoro_realtime": {
            "model": "kokoro-82m",
            "route": "local_first",
            "compile_controls": ["voice", "speed", "punctuation"],
        },
        "expressive_realtime": {
            "model": "unselected",
            "route": "local_first",
            "compile_controls": ["style_prompt", "emotion", "intensity", "voice_profile"],
            "required_voice_profiles": profiles,
        },
    }


def write_review_csv(path: pathlib.Path, performances: Sequence[Performance]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=(
                "line_id",
                "source",
                "source_line",
                "label",
                "speaker",
                "emotion",
                "intensity",
                "pace",
                "volume",
                "energy",
                "fallback_voice",
                "text",
                "delivery",
                "rationale",
                "approval",
                "notes",
            ),
        )
        writer.writeheader()
        for perf in performances:
            writer.writerow(
                {
                    "line_id": perf.line_id,
                    "source": perf.source,
                    "source_line": perf.source_line,
                    "label": perf.label,
                    "speaker": perf.speaker,
                    "emotion": perf.emotion,
                    "intensity": perf.intensity,
                    "pace": perf.pace,
                    "volume": perf.volume,
                    "energy": perf.energy,
                    "fallback_voice": perf.fallback_voice,
                    "text": perf.text,
                    "delivery": perf.delivery,
                    "rationale": "; ".join(perf.rationale),
                    "approval": "",
                    "notes": "",
                }
            )


def readme_text(performances: Sequence[Performance]) -> str:
    counts: dict[str, int] = {}
    speakers: dict[str, int] = {}
    for perf in performances:
        counts[perf.emotion] = counts.get(perf.emotion, 0) + 1
        speakers[perf.speaker] = speakers.get(perf.speaker, 0) + 1
    counts_text = "\n".join(f"- {name}: {counts[name]}" for name in sorted(counts))
    speakers_text = "\n".join(f"- {name}: {speakers[name]}" for name in sorted(speakers))
    return f"""# Eternum v2 TTS Experiment Packet

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

{counts_text}

## Speaker Counts

{speakers_text}

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
"""


if __name__ == "__main__":
    raise SystemExit(main())
