"""Audio RPC handlers."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger
from models.registry import ModelRegistry
import config
from rpc.helpers import _ensure_wav, _synthesize_midi_numpy

# ── Music Generation ─────────────────────────────────────────────────────────

def _generate_music(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        prompt   : str   — text description
        genre    : str   — optional
        tempo    : int   — BPM (default 120)
        key      : str   — e.g. "C minor"
        duration : float — seconds (default 15 free / 60 pro)
        seed     : int   — optional, -1 = random
        tier     : str   — "free" | "pro" | "studio"
    returns:
        {"audio_path": str, "duration": float, "sample_rate": int}
    """
    from cloud.router import get_music_provider
    import config

    tier = params.get("tier", "free")
    if tier == "studio":
        max_dur = config.MAX_DURATION_STUDIO
    elif tier == "pro":
        max_dur = config.MAX_DURATION_PRO
    else:
        max_dur = config.MAX_DURATION_FREE
    duration = min(float(params.get("duration", max_dur)), max_dur)

    # lyrics mode → force_instrumental flag + optional custom lyrics
    lyrics_mode = params.get("lyrics", "auto")  # "auto" | "instrumental" | "custom"
    force_instrumental = (lyrics_mode == "instrumental")
    lyrics_text = params.get("lyrics_text", "") if lyrics_mode == "custom" else ""

    # ── Custom lyrics: warn if prompt doesn't mention a singer (Opus check) ──
    if lyrics_mode == "custom" and not params.get("singer_confirmed"):
        prompt_text = params.get("prompt", "").strip()
        logger.info(f"[singer_check] lyrics=custom confirmed={params.get('singer_confirmed')} prompt={prompt_text!r}")
        if prompt_text:
            try:
                import anthropic as _anthropic
                _client = _anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                _resp = _client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=10,
                    system="Reply only YES or NO.",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Does this music prompt explicitly mention a singer, "
                            f"vocalist, voice, or rapper?\nPrompt: \"{prompt_text}\"\n"
                            f"Answer YES or NO only."
                        )
                    }]
                )
                answer = _resp.content[0].text.strip().upper()
                if answer.startswith("NO"):
                    return {
                        "singer_warning": True,
                        "error": (
                            "Your prompt doesn't mention a singer. "
                            "Custom lyrics need a vocalist — add something like "
                            "\"female singer\", \"male vocalist\", or \"rapper\" to your prompt."
                        )
                    }
            except Exception as _e:
                logger.warning(f"[singer_check] Opus check failed: {_e}")

    # Inspo: reference style note — filter to existing files; prepend to prompt
    inspo_paths = [p for p in params.get("inspo_paths", []) if p and Path(p).is_file()]
    if inspo_paths:
        params = {**params, "prompt": f"[reference style provided] {params.get('prompt', '')}"}

    # influence param forwarded as-is; providers ignore unknown kwargs gracefully

    model_name = params.get("model", "elevenlabs_music")

    # Explicit model routing — ElevenLabs music gen
    if model_name == "elevenlabs_music":
        from cloud.elevenlabs_provider import ElevenLabsMusicProvider
        provider = ElevenLabsMusicProvider()
    else:
        provider = get_music_provider(tier)

    if provider is None:
        return {"error": "Music generation requires ElevenLabs (ELEVENLABS_API_KEY). Set CLOUD_PROVIDER=elevenlabs in config.py."}

    try:
        return provider.generate(
            prompt=params.get("prompt", ""),
            duration=duration,
            tempo=int(params.get("tempo", 120)),
            key=params.get("key", ""),
            genre=params.get("genre", ""),
            seed=int(params.get("seed", -1)),
            force_instrumental=force_instrumental,
            lyrics_text=lyrics_text,
            tier=tier,
        )
    except Exception as exc:
        exc_str = str(exc)
        # quota_exceeded — surface a clean actionable message
        if "quota_exceeded" in exc_str or "quota" in exc_str.lower():
            import re as _re
            credits_match = _re.search(
                r"You have (\d+) credits remaining.*?(\d+) credits are required", exc_str
            )
            if credits_match:
                have, need = credits_match.group(1), credits_match.group(2)
                return {"error": (
                    f"ElevenLabs quota exceeded: {have} credits remaining, "
                    f"{need} required. Top up at elevenlabs.io/subscription"
                )}
            return {"error": "ElevenLabs quota exceeded. Top up at elevenlabs.io/subscription"}
        raise


# ── Stem Splitting ────────────────────────────────────────────────────────────

