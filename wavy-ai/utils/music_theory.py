"""
music_theory.py — Deterministic music theory helpers used as LLM fallbacks
and as reference context embedded in prompts.
"""

from __future__ import annotations

# ── Scale definitions ──────────────────────────────────────────────────────────

_SEMITONE_MAP = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

_SCALE_INTERVALS = {
    "major":         [0, 2, 4, 5, 7, 9, 11],
    "minor":         [0, 2, 3, 5, 7, 8, 10],
    "dorian":        [0, 2, 3, 5, 7, 9, 10],
    "phrygian":      [0, 1, 3, 5, 7, 8, 10],
    "mixolydian":    [0, 2, 4, 5, 7, 9, 10],
    "pentatonic":    [0, 2, 4, 7, 9],
    "minor_pent":    [0, 3, 5, 7, 10],
    "blues":         [0, 3, 5, 6, 7, 10],
    "harmonic_minor":[0, 2, 3, 5, 7, 8, 11],
}


def _root_midi(root: str, octave: int = 4) -> int:
    semitone = _SEMITONE_MAP.get(root, 0)
    return (octave + 1) * 12 + semitone


def scale_notes(root: str, scale_type: str, octave: int = 4) -> list[int]:
    """Return MIDI pitch list for one octave of the given scale."""
    base = _root_midi(root, octave)
    intervals = _SCALE_INTERVALS.get(scale_type.lower().replace(" ", "_"), _SCALE_INTERVALS["major"])
    return [base + i for i in intervals]


# ── Scale enforcement helpers ──────────────────────────────────────────────────

# Per-role MIDI pitch ranges: (lo_inclusive, hi_inclusive)
_ROLE_RANGES: dict[str, tuple[int, int]] = {
    "bass":    (28, 52),   # MIDI octave 1-3
    "chords":  (48, 72),   # MIDI octave 3-5
    "pad":     (48, 72),
    "melody":  (60, 84),   # MIDI octave 4-6
    "lead":    (60, 84),
    "counter": (55, 79),
    "drums":   (35, 81),   # GM drum notes (don't touch)
}


def snap_to_scale(pitch: int, key: str, scale_type: str) -> int:
    """Snap a MIDI pitch to the nearest note in the given scale.
    Preserves octave as much as possible (only adjusts pitch class)."""
    intervals = _SCALE_INTERVALS.get(
        scale_type.lower().replace(" ", "_"), _SCALE_INTERVALS["major"]
    )
    root_pc = _SEMITONE_MAP.get(key, 0)
    # Build set of valid pitch classes
    valid_pcs = {(root_pc + iv) % 12 for iv in intervals}
    if pitch % 12 in valid_pcs:
        return pitch
    # Try ±1, ±2 semitones (closest wins)
    for delta in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6):
        candidate = pitch + delta
        if candidate % 12 in valid_pcs:
            return max(0, min(127, candidate))
    return pitch  # Shouldn't happen


def snap_notes_to_scale(notes: list[dict], key: str, scale_type: str,
                        role: str = "") -> list[dict]:
    """
    Post-process a list of note dicts to ensure all pitches are in the given scale.
    Also enforces per-role MIDI pitch range.
    Drums are left unchanged.
    """
    if role == "drums":
        return notes

    lo, hi = _ROLE_RANGES.get(role, (0, 127))
    result = []
    for n in notes:
        pitch = int(n.get("pitch", 60))
        # Snap to scale
        pitch = snap_to_scale(pitch, key, scale_type)
        # Enforce octave range
        while pitch < lo:
            pitch += 12
        while pitch > hi:
            pitch -= 12
        result.append({**n, "pitch": pitch})
    return result


def chord_voicing(root: str, quality: str, octave: int = 4) -> list[dict]:
    """
    Return a list of note dicts for a block chord.
    quality: "major" | "minor" | "dom7" | "maj7" | "min7" | "add9" | "min9"
    Notes start at beat 0, last 4 beats. Velocity gradient: bass→mid→top.
    """
    _CHORD_INTERVALS: dict[str, list[int]] = {
        "major": [0, 4, 7],
        "minor": [0, 3, 7],
        "dom7":  [0, 4, 7, 10],
        "maj7":  [0, 4, 7, 11],
        "min7":  [0, 3, 7, 10],
        "sus2":  [0, 2, 7],
        "sus4":  [0, 5, 7],
        "add9":  [0, 4, 7, 14],    # contemporary pop/lo-fi
        "min9":  [0, 3, 7, 10, 14],  # R&B/jazz
    }
    _VELOCITIES = [80, 70, 78, 68]   # bass → mid → top → extension
    base = _root_midi(root, octave)
    intervals = _CHORD_INTERVALS.get(quality.lower(), _CHORD_INTERVALS["major"])
    return [
        {"pitch": base + i, "beat": 0.0, "duration": 4.0,
         "velocity": _VELOCITIES[idx % len(_VELOCITIES)]}
        for idx, i in enumerate(intervals)
    ]


# ── Genre drum patterns ────────────────────────────────────────────────────────

# MIDI drum map (General MIDI percussion channel 10 / note numbers)
KICK  = 36
SNARE = 38
CLAP  = 39
CH_HAT = 42   # closed hi-hat
OH_HAT = 46   # open hi-hat
RIDE  = 51

