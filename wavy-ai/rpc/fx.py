"""FX, NCS, SoundFont, and analysis RPC handlers."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger
from models.registry import ModelRegistry
import config

# ── Genre FX / Pitch / Arp / Granular handlers (v0.9.5) ──────────────────────

def _apply_track_fx(params: dict, registry: ModelRegistry) -> dict:
    """Apply genre-aware pedalboard FX chain to an audio file.
    params: {audio_path, genre, role}
    returns: {audio_path}
    """
    from utils.audio_fx import apply_genre_fx
    audio_path = str(params.get("audio_path", ""))
    genre      = str(params.get("genre", "default"))
    role       = str(params.get("role", "any"))
    if not audio_path:
        return {"error": "audio_path required"}
    try:
        out_path = apply_genre_fx(audio_path, genre, role)
        return {"audio_path": out_path}
    except Exception as exc:
        logger.error(f"[apply_track_fx] {exc}")
        return {"error": _clean_str(exc)}


def _pitch_correct_audio(params: dict, registry: ModelRegistry) -> dict:
    """Apply Auto-Tune pitch correction to a vocal or instrument audio file.
    params: {audio_path, key, scale, strength}
    returns: {audio_path, track_name}
    """
    from utils.pitch_utils import pitch_correct
    audio_path = str(params.get("audio_path", ""))
    key        = str(params.get("key", "C"))
    scale      = str(params.get("scale", "minor"))
    strength   = float(params.get("strength", 0.8))
    if not audio_path:
        return {"error": "audio_path required"}
    try:
        out_path = pitch_correct(audio_path, key, scale, strength)
        return {"audio_path": out_path, "track_name": Path(out_path).stem}
    except Exception as exc:
        logger.error(f"[pitch_correct_audio] {exc}")
        return {"error": _clean_str(exc)}


def _generate_arpeggio(params: dict, registry: ModelRegistry) -> dict:
    """Generate an arpeggiated MIDI pattern from chord notes.
    params: {chord_notes:[int], bpm, style, bars}
    returns: {parts:[{name, midi_path, instrument, color, note_count}]}
    """
    from utils.arp_generator import generate_arp
    chord_notes = [int(n) for n in params.get("chord_notes", [60, 64, 67])]
    bpm         = int(params.get("bpm", 120))
    style       = str(params.get("style", "16th"))
    bars        = int(params.get("bars", 2))
    try:
        midi_path = generate_arp(chord_notes, bpm, style, bars)
        note_count = bars * max(1, round(4.0 / {"8th": 0.5, "16th": 0.25,
                                                 "triplet_16th": 1/3}.get(style, 0.25)))
        return {
            "parts": [{
                "name":       "Arpeggio",
                "midi_path":  midi_path,
                "instrument": "tripleoscillator",
                "color":      "#9b59b6",
                "note_count": note_count,
            }]
        }
    except Exception as exc:
        logger.error(f"[generate_arpeggio] {exc}")
        return {"error": _clean_str(exc)}


def _granular_chop_audio(params: dict, registry: ModelRegistry) -> dict:
    """Apply granular synthesis to an audio file.
    params: {audio_path, grain_ms, pitch_spread, density}
    returns: {audio_path, track_name}
    """
    from utils.granular import granular_chop
    audio_path   = str(params.get("audio_path", ""))
    grain_ms     = float(params.get("grain_ms", 80.0))
    pitch_spread = float(params.get("pitch_spread", 0.3))
    density      = float(params.get("density", 0.5))
    if not audio_path:
        return {"error": "audio_path required"}
    try:
        out_path = granular_chop(audio_path, grain_ms, pitch_spread, density)
        return {"audio_path": out_path, "track_name": "Granular Pad"}
    except Exception as exc:
        logger.error(f"[granular_chop_audio] {exc}")
        return {"error": _clean_str(exc)}


# ── NCS Toolkit ───────────────────────────────────────────────────────────────

def _ncs_song_structure(params: dict, registry: ModelRegistry) -> dict:
    """Return a full NCS-style 72-bar song structure breakdown.

    params:
        genre : str  — "ncs_future_bass" | "melodic_dubstep" | "ncs_big_room" (default: ncs_future_bass)
        key   : str  — root note, e.g. "A" (default: "A")
        scale : str  — "major" | "minor" (default: "minor")
        bpm   : int  — BPM (default: 128)
    returns:
        {"sections": [...], "key": str, "scale": str, "bpm": int, "genre": str}
    """
    genre = params.get("genre", "ncs_future_bass")
    key   = params.get("key",   "A")
    scale = params.get("scale", "minor")
    bpm   = int(params.get("bpm", 128))

    # Standard NCS 72-bar arrangement
    _SECTIONS = [
        {"name": "Intro",    "bars": 8,  "description": "Atmospheric intro, synth pads, no drums"},
        {"name": "Build 1",  "bars": 8,  "description": "Rising energy, full drum build, white noise riser"},
        {"name": "Drop 1",   "bars": 16, "description": "Main drop — supersaw chords, 808 bass, full energy"},
        {"name": "Break",    "bars": 8,  "description": "Breakdown — stripped back, emotional chord progression"},
        {"name": "Build 2",  "bars": 8,  "description": "Second build — more intense, vocal chops"},
        {"name": "Drop 2",   "bars": 16, "description": "Second drop — often with added elements or variation"},
        {"name": "Outro",    "bars": 8,  "description": "Wind-down, pad wash, fade or sudden cut"},
    ]

    # Assign start bars
    sections = []
    start = 0
    for s in _SECTIONS:
        sections.append({
            "name":        s["name"],
            "start_bar":   start,
            "bars":        s["bars"],
            "description": s["description"],
        })
        start += s["bars"]

    return {
        "sections": sections,
        "key":      key,
        "scale":    scale,
        "bpm":      bpm,
        "genre":    genre,
        "total_bars": start,
    }


def _generate_riser(params: dict, registry: ModelRegistry) -> dict:
    """Generate a transition sound (riser, impact, crash, etc.).

    params:
        riser_type : str   — "white_noise_riser" | "reverse_crash" | "downlifter"
                             | "impact_hit" | "cymbal_crash"
        bpm        : float — track BPM (default 128)
        bars       : float — length in bars (default 2)
    returns:
        {"audio_path": str, "riser_type": str, "duration": float}
    """
    from utils.riser_generator import generate_riser
    riser_type = params.get("riser_type", "white_noise_riser")
    bpm        = float(params.get("bpm",  128))
    bars       = float(params.get("bars", 2))
    try:
        audio_path = generate_riser(riser_type, bpm=bpm, bars=bars)
        # Compute actual duration
        beat_sec = 60.0 / max(1.0, bpm)
        duration = beat_sec * 4.0 * bars
        if riser_type == "impact_hit":
            duration = min(duration, beat_sec)
        return {"audio_path": audio_path, "riser_type": riser_type, "duration": duration}
    except Exception as exc:
        logger.error(f"[generate_riser] {exc}")
        return {"error": _clean_str(exc)}


def _apply_sidechain_pump(params: dict, registry: ModelRegistry) -> dict:
    """Apply sidechain pump effect to an audio file.

    params:
        audio_path  : str   — input WAV file
        bpm         : int   — track BPM (default 128)
        depth       : float — pump depth 0.0–1.0 (default 0.7)
        release_ms  : float — release time in ms (default 200)
    returns:
        {"audio_path": str}
    """
    from utils.audio_fx import simulate_sidechain
    audio_path = params.get("audio_path", "")
    if not audio_path or not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    bpm        = int(params.get("bpm", 128))
    depth      = float(params.get("depth", 0.7))
    release_ms = float(params.get("release_ms", 200.0))
    try:
        out_path = simulate_sidechain(audio_path, bpm=bpm,
                                     depth=depth, release_ms=release_ms)
        return {"audio_path": out_path}
    except Exception as exc:
        logger.error(f"[apply_sidechain_pump] {exc}")
        return {"error": _clean_str(exc)}


# ── SoundFont Manager ──────────────────────────────────────────────────────

def _list_soundfonts(params: dict, registry: ModelRegistry) -> dict:
    """Return available SF2 packs with install status.

    returns: {soundfonts: [{name, size_mb, installed, path, ...}], sf_dir: str}
    """
    from utils.soundfont_manager import list_installed, _sf2_dir
    sf_dir = str(_sf2_dir())
    return {"soundfonts": list_installed(), "sf_dir": sf_dir}


def _download_soundfont_rpc(params: dict, registry: ModelRegistry) -> dict:
    """Download a soundfont pack by name.

    params: {name: str}
    returns: {path: str, name: str}
    """
    from utils.soundfont_manager import download_soundfont
    name = params.get("name", "")
    if not name:
        return {"error": "'name' param required"}
    try:
        path = download_soundfont(name)
        return {"path": path, "name": name}
    except Exception as exc:
        logger.error(f"[download_soundfont] {name}: {exc}")
        return {"error": _clean_str(exc)}


# ── AI FX Chain from Text (v0.12.0) ──────────────────────────────────────────

def _text_to_fx_chain(params: dict, registry: ModelRegistry) -> dict:
    """Convert a text description to an FX chain and optionally apply to audio.

    params:
        prompt     : str — description (e.g. "warm lo-fi radio")
        audio_path : str — optional audio file to process
    returns:
        {fx_chain: [{name, params}], audio_path?}
    """
    prompt = params.get("prompt", "").strip()
    audio_path = params.get("audio_path", "")
    if not prompt:
        return {"error": "prompt is required"}

    # Use LLM to interpret prompt into FX chain
    from cloud.router import get_command_provider
    import json as _json
    import re as _re

    FX_SYSTEM = (
        "You are an audio FX engineer. Convert this description into a pedalboard FX chain.\n"
        "Available effects: reverb, delay, chorus, compressor, gain, limiter, "
        "distortion, phaser, pitch_shift, highpass, lowpass, ladderfilter\n"
        "Return ONLY valid JSON:\n"
        '{"fx_chain": [{"name": "reverb", "params": {"room_size": 0.7, "wet_level": 0.3}}, ...]}\n'
        "Parameter ranges:\n"
        "- reverb: room_size(0-1), damping(0-1), wet_level(0-1), dry_level(0-1), width(0-1)\n"
        "- delay: delay_seconds(0-2), feedback(0-0.9), mix(0-1)\n"
        "- chorus: rate_hz(0.1-5), depth(0-1), mix(0-1), centre_delay_ms(5-15)\n"
        "- compressor: threshold_db(-50-0), ratio(1-20), attack_ms(0.1-100), release_ms(10-1000)\n"
        "- gain: gain_db(-20-20)\n"
        "- limiter: threshold_db(-20-0), release_ms(10-500)\n"
        "- distortion: drive_db(0-40)\n"
        "- phaser: rate_hz(0.1-10), depth(0-1), mix(0-1)\n"
        "- pitch_shift: semitones(-12-12)\n"
        "- highpass: cutoff_hz(20-5000)\n"
        "- lowpass: cutoff_hz(200-20000)\n"
        "- ladderfilter: cutoff_hz(20-20000), resonance(0-1), drive(1-5)\n"
        "No extra text. Only JSON."
    )

    fx_chain = []
    provider = get_command_provider()
    if provider:
        try:
            raw = provider.parse_command(f"{FX_SYSTEM}\n\nUser: {prompt}", {})
            explanation = raw.get("explanation", "")
            m = _re.search(r'\{[\s\S]*?"fx_chain"\s*:\s*\[[\s\S]*?\]\s*\}', explanation)
            if m:
                fx_chain = _json.loads(m.group()).get("fx_chain", [])
        except Exception as exc:
            logger.warning(f"[text_to_fx_chain] LLM failed: {exc}")

    # Fallback preset chains
    if not fx_chain:
        prompt_lower = prompt.lower()
        if "lo-fi" in prompt_lower or "lofi" in prompt_lower:
            fx_chain = [
                {"name": "lowpass", "params": {"cutoff_hz": 4000}},
                {"name": "distortion", "params": {"drive_db": 8}},
                {"name": "reverb", "params": {"room_size": 0.4, "wet_level": 0.25}},
                {"name": "compressor", "params": {"threshold_db": -15, "ratio": 4}},
            ]
        elif "radio" in prompt_lower or "vintage" in prompt_lower:
            fx_chain = [
                {"name": "highpass", "params": {"cutoff_hz": 300}},
                {"name": "lowpass", "params": {"cutoff_hz": 3500}},
                {"name": "distortion", "params": {"drive_db": 12}},
                {"name": "compressor", "params": {"threshold_db": -10, "ratio": 6}},
            ]
        elif "spacey" in prompt_lower or "ambient" in prompt_lower or "ethereal" in prompt_lower:
            fx_chain = [
                {"name": "reverb", "params": {"room_size": 0.9, "wet_level": 0.5, "damping": 0.3}},
                {"name": "delay", "params": {"delay_seconds": 0.4, "feedback": 0.5, "mix": 0.3}},
                {"name": "chorus", "params": {"rate_hz": 0.5, "depth": 0.6, "mix": 0.3}},
            ]
        else:
            fx_chain = [
                {"name": "compressor", "params": {"threshold_db": -18, "ratio": 3}},
                {"name": "reverb", "params": {"room_size": 0.5, "wet_level": 0.2}},
            ]

    result: dict = {"fx_chain": fx_chain}

    # Apply FX to audio if path provided
    if audio_path and Path(audio_path).is_file():
        try:
            from pedalboard import (Pedalboard, Reverb, Delay, Chorus, Compressor,
                                    Gain, Limiter, Distortion, Phaser, PitchShift,
                                    HighpassFilter, LowpassFilter, LadderFilter)
            from pedalboard.io import AudioFile

            fx_map = {
                "reverb": Reverb, "delay": Delay, "chorus": Chorus,
                "compressor": Compressor, "gain": Gain, "limiter": Limiter,
                "distortion": Distortion, "phaser": Phaser, "pitch_shift": PitchShift,
                "highpass": HighpassFilter, "lowpass": LowpassFilter,
                "ladderfilter": LadderFilter,
            }

            effects = []
            for fx in fx_chain:
                fx_cls = fx_map.get(fx["name"])
                if fx_cls:
                    p = fx.get("params", {})
                    try:
                        effects.append(fx_cls(**p))
                    except Exception as e:
                        logger.warning(f"[text_to_fx_chain] skipping {fx['name']}: {e}")

            if effects:
                board = Pedalboard(effects)
                with AudioFile(audio_path) as f:
                    audio = f.read(f.frames)
                    sr = f.samplerate
                processed = board(audio, sr)
                out_path = str(Path(audio_path).parent / f"fx_{uuid.uuid4().hex[:8]}.wav")
                with AudioFile(out_path, "w", sr, processed.shape[0]) as f:
                    f.write(processed)
                result["audio_path"] = out_path
                result["duration"] = processed.shape[1] / sr
        except Exception as exc:
            logger.error(f"[text_to_fx_chain] FX application failed: {exc}")
            result["error"] = f"FX applied but audio processing failed: {_clean_str(exc)}"

    return result


# ── Analyze Reference Track (v0.12.0) ─────────────────────────────────────────

def _analyze_reference(params: dict, registry: ModelRegistry) -> dict:
    """Analyze an audio file to extract style descriptors for reference-based generation.

    params:
        audio_path : str — path to reference audio file
    returns:
        {bpm, key, scale, loudness_lufs, spectral_description, style_prompt}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path or not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}

    result: dict = {}

    # Ensure WAV for analysis
    wav_path = _ensure_wav(audio_path)

    try:
        audio_data, sr = sf.read(str(wav_path), always_2d=True)
        mono = audio_data.mean(axis=1).astype(np.float32)
    except Exception as exc:
        return {"error": f"Could not read audio: {_clean_str(exc)}"}

    # BPM detection via onset correlation
    try:
        # Simple BPM estimation via autocorrelation of energy envelope
        hop = 512
        frame_len = 2048
        energy = np.array([
            np.sum(mono[i:i+frame_len]**2)
            for i in range(0, len(mono) - frame_len, hop)
        ])
        if len(energy) > 100:
            # Onset detection via diff
            onset = np.maximum(0, np.diff(energy))
            # Autocorrelation
            corr = np.correlate(onset, onset, mode='full')
            corr = corr[len(corr)//2:]
            # Search for peak in 60-200 BPM range
            min_lag = int(60 * sr / hop / 200)  # 200 BPM
            max_lag = int(60 * sr / hop / 60)   # 60 BPM
            if max_lag < len(corr):
                search = corr[min_lag:max_lag]
                if len(search) > 0:
                    best_lag = min_lag + np.argmax(search)
                    estimated_bpm = round(60 * sr / hop / best_lag)
                    result["bpm"] = int(estimated_bpm)
    except Exception as exc:
        logger.warning(f"[analyze_reference] BPM detection failed: {exc}")

    # Loudness measurement
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(audio_data)
        result["loudness_lufs"] = round(loudness, 1)
    except Exception:
        pass

    # Spectral analysis for brightness descriptor
    try:
        # Compute spectral centroid
        n_fft = 4096
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        # Take a few frames from the middle
        mid = len(mono) // 2
        frames = []
        for offset in range(-3, 4):
            start = mid + offset * n_fft
            if 0 <= start <= len(mono) - n_fft:
                spectrum = np.abs(np.fft.rfft(mono[start:start + n_fft]))
                centroid = np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-10)
                frames.append(centroid)
        if frames:
            avg_centroid = np.mean(frames)
            if avg_centroid < 1500:
                brightness = "dark, warm"
            elif avg_centroid < 3000:
                brightness = "balanced, neutral"
            elif avg_centroid < 5000:
                brightness = "bright"
            else:
                brightness = "very bright, airy"
            result["spectral_description"] = brightness
    except Exception:
        pass

    # Key detection via chroma analysis
    try:
        chroma_counts = np.zeros(12)
        n_fft = 4096
        for start in range(0, min(len(mono), sr * 30) - n_fft, n_fft // 2):
            spectrum = np.abs(np.fft.rfft(mono[start:start + n_fft]))
            freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
            for i, magnitude in enumerate(spectrum):
                if freqs[i] > 50 and freqs[i] < 5000 and magnitude > 0.01:
                    note = int(round(12 * np.log2(freqs[i] / 440 + 1e-10))) % 12
                    chroma_counts[note] += magnitude

        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        dominant_note = note_names[np.argmax(chroma_counts)]

        # Simple major/minor detection via thirds
        root_idx = np.argmax(chroma_counts)
        major_third = chroma_counts[(root_idx + 4) % 12]
        minor_third = chroma_counts[(root_idx + 3) % 12]
        detected_scale = "major" if major_third > minor_third else "minor"

        result["key"] = dominant_note
        result["scale"] = detected_scale
    except Exception:
        pass

    # Build a style prompt from analysis
    parts = []
    if "bpm" in result:
        parts.append(f"{result['bpm']} BPM")
    if "key" in result:
        parts.append(f"{result['key']} {result.get('scale', 'minor')}")
    if "spectral_description" in result:
        parts.append(result["spectral_description"])
    if "loudness_lufs" in result:
        if result["loudness_lufs"] > -10:
            parts.append("loud, compressed")
        elif result["loudness_lufs"] < -20:
            parts.append("soft, dynamic")

    result["style_prompt"] = "In the style of: " + ", ".join(parts) if parts else ""

    return result


# ── Analyze Song Material (v0.12.0) ──────────────────────────────────────────

def _analyze_song_material(params: dict, registry: ModelRegistry) -> dict:
    """Analyze multiple audio tracks from the Song Editor to build a combined
    style reference for new generations.

    params:
        audio_paths : list[str] — paths to Song Editor audio tracks
    returns:
        {bpm, key, scale, style_prompt, track_count}
    """
    audio_paths = params.get("audio_paths", [])
    if not audio_paths:
        return {"error": "audio_paths list is required"}

    # Analyze each track and aggregate
    all_bpms = []
    all_keys = []
    all_spectral = []
    all_loudness = []

    for path in audio_paths:
        if not Path(path).is_file():
            continue
        analysis = _analyze_reference({"audio_path": path}, registry)
        if "bpm" in analysis:
            all_bpms.append(analysis["bpm"])
        if "key" in analysis:
            all_keys.append(f"{analysis['key']} {analysis.get('scale', 'minor')}")
        if "spectral_description" in analysis:
            all_spectral.append(analysis["spectral_description"])
        if "loudness_lufs" in analysis:
            all_loudness.append(analysis["loudness_lufs"])

    result: dict = {"track_count": len(audio_paths)}

    if all_bpms:
        # Use median BPM
        result["bpm"] = int(np.median(all_bpms))
    if all_keys:
        # Use most common key
        from collections import Counter
        result["key_info"] = Counter(all_keys).most_common(1)[0][0]
        parts = result["key_info"].split()
        result["key"] = parts[0]
        result["scale"] = parts[1] if len(parts) > 1 else "minor"
    if all_loudness:
        result["loudness_lufs"] = round(float(np.mean(all_loudness)), 1)

    # Build aggregate style prompt
    style_parts = []
    if "bpm" in result:
        style_parts.append(f"{result['bpm']} BPM")
    if "key" in result:
        style_parts.append(f"{result['key']} {result.get('scale', 'minor')}")
    if all_spectral:
        # Most common spectral descriptor
        from collections import Counter
        common_spectral = Counter(all_spectral).most_common(1)[0][0]
        style_parts.append(common_spectral)

    result["style_prompt"] = (
        f"Build on existing song material ({len(audio_paths)} tracks): "
        + ", ".join(style_parts)
    ) if style_parts else ""

    return result

