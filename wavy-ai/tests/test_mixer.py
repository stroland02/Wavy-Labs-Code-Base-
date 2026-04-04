"""
Tests for the MixerModel — analyze and master (CPU only, no ONNX session needed).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile", reason="soundfile not installed")
sf = soundfile

sys.path.insert(0, str(Path(__file__).parent.parent))

# MixerModel imports onnxruntime at import time; skip entire module if unavailable
onnxruntime = pytest.importorskip("onnxruntime", reason="onnxruntime not installed")

from models.mixer import MixerModel  # noqa: E402


@pytest.fixture(scope="module")
def mixer():
    # Patch ONNX session so we don't need a real model file
    with patch("onnxruntime.InferenceSession", side_effect=Exception("no onnx in CI")):
        return MixerModel()


class TestAnalyze:
    def test_analyze_single_track(self, mixer, silence_wav):
        result = mixer.analyze(track_paths=[str(silence_wav)])
        assert "suggestions" in result
        assert len(result["suggestions"]) == 1
        s = result["suggestions"][0]
        assert "gain_db" in s
        assert "rms_db" in s

    def test_analyze_multiple_tracks(self, mixer, silence_wav):
        result = mixer.analyze(track_paths=[str(silence_wav), str(silence_wav)])
        assert len(result["suggestions"]) == 2

    def test_analyze_with_reference(self, mixer, silence_wav):
        result = mixer.analyze(
            track_paths=[str(silence_wav)],
            reference_path=str(silence_wav),
        )
        # One track suggestion + one reference suggestion
        assert len(result["suggestions"]) == 2
        ref = next(s for s in result["suggestions"] if s["track"] == "__reference__")
        assert ref["type"] == "target_lufs"


class TestMaster:
    def test_master_produces_output(self, mixer, silence_wav):
        result = mixer.master(audio_path=str(silence_wav), target_lufs=-14.0)
        assert "output_path" in result
        assert Path(result["output_path"]).exists()
        assert "applied_settings" in result

    def test_master_gain_applied(self, mixer, silence_wav):
        result = mixer.master(audio_path=str(silence_wav), target_lufs=-14.0)
        settings = result["applied_settings"]
        assert "gain_applied_db" in settings
        assert isinstance(settings["gain_applied_db"], float)