def drum_pattern(genre: str, bars: int = 4) -> list[dict]:
    """
    Return a list of drum note dicts for the given genre across `bars` bars.
    beat positions are absolute (4 beats per bar in 4/4).
    """
    genre = genre.lower()

    # Base 1-bar pattern as (beat_within_bar, pitch, velocity)
    if genre in ("trap", "trap beat"):
        one_bar: list[tuple[float, int, int]] = [
            # Kick on 1
            (0.0,  KICK,   100),
            # Snare / clap on 2 and 4
            (2.0,  SNARE,  90),
            (4.0 - 0.001, SNARE, 85),   # beat 4 (index 3 in 0-based)
            # Triplet hi-hats
            (0.0,  CH_HAT, 70),
            (0.333,CH_HAT, 55),
            (0.667,CH_HAT, 60),
            (1.0,  CH_HAT, 70),
            (1.333,CH_HAT, 55),
            (1.667,CH_HAT, 60),
            (2.0,  CH_HAT, 70),
            (2.333,CH_HAT, 55),
            (2.667,CH_HAT, 60),
            (3.0,  CH_HAT, 70),
            (3.333,CH_HAT, 55),
            (3.667,CH_HAT, 60),
        ]
    elif genre in ("lo-fi", "lofi", "lo-fi hip hop", "lofi hip hop"):
        one_bar = [
            (0.0,  KICK,  90),
            (1.5,  KICK,  75),
            (2.0,  SNARE, 85),
            (3.75, KICK,  70),
            # Lazy hi-hats every 0.5 beats
            (0.0,  CH_HAT, 60),
            (0.5,  CH_HAT, 45),
            (1.0,  CH_HAT, 60),
            (1.5,  CH_HAT, 50),
            (2.0,  CH_HAT, 60),
            (2.5,  CH_HAT, 45),
            (3.0,  CH_HAT, 60),
            (3.5,  CH_HAT, 50),
        ]
    elif genre in ("house", "tech house", "deep house"):
        one_bar = [
            # Four-on-the-floor kick
            (0.0, KICK, 110), (1.0, KICK, 105), (2.0, KICK, 110), (3.0, KICK, 105),
            # Snare on 2 and 4
            (1.0, SNARE, 90), (3.0, SNARE, 90),
            # 8th-note hats
            (0.0, CH_HAT, 65), (0.5, CH_HAT, 55),
            (1.0, CH_HAT, 65), (1.5, CH_HAT, 55),
            (2.0, CH_HAT, 65), (2.5, CH_HAT, 55),
            (3.0, CH_HAT, 65), (3.5, CH_HAT, 55),
        ]
    elif genre in ("dnb", "drum and bass", "drum & bass"):
        one_bar = [
            (0.0,  KICK,  105),
            (0.75, SNARE,  95),
            (1.5,  KICK,  100),
            (1.875,SNARE,  80),
            (2.0,  SNARE,  95),
            (2.75, KICK,  100),
            (3.5,  SNARE,  90),
            # 16th hats
            (0.0,  CH_HAT, 55), (0.25, CH_HAT, 40),
            (0.5,  CH_HAT, 55), (0.75, CH_HAT, 40),
            (1.0,  CH_HAT, 55), (1.25, CH_HAT, 40),
            (1.5,  CH_HAT, 55), (1.75, CH_HAT, 40),
            (2.0,  CH_HAT, 55), (2.25, CH_HAT, 40),
            (2.5,  CH_HAT, 55), (2.75, CH_HAT, 40),
            (3.0,  CH_HAT, 55), (3.25, CH_HAT, 40),
            (3.5,  CH_HAT, 55), (3.75, CH_HAT, 40),
        ]
    elif genre in ("rage_trap", "rage trap", "rage"):
        # Rage Trap: distorted 808, 32nd hi-hat triplet rolls, sparse kick
        one_bar = [
            (0.0,   KICK,   110),
            (2.5,   KICK,    85),
            # Clap on 3
            (2.0,   CLAP,    95),
            # 32nd triplet hi-hat rolls (every ~0.083 beats)
            (0.0,   CH_HAT,  80), (0.083, CH_HAT, 55), (0.167, CH_HAT, 60),
            (0.25,  CH_HAT,  75), (0.333, CH_HAT, 50), (0.417, CH_HAT, 55),
            (0.5,   CH_HAT,  80), (0.583, CH_HAT, 55), (0.667, CH_HAT, 60),
            (0.75,  CH_HAT,  75), (0.833, CH_HAT, 50), (0.917, CH_HAT, 55),
            (1.0,   CH_HAT,  80), (1.083, CH_HAT, 55), (1.167, CH_HAT, 60),
            (1.25,  CH_HAT,  75), (1.333, CH_HAT, 50), (1.417, CH_HAT, 55),
            (1.5,   CH_HAT,  80), (1.583, CH_HAT, 55), (1.667, CH_HAT, 60),
            (1.75,  CH_HAT,  75), (1.833, CH_HAT, 50), (1.917, CH_HAT, 55),
            (2.0,   CH_HAT,  80), (2.083, CH_HAT, 55), (2.167, CH_HAT, 60),
            (2.25,  CH_HAT,  75), (2.333, CH_HAT, 50), (2.417, CH_HAT, 55),
            (2.5,   CH_HAT,  80), (2.583, CH_HAT, 55), (2.667, CH_HAT, 60),
            (2.75,  CH_HAT,  75), (2.833, CH_HAT, 50), (2.917, CH_HAT, 55),
            (3.0,   CH_HAT,  80), (3.083, CH_HAT, 55), (3.167, CH_HAT, 60),
            (3.25,  CH_HAT,  75), (3.333, CH_HAT, 50), (3.417, CH_HAT, 55),
            (3.5,   CH_HAT,  80), (3.583, CH_HAT, 55), (3.667, CH_HAT, 60),
            (3.75,  CH_HAT,  75), (3.833, CH_HAT, 50), (3.917, CH_HAT, 55),
        ]
    elif genre in ("uk_drill", "uk drill", "drill"):
        # UK Drill: eerie, triplet 16th hi-hats, kick on 1 + syncopated, snare on 3
        one_bar = [
            (0.0,   KICK,   105),
            (1.25,  KICK,    80),
            (2.75,  KICK,    90),
            (2.0,   SNARE,   95),
            # Triplet 16th hats
            (0.0,   CH_HAT, 70), (0.333, CH_HAT, 50), (0.667, CH_HAT, 55),
            (1.0,   CH_HAT, 70), (1.333, CH_HAT, 50), (1.667, CH_HAT, 55),
            (2.0,   CH_HAT, 70), (2.333, CH_HAT, 50), (2.667, CH_HAT, 55),
            (3.0,   CH_HAT, 70), (3.333, CH_HAT, 50), (3.667, CH_HAT, 55),
            # Open hat on off-beats
            (0.5,   OH_HAT, 45), (1.5, OH_HAT, 45),
            (3.0,   OH_HAT, 50),
        ]
    elif genre in ("future_bass", "future bass"):
        # Future Bass: 4-on-floor kick, synth perc (open hats), sparse snare
        one_bar = [
            # Four-on-the-floor kick
            (0.0, KICK, 115), (1.0, KICK, 108), (2.0, KICK, 112), (3.0, KICK, 108),
            # Snare/clap on 2 and 4 (drops)
            (1.0, CLAP,  90), (3.0, CLAP,  90),
            # Synth-style open hat perc on off-beats
            (0.5, OH_HAT, 70), (1.5, OH_HAT, 60), (2.5, OH_HAT, 70), (3.5, OH_HAT, 60),
            # Tight 16th hats
            (0.0,  CH_HAT, 60), (0.25, CH_HAT, 45),
            (0.5,  CH_HAT, 60), (0.75, CH_HAT, 45),
            (1.0,  CH_HAT, 60), (1.25, CH_HAT, 45),
            (1.5,  CH_HAT, 60), (1.75, CH_HAT, 45),
            (2.0,  CH_HAT, 60), (2.25, CH_HAT, 45),
            (2.5,  CH_HAT, 60), (2.75, CH_HAT, 45),
            (3.0,  CH_HAT, 60), (3.25, CH_HAT, 45),
            (3.5,  CH_HAT, 60), (3.75, CH_HAT, 45),
        ]
    elif genre in ("big_room", "big room", "big room house"):
        # Big Room: deep festival kick, minimal syncopated, tension rides
        one_bar = [
            (0.0, KICK, 120), (1.0, KICK, 115), (2.0, KICK, 118), (3.0, KICK, 115),
            # Clap on 2 and 4
            (1.0, CLAP,  95), (3.0, CLAP,  95),
            # Open ride on off-beats (festival feel)
            (0.5, RIDE,  55), (2.5, RIDE,  50),
            # Sparse 8th hats
            (0.0, CH_HAT, 50), (1.0, CH_HAT, 50), (2.0, CH_HAT, 50), (3.0, CH_HAT, 50),
        ]
    elif genre in ("melodic_dubstep", "melodic dubstep"):
        # Melodic Dubstep: half-time feel — kick on 1+2.5, snare only on 3, rolling 16th hats
        one_bar = [
            (0.0,  KICK,  110),
            (2.5,  KICK,   90),
            (2.0,  SNARE,  95),
            # Rolling 16th hats (denser toward beat 2 and 4)
            (0.0,  CH_HAT, 55), (0.25, CH_HAT, 42),
            (0.5,  CH_HAT, 60), (0.75, CH_HAT, 38),
            (1.0,  CH_HAT, 65), (1.25, CH_HAT, 42),
            (1.5,  CH_HAT, 72), (1.75, CH_HAT, 45),
            (2.0,  CH_HAT, 55), (2.25, CH_HAT, 42),
            (2.5,  CH_HAT, 60), (2.75, CH_HAT, 38),
            (3.0,  CH_HAT, 65), (3.25, CH_HAT, 42),
            (3.5,  CH_HAT, 72), (3.75, CH_HAT, 50),
            # Open hat spray on beat 3.5 (dubstep tension)
            (1.5,  OH_HAT, 60), (3.5, OH_HAT, 55),
        ]
    elif genre in ("ncs_future_bass", "ncs future bass"):
        # NCS Future Bass: upgraded future_bass with ghost kick, open-hat spray, denser perc
        one_bar = [
            # Four-on-the-floor kick
            (0.0, KICK, 118), (1.0, KICK, 110), (2.0, KICK, 115), (3.0, KICK, 110),
            # Ghost kick at 2.75
            (2.75, KICK,  72),
            # Clap on 2 and 4
            (1.0, CLAP,  95), (3.0, CLAP,  92),
            # Open-hat spray (three quick hits before beat 2)
            (0.75, OH_HAT, 55), (0.875, OH_HAT, 65), (1.0, OH_HAT, 50),
            (2.75, OH_HAT, 58), (2.875, OH_HAT, 68), (3.0, OH_HAT, 52),
            # Dense 16th hats
            (0.0,  CH_HAT, 65), (0.25, CH_HAT, 48),
            (0.5,  CH_HAT, 62), (0.75, CH_HAT, 45),
            (1.0,  CH_HAT, 65), (1.25, CH_HAT, 48),
            (1.5,  CH_HAT, 62), (1.75, CH_HAT, 45),
            (2.0,  CH_HAT, 65), (2.25, CH_HAT, 48),
            (2.5,  CH_HAT, 62), (2.75, CH_HAT, 45),
            (3.0,  CH_HAT, 65), (3.25, CH_HAT, 48),
            (3.5,  CH_HAT, 62), (3.75, CH_HAT, 45),
        ]
    elif genre in ("ncs_big_room", "ncs big room"):
        # NCS Big Room: festival stomps with stutter at 3.5, ride on offbeats
        one_bar = [
            # Hard kicks (festival level)
            (0.0, KICK, 127), (1.0, KICK, 122), (2.0, KICK, 125), (3.0, KICK, 120),
            # Stutter kick at 3.5
            (3.5, KICK,  85), (3.75, KICK, 80),
            # Clap on 2 and 4
            (1.0, CLAP,  98), (3.0, CLAP,  98),
            # Ride on offbeats
            (0.5, RIDE,  60), (1.5, RIDE,  55), (2.5, RIDE,  60),
            # Sparse hats
            (0.0, CH_HAT, 52), (1.0, CH_HAT, 52), (2.0, CH_HAT, 52), (3.0, CH_HAT, 52),
        ]
    elif genre in ("neo_soul", "neo soul", "neo-soul"):
        # Neo-Soul: brush-style swing, ghost notes, warm pocket
        one_bar = [
            (0.0,   KICK,   90),
            (1.75,  KICK,   70),   # pushed kick (swing)
            (2.0,   SNARE,  88),
            (3.5,   SNARE,  80),
            # Ghost notes (low velocity)
            (0.5,   SNARE,  35), (1.0, SNARE, 30), (1.5, SNARE, 38),
            (2.5,   SNARE,  32), (3.0, SNARE, 28), (3.75, SNARE, 35),
            # Swing 8th hats (dotted feel)
            (0.0,   CH_HAT, 65), (0.667, CH_HAT, 45),
            (1.333, CH_HAT, 65), (2.0,   CH_HAT, 55),
            (2.667, CH_HAT, 65), (3.333, CH_HAT, 45),
            # Open hat on 4.5
            (3.5,   OH_HAT, 50),
        ]
    elif genre in ("pop_trap", "pop trap"):
        # Pop Trap: clean punchy, minimal hats, catchy pocket
        one_bar = [
            (0.0,  KICK,  110),
            (2.0,  KICK,   85),
            (3.25, KICK,   90),
            # Clap on 2 and 4
            (1.0,  CLAP,   95), (3.0, CLAP, 90),
            # 8th note hats (clean)
            (0.0,  CH_HAT, 65), (0.5,  CH_HAT, 50),
            (1.0,  CH_HAT, 65), (1.5,  CH_HAT, 50),
            (2.0,  CH_HAT, 65), (2.5,  CH_HAT, 50),
            (3.0,  CH_HAT, 65), (3.5,  CH_HAT, 50),
        ]
    else:
        # Generic hip-hop / pop
        one_bar = [
            (0.0,  KICK,  100),
            (1.0,  KICK,   80),
            (2.0,  SNARE,  90),
            (3.0,  SNARE,  85),
            # 8th hats
            (0.0,  CH_HAT, 60), (0.5, CH_HAT, 45),
            (1.0,  CH_HAT, 60), (1.5, CH_HAT, 45),
            (2.0,  CH_HAT, 60), (2.5, CH_HAT, 45),
            (3.0,  CH_HAT, 60), (3.5, CH_HAT, 45),
        ]

    notes = []
    for bar in range(bars):
        offset = bar * 4.0
        for beat, pitch, vel in one_bar:
            notes.append({
                "pitch":    pitch,
                "beat":     round(offset + beat, 6),
                "duration": 0.125,
                "velocity": vel,
            })
    return notes


