"""Shared helpers used across RPC handler modules."""

from __future__ import annotations

import uuid
from pathlib import Path

import mido
import numpy as np
import soundfile as sf
from loguru import logger

import config


def _clean_str(exc: Exception) -> str:
    """Short single-line description from any exception."""
    raw = str(exc).split("\n")[0].strip()
    return raw[:120] or type(exc).__name__


# ── Path validation ──────────────────────────────────────────────────────────
_ALLOWED_ROOTS: list[Path] | None = None

def _allowed_roots() -> list[Path]:
    """Lazily build the list of allowed directory roots for file operations."""
    global _ALLOWED_ROOTS
    if _ALLOWED_ROOTS is None:
        import tempfile
        _ALLOWED_ROOTS = [
            config.DATA_DIR.resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]
    return _ALLOWED_ROOTS

def _validate_path(path_str: str, label: str = "path") -> Path:
    """Resolve a file path and ensure it falls within allowed directories.
    Raises ValueError if the path escapes the sandbox."""
    p = Path(path_str).resolve()
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise ValueError(f"{label} outside allowed directories: {path_str}")


def _ensure_wav(path: str | Path) -> Path:
    """Return path as WAV, converting MP3/FLAC if needed.

    LMMS uses libsndfile for audio decoding which does not support MP3.
    Converting at import time ensures waveforms display correctly and the
    file path is stored in SampleClip so stem-splitting can find the track.
    Converted WAV is cached next to the source file (same dir, .wav suffix).
    """
    p = Path(path)
    if p.suffix.lower() == ".wav":
        return p
    wav_path = p.with_suffix(".wav")
    if wav_path.exists() and wav_path.stat().st_size > 1_000:
        return wav_path
    try:
        from pedalboard.io import AudioFile
        with AudioFile(str(p)) as f:
            audio = f.read(f.frames)
            sr = f.samplerate
        with AudioFile(str(wav_path), "w", sr, audio.shape[0]) as f:
            f.write(audio)
        logger.info(f"[ensure_wav] converted {p.name} → {wav_path.name}")
        return wav_path
    except Exception as exc:
        logger.warning(f"[ensure_wav] conversion failed for {p.name}: {exc}; using original")
        return p


# ── MIDI → WAV synthesis ──────────────────────────────────────────────────────

def _synthesize_midi_numpy(midi_path: str, sr: int = 44100) -> str | None:
    """Render a MIDI file to a WAV using simple numpy additive synthesis.

    Uses a two-harmonic sine model with a short ADSR envelope per note.
    Quality is modest (organ-like) but requires only mido / numpy / soundfile,
    all of which are already installed.  Returns the WAV path, or None if the
    MIDI contains no audible notes.
    """
    mid = mido.MidiFile(midi_path)
    tpb = mid.ticks_per_beat or 480

    # Collect (start_sec, end_sec, pitch, velocity) for every note-on/off pair
    note_events: list[tuple[float, float, int, int]] = []
    for track in mid.tracks:
        abs_tick = 0
        cur_tempo = 500_000  # 120 BPM default
        active: dict[int, tuple[int, int]] = {}  # pitch → (abs_tick, velocity)
        for msg in track:
            abs_tick += msg.time
            if msg.type == "set_tempo":
                cur_tempo = msg.tempo
            elif msg.type == "note_on" and msg.velocity > 0:
                active[msg.note] = (abs_tick, msg.velocity)
            elif msg.type in ("note_off",) or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                if msg.note in active:
                    on_tick, vel = active.pop(msg.note)
                    # Convert ticks → seconds using a fixed tempo for simplicity
                    tps = tpb / (cur_tempo / 1_000_000)  # ticks per second
                    note_events.append((
                        on_tick / tps,
                        abs_tick / tps,
                        msg.note,
                        vel,
                    ))

    if not note_events:
        return None

    total_sec = max(end for _, end, _, _ in note_events) + 0.5
    audio = np.zeros(int(total_sec * sr), dtype=np.float32)

    for start_s, end_s, pitch, vel in note_events:
        freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
        n = int((end_s - start_s) * sr)
        if n <= 0:
            continue
        t = np.linspace(0, end_s - start_s, n, endpoint=False)
        # Two harmonics — sounds like a soft organ
        wave = (0.65 * np.sin(2 * np.pi * freq * t)
                + 0.25 * np.sin(4 * np.pi * freq * t)
                + 0.10 * np.sin(6 * np.pi * freq * t))
        # Simple ADSR-lite envelope
        atk = min(int(0.01 * sr), n)
        rel = min(int(0.08 * sr), n)
        env = np.ones(n, dtype=np.float32)
        env[:atk] = np.linspace(0.0, 1.0, atk)
        env[max(0, n - rel):] = np.linspace(1.0, 0.0, min(rel, n))
        wave = wave * env * (vel / 127.0) * 0.12

        i0 = int(start_s * sr)
        i1 = i0 + n
        if i1 > len(audio):
            audio = np.pad(audio, (0, i1 - len(audio)))
        audio[i0:i1] += wave

    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = (audio / peak * 0.85).astype(np.float32)

    out_path = str(Path(midi_path).with_suffix(".wav"))
    sf.write(out_path, audio, sr)
    logger.info(f"MIDI synthesized → {out_path} ({len(note_events)} notes)")
    return out_path
