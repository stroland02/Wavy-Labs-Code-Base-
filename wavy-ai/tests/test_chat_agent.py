"""
Tests for ChatAgent.
Audio-path tests mock MusicGen so no GPU needed.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Make wavy-ai root importable ──────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Minimal stubs so config / loguru don't fail in CI ─────────────────────────

_TMP = Path(__file__).parent / "tmp_chat"
_TMP.mkdir(exist_ok=True)

config_stub = types.ModuleType("config")
config_stub.GENERATION_DIR = _TMP
config_stub.GROQ_API_KEY = ""
config_stub.ANTHROPIC_API_KEY = ""
sys.modules.setdefault("config", config_stub)

loguru_stub = types.ModuleType("loguru")
loguru_stub.logger = MagicMock()
sys.modules.setdefault("loguru", loguru_stub)

# ── Import under test ──────────────────────────────────────────────────────────

from agents.chat_agent import ChatAgent


# ── TestDetectGenre ────────────────────────────────────────────────────────────

class TestDetectGenre:
    def setup_method(self):
        self.agent = ChatAgent()

    def test_lofi_detected(self):
        assert self.agent._detect_genre("lofi piano melody") == "lofi"

    def test_trap_detected(self):
        assert self.agent._detect_genre("trap beat with 808") == "trap"

    def test_jazz_detected(self):
        assert self.agent._detect_genre("jazz swing improvisation") == "jazz"

    def test_ambient_detected(self):
        assert self.agent._detect_genre("dark ambient drone") == "ambient"

    def test_default_is_lofi(self):
        assert self.agent._detect_genre("a random music prompt") == "lofi"

    def test_case_insensitive(self):
        assert self.agent._detect_genre("LOFI study music") == "lofi"


# ── TestFallbackIntent ─────────────────────────────────────────────────────────

class TestFallbackIntent:
    def setup_method(self):
        self.agent = ChatAgent()

    def test_required_keys_present(self):
        result = self.agent._fallback_intent("lofi piano chill")
        for key in ("key", "scale", "bpm", "genre", "musicgen_prompt"):
            assert key in result

    def test_genre_from_keywords(self):
        result = self.agent._fallback_intent("trap beat 808")
        assert result["genre"] == "trap"

    def test_bpm_extracted(self):
        result = self.agent._fallback_intent("a 140 bpm track")
        assert result["bpm"] == 140

    def test_bpm_clamped(self):
        result = self.agent._fallback_intent("a 999 bpm hyper")
        assert result["bpm"] <= 200


# ── TestChatAgentAudio ────────────────────────────────────────────────────────

class TestChatAgentAudio:
    """Audio path tests — mock MusicGen so no GPU needed."""

    def setup_method(self):
        self.agent = ChatAgent()

    def _make_registry(self, wav_path: str):
        fake_model = MagicMock()
        fake_model.generate.return_value = wav_path
        registry = MagicMock()
        registry.get.return_value = fake_model
        return registry

    def test_audio_returns_correct_mode(self, tmp_path):
        wav = str(tmp_path / "out.wav")
        Path(wav).write_bytes(b"RIFF")  # fake WAV
        registry = self._make_registry(wav)
        result = self.agent._generate_audio(
            {"musicgen_prompt": "dark ambient", "genre": "ambient"},
            registry,
        )
        assert result["mode"] == "audio"
        assert result["audio_parts"][0]["path"] == wav

    def test_audio_error_propagated(self):
        registry = MagicMock()
        registry.get.side_effect = RuntimeError("model not loaded")
        result = self.agent._generate_audio({"musicgen_prompt": "test"}, registry)
        assert "error" in result

    def test_generate_routes_to_audio_with_registry(self, tmp_path):
        """generate() with any prompt + registry → audio."""
        wav = str(tmp_path / "track.wav")
        Path(wav).write_bytes(b"RIFF")
        registry = self._make_registry(wav)

        result = self.agent.generate(
            {"prompt": "lofi chill piano melody in C minor"},
            registry=registry,
        )
        assert result["mode"] == "audio"
        assert len(result["audio_parts"]) > 0

    def test_generate_without_registry_returns_error(self):
        """generate() without registry → error (no MIDI fallback)."""
        result = self.agent.generate({"prompt": "lofi chill"}, registry=None)
        assert "error" in result

    def test_empty_prompt_returns_error(self):
        result = self.agent.generate({"prompt": ""}, registry=None)
        assert "error" in result