# ── Bass lines ────────────────────────────────────────────────────────────────

def bass_line(root: str, scale_type: str, bars: int = 4,
              style: str = "simple") -> list[dict]:
    """
    Generate a bass line for the given key/scale.
    style: "simple" | "walking" | "trap" | "808"
    """
    pitches = scale_notes(root, scale_type, octave=2)  # low octave

    notes = []
    style = style.lower()

    for bar in range(bars):
        bar_start = bar * 4.0

        if style == "808":
            # Sustained root (1.75 beats) + sparse 8th fills — classic 808 pattern
            p2 = pitches[2] if len(pitches) > 2 else pitches[0]
            p4 = pitches[4] if len(pitches) > 4 else pitches[0]
            pattern = [
                (0.0, pitches[0], 1.75, 110),
                (2.0, p2,         0.5,  90),
                (3.0, pitches[0], 0.5,  95),
                (3.5, p4,         0.25, 80),
            ]
        elif style == "trap":
            # Root on 1, then sparse 8th-note hits
            pattern = [(0.0, pitches[0], 0.5, 110),
                       (1.5, pitches[0], 0.25, 90),
                       (2.0, pitches[4] if len(pitches) > 4 else pitches[0], 0.5, 100),
                       (3.0, pitches[0], 0.5, 95),
                       (3.5, pitches[2] if len(pitches) > 2 else pitches[0], 0.25, 80)]
        elif style == "walking":
            # Walk through scale degrees
            scale_idx = [0, 2, 4, 5, 4, 2, 1, 0]
            pattern = [(i * 0.5, pitches[scale_idx[i % len(scale_idx)]], 0.5, 80)
                       for i in range(8)]
        else:
            # Simple root–fifth–root–fifth
            fifth = pitches[4] if len(pitches) > 4 else pitches[0]
            pattern = [
                (0.0,  pitches[0], 1.0, 100),
                (1.0,  fifth,      0.5, 85),
                (2.0,  pitches[0], 1.0, 95),
                (3.0,  fifth,      0.5, 80),
                (3.5,  pitches[0], 0.5, 90),
            ]

        for beat, pitch, dur, vel in pattern:
            notes.append({
                "pitch":    pitch,
                "beat":     round(bar_start + beat, 6),
                "duration": dur,
                "velocity": vel,
            })

    return notes


