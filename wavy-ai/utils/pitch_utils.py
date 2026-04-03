"""
pitch_utils.py — Pitch correction / Auto-Tune using librosa.

pitch_correct(audio_path, key, scale, strength) → processed WAV path
"""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

import config

_SCALE_SEMITONES: dict[str, list[int]] = {
    "major":       [0, 2, 4, 5, 7, 9, 11],
    "minor":       [0, 2, 3, 5, 7, 8, 10],
    "dorian":      [0, 2, 3, 5, 7, 9, 10],
    "phrygian":    [0, 1, 3, 5, 7, 8, 10],
    "mixolydian":  [0, 2, 4, 5, 7, 9, 10],
    "pentatonic":  [0, 2, 4, 7, 9],
    "minor_pent":  [0, 3, 5, 7, 10],
}

_NOTE_SEMITONES: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def pitch_correct(audio_path: str, key: str = "C", scale: str = "minor",
                  strength: float = 0.8) -> str:
    """Apply pitch correction (Auto-Tune) to an audio file.

    Uses librosa pyin for pitch detection + pitch_shift for correction.
    strength: 0.0 (no correction) → 1.0 (hard snap to scale).

    Returns path to processed WAV. Falls back to original path if librosa
    is not installed.
    """
    try:
        import librosa
    except ImportError:
        return audio_path

    src = Path(audio_path)
    y, sr = librosa.load(str(src), sr=None, mono=True)

    root_pc = _NOTE_SEMITONES.get(key, 0)
    intervals = _SCALE_SEMITONES.get(
        scale.lower().replace(" ", "_").replace("-", "_"),
        _SCALE_SEMITONES["minor"]
    )
    valid_pcs = {(root_pc + iv) % 12 for iv in intervals}

    # Frame parameters (50 ms frames with 12.5 ms hop)
    frame_len = max(512, int(sr * 0.05 / 512) * 512)
    hop_len = frame_len // 4

    # Estimate pitch
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
        frame_length=frame_len,
        hop_length=hop_len,
    )

    y_out = y.copy()

    for i, (freq, voiced) in enumerate(zip(f0, voiced_flag)):
        if not voiced or freq is None or np.isnan(freq):
            continue
        midi_f = librosa.hz_to_midi(float(freq))
        pc = int(round(midi_f)) % 12
        if pc in valid_pcs:
            continue

        # Nearest valid pitch class (wrapping aware)
        nearest_pc = min(valid_pcs, key=lambda v: min(abs(pc - v), 12 - abs(pc - v)))
        diff = nearest_pc - pc
        if diff > 6:
            diff -= 12
        elif diff < -6:
            diff += 12

        start = i * hop_len
        end = min(start + frame_len * 2, len(y))
        chunk = y[start:end]
        if len(chunk) < 512:
            continue

        shifted = librosa.effects.pitch_shift(chunk, sr=sr, n_steps=float(diff))
        shifted = shifted[:len(chunk)]
        y_out[start:start + len(shifted)] = (
            shifted * strength + y[start:start + len(shifted)] * (1.0 - strength)
        )

    out_path = config.GENERATION_DIR / f"pitched_{uuid.uuid4().hex[:8]}.wav"
    sf.write(str(out_path), y_out.astype(np.float32), sr)
    return str(out_path)
