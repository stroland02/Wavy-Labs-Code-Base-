"""
compose_agent.py — Multi-track arrangement generator using Claude (with fallbacks).

Mode "arrange": Plans a full composition (drums/bass/chords/melody) and generates
                a separate MIDI file per part.
Mode "fill":    Single-stage, returns notes for the active piano roll clip.
"""

from __future__ import annotations

import json
import random as _rand
import re
import uuid
from pathlib import Path
from typing import Any

import mido
from loguru import logger

import config
from utils.midi_library import (
    find_seed          as _midi_find_seed,   # kept for tests / key-anchor path
    find_midi_for_role as _midi_find_role,
    find_midi_raw      as _midi_find_raw,
)
from utils.music_theory import (
    drum_pattern,
    bass_line,
    chord_progression,
    melody_line,
    scale_notes,
    chord_schedule,
    chord_progression_from_schedule,
    bass_line_harmonic,
    melody_line_harmonic,
    snap_notes_to_scale,
    detect_key_from_notes,
)


# ── Session store (in-process, capped at 50) ─────────────────────────────────

_MAX_SESSIONS = 50
_sessions: dict[str, dict] = {}

# Default part colors by role
_ROLE_COLORS = {
    "drums":   "#e74c3c",
    "bass":    "#2ecc71",
    "chords":  "#3498db",
    "melody":  "#9b59b6",
    "counter": "#f39c12",
    "pad":     "#1abc9c",
    "lead":    "#e67e22",
}

# Per-role instrument plugin names (used in createMidiTrack)
_INSTRUMENT_FOR_ROLE = {
    "bass":    "lb302",
    "melody":  "bitinvader",
    "lead":    "bitinvader",
    "chords":  "tripleoscillator",
    "pad":     "tripleoscillator",
    "counter": "tripleoscillator",
}

# Normalize free-form LLM role names to canonical preset keys
_ROLE_NORMALIZE: dict[str, str] = {
    # Keyboard / chords variants
    "piano":        "chords",
    "keys":         "chords",
    "keyboard":     "chords",
    "electric piano": "chords",
    "ep":           "chords",
    "organ":        "chords",
    "synth chords": "chords",
    "chords":       "chords",
    # Melody / lead vocal variants
    "vocal":        "melody",
    "lead vocal":   "melody",
    "lead_vocal":   "melody",
    "vocals":       "melody",
    "synth lead":   "melody",
    "synth_lead":   "melody",
    "arp":          "melody",
    "arpeggiated":  "melody",
    # Pad variants
    "ambient pad":  "pad",
    "ambient_pad":  "pad",
    "strings":      "pad",
    "strings pad":  "pad",
    "atmosphere":   "pad",
    "ambient":      "pad",
    "synth pad":    "pad",
    # Lead / guitar variants
    "guitar":       "lead",
    "electric guitar": "lead",
    "synth":        "lead",
    "lead synth":   "lead",
    # Counter / harmony variants
    "harmony":      "counter",
    "counter melody": "counter",
    "counter_melody": "counter",
    "countermelody": "counter",
    "backing":      "counter",
    # Explicit canonical (pass-through)
    "bass":         "bass",
    "lead":         "lead",
    "melody":       "melody",
    "pad":          "pad",
    "counter":      "counter",
    "drums":        "drums",
}


def _detect_genre(prompt: str, bpm: int) -> str:
    """Detect music genre from prompt text and BPM.

    Active genres: default, future_bass, house, trap, ambient, lofi, jazz, 808
    Removed sub-genres map to closest active parent.
    """
    text = prompt.lower()
    # Check specific sub-genres first → map to closest active genre
    if any(w in text for w in ("rage trap", "rage_trap", "playboi carti", "carti", "rage beat")):
        return "trap"
    if any(w in text for w in ("uk drill", "uk_drill", "central cee", "drill")):
        return "trap"
    if any(w in text for w in ("future bass", "future_bass", "alan walker", "melodic bass")):
        return "future_bass"
    if any(w in text for w in ("big room", "big_room", "tiesto", "tiësto", "festival edm")):
        return "house"
    if any(w in text for w in ("neo soul", "neo-soul", "neo_soul", "omar apollo", "r&b groove", "rnb groove")):
        return "jazz"
    if any(w in text for w in ("pop trap", "pop_trap", "kid laroi", "laroi", "guitar trap")):
        return "trap"
    if any(w in text for w in ("trap", "808")):
        return "trap"
    if any(w in text for w in ("dnb", "drum and bass", "drum & bass", "jungle", "breakbeat")):
        return "house"
    if any(w in text for w in ("r&b", "rnb", "r & b", "soul", "funk", "groove")):
        return "jazz"
    if any(w in text for w in ("jazz", "swing", "bebop", "bossa", "blues")):
        return "jazz"
    if any(w in text for w in ("ambient", "atmosphere", "drone", "space", "ethereal")):
        return "ambient"
    if any(w in text for w in ("lo-fi", "lofi", "lo fi", "chill", "study")):
        return "lofi"
    if any(w in text for w in ("house", "techno", "edm", "dance", "club", "rave", "garage")):
        return "house"
    # BPM heuristics (after keyword matching)
    if 165 <= bpm <= 185:
        return "house"      # DnB-speed → house (closest active EDM genre)
    if bpm >= 145:
        return "trap"
    if bpm >= 125:
        return "house"
    if 100 <= bpm <= 124:
        return "jazz"
    if bpm <= 99:
        return "lofi"
    return "default"