# ── Chord progressions ────────────────────────────────────────────────────────

_COMMON_PROGRESSIONS: dict[str, list[tuple[int, str]]] = {
    # Major pop:  I – V – vi – IV  (C → G → Am → F)
    "major":   [(0, "major"),  (7, "major"),  (9, "minor"),  (5, "major")],
    # Natural minor: i – VII – VI – VII  (Am → G → F → G)
    "minor":   [(0, "minor"),  (10, "major"), (8, "major"),  (10, "major")],
    # Lo-fi: Imaj7 – vi-min7 – IVmaj7 – V7  (Cmaj7 → Am7 → Fmaj7 → G7)
    "lofi":    [(0, "maj7"),   (9, "min7"),   (5, "maj7"),   (7, "dom7")],
    # Trap: i-min7 – iv-min7 – VI – VII  (Am7 → Dm7 → F → G, dark & jazzy)
    "trap":    [(0, "min7"),   (5, "min7"),   (8, "major"),  (10, "major")],
    # House: i – VI – III – VII  (Am → F → C → G, driving)
    "house":   [(0, "minor"),  (8, "major"),  (3, "major"),  (10, "major")],
    # Jazz: ii-min7 – V7 – Imaj7 – vi-min7  (Dm7 → G7 → Cmaj7 → Am7)
    "jazz":    [(2, "min7"),   (7, "dom7"),   (0, "maj7"),   (9, "min7")],
    # DnB / breakbeat: i – VII – VI – VII  (Am → G → F → G, bleak)
    "dnb":     [(0, "minor"),  (10, "major"), (8, "major"),  (10, "major")],
    # Ambient: slow, ethereal  Iadd9 – vi-min9 – IVmaj7 – Vsus2
    "ambient": [(0, "add9"),   (9, "min9"),   (5, "maj7"),   (7, "sus2")],
    # Bedroom pop / default: I – V – vi – IV  (same as major but with 7ths)
    "default": [(0, "maj7"),   (7, "dom7"),   (9, "min7"),   (5, "maj7")],
}


def chord_progression(root: str, scale_type: str, bars: int = 4,
                      style: str = "default") -> list[dict]:
    """Return block chords for a 4-bar progression (one chord per bar).
    Extra styles: "stab" (syncopated quarter-note stabs), "arp" (8th-note arpeggio)."""
    # Normalise "lo-fi" variants for prog_key lookup
    style_key = style.lower().replace("lo-fi", "lofi").replace("lo fi", "lofi")
    prog_key = style_key if style_key in _COMMON_PROGRESSIONS else scale_type.lower()
    prog_key = prog_key if prog_key in _COMMON_PROGRESSIONS else "major"

    progression = _COMMON_PROGRESSIONS[prog_key]
    root_semitone = _SEMITONE_MAP.get(root, 0)
    inv_map = {v: k for k, v in _SEMITONE_MAP.items()}

    notes: list[dict] = []
    for bar in range(bars):
        chord_offset_semitones, quality = progression[bar % len(progression)]
        chord_root_semitone = (root_semitone + chord_offset_semitones) % 12
        chord_root_name = inv_map.get(chord_root_semitone, "C")

        bar_start = float(bar * 4)
        voicing = chord_voicing(chord_root_name, quality, octave=4)

        if style_key in ("stab", "house"):
            # House/stab: chord on beat 0 (0.5 beats) + syncopated stab on beat 2.5
            for beat_off, dur, vel in ((0.0, 0.5, 82), (1.5, 0.25, 68), (2.5, 0.5, 78), (3.5, 0.25, 65)):
                for n in voicing:
                    notes.append({
                        "pitch":    n["pitch"],
                        "beat":     round(bar_start + beat_off, 6),
                        "duration": dur,
                        "velocity": vel,
                    })
        elif style_key == "arp":
            # Arpeggiate chord tones every 0.5 beats across the bar
            sorted_pitches = sorted(n["pitch"] for n in voicing)
            for i in range(8):
                notes.append({
                    "pitch":    sorted_pitches[i % len(sorted_pitches)],
                    "beat":     round(bar_start + i * 0.5, 6),
                    "duration": 0.5,
                    "velocity": 65 + (i % 3) * 5,
                })
        elif style_key == "ambient":
            # Ambient: extra-long sustain (8 beats = 2 bars per chord)
            for n in voicing:
                notes.append({
                    "pitch":    n["pitch"],
                    "beat":     round(bar_start + n["beat"], 6),
                    "duration": 8.0,
                    "velocity": max(40, n["velocity"] - 20),  # quieter, soft wash
                })
        else:
            # Default: full-bar block chords (ring for the whole bar)
            for n in voicing:
                notes.append({
                    "pitch":    n["pitch"],
                    "beat":     round(bar_start + n["beat"], 6),
                    "duration": 4.0,
                    "velocity": n["velocity"],
                })

    return notes


