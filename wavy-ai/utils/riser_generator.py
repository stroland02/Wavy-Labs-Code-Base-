"""
riser_generator.py — Pure numpy/scipy riser/transition sound generation.

Generates NCS-style transition sounds: white noise risers, reverse crashes,
downlifters, impact hits, and cymbal crashes.

Usage:
    from utils.riser_generator import generate_riser
    path = generate_riser("white_noise_riser", bpm=128, bars=4)
"""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

import config

_SR = 44100  # sample rate for all generated audio


def _riser_duration(bpm: float, bars: float) -> float:
    """Convert bars at the given BPM to seconds."""
    beat_sec = 60.0 / max(1.0, bpm)
    return beat_sec * 4.0 * bars  # 4 beats per bar


def _white_noise_riser(duration: float, sr: int = _SR) -> np.ndarray:
    """8-stage bandpass sweep with exponential volume ramp."""
    n = int(duration * sr)
    noise = np.random.randn(n).astype(np.float32)

    # Exponential volume envelope (quiet → loud)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    env = np.power(t, 2.5)

    # Bandpass sweep: low cutoff sweeps from 200 Hz → 8 kHz
    # Approximate with a time-varying FIR (8 frequency stages)
    stages = 8
    out = np.zeros(n, dtype=np.float32)
    stage_len = n // stages

    for i in range(stages):
        start = i * stage_len
        end   = min(start + stage_len, n)
        seg   = noise[start:end].copy()

        progress = i / max(1, stages - 1)
        # Frequency sweep: 200 Hz → 8 kHz (exponential)
        lo_hz = 200.0 * (40.0 ** progress)   # 200 → 8000
        hi_hz = min(lo_hz * 2.0, sr / 2.0 - 1)

        # Simple bandpass via FFT
        seg_fft = np.fft.rfft(seg, n=len(seg))
        freqs   = np.fft.rfftfreq(len(seg), d=1.0 / sr)
        mask    = (freqs >= lo_hz) & (freqs <= hi_hz)
        seg_fft *= mask
        seg_bp  = np.fft.irfft(seg_fft, n=len(seg)).astype(np.float32)
        out[start:end] = seg_bp

    return out * env


def _reverse_crash(duration: float, sr: int = _SR) -> np.ndarray:
    """Generated crash symbol flipped in time (reversed crash / uplifter)."""
    n = int(duration * sr)
    noise = np.random.randn(n).astype(np.float32)

    # Crash envelope: fast attack, exponential decay
    env = np.exp(-np.linspace(0.0, 6.0, n, dtype=np.float32))
    env[:int(0.002 * sr)] = np.linspace(0.0, 1.0, int(0.002 * sr))

    # Bandpass around cymbal frequencies (5–16 kHz)
    seg_fft = np.fft.rfft(noise)
    freqs   = np.fft.rfftfreq(n, d=1.0 / sr)
    mask    = (freqs >= 5000.0) & (freqs <= 16000.0)
    seg_fft *= mask
    crash   = np.fft.irfft(seg_fft, n=n).astype(np.float32)
    crash  *= env

    # Flip for "reverse crash" uplifter effect
    return crash[::-1].copy()


def _downlifter(duration: float, sr: int = _SR) -> np.ndarray:
    """Downward pitch sweep using a decreasing-frequency sine + noise."""
    n = int(duration * sr)
    t = np.linspace(0.0, duration, n, dtype=np.float32)

    # Frequency sweep from 800 Hz → 40 Hz (exponential downward)
    freq_start, freq_end = 800.0, 40.0
    freq_t = freq_start * ((freq_end / freq_start) ** (t / duration))
    phase  = 2.0 * np.pi * np.cumsum(freq_t) / sr
    tone   = np.sin(phase).astype(np.float32)

    # Volume envelope: loud → silence
    env = np.linspace(1.0, 0.0, n, dtype=np.float32) ** 1.5
    # Add a bit of noise for texture
    noise_layer = np.random.randn(n).astype(np.float32) * 0.15

    return (tone + noise_layer) * env


