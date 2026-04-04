"""
test_rpc_handlers.py
====================
Unit tests for every RPC handler in rpc_handlers.py.

All model inference is mocked so no GPU / model files are required.
The ModelRegistry is patched per-test via monkeypatch.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import mido
import numpy as np
import pytest

from models.registry import ModelRegistry
from rpc_handlers import RPC_HANDLERS, _synthesize_midi_numpy


# ── MIDI synthesis helper ─────────────────────────────────────────────────────

def _make_test_midi(path: str, n_notes: int = 4) -> None:
    """Write a minimal valid MIDI file with n_notes to *path*."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    tick = 0
    for i in range(n_notes):
        pitch = 60 + i
        track.append(mido.Message("note_on",  note=pitch, velocity=80, time=tick if i else 0))
        track.append(mido.Message("note_off", note=pitch, velocity=0,  time=240))
        tick = 0
    mid.tracks.append(track)
    mid.save(path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call(method: str, params: dict, registry: ModelRegistry) -> Any:
    """Invoke a named handler and return its result (may raise)."""
    handler = RPC_HANDLERS[method]
    return handler(params, registry)


def _mock_registry(**model_return_values: dict) -> ModelRegistry:
    """
    Build a ModelRegistry whose .get(name) returns a MagicMock configured
    so that calling any method on it returns the corresponding dict.

    Example:
        registry = _mock_registry(
            demucs={"stems": {"vocals": "/tmp/vocals.wav"}}
        )
    """
    registry = MagicMock(spec=ModelRegistry)
    _cache: dict = {}

    def _get_side_effect(name: str) -> MagicMock:
        if name not in _cache:
            mock_model = MagicMock()
            return_val = model_return_values.get(name, {})
            # Every method on the mock returns return_val
            mock_model.generate.return_value = return_val
            mock_model.split.return_value   = return_val
            mock_model.analyze.return_value = return_val
            mock_model.master.return_value  = return_val
            mock_model.parse_command.return_value = return_val
            mock_model.convert.return_value = return_val
            _cache[name] = mock_model
        return _cache[name]

    registry.get.side_effect = _get_side_effect
    registry.loaded_model_names.return_value = []
    registry.model_status.return_value = []
    return registry


# ── health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self):
        registry = _mock_registry()
        registry.loaded_model_names.return_value = ["demucs"]
        result = _call("health", {}, registry)
        assert result["status"] == "ok"
        assert result["version"] == "1.0.0"
        assert "demucs" in result["loaded_models"]

    def test_empty_loaded_models(self):
        registry = _mock_registry()
        result = _call("health", {}, registry)
        assert result["loaded_models"] == []


# ── generate_music ────────────────────────────────────────────────────────────

class TestGenerateMusic:
    _good_result = {
        "audio_path": "/tmp/wavy_out_001.wav",
        "duration": 15.0,
        "sample_rate": 44100,
    }

    def _make_mock_provider(self):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = self._good_result
        return mock_provider

    def test_calls_cloud_provider_by_default(self):
        registry = _mock_registry()
        mock_provider = self._make_mock_provider()
        with patch("cloud.router.get_music_provider", return_value=mock_provider):
            params = {"prompt": "chill lo-fi beat", "duration": 15}
            result = _call("generate_music", params, registry)
        assert result["audio_path"].endswith(".wav")
        mock_provider.generate.assert_called_once()

    def test_passes_prompt_and_params_to_provider(self):
        registry = _mock_registry()
        mock_provider = self._make_mock_provider()
        with patch("cloud.router.get_music_provider", return_value=mock_provider):
            params = {
                "prompt": "jazz piano",
                "genre": "jazz",
                "tempo": 90,
                "key": "F major",
                "duration": 15,
                "seed": 42,
                "tier": "free",
            }
            _call("generate_music", params, registry)
        call_kwargs = mock_provider.generate.call_args[1]
        assert call_kwargs["prompt"] == "jazz piano"
        assert call_kwargs["genre"] == "jazz"
        assert call_kwargs["tempo"] == 90
        assert call_kwargs["key"] == "F major"

    def test_free_tier_caps_duration(self):
        import config
        registry = _mock_registry()
        mock_provider = self._make_mock_provider()
        with patch("cloud.router.get_music_provider", return_value=mock_provider):
            params = {"prompt": "beat", "duration": 999, "tier": "free"}
            _call("generate_music", params, registry)
        call_kwargs = mock_provider.generate.call_args[1]
        assert call_kwargs["duration"] <= config.MAX_DURATION_FREE


# ── split_stems ───────────────────────────────────────────────────────────────

class TestSplitStems:
    _good_result = {
        "stems": {
            "vocals": "/tmp/vocals.wav",
            "drums":  "/tmp/drums.wav",
        }
    }

    def test_delegates_to_demucs(self, tmp_path):
        audio = tmp_path / "in.wav"
        audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        registry = _mock_registry(demucs=self._good_result)
        result = _call("split_stems", {"audio_path": str(audio), "stems": 2}, registry)
        registry.get.assert_called_with("demucs")
        assert "stems" in result

    def test_passes_stems_count(self, tmp_path):
        audio = tmp_path / "in.wav"
        audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        registry = _mock_registry(demucs=self._good_result)
        params = {"audio_path": str(audio), "stems": 4}
        _call("split_stems", params, registry)
        mock_model = registry.get("demucs")
        mock_model.split.assert_called_once_with(**params)


# ── mix_analyze ───────────────────────────────────────────────────────────────

class TestMixAnalyze:
    _good_result = {
        "suggestions": [
            {"track": "vocals", "gain_db": 2.5},
            {"track": "drums",  "gain_db": -1.0},
        ]
    }

    def test_delegates_to_mixer(self):
        registry = _mock_registry(mixer=self._good_result)
        params = {"track_paths": ["/a.wav", "/b.wav"], "reference_path": None}
        result = _call("mix_analyze", params, registry)
        registry.get.assert_called_with("mixer")
        assert "suggestions" in result

    def test_no_reference_path(self):
        registry = _mock_registry(mixer=self._good_result)
        params = {"track_paths": ["/a.wav"]}
        result = _call("mix_analyze", params, registry)
        assert isinstance(result["suggestions"], list)


# ── master_audio ──────────────────────────────────────────────────────────────

class TestMasterAudio:
    _good_result = {
        "output_path": "/tmp/mastered.wav",
        "applied_settings": {"target_lufs": -14.0, "compressor_ratio": 4.0},
    }

    def test_delegates_to_mixer(self, tmp_path):
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"")
        registry = _mock_registry(mixer=self._good_result)
        result = _call("master_audio", {"audio_path": str(wav), "target_lufs": -14.0}, registry)
        registry.get.assert_called_with("mixer")
        assert result["output_path"].endswith(".wav")

    def test_applied_settings_present(self, tmp_path):
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"")
        registry = _mock_registry(mixer=self._good_result)
        result = _call("master_audio", {"audio_path": str(wav)}, registry)
        assert "applied_settings" in result

    def test_missing_audio_path_returns_error(self):
        registry = _mock_registry(mixer={})
        result = _call("master_audio", {}, registry)
        assert "error" in result

    def test_nonexistent_file_returns_error(self):
        registry = _mock_registry(mixer={})
        result = _call("master_audio", {"audio_path": "/no/such/file.wav"}, registry)
        assert "error" in result