# ── Melody ────────────────────────────────────────────────────────────────────

def drum_pattern_to_steps(genre: str, bars: int = 1) -> list[dict]:
    """
    Convert drum_pattern() output to a list of 16-step bool rows.
    Returns: [{name: str, color: str, steps: [bool x 16]}]
    Uses 1 bar only (for beat grid widget).
    """
    notes = drum_pattern(genre, bars=1)

    DRUM_ROLES: dict[int, tuple[str, str]] = {
        KICK:   ("Kick",     "#e74c3c"),
        SNARE:  ("Snare",    "#f39c12"),
        CLAP:   ("Clap",     "#f39c12"),
        CH_HAT: ("Hi-Hat",   "#3498db"),
        OH_HAT: ("Open Hat", "#2980b9"),
        RIDE:   ("Ride",     "#1abc9c"),
    }

    pitch_steps: dict[int, list[bool]] = {}
    for n in notes:
        pitch = n["pitch"]
        if pitch not in pitch_steps:
            pitch_steps[pitch] = [False] * 16
        beat = float(n["beat"])
        step = round(beat * 4) % 16
        pitch_steps[pitch][step] = True

    rows = []
    for pitch, (name, color) in DRUM_ROLES.items():
        if pitch in pitch_steps:
            rows.append({"name": name, "color": color, "steps": pitch_steps[pitch]})

    # Fill in any missing core rows so the grid always has Kick/Snare/Hi-Hat/Clap
    existing_names = {r["name"] for r in rows}
    defaults = [
        ("Kick",   "#e74c3c", KICK),
        ("Snare",  "#f39c12", SNARE),
        ("Hi-Hat", "#3498db", CH_HAT),
        ("Clap",   "#f39c12", CLAP),
    ]
    for name, color, _ in defaults:
        if name not in existing_names:
            rows.append({"name": name, "color": color, "steps": [False] * 16})

    return rows


# ── Harmonic Engine ───────────────────────────────────────────────────────────

# (semitone_offset_from_root, quality) per chord in a 4-bar cycle
_PROGRESSIONS_BY_GENRE: dict[tuple[str, str], list[tuple[int, str]]] = {
    ("pop",     "major"): [(0,"add9"), (7,"maj7"), (9,"min7"), (5,"maj7")],
    ("pop",     "minor"): [(0,"min7"), (10,"maj"), (8,"maj7"), (10,"maj")],
    ("jazz",    "major"): [(2,"min7"), (7,"dom7"), (0,"maj7"), (0,"maj7")],
    ("jazz",    "minor"): [(2,"min7"), (7,"dom7"), (0,"min7"), (0,"min7")],
    ("blues",   "major"): [(0,"dom7"), (5,"dom7"), (7,"dom7"), (0,"dom7")],
    ("blues",   "minor"): [(0,"min7"), (5,"min7"), (7,"dom7"), (0,"min7")],
    ("lofi",    "major"): [(0,"maj7"), (2,"min7"), (9,"min7"), (5,"maj7")],
    ("lofi",    "minor"): [(0,"min9"), (10,"maj7"), (8,"maj7"), (7,"min7")],
    ("trap",    "major"): [(0,"add9"), (7,"maj7"), (9,"min7"), (5,"maj7")],
    ("trap",    "minor"): [(0,"min7"), (10,"maj"), (8,"maj"), (7,"maj")],
    ("house",   "major"): [(0,"maj7"), (5,"maj7"), (9,"min7"), (7,"maj7")],
    ("house",   "minor"): [(0,"min7"), (8,"maj7"), (3,"maj"), (10,"maj")],
    ("ambient", "major"): [(0,"add9"), (4,"min7"), (9,"min9"), (5,"maj7")],
    ("ambient", "minor"): [(0,"min9"), (8,"maj7"), (5,"maj7"), (7,"sus2")],
    ("dnb",        "major"): [(0,"maj"),  (10,"maj"), (8,"maj"), (7,"maj")],
    ("dnb",        "minor"): [(0,"min7"), (10,"maj"), (8,"maj"), (10,"maj")],
    # New genres (v0.9.5)
    ("rage_trap",  "major"): [(0,"add9"), (10,"maj"), (8,"maj"), (7,"maj")],
    ("rage_trap",  "minor"): [(0,"min7"), (10,"maj"), (8,"maj"), (3,"maj")],
    ("uk_drill",   "major"): [(0,"min7"), (8,"maj7"), (5,"maj7"), (10,"maj")],
    ("uk_drill",   "minor"): [(0,"min7"), (10,"maj"), (8,"maj"), (5,"min7")],
    ("future_bass","major"): [(0,"add9"), (7,"maj7"), (4,"min7"), (5,"maj7")],
    ("future_bass","minor"): [(0,"min9"), (8,"maj7"), (3,"maj"),  (7,"sus2")],
    # NCS-specific genres (v0.9.9)
    ("ncs_future_bass","major"): [(0,"add9"),  (7,"sus2"),  (4,"min7"),  (5,"maj7")],
    ("ncs_future_bass","minor"): [(0,"min9"),  (8,"maj7"),  (3,"add9"),  (10,"maj7")],
    ("melodic_dubstep","major"): [(0,"add9"),  (8,"maj7"),  (5,"maj7"),  (7,"sus2")],
    ("melodic_dubstep","minor"): [(0,"min9"),  (10,"maj7"), (8,"maj7"),  (5,"maj7")],
    ("ncs_big_room",   "major"): [(0,"add9"),  (10,"maj"),  (8,"maj"),   (7,"maj")],
    ("ncs_big_room",   "minor"): [(0,"min7"),  (8,"maj7"),  (3,"add9"),  (10,"maj7")],
    ("big_room",   "major"): [(0,"add9"), (10,"maj"), (8,"maj"), (7,"maj")],
    ("big_room",   "minor"): [(0,"min7"), (10,"maj"), (8,"maj"), (7,"min7")],
    ("neo_soul",   "major"): [(0,"maj7"), (2,"min7"), (5,"maj7"), (7,"dom7")],
    ("neo_soul",   "minor"): [(0,"min9"), (5,"min7"), (8,"maj7"), (10,"maj7")],
    ("pop_trap",   "major"): [(0,"add9"), (7,"maj7"), (9,"min7"), (5,"maj7")],
    ("pop_trap",   "minor"): [(0,"min7"), (10,"maj"), (8,"maj"),  (3,"maj")],
    ("default",    "major"): [(0,"add9"), (7,"maj7"), (9,"min7"), (5,"maj7")],
    ("default",    "minor"): [(0,"min7"), (10,"maj"), (8,"maj7"), (10,"maj")],
}