def _impact_hit(duration: float, sr: int = _SR) -> np.ndarray:
    """60 Hz sine burst (BOOM) + highpass noise burst (SMACK)."""
    n   = int(duration * sr)
    out = np.zeros(n, dtype=np.float32)

    # Sub boom: 60 Hz sine with fast decay
    boom_len = min(int(0.4 * sr), n)
    t_boom   = np.linspace(0.0, boom_len / sr, boom_len, dtype=np.float32)
    boom_env = np.exp(-t_boom * 8.0)
    boom     = np.sin(2.0 * np.pi * 60.0 * t_boom) * boom_env * 0.85
    out[:boom_len] += boom

    # Transient smack: highpass noise burst (very short)
    smack_len = min(int(0.06 * sr), n)
    smack_noise = np.random.randn(smack_len).astype(np.float32)
    # Highpass via FFT
    s_fft  = np.fft.rfft(smack_noise)
    f_s    = np.fft.rfftfreq(smack_len, d=1.0 / sr)
    s_fft *= (f_s > 3000.0)
    smack  = np.fft.irfft(s_fft, n=smack_len).astype(np.float32)
    smack_env = np.exp(-np.linspace(0.0, 10.0, smack_len, dtype=np.float32))
    out[:smack_len] += smack * smack_env * 0.6

    return out


def _cymbal_crash(duration: float, sr: int = _SR) -> np.ndarray:
    """Bandpass noise with exponential decay + fast transient."""
    n     = int(duration * sr)
    noise = np.random.randn(n).astype(np.float32)

    # Bandpass 5–14 kHz
    n_fft  = np.fft.rfft(noise)
    freqs  = np.fft.rfftfreq(n, d=1.0 / sr)
    mask   = (freqs >= 5000.0) & (freqs <= 14000.0)
    n_fft *= mask
    crash  = np.fft.irfft(n_fft, n=n).astype(np.float32)

    # Envelope: very fast attack (2 ms), exponential decay
    atk    = max(1, int(0.002 * sr))
    env    = np.exp(-np.linspace(0.0, 5.0 * (1.0 / max(0.5, duration)), n,
                                 dtype=np.float32))
    env[:atk] = np.linspace(0.0, 1.0, atk)

    return crash * env


def _normalize(audio: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """Normalize audio to target peak (absolute value)."""
    max_val = np.max(np.abs(audio))
    if max_val < 1e-9:
        return audio
    return (audio / max_val * peak).astype(np.float32)


# ── Public API ─────────────────────────────────────────────────────────────────

_GENERATORS = {
    "white_noise_riser": _white_noise_riser,
    "reverse_crash":     _reverse_crash,
    "downlifter":        _downlifter,
    "impact_hit":        _impact_hit,
    "cymbal_crash":      _cymbal_crash,
}


def generate_riser(riser_type: str, bpm: float = 128.0, bars: float = 2.0,
                   sr: int = _SR) -> str:
    """Generate a transition sound and return its WAV file path.

    Args:
        riser_type: One of "white_noise_riser", "reverse_crash", "downlifter",
                    "impact_hit", "cymbal_crash".
        bpm:        Track BPM (determines duration from bars).
        bars:       How many bars long the riser should be (float OK for 0.5-bar hits).
        sr:         Sample rate (default 44100).

    Returns:
        Absolute path to the generated WAV file.

    Raises:
        ValueError: if riser_type is unrecognized.
    """
    riser_type = riser_type.lower().replace(" ", "_").replace("-", "_")
    if riser_type not in _GENERATORS:
        valid = ", ".join(_GENERATORS.keys())
        raise ValueError(f"Unknown riser type {riser_type!r}. Valid: {valid}")

    duration = _riser_duration(bpm, bars)
    # Impact hits are always short (1 beat at most)
    if riser_type == "impact_hit":
        duration = min(duration, 60.0 / max(1.0, bpm))

    audio = _GENERATORS[riser_type](duration, sr)
    audio = _normalize(audio, peak=0.88)

    # Stereo output (duplicate mono to two channels)
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=1)

    out_dir = config.GENERATION_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"riser_{riser_type}_{uuid.uuid4().hex[:8]}.wav"
    sf.write(str(out_path), audio, sr)

    return str(out_path)