# ── prompt_command ────────────────────────────────────────────────────────────

class TestPromptCommand:
    _good_result = {
        "actions": [{"type": "set_tempo", "bpm": 90}],
        "explanation": "Reduced tempo to 90 BPM for a relaxed feel.",
    }

    def test_delegates_to_prompt_cmd(self):
        """When no cloud keys are set, falls back to registry local model."""
        registry = _mock_registry(prompt_cmd=self._good_result)
        params = {
            "prompt": "slow it down a bit",
            "daw_context": {"tempo": 120, "tracks": []},
        }
        import unittest.mock as _mock
        # Clear all cloud API keys so the local registry fallback is used
        with _mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "GROQ_API_KEY": ""}):
            import config
            config.ANTHROPIC_API_KEY = ""
            config.GROQ_API_KEY = ""
            result = _call("prompt_command", params, registry)
            config.ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
            config.GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
        registry.get.assert_called_with("prompt_cmd")
        assert isinstance(result["actions"], list)
        assert result["explanation"]

    def test_empty_actions_list(self):
        registry = _mock_registry(prompt_cmd={"actions": [], "explanation": "Nothing to do."})
        result = _call("prompt_command", {"prompt": "do nothing"}, registry)
        assert result["actions"] == []


# ── _synthesize_midi_numpy ────────────────────────────────────────────────────