_CHORD_INTERVALS_MAP: dict[str, list[int]] = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
    "dom7":  [0, 4, 7, 10],
    "maj7":  [0, 4, 7, 11],
    "min7":  [0, 3, 7, 10],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "add9":  [0, 4, 7, 14],
    "min9":  [0, 3, 7, 10, 14],
    "dim":      [0, 3, 6],
    "maj":      [0, 4, 7],
    "min":      [0, 3, 7],
    # NCS floating/sparse voicings (v0.9.9)
    "maj7sus2": [0, 2, 7, 11],  # floating NCS supersaw sound
    "power5":   [0, 7],          # sparse stab
}

_INV_SEMITONE: dict[int, str] = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B",
}


def supersaw_voicing(root: str, quality: str, octave: int = 4) -> list[dict]:
    """
    Return a 7-note NCS-style stacked chord voicing:
      sub-octave root + standard chord (octave 4) + octave doublings (5-6).
    Used to simulate the supersaw wide stack sound via multiple oscillators.
    Notes start at beat 0, last 4 beats.
    """
    intervals = _CHORD_INTERVALS_MAP.get(quality.lower(), [0, 4, 7])
    root_pc   = _SEMITONE_MAP.get(root, 0)

    # Sub-octave root (octave 2)
    sub_root = (octave - 2 + 1) * 12 + root_pc  # MIDI octave 2

    # Standard chord voicing (octave 4)
    base = (octave + 1) * 12 + root_pc
    chord_notes = [base + iv for iv in intervals]

    # Upper octave doubling (octave 5) — only root + 3rd + 5th
    upper = [(base + 12 + iv) for iv in intervals[:3]]

    all_pitches = [sub_root] + chord_notes + upper[:3]
    velocities  = [100, 80, 75, 78, 68, 65, 60]

    return [
        {"pitch": max(0, min(127, p)), "beat": 0.0,
         "duration": 4.0, "velocity": v}
        for p, v in zip(all_pitches, velocities)
    ]


def chord_schedule(key: str, scale_type: str, genre: str, bars: int) -> list[dict]:
    """
    Returns one chord entry per bar for `bars` bars, cycling the progression.
    Each entry: {"bar": i, "beat": 0.0, "root": midi_int, "quality": str, "pitches": [int]}
    Pitches voiced in octave 4-5 range (48-72).
    """
    scale_type_norm = scale_type.lower()
    # Normalize scale_type: anything that isn't "minor" maps to "major"
    if scale_type_norm not in ("major", "minor"):
        scale_type_norm = "major"

    genre_norm = genre.lower()
    lookup = (genre_norm, scale_type_norm)
    if lookup not in _PROGRESSIONS_BY_GENRE:
        lookup = ("pop", scale_type_norm)
    if lookup not in _PROGRESSIONS_BY_GENRE:
        lookup = ("default", "minor")

    prog = _PROGRESSIONS_BY_GENRE[lookup]
    root_semitone = _SEMITONE_MAP.get(key, 0)

    result = []
    for bar in range(bars):
        offset_semitones, quality = prog[bar % len(prog)]
        chord_root_semitone = (root_semitone + offset_semitones) % 12
        # Voice in octave 4 (MIDI 48-60 base)
        base_midi = 48 + chord_root_semitone
        intervals = _CHORD_INTERVALS_MAP.get(quality, [0, 4, 7])
        pitches = []
        for iv in intervals:
            p = base_midi + iv
            # Wrap up an octave if too low
            if p < 48:
                p += 12
            # Keep within 48-84 range
            while p > 72:
                p -= 12
            pitches.append(p)
        result.append({
            "bar":     bar,
            "beat":    0.0,
            "root":    base_midi,
            "quality": quality,
            "pitches": pitches,
        })
    return result


_CHORD_RHYTHM_PATTERNS: dict[str, list[tuple[float, float, int]]] = {
    # (beat_offset, duration, base_velocity)
    "pop":            [(0.0, 2.0, 82), (2.0, 2.0, 78)],
    "jazz":           [(0.5, 0.5, 75), (1.5, 0.5, 70), (2.5, 0.5, 75), (3.5, 0.5, 68)],
    "blues":          [(0.0, 0.75, 82), (1.0, 0.5, 75), (1.5, 0.5, 78),
                       (2.0, 0.75, 80), (2.5, 0.5, 72), (3.0, 0.5, 76)],
    "lofi":           [(0.0, 1.25, 70), (2.0, 0.75, 64), (3.25, 0.25, 60)],
    "trap":           [(0.0, 4.0, 68)],
    "house":          [(0.0, 0.5, 82), (1.5, 0.5, 76), (2.5, 0.5, 80), (3.5, 0.25, 70)],
    "ambient":        [(0.0, 8.0, 56)],
    "dnb":            [(0.0, 0.5, 80), (1.0, 0.5, 74), (2.0, 0.5, 78), (3.0, 0.5, 72)],
    # NCS syncopated stab: hard hit on 1, quick stabs on 1.5 / 2.5 / 3.5
    "ncs_stab":       [(0.0, 0.25, 90), (1.5, 0.25, 80), (2.5, 0.25, 85), (3.5, 0.25, 75)],
    # NCS chop: eighth-note chops with velocity variation (pumping feel)
    "ncs_chop":       [(0.0, 0.5, 88), (0.5, 0.5, 72), (1.0, 0.5, 85), (1.5, 0.5, 68),
                       (2.0, 0.5, 90), (2.5, 0.5, 72), (3.0, 0.5, 85), (3.5, 0.5, 65)],
    "default":        [(0.0, 4.0, 74)],
}