# Genre-aware preset mapping — (instrument_plugin, relative_preset_path)
# Paths are relative to <lmms data dir>/presets/
_PRESET_FOR_GENRE_ROLE: dict[str, dict[str, tuple[str, str]]] = {
    # ── Active genres (v0.10.3 — LSP community presets) ───────────────────
    "trap": {
        "bass":    ("lb302",            "LB302/Wavy-SubBass.xpf"),
        "chords":  ("tripleoscillator", "TripleOscillator/LSP-TrapEPiano.xpf"),
        "pad":     ("tripleoscillator", "TripleOscillator/LSP-ReeseBass.xpf"),
        "melody":  ("tripleoscillator", "TripleOscillator/Wavy-TrapLead.xpf"),
        "lead":    ("monstro",          "Monstro/LSP-CyberpunkBass.xpf"),
        "counter": ("bitinvader",       "BitInvader/pluck.xpf"),
    },
    "lofi": {
        "bass":    ("lb302",            "LB302/Wavy-SubBass.xpf"),
        "chords":  ("tripleoscillator", "TripleOscillator/LSP-DreamcorePiano.xpf"),
        "pad":     ("organic",          "Organic/pad_sweep.xpf"),
        "melody":  ("tripleoscillator", "TripleOscillator/LSP-TanakaLofiKeyz.xpf"),
        "lead":    ("tripleoscillator", "TripleOscillator/LSP-Traum.xpf"),
        "counter": ("organic",          "Organic/Wavy-LofPad.xpf"),
    },
    "house": {
        "bass":    ("lb302",            "LB302/Wavy-HouseBass.xpf"),
        "chords":  ("tripleoscillator", "TripleOscillator/LSP-DetroitChord.xpf"),
        "pad":     ("tripleoscillator", "TripleOscillator/LSP-PadHouse.xpf"),
        "melody":  ("tripleoscillator", "TripleOscillator/LSP-HousePiano.xpf"),
        "lead":    ("tripleoscillator", "TripleOscillator/Wavy-HouseStab.xpf"),
        "counter": ("opulenz",          "OpulenZ/Combo_organ.xpf"),
    },
    "ambient": {
        "bass":    ("tripleoscillator", "TripleOscillator/LSP-BassAmbient.xpf"),
        "chords":  ("organic",          "Organic/pad_rich.xpf"),
        "pad":     ("organic",          "Organic/pad_ethereal.xpf"),
        "melody":  ("tripleoscillator", "TripleOscillator/LSP-Kalimba.xpf"),
        "lead":    ("tripleoscillator", "TripleOscillator/LSP-SmokeSynth.xpf"),
        "counter": ("tripleoscillator", "TripleOscillator/LSP-SynthStrings.xpf"),
    },
    "jazz": {
        "bass":    ("lb302",            "LB302/Wavy-JazzBass.xpf"),
        "chords":  ("opulenz",          "OpulenZ/Combo_organ.xpf"),
        "pad":     ("opulenz",          "OpulenZ/Pad.xpf"),
        "melody":  ("opulenz",          "OpulenZ/Vibraphone.xpf"),
        "lead":    ("monstro",          "Monstro/LSP-EPiano.xpf"),
        "counter": ("tripleoscillator", "TripleOscillator/LSP-FunkBass4.xpf"),
    },
    "future_bass": {
        "bass":    ("lb302",            "LB302/GoodOldTimes.xpf"),
        "chords":  ("tripleoscillator", "TripleOscillator/FutureBass.xpf"),
        "pad":     ("tripleoscillator", "TripleOscillator/LSP-SynthwavePad.xpf"),
        "melody":  ("tripleoscillator", "TripleOscillator/LSP-CuteElectroLead.xpf"),
        "lead":    ("monstro",          "Monstro/Phat.xpf"),
        "counter": ("tripleoscillator", "TripleOscillator/LSP-SynthwaveSawArp.xpf"),
    },
    "default": {
        "bass":    ("lb302",            "LB302/AcidLead.xpf"),
        "chords":  ("tripleoscillator", "TripleOscillator/DetunedGhost.xpf"),
        "pad":     ("organic",          "Organic/pad_rich.xpf"),
        "melody":  ("bitinvader",       "BitInvader/toy_piano.xpf"),
        "lead":    ("bitinvader",       "BitInvader/pluck.xpf"),
        "counter": ("bitinvader",       "BitInvader/bell.xpf"),
    },
}

# User-selectable instrument choices per role — returned by get_instrument_choices RPC
_INSTRUMENT_CHOICES: dict[str, list[dict]] = {
    "bass": [
        {"label": "303 Acid",       "instrument": "lb302",            "preset": "LB302/AcidLead.xpf"},
        {"label": "303 Growl",      "instrument": "lb302",            "preset": "LB302/AngryLead.xpf"},
        {"label": "House Bass",     "instrument": "lb302",            "preset": "LB302/Wavy-HouseBass.xpf"},
        {"label": "Sub Bass",       "instrument": "lb302",            "preset": "LB302/Wavy-SubBass.xpf"},
        {"label": "Cyberpunk Bass", "instrument": "monstro",          "preset": "Monstro/LSP-CyberpunkBass.xpf"},
        {"label": "Reese Bass",     "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-ReeseBass.xpf"},
        {"label": "Funk Bass",      "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-FunkBass4.xpf"},
        {"label": "Ambient Bass",   "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-BassAmbient.xpf"},
    ],
    "chords": [
        {"label": "Detroit Chord",  "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-DetroitChord.xpf"},
        {"label": "House Piano",    "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-HousePiano.xpf"},
        {"label": "Trap Piano",     "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-TrapEPiano.xpf"},
        {"label": "E-Piano",        "instrument": "opulenz",          "preset": "OpulenZ/Epiano.xpf"},
        {"label": "Combo Organ",    "instrument": "opulenz",          "preset": "OpulenZ/Combo_organ.xpf"},
        {"label": "Detuned Synth",  "instrument": "tripleoscillator", "preset": "TripleOscillator/DetunedGhost.xpf"},
    ],
    "melody": [
        {"label": "Electro Lead",   "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-CuteElectroLead.xpf"},
        {"label": "Kalimba",        "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-Kalimba.xpf"},
        {"label": "Lofi Keyz",      "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-TanakaLofiKeyz.xpf"},
        {"label": "Dreamcore Keys", "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-DreamcorePiano.xpf"},
        {"label": "Vibraphone",     "instrument": "opulenz",          "preset": "OpulenZ/Vibraphone.xpf"},
        {"label": "Toy Piano",      "instrument": "bitinvader",       "preset": "BitInvader/toy_piano.xpf"},
    ],
    "lead": [
        {"label": "Cute Electro",   "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-CuteElectroLead.xpf"},
        {"label": "Smoke Synth",    "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-SmokeSynth.xpf"},
        {"label": "Monstro E Piano","instrument": "monstro",          "preset": "Monstro/LSP-EPiano.xpf"},
        {"label": "Phat Stab",      "instrument": "monstro",          "preset": "Monstro/Phat.xpf"},
        {"label": "Acid Lead",      "instrument": "lb302",            "preset": "LB302/AcidLead.xpf"},
        {"label": "Clarinet",       "instrument": "opulenz",          "preset": "OpulenZ/Clarinet.xpf"},
    ],
    "pad": [
        {"label": "Synthwave Pad",  "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-SynthwavePad.xpf"},
        {"label": "Synth Strings",  "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-SynthStrings.xpf"},
        {"label": "House Pad",      "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-PadHouse.xpf"},
        {"label": "Dream Pad",      "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-Traum.xpf"},
        {"label": "Ethereal Pad",   "instrument": "organic",          "preset": "Organic/pad_ethereal.xpf"},
        {"label": "Rich Pad",       "instrument": "organic",          "preset": "Organic/pad_rich.xpf"},
    ],
    "counter": [
        {"label": "Supersaw Arp",   "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-SynthwaveSawArp.xpf"},
        {"label": "Funk Bass",      "instrument": "tripleoscillator", "preset": "TripleOscillator/LSP-FunkBass4.xpf"},
        {"label": "Blues Organ",    "instrument": "organic",          "preset": "Organic/organ_blues.xpf"},
        {"label": "Drama",          "instrument": "bitinvader",       "preset": "BitInvader/drama.xpf"},
        {"label": "Space FX",       "instrument": "bitinvader",       "preset": "BitInvader/spacefx.xpf"},
    ],
}


# Drum voice splitting — maps GM pitch sets to Kicker presets
_DRUM_VOICES: dict[str, tuple[frozenset[int], str, str]] = {
    "Kick":     (frozenset({35, 36}),     "Kicker/TrapKick.xpf",    "#e74c3c"),
    "Snare":    (frozenset({38, 40}),     "Kicker/SnareLong.xpf",   "#e67e22"),
    "Clap":     (frozenset({39}),         "Kicker/Clap.xpf",        "#f1c40f"),
    "Hi-Hat":   (frozenset({42, 44}),     "Kicker/HihatClosed.xpf", "#3498db"),
    "Open Hat": (frozenset({46}),         "Kicker/HihatOpen.xpf",   "#2980b9"),
}

