"""
Tests for cloud/elevenlabs_provider.py — all 11 provider classes.
All external API calls are mocked — no real keys needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_sf_info(duration=10.0, samplerate=44100):
    info = MagicMock()
    info.duration = duration
    info.samplerate = samplerate
    return info


def _mock_elevenlabs_module():
    """Build a mock elevenlabs module with minimal class stubs."""
    mock_el = MagicMock()
    mock_el.ElevenLabs = MagicMock
    mock_el.VoiceSettings = MagicMock
    return mock_el


# ── ElevenLabsTTSProvider ────────────────────────────────────────────────────

class TestElevenLabsTTSProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider()

    def test_missing_sdk_raises_import_error(self):
        provider = self._make_provider()
        with patch.dict(sys.modules, {"elevenlabs": None}):
            with pytest.raises(ImportError, match="elevenlabs package not installed"):
                provider.generate(text="hello")

    def test_missing_key_raises_runtime_error(self):
        provider = self._make_provider()
        mock_el = _mock_elevenlabs_module()
        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.ELEVENLABS_API_KEY = ""
            with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
                provider.generate(text="hello")

    def test_generate_saves_audio(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client
        mock_el.VoiceSettings = MagicMock

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg, \
             patch("cloud.elevenlabs_provider.sf") as mock_sf:
            mock_cfg.VOCALS_DIR = str(tmp_path)
            mock_sf.info.return_value = _mock_sf_info(5.0)

            result = provider.generate(text="Hello world", voice_id="abc123")

        assert "audio_path" in result
        assert result["voice_id"] == "abc123"
        mock_client.text_to_speech.convert.assert_called_once()


# ── ElevenLabsVoiceCloningProvider ───────────────────────────────────────────

class TestElevenLabsVoiceCloningProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsVoiceCloningProvider
        return ElevenLabsVoiceCloningProvider()

    def test_missing_key_raises_runtime_error(self):
        provider = self._make_provider()
        mock_el = _mock_elevenlabs_module()
        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.ELEVENLABS_API_KEY = ""
            with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
                provider.clone_instant(name="test", audio_paths=[])

    def test_clone_returns_voice_id(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_voice = MagicMock()
        mock_voice.voice_id = "new_voice_123"
        mock_voice.name = "My Clone"
        mock_client = MagicMock()
        mock_client.clone.return_value = mock_voice
        mock_el.ElevenLabs.return_value = mock_client

        # Create a dummy audio file
        dummy = tmp_path / "sample.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            result = provider.clone_instant(
                name="My Clone",
                audio_paths=[str(dummy)],
            )

        assert result["voice_id"] == "new_voice_123"
        assert result["name"] == "My Clone"


# ── ElevenLabsSpeechToSpeechProvider ─────────────────────────────────────────

class TestElevenLabsSpeechToSpeechProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsSpeechToSpeechProvider
        return ElevenLabsSpeechToSpeechProvider()

    def test_convert_saves_audio(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()
        mock_client.speech_to_speech.convert.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "input.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg, \
             patch("cloud.elevenlabs_provider.sf") as mock_sf:
            mock_cfg.VOCALS_DIR = str(tmp_path)
            mock_sf.info.return_value = _mock_sf_info(3.0)

            result = provider.convert(audio_path=str(dummy), voice_id="xyz")

        assert "audio_path" in result
        assert result["voice_id"] == "xyz"


# ── ElevenLabsMusicProvider ──────────────────────────────────────────────────

class TestElevenLabsMusicProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsMusicProvider
        return ElevenLabsMusicProvider()

    def test_generate_saves_audio(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()
        mock_client.text_to_sound_effects.convert.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg, \
             patch("cloud.elevenlabs_provider.sf") as mock_sf:
            mock_cfg.GENERATION_DIR = str(tmp_path)
            mock_sf.info.return_value = _mock_sf_info(30.0)

            result = provider.generate(prompt="upbeat jazz", duration=30)

        assert "audio_path" in result
        assert result["duration"] == 30.0


# ── ElevenLabsSFXProvider ────────────────────────────────────────────────────

class TestElevenLabsSFXProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsSFXProvider
        return ElevenLabsSFXProvider()

    def test_generate_saves_audio(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()
        mock_client.text_to_sound_effects.convert.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg, \
             patch("cloud.elevenlabs_provider.sf") as mock_sf:
            mock_cfg.SFX_DIR = str(tmp_path)
            mock_sf.info.return_value = _mock_sf_info(5.0)

            result = provider.generate(text="thunder crash", duration_seconds=5)

        assert "audio_path" in result
        assert result["duration"] == 5.0


# ── ElevenLabsVoiceIsolatorProvider ──────────────────────────────────────────

class TestElevenLabsVoiceIsolatorProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsVoiceIsolatorProvider
        return ElevenLabsVoiceIsolatorProvider()

    def test_isolate_saves_audio(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()
        mock_client.audio_isolation.audio_isolation.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "mix.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.STEMS_DIR = str(tmp_path)

            result = provider.isolate(audio_path=str(dummy))

        assert "audio_path" in result


# ── ElevenLabsScribeProvider ─────────────────────────────────────────────────

class TestElevenLabsScribeProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsScribeProvider
        return ElevenLabsScribeProvider()

    def test_transcribe_returns_text(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_word = MagicMock()
        mock_word.text = "hello"
        mock_word.start = 0.0
        mock_word.end = 0.5

        mock_result = MagicMock()
        mock_result.text = "hello world"
        mock_result.words = [mock_word]
        mock_client.speech_to_text.convert.return_value = mock_result
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "speech.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.TRANSCRIPTS_DIR = str(tmp_path)

            result = provider.transcribe(audio_path=str(dummy), language_code="en")

        assert result["text"] == "hello world"
        assert result["language"] == "en"
        assert len(result["words"]) == 1


# ── ElevenLabsForcedAlignmentProvider ────────────────────────────────────────

class TestElevenLabsForcedAlignmentProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsForcedAlignmentProvider
        return ElevenLabsForcedAlignmentProvider()

    def test_align_returns_alignment(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_word = MagicMock()
        mock_word.text = "test"
        mock_word.start = 0.0
        mock_word.end = 0.3

        mock_result = MagicMock()
        mock_result.text = "test phrase"
        mock_result.words = [mock_word]
        mock_client.speech_to_text.convert.return_value = mock_result
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "audio.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            result = provider.align(
                audio_path=str(dummy),
                text="test phrase",
                language_code="en",
            )

        assert len(result["alignment"]) == 1
        assert result["alignment"][0]["word"] == "test"


# ── ElevenLabsDubbingProvider ────────────────────────────────────────────────

class TestElevenLabsDubbingProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsDubbingProvider
        return ElevenLabsDubbingProvider()

    def test_dub_returns_audio_path(self, tmp_path):
        from unittest.mock import patch as _patch
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_dub_response = MagicMock()
        mock_dub_response.dubbing_id = "dub_123"
        mock_client.dubbing.create.return_value = mock_dub_response

        # Provider polls via client.dubbing.get() — mock it to return "dubbed" immediately
        mock_status = MagicMock()
        mock_status.status = "dubbed"
        mock_client.dubbing.get.return_value = mock_status

        # Provider downloads via client.dubbing.audio.get()
        mock_client.dubbing.audio.get.return_value = [b"\x00" * 100]
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "source.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg, \
             _patch("time.sleep"):   # prevent polling delay
            mock_cfg.DUBBING_DIR = str(tmp_path)

            result = provider.dub(
                audio_path=str(dummy),
                target_language="es",
                source_language="en",
            )

        assert "audio_path" in result
        assert result["dubbing_id"] == "dub_123"

    def test_missing_key_raises_runtime_error(self, tmp_path):
        provider = self._make_provider()
        mock_el = _mock_elevenlabs_module()

        dummy = tmp_path / "source.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.ELEVENLABS_API_KEY = ""
            with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
                provider.dub(
                    audio_path=str(dummy),
                    target_language="es",
                )


# ── ElevenLabsProfessionalVoiceCloningProvider ───────────────────────────────

class TestElevenLabsProfessionalVoiceCloningProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsProfessionalVoiceCloningProvider
        return ElevenLabsProfessionalVoiceCloningProvider()

    def test_create_returns_voice_id(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        # pvc.create → voice_id
        mock_voice_resp = MagicMock()
        mock_voice_resp.voice_id = "pvc_voice_abc"
        mock_client.voices.pvc.create.return_value = mock_voice_resp

        # pvc.samples.create → list of samples
        mock_sample = MagicMock()
        mock_client.voices.pvc.samples.create.return_value = [mock_sample]

        # pvc.train → status
        mock_train_resp = MagicMock()
        mock_train_resp.status = "queued"
        mock_client.voices.pvc.train.return_value = mock_train_resp

        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "sample.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            result = provider.create(
                name="Pro Clone",
                language="en",
                audio_paths=[str(dummy)],
                description="Test PVC",
            )

        assert result["voice_id"] == "pvc_voice_abc"
        assert result["name"] == "Pro Clone"
        assert result["samples_uploaded"] == 1
        assert result["training_status"] == "queued"
        mock_client.voices.pvc.create.assert_called_once_with(
            name="Pro Clone", language="en", description="Test PVC"
        )
        mock_client.voices.pvc.train.assert_called_once_with(voice_id="pvc_voice_abc")

    def test_get_training_status_returns_state(self):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_ft = MagicMock()
        mock_ft.finetuning_state = "fine_tuned"
        mock_ft.progress = {"percent": 100}
        mock_ft.message = "Training complete"

        mock_voice = MagicMock()
        mock_voice.voice_id = "pvc_voice_abc"
        mock_voice.name = "Pro Clone"
        mock_voice.fine_tuning = mock_ft
        mock_client.voices.get.return_value = mock_voice
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            result = provider.get_training_status(voice_id="pvc_voice_abc")

        assert result["finetuning_state"] == "fine_tuned"
        assert result["is_ready"] is True
        assert result["is_failed"] is False

    def test_create_remove_background_noise_passed(self, tmp_path):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_voice_resp = MagicMock()
        mock_voice_resp.voice_id = "pvc_xyz"
        mock_client.voices.pvc.create.return_value = mock_voice_resp
        mock_client.voices.pvc.samples.create.return_value = [MagicMock()]
        mock_train = MagicMock(); mock_train.status = "queued"
        mock_client.voices.pvc.train.return_value = mock_train
        mock_el.ElevenLabs.return_value = mock_client

        dummy = tmp_path / "sample.wav"
        dummy.write_bytes(b"\x00" * 100)

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            provider.create(
                name="Clean Clone",
                language="fr",
                audio_paths=[str(dummy)],
                remove_background_noise=True,
            )

        call_kwargs = mock_client.voices.pvc.samples.create.call_args[1]
        assert call_kwargs["remove_background_noise"] is True


# ── ElevenLabsVoiceRemixingProvider ─────────────────────────────────────────

class TestElevenLabsVoiceRemixingProvider:

    def _make_provider(self):
        from cloud.elevenlabs_provider import ElevenLabsVoiceRemixingProvider
        return ElevenLabsVoiceRemixingProvider()

    def test_remix_returns_previews(self, tmp_path):
        import base64 as _b64
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        # A minimal 3-byte "MP3" payload (content doesn't matter — it's all mocked)
        audio_bytes = b"\xff\xfb\x90"
        mock_preview = MagicMock()
        mock_preview.audio_base_64 = _b64.b64encode(audio_bytes).decode()
        mock_preview.generated_voice_id = "gen_remix_001"
        mock_preview.duration_secs = 3.0
        mock_preview.media_type = "audio/mpeg"

        mock_response = MagicMock()
        mock_response.previews = [mock_preview]
        mock_response.text = "Sample text used"
        mock_client.text_to_voice.remix.return_value = mock_response
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.VOCALS_DIR = str(tmp_path)

            result = provider.remix(
                voice_id="src_voice_123",
                voice_description="Make it deeper with a Southern US accent",
            )

        assert len(result["previews"]) == 1
        assert result["previews"][0]["generated_voice_id"] == "gen_remix_001"
        assert result["previews"][0]["duration_secs"] == 3.0
        assert result["sample_text"] == "Sample text used"

        # File should exist on disk
        audio_path = result["previews"][0]["audio_path"]
        assert Path(audio_path).exists()
        assert Path(audio_path).read_bytes() == audio_bytes

    def test_remix_passes_optional_params(self, tmp_path):
        import base64 as _b64
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_preview = MagicMock()
        mock_preview.audio_base_64 = _b64.b64encode(b"\x00").decode()
        mock_preview.generated_voice_id = "gen_002"
        mock_preview.duration_secs = 2.0
        mock_preview.media_type = "audio/mpeg"

        mock_response = MagicMock()
        mock_response.previews = [mock_preview]
        mock_response.text = ""
        mock_client.text_to_voice.remix.return_value = mock_response
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"), \
             patch("cloud.elevenlabs_provider.config") as mock_cfg:
            mock_cfg.VOCALS_DIR = str(tmp_path)

            provider.remix(
                voice_id="v1",
                voice_description="Higher pitch",
                text="Hello world",
                seed=42,
                guidance_scale=0.8,
                prompt_strength=0.6,
            )

        call_kwargs = mock_client.text_to_voice.remix.call_args[1]
        assert call_kwargs["seed"] == 42
        assert call_kwargs["guidance_scale"] == 0.8
        assert call_kwargs["prompt_strength"] == 0.6
        assert call_kwargs["text"] == "Hello world"
        assert call_kwargs["auto_generate_text"] is False   # suppressed when text provided

    def test_save_remix_returns_voice(self):
        provider = self._make_provider()
        mock_el = MagicMock()
        mock_client = MagicMock()

        mock_voice = MagicMock()
        mock_voice.voice_id = "saved_voice_777"
        mock_voice.name = "My Remix"
        mock_client.text_to_voice.create.return_value = mock_voice
        mock_el.ElevenLabs.return_value = mock_client

        with patch("cloud.elevenlabs_provider._require_sdk", return_value=mock_el), \
             patch("cloud.elevenlabs_provider._require_key", return_value="test-key"):
            result = provider.save_remix(
                voice_name="My Remix",
                voice_description="Deeper British voice",
                generated_voice_id="gen_remix_001",
            )

        assert result["voice_id"] == "saved_voice_777"
        assert result["name"] == "My Remix"
        mock_client.text_to_voice.create.assert_called_once_with(
            voice_name="My Remix",
            voice_description="Deeper British voice",
            generated_voice_id="gen_remix_001",
        )
