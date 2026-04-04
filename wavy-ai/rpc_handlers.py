"""
RPC handler registry — maps method names to callables.
Each handler signature: (params: dict, registry: ModelRegistry) -> Any

This module is a thin registry that imports handlers from domain-specific
sub-modules under ``rpc/``.  Backward-compatible re-exports (_validate_path,
_ensure_wav) are kept for callers like server.py.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from models.registry import ModelRegistry

# ── Re-exports for backward compatibility (server.py imports these) ──────────
from rpc.helpers import _validate_path, _ensure_wav  # noqa: F401

# ── Domain modules ───────────────────────────────────────────────────────────
from rpc.core import (
    _health, _list_models, _delete_model, _load_model, _unload_model,
    _save_persona, _load_personas, _startup_check, _set_session_context,
    _update_api_keys,
)
from rpc.audio import (
    _generate_music, _split_stems, _mix_analyze, _master_audio,
    _prompt_command, _code_to_music, _generate_stem, _replace_section,
    _extend_music, _chat_generate,
)
from rpc.midi import (
    _audio_to_midi, _prompt_to_midi, _chord_suggestions, _beat_builder,
    _regenerate_bar, _get_instrument_choices, _compose,
    _midi_extend, _midi_recompose, _midi_layer,
)
from rpc.library import (
    _get_bitmidi_inspirations, _database_tips, _browse_dataset,
    _download_library_file, _midicaps_library_status,
    _start_midicaps_download, _test_databases,
)
from rpc.elevenlabs import (
    _elevenlabs_tts, _elevenlabs_voice_clone, _elevenlabs_speech_to_speech,
    _elevenlabs_sfx, _elevenlabs_voice_isolate, _elevenlabs_transcribe,
    _elevenlabs_forced_align, _elevenlabs_dub, _elevenlabs_music_stems,
    _elevenlabs_list_voices,
)
from rpc.fx import (
    _apply_track_fx, _pitch_correct_audio, _generate_arpeggio,
    _granular_chop_audio, _ncs_song_structure, _generate_riser,
    _apply_sidechain_pump, _list_soundfonts, _download_soundfont_rpc,
    _text_to_fx_chain, _analyze_reference, _analyze_song_material,
)
from rpc.instruments import (
    _list_instruments, _get_instrument_details,
    _download_instrument_pack, _list_instrument_packs,
)

# ── Handler registry ─────────────────────────────────────────────────────────
RPC_HANDLERS: Dict[str, Callable[[dict, ModelRegistry], Any]] = {
    "health":            _health,
    "startup_check":     _startup_check,
    "update_api_keys":   _update_api_keys,
    "generate_music":  _generate_music,
    "split_stems":     _split_stems,
    "mix_analyze":     _mix_analyze,
    "master_audio":    _master_audio,
    "prompt_command":  _prompt_command,
    "code_to_music":   _code_to_music,
    "list_models":     _list_models,
    "load_model":      _load_model,
    "unload_model":    _unload_model,
    "delete_model":    _delete_model,
    # Suno-inspired features
    "generate_stem":   _generate_stem,
    "replace_section": _replace_section,
    "audio_to_midi":   _audio_to_midi,
    "extend_music":    _extend_music,
    "prompt_to_midi":  _prompt_to_midi,
    "save_persona":    _save_persona,
    "load_personas":   _load_personas,
    "compose":                    _compose,
    "chat_generate":              _chat_generate,
    "get_instrument_choices":     _get_instrument_choices,
    "get_bitmidi_inspirations":   _get_bitmidi_inspirations,
    "database_tips":              _database_tips,
    "browse_dataset":             _browse_dataset,
    "download_library_file":      _download_library_file,
    "midicaps_library_status":    _midicaps_library_status,
    "start_midicaps_download":    _start_midicaps_download,
    "test_databases":             _test_databases,
    "regenerate_bar":          _regenerate_bar,
    "chord_suggestions":   _chord_suggestions,
    "beat_builder":        _beat_builder,
    "set_session_context": _set_session_context,
    # Genre FX / Pitch / Arp / Granular (v0.9.5)
    "apply_track_fx":        _apply_track_fx,
    "pitch_correct_audio":   _pitch_correct_audio,
    "generate_arpeggio":     _generate_arpeggio,
    "granular_chop_audio":   _granular_chop_audio,
    # ElevenLabs
    "elevenlabs_tts":              _elevenlabs_tts,
    "elevenlabs_voice_clone":      _elevenlabs_voice_clone,
    "elevenlabs_speech_to_speech": _elevenlabs_speech_to_speech,
    "elevenlabs_sfx":              _elevenlabs_sfx,
    "elevenlabs_voice_isolate":    _elevenlabs_voice_isolate,
    "elevenlabs_transcribe":       _elevenlabs_transcribe,
    "elevenlabs_forced_align":     _elevenlabs_forced_align,
    "elevenlabs_dub":              _elevenlabs_dub,
    "elevenlabs_music_stems":      _elevenlabs_music_stems,
    "elevenlabs_list_voices":      _elevenlabs_list_voices,
    # NCS Toolkit (v0.9.9)
    "ncs_song_structure":    _ncs_song_structure,
    "generate_riser":        _generate_riser,
    "apply_sidechain_pump":  _apply_sidechain_pump,
    # SoundFont Manager (v0.10.2)
    "list_soundfonts":       _list_soundfonts,
    "download_soundfont":    _download_soundfont_rpc,
    # AI Production Suite (v0.12.0)
    "midi_extend":           _midi_extend,
    "midi_recompose":        _midi_recompose,
    "midi_layer":            _midi_layer,
    "text_to_fx_chain":      _text_to_fx_chain,
    "analyze_reference":     _analyze_reference,
    "analyze_song_material": _analyze_song_material,
    # Instrument Catalog (v0.14.0)
    "list_instruments":          _list_instruments,
    "get_instrument_details":    _get_instrument_details,
    "download_instrument_pack":  _download_instrument_pack,
    "list_instrument_packs":     _list_instrument_packs,
}
