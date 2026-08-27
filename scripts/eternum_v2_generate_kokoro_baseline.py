#!/usr/bin/env python3
"""Generate Kokoro baseline WAVs for an Eternum v2 experiment packet."""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import time
from typing import Any


PACE_SPEED = {
    "very_slow": 0.82,
    "slow": 0.9,
    "normal": 1.0,
    "quick": 1.08,
    "rushed": 1.15,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Kokoro baseline WAVs for a v2 TTS packet.")
    parser.add_argument(
        "packet",
        nargs="?",
        default="experiments/eternum-v2/sample",
        help="Experiment packet directory containing performance.json.",
    )
    parser.add_argument("--model", default="kokoro-82m")
    parser.add_argument("--policy", default="local_first")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    packet = pathlib.Path(args.packet).resolve()
    performance_path = packet / "performance.json"
    if not performance_path.exists():
        print(f"Missing {performance_path}")
        return 65

    try:
        from octomil import Octomil
    except Exception as exc:
        print("Could not import octomil. Run inside the demo SDK environment.")
        print(repr(exc))
        return 66

    return asyncio.run(generate(packet, performance_path, args.model, args.policy, args.limit, Octomil))


async def generate(
    packet: pathlib.Path,
    performance_path: pathlib.Path,
    model: str,
    policy: str,
    limit: int | None,
    octomil_cls: Any,
) -> int:
    payload = json.loads(performance_path.read_text(encoding="utf-8"))
    lines = list(payload.get("lines") or [])
    if limit is not None:
        lines = lines[:limit]
    out_dir = packet / "audio" / "kokoro-baseline"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = octomil_cls.from_env()
    await client.initialize()

    manifest_entries = []
    failures = 0
    for index, line in enumerate(lines, start=1):
        line_id = line["line_id"]
        voice = line["fallback_voice"]
        text = line["text"]
        speed = PACE_SPEED.get(line.get("pace", "normal"), 1.0)
        output_path = out_dir / f"{line_id}.wav"
        started = time.monotonic()
        try:
            response = await client.audio.speech.create(
                model=model,
                input=text,
                voice=voice,
                response_format="wav",
                speed=speed,
                policy=policy,
                cache="off",
            )
            data = response.audio_bytes
            output_path.write_bytes(data)
            elapsed_ms = round((time.monotonic() - started) * 1000.0)
            status = "generated"
            size = len(data)
        except Exception as exc:
            failures += 1
            elapsed_ms = round((time.monotonic() - started) * 1000.0)
            status = "failed"
            size = 0
            print(f"[{index}/{len(lines)}] FAIL {line_id}: {exc!r}")
        else:
            print(f"[{index}/{len(lines)}] OK {line_id} {size} bytes {elapsed_ms}ms")

        manifest_entries.append(
            {
                "line_id": line_id,
                "speaker": line["speaker"],
                "text_hash": line["text_hash"],
                "performance_hash": line["performance_hash"],
                "audio": str(output_path.relative_to(packet)),
                "engine": model,
                "voice": voice,
                "speed": speed,
                "status": status,
                "bytes": size,
                "elapsed_ms": elapsed_ms,
            }
        )

    manifest = {
        "version": 2,
        "engine": model,
        "variant": "kokoro-baseline",
        "entries": manifest_entries,
    }
    (packet / "bake_manifest.kokoro-baseline.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