class TestSynthesizeMidiNumpy:
    def test_produces_wav_file(self, tmp_path):
        mid_path = str(tmp_path / "test.mid")
        _make_test_midi(mid_path, n_notes=4)
        wav = _synthesize_midi_numpy(mid_path)
        assert wav is not None
        assert wav.endswith(".wav")
        assert Path(wav).exists()
        assert Path(wav).stat().st_size > 1000  # non-trivial audio

    def test_audio_is_float32_normalized(self, tmp_path):
        import soundfile as sf
        mid_path = str(tmp_path / "norm.mid")
        _make_test_midi(mid_path, n_notes=8)
        wav = _synthesize_midi_numpy(mid_path)
        data, sr = sf.read(wav, dtype="float32")
        assert sr == 44100
        assert np.max(np.abs(data)) <= 1.0
        assert np.max(np.abs(data)) > 0.1  # has actual signal

    def test_empty_midi_returns_none(self, tmp_path):
        mid_path = str(tmp_path / "empty.mid")
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        mid.tracks.append(mido.MidiTrack())
        mid.save(mid_path)
        result = _synthesize_midi_numpy(mid_path)
        assert result is None

    def test_output_path_is_midi_with_wav_extension(self, tmp_path):
        mid_path = str(tmp_path / "song.mid")
        _make_test_midi(mid_path)
        wav = _synthesize_midi_numpy(mid_path)
        assert wav == str(tmp_path / "song.wav")


# ── code_to_music ─────────────────────────────────────────────────────────────

class TestCodeToMusic:
    _good_result_no_audio = {
        "midi_path": "",   # filled in per-test with real tmp path
        "audio_paths": [],
        "track_defs": [{"track": "piano", "type": "melody"}],
        "generate_requests": [],
    }

    def _result_with_midi(self, tmp_path: Path) -> dict:
        mid_path = str(tmp_path / "song.mid")
        _make_test_midi(mid_path)
        return {**self._good_result_no_audio, "midi_path": mid_path}

    def test_delegates_to_code_to_music(self, tmp_path):
        result = self._result_with_midi(tmp_path)
        registry = _mock_registry(code_to_music=result)
        params = {"code": "track('piano').melody(['C4'], duration='quarter')", "mode": "dsl"}
        out = _call("code_to_music", params, registry)
        registry.get.assert_called_with("code_to_music")
        assert out["midi_path"].endswith(".mid")

    def test_all_modes_accepted(self, tmp_path):
        for mode in ("dsl", "python", "csv", "json_data"):
            result = self._result_with_midi(tmp_path)
            registry = _mock_registry(code_to_music=result)
            _call("code_to_music", {"code": "x", "mode": mode}, registry)
            registry.get.assert_called_with("code_to_music")

    def test_synthesizes_midi_to_wav_when_no_audio_paths(self, tmp_path):
        """MIDI tracks without generate() calls should produce a synthesized WAV."""
        result = self._result_with_midi(tmp_path)
        registry = _mock_registry(code_to_music=result)
        with patch("cloud.router.get_music_provider", return_value=None):
            out = _call("code_to_music", {"code": "x", "mode": "dsl"}, registry)
        # Synthesis should have filled in audio_paths
        assert len(out["audio_paths"]) == 1
        assert out["audio_paths"][0].endswith(".wav")
        assert Path(out["audio_paths"][0]).exists()

    def test_does_not_re_synthesize_when_audio_already_present(self, tmp_path):
        """If generate_requests already produced audio_paths, skip numpy synthesis."""
        mid_path = str(tmp_path / "song.mid")
        _make_test_midi(mid_path)
        existing_wav = str(tmp_path / "cloud.wav")
        Path(existing_wav).write_bytes(b"RIFF" + b"\x00" * 40)  # dummy WAV
        result = {
            "midi_path": mid_path,
            "audio_paths": [existing_wav],
            "track_defs": [{"track": "synth", "type": "generate"}],
            "generate_requests": [],
        }
        registry = _mock_registry(code_to_music=result)
        with patch("cloud.router.get_music_provider", return_value=None):
            out = _call("code_to_music", {"code": "x", "mode": "dsl"}, registry)
        # Should keep the existing path, not add a second one
        assert out["audio_paths"] == [existing_wav]


# ── list_models ───────────────────────────────────────────────────────────────

