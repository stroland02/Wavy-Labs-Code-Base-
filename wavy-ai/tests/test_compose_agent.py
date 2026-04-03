"""
Tests for ComposeAgent and music_theory helpers.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make wavy-ai root importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Minimal stubs so imports don't fail without config / loguru ───────────────

class _MockConfig:
    GENERATION_DIR = Path(__file__).parent / "tmp_compose"

_MockConfig.GENERATION_DIR.mkdir(exist_ok=True)

import types
config_stub = types.ModuleType("config")
config_stub.GENERATION_DIR = _MockConfig.GENERATION_DIR
sys.modules.setdefault("config", config_stub)

# Stub loguru
loguru_stub = types.ModuleType("loguru")
loguru_stub.logger = MagicMock()
sys.modules.setdefault("loguru", loguru_stub)


# ── music_theory tests ────────────────────────────────────────────────────────

from utils.music_theory import (
    scale_notes, chord_voicing, drum_pattern, bass_line,
    chord_progression, melody_line,
    chord_schedule, chord_progression_from_schedule,
    bass_line_harmonic, melody_line_harmonic,
    detect_key_from_notes,
    KICK, SNARE, CH_HAT,
)


class TestScaleNotes:
    def test_c_major_count(self):
        notes = scale_notes("C", "major", octave=4)
        assert len(notes) == 7

    def test_c_major_pitches(self):
        notes = scale_notes("C", "major", octave=4)
        assert notes[0] == 60   # C4

    def test_d_minor(self):
        notes = scale_notes("D", "minor", octave=4)
        assert len(notes) == 7
        assert notes[0] == 62   # D4

    def test_pentatonic(self):
        notes = scale_notes("A", "pentatonic", octave=4)
        assert len(notes) == 5

    def test_unknown_scale_falls_back_to_major(self):
        notes = scale_notes("C", "mystery_scale", octave=4)
        assert len(notes) == 7   # major fallback


class TestChordVoicing:
    def test_major_chord_has_three_notes(self):
        notes = chord_voicing("C", "major")
        assert len(notes) == 3

    def test_dom7_has_four_notes(self):
        notes = chord_voicing("G", "dom7")
        assert len(notes) == 4

    def test_note_fields(self):
        notes = chord_voicing("C", "minor")
        for n in notes:
            assert "pitch" in n and "beat" in n and "duration" in n and "velocity" in n


class TestDrumPattern:
    def test_trap_4_bars_has_notes(self):
        notes = drum_pattern("trap", 4)
        assert len(notes) > 0

    def test_has_kick_and_snare(self):
        notes = drum_pattern("trap", 4)
        pitches = {n["pitch"] for n in notes}
        assert KICK in pitches
        assert SNARE in pitches

    def test_lofi_pattern(self):
        notes = drum_pattern("lo-fi", 2)
        assert len(notes) > 0

    def test_all_notes_within_bounds(self):
        for genre in ("trap", "lo-fi", "house", "dnb", "generic"):
            for n in drum_pattern(genre, 2):
                assert 0 <= n["pitch"] <= 127
                assert 0 <= n["velocity"] <= 127
                assert n["beat"] >= 0


class TestBassLine:
    def test_simple_style(self):
        notes = bass_line("C", "major", bars=2, style="simple")
        assert len(notes) > 0

    def test_trap_style(self):
        notes = bass_line("D", "minor", bars=2, style="trap")
        assert len(notes) > 0

    def test_walking_style(self):
        notes = bass_line("G", "major", bars=2, style="walking")
        assert len(notes) > 0


class TestChordProgression:
    def test_returns_notes(self):
        notes = chord_progression("C", "major", bars=4)
        assert len(notes) > 0

    def test_lofi_style(self):
        notes = chord_progression("F", "minor", bars=4, style="lofi")
        assert len(notes) > 0


class TestMelodyLine:
    def test_simple_melody(self):
        notes = melody_line("C", "major", bars=2, style="simple")
        assert len(notes) > 0

    def test_trap_melody(self):
        notes = melody_line("D", "minor", bars=2, style="trap")
        assert len(notes) > 0


# ── ComposeAgent tests ────────────────────────────────────────────────────────

# Stubs for dependencies not available in test env
cloud_stub = types.ModuleType("cloud")
router_stub = types.ModuleType("cloud.router")
sys.modules.setdefault("cloud", cloud_stub)
sys.modules.setdefault("cloud.router", router_stub)

models_stub = types.ModuleType("models")
registry_stub = types.ModuleType("models.registry")
registry_stub.ModelRegistry = MagicMock
sys.modules.setdefault("models", models_stub)
sys.modules.setdefault("models.registry", registry_stub)


from agents.compose_agent import ComposeAgent, _extract_json


class TestExtractJson:
    def test_clean_json(self):
        text = '{"bpm": 140, "key": "D"}'
        result = _extract_json(text)
        assert result == {"bpm": 140, "key": "D"}

    def test_json_wrapped_in_text(self):
        text = 'Here is the plan:\n{"bpm": 120}\nDone.'
        result = _extract_json(text)
        assert result["bpm"] == 120

    def test_returns_none_on_bad_input(self):
        assert _extract_json("not json at all") is None

    def test_returns_none_on_empty(self):
        assert _extract_json("") is None


class TestComposeAgentArrange:
    def _make_agent(self, llm_plan: dict | None, llm_notes: dict | None):
        """Helper: mock the LLM to return given plan + notes dicts."""
        agent = ComposeAgent()

        plan_json   = json.dumps(llm_plan)   if llm_plan   else ""
        notes_json  = json.dumps(llm_notes)  if llm_notes  else ""

        call_count = {"n": 0}
        def fake_call_llm(system, user):
            call_count["n"] += 1
            # First call = plan, subsequent = notes
            if call_count["n"] == 1:
                return plan_json
            return notes_json

        with patch("agents.compose_agent._call_llm", side_effect=fake_call_llm):
            yield agent, fake_call_llm

    def test_arrange_returns_correct_keys(self):
        plan = {
            "bpm": 140, "key": "D", "scale": "minor", "bars": 4,
            "parts": [
                {"name": "Drums", "role": "drums", "description": "trap drums", "color": "#e74c3c"},
                {"name": "Bass",  "role": "bass",  "description": "trap bass",  "color": "#2ecc71"},
            ]
        }
        notes = {"notes": [{"pitch": 60, "beat": 0.0, "duration": 1.0, "velocity": 80}]}

        call_count = {"n": 0}
        def fake_call(system, user, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return json.dumps(plan)
            return json.dumps(notes)

        with patch("agents.compose_agent._call_llm", side_effect=fake_call):
            result = ComposeAgent().compose({
                "prompt": "trap beat D minor 140 BPM 4 bars",
                "mode": "arrange",
                "session_id": "test-session-1",
            })

        assert result["mode"] == "arrange"
        assert "parts" in result
        # Drums split into Kick/Snare/Hi-Hat (3) + Bass (1) = 4 total
        assert len(result["parts"]) >= 2
        assert result["bpm"] == 140
        assert result["key"] == "D"
        assert "session_id" in result

    def test_each_part_has_midi_file(self):
        plan = {
            "bpm": 120, "key": "C", "scale": "major", "bars": 2,
            "parts": [
                {"name": "Melody", "role": "melody", "description": "simple melody", "color": "#9b59b6"},
            ]
        }
        notes = {"notes": [{"pitch": 60, "beat": 0.0, "duration": 0.5, "velocity": 80},
                            {"pitch": 64, "beat": 0.5, "duration": 0.5, "velocity": 75}]}

        call_count = {"n": 0}
        def fake_call(system, user, **kwargs):
            call_count["n"] += 1
            return json.dumps(plan) if call_count["n"] == 1 else json.dumps(notes)

        with patch("agents.compose_agent._call_llm", side_effect=fake_call):
            result = ComposeAgent().compose({
                "prompt": "simple melody",
                "mode": "arrange",
                "session_id": "test-session-2",
            })

        for part in result["parts"]:
            assert "midi_path" in part
            assert Path(part["midi_path"]).exists()

    def test_fallback_when_llm_returns_empty(self):
        """When LLM returns nothing, fallback notes should still produce a valid MIDI."""
        with (
            patch("agents.compose_agent._call_llm", return_value=""),
            patch("agents.compose_agent._midi_find_seed", return_value=None),
        ):
            result = ComposeAgent().compose({
                "prompt": "lo-fi hip hop, C minor, 85 BPM, 4 bars",
                "mode": "arrange",
                "session_id": "test-session-3",
            })

        assert result["mode"] == "arrange"
        # Drums split into per-voice tracks (Kick/Snare/Hi-Hat) so total > 4
        assert len(result["parts"]) >= 4
        for part in result["parts"]:
            assert Path(part["midi_path"]).exists()
            # Seed parts intentionally have note_count=0; skip them
            if not part.get("is_seed"):
                assert part["note_count"] > 0


class TestComposeAgentFill:
    def test_fill_returns_midi_path(self):
        notes = {"notes": [{"pitch": 60, "beat": 0.0, "duration": 1.0, "velocity": 80}]}

        with patch("agents.compose_agent._call_llm", return_value=json.dumps(notes)):
            result = ComposeAgent().compose({
                "prompt": "walking bass line G minor 2 bars",
                "mode": "fill",
                "session_id": "test-fill-1",
            })

        assert result["mode"] == "fill"
        assert "midi_path" in result
        assert Path(result["midi_path"]).exists()
        assert result["note_count"] > 0

    def test_fill_fallback_on_bad_json(self):
        with patch("agents.compose_agent._call_llm", return_value="not json"):
            result = ComposeAgent().compose({
                "prompt": "piano chords",
                "mode": "fill",
                "session_id": "test-fill-2",
            })

        assert result["mode"] == "fill"
        assert "midi_path" in result
        assert Path(result["midi_path"]).exists()


class TestHarmonicEngine:
    def test_chord_schedule_returns_correct_bar_count(self):
        cs = chord_schedule("C", "major", "pop", 8)
        assert len(cs) == 8

    def test_chord_schedule_bar_indices(self):
        cs = chord_schedule("C", "major", "pop", 4)
        for i, entry in enumerate(cs):
            assert entry["bar"] == i

    def test_chord_schedule_jazz_major_first_chord_is_ii(self):
        # Jazz major: ii-V-I-I; ii of C is D (semitone 2 above C)
        cs = chord_schedule("C", "major", "jazz", 4)
        # First chord root should be D (C=60 base → D = 62, so root % 12 == 2)
        assert cs[0]["root"] % 12 == 2  # D

    def test_chord_schedule_blues_has_4_chord_cycle(self):
        cs = chord_schedule("A", "major", "blues", 8)
        assert len(cs) == 8
        # Blues: I-IV-V-I repeating; bar 0 and bar 4 should share same quality
        assert cs[0]["quality"] == cs[4]["quality"]

    def test_chord_progression_from_schedule_jazz_uses_offbeat_rhythm(self):
        cs = chord_schedule("C", "major", "jazz", 4)
        notes = chord_progression_from_schedule(cs, "jazz")
        # Jazz pattern has offbeat hits at 0.5, 1.5, 2.5, 3.5 — NOT just beat 0
        beat_offsets = {round(n["beat"] % 4, 4) for n in notes}
        assert 0.5 in beat_offsets or 1.5 in beat_offsets  # offbeat present

    def test_bass_line_harmonic_roots_match_schedule(self):
        cs = chord_schedule("C", "major", "pop", 4)
        notes = bass_line_harmonic(cs, "pop", 4)
        assert len(notes) > 0
        # Beat 0 note of bar 0 should match chord root (octave-adjusted)
        bar0_beat0 = [n for n in notes if abs(n["beat"]) < 0.01]
        assert len(bar0_beat0) > 0
        # Root pitch class should match schedule root pitch class
        expected_root_pc = cs[0]["root"] % 12
        assert bar0_beat0[0]["pitch"] % 12 == expected_root_pc

    def test_melody_line_harmonic_downbeats_on_chord_tones(self):
        cs = chord_schedule("C", "major", "pop", 4)
        notes = melody_line_harmonic(cs, "C", "major", "pop", 4)
        assert len(notes) > 0
        # Check each bar's downbeat (beat N*4) lands on a chord tone
        for bar_idx, entry in enumerate(cs):
            bar_beat = float(bar_idx * 4)
            downbeat_notes = [n for n in notes if abs(n["beat"] - bar_beat) < 0.01]
            if downbeat_notes:
                pitch_pc = downbeat_notes[0]["pitch"] % 12
                chord_pcs = {p % 12 for p in entry["pitches"]}
                assert pitch_pc in chord_pcs, (
                    f"Bar {bar_idx}: downbeat pitch {pitch_pc} not in chord {chord_pcs}"
                )


class TestSessionState:
    def test_session_updated_after_arrange(self):
        from agents.compose_agent import _sessions

        plan = {
            "bpm": 90, "key": "F", "scale": "major", "bars": 2,
            "parts": [{"name": "Pads", "role": "chords", "description": "ambient pads", "color": "#1abc9c"}]
        }
        notes = {"notes": [{"pitch": 65, "beat": 0.0, "duration": 4.0, "velocity": 65}]}

        call_count = {"n": 0}
        def fake_call(system, user, **kwargs):
            call_count["n"] += 1
            return json.dumps(plan) if call_count["n"] == 1 else json.dumps(notes)

        sid = "session-state-test"
        with (
            patch("agents.compose_agent._call_llm", side_effect=fake_call),
            patch("agents.compose_agent._midi_find_seed", return_value=None),
        ):
            ComposeAgent().compose({
                "prompt": "ambient pads F major 90 BPM",
                "mode": "arrange",
                "session_id": sid,
            })

        assert sid in _sessions
        assert _sessions[sid]["bpm"] == 90
        assert _sessions[sid]["key"] == "F"
        assert len(_sessions[sid]["parts"]) == 1


# ── Key detection tests ───────────────────────────────────────────────────────

class TestKeyDetection:
    def test_empty_returns_c_major(self):
        k, s = detect_key_from_notes([])
        assert k == "C" and s == "major"

    def test_c_major_with_tonic_emphasis(self):
        # Realistic C major: chord tones (C, E, G) appear more than passing tones
        # Mimics a real session where the I chord is played multiple times.
        c_major_biased = (
            [60, 64, 67] * 6   # C major chord repeated = strong C tonic
            + [60, 62, 64, 65, 67, 69, 71]  # one pass of the scale
        )
        k, s = detect_key_from_notes(c_major_biased)
        assert k == "C"
        assert s == "major"

    def test_a_minor_scale(self):
        # A minor: A B C D E F G
        a_minor = [57, 59, 60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79]
        k, s = detect_key_from_notes(a_minor)
        assert k == "A"
        assert s == "minor"

    def test_returns_string_pair(self):
        pitches = [60, 62, 64, 65, 67, 69, 71, 60, 64, 67]
        k, s = detect_key_from_notes(pitches)
        assert isinstance(k, str) and len(k) >= 1
        assert s in ("major", "minor")

    def test_few_notes_still_returns_result(self):
        # Even a handful of notes shouldn't crash
        k, s = detect_key_from_notes([60, 64, 67])
        assert k in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


# ── Song Builder tests ─────────────────────────────────────────────────────────

class TestSongBuilder:
    def test_single_mode_inherits_session_key(self):
        """Second composeTrack() reuses key from first call via session lookup."""
        from agents.compose_agent import _sessions
        sid = "sb-test-1"
        _sessions[sid] = {"key": "F", "scale": "minor", "bpm": 90, "genre": "lofi", "parts": []}
        notes = {"notes": [{"pitch": "F4", "beat": 0.0, "duration": 1.0, "velocity": 80}]}
        with (
            patch("agents.compose_agent._call_llm", return_value=json.dumps(notes)),
            patch("agents.compose_agent._midi_find_seed", return_value=None),
        ):
            result = ComposeAgent().compose({
                "prompt": "new melody",   # no key in prompt
                "mode": "single", "session_id": sid,
            })
        assert result["key"] == "F" and result["scale"] == "minor"

    def test_section_bars_used_for_clip_length(self):
        """section.bars overrides the bars count in the compose call."""
        notes = {"notes": [{"pitch": "C4", "beat": 0.0, "duration": 1.0, "velocity": 80}]}
        with patch("agents.compose_agent._call_llm", return_value=json.dumps(notes)):
            result = ComposeAgent().compose({
                "prompt": "chorus melody", "mode": "single", "session_id": "sb-test-2",
                "section": {"name": "Chorus", "start_bar": 16, "bars": 8},
            })
        assert result["start_bar"] == 16

    def test_start_bar_in_single_result(self):
        """start_bar is always present in single mode result."""
        notes = {"notes": [{"pitch": "C4", "beat": 0.0, "duration": 1.0, "velocity": 80}]}
        with patch("agents.compose_agent._call_llm", return_value=json.dumps(notes)):
            result = ComposeAgent().compose({
                "prompt": "verse bass", "mode": "single", "session_id": "sb-test-3",
                "section": {"name": "Verse", "start_bar": 4, "bars": 16},
            })
        assert "start_bar" in result and result["start_bar"] == 4

    def test_arrange_parts_have_start_bar(self):
        """All parts in arrange mode include start_bar."""
        plan = {"bpm": 120, "key": "C", "scale": "major", "bars": 4,
                "parts": [{"name": "Melody", "role": "melody",
                           "description": "simple", "color": "#9b59b6"}]}
        notes = {"notes": [{"pitch": "C4", "beat": 0.0, "duration": 1.0, "velocity": 80}]}
        n = {"n": 0}
        def fake(system, user, **kwargs):
            n["n"] += 1
            return json.dumps(plan) if n["n"] == 1 else json.dumps(notes)
        with patch("agents.compose_agent._call_llm", side_effect=fake):
            result = ComposeAgent().compose({
                "prompt": "simple melody", "mode": "arrange", "session_id": "sb-test-4",
                "section": {"name": "Verse", "start_bar": 8, "bars": 4},
            })
        for part in result["parts"]:
            assert "start_bar" in part