# Genre-specific drum preset overrides (only keys that differ from defaults above)
_DRUM_VOICES_GENRE: dict[str, dict[str, str]] = {
    "lofi":       {"Kick": "Kicker/KickPower.xpf",   "Snare": "Kicker/TR909-RimShot.xpf"},
    "jazz":       {"Kick": "Kicker/KickPower.xpf",   "Snare": "Kicker/SnareMarch.xpf"},
    "house":      {"Kick": "Kicker/KickPower.xpf",   "Snare": "Kicker/Clap.xpf"},
    "trap":       {"Snare": "Kicker/Clap.xpf"},
    "ambient":    {"Kick": "Kicker/KickPower.xpf",   "Snare": "Kicker/SnareMarch.xpf"},
    "future_bass":{"Kick": "Kicker/KickPower.xpf",   "Snare": "Kicker/Clap.xpf"},
}


# ── 808 Slide helper (Fix E) ───────────────────────────────────────────────────

def _build_808_note(pitch_midi: int, duration_beats: float,
                     env_length: float = 0.7, distortion: float = 0.0,
                     slide_ms: int = 0) -> dict:
    """Build a note dict for Kicker-based 808 with optional slide/distortion.

    Extra fields are hints for Kicker XML generation (not used by standard
    _write_midi but available for future preset-override integration).

    env_length:  0.0–1.0  — decay/sustain length for Kicker
    distortion:  0.0–1.0  — clip distortion level (0=clean 808, 1=rage-style)
    slide_ms:    int       — pitch slide duration in milliseconds (0=no slide)
    """
    return {
        "pitch":               pitch_midi,
        "beat":                0.0,   # caller must set the correct absolute beat
        "duration":            duration_beats,
        "velocity":            110,
        "_kicker_env_length":  env_length,
        "_kicker_distortion":  distortion,
        "_kicker_slide_ms":    slide_ms,
    }


# ── Sidechain velocity helper (Fix F) ─────────────────────────────────────────

def _apply_sidechain_velocities(notes: list[dict], kick_beats: list[float],
                                  duck_vel: int = 30, normal_vel: int = 100) -> list[dict]:
    """Simulate sidechain compression by ducking pad velocity on kick beats.

    Sets note velocity to duck_vel on kick beats, normal_vel otherwise.
    Uses ±0.15 beat tolerance for kick beat detection.
    """
    kick_set = [round(b, 3) for b in kick_beats]
    result = []
    for n in notes:
        beat = round(float(n.get("beat", 0.0)), 3)
        is_on_kick = any(abs(beat - kb) < 0.15 for kb in kick_set)
        vel = duck_vel if is_on_kick else normal_vel
        result.append({**n, "velocity": vel})
    return result

# ── System prompts ─────────────────────────────────────────────────────────────

_PLAN_SYSTEM = """\
You are Wavy — an expert music producer and theorist. Given a user prompt, output
ONLY valid JSON with exactly this structure:
{
  "bpm": <int 60-200>,
  "key": <string, e.g. "C", "F#", "Bb">,
  "scale": <"major" or "minor">,
  "bars": <int 2-32>,
  "parts": [
    {
      "name": <string, instrument name>,
      "role": <"drums"|"bass"|"chords"|"melody"|"counter"|"pad"|"lead">,
      "description": <string, what this part should sound like>,
      "color": <"#rrggbb">
    }
  ]
}

Genre guidance — detect from prompt and apply appropriate settings:
- default:     140 BPM, C major, Kicker channel rack (Kick/Clap/Hat/Snare)
- future_bass: 128 BPM, A minor, supersaw chords, sidechain pumping pads, electro lead
- house:       128 BPM, A minor, four-on-the-floor kick, detroit chords, house piano
- trap:        140 BPM, F minor, triplet hi-hats, 808 sub, cyberpunk bass, trap piano
- ambient:     70 BPM, C major, ethereal pads, synth strings, kalimba, smoke synth
- lofi:        85 BPM, F major, dreamcore keys, lofi keyz, warm bass, vinyl pad
- jazz:        100 BPM, D minor, jazz piano, vibraphone, e-piano, funk bass, combo organ
- 808:         140 BPM, C minor, AudioFileProcessor sample rack (808 kit)

No extra text, no markdown, no explanation — pure JSON only."""

_NOTES_SYSTEM = """\
You are a music theory expert generating a {role} part.
Key: {key} {scale} | Tempo: {bpm} BPM | Bars: {bars}
Description: {description}

Output ONLY valid JSON:
{{"notes": [{{"pitch": "<NoteOctave>", "beat": <float>, "duration": <float>, "velocity": <int>}}, ...]}}

CRITICAL PITCH RULES:
- pitch field MUST be a note name string like "E4", "F#3", "Bb5"
- Use ONLY notes from the {key} {scale} scale: {scale_note_names}
- Do NOT use any other notes — every pitch must be from that list
- beat: absolute position (0.0 = bar 1 beat 1, 4.0 = bar 2 beat 1)
- duration: in beats (0.25=16th, 0.5=8th, 1.0=quarter, 2.0=half, 4.0=whole)
- velocity: 1-127

Chord progression (land on chord root or chord tone on beat 1 of each bar):
{chord_progression}

Per-role rules:
- bass:    Use octave 1-2 (e.g. E1, A1, D2). Root note on beat 1 each bar.
           4-8 notes/bar. Passing tone one semitone below next chord root on beat 3.5.
- melody:  Use octave 4-5 (e.g. E4, F#5). 6-10 notes/bar with rests between phrases.
           Land on chord tone at bar start. End phrase on root or 5th. 2-bar motif + variation.
           Accent beat 1 (velocity 88-95), beats 2-4 lower (68-80).
- lead:    Octave 4-5. Single expressive lines, velocity 75-100. Leave space for breathing.
- counter: Octave 3-4. Complement melody in contrary motion. 65-80 velocity.
- pad:     Octave 3-4. Sustained chords 2.0-4.0 beats. Velocity 55-70.

No extra text — pure JSON only."""

_FILL_SYSTEM = """\
You are a music theory expert. Generate notes for the active piano roll clip.
Prompt: {prompt}
Key: {key} {scale} | Tempo: {bpm} BPM | Bars: {bars}

Output ONLY valid JSON:
{{"notes": [{{"pitch": "<NoteOctave>", "beat": <float>, "duration": <float>, "velocity": <int>}}]}}

CRITICAL RULES:
- pitch MUST be a note name string like "E5", "F#4", "Bb5"
- Use ONLY notes from {key} {scale}: {scale_note_names}
- beat: absolute (0.0 = beat 1 of bar 1, 4.0 = beat 1 of bar 2)
- duration in beats (0.5=8th, 1.0=quarter, 2.0=half)
- velocity 1-127
- Octave 4-5. Land on chord root on beat 1 each bar. 2-bar motif + variation.
- Accent beat 1 (velocity 90), beats 2-4 (velocity 70-80). Leave rests.

Chord progression (land chord root/3rd/5th on beat 1):
{chord_progression}

No extra text."""


