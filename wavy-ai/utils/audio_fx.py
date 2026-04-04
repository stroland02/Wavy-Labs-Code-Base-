"""
audio_fx.py — Per-track genre-aware FX chain using pedalboard.

apply_genre_fx(audio_path, genre, role) → processed WAV path
"""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

import config

try:
    from pedalboard import Pedalboard, Gain, Distortion, Chorus, Reverb
    _PEDALBOARD_OK = True
except ImportError:
    _PEDALBOARD_OK = False


# (role, genre) → ordered list of FX names to apply
_FX_CHAINS: dict[tuple[str, str], list[str]] = {
    ("808",    "rage_trap"):        ["hard_clip", "gain_6db"],
    ("808",    "uk_drill"):         ["hard_clip", "gain_3db"],
    ("808",    "trap"):             ["gain_3db"],
    ("pad",    "house"):            ["chorus", "hall_reverb"],
    ("pad",    "future_bass"):      ["chorus", "hall_reverb"],
    ("pad",    "big_room"):         ["chorus", "hall_reverb"],
    ("melody", "neo_soul"):         ["tape_sat"],
    ("lead",   "uk_drill"):         ["dark_reverb", "light_grit"],
    ("lead",   "rage_trap"):        ["light_grit"],
    ("any",    "ambient"):          ["long_hall_reverb"],
    ("any",    "atmospheric"):      ["long_hall_reverb"],
    # NCS / Future Bass chains (v0.9.9)
    ("pad",    "ncs_future_bass"):  ["supersaw_width", "huge_hall", "ott_crush"],
    ("pad",    "melodic_dubstep"):  ["supersaw_width", "huge_hall"],
    ("pad",    "ncs_big_room"):     ["supersaw_width", "huge_hall", "ott_crush"],
    ("lead",   "ncs_future_bass"):  ["ncs_reverb", "ncs_pluck_verb"],
    ("lead",   "melodic_dubstep"):  ["ncs_reverb"],
    ("pluck",  "ncs_future_bass"):  ["ncs_pluck_verb", "ott_crush"],
    ("808",    "ncs_future_bass"):  ["808_sub"],
    ("808",    "melodic_dubstep"):  ["808_sub", "hard_clip"],
    ("chords", "ncs_future_bass"):  ["stab_sat", "supersaw_width", "ncs_reverb"],
    ("chords", "ncs_big_room"):     ["stab_sat", "supersaw_width", "huge_hall"],
}


def apply_genre_fx(audio_path: str, genre: str, role: str = "any") -> str:
    """Apply a genre-specific pedalboard FX chain to an audio file.

    Returns path to processed WAV (same path if pedalboard unavailable or no chain found).
    """
    if not _PEDALBOARD_OK:
        return audio_path

    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    data, sr = sf.read(str(src), always_2d=True)  # shape: (samples, channels)

    chain_key = (role.lower(), genre.lower())
    if chain_key not in _FX_CHAINS:
        chain_key = ("any", genre.lower())
    if chain_key not in _FX_CHAINS:
        return str(src)  # no FX defined for this combo

    board = _build_chain(_FX_CHAINS[chain_key])
    # pedalboard expects (channels, samples) float32
    processed = board(data.T.astype(np.float32), sr)
    processed = processed.T  # back to (samples, channels)

    out_path = config.GENERATION_DIR / f"fx_{uuid.uuid4().hex[:8]}.wav"
    sf.write(str(out_path), processed, sr)
    return str(out_path)


