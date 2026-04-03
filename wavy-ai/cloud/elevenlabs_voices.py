"""
ElevenLabs voice listing with TTL cache and hardcoded fallback.
"""

from __future__ import annotations

import threading
import time

from loguru import logger

import config

# Cache: (timestamp, list[dict])
_cache: tuple[float, list[dict]] = (0.0, [])
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 minutes

# Hardcoded premade voices — used when no API key is set or API is unreachable
DEFAULT_VOICES: list[dict] = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George",   "category": "premade"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah",    "category": "premade"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam",     "category": "premade"},
    {"voice_id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "category": "premade"},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily",     "category": "premade"},
    {"voice_id": "bIHbv24MWmeRgasZH58o", "name": "Will",     "category": "premade"},
    {"voice_id": "nPczCjzI2devNBz1zQrb", "name": "Brian",    "category": "premade"},
    {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda",  "category": "premade"},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel",   "category": "premade"},
]


def list_voices() -> list[dict]:
    """Return available ElevenLabs voices with 5-min TTL cache.

    Falls back to DEFAULT_VOICES if no API key or on error.
    Thread-safe: uses a lock to prevent duplicate fetches.
    """
    global _cache

    now = time.time()
    with _cache_lock:
        if _cache[1] and (now - _cache[0]) < _CACHE_TTL:
            return _cache[1]

    key = config.ELEVENLABS_API_KEY
    if not key:
        return DEFAULT_VOICES

    try:
        from cloud.elevenlabs_provider import _require_sdk
        el = _require_sdk()
        client = el.ElevenLabs(api_key=key)
        response = client.voices.get_all()

        voices = [
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "category": getattr(v, "category", "unknown"),
            }
            for v in response.voices
        ]

        if voices:
            with _cache_lock:
                _cache = (now, voices)
            logger.debug(f"ElevenLabs voices cached: {len(voices)} voices")
            return voices

    except Exception as exc:
        logger.warning(f"ElevenLabs voice listing failed: {exc}")

    with _cache_lock:
        return _cache[1] if _cache[1] else DEFAULT_VOICES
