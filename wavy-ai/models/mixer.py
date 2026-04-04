"""
AI Mixing / Mastering pipeline — rule-based spectral analysis + pedalboard mastering.
No external model weights required; fully functional out of the box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from loguru import logger

from .base import BaseModel

TARGET_LUFS_DEFAULT = -14.0
TARGET_TP_DEFAULT   = -1.0   # dBTP


class MixerModel(BaseModel):
    MODEL_ID = "wavy-labs/mixer-builtin"

    def _load(self) -> None:
        # No weights to load — rule-based pipeline is always ready.
        self._loaded = True
        logger.info("Mixer ready (rule-based).")

    # ── Analyze ───────────────────────────────────────────────────────────────

    def analyze(
        self,
        track_paths: List[str],
        reference_path: Optional[str] = None,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        """Analyze stems and return gain/headroom suggestions."""
        suggestions = []
        for path in track_paths:
            audio, sr = sf.read(path, always_2d=True)
            mono = audio.mean(axis=1)
            suggestions.append(self._analyze_track(mono, sr, Path(path).stem))

        if reference_path:
            ref_audio, ref_sr = sf.read(reference_path, always_2d=True)
            suggestions.append(self._analyze_reference(ref_audio.mean(axis=1), ref_sr))

        return {"suggestions": suggestions}

    def _analyze_track(self, mono: np.ndarray, sr: int, name: str) -> dict:
        rms = float(np.sqrt(np.mean(mono ** 2)))
        peak = float(np.max(np.abs(mono)))
        headroom_db = -20 * np.log10(peak + 1e-9)
        gain_db = max(0.0, min(6.0, -20.0 - (20 * np.log10(rms + 1e-9))))
        return {
            "track":       name,
            "type":        "gain",
            "gain_db":     round(gain_db, 1),
            "headroom_db": round(headroom_db, 1),
            "rms_db":      round(20 * np.log10(rms + 1e-9), 1),
        }

    def _analyze_reference(self, ref_mono: np.ndarray, sr: int) -> dict:
        meter = pyln.Meter(sr)
        lufs = meter.integrated_loudness(ref_mono)
        return {"track": "__reference__", "type": "target_lufs", "lufs": round(lufs, 1)}

    # ── Master ────────────────────────────────────────────────────────────────

    def master(
        self,
        audio_path: str,
        target_lufs: float = TARGET_LUFS_DEFAULT,
        reference_path: Optional[str] = None,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        from pedalboard import Pedalboard, Compressor, Limiter as LimiterPlugin  # type: ignore

        logger.info(f"Mastering {audio_path!r} → {target_lufs} LUFS …")

        audio, sr = sf.read(audio_path, always_2d=True)
        audio_f = audio.astype(np.float32)

        meter = pyln.Meter(sr)
        current_lufs = meter.integrated_loudness(audio_f.mean(axis=1).astype(np.float64))
        gain = float(np.clip(target_lufs - current_lufs, -40.0, 40.0))

        board = Pedalboard([
            Compressor(threshold_db=-18.0, ratio=2.0, attack_ms=10, release_ms=200),
            LimiterPlugin(threshold_db=TARGET_TP_DEFAULT),
        ])
        audio_f *= np.power(10.0, gain / 20.0)
        processed = board(audio_f.T, sr).T

        out_path = self._unique_path("mastered", ".wav", subfolder="mastered")
        sf.write(str(out_path), processed, sr)
        logger.info(f"Saved: {out_path}")

        return {
            "output_path": str(out_path),
            "applied_settings": {
                "target_lufs":     target_lufs,
                "gain_applied_db": round(gain, 1),
                "compressor":      {"threshold_db": -18.0, "ratio": 2.0},
                "limiter_db":      TARGET_TP_DEFAULT,
            },
        }