def _build_chain(fx_names: list[str]):
    """Build a Pedalboard from a list of FX name strings."""
    plugins = []
    for name in fx_names:
        if name == "hard_clip":
            plugins.append(Distortion(drive_db=18.0))
        elif name == "gain_6db":
            plugins.append(Gain(gain_db=6.0))
        elif name == "gain_3db":
            plugins.append(Gain(gain_db=3.0))
        elif name == "chorus":
            plugins.append(Chorus(rate_hz=0.5, depth=0.25,
                                  centre_delay_ms=7.0, feedback=0.0, mix=0.5))
        elif name == "hall_reverb":
            plugins.append(Reverb(room_size=0.7, damping=0.5,
                                  wet_level=0.35, dry_level=0.65))
        elif name == "long_hall_reverb":
            plugins.append(Reverb(room_size=0.95, damping=0.3,
                                  wet_level=0.5, dry_level=0.5))
        elif name == "dark_reverb":
            plugins.append(Reverb(room_size=0.5, damping=0.8,
                                  wet_level=0.3, dry_level=0.7))
        elif name == "tape_sat":
            plugins.append(Distortion(drive_db=3.0))
        elif name == "light_grit":
            plugins.append(Distortion(drive_db=8.0))
        # NCS FX (v0.9.9)
        elif name == "ott_crush":
            # OTT approximation: soft saturation + gain compensation
            plugins.append(Distortion(drive_db=4.0))
            plugins.append(Gain(gain_db=-2.0))
        elif name == "supersaw_width":
            # Wide supersaw effect via 3-voice chorus
            plugins.append(Chorus(rate_hz=0.3, depth=0.4,
                                  centre_delay_ms=7.0, feedback=0.0, mix=0.6))
        elif name == "huge_hall":
            # Very large hall reverb for NCS pad/lead wash
            plugins.append(Reverb(room_size=0.95, damping=0.3,
                                  wet_level=0.45, dry_level=0.55))
        elif name == "ncs_reverb":
            # Standard NCS lead reverb
            plugins.append(Reverb(room_size=0.80, damping=0.4,
                                  wet_level=0.38, dry_level=0.62))
        elif name == "808_sub":
            # 808 harmonic richness: mild distortion + slight gain boost
            plugins.append(Distortion(drive_db=5.0))
            plugins.append(Gain(gain_db=2.0))
        elif name == "ncs_pluck_verb":
            # Short, tight reverb for pluck lead
            plugins.append(Reverb(room_size=0.45, damping=0.6,
                                  wet_level=0.25, dry_level=0.75))
        elif name == "stab_sat":
            # Chord stab saturation
            plugins.append(Distortion(drive_db=6.0))
            plugins.append(Gain(gain_db=-1.5))
    return Pedalboard(plugins)


def simulate_sidechain(audio_path: str, bpm: int = 128,
                       depth: float = 0.7, release_ms: float = 200.0) -> str:
    """Apply a beat-synced gain envelope that dips on every kick beat.

    Produces the classic sidechaining pump effect without a real compressor.
    depth=1.0 means silence on the beat; depth=0.0 = no effect.
    Returns path to processed WAV file.
    """
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    data, sr = sf.read(str(src), always_2d=True)  # (samples, channels)
    n_samples = len(data)

    # Beat grid: one kick every beat (quarter note)
    beat_sec    = 60.0 / max(1, bpm)
    release_smp = int(release_ms / 1000.0 * sr)

    envelope = np.ones(n_samples, dtype=np.float32)
    beat_smp  = beat_sec * sr

    # Build envelope: dip at each beat, exponential recovery
    beat_idx = 0
    while True:
        onset = int(round(beat_idx * beat_smp))
        if onset >= n_samples:
            break
        # Instantaneous dip to (1 - depth)
        end = min(onset + release_smp, n_samples)
        ramp_len = end - onset
        if ramp_len > 0:
            gain_floor = 1.0 - depth
            ramp = np.linspace(gain_floor, 1.0, ramp_len, dtype=np.float32)
            envelope[onset:end] = np.minimum(envelope[onset:end], ramp)
        beat_idx += 1

    # Apply envelope (broadcast over channels)
    processed = data * envelope[:, np.newaxis]

    out_path = config.GENERATION_DIR / f"sidechain_{uuid.uuid4().hex[:8]}.wav"
    sf.write(str(out_path), processed.astype(np.float32), sr)
    return str(out_path)
