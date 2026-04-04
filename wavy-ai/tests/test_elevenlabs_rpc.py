"""
Tests for ElevenLabs RPC handlers in rpc_handlers.py.
All providers are mocked — no real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_registry():
    """Build a mock ModelRegistry."""
    registry = MagicMock()
    return registry


# ── elevenlabs_tts ───────────────────────────────────────────────────────────

class TestElevenLabsTTSHandler:

    def test_tts_calls_provider(self):
        from rpc_handlers import _elevenlabs_tts
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "audio_path": "/tmp/tts.mp3",
            "duration": 5.0,
            "sample_rate": 44100,
            "voice_id": "abc",
        }

        with patch("rpc_handlers.get_tts_provider", return_value=mock_provider, create=True), \
             patch("cloud.router.get_tts_provider", return_value=mock_provider):
            result = _elevenlabs_tts(
                {"text": "hello", "voice_id": "abc"},
                _mock_registry(),
            )

        assert result["audio_path"] == "/tmp/tts.mp3"

    def test_tts_returns_error_when_no_key(self):
        from rpc_handlers import _elevenlabs_tts

        registry = _mock_registry()

        with patch("cloud.router.get_tts_provider", return_value=None):
            result = _elevenlabs_tts({"text": "hello"}, registry)

        assert "error" in result
        assert "ELEVENLABS_API_KEY" in result["error"]


# ── elevenlabs_voice_clone ───────────────────────────────────────────────────

class TestElevenLabsVoiceCloneHandler:

    def test_clone_calls_provider(self):
        from rpc_handlers import _elevenlabs_voice_clone
        mock_provider = MagicMock()
        mock_provider.clone_instant.return_value = {
            "voice_id": "new_voice",
            "name": "Clone",
        }

        with patch(
            "rpc_handlers.ElevenLabsVoiceCloningProvider",
            return_value=mock_provider,
            create=True,
        ), patch(
            "cloud.elevenlabs_provider.ElevenLabsVoiceCloningProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_voice_clone(
                {"name": "Clone", "audio_paths": ["/tmp/a.wav"]},
                _mock_registry(),
            )

        assert result["voice_id"] == "new_voice"


# ── elevenlabs_sfx ───────────────────────────────────────────────────────────

class TestElevenLabsSFXHandler:

    def test_sfx_calls_provider(self):
        from rpc_handlers import _elevenlabs_sfx
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "audio_path": "/tmp/sfx.mp3",
            "duration": 5.0,
        }

        with patch(
            "cloud.elevenlabs_provider.ElevenLabsSFXProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_sfx(
                {"text": "explosion", "duration_seconds": 5},
                _mock_registry(),
            )

        assert result["audio_path"] == "/tmp/sfx.mp3"


# ── elevenlabs_voice_isolate ─────────────────────────────────────────────────

class TestElevenLabsVoiceIsolateHandler:

    def test_isolate_calls_provider(self):
        from rpc_handlers import _elevenlabs_voice_isolate
        mock_provider = MagicMock()
        mock_provider.isolate.return_value = {"audio_path": "/tmp/isolated.mp3"}

        with patch("cloud.router.get_voice_isolator", return_value=mock_provider):
            result = _elevenlabs_voice_isolate(
                {"audio_path": "/tmp/mix.wav"},
                _mock_registry(),
            )

        assert result["audio_path"] == "/tmp/isolated.mp3"

    def test_isolate_falls_back_to_demucs(self):
        from rpc_handlers import _elevenlabs_voice_isolate

        mock_demucs = MagicMock()
        mock_demucs.split.return_value = {
            "stems": {"vocals": "/tmp/vocals.wav", "other": "/tmp/other.wav"}
        }
        registry = _mock_registry()
        registry.get.return_value = mock_demucs

        with patch("cloud.router.get_voice_isolator", return_value=None):
            result = _elevenlabs_voice_isolate(
                {"audio_path": "/tmp/mix.wav"},
                registry,
            )

        assert "stems" in result
        registry.get.assert_called_with("demucs")


# ── elevenlabs_transcribe ────────────────────────────────────────────────────

class TestElevenLabsTranscribeHandler:

    def test_transcribe_calls_provider(self):
        from rpc_handlers import _elevenlabs_transcribe
        mock_provider = MagicMock()
        mock_provider.transcribe.return_value = {
            "text": "hello world",
            "language": "en",
            "words": [],
        }

        with patch(
            "cloud.elevenlabs_provider.ElevenLabsScribeProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_transcribe(
                {"audio_path": "/tmp/audio.wav", "language_code": "en"},
                _mock_registry(),
            )

        assert result["text"] == "hello world"


# ── elevenlabs_list_voices ───────────────────────────────────────────────────

class TestElevenLabsListVoicesHandler:

    def test_list_voices_returns_voices(self):
        from rpc_handlers import _elevenlabs_list_voices
        mock_voices = [
            {"voice_id": "a", "name": "Alice", "category": "premade"},
            {"voice_id": "b", "name": "Bob", "category": "premade"},
        ]

        with patch("cloud.elevenlabs_voices.list_voices", return_value=mock_voices):
            result = _elevenlabs_list_voices({}, _mock_registry())

        assert len(result["voices"]) == 2
        assert result["voices"][0]["name"] == "Alice"

    def test_list_voices_fallback_on_error(self):
        from rpc_handlers import _elevenlabs_list_voices
        from cloud.elevenlabs_voices import DEFAULT_VOICES

        with patch("cloud.elevenlabs_voices.list_voices", side_effect=RuntimeError("fail")):
            result = _elevenlabs_list_voices({}, _mock_registry())

        assert len(result["voices"]) == len(DEFAULT_VOICES)


# ── elevenlabs_dub ───────────────────────────────────────────────────────────

class TestElevenLabsDubHandler:

    def test_dub_calls_provider(self):
        from rpc_handlers import _elevenlabs_dub
        mock_provider = MagicMock()
        mock_provider.dub.return_value = {
            "audio_path": "/tmp/dubbed.mp3",
            "dubbing_id": "dub_456",
        }

        with patch(
            "cloud.elevenlabs_provider.ElevenLabsDubbingProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_dub(
                {
                    "audio_path": "/tmp/source.wav",
                    "target_language": "es",
                    "source_language": "en",
                },
                _mock_registry(),
            )

        assert result["dubbing_id"] == "dub_456"


# ── elevenlabs_speech_to_speech ──────────────────────────────────────────────

class TestElevenLabsSTSHandler:

    def test_sts_calls_provider(self):
        from rpc_handlers import _elevenlabs_speech_to_speech
        mock_provider = MagicMock()
        mock_provider.convert.return_value = {
            "audio_path": "/tmp/sts.mp3",
            "voice_id": "xyz",
        }

        with patch(
            "cloud.elevenlabs_provider.ElevenLabsSpeechToSpeechProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_speech_to_speech(
                {"audio_path": "/tmp/input.wav", "voice_id": "xyz"},
                _mock_registry(),
            )

        assert result["voice_id"] == "xyz"


# ── elevenlabs_forced_align ──────────────────────────────────────────────────

class TestElevenLabsForcedAlignHandler:

    def test_align_calls_provider(self):
        from rpc_handlers import _elevenlabs_forced_align
        mock_provider = MagicMock()
        mock_provider.align.return_value = {
            "alignment": [{"word": "hi", "start": 0.0, "end": 0.2}],
            "text": "hi there",
        }

        with patch(
            "cloud.elevenlabs_provider.ElevenLabsForcedAlignmentProvider",
            return_value=mock_provider,
        ):
            result = _elevenlabs_forced_align(
                {
                    "audio_path": "/tmp/audio.wav",
                    "text": "hi there",
                    "language_code": "en",
                },
                _mock_registry(),
            )

        assert len(result["alignment"]) == 1