def _split_stems(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        audio_path : str  — input audio file
        stems      : int  — 2 | 4 | 6  (also accepts num_stems)
    returns:
        {"stems": [{"name": str, "path": str}, ...]}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path:
        return {"error": "'audio_path' is required"}
    if not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    # Support both "stems" and "num_stems" param names
    merged = dict(params)
    if "num_stems" in merged and "stems" not in merged:
        merged["stems"] = merged.pop("num_stems")
    model = registry.get("demucs")
    result = model.split(**merged)
    # Normalise to list-of-dicts format for UI consumption
    stems_raw = result.get("stems", {})
    if isinstance(stems_raw, dict):
        stems_list = [{"name": k, "path": v} for k, v in stems_raw.items()]
        result["stems"] = stems_list
    return result


# ── Mixing / Mastering ────────────────────────────────────────────────────────

def _mix_analyze(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        track_paths   : list[str]  — paths to all track stems
        reference_path: str | None — optional reference track
    returns:
        {"suggestions": [...AutomationPattern dicts...]}
    """
    # C++ client sends "audio_paths"; MixerModel.analyze() expects "track_paths"
    track_paths = params.get("track_paths") or params.get("audio_paths", [])
    reference_path = params.get("reference_path")
    missing = [p for p in track_paths if p and not Path(p).exists()]
    if missing:
        logger.warning(f"_mix_analyze: missing files: {missing}")
    try:
        model = registry.get("mixer")
        return model.analyze(track_paths=track_paths, reference_path=reference_path)
    except Exception as exc:
        logger.error(f"_mix_analyze error: {exc}")
        return {"error": str(exc), "suggestions": []}


def _master_audio(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        audio_path     : str
        target_lufs    : float — default -14.0
        reference_path : str | None
    returns:
        {"output_path": str, "applied_settings": dict}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path:
        return {"error": "'audio_path' is required"}
    if not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    try:
        model = registry.get("mixer")
        return model.master(**params)
    except Exception as exc:
        logger.error(f"_master_audio error: {exc}")
        return {"error": str(exc)}


# ── Prompt Commands ───────────────────────────────────────────────────────────

def _prompt_command(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        prompt       : str  — natural language command
        daw_context  : dict — current song state (tracks, tempo, key, etc.)
    returns:
        {"actions": [...JSON action objects...], "explanation": str}
    """
    from cloud.router import get_command_provider

    prompt  = params.get("prompt", "")
    context = params.get("daw_context")
    history = params.get("history") or []

    provider = get_command_provider()
    if provider is None:
        # No Anthropic API key — try local Mistral/Llama as fallback
        try:
            model = registry.get("prompt_cmd")
            return model.parse_command(prompt, context, history=history)
        except Exception as exc:
            logger.warning(f"Local prompt model unavailable: {exc}")
            return {
                "error": (
                    "Prompt commands require an Anthropic API key (ANTHROPIC_API_KEY) "
                    "or a local Mistral GGUF model. "
                    "Set ANTHROPIC_API_KEY in your environment to enable Claude."
                ),
                "actions": [],
                "explanation": "",
            }
    return provider.parse_command(prompt, context, history=history)


# ── Code to Music ─────────────────────────────────────────────────────────────

def _code_to_music(params: dict, registry: ModelRegistry) -> dict:
    """
    params:
        code        : str  — Python/JS snippet or Wavy DSL
        mode        : str  — "dsl" | "python" | "csv" | "json_data"
        csv_data    : str  — (optional) raw CSV content
        json_data   : str  — (optional) raw JSON content
    returns:
        {"midi_path": str, "audio_paths": list[str], "track_defs": list[dict],
         "generate_requests": list[dict]}

    Tracks that use generate("prompt") in the DSL/Python API are forwarded to
    the music generation model so the caller receives real audio paths.
    """
    model = registry.get("code_to_music")
    result = model.convert(**params)

    generate_requests = result.get("generate_requests", [])
    if generate_requests:
        from cloud.router import get_music_provider
        tier = params.get("tier", "free")
        provider = get_music_provider(tier)
        audio_paths: list = list(result.get("audio_paths", []))
        for req in generate_requests:
            try:
                if provider is None:
                    logger.warning("code_to_music: no music provider, skipping generate() call")
                    continue
                gen_result = provider.generate(
                        prompt=req.get("prompt", ""),
                        duration=float(req.get("duration", 15)),
                        tempo=int(req.get("tempo", 120)),
                        tier=tier,
                    )
                audio_paths.append(gen_result["audio_path"])
            except Exception as exc:
                logger.warning(f"code_to_music: generate failed for {req!r}: {exc}")
        result["audio_paths"] = audio_paths

    # Synthesize MIDI → WAV for pattern/melody tracks that didn't go through
    # the generate() path (e.g. pure DSL patterns, data sonification).
    if not result.get("audio_paths") and result.get("track_defs") and result.get("midi_path"):
        try:
            wav = _synthesize_midi_numpy(result["midi_path"])
            if wav:
                result["audio_paths"] = [wav]
        except Exception as exc:
            logger.warning(f"code_to_music: MIDI synthesis failed: {exc}")

    return result


# ── Stem Generation ───────────────────────────────────────────────────────────

def _generate_stem(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, reference_path, stem_type, duration, influence, tier
    returns: {"audio_path": str, "duration": float}
    """
    from cloud.router import get_music_provider
    reference_path = params.get("reference_path", "")
    if reference_path and not Path(reference_path).is_file():
        return {"error": f"reference_path not found: {reference_path!r}"}
    stem_type = params.get("stem_type", "")
    full_prompt = f"{stem_type} stem: {params.get('prompt', '')}".strip(": ")
    provider = get_music_provider(params.get("tier", "free"))
    if provider:
        return provider.generate(
            prompt=full_prompt,
            duration=float(params.get("duration", 15)),
            tempo=int(params.get("tempo", 120)),
            tier=params.get("tier", "free"),
        )
    return {"error": "Music generation requires ElevenLabs (ELEVENLABS_API_KEY not set or CLOUD_PROVIDER=local)"}


# ── Replace Section (in-painting) ─────────────────────────────────────────────

def _replace_section(params: dict, registry: ModelRegistry) -> dict:
    """
    params: audio_path, start_sec, end_sec, prompt, tempo, tier
    returns: {"audio_path": str}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path or not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    start_sec = float(params.get("start_sec", 0))
    end_sec   = float(params.get("end_sec", 0))
    duration  = max(0.5, end_sec - start_sec)
    from cloud.router import get_music_provider
    provider = get_music_provider(params.get("tier", "free"))
    try:
        if provider:
            gen_result = provider.generate(
                prompt=params.get("prompt", ""),
                duration=duration,
                tempo=int(params.get("tempo", 120)),
                tier=params.get("tier", "free"),
            )
        else:
            return {"error": "replace_section requires ElevenLabs (ELEVENLABS_API_KEY not set)"}
    except Exception as exc:
        return {"error": f"Segment generation failed: {exc}"}
    orig, sr = sf.read(audio_path, always_2d=True)
    repl, sr2 = sf.read(gen_result["audio_path"], always_2d=True)
    if sr2 != sr:
        try:
            from scipy.signal import resample_poly
            from fractions import Fraction
            f = Fraction(sr / sr2).limit_denominator(100)
            repl = resample_poly(repl, f.numerator, f.denominator, axis=0)
        except ImportError:
            logger.warning("scipy not installed — skipping resample in replace_section")
    start_samp = int(start_sec * sr)
    end_samp   = int(end_sec * sr)
    needed = end_samp - start_samp
    repl_fit = repl[:needed, :orig.shape[1]]
    if len(repl_fit) < needed:
        repl_fit = np.vstack([repl_fit, np.zeros((needed - len(repl_fit), orig.shape[1]))])
    orig[start_samp:end_samp] = repl_fit
    out_path = str(Path(audio_path).parent / f"replaced_{uuid.uuid4().hex[:8]}.wav")
    sf.write(out_path, orig, sr)
    return {"audio_path": out_path}


# ── Extend Music (out-painting) ───────────────────────────────────────────────

def _extend_music(params: dict, registry: ModelRegistry) -> dict:
    """
    params: audio_path, extend_seconds (default 15), prompt, tempo, tier
    returns: {"audio_path": str, "duration": float}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path or not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    extend_sec = float(params.get("extend_seconds", 15))
    prompt = params.get("prompt", "continuation, same style")
    from cloud.router import get_music_provider
    provider = get_music_provider(params.get("tier", "free"))
    try:
        if provider:
            gen_result = provider.generate(
                prompt=prompt, duration=extend_sec,
                tempo=int(params.get("tempo", 120)),
                tier=params.get("tier", "free"),
            )
        else:
            return {"error": "extend_music requires ElevenLabs (ELEVENLABS_API_KEY not set)"}
    except Exception as exc:
        return {"error": f"Extension generation failed: {exc}"}
    orig, sr = sf.read(audio_path, always_2d=True)
    ext,  sr2 = sf.read(gen_result["audio_path"], always_2d=True)
    if sr2 != sr:
        try:
            from scipy.signal import resample_poly
            from fractions import Fraction
            f = Fraction(sr / sr2).limit_denominator(100)
            ext = resample_poly(ext, f.numerator, f.denominator, axis=0)
        except ImportError:
            logger.warning("scipy not installed — skipping resample in extend_music")
    ch = orig.shape[1]
    if ext.shape[1] > ch:
        ext = ext[:, :ch]
    elif ext.shape[1] < ch:
        ext = np.hstack([ext] * (ch // ext.shape[1] + 1))[:, :ch]
    combined = np.vstack([orig, ext])
    out_path = str(Path(audio_path).parent / f"extended_{uuid.uuid4().hex[:8]}.wav")
    sf.write(out_path, combined, sr)
    return {"audio_path": out_path, "duration": len(combined) / sr}


# ── Chat Generate ─────────────────────────────────────────────────────────────

def _chat_generate(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, session_id
    returns:
        mode=="audio": {mode, audio_parts:[{path, title}], explanation}
        mode=="midi":  {mode, parts:[{midi_path, role,...}], explanation, key, scale, bpm}
    """
    import traceback
    print(f"[rpc] chat_generate called with params={params}", flush=True)
    try:
        from agents.chat_agent import ChatAgent
        result = ChatAgent().generate(params, registry)
        print(f"[rpc] chat_generate result mode={result.get('mode')!r} error={result.get('error')!r}", flush=True)
        return result
    except Exception as exc:
        print(f"[rpc] chat_generate EXCEPTION: {exc}", flush=True)
        traceback.print_exc()
        raise

