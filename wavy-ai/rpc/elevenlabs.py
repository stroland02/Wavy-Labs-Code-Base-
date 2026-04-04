"""ElevenLabs RPC handlers."""
from __future__ import annotations

from loguru import logger
from models.registry import ModelRegistry

# ── ElevenLabs handlers ──────────────────────────────────────────────────────

def _elevenlabs_tts(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs TTS — requires ELEVENLABS_API_KEY."""
    from cloud.router import get_tts_provider
    provider = get_tts_provider()
    if provider is None:
        return {"error": "ELEVENLABS_API_KEY not set. ElevenLabs is required for TTS."}
    return provider.generate(**params)


def _elevenlabs_voice_clone(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs instant voice cloning -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsVoiceCloningProvider
    provider = ElevenLabsVoiceCloningProvider()
    return provider.clone_instant(**params)


def _elevenlabs_speech_to_speech(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs speech-to-speech -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsSpeechToSpeechProvider
    provider = ElevenLabsSpeechToSpeechProvider()
    return provider.convert(**params)


def _elevenlabs_sfx(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs SFX generation -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsSFXProvider
    provider = ElevenLabsSFXProvider()
    return provider.generate(**params)


def _elevenlabs_voice_isolate(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs voice isolation -- falls back to Demucs 2-stem."""
    try:
        from cloud.router import get_voice_isolator
        provider = get_voice_isolator()
        if provider is None:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        return provider.isolate(**params)
    except Exception as exc:
        logger.warning(f"ElevenLabs voice isolate failed ({exc}), falling back to Demucs")
        try:
            model = registry.get("demucs")
            return model.split(
                audio_path=params.get("audio_path", ""),
                stems=2,
            )
        except Exception as demucs_exc:
            return {"error": f"ElevenLabs isolate failed ({exc}) and Demucs fallback failed ({demucs_exc})"}


def _elevenlabs_transcribe(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs Scribe (STT) -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsScribeProvider
    provider = ElevenLabsScribeProvider()
    return provider.transcribe(**params)


def _elevenlabs_forced_align(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs forced alignment -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsForcedAlignmentProvider
    provider = ElevenLabsForcedAlignmentProvider()
    return provider.align(**params)


def _elevenlabs_dub(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs AI dubbing -- no fallback."""
    from cloud.elevenlabs_provider import ElevenLabsDubbingProvider
    provider = ElevenLabsDubbingProvider()
    return provider.dub(**params)


def _elevenlabs_music_stems(params: dict, registry: ModelRegistry) -> dict:
    """ElevenLabs Music stem splitter -- falls back to Demucs 4-stem."""
    try:
        from cloud.elevenlabs_provider import ElevenLabsMusicProvider
        provider = ElevenLabsMusicProvider()
        return provider.separate_stems(**params)
    except Exception as exc:
        logger.warning(f"ElevenLabs music stems failed ({exc}), falling back to Demucs")
        try:
            model = registry.get("demucs")
            return model.split(
                audio_path=params.get("audio_path", ""),
                stems=params.get("stems", 4),
            )
        except Exception as demucs_exc:
            return {"error": f"EL stem split failed ({exc}) and Demucs fallback failed ({demucs_exc})"}


def _elevenlabs_list_voices(params: dict, registry: ModelRegistry) -> dict:
    """List available ElevenLabs voices -- falls back to default list."""
    from cloud.elevenlabs_voices import list_voices, DEFAULT_VOICES
    try:
        voices = list_voices()
    except Exception:
        voices = DEFAULT_VOICES
    return {"voices": voices}

