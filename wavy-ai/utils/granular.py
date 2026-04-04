"""
granular.py — Granular audio synthesis/chopper using numpy + soundfile.

granular_chop(audio_path, grain_ms, pitch_spread, density) → WAV path
"""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

import config


def granular_chop(audio_path: str, grain_ms: float = 80.0,
                  pitch_spread: float = 0.3, density: float = 0.5) -> str:
    """Apply granular synthesis to an audio file.

    Chops audio into short grains, applies random pitch scatter (via linear
    resampling), and reassembles using overlap-add with a Hann window.

    grain_ms:     grain size in milliseconds (20–500)
    pitch_spread: max pitch scatter in semitones (0.0–4.0)
    density:      overlap density 0.0=sparse 1.0=fully overlapping

    Returns: absolute path to processed WAV file.
    """
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    y, sr = sf.read(str(src), always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)  # mix to mono
    y = y.astype(np.float32)

    grain_samples = max(64, int(sr * grain_ms / 1000.0))
    hop = max(1, int(grain_samples * max(0.01, 1.0 - density)))
    n_grains = max(1, (len(y) - grain_samples) // hop)

    out_len = len(y) + grain_samples * 2
    output = np.zeros(out_len, dtype=np.float32)
    window = np.hanning(grain_samples).astype(np.float32)

    rng = np.random.default_rng(42)

    for i in range(n_grains):
        # Slightly randomize grain source position (±10% of grain size)
        scatter = rng.integers(-grain_samples // 10, grain_samples // 10 + 1)
        src_pos = max(0, min(len(y) - grain_samples, i * hop + scatter))
        grain = y[src_pos:src_pos + grain_samples].copy()
        if len(grain) < grain_samples:
            grain = np.pad(grain, (0, grain_samples - len(grain)))

        # Random pitch shift via linear resampling (lightweight, no librosa needed)
        if pitch_spread > 0.0:
            semitones = float(rng.uniform(-pitch_spread, pitch_spread))
            ratio = 2.0 ** (semitones / 12.0)
            new_len = max(1, int(grain_samples / ratio))
            # Resample grain to new_len then stretch/compress back to grain_samples
            indices_1 = np.linspace(0, len(grain) - 1, new_len)
            grain_resampled = np.interp(indices_1, np.arange(len(grain)), grain)
            indices_2 = np.linspace(0, len(grain_resampled) - 1, grain_samples)
            grain = np.interp(indices_2,
                              np.arange(len(grain_resampled)),
                              grain_resampled).astype(np.float32)

        grain = grain * window

        dst = i * hop
        output[dst:dst + grain_samples] += grain

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 1e-6:
        output = output / peak * 0.85

    # Trim to slightly longer than source
    output = output[:len(y) + grain_samples]

    out_path = config.GENERATION_DIR / f"granular_{uuid.uuid4().hex[:8]}.wav"
    sf.write(str(out_path), output, sr)
    return str(out_path)
