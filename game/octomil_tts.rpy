## Drop-in local TTS via the Octomil SDK (4.12.4+).
##
## Bootstraps the octomil[tts] deps from autorun/lib/octomil-deps, runs Kokoro
## on-device through sherpa-onnx, caches WAVs under game/cache/tts_octomil/,
## plays them on Ren'Py's voice channel. Any failure is non-fatal — the game
## just plays silently.

init -10 python:
    import os, sys, json, hashlib, threading, traceback, re, struct, time

    # Local-only TTS needs NO real credentials. The kokoro-82m recipe is
    # static inside the SDK and its weights download from a PUBLIC GitHub
    # release (github.com/k2-fsa/sherpa-onnx/releases) — no Octomil key is
    # used for model resolution, download, or on-device inference. from_env()
    # only checks these are *non-empty*; it does NOT validate them against
    # the server for local use, and the local path emits no telemetry. So we
    # ship harmless placeholders.
    #
    # SECURITY: never embed an `oct_sk_live_...` server key in a distributed
    # build — it is plainly extractable from the app bundle and grants access
    # to the org's API/quota/billing. The previously-embedded live key has
    # been removed here and MUST be revoked in the Octomil dashboard.
    OCTOMIL_ORG_ID     = "eternum-tts-local"
    OCTOMIL_SERVER_KEY = "local-only-no-cloud"
    OCTOMIL_MODEL      = "kokoro-82m"
    OCTOMIL_DEPS       = os.path.join(config.basedir, "lib", "octomil-deps")
    OCTOMIL_RUNTIME_DYLIB = os.path.join(
        config.basedir,
        "lib", "octomil-runtime", "pr100", "tts", "lib",
        "liboctomil-runtime.dylib",
    )

    # Octomil 4.13.0 ships Kokoro 82M v1.0 multi-lang (53 voices) and the
    # voice→sid mismatch is fixed — voice names now resolve correctly.
    DEFAULT_VOICE = "af_bella"
    VOICE_POOL = [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah",
        "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir",
        "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel",
        "bm_fable", "bm_george", "bm_lewis", "ef_dora", "em_alex",
        "ff_siwis", "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
        "if_sara", "im_nicola", "jf_alpha", "jf_gongitsune",
        "jf_nezumi", "jf_tebukuro", "jm_kumo", "pf_dora", "pm_alex",
        "pm_santa", "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao",
        "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia",
        "zm_yunyang",
    ]

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

    # Per-character voice overrides. Eternum often exposes Ren'Py tag-only
    # speakers (`mc`, `x`, `a`, etc.), so each voice is pinned by short tag,
    # nickname, and display/full-name aliases where known.
    VOICE_MAP = {}
    def _pin_voice(voice, *keys):
        for key in keys:
            for variant in _octomil_key_variants(key):
                VOICE_MAP[variant] = voice

    # Main cast.
    _pin_voice("am_michael", "mc", "orion", "orion richards", "protagonist", "player name")
    _pin_voice("af_sarah", "x", "alex", "alexandra", "alexandra bardot")
    _pin_voice("bf_lily", "a", "annie", "annie winters")
    _pin_voice("bm_fable", "c", "chang", "chang wong")
    _pin_voice("af_sky", "d", "dal", "dalia", "dalia carter")
    _pin_voice("af_nova", "l", "luna", "lunita", "luny", "luna hernandez")
    _pin_voice("af_nicole", "n", "nan", "nancy", "nancy carter")
    _pin_voice("af_jessica", "no", "nova", "delilah", "delilah warren", "cheeto", "nova johnson")
    _pin_voice("af_heart", "p", "pen", "penny", "penelope", "penelope carter", "penelope paige carter")

    # Side cast.
    _pin_voice("am_fenrir", "ax", "axel", "axel bardot")
    _pin_voice("am_onyx", "ben", "benja", "benjamin", "benjamin dawson")
    _pin_voice("bm_fable", "chop chop", "chop-chop", "bonsai shearer", "gypsy goldtooth", "quantum quasar starlord")
    _pin_voice("bm_fable", "je", "jerry", "jeremaine", "jeremaine of noriander")
    _pin_voice("bm_george", "maximo")
    _pin_voice("af_river", "micaela", "micaela garcia")
    _pin_voice("am_onyx", "founder", "the founder")
    _pin_voice("em_alex", "her", "victor", "victor hernandez", "hernandez", "mr hernandez", "mr. hernandez")
    _pin_voice("am_onyx", "william", "william bardot")
    _pin_voice("af_river", "cha", "charlotte")
    _pin_voice("af_jessica", "ma", "maat")
    _pin_voice("bf_isabella", "ca", "calypso")

    # Make-an-appearance / recurring world voices.
    _pin_voice("jm_kumo", "akira")
    _pin_voice("bm_george", "alastor", "alastor linus")
    _pin_voice("bm_fable", "alfonso")
    _pin_voice("bf_isabella", "alice", "mr mos wife", "mr. mos wife")
    _pin_voice("af_aoede", "alicia", "alicia flink")
    _pin_voice("hf_alpha", "anastasia")
    _pin_voice("af_kore", "anna", "anna piaget")
    _pin_voice("bf_lily", "annie flink", "anne flink")
    _pin_voice("bm_daniel", "arannis", "arannis thornvale", "general arannis")
    _pin_voice("af_alloy", "aspen", "aspen simmons")
    _pin_voice("af_sky", "astrocorp employee")
    _pin_voice("am_echo", "avery")
    _pin_voice("bf_lily", "aysha")
    _pin_voice("am_santa", "balbus", "balbus bundledore")
    _pin_voice("bm_lewis", "bennie", "bennie garrington")
    _pin_voice("am_echo", "bobbie", "bobbie briggs")
    _pin_voice("am_fenrir", "brock", "brock domen")
    _pin_voice("af_sky", "carolyn")
    _pin_voice("am_liam", "cassian")
    _pin_voice("bf_lily", "chloe")
    _pin_voice("bm_george", "cicero")
    _pin_voice("bm_lewis", "clarence", "clarence ruiz")
    _pin_voice("hm_omega", "clonk")
    _pin_voice("bm_george", "commander hasler", "hasler")
    _pin_voice("am_onyx", "con")
    _pin_voice("bm_lewis", "cornelius", "cornelius garrington")
    _pin_voice("af_kore", "dolores")
    _pin_voice("ff_siwis", "dona", "dona mandrake")
    _pin_voice("bm_lewis", "dr du pont", "dr. du pont", "du pont")
    _pin_voice("am_fenrir", "elliot", "elliot cook")
    _pin_voice("bm_lewis", "emperor claudius", "emperor claudius iii", "claudius")
    _pin_voice("am_puck", "enzo")
    _pin_voice("bf_emma", "eva")
    _pin_voice("af_river", "falazio")
    _pin_voice("bm_lewis", "gemini", "the blind oracle")
    _pin_voice("af_alloy", "gertrude", "gerty")
    _pin_voice("af_kore", "harley", "harley jones")
    _pin_voice("am_eric", "haskel")
    _pin_voice("bf_isabella", "helga", "helga owler")
    _pin_voice("em_alex", "hugo", "hugo hernandez")
    _pin_voice("hf_alpha", "idriel", "the eternum lady")
    _pin_voice("af_kore", "irina", "irina mercer", "doctor mercer", "dr mercer", "dr. mercer")
    _pin_voice("bf_isabella", "jade")
    _pin_voice("bm_daniel", "jasper", "jasper wagner", "colonel wagner")
    _pin_voice("am_fenrir", "jasticus", "jasticus the decapitator")
    _pin_voice("af_jessica", "judith")
    _pin_voice("am_liam", "kainan", "kai")
    _pin_voice("af_sky", "katniss")
    _pin_voice("am_puck", "kermit")
    _pin_voice("af_sky", "kitty")
    _pin_voice("bf_isabella", "lisa", "lisa astor")
    _pin_voice("bf_lily", "lorelei")
    _pin_voice("am_eric", "lucas")
    _pin_voice("af_nicole", "lucinda", "lucinda garcia")
    _pin_voice("ef_dora", "luna grandma", "luna's grandma")
    _pin_voice("af_heart", "mad", "madam ambrose")
    _pin_voice("af_alloy", "madison")
    _pin_voice("bm_george", "marcellus")
    _pin_voice("af_alloy", "maria")
    _pin_voice("bm_fable", "marvolo")
    _pin_voice("am_santa", "maurice")
    _pin_voice("af_sky", "megan")
    _pin_voice("bm_fable", "melton")
    _pin_voice("bf_emma", "millie")
    _pin_voice("zf_xiaobei", "moon", "moon chi", "fang", "lee ha-jeong")
    _pin_voice("bm_lewis", "mr mos", "mr. mos")
    _pin_voice("af_aoede", "mysterious woman")
    _pin_voice("am_onyx", "nico", "nico valentino")
    _pin_voice("bm_george", "nikolay")
    _pin_voice("am_echo", "noah")
    _pin_voice("ef_dora", "olivia", "olivia hernandez")
    _pin_voice("am_santa", "pancho")
    _pin_voice("bm_fable", "philippe", "philly")
    _pin_voice("am_echo", "player")
    _pin_voice("hf_beta", "pra", "pra2", "praetorian")
    _pin_voice("bf_lily", "aaa", "princess anabelle", "anabelle")
    _pin_voice("bf_isabella", "priscilla", "priscilla bardot")
    _pin_voice("bm_daniel", "prof", "professor", "professor abbott", "abbott")
    _pin_voice("bm_fable", "professor connor", "connor")
    _pin_voice("bm_lewis", "professor keating", "keating")
    _pin_voice("hm_omega", "pyramid head", "pyri")
    _pin_voice("em_alex", "raul")
    _pin_voice("af_kore", "regina")
    _pin_voice("af_nicole", "san", "sandra")
    _pin_voice("zf_xiaoyi", "sister baek")
    _pin_voice("am_santa", "snuggles", "snuggles the happy bear")
    _pin_voice("bf_lily", "susie")
    _pin_voice("hf_beta", "tatiana")
    _pin_voice("bm_george", "tha", "thanatos", "thanny")
    _pin_voice("bm_lewis", "titus", "titus dubitatius")
    _pin_voice("am_puck", "vasil")
    _pin_voice("bf_lily", "warthogs student")
    _pin_voice("bm_lewis", "warthogs student ii", "warthogs student (ii)")
    _pin_voice("zf_xiaoni", "wenlin")
    _pin_voice("am_onyx", "xet")

    # Deliberate gender overrides from playtesting / user direction.
    _pin_voice("af_nicole", "mat", "matt")
    _pin_voice("af_nova", "girl", "blank", "bla", "unknown")
    _pin_voice("am_puck", "???")
    _pin_voice("am_adam", "class", "class2", "student")

    _TTS_CACHE_REL = os.path.join("cache", "tts_octomil")
    _TTS_CACHE_ABS = os.path.join(config.gamedir, _TTS_CACHE_REL)
    try:
        os.makedirs(_TTS_CACHE_ABS, exist_ok=True)
    except Exception:
        pass

    _OCTOMIL_LOG = os.path.join(_TTS_CACHE_ABS, "debug.log")
    def _octomil_log(msg):
        try:
            with open(_OCTOMIL_LOG, "a") as f:
                f.write(msg + "\n")
        except Exception:
            pass
    _octomil_log("---- octomil_tts.rpy init ----")

    # ---- 1. Bootstrap: sysconfig shim, env vars, sys.path ----
    if os.path.isdir(OCTOMIL_DEPS) and OCTOMIL_DEPS not in sys.path:
        sys.path.insert(0, OCTOMIL_DEPS)
    os.environ.setdefault("OCTOMIL_ORG_ID", OCTOMIL_ORG_ID)
    os.environ.setdefault("OCTOMIL_SERVER_KEY", OCTOMIL_SERVER_KEY)
    os.environ.setdefault("OCTOMIL_RUNTIME_DYLIB", OCTOMIL_RUNTIME_DYLIB)
    os.environ.setdefault("OCTOMIL_RUNTIME_FLAVOR", "tts")
    # Apple Silicon speed lever: route sherpa-onnx through the CoreML
    # execution provider (ANE/GPU) instead of plain CPU. Often 2-4x
    # faster for Kokoro on M-series. The SDK keeps "cpu" as its default
    # because CoreML has shown numerical-precision quirks on some Kokoro
    # graphs that surface as audio-quality regressions (not crashes).
    # setdefault means an externally exported OCTOMIL_SHERPA_PROVIDER
    # still wins, so to A/B or revert without editing this file:
    #   export OCTOMIL_SHERPA_PROVIDER=cpu
    # VERIFY after enabling: launch once, confirm TTS still plays, and
    # listen for any voice degradation. If quality regresses, flip to cpu.
    # Benchmarked on an M5 (engine RTF = synth_time / audio_duration, lower
    # is faster), all measured from this game's debug.log:
    #   fp32 + cpu     : 0.39   <- best, current
    #   int8 + cpu     : 0.69
    #   int8 + coreml  : 0.83
    # int8 quantization is ~1.75x SLOWER than fp32 here (ARM int8 kernels
    # don't beat Apple's fp32 Accelerate/AMX path), and CoreML adds partition
    # overhead rather than accelerating Kokoro. So: fp32 model + cpu provider.
    os.environ.setdefault("OCTOMIL_SHERPA_PROVIDER", "cpu")

    import sysconfig as _sc
    _SYSCONFIG_SHIM = {
        "get_config_var":      lambda n: None,
        "get_config_vars":     (lambda *a: ([None]*len(a) if a else {})),
        "get_python_version":  lambda: "3.9",
        "get_platform":        lambda: "macosx-11.0-arm64",
        "get_scheme_names":    lambda: ("posix_prefix",),
        "get_default_scheme":  lambda: "posix_prefix",
        "get_preferred_scheme":lambda kind="prefix": "posix_prefix",
        "get_paths":           (lambda *a, **k: {
            "stdlib": os.path.dirname(_sc.__file__),
            "platstdlib": os.path.dirname(_sc.__file__),
            "purelib": getattr(_sc, "PURELIB", ""),
            "platlib": getattr(_sc, "PLATLIB", ""),
            "include": "", "platinclude": "",
            "scripts": os.path.dirname(sys.executable), "data": sys.prefix,
        }),
        "parse_config_h":      lambda *a, **k: {},
        "_get_sysconfigdata_name": lambda: "_sysconfigdata__darwin_darwin",
    }
    for _k, _v in _SYSCONFIG_SHIM.items():
        if not hasattr(_sc, _k):
            setattr(_sc, _k, _v)

    # ---- 2. SDK init on a worker thread with a long-lived asyncio loop ----
    _octomil_state = {
        "client": None,
        "loop": None,
        "ready": False,
        "error": None,
        # abs_path of the line the player is currently on. Async synths
        # (live + deferred prefetch) check this before playing so a line
        # that finished synthesizing AFTER the player advanced doesn't talk
        # over the new line. Updated on every say (cancel-on-advance).
        "current_path": None,
    }

    def _octomil_loop_thread(state):
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            state["loop"] = loop

            from octomil import Octomil
            client = Octomil.from_env()
            loop.run_until_complete(client.initialize())
            # Warmup is a superset of prepare(): downloads bytes, constructs
            # the engine, calls backend.load_model(...), and caches the loaded
            # instance on the kernel — so the first dialogue line skips
            # the ~1.5s per-stream setup_ms we'd otherwise eat.
            try:
                t0 = time.monotonic()
                warm = client.warmup(
                    model=OCTOMIL_MODEL, capability="tts", policy="local_first",
                )
                if hasattr(warm, "__await__"):
                    warm = loop.run_until_complete(warm)
                _octomil_log(
                    "warmup OK loaded=%s latency_ms=%s elapsed=%.0fms" % (
                        getattr(warm, "backend_loaded", "?"),
                        getattr(warm, "latency_ms", "?"),
                        (time.monotonic() - t0) * 1000.0,
                    )
                )
            except Exception as e:
                # Fall back to prepare() if warmup isn't available on this SDK
                # version; first stream will pay setup_ms but everything works.
                _octomil_log("warmup failed (%s); falling back to prepare()" % repr(e))
                client._kernel.prepare(
                    model=OCTOMIL_MODEL, capability="tts", policy="local_first",
                )
            state["client"] = client
            state["ready"] = True
            loop.run_forever()
        except Exception as e:
            state["error"] = repr(e)
            print("[octomil_tts] init failed:", e)
            traceback.print_exc()

    _octomil_thread = threading.Thread(
        target=_octomil_loop_thread, args=(_octomil_state,),
        name="octomil-tts", daemon=True,
    )
    _octomil_thread.start()

    # ---- 3. Voice / path helpers ----
    def _octomil_voice_for_key(key):
        if key and isinstance(key, str):
            variants = _octomil_key_variants(key)
            if variants:
                for variant in variants:
                    if variant in VOICE_MAP:
                        return VOICE_MAP[variant]
                idx = int(hashlib.md5(variants[0].encode("utf-8")).hexdigest(), 16) % len(VOICE_POOL)
                return VOICE_POOL[idx]
        return DEFAULT_VOICE

    def _octomil_voice_for(who):
        name = ""
        if who is not None:
            name = getattr(who, "name", None) or ""
            if not isinstance(name, str):
                name = str(name)
        name = name.strip()
        # Also try a few alternate identity sources so renamable MCs and
        # narrator-style speakers are catchable in VOICE_MAP.
        try:
            tag = getattr(store, "_last_say_who", None)
        except Exception:
            tag = None
        try:
            who_name = getattr(store, "_last_say_who_name", None)
        except Exception:
            who_name = None
        for candidate in (name, who_name, tag, who if isinstance(who, str) else None):
            if candidate and isinstance(candidate, str) and candidate.strip():
                voice = _octomil_voice_for_key(candidate)
                _octomil_log("speaker: name=%r tag=%r who_name=%r who_repr=%r voice=%s key=%r" % (
                    name, tag, who_name, repr(who)[:80], voice, candidate))
                return voice
        voice = DEFAULT_VOICE
        _octomil_log("speaker: name=%r tag=%r who_name=%r who_repr=%r voice=%s key=None" % (
            name, tag, who_name, repr(who)[:80], voice))
        return voice

    def _octomil_paths(voice, text):
        h = hashlib.sha256((voice + "\x00" + text).encode("utf-8")).hexdigest()[:20]
        rel = _TTS_CACHE_REL.replace(os.sep, "/") + "/" + h + ".wav"
        return os.path.join(_TTS_CACHE_ABS, h + ".wav"), rel

    # ---- 4. Non-blocking synthesis ----
    # Synth runs on the worker loop; when the WAV lands, a done-callback
    # plays it on the sound channel (only if the user hasn't advanced past
    # this line). The say callback returns immediately so dialogue text
    # renders without waiting for audio.
    _octomil_pending = {}
    _octomil_pending_lock = threading.Lock()
    # abs_paths the player has landed on while a *speculative* (autoplay=False)
    # prefetch for that exact line is still in flight. The prefetch coroutine
    # doesn't play, so without this the line would synth silently. The synth
    # done-callback consults this set and plays the WAV when it lands.
    _octomil_play_wanted = set()

    # Resolve TtsRequestPriority — added in 4.15 (PR #485). Fall back to
    # plain strings if the enum isn't importable on older SDKs.
    try:
        from octomil.audio.scheduler import TtsRequestPriority
        _PRI_FOREGROUND  = TtsRequestPriority.FOREGROUND
        _PRI_SPECULATIVE = TtsRequestPriority.SPECULATIVE
    except Exception:
        _PRI_FOREGROUND  = "foreground"
        _PRI_SPECULATIVE = "speculative"

    def _wav_header_for(pcm_size, sample_rate, channels=1, bits=16):
        byte_rate = sample_rate * channels * bits // 8
        block_align = channels * bits // 8
        return struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + pcm_size, b"WAVE",
            b"fmt ", 16, 1, channels, sample_rate, byte_rate, block_align, bits,
            b"data", pcm_size,
        )

    def _write_wav(path, pcm_bytes, sample_rate):
        with open(path, "wb") as f:
            f.write(_wav_header_for(len(pcm_bytes), sample_rate))
            f.write(pcm_bytes)

    def _octomil_audio_data(abs_path):
        """Load a WAV from disk as in-memory AudioData. Bypasses Ren'Py's
        loader path resolution (which silently rejects abs paths outside
        the game/ root on some 8.x builds)."""
        try:
            with open(abs_path, "rb") as f:
                blob = f.read()
            return renpy.audio.audio.AudioData(blob, os.path.basename(abs_path))
        except Exception as e:
            _octomil_log("audio_data load err: " + repr(e))
            return abs_path  # fall back to path-based play

    def _stream_mode_str(started):
        # 4.14.0+: started.streaming_capability.mode is "sentence_chunk",
        # "progressive", or "final_chunk". 4.13.x had started.streaming_mode
        # ("realtime" or "final_chunk"). Try the new shape first.
        cap = getattr(started, "streaming_capability", None)
        if cap is not None:
            m = getattr(cap, "mode", None)
            if m is not None:
                return getattr(m, "value", str(m))
        m = getattr(started, "streaming_mode", None)
        if m is not None:
            return getattr(m, "value", str(m))
        return "?"

    # Modes that justify playing chunks as they arrive. For "final_chunk"
    # we only get one chunk at the end so there's no TTFB benefit — buffer
    # and play once via the cache-style path.
    _OCTOMIL_EAGER_MODES = ("sentence_chunk", "progressive", "realtime")

    def _log_stream_metrics(tag, voice, text, started, completed,
                            ttfb_caller_ms, chunk_count, bytes_total):
        # 4.15.0: legacy `latency_ms` / `first_chunk_ms` were removed in
        # favor of the "honest metrics" quartet:
        #   setup_ms — engine setup time per stream
        #   engine_first_chunk_ms — sherpa's actual synth-to-first-sample
        #   e2e_first_chunk_ms — end-to-end (setup + engine + queue)
        #   total_latency_ms — wall clock until completion
        try:
            setup = getattr(completed, "setup_ms", None)
            eng_ttfb = getattr(completed, "engine_first_chunk_ms", None)
            e2e_ttfb = getattr(completed, "e2e_first_chunk_ms", None)
            total = getattr(completed, "total_latency_ms", None)
            queued = getattr(completed, "queued_ms", None)
            dur = getattr(completed, "duration_ms", None)
            rtf = (dur / total) if (dur and total) else None
            mode = _stream_mode_str(started) if started is not None else "?"
            locality = getattr(started, "locality", "?") if started else "?"
            engine = getattr(started, "engine", "?") if started else "?"
            def f(v):
                return ("%.0f" % v) if v is not None else "?"
            _octomil_log(
                "%s voice=%s mode=%s loc=%s eng=%s "
                "setup=%sms eng_ttfb=%sms e2e_ttfb=%sms total=%sms "
                "ttfb_caller=%.0fms queued=%sms dur=%sms rtf=%s "
                "chunks=%d bytes=%d text=%r" % (
                    tag, voice, mode, locality, engine,
                    f(setup), f(eng_ttfb), f(e2e_ttfb), f(total),
                    ttfb_caller_ms or 0.0, f(queued), f(dur),
                    ("%.2f" % rtf) if rtf is not None else "?",
                    chunk_count, bytes_total, text[:60],
                )
            )
        except Exception as e:
            _octomil_log("metrics log err: " + repr(e))

    # Live-stream coroutine: collects PCM chunks from the engine, writes
    # the assembled WAV at abs_path, and plays it once. We don't bother
    # with per-chunk playback — Ren'Py's loader is unreliable on runtime
    # subdirs, and streaming benefit is sentence-bounded which means most
    # Eternum dialogue lines wouldn't see TTFB improvement anyway.
    async def _octomil_stream_live(client, voice, text, abs_path, rel_path):
        sample_rate = 24000
        pcm_chunks = []
        chunk_count = 0
        bytes_total = 0
        started = completed = None
        ttfb_caller_ms = None
        t0 = time.monotonic()
        # Foreground = the player is on this line right now. Scheduler
        # should preempt any in-flight speculative prefetches.
        try:
            stream_cm = client.audio.speech.stream(
                model=OCTOMIL_MODEL, input=text, voice=voice,
                response_format="pcm_s16le", policy="private",
                priority=_PRI_FOREGROUND,
            )
        except TypeError:
            # SDK older than 4.15 doesn't accept priority kwarg
            stream_cm = client.audio.speech.stream(
                model=OCTOMIL_MODEL, input=text, voice=voice,
                response_format="pcm_s16le", policy="private",
            )
        async with stream_cm as stream:
            async for event in stream:
                etype = type(event).__name__
                if etype == "SpeechStreamStarted":
                    started = event
                    sr = getattr(event, "sample_rate", None)
                    if sr:
                        sample_rate = sr
                elif etype == "SpeechAudioChunk":
                    data = getattr(event, "data", b"")
                    if not data:
                        continue
                    if ttfb_caller_ms is None:
                        ttfb_caller_ms = (time.monotonic() - t0) * 1000.0
                    pcm_chunks.append(data)
                    chunk_count += 1
                    bytes_total += len(data)
                elif etype == "SpeechStreamCompleted":
                    completed = event
        _log_stream_metrics("stream-live", voice, text, started, completed,
                            ttfb_caller_ms, chunk_count, bytes_total)
        # Assemble the complete WAV at the canonical cache path, then play.
        # Chunk-by-chunk playback was tried but Ren'Py's loader appears not
        # to reliably resolve files inside subdirectories at runtime, and
        # streaming TTFB benefit is sentence-bounded anyway.
        try:
            final_pcm = b"".join(pcm_chunks)
            if not final_pcm:
                return
            tmp = abs_path + ".part"
            _write_wav(tmp, final_pcm, sample_rate)
            os.replace(tmp, abs_path)
            if _octomil_state.get("current_path") != abs_path:
                # Player advanced past this line while it synthesized — the
                # WAV is cached for next time, but don't play it over the
                # line they're on now (cancel-on-advance).
                _octomil_log("live-play skip (advanced away) voice=%s" % voice)
                return
            try:
                renpy.sound.play(_octomil_audio_data(abs_path), channel=_OCTOMIL_PLAY_CHANNEL)
                _octomil_log("live-play OK voice=%s" % voice)
            except Exception as e:
                _octomil_log("live-play err: " + repr(e))
        except Exception as e:
            _octomil_log("assemble err: " + repr(e))

    # Cache-only coroutine for prefetch: streams to PCM, writes one WAV.
    # No playback during the stream — just builds the cache entry.
    # Submitted at SPECULATIVE priority so the scheduler yields to any
    # foreground request the player triggers before this finishes.
    async def _octomil_stream_cache(client, voice, text, abs_path):
        sample_rate = 24000
        pcm_chunks = []
        chunk_count = 0
        bytes_total = 0
        started = completed = None
        ttfb_caller_ms = None
        t0 = time.monotonic()
        try:
            stream_cm = client.audio.speech.stream(
                model=OCTOMIL_MODEL, input=text, voice=voice,
                response_format="pcm_s16le", policy="private",
                priority=_PRI_SPECULATIVE,
            )
        except TypeError:
            stream_cm = client.audio.speech.stream(
                model=OCTOMIL_MODEL, input=text, voice=voice,
                response_format="pcm_s16le", policy="private",
            )
        async with stream_cm as stream:
            async for event in stream:
                etype = type(event).__name__
                if etype == "SpeechStreamStarted":
                    started = event
                    sr = getattr(event, "sample_rate", None)
                    if sr:
                        sample_rate = sr
                elif etype == "SpeechAudioChunk":
                    data = getattr(event, "data", b"")
                    if not data:
                        continue
                    if ttfb_caller_ms is None:
                        ttfb_caller_ms = (time.monotonic() - t0) * 1000.0
                    pcm_chunks.append(data)
                    chunk_count += 1
                    bytes_total += len(data)
                elif etype == "SpeechStreamCompleted":
                    completed = event
        _log_stream_metrics("stream-cache", voice, text, started, completed,
                            ttfb_caller_ms, chunk_count, bytes_total)
        try:
            final_pcm = b"".join(pcm_chunks)
            if final_pcm:
                tmp = abs_path + ".part"
                _write_wav(tmp, final_pcm, sample_rate)
                os.replace(tmp, abs_path)
        except Exception as e:
            _octomil_log("cache wav err: " + repr(e))

    def _octomil_kickoff_synth(voice, text, abs_path, rel_path, autoplay=True):
        client = _octomil_state.get("client")
        loop = _octomil_state.get("loop")
        if client is None or loop is None:
            return
        with _octomil_pending_lock:
            if abs_path in _octomil_pending:
                return  # already queued
            import asyncio
            if autoplay:
                coro = _octomil_stream_live(client, voice, text, abs_path, rel_path)
            else:
                coro = _octomil_stream_cache(client, voice, text, abs_path)
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            _octomil_pending[abs_path] = fut

        def _on_done(f):
            try:
                f.result()  # raises if stream failed
            except Exception as e:
                _octomil_log("stream bg fail: " + repr(e))
            finally:
                with _octomil_pending_lock:
                    _octomil_pending.pop(abs_path, None)
                    wanted = abs_path in _octomil_play_wanted
                    _octomil_play_wanted.discard(abs_path)
                # The player landed on this line while it was prefetching
                # (autoplay=False), so the coroutine never played it. Now
                # that the WAV exists, play it (a beat late, but audible
                # instead of silent).
                if wanted and os.path.exists(abs_path) and _octomil_state.get("current_path") == abs_path:
                    try:
                        renpy.sound.play(_octomil_audio_data(abs_path), channel=_OCTOMIL_PLAY_CHANNEL)
                        _octomil_log("deferred-play OK voice=%s" % voice)
                    except Exception as e:
                        _octomil_log("deferred-play err: " + repr(e))
        fut.add_done_callback(_on_done)

    # Walk the AST forward from the current node and prefetch the next few
    # Say lines so they're cached before the user advances.
    #
    # Bounded to 2 (was 4, then 1). The engine has a single serialized slot
    # (scheduler max_concurrency=1) and sherpa's Generate() is a blocking
    # C++ call that only yields at sentence boundaries. Lookahead 4 stacked
    # the foreground request behind up to four speculative synths -> the
    # ~50s queued_ms stalls seen in debug.log. Lookahead 2 gives a fast
    # reader a one-extra-line buffer while keeping the worst-case foreground
    # wait bounded (foreground runs at FOREGROUND priority so the scheduler
    # preempts in-flight SPECULATIVE prefetches). Cancel-on-advance + the
    # deferred-play path keep late synths from playing over the wrong line.
    PREFETCH_LOOKAHEAD = 2
    # On cache miss, block this long waiting for synth before giving up and
    # going async. Kokoro on Apple Silicon often finishes a short line in
    # ~200-400ms, so this catches the common case with no perceptible lag.
    SYNC_SYNTH_TIMEOUT = 0.35
    def _octomil_voice_for_tag(tag):
        return _octomil_voice_for_key(tag)

    def _octomil_prefetch_upcoming():
        try:
            ctx = renpy.game.context()
            current_name = ctx.current
        except Exception as e:
            _octomil_log("prefetch ctx err: " + repr(e))
            return
        if not current_name:
            _octomil_log("prefetch skip: ctx.current is empty")
            return
        try:
            node = renpy.game.script.lookup(current_name)
        except Exception as e:
            _octomil_log("prefetch lookup err: " + repr(e))
            return
        found = 0
        steps = 0
        seen_types = []
        while node is not None and found < PREFETCH_LOOKAHEAD and steps < 80:
            steps += 1
            try:
                node = getattr(node, "next", None)
            except Exception as e:
                _octomil_log("prefetch next err: " + repr(e))
                return
            if node is None:
                _octomil_log("prefetch end: walked %d nodes, types=%s, found=%d" % (
                    steps, seen_types[:8], found))
                return
            t = type(node).__name__
            seen_types.append(t)
            # "Say" — plain dialogue.
            # "TranslateSay" — dialogue with a translation id attached
            #   (Ren'Py emits these for any line under a `translate` block;
            #   Eternum has localization so every dialogue is TranslateSay).
            if t not in ("Say", "TranslateSay"):
                continue
            tag = getattr(node, "who", None)
            raw = getattr(node, "what", None)
            if not raw:
                continue
            try:
                substituted = renpy.substitute(raw)
            except Exception:
                substituted = raw
            cleaned = _octomil_clean(substituted)
            if not cleaned:
                continue
            voice = _octomil_voice_for_tag(tag if isinstance(tag, str) else None)
            abs_path, rel_path = _octomil_paths(voice, cleaned)
            if os.path.exists(abs_path):
                _octomil_log("prefetch hit#%d already cached: %r" % (found+1, cleaned[:40]))
            else:
                _octomil_log("prefetch hit#%d kickoff: tag=%r voice=%s text=%r" % (
                    found+1, tag, voice, cleaned[:40]))
                _octomil_kickoff_synth(voice, cleaned, abs_path, rel_path, autoplay=False)
            found += 1
        if found == 0:
            _octomil_log("prefetch found 0 say nodes after %d steps; types=%s" % (
                steps, seen_types[:10]))

    # We use Ren'Py's built-in "sound" channel instead of registering a
    # custom one. The "sound" mixer is always unmuted in shipped games (it
    # plays SFX) and the channel itself is initialized by Ren'Py before
    # init python runs, so there's no risk of a registration race.
    _OCTOMIL_PLAY_CHANNEL = "sound"

    # Strip Ren'Py text tags and stage-direction asterisks before synthesis.
    # Kokoro treats "*laughs*" / "*stands up*" as literal words, not acting
    # controls, so omit them instead of making characters narrate actions.
    # Examples:
    #   "{i}*turning around*{/i} Oh hi."  -> "Oh hi."
    #   "W-W-What a surprise!"             -> "What a surprise!"
    #   "I t-thought you were asleep!"     -> "I thought you were asleep!"
    #   "Hmmmmmm..."                       -> "Hmm..."
    #   "{w=0.5}{nw}"                      -> ""
    #   "He said{p} \"hi\""                 -> "He said. \"hi\""
    _RPY_PAUSE_RE     = re.compile(r"\{p(?:=[^}]*)?\}")       # {p}, {p=1.0}
    _RPY_TAG_RE       = re.compile(r"\{[^}]*\}")              # {i}, {/i}, {w=0.5}, {color=#fff}, {nw}
    _STAGE_RE         = re.compile(r"\*([^*]+)\*")            # *action* -> removed
    _STUTTER_RE       = re.compile(r"\b((?:[A-Za-z]\s*[-–—]\s*)+)([A-Za-z][A-Za-z']*)")
    _VOCALIZATION_RE  = re.compile(r"\b(?:h+m+|u+m+|a+h+|o+h+|e+h+)\b", re.IGNORECASE)
    _MULTISPACE_RE    = re.compile(r"\s+")

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
        s = _MULTISPACE_RE.sub(" ", s).strip()
        return s

    def octomil_tts_say(who, what):
        text = _octomil_clean(what)
        if not text:
            # Narration / no-voice line. Mark "no current voiced line" so an
            # in-flight synth for the previous line suppresses its own
            # playback (current_path guard). No hard channel stop.
            _octomil_state["current_path"] = None
            return
        # Voice id + cache path are pure (hashing only, no engine), so we
        # compute them even before the engine has finished warming up.
        voice = _octomil_voice_for(who)
        abs_path, rel_path = _octomil_paths(voice, text)
        # Cancel-on-advance (soft): record this line as current so any
        # in-flight async synth for an EARLIER line suppresses its own
        # playback (the current_path guard) instead of talking over this
        # one. We do NOT hard-stop the channel — a cache-hit play() already
        # replaces the previous voice, and hard-stopping on every advance
        # was clipping rapid dialogue and could cut the game's own SFX
        # (this is the shared "sound" channel).
        _octomil_state["current_path"] = abs_path
        # Ensure mixer is audible.
        try:
            if renpy.game.preferences.get_volume("sfx") <= 0.01:
                renpy.game.preferences.set_volume("sfx", 1.0)
            renpy.game.preferences.set_mute("sfx", False)
        except Exception:
            pass
        if os.path.exists(abs_path):
            # Cache hit — pure WAV playback, NO engine required. Crucially
            # this runs even while the engine is still warming up (the
            # ~3-22s cold model load), so any line the player has heard
            # before is never silent during cold start. Only brand-new
            # (uncached) lines have to wait for warmup to finish.
            try:
                renpy.sound.play(_octomil_audio_data(abs_path), channel=_OCTOMIL_PLAY_CHANNEL)
                _octomil_log("cache-play OK voice=%s" % voice)
            except Exception as e:
                _octomil_log("cache-play err: " + repr(e))
            _octomil_prefetch_upcoming()  # no-op until the engine is ready
            return
        # Cache miss — synthesis needs the engine. If warmup hasn't finished
        # (state["client"] not set yet), we can't synth this line; it shows
        # without voice. This only bites brand-new lines during cold start.
        if not _octomil_state.get("ready"):
            _octomil_log("warming, can't synth new line yet: " + text[:40])
            return
        with _octomil_pending_lock:
            in_flight = abs_path in _octomil_pending
        if in_flight:
            # A speculative prefetch for this exact line is already running
            # (autoplay=False) — the player just caught up to it. Mark it so
            # the done-callback plays it; don't kick a duplicate synth (it
            # would no-op on the pending guard and the line would stay silent).
            with _octomil_pending_lock:
                _octomil_play_wanted.add(abs_path)
            _octomil_log("await in-flight prefetch -> will play voice=%s" % voice)
        else:
            # Cold miss — synthesize live (plays once assembled).
            _octomil_kickoff_synth(voice, text, abs_path, rel_path, autoplay=True)
        # Prefetch the next line so the following advance is a cache hit.
        # PREFETCH_LOOKAHEAD bounds queue depth; this is also what lets a
        # cold cache warm up at all.
        _octomil_prefetch_upcoming()

    # ---- 5. Hook into Ren'Py's character callback chain ----
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
