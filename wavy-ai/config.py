"""
Wavy Labs AI backend — central configuration.
All constants are overridable via environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

import appdirs

# Load .env file from the wavy-ai directory if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass  # python-dotenv optional; set env vars manually if not installed

# ── Server ────────────────────────────────────────────────────────────────────
HOST: str = os.environ.get("WAVY_AI_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("WAVY_AI_PORT", "5555"))

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR: Path = Path(
    os.environ.get("WAVY_DATA_DIR",
                   appdirs.user_data_dir("WavyLabs", "WavyLabs"))
)
MODEL_DIR:      Path = DATA_DIR / "models"
GENERATION_DIR: Path = DATA_DIR / "generations"
STEMS_DIR:      Path = DATA_DIR / "stems"
VOCALS_DIR:     Path = DATA_DIR / "vocals"
MASTERED_DIR:   Path = DATA_DIR / "mastered"
CTM_DIR:        Path = DATA_DIR / "code_to_music"
SFX_DIR:        Path = DATA_DIR / "sfx"
DUBBING_DIR:    Path = DATA_DIR / "dubbing"
TRANSCRIPTS_DIR:Path = DATA_DIR / "transcripts"
MIDI_LIBRARY_DIR:Path = DATA_DIR / "midi_library"

for _d in (MODEL_DIR, GENERATION_DIR, STEMS_DIR, VOCALS_DIR, MASTERED_DIR,
           CTM_DIR, SFX_DIR, DUBBING_DIR, TRANSCRIPTS_DIR, MIDI_LIBRARY_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Model defaults ────────────────────────────────────────────────────────────
DEFAULT_MUSIC_MODEL: str   = os.environ.get("WAVY_DEFAULT_MODEL", "elevenlabs_music")
DEFAULT_DURATION:    float = float(os.environ.get("WAVY_DEFAULT_DURATION", "30"))
DEFAULT_TEMPO:       int   = int(os.environ.get("WAVY_DEFAULT_TEMPO", "120"))
DEFAULT_STEMS:       int   = int(os.environ.get("WAVY_DEFAULT_STEMS", "4"))
TARGET_LUFS:         float = float(os.environ.get("WAVY_TARGET_LUFS", "-14.0"))

# ── Cloud provider ────────────────────────────────────────────────────────────
CLOUD_PROVIDER:      str = os.environ.get("WAVY_CLOUD_PROVIDER", "elevenlabs")
ANTHROPIC_API_KEY:   str = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_API_KEY:        str = os.environ.get("GROQ_API_KEY", "")
ELEVENLABS_API_KEY:  str = os.environ.get("ELEVENLABS_API_KEY", "")
FREESOUND_API_KEY:   str = os.environ.get("FREESOUND_API_KEY", "")
HOOKTHEORY_ACTIVKEY: str = os.environ.get("HOOKTHEORY_ACTIVKEY", "")
JAMENDO_CLIENT_ID:   str = os.environ.get("JAMENDO_CLIENT_ID",   "0de4e92c")
SOUNDCLOUD_CLIENT_ID:str = os.environ.get("SOUNDCLOUD_CLIENT_ID","")


# ── Generation limits ─────────────────────────────────────────────────────────
MAX_DURATION_FREE:   float = 15.0   # musicgen-small; keep short for free tier
MAX_DURATION_PRO:    float = 60.0
MAX_DURATION_STUDIO: float = 300.0

# ── GPU ───────────────────────────────────────────────────────────────────────
FORCE_CPU: bool = os.environ.get("WAVY_FORCE_CPU", "").lower() in ("1", "true", "yes")
