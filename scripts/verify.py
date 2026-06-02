#!/usr/bin/env python3
import asyncio
import os
import pathlib
import subprocess
import sys
import textwrap


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/RenPyGame.app", file=sys.stderr)
        return 64

    app = pathlib.Path(sys.argv[1]).resolve()
    autorun = app / "Contents" / "Resources" / "autorun"
    py = app / "Contents" / "MacOS" / "python"
    deps = autorun / "lib" / "octomil-deps"
    runtime_version = os.environ.get("OCTOMIL_RUNTIME_VERSION", "v0.1.19")
    dylib = autorun / "lib" / "octomil-runtime" / runtime_version / "tts" / "lib" / "liboctomil-runtime.dylib"

    missing = [str(p) for p in (autorun, py, deps, dylib) if not p.exists()]
    if missing:
        print("Missing required paths:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 65

    code = textwrap.dedent(
        f"""
        import asyncio, os, sys, sysconfig
        sys.path.insert(0, {str(deps)!r})
        os.environ.setdefault("OCTOMIL_RUNTIME_DYLIB", {str(dylib)!r})
        os.environ.setdefault("OCTOMIL_RUNTIME_FLAVOR", "tts")
        os.environ.setdefault("OCTOMIL_SHERPA_PROVIDER", "cpu")
        os.environ.setdefault("OCTOMIL_ORG_ID", "renpy-local-verify")
        os.environ.setdefault("OCTOMIL_SERVER_KEY", "local-only-no-cloud")

        _SYSCONFIG_SHIM = {{
            "get_config_var": lambda n: None,
            "get_config_vars": (lambda *a: ([None] * len(a) if a else {{}})),
            "get_python_version": lambda: "3.9",
            "get_platform": lambda: "macosx-11.0-arm64",
            "get_scheme_names": lambda: ("posix_prefix",),
            "get_default_scheme": lambda: "posix_prefix",
            "get_preferred_scheme": lambda kind="prefix": "posix_prefix",
            "get_paths": (lambda *a, **k: {{
                "stdlib": os.path.dirname(sysconfig.__file__),
                "platstdlib": os.path.dirname(sysconfig.__file__),
                "purelib": getattr(sysconfig, "PURELIB", ""),
                "platlib": getattr(sysconfig, "PLATLIB", ""),
                "include": "",
                "platinclude": "",
                "scripts": os.path.dirname(sys.executable),
                "data": sys.prefix,
            }}),
            "parse_config_h": lambda *a, **k: {{}},
            "_get_sysconfigdata_name": lambda: "_sysconfigdata__darwin_darwin",
        }}
        for key, value in _SYSCONFIG_SHIM.items():
            if not hasattr(sysconfig, key):
                setattr(sysconfig, key, value)

        from octomil import Octomil

        async def run():
            client = Octomil()
            await client.initialize()
            warm = client.warmup(model="kokoro-82m", capability="tts", policy="local_first")
            if hasattr(warm, "__await__"):
                warm = await warm
            response = await client.audio.speech.create(
                model="kokoro-82m",
                voice="af_sarah",
                input="Local Kokoro TTS is working.",
                response_format="wav",
                policy="local_first",
            )
            data = getattr(response, "audio_bytes", None)
            if data is None:
                raise TypeError("Unsupported speech response shape: " + repr(type(response)))
            print("warmup_loaded", getattr(warm, "backend_loaded", "?"))
            print("audio_bytes", len(data))

        asyncio.run(run())
        """
    )

    env = os.environ.copy()
    result = subprocess.run([str(py), "-c", code], text=True, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
