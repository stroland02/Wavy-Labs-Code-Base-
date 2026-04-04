"""
Cloud provider router — selects the right music/command provider.

Music generation (default: ElevenLabs cloud API):
  WAVY_CLOUD_PROVIDER=elevenlabs  (default) → ElevenLabsMusicProvider
  WAVY_CLOUD_PROVIDER=local                 → None (returns error — no local fallback)

Prompt commands (priority order):
  ANTHROPIC_API_KEY   → AnthropicCommandProvider  (best quality)
  GROQ_API_KEY        → GroqCommandProvider        (free tier, llama-3.3-70b)
  (none set)          → None (caller uses registry: local Mistral 7B GGUF fallback)

ElevenLabs APIs (TTS, SFX, Voice Isolate, Scribe, Dubbing):
  All require ELEVENLABS_API_KEY.
"""

from __future__ import annotations

import config


def get_music_provider(tier: str = "free"):
    """
    Returns a cloud music provider, or None to signal local fallback.
    Default: ElevenLabs. None → returns error (no local fallback).
    """
    name = config.CLOUD_PROVIDER
    if name == "local":
        return None
    # Default: ElevenLabs
    from cloud.elevenlabs_provider import ElevenLabsMusicProvider
    return ElevenLabsMusicProvider()


def get_command_provider():
    """
    Returns a cloud command provider, or None to signal local fallback.
    Priority: Anthropic → Groq → None (local Mistral 7B GGUF).
    """
    if config.ANTHROPIC_API_KEY:
        from cloud.anthropic_provider import AnthropicCommandProvider
        return AnthropicCommandProvider()
    if config.GROQ_API_KEY:
        from cloud.groq_provider import GroqCommandProvider
        return GroqCommandProvider()
    return None


# ── ElevenLabs-specific routers ──────────────────────────────────────────────

def get_tts_provider():
    """Returns an ElevenLabs TTS provider if API key is set, else None."""
    if config.ELEVENLABS_API_KEY:
        from cloud.elevenlabs_provider import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider()
    return None


def get_sfx_provider():
    """Returns an ElevenLabs SFX provider if API key is set, else None."""
    if config.ELEVENLABS_API_KEY:
        from cloud.elevenlabs_provider import ElevenLabsSFXProvider
        return ElevenLabsSFXProvider()
    return None


def get_voice_isolator():
    """Returns an ElevenLabs Voice Isolator if API key is set, else None."""
    if config.ELEVENLABS_API_KEY:
        from cloud.elevenlabs_provider import ElevenLabsVoiceIsolatorProvider
        return ElevenLabsVoiceIsolatorProvider()
    return None


def get_scribe_provider():
    """Returns an ElevenLabs Scribe (STT) provider if API key is set, else None."""
    if config.ELEVENLABS_API_KEY:
        from cloud.elevenlabs_provider import ElevenLabsScribeProvider
        return ElevenLabsScribeProvider()
    return None


def get_dubbing_provider():
    """Returns an ElevenLabs Dubbing provider if API key is set, else None."""
    if config.ELEVENLABS_API_KEY:
        from cloud.elevenlabs_provider import ElevenLabsDubbingProvider
        return ElevenLabsDubbingProvider()
    return None