class TestListModels:
    def test_returns_models_key(self):
        registry = _mock_registry()
        registry.model_status.return_value = [
            {"name": "demucs", "loaded": False, "vram_gb": 4},
        ]
        with patch("model_check.get_model_disk_size", return_value=0.0):
            result = _call("list_models", {}, registry)
        assert "models" in result
        assert result["models"][0]["name"] == "demucs"

    def test_empty_registry(self):
        registry = _mock_registry()
        registry.model_status.return_value = []
        with patch("model_check.get_model_disk_size", return_value=0.0):
            result = _call("list_models", {}, registry)
        assert result["models"] == []

    def test_disk_size_included(self):
        registry = _mock_registry()
        registry.model_status.return_value = [
            {"name": "demucs", "loaded": True},
        ]
        with patch("model_check.get_model_disk_size", return_value=0.42):
            result = _call("list_models", {}, registry)
        assert result["models"][0]["disk_size_gb"] == pytest.approx(0.42)


# ── delete_model ──────────────────────────────────────────────────────────────

class TestDeleteModel:
    def test_deletes_installed_model(self):
        registry = _mock_registry()
        with patch("model_check.uninstall_model", return_value=True) as mock_uninstall:
            result = _call("delete_model", {"name": "demucs"}, registry)
        mock_uninstall.assert_called_once_with("demucs")
        registry.unload.assert_called_once_with("demucs")
        assert result["deleted"] == "demucs"
        assert result["success"] is True

    def test_returns_false_when_not_found(self):
        registry = _mock_registry()
        with patch("model_check.uninstall_model", return_value=False):
            result = _call("delete_model", {"name": "nonexistent"}, registry)
        assert result["success"] is False

    def test_missing_name_raises(self):
        registry = _mock_registry()
        with pytest.raises(ValueError, match="'name' param required"):
            _call("delete_model", {}, registry)

    def test_unloads_before_delete(self):
        """Registry.unload must be called before disk deletion."""
        call_order = []
        registry = _mock_registry()
        registry.unload.side_effect = lambda n: call_order.append("unload")

        def fake_uninstall(name):
            call_order.append("delete")
            return True

        with patch("model_check.uninstall_model", side_effect=fake_uninstall):
            _call("delete_model", {"name": "demucs"}, registry)
        assert call_order == ["unload", "delete"]


# ── load_model ────────────────────────────────────────────────────────────────

class TestLoadModel:
    def test_calls_registry_load(self):
        registry = _mock_registry()
        result = _call("load_model", {"name": "demucs"}, registry)
        registry.load.assert_called_once_with("demucs")
        assert result["loaded"] == "demucs"

    def test_missing_name_raises(self):
        registry = _mock_registry()
        with pytest.raises(KeyError):
            _call("load_model", {}, registry)


# ── unload_model ──────────────────────────────────────────────────────────────

class TestUnloadModel:
    def test_calls_registry_unload(self):
        registry = _mock_registry()
        result = _call("unload_model", {"name": "demucs"}, registry)
        registry.unload.assert_called_once_with("demucs")
        assert result["unloaded"] == "demucs"

    def test_missing_name_raises(self):
        registry = _mock_registry()
        with pytest.raises(KeyError):
            _call("unload_model", {}, registry)


# ── registry completeness ─────────────────────────────────────────────────────

class TestRegistryCompleteness:
    EXPECTED_METHODS = {
        "health",
        "generate_music",
        "split_stems",
        "mix_analyze",
        "master_audio",
        "prompt_command",
        "code_to_music",
        "list_models",
        "load_model",
        "unload_model",
        "delete_model",
        "elevenlabs_tts",
        "elevenlabs_voice_clone",
        "elevenlabs_speech_to_speech",
        "elevenlabs_sfx",
        "elevenlabs_voice_isolate",
        "elevenlabs_transcribe",
        "elevenlabs_forced_align",
        "elevenlabs_dub",
        "elevenlabs_music_stems",
        "elevenlabs_list_voices",
        # New handlers (v0.4.x)
        "generate_stem",
        "replace_section",
        "audio_to_midi",
        "extend_music",
        "prompt_to_midi",
        "save_persona",
        "load_personas",
    }

    def test_all_expected_methods_registered(self):
        assert self.EXPECTED_METHODS == set(RPC_HANDLERS.keys())

    def test_all_handlers_callable(self):
        for name, fn in RPC_HANDLERS.items():
            assert callable(fn), f"Handler '{name}' is not callable"