# ── Helpers ───────────────────────────────────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_QUALITY_DISPLAY: dict[str, str] = {
    "maj7": "maj7", "min7": "min7", "dom7": "7", "add9": "add9",
    "min9": "m9",   "sus2": "sus2", "maj":  "",  "min":  "m",
    "dim":  "dim",
}


def _chord_context_str(cs: list[dict]) -> str:
    """Human-readable chord schedule to inject into LLM prompts."""
    lines = []
    for e in cs:
        root_name = _NOTE_NAMES[e["root"] % 12]
        suffix = _QUALITY_DISPLAY.get(e["quality"], e["quality"])
        tones_str = " ".join(
            f"{_NOTE_NAMES[p % 12]}{p // 12 - 1}" for p in e["pitches"]
        )
        lines.append(f"  Bar {e['bar']+1}: {root_name}{suffix}  [{tones_str}]")
    return "\n".join(lines)


def _note_name(midi: int) -> str:
    """Convert MIDI pitch number to human-readable note name (e.g. 60 → C4)."""
    if midi < 0 or midi > 127:
        return f"?{midi}"
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _notes_summary(notes: list[dict], role: str) -> str:
    """Return a compact diagnostic string for a list of note dicts."""
    if not notes:
        return "NO NOTES"
    pitches   = [int(n.get("pitch",    0))   for n in notes]
    beats     = [float(n.get("beat",   0.0)) for n in notes]
    durs      = [float(n.get("duration", 0.0)) for n in notes]
    vels      = [int(n.get("velocity", 0))   for n in notes]
    lo, hi    = min(pitches), max(pitches)
    beat0     = min(beats)
    beatN     = max(beats)
    avg_dur   = sum(durs) / len(durs) if durs else 0
    avg_vel   = sum(vels) / len(vels) if vels else 0
    # Check for suspicious patterns
    warnings: list[str] = []
    if lo == hi:
        warnings.append("ALL_SAME_PITCH")
    if lo < 21:
        warnings.append(f"VERY_LOW_PITCH({lo})")
    if hi > 108:
        warnings.append(f"VERY_HIGH_PITCH({hi})")
    if avg_vel < 20:
        warnings.append(f"LOW_VEL({avg_vel:.0f})")
    if role not in ("drums",) and avg_dur < 0.12:
        warnings.append(f"VERY_SHORT_DUR({avg_dur:.2f})")
    warn_str = "  *** " + " | ".join(warnings) if warnings else ""
    return (
        f"{len(notes)} notes  pitch {_note_name(lo)}-{_note_name(hi)}({lo}-{hi})"
        f"  vel {min(vels)}-{max(vels)} avg={avg_vel:.0f}"
        f"  dur avg={avg_dur:.2f}  beats {beat0:.1f}-{beatN:.1f}"
        + warn_str
    )


_NOTE_NAME_TO_MIDI: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

def _coerce_note_names(notes: list[dict]) -> list[dict]:
    """Convert any pitch fields that are note-name strings ('C4', 'F#3') to MIDI ints."""
    import re as _re
    result = []
    for n in notes:
        p = n.get("pitch", 60)
        if isinstance(p, str):
            m = _re.match(r"([A-G][#b]?)(-?\d+)", p.strip())
            if m:
                note, octave = m.group(1), int(m.group(2))
                midi = (octave + 1) * 12 + _NOTE_NAME_TO_MIDI.get(note, 0)
                n = {**n, "pitch": max(0, min(127, midi))}
            else:
                # Try parsing as plain int string
                try:
                    n = {**n, "pitch": int(p)}
                except ValueError:
                    pass
        result.append(n)
    return result


def _is_chord_track(notes: list[dict]) -> bool:
    """Return True if notes contain real chords (≥2 simultaneous pitches at same beat position)."""
    from collections import Counter
    # Round beat to nearest 1/8 beat to group simultaneous notes
    beats = Counter(round(float(n.get("beat", 0.0)) * 8) for n in notes)
    return max(beats.values(), default=0) >= 2


from utils.json_extract import extract_json as _extract_json



def _scale_note_names_for_prompt(key: str, scale: str,
                                  octaves: tuple[int, ...] = (1, 2, 3, 4, 5, 6)) -> str:
    """Return only note name strings across multiple octaves — e.g. 'E1 F#1 G#1 ...'.
    LLMs generate far more accurate pitches when given note names instead of MIDI numbers."""
    pitches: list[int] = []
    for oct in octaves:
        pitches.extend(scale_notes(key, scale, octave=oct))
    pitches = sorted(set(pitches))
    return " ".join(f"{_NOTE_NAMES[p % 12]}{p // 12 - 1}" for p in pitches)


def _call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    """Call the best available LLM with our system prompt directly (bypasses parse_command).
    Priority: Anthropic claude-opus-4-6 → Groq llama-3.3-70b → empty string."""
    # Try Anthropic claude-opus-4-6 first
    if config.ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except Exception as exc:
            logger.warning(f"compose_agent Anthropic call failed: {exc}")
    # Fall back to Groq llama-3.3-70b
    if config.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": user}],
                temperature=0.7,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            logger.warning(f"compose_agent Groq call failed: {exc}")
    return ""


def _write_midi(notes: list[dict], bpm: int, output_path: Path,
                is_drums: bool = False) -> tuple[int, dict]:
    """Write a list of note dicts to a MIDI file.
    Returns (note_count, note_summary) where note_summary groups notes by bar index."""
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Set tempo
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # On drums channel, set channel to 9
    channel = 9 if is_drums else 0

    # Build event list + note_summary
    events: list[tuple[int, str, int, int]] = []
    note_summary: dict[int, list[dict]] = {}

    for n in notes:
        pitch    = max(0, min(127, int(n.get("pitch", 60))))
        beat     = float(n.get("beat", 0.0))
        dur      = float(n.get("duration", 0.5))
        velocity = max(1, min(127, int(n.get("velocity", 80))))

        start_tick = int(beat * 480)
        end_tick   = int((beat + dur) * 480)
        events.append((start_tick, "note_on",  pitch, velocity))
        events.append((end_tick,   "note_off", pitch, 0))

        bar = int(beat // 4)
        if bar not in note_summary:
            note_summary[bar] = []
        note_summary[bar].append({
            "pitch":    pitch,
            "beat":     round(beat % 4, 4),  # beat within bar
            "duration": dur,
            "velocity": velocity,
        })

    events.sort(key=lambda x: x[0])

    # ── Humanization ──────────────────────────────────────────────────────────
    rng = _rand.Random(abs(hash(str(output_path))))
    if is_drums:
        # Drums: velocity variation only — timing jitter ruins the pocket
        humanized: list[tuple[int, str, int, int]] = []
        for tick, mtype, pitch, vel in events:
            if mtype == "note_on":
                humanized.append((tick, mtype, pitch,
                                   max(1, min(127, vel + rng.randint(-5, 5)))))
            else:
                humanized.append((tick, mtype, pitch, vel))
        events = humanized
    else:
        # Pitched instruments: timing jitter (±8 ticks ≈ 10ms at 480PPQ) + velocity
        humanized = []
        for tick, mtype, pitch, vel in events:
            jitter = rng.randint(-8, 8)
            if mtype == "note_on":
                humanized.append((max(0, tick + jitter), mtype, pitch,
                                   max(1, min(127, vel + rng.randint(-8, 8)))))
            else:
                humanized.append((max(0, tick + jitter), mtype, pitch, vel))
        events = sorted(humanized, key=lambda x: x[0])

    prev_tick = 0
    for tick, msg_type, pitch, vel in events:
        delta = max(0, tick - prev_tick)
        track.append(mido.Message(msg_type, note=pitch, velocity=vel,
                                  channel=channel, time=delta))
        prev_tick = tick

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(output_path))
    note_count = len([e for e in events if e[1] == "note_on"])
    return note_count, note_summary


