## Drop-in local TTS via Octomil.
##
## App-owned responsibilities in this file:
##   - Ren'Py callback hook
##   - speaker/tag -> voice lookup
##   - Ren'Py text cleanup
##   - AST lookahead for prefetch
##   - Ren'Py sound playback
##
## Octomil owns the generic TTS machinery:
##   - client lifecycle + warmup
##   - generated WAV cache
##   - async worker loop
##   - foreground/speculative priority
##   - stale-job pruning on rapid advance

init -10 python:
    import hashlib
    import json
    import os
    import re
    import sys
    import sysconfig as _sc

    OCTOMIL_ORG_ID = "renpy-local-tts"
    OCTOMIL_SERVER_KEY = "local-only-no-cloud"
    OCTOMIL_MODEL = "kokoro-82m"
    OCTOMIL_DEPS = os.path.join(config.basedir, "lib", "octomil-deps")
    OCTOMIL_RUNTIME_VERSION = os.environ.get("OCTOMIL_RUNTIME_VERSION", "v0.1.18")
    OCTOMIL_RUNTIME_DYLIB = os.environ.get(
        "OCTOMIL_RUNTIME_DYLIB",
        os.path.join(
            config.basedir,
            "lib", "octomil-runtime", OCTOMIL_RUNTIME_VERSION, "tts", "lib",
            "liboctomil-runtime.dylib",
        ),
    )

    DEFAULT_VOICE = "af_bella"
    VOICE_MAP_PATH = os.path.join(config.gamedir, "octomil_voice_map.json")
    TTS_CACHE_DIR = os.path.join(config.gamedir, "cache", "tts_octomil")
    OCTOMIL_LOG = os.path.join(TTS_CACHE_DIR, "debug.log")
    PREFETCH_LOOKAHEAD = 2
    PLAY_CHANNEL = "sound"

    try:
        os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    def _octomil_log(msg):
        try:
            with open(OCTOMIL_LOG, "a") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    _octomil_log("---- octomil_tts.rpy init ----")

    if os.path.isdir(OCTOMIL_DEPS) and OCTOMIL_DEPS not in sys.path:
        sys.path.insert(0, OCTOMIL_DEPS)

    os.environ.setdefault("OCTOMIL_ORG_ID", OCTOMIL_ORG_ID)
    os.environ.setdefault("OCTOMIL_SERVER_KEY", OCTOMIL_SERVER_KEY)
    os.environ.setdefault("OCTOMIL_RUNTIME_DYLIB", OCTOMIL_RUNTIME_DYLIB)
    os.environ.setdefault("OCTOMIL_RUNTIME_FLAVOR", "tts")
    os.environ.setdefault("OCTOMIL_SHERPA_PROVIDER", "cpu")

    _SYSCONFIG_SHIM = {
        "get_config_var": lambda n: None,
        "get_config_vars": (lambda *a: ([None] * len(a) if a else {})),
        "get_python_version": lambda: "3.9",
        "get_platform": lambda: "macosx-11.0-arm64",
        "get_scheme_names": lambda: ("posix_prefix",),
        "get_default_scheme": lambda: "posix_prefix",
        "get_preferred_scheme": lambda kind="prefix": "posix_prefix",
        "get_paths": (lambda *a, **k: {
            "stdlib": os.path.dirname(_sc.__file__),
            "platstdlib": os.path.dirname(_sc.__file__),
            "purelib": getattr(_sc, "PURELIB", ""),
            "platlib": getattr(_sc, "PLATLIB", ""),
            "include": "",
            "platinclude": "",
            "scripts": os.path.dirname(sys.executable),
            "data": sys.prefix,
        }),
        "parse_config_h": lambda *a, **k: {},
        "_get_sysconfigdata_name": lambda: "_sysconfigdata__darwin_darwin",
    }
    for _k, _v in _SYSCONFIG_SHIM.items():
        if not hasattr(_sc, _k):
            setattr(_sc, _k, _v)

    from octomil.integrations.local_tts import LocalTTSLine, LocalTTSPipeline

    def _octomil_key_variants(key):
        if not key or not isinstance(key, str):
            return []
        normalized = re.sub(r"\s+", " ", key.strip().lower())
        if not normalized:
            return []
        compact = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        variants = [normalized]
        if compact:
            variants.extend([
                compact,
                compact.replace(" ", "_"),
                compact.replace(" ", ""),
            ])
        deduped = []
        for variant in variants:
            if variant and variant not in deduped:
                deduped.append(variant)
        return deduped

    def _load_voice_data():
        try:
            with open(VOICE_MAP_PATH, "r") as f:
                data = json.load(f)
            aliases = data.get("aliases") or {}
            pool = data.get("voice_pool") or []
            return aliases, pool
        except Exception as e:
            _octomil_log("voice map load failed: " + repr(e))
            return {}, []

    VOICE_MAP, VOICE_POOL = _load_voice_data()
    if not VOICE_POOL:
        VOICE_POOL = [DEFAULT_VOICE]

    def _octomil_voice_for_key(key):
        variants = _octomil_key_variants(key)
        for variant in variants:
            if variant in VOICE_MAP:
                return VOICE_MAP[variant]
        if variants:
            idx = int(hashlib.md5(variants[0].encode("utf-8")).hexdigest(), 16) % len(VOICE_POOL)
            return VOICE_POOL[idx]
        return DEFAULT_VOICE

    def _octomil_voice_for(who):
        name = ""
        if who is not None:
            name = getattr(who, "name", None) or ""
            if not isinstance(name, str):
                name = str(name)
        try:
            tag = getattr(store, "_last_say_who", None)
        except Exception:
            tag = None
        try:
            who_name = getattr(store, "_last_say_who_name", None)
        except Exception:
            who_name = None
        for candidate in (name.strip(), who_name, tag, who if isinstance(who, str) else None):
            if candidate and isinstance(candidate, str) and candidate.strip():
                voice = _octomil_voice_for_key(candidate)
                _octomil_log("speaker: name=%r tag=%r who_name=%r voice=%s key=%r" % (
                    name, tag, who_name, voice, candidate))
                return voice
        return DEFAULT_VOICE

    _RPY_PAUSE_RE = re.compile(r"\{p(?:=[^}]*)?\}")
    _RPY_TAG_RE = re.compile(r"\{[^}]*\}")
    _STAGE_RE = re.compile(r"\*([^*]+)\*")
    _STUTTER_RE = re.compile(r"\b((?:[A-Za-z]\s*[-–—]\s*)+)([A-Za-z][A-Za-z']*)")
    _VOCALIZATION_RE = re.compile(r"\b(?:h+m+|u+m+|a+h+|o+h+|e+h+)\b", re.IGNORECASE)
    _MULTISPACE_RE = re.compile(r"\s+")

    def _octomil_normalize_stutters(text):
        def repl(match):
            letters = re.findall(r"[A-Za-z]", match.group(1))
            word = match.group(2)
            if letters and all(ch.lower() == word[0].lower() for ch in letters):
                return word
            return match.group(0)
        return _STUTTER_RE.sub(repl, text)

    def _octomil_normalize_vocalizations(text):
        def repl(match):
            value = match.group(0).lower()
            if value.startswith("h"):
                return "Hmm"
            if value.startswith("u"):
                return "Um"
            if value.startswith("a"):
                return "Ah"
            if value.startswith("o"):
                return "Oh"
            if value.startswith("e"):
                return "Eh"
            return match.group(0)
        return _VOCALIZATION_RE.sub(repl, text)

    def _octomil_clean(text):
        if not text:
            return ""
        s = _RPY_PAUSE_RE.sub(". ", text)
        s = _STAGE_RE.sub(" ", s)
        s = _RPY_TAG_RE.sub(" ", s)
        s = _octomil_normalize_stutters(s)
        s = _octomil_normalize_vocalizations(s)
        s = s.replace("*", "")
        return _MULTISPACE_RE.sub(" ", s).strip()

    def _octomil_audio_data(abs_path):
        try:
            with open(abs_path, "rb") as f:
                blob = f.read()
            return renpy.audio.audio.AudioData(blob, os.path.basename(abs_path))
        except Exception as e:
            _octomil_log("audio_data load err: " + repr(e))
            return abs_path

    def _octomil_play_wav(abs_path):
        renpy.sound.play(_octomil_audio_data(abs_path), channel=PLAY_CHANNEL)

    _octomil_tts = LocalTTSPipeline(
        model=OCTOMIL_MODEL,
        cache_dir=TTS_CACHE_DIR,
        play=_octomil_play_wav,
        policy="private",
        log=_octomil_log,
    )
    _octomil_tts.start()

    def _octomil_line_for_tag(tag, raw):
        if not raw:
            return None
        try:
            substituted = renpy.substitute(raw)
        except Exception:
            substituted = raw
        cleaned = _octomil_clean(substituted)
        if not cleaned:
            return None
        voice = _octomil_voice_for_key(tag if isinstance(tag, str) else None)
        return LocalTTSLine(cleaned, voice)

    def _octomil_prefetch_upcoming():
        try:
            ctx = renpy.game.context()
            current_name = ctx.current
            node = renpy.game.script.lookup(current_name) if current_name else None
        except Exception as e:
            _octomil_log("prefetch ctx err: " + repr(e))
            return
        lines = []
        steps = 0
        while node is not None and len(lines) < PREFETCH_LOOKAHEAD and steps < 80:
            steps += 1
            try:
                node = getattr(node, "next", None)
            except Exception as e:
                _octomil_log("prefetch next err: " + repr(e))
                return
            if node is None:
                break
            if type(node).__name__ not in ("Say", "TranslateSay"):
                continue
            line = _octomil_line_for_tag(getattr(node, "who", None), getattr(node, "what", None))
            if line is not None:
                _octomil_log("prefetch hit#%d: tag=%r voice=%s text=%r" % (
                    len(lines) + 1, getattr(node, "who", None), line.voice, line.text[:40]))
                lines.append(line)
        if lines:
            _octomil_tts.prefetch(lines)

    def octomil_tts_say(who, what):
        text = _octomil_clean(what)
        if not text:
            _octomil_tts.clear_current()
            return
        try:
            if renpy.game.preferences.get_volume("sfx") <= 0.01:
                renpy.game.preferences.set_volume("sfx", 1.0)
            renpy.game.preferences.set_mute("sfx", False)
        except Exception:
            pass
        voice = _octomil_voice_for(who)
        result = _octomil_tts.play_current(LocalTTSLine(text, voice))
        _octomil_log("say result=%s voice=%s text=%r" % (result.status, voice, text[:40]))
        _octomil_prefetch_upcoming()

    def _octomil_character_callback(event, interact=True, **kwargs):
        if event != "begin":
            return
        what = kwargs.get("what")
        if what is None:
            what = getattr(store, "_last_say_what", None)
        who = kwargs.get("who")
        if who is None:
            who = getattr(store, "_last_say_who", None)
        octomil_tts_say(who, what)

    if _octomil_character_callback not in config.all_character_callbacks:
        config.all_character_callbacks.append(_octomil_character_callback)