def chord_progression_from_schedule(cs: list[dict], genre: str) -> list[dict]:
    """Generate chord notes using chord schedule + genre-specific rhythm pattern."""
    pattern = _CHORD_RHYTHM_PATTERNS.get(genre, _CHORD_RHYTHM_PATTERNS["default"])
    notes = []
    for entry in cs:
        bar_offset = entry["bar"] * 4.0
        pitches = entry["pitches"]
        for (b_off, dur, base_vel) in pattern:
            for i, pitch in enumerate(pitches):
                vel = max(55, min(100, base_vel - i * 4))
                notes.append({
                    "pitch":    pitch,
                    "beat":     round(bar_offset + b_off, 6),
                    "duration": dur,
                    "velocity": vel,
                })
    return notes


# Bass rhythm patterns: (beat_offset, semitone_from_root, duration, velocity)
_BASS_RHYTHM_PATTERNS: dict[str, list[tuple[float, int, float, int]] | str] = {
    "pop":     [(0.0, 0, 1.5, 100), (2.0, 0, 1.5, 90)],
    "jazz":    "walking",
    "blues":   [(0.0, 0, 1.0, 100), (1.0, 7, 0.5, 85),
                (1.5, 0, 0.5, 90), (2.0, 0, 1.0, 95),
                (3.0, 7, 0.5, 80), (3.5, 0, 0.5, 90)],
    "trap":    [(0.0, 0, 1.75, 110), (2.0, 7, 0.5, 90), (3.0, 0, 0.75, 95)],
    "lofi":    [(0.0, 0, 1.0, 88), (2.5, 0, 0.5, 75)],
    "house":   [(0.0, 0, 0.5, 100), (0.5, 0, 0.5, 80),
                (1.0, 7, 0.5, 88), (2.0, 0, 0.5, 100), (3.0, 7, 0.5, 82)],
    "ambient": [(0.0, 0, 4.0, 62)],
    "dnb":     [(0.0, 0, 0.5, 105), (0.75, 0, 0.25, 82),
                (1.5, 0, 0.5, 90), (3.0, 0, 0.5, 98)],
    "default": [(0.0, 0, 1.0, 100), (2.0, 7, 0.5, 85),
                (2.5, 0, 0.5, 90), (3.0, 0, 0.5, 80)],
}


def bass_line_harmonic(chord_sched: list[dict], genre: str, bars: int) -> list[dict]:
    """Generate a harmonically-aware bass line following the chord schedule."""
    pattern = _BASS_RHYTHM_PATTERNS.get(genre, _BASS_RHYTHM_PATTERNS["default"])
    notes = []

    for idx, entry in enumerate(chord_sched):
        bar = entry["bar"]
        if bar >= bars:
            break
        bar_offset = bar * 4.0
        # Bass root = chord root forced to octave 2 (MIDI 24-35 range)
        chord_root = entry["root"]
        bass_root = (chord_root % 12) + 36  # octave 2 (C2=36)

        if pattern == "walking":
            # Determine target for next bar (for voice leading)
            next_root = chord_sched[(idx + 1) % len(chord_sched)]["root"]
            next_bass = (next_root % 12) + 36
            # Walk: root on 1, chromatic/stepwise movement on beats 2,3,4
            walk_pitches = [
                bass_root,
                bass_root + 2,
                bass_root + 4,
                next_bass - 1 if next_bass > bass_root else next_bass + 1,
            ]
            walk_vels = [100, 80, 85, 75]
            for i, (wp, wv) in enumerate(zip(walk_pitches, walk_vels)):
                notes.append({
                    "pitch":    max(24, min(55, wp)),
                    "beat":     round(bar_offset + i * 1.0, 6),
                    "duration": 1.0,
                    "velocity": wv,
                })
        else:
            for (b_off, semitone_offset, dur, vel) in pattern:
                pitch = bass_root + semitone_offset
                # Keep in bass range 24-55
                while pitch > 55:
                    pitch -= 12
                while pitch < 24:
                    pitch += 12
                notes.append({
                    "pitch":    pitch,
                    "beat":     round(bar_offset + b_off, 6),
                    "duration": dur,
                    "velocity": vel,
                })

            # Approach note on beat 3.75 when chord changes next bar
            if idx + 1 < len(chord_sched):
                next_root = chord_sched[idx + 1]["root"]
                next_bass = (next_root % 12) + 36
                if next_bass != bass_root and genre in ("pop", "jazz", "blues"):
                    approach = next_bass - 1 if next_bass > bass_root else next_bass + 1
                    notes.append({
                        "pitch":    max(24, min(55, approach)),
                        "beat":     round(bar_offset + 3.75, 6),
                        "duration": 0.25,
                        "velocity": 72,
                    })

    return notes