def _fallback_notes(role: str, key: str, scale: str, bars: int,
                    description: str) -> list[dict]:
    """Generate deterministic notes when LLM fails."""
    role = role.lower()
    desc_lower = description.lower()

    # Infer genre from description
    genre = "generic"
    for g in ("trap", "lo-fi", "lofi", "house", "dnb", "drum and bass"):
        if g in desc_lower:
            genre = g
            break

    style = "simple"
    if "walk" in desc_lower:
        style = "walking"
    elif "trap" in desc_lower:
        style = "trap"

    if role == "drums":
        return drum_pattern(genre, bars)
    elif role == "bass":
        cs_local = chord_schedule(key, scale, "default", bars)
        return bass_line_harmonic(cs_local, "default", bars)
    elif role == "chords":
        cs_local = chord_schedule(key, scale, "default", bars)
        return chord_progression_from_schedule(cs_local, "default")
    elif role in ("melody", "lead", "counter"):
        cs_local = chord_schedule(key, scale, "default", bars)
        return melody_line_harmonic(cs_local, key, scale, "default", bars)
    else:
        # Generic: arpeggiate scale
        notes_pitches = scale_notes(key, scale, octave=4)
        notes = []
        for bar in range(bars):
            for i, p in enumerate(notes_pitches[:4]):
                notes.append({"pitch": p, "beat": bar * 4.0 + i, "duration": 0.5, "velocity": 75})
        return notes


def _split_drum_voices(notes: list[dict], bpm: int, genre: str = "default") -> list[dict]:
    """Split a combined drum note list into per-voice parts, each using Kicker."""
    genre_presets = _DRUM_VOICES_GENRE.get(genre, {})
    result: list[dict] = []
    for voice_name, (pitches_set, default_preset, color) in _DRUM_VOICES.items():
        preset = genre_presets.get(voice_name, default_preset)
        voice_notes = [
            {**n, "pitch": 60}  # Normalize pitch to 60; Kicker triggers at any pitch
            for n in notes
            if int(n.get("pitch", 0)) in pitches_set
        ]
        if not voice_notes:
            continue
        path = config.GENERATION_DIR / (
            f"drum_{voice_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.mid"
        )
        count, note_summary = _write_midi(voice_notes, bpm, path, is_drums=False)
        if count > 0:
            result.append({
                "name":         voice_name,
                "role":         "drums",
                "midi_path":    str(path),
                "color":        color,
                "note_count":   count,
                "note_summary": note_summary,
                "instrument":   "kicker",
                "preset_name":  preset,
            })
    return result


def _session_context(session_id: str) -> str:
    """Build a text summary of an existing session for follow-up prompts."""
    s = _sessions.get(session_id, {})
    if not s:
        return ""
    parts_summary = ", ".join(p["name"] for p in s.get("parts", []))
    return (
        f"Previous composition: {s.get('bpm')} BPM, {s.get('key')} "
        f"{s.get('scale')}, {s.get('bars')} bars. "
        f"Tracks created: {parts_summary}."
    )


def _get_role_midi(
    genre: str, role: str, bars: int, bpm: int, session_id: str,
    prompt: str = "", target_key: str = "", target_scale: str = "",
    full_mix: bool = False,
) -> dict | None:
    """
    Return a processed BitMidi file for the requested role.

    If the session already has a downloaded source MIDI, re-extract the
    new role from the same file (ensures all tracks share harmonic context).
    Otherwise search/download a fresh file and store it in the session.

    Returns a dict with midi_path, note_count, key, scale, bpm, title — or None.
    """
    session    = _sessions.get(session_id, {})
    seed_info  = session.get("seed_info") or {}
    source_midi = seed_info.get("source_midi", "")
    source_key  = seed_info.get("source_key",  "")

    from pathlib import Path as _Path
    src_path = _Path(source_midi) if source_midi else None

    logger.info(
        f"  BitMidi: _get_role_midi called — genre={genre} role={role} "
        f"bars={bars} bpm={bpm} prompt={prompt[:60]!r} "
        f"target_key={target_key} source_midi={'(reuse) ' + str(src_path) if src_path else '(new search)'}"
    )

    try:
        result = _midi_find_role(
            genre, role, bars, bpm,
            prompt      = prompt,
            target_key  = target_key,
            target_scale= target_scale,
            source_midi = src_path,
            source_key  = source_key,
            full_mix    = full_mix,
        )
        if result:
            logger.info(
                f"  BitMidi: SUCCESS — '{result.get('title', '?')}' "
                f"{result.get('note_count', 0)} notes → {Path(result['midi_path']).name}"
            )
            # Persist new source so subsequent role calls re-extract from the same
            # MIDI file — ensures harmonic coherence across all tracks in a session.
            if result.get("source_midi") and not source_midi:
                new_seed = dict(seed_info)
                new_seed["source_midi"] = result["source_midi"]
                new_seed["source_key"]  = result.get("key", "")
                existing = _sessions.get(session_id, {})
                _sessions[session_id] = {**existing, "seed_info": new_seed}
        else:
            logger.warning(
                f"  BitMidi: returned None — genre={genre} role={role} "
                f"prompt={prompt[:60]!r} (will fall back to harmonic engine)"
            )
        return result
    except Exception as exc:
        logger.warning(f"  BitMidi: _get_role_midi EXCEPTION: {type(exc).__name__}: {exc}")
        import traceback
        logger.debug(f"  BitMidi traceback:\n{traceback.format_exc()}")
        return None


def _evict_old_sessions() -> None:
    if len(_sessions) >= _MAX_SESSIONS:
        # Remove the oldest entry
        oldest = next(iter(_sessions))
        del _sessions[oldest]


