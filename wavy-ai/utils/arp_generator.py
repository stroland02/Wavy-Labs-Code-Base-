"""
arp_generator.py — Arpeggiator MIDI pattern generator.

generate_arp(chord_notes, bpm, style, bars) → MIDI file path
"""
from __future__ import annotations

import random as _rand
import uuid
from pathlib import Path

import mido

import config

# style → (note_interval_beats, direction)
_STYLES: dict[str, tuple[float, str]] = {
    "8th":          (0.5,        "up"),
    "16th":         (0.25,       "up"),
    "triplet_16th": (1.0 / 3.0,  "up"),
    "pingpong":     (0.25,       "pingpong"),
    "random":       (0.25,       "random"),
}


def generate_arp(chord_notes: list[int], bpm: int = 120,
                 style: str = "16th", bars: int = 2) -> str:
    """Generate an arpeggiated MIDI pattern from a list of MIDI note numbers.

    chord_notes: e.g. [60, 64, 67] for C major
    bpm: tempo in BPM
    style: "8th" | "16th" | "triplet_16th" | "pingpong" | "random"
    bars: length of the generated pattern

    Returns: absolute path to generated MIDI file.
    """
    if not chord_notes:
        chord_notes = [60, 64, 67]

    interval, direction = _STYLES.get(style, _STYLES["16th"])
    sorted_notes = sorted(chord_notes)

    notes_per_bar = max(1, round(4.0 / interval))
    total_notes = bars * notes_per_bar

    # Build pitch sequence
    sequence: list[int] = []
    if direction == "pingpong":
        fwd = sorted_notes + list(reversed(sorted_notes[1:-1])) if len(sorted_notes) > 2 else sorted_notes
        for i in range(total_notes):
            sequence.append(fwd[i % len(fwd)])
    elif direction == "random":
        for _ in range(total_notes):
            sequence.append(_rand.choice(sorted_notes))
    else:  # "up"
        for i in range(total_notes):
            sequence.append(sorted_notes[i % len(sorted_notes)])

    # Write MIDI
    tpb = 480
    mid = mido.MidiFile(ticks_per_beat=tpb, type=0)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    track.append(mido.Message("program_change", channel=0, program=0, time=0))

    note_ticks = max(1, int(interval * tpb))

    events: list[tuple[int, str, int, int]] = []
    for i, pitch in enumerate(sequence):
        start = i * note_ticks
        end = start + max(1, int(note_ticks * 0.88))  # slight staccato gap
        vel = 80 + (i % 3) * 8
        events.append((start, "note_on",  pitch, vel))
        events.append((end,   "note_off", pitch, 0))

    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

    prev = 0
    for tick, mtype, pitch, vel in events:
        delta = max(0, tick - prev)
        track.append(mido.Message(mtype, note=pitch, velocity=vel,
                                   channel=0, time=delta))
        prev = tick

    track.append(mido.MetaMessage("end_of_track", time=0))

    out_path = config.GENERATION_DIR / f"arp_{uuid.uuid4().hex[:8]}.mid"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(out_path))
    return str(out_path)