_MELODY_RHYTHM_BY_GENRE: dict[str, tuple[list[float], list[float]]] = {
    # (beat_offsets, durations)
    "trap":           ([0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                       [0.25, 0.25, 0.5, 0.5, 0.5, 0.25, 0.5, 0.5]),
    "rnb":            ([0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                       [0.25, 0.25, 0.5, 0.5, 0.5, 0.25, 0.5, 0.5]),
    "jazz":           ([0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.75],
                       [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.25, 0.25]),
    "lofi":           ([0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.75],
                       [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.25, 0.25]),
    # NCS lead: wide intervallic anthem feel, strong beat-1 landing
    "ncs_lead":       ([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                       [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.75, 0.25]),
    "anthem":         ([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                       [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.75, 0.25]),
    # NCS pluck: staccato 16th-note grid, punchy velocities
    "ncs_pluck":      ([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
                        2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75],
                       [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2,
                        0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    "pluck":          ([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
                        2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75],
                       [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2,
                        0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    "default":        ([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                       [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 0.5]),
}


def melody_line_harmonic(chord_sched: list[dict], key: str, scale_type: str,
                         genre: str, bars: int) -> list[dict]:
    """Generate a chord-aware melody — beat 0 of each bar lands on a chord tone."""
    scale_pits = scale_notes(key, scale_type, octave=5)
    rhythm_key = genre if genre in _MELODY_RHYTHM_BY_GENRE else "default"
    beat_offs, durs = _MELODY_RHYTHM_BY_GENRE[rhythm_key]

    notes = []
    prev_pitch = scale_pits[0]

    for idx, entry in enumerate(chord_sched):
        bar = entry["bar"]
        if bar >= bars:
            break
        bar_offset = bar * 4.0
        chord_pitches = entry["pitches"]

        # Find chord tone in melody octave nearest to prev_pitch
        # Chord pitches are in octave 4-5; shift to octave 5 for melody
        def _nearest_chord_tone(target: int) -> int:
            candidates = []
            for cp in chord_pitches:
                # Try in octave 5 and 6
                for shift in (12, 24):
                    p = (cp % 12) + 60 + (shift - 12)  # normalize to C5-range
                    candidates.append(p)
            if not candidates:
                return target
            return min(candidates, key=lambda p: abs(p - target))

        downbeat_pitch = _nearest_chord_tone(prev_pitch)
        downbeat_vel = 92

        bar_notes = []
        # Beat 0: chord tone
        bar_notes.append({
            "pitch":    max(60, min(84, downbeat_pitch)),
            "beat":     round(bar_offset, 6),
            "duration": durs[0],
            "velocity": downbeat_vel,
        })
        prev_pitch = downbeat_pitch

        # Middle beats: scale tones, prefer chord extensions
        chord_set = set(cp % 12 for cp in chord_pitches)
        for i in range(1, len(beat_offs)):
            b = beat_offs[i]
            if b >= 4.0:
                break
            # Pick scale note nearest to prev_pitch, biased toward chord tones
            candidates = []
            for sp in scale_pits:
                # Prefer chord tones (bias them closer)
                dist = abs(sp - prev_pitch)
                if sp % 12 in chord_set:
                    dist -= 1  # bonus for chord tone
                candidates.append((dist, sp))
            candidates.sort(key=lambda x: x[0])
            chosen = candidates[0][1] if candidates else prev_pitch

            # Keep in melody range 60-84
            while chosen < 60:
                chosen += 12
            while chosen > 84:
                chosen -= 12

            vel = 70 + (i % 4) * 3
            bar_notes.append({
                "pitch":    chosen,
                "beat":     round(bar_offset + b, 6),
                "duration": durs[i] if i < len(durs) else 0.5,
                "velocity": vel,
            })
            prev_pitch = chosen

        # Lead-out at 3.5: aim toward next chord root or 3rd
        if idx + 1 < len(chord_sched) and beat_offs[-1] < 3.5:
            next_entry = chord_sched[idx + 1]
            next_root_pc = next_entry["root"] % 12
            # Target root in melody octave
            target = next_root_pc + 60
            while target > 84:
                target -= 12
            bar_notes.append({
                "pitch":    max(60, min(84, target)),
                "beat":     round(bar_offset + 3.5, 6),
                "duration": 0.5,
                "velocity": 65,
            })

        notes.extend(bar_notes)

    return notes


def melody_line(root: str, scale_type: str, bars: int = 4,
                style: str = "arc") -> list[dict]:
    """Generate a melodic phrase.
    style: "simple" | "trap" | "rnb" | "walking" | "arc" (default, arch contour)
    """
    pitches = scale_notes(root, scale_type, octave=5)

    notes = []
    style = style.lower()

    for bar in range(bars):
        bar_start = bar * 4.0

        if style in ("trap", "rnb"):
            # Syncopated short notes
            pattern_idx = [0, 0, 2, 4, 4, 2, 0, 4]
            durations   = [0.25, 0.5, 0.25, 0.5, 0.25, 0.25, 0.5, 0.5]
            beats       = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        elif style == "walking":
            pattern_idx = list(range(min(8, len(pitches))))
            durations   = [0.5] * 8
            beats       = [i * 0.5 for i in range(8)]
        elif style == "arc":
            # Arch contour: ascending first half, resolve in second half
            half = max(1, bars // 2)
            top_idx = len(pitches) - 1
            if bar < half:
                progress = bar / half
                base = int(progress * top_idx)
                raw = [base, base + 1, base + 2, base + 2,
                       base + 3, base + 2, base + 3, base + 3]
            else:
                progress = (bar - half) / max(1, bars - half)
                base = max(0, top_idx - int(progress * top_idx))
                raw = [base, base - 1, base - 1, base - 2,
                       base - 2, base - 3, 1, 0]
            pattern_idx = [max(0, min(len(pitches) - 1, i)) for i in raw]
            durations   = [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.75]
            beats       = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.5]
        else:  # "simple"
            pattern_idx = [0, 2, 4, 6 % len(pitches), 4, 2, 0, 4]
            durations   = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 0.5]
            beats       = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.75]

        for i, (beat, idx, dur) in enumerate(zip(beats, pattern_idx, durations)):
            if beat >= 4.0:
                break
            p_idx = idx % len(pitches)
            notes.append({
                "pitch":    pitches[p_idx],
                "beat":     round(bar_start + beat, 6),
                "duration": dur,
                "velocity": 75 + (i % 4) * 5,
            })

    return notes


# ── Key detection ─────────────────────────────────────────────────────────────

# Krumhansl-Schmuckler key profiles (major and minor).
_KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

_NOTE_NAMES_ORDERED = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def detect_key_from_notes(pitches: list[int]) -> tuple[str, str]:
    """
    Use Krumhansl-Schmuckler pitch-class profiles to detect the most likely
    key and scale type from a list of MIDI pitch integers.

    Returns ``(key, scale_type)`` e.g. ``("C", "major")`` or ``("A", "minor")``.
    Falls back to ``("C", "major")`` if ``pitches`` is empty.
    """
    if not pitches:
        return "C", "major"

    # Build pitch-class histogram (counts per semitone 0-11)
    hist = [0.0] * 12
    for p in pitches:
        hist[p % 12] += 1.0

    # Normalize
    total = sum(hist) or 1.0
    hist = [h / total for h in hist]

    best_score = -1.0
    best_key = "C"
    best_scale = "major"

    for root in range(12):
        # Rotate histogram to align with this root
        rotated = hist[root:] + hist[:root]

        # Pearson-like dot product (profile is already mean-centred-ish for KS)
        maj_score = sum(rotated[i] * _KS_MAJOR[i] for i in range(12))
        min_score = sum(rotated[i] * _KS_MINOR[i] for i in range(12))

        if maj_score > best_score:
            best_score = maj_score
            best_key = _NOTE_NAMES_ORDERED[root]
            best_scale = "major"
        if min_score > best_score:
            best_score = min_score
            best_key = _NOTE_NAMES_ORDERED[root]
            best_scale = "minor"

    return best_key, best_scale