def _parse_key_from_prompt(prompt: str) -> str | None:
    """Extract key note name from text like 'C minor', 'F# major', 'Bb minor'."""
    m = re.search(r"\b([A-G][#b]?)\s+(?:major|minor)\b", prompt, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _parse_scale_from_prompt(prompt: str) -> str | None:
    """Extract scale type ('major' or 'minor') from prompt text."""
    m = re.search(r"\b([A-G][#b]?)\s+(major|minor)\b", prompt, re.IGNORECASE)
    if m:
        return m.group(2).lower()
    m = re.search(r"\b(major|minor)\b", prompt, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def _parse_bpm_from_prompt(prompt: str) -> int | None:
    """Extract BPM value from text like '140 BPM' or 'at 85bpm'."""
    m = re.search(r"\b(\d{2,3})\s*bpm\b", prompt, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 40 <= val <= 240:
            return val
    return None


def _parse_bars_from_prompt(prompt: str) -> int | None:
    """Extract bar count from text like '4 bars' or '8 bar'."""
    m = re.search(r"\b(\d+)\s*bars?\b", prompt, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 64:
            return val
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

class ComposeAgent:
    """
    Stateless callable — all state is in the module-level _sessions dict.
    """

    def compose(self, params: dict, registry: Any = None) -> dict:
        """
        params:
          prompt              str
          mode                "arrange" | "fill" | "single"
          session_id          str (UUID; empty = new session)
          role                str — for mode=="single" (melody/bass/chords/lead/pad/drums)
          instrument_override dict — {instrument, preset} — for mode=="single"
          daw_context         dict (optional engine context)
          bpm                 int (optional override)
          bars                int (optional override)

        Returns:
          mode=="arrange": {mode, parts:[{name,midi_path,color,note_count}],
                            explanation, session_id, bpm, key, bars}
          mode=="fill":    {mode, midi_path, note_count, explanation, session_id}
          mode=="single":  {mode, parts:[{name,midi_path,...}], explanation, session_id}
        """
        prompt              = str(params.get("prompt", "")).strip()
        mode                = str(params.get("mode", "arrange")).lower()
        session_id          = str(params.get("session_id", "")).strip() or str(uuid.uuid4())
        bpm_hint            = params.get("bpm")
        bars_hint           = params.get("bars")
        instrument_overrides = params.get("instrument_overrides", {})

        if not prompt:
            return {"error": "prompt is required"}

        ctx_text = _session_context(session_id)
        user_msg = (ctx_text + "\n\n" + prompt).strip() if ctx_text else prompt

        # ── Detect key from existing session MIDI notes ───────────────────────
        # C++ sends existing InstrumentTrack note pitches via daw_context so new
        # tracks are harmonically anchored to whatever is already in the project.
        daw_context = params.get("daw_context", {})
        _existing_pitches = [int(p) for p in daw_context.get("existing_notes", [])]
        _detected_key: str | None = None
        _detected_scale: str | None = None
        if len(_existing_pitches) >= 8:
            _detected_key, _detected_scale = detect_key_from_notes(_existing_pitches)
            logger.info(
                f"  ║  session scan: detected key={_detected_key} {_detected_scale}"
                f" from {len(_existing_pitches)} existing notes"
            )

        # ── Mode: fill (single-part, active piano roll) ───────────────────────
        if mode == "fill":
            bpm   = int(bpm_hint or 120)
            bars  = int(bars_hint or 4)
            # Use session-detected key as fallback when prompt doesn't specify
            _prompt_key = _parse_key_from_prompt(prompt)
            key   = str(params.get("key") or _prompt_key or _detected_key or "C")
            scale = str(params.get("scale") or _parse_scale_from_prompt(prompt) or _detected_scale or "major")
            genre = _detect_genre(prompt, bpm)
            scale_note_names = _scale_note_names_for_prompt(key, scale)
            cs    = chord_schedule(key, scale, genre, bars)
            chord_ctx = _chord_context_str(cs)
            raw  = _call_llm(
                _FILL_SYSTEM.format(prompt=prompt, key=key, scale=scale,
                                    bpm=bpm, bars=bars,
                                    scale_note_names=scale_note_names,
                                    chord_progression=chord_ctx),
                user_msg, max_tokens=2048)
            notes: list[dict] = []
            parsed = _extract_json(raw)
            if parsed and "notes" in parsed:
                notes = _coerce_note_names(parsed["notes"])
            if not notes:
                logger.warning("compose fill: LLM returned no notes, using harmonic fallback")
                cs_fill = chord_schedule(key, scale, genre, bars)
                notes = melody_line_harmonic(cs_fill, key, scale, genre, bars)
            else:
                notes = snap_notes_to_scale(notes, key, scale, role="melody")

            path = config.GENERATION_DIR / f"compose_fill_{uuid.uuid4().hex[:8]}.mid"
            count, note_summary = _write_midi(notes, bpm, path)
            return {
                "mode":         "fill",
                "midi_path":    str(path),
                "note_count":   count,
                "note_summary": note_summary,
                "explanation":  f"Generated {count} notes at {bpm} BPM.",
                "session_id":   session_id,
            }

        # ── Mode: single (one track) ─────────────────────────────────────────
        if mode == "single":
            role_raw = str(params.get("role", "melody")).lower().strip()
            role     = _ROLE_NORMALIZE.get(role_raw, role_raw)
            is_drums = role == "drums"

            # Inherit key/scale/bpm/genre from existing session for harmonic unity
            session = _sessions.get(session_id, {})
            key   = str(params.get("key",   "") or _parse_key_from_prompt(prompt)   or session.get("key")   or _detected_key   or "C")
            scale = str(params.get("scale", "") or _parse_scale_from_prompt(prompt) or session.get("scale") or _detected_scale or "minor")
            bpm   = int(params.get("bpm",   0)  or _parse_bpm_from_prompt(prompt)   or session.get("bpm")   or 120)
            bars  = int(params.get("bars",  0)  or _parse_bars_from_prompt(prompt)  or 4)

            # Section-based positioning: override bars and set start_bar
            section   = params.get("section", {})
            if section and section.get("bars"):
                bars = int(section["bars"])
            start_bar = int(section.get("start_bar", 0)) if section else 0

            genre = _detect_genre(prompt, bpm)

            # Instrument: override or genre preset
            override = params.get("instrument_override", {})
            if override and override.get("instrument"):
                plugin      = str(override.get("instrument", "tripleoscillator"))
                preset_name = str(override.get("preset", ""))
            else:
                genre_presets = _PRESET_FOR_GENRE_ROLE.get(genre, _PRESET_FOR_GENRE_ROLE["default"])
                plugin, preset_name = genre_presets.get(
                    role, (_INSTRUMENT_FOR_ROLE.get(role, "tripleoscillator"), "")
                )

            logger.info(
                f"╔═ COMPOSE SINGLE ══════════════════════════════════════\n"
                f"║  role={role}  genre={genre}  bpm={bpm}  key={key} {scale}  bars={bars}\n"
                f"║  instrument={plugin}/{preset_name or 'default'}\n"
                f"╚══════════════════════════════════════════════════════"
            )

            # ── Note generation ───────────────────────────────────────────────
            # Drums: always deterministic — split into voice tracks
            if is_drums:
                notes = drum_pattern(genre, bars)
                logger.info(f"  ┌─ {role}  {_notes_summary(notes, role)}")
                split = _split_drum_voices(notes, bpm, genre)
                if split:
                    for sv in split:
                        sv["start_bar"] = start_bar
                        sv["bars"]      = bars
                    _evict_old_sessions()
                    existing = _sessions.get(session_id, {})
                    _sessions[session_id] = {
                        **existing,
                        "bpm": bpm, "key": key, "scale": scale, "genre": genre, "bars": bars,
                        "parts": existing.get("parts", []) + split,
                    }
                    return {
                        "mode":        "single",
                        "parts":       split,
                        "explanation": f"Generated {len(split)} drum tracks — {genre} pattern, {bpm} BPM, {bars} bars.",
                        "session_id":  session_id,
                        "start_bar":   start_bar,
                        "key": key, "scale": scale, "bpm": bpm, "genre": genre,
                    }
                logger.warning("compose single: drum split produced 0 tracks, writing combined")
                out_path = config.GENERATION_DIR / f"compose_{role}_{uuid.uuid4().hex[:8]}.mid"
                note_count, note_summary = _write_midi(notes, bpm, out_path, is_drums=True)
            else:
                # Pitched role: raw BitMidi → ImportFilter (one track per MIDI channel,
                # SF2Player + GeneralUser GS — sounds like manual File → Import MIDI).
                seed_slug = params.get("seed_midi_slug", "").strip()
                if seed_slug:
                    from utils.midi_library import download_midi as _download_midi
                    raw_path = _download_midi(seed_slug, prompt)
                    logger.info(f"  ┌─ {role}  exact slug '{seed_slug}' → {raw_path}")
                else:
                    raw_path = _midi_find_raw(genre, prompt=prompt)
                if raw_path:
                    logger.info(
                        f"  ┌─ {role}  import_midi_file → {raw_path.name}"
                    )
                    part = {
                        "name":        role.capitalize(),
                        "role":        role,
                        "action_type": "import_midi_file",
                        "midi_path":   str(raw_path),
                        "color":       _ROLE_COLORS.get(role, "#9b59b6"),
                        "bars":        bars,
                        "start_bar":   start_bar,
                        "note_count":  0,
                    }
                    _evict_old_sessions()
                    existing = _sessions.get(session_id, {})
                    _sessions[session_id] = {
                        **existing,
                        "bpm":   bpm, "key": key, "scale": scale, "genre": genre, "bars": bars,
                        "parts": existing.get("parts", []) + [part],
                    }
                    explanation = f"Importing {role} from MIDI — {key} {scale}, {bpm} BPM, {bars} bars."
                    return {
                        "mode":        "single",
                        "parts":       [part],
                        "explanation": explanation,
                        "session_id":  session_id,
                        "start_bar":   start_bar,
                        "key":         key,
                        "scale":       scale,
                        "bpm":         bpm,
                        "genre":       genre,
                    }
                # Harmonic engine fallback (BitMidi unavailable)
                cs_single = chord_schedule(key, scale, genre, bars)
                if role == "chords":
                    notes = chord_progression_from_schedule(cs_single, genre)
                elif role == "pad":
                    notes = chord_progression_from_schedule(cs_single, "ambient")
                elif role == "bass":
                    notes = bass_line_harmonic(cs_single, genre, bars)
                else:
                    notes = melody_line_harmonic(cs_single, key, scale, genre, bars)
                logger.info(f"  ┌─ {role}  HARMONIC FALLBACK  {_notes_summary(notes, role)}")
                out_path = config.GENERATION_DIR / f"compose_{role}_{uuid.uuid4().hex[:8]}.mid"
                note_count, note_summary = _write_midi(notes, bpm, out_path, is_drums=False)

            logger.info(f"  └─ {note_count} notes → {out_path.name}")

            part = {
                "name":         role.capitalize(),
                "role":         role,
                "midi_path":    str(out_path),
                "color":        _ROLE_COLORS.get(role, "#9b59b6"),
                "note_count":   note_count,
                "note_summary": note_summary,
                "instrument":   plugin,
                "preset_name":  preset_name,
                "start_bar":    start_bar,
                "bars":         bars,
            }
            _evict_old_sessions()
            existing = _sessions.get(session_id, {})
            _sessions[session_id] = {
                **existing,
                "bpm":   bpm, "key": key, "scale": scale, "genre": genre, "bars": bars,
                "parts": existing.get("parts", []) + [part],
            }
            explanation = f"Generated {role} — {note_count} notes, {key} {scale}, {bpm} BPM, {bars} bars."
            return {
                "mode":        "single",
                "parts":       [part],
                "explanation": explanation,
                "session_id":  session_id,
                "start_bar":   start_bar,
                "key":         key,
                "scale":       scale,
                "bpm":         bpm,
                "genre":       genre,
            }

        # ── Mode: arrange (multi-part) ────────────────────────────────────────

        # Stage 1: LLM planning
        plan: dict = {}
        raw_plan = _call_llm(_PLAN_SYSTEM, user_msg, max_tokens=2048)
        if raw_plan:
            plan = _extract_json(raw_plan) or {}

        # Validate / fill defaults
        bpm   = int(bpm_hint or plan.get("bpm", 120))
        key   = str(plan.get("key", "C"))
        scale = str(plan.get("scale", "minor"))
        bars  = int(bars_hint or plan.get("bars", 4))
        parts_plan: list[dict] = plan.get("parts", [])

        # Section-based positioning
        section   = params.get("section", {})
        if section and section.get("bars"):
            bars = int(section["bars"])
        start_bar = int(section.get("start_bar", 0)) if section else 0

        # If existing session tracks were scanned, anchor key/scale to them so
        # new parts are harmonically coherent with what's already in the project.
        if _detected_key:
            key   = _detected_key
            scale = _detected_scale or scale
            logger.info(f"  ║  key anchored to session: {key} {scale}")

        if not parts_plan:
            logger.warning("compose arrange: no parts from LLM, using default 4-part layout")
            parts_plan = [
                {"name": "Drums",  "role": "drums",  "description": prompt, "color": "#e74c3c"},
                {"name": "Bass",   "role": "bass",   "description": prompt, "color": "#2ecc71"},
                {"name": "Chords", "role": "chords", "description": prompt, "color": "#3498db"},
                {"name": "Melody", "role": "melody", "description": prompt, "color": "#9b59b6"},
            ]

        # Stage 2: Generate notes per part
        output_parts: list[dict] = []
        genre = _detect_genre(prompt, bpm)

        genre_presets = _PRESET_FOR_GENRE_ROLE.get(genre, _PRESET_FOR_GENRE_ROLE["default"])

        # ── Shared chord schedule for chords/pad tracks ───────────────────────
        cs = chord_schedule(key, scale, genre, bars)

        logger.info(
            f"╔═ COMPOSE ════════════════════════════════════════════\n"
            f"║  genre={genre}  bpm={bpm}  key={key} {scale}  bars={bars}\n"
            f"║  parts: {[p.get('name','?') + '(' + p.get('role','?') + ')' for p in parts_plan]}\n"
            f"╚══════════════════════════════════════════════════════"
        )

        for part in parts_plan:
            role_raw    = str(part.get("role", "melody")).lower().strip()
            role        = _ROLE_NORMALIZE.get(role_raw, role_raw)
            name        = str(part.get("name", role.capitalize()))
            description = str(part.get("description", prompt))
            color       = str(part.get("color", _ROLE_COLORS.get(role, "#9b59b6")))
            is_drums    = role == "drums"
            if role in instrument_overrides:
                ov = instrument_overrides[role]
                instrument   = str(ov.get("instrument", "tripleoscillator"))
                preset_name  = str(ov.get("preset", ""))
                src = "OVERRIDE"
            else:
                instrument, preset_name = genre_presets.get(
                    role, (_INSTRUMENT_FOR_ROLE.get(role, "tripleoscillator"), "")
                )
                src = "genre"

            # ── Drums: deterministic, split into voice tracks ─────────────────
            if is_drums:
                notes = drum_pattern(genre, bars)
                drum_pitches_found = sorted(set(int(n.get("pitch", 0)) for n in notes))
                logger.info(
                    f"  ┌─ {name} ({role}) [DETERMINISTIC] instrument={instrument}/{preset_name or 'default'} [{src}]\n"
                    f"  │  raw drum pitches: {drum_pitches_found}\n"
                    f"  │  {_notes_summary(notes, role)}"
                )
                split = _split_drum_voices(notes, bpm, genre)
                if split:
                    for sv in split:
                        sv["start_bar"] = start_bar
                        sv["bars"]      = bars
                        logger.info(f"  │    drum split → {sv['name']}: {sv['note_count']} notes  preset={sv['preset_name']}")
                    output_parts.extend(split)
                    logger.info(f"  └─ drums split into {len(split)} voice tracks")
                    continue
                else:
                    logger.warning(f"  └─ drum split produced 0 tracks! pitches didn't match any voice set")
                path = config.GENERATION_DIR / f"compose_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.mid"
                count, note_summary = _write_midi(notes, bpm, path, is_drums=True)
                logger.info(f"  └─ wrote {count} notes → {path.name}")
                output_parts.append({
                    "name": name, "role": role, "midi_path": str(path), "color": color,
                    "note_count": count, "note_summary": note_summary,
                    "instrument": instrument, "preset_name": preset_name,
                    "start_bar": start_bar, "bars": bars,
                })
                continue

            # ── Chords/Pad: deterministic ─────────────────────────────────────
            if role in ("chords", "pad"):
                notes    = chord_progression_from_schedule(cs, genre if role == "chords" else "ambient")
                midi_src = "DETERMINISTIC"
                logger.info(
                    f"  ┌─ {name} ({role}) [{midi_src}] instrument={instrument}/{preset_name or 'default'} [{src}]\n"
                    f"  │  {_notes_summary(notes, role)}"
                )
                path = config.GENERATION_DIR / f"compose_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.mid"
                count, note_summary = _write_midi(notes, bpm, path)
                logger.info(f"  └─ wrote {count} notes → {path.name}")
                output_parts.append({
                    "name": name, "role": role, "midi_path": str(path), "color": color,
                    "note_count": count, "note_summary": note_summary,
                    "instrument": instrument, "preset_name": preset_name,
                    "start_bar": start_bar, "bars": bars,
                })
                continue

            # ── Bass / Melody / Lead / Counter: harmonic or BitMidi ──────────
            bitmidi_result = None
            bitmidi_result = _get_role_midi(
                    genre, role, bars, bpm, session_id,
                    prompt=description, target_key=key, target_scale=scale,
                )
            if bitmidi_result:
                path         = Path(bitmidi_result["midi_path"])
                count        = bitmidi_result["note_count"]
                note_summary = {}
                midi_src     = "BITMIDI"
                logger.info(
                    f"  ┌─ {name} ({role}) [{midi_src}] instrument={instrument}/{preset_name or 'default'} [{src}]\n"
                    f"  │  BitMidi: '{bitmidi_result['title']}'  {count} notes → {path.name}"
                )
            else:
                if role == "bass":
                    notes = bass_line_harmonic(cs, genre, bars)
                else:
                    notes = melody_line_harmonic(cs, key, scale, genre, bars)
                if not notes:
                    notes = _fallback_notes(role, key, scale, bars, description)
                midi_src = "FALLBACK"
                logger.info(
                    f"  ┌─ {name} ({role}) [{midi_src}] instrument={instrument}/{preset_name or 'default'} [{src}]\n"
                    f"  │  {_notes_summary(notes, role)}"
                )
                path = config.GENERATION_DIR / f"compose_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.mid"
                count, note_summary = _write_midi(notes, bpm, path)
            logger.info(f"  └─ {count} notes → {path.name}")
            output_parts.append({
                "name": name, "role": role, "midi_path": str(path), "color": color,
                "note_count": count, "note_summary": note_summary,
                "instrument": instrument, "preset_name": preset_name,
                "start_bar": start_bar, "bars": bars,
            })

        # Save / update session (preserve seed_info stored by _get_role_midi)
        _evict_old_sessions()
        existing = _sessions.get(session_id, {})
        _sessions[session_id] = {
            "bpm":       bpm,
            "key":       key,
            "scale":     scale,
            "bars":      bars,
            "genre":     genre,
            "parts":     output_parts,
            "seed_info": existing.get("seed_info"),
        }

        explanation = (
            f"Created {len(output_parts)} tracks: "
            + ", ".join(p["name"] for p in output_parts)
            + f" — {bpm} BPM, {key} {scale}, {bars} bars."
        )

        return {
            "mode":        "arrange",
            "parts":       output_parts,
            "explanation": explanation,
            "session_id":  session_id,
            "start_bar":   start_bar,
            "bpm":         bpm,
            "key":         key,
            "scale":       scale,
            "genre":       genre,
            "bars":        bars,
        }

    def regenerate_bar(self, params: dict, registry: Any = None) -> dict:
        """
        Regenerate notes for a single bar of one part.
        params:
          session_id  str   — existing session UUID
          part_name   str   — track name to update
          bar_index   int   — 0-based bar to replace
          role        str   — drums/bass/chords/melody (optional, inferred from session)
          key         str   — optional override (from session if not provided)
          scale       str   — optional override
          bpm         int   — optional override
        Returns:
          {midi_path, notes, note_summary, bar_index}
        """
        session_id = str(params.get("session_id", "")).strip()
        part_name  = str(params.get("part_name", "")).strip()
        bar_index  = int(params.get("bar_index", 0))

        session = _sessions.get(session_id, {})
        bpm   = int(params.get("bpm") or session.get("bpm", 120))
        key   = str(params.get("key") or session.get("key", "C"))
        scale = str(params.get("scale") or session.get("scale", "minor"))

        # Find role from session parts
        role = str(params.get("role", "melody")).lower()
        for p in session.get("parts", []):
            if p.get("name", "").lower() == part_name.lower():
                role = p.get("role", role)
                break

        description = f"Bar {bar_index + 1} of {part_name}"
        scale_note_names = _scale_note_names_for_prompt(key, scale)
        cs_regen = chord_schedule(key, scale, "default", 1)
        chord_ctx_regen = _chord_context_str(cs_regen)
        notes_sys = _NOTES_SYSTEM.format(
            role=role, key=key, scale=scale, bpm=bpm,
            bars=1, description=description,
            scale_note_names=scale_note_names,
            chord_progression=chord_ctx_regen,
        )
        raw_notes = _call_llm(notes_sys,
            f"Generate 1 bar of notes for: {part_name} (bar {bar_index + 1})")
        notes_parsed = _extract_json(raw_notes)
        notes: list[dict] = []
        if notes_parsed and "notes" in notes_parsed:
            notes = snap_notes_to_scale(
                _coerce_note_names(notes_parsed["notes"]), key, scale, role
            )
        if not notes:
            notes = _fallback_notes(role, key, scale, 1, description)

        # Offset notes to the target bar
        for n in notes:
            n["beat"] = float(n.get("beat", 0.0)) % 4.0  # clamp to 1 bar

        path = config.GENERATION_DIR / f"regen_bar_{bar_index}_{uuid.uuid4().hex[:8]}.mid"
        count, note_summary = _write_midi(notes, bpm, path, is_drums=(role == "drums"))

        return {
            "midi_path":    str(path),
            "note_count":   count,
            "notes":        notes,
            "note_summary": note_summary,
            "bar_index":    bar_index,
            "part_name":    part_name,
        }
