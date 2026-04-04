"""
Tests for chat widget RPC handlers:
  - _set_session_context  (A5)
  - _chord_suggestions    (A2)
  - _beat_builder         (A3)
  - _regenerate_bar       (A1, delegates to ComposeAgent)
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make wavy-ai root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Stubs ─────────────────────────────────────────────────────────────────────

class _MockConfig:
    GENERATION_DIR = Path(__file__).parent / "tmp_widgets"
    ANTHROPIC_API_KEY = ""
    GROQ_API_KEY = ""

_MockConfig.GENERATION_DIR.mkdir(exist_ok=True)

config_stub = types.ModuleType("config")
config_stub.GENERATION_DIR = _MockConfig.GENERATION_DIR
config_stub.ANTHROPIC_API_KEY = ""
config_stub.GROQ_API_KEY = ""
sys.modules.setdefault("config", config_stub)

loguru_stub = types.ModuleType("loguru")
loguru_stub.logger = MagicMock()
sys.modules.setdefault("loguru", loguru_stub)

# Stub cloud.router so tests don't need network
cloud_pkg = types.ModuleType("cloud")
cloud_router = types.ModuleType("cloud.router")
cloud_router.get_command_provider = lambda: None
sys.modules.setdefault("cloud", cloud_pkg)
sys.modules.setdefault("cloud.router", cloud_router)


# ── Import the handlers under test ────────────────────────────────────────────

import rpc_handlers as _rh

# Clear global context before each test so tests don't bleed into each other
@pytest.fixture(autouse=True)
def _reset_context():
    _rh._global_context.clear()
    yield
    _rh._global_context.clear()


# ── SessionContext tests (A5) ─────────────────────────────────────────────────

class TestSetSessionContext:
    def _call(self, **kw):
        return _rh._set_session_context(kw, None)

    def test_set_key_bpm(self):
        result = self._call(key="D", bpm=140)
        ctx = result["context"]
        assert ctx["key"] == "D"
        assert ctx["bpm"] == 140

    def test_set_partial_update(self):
        self._call(key="A", scale="minor")
        result = self._call(bpm=90)
        ctx = result["context"]
        assert ctx["key"] == "A"
        assert ctx["scale"] == "minor"
        assert ctx["bpm"] == 90

    def test_clear_key_with_none(self):
        self._call(key="F")
        result = self._call(key=None)
        assert "key" not in result["context"]

    def test_returns_context(self):
        result = self._call(key="G", scale="major", bpm=120)
        assert "context" in result
        assert result["context"]["key"] == "G"


# ── ChordSuggestions tests (A2) ───────────────────────────────────────────────

class TestChordSuggestions:
    def _call(self, **kw):
        return _rh._chord_suggestions(kw, None)

    def test_returns_chords_list(self):
        result = self._call(prompt="jazz in C", key="C", scale="major", num_chords=4)
        assert "chords" in result
        assert len(result["chords"]) == 4

    def test_each_chord_has_notes(self):
        result = self._call(key="A", scale="minor", num_chords=4)
        for chord in result["chords"]:
            assert "notes" in chord
            assert len(chord["notes"]) >= 3  # triad minimum

    def test_each_chord_has_name(self):
        result = self._call(key="C", scale="major")
        for chord in result["chords"]:
            assert chord.get("name")
            assert chord.get("root")
            assert chord.get("quality")

    def test_widget_field(self):
        result = self._call(key="F", scale="minor")
        assert result.get("widget") == "chords"

    def test_inherits_global_context(self):
        _rh._global_context["key"] = "Bb"
        _rh._global_context["scale"] = "minor"
        result = self._call(num_chords=4)
        assert result["key"] == "Bb"
        assert result["scale"] == "minor"

    def test_num_chords_respected(self):
        for n in (2, 4):
            result = self._call(key="C", scale="major", num_chords=n)
            assert len(result["chords"]) == n

    def test_notes_are_midi_pitches(self):
        result = self._call(key="C", scale="major")
        for chord in result["chords"]:
            for pitch in chord["notes"]:
                assert 0 <= pitch <= 127


# ── BeatBuilder tests (A3) ────────────────────────────────────────────────────

class TestBeatBuilder:
    def _call(self, **kw):
        return _rh._beat_builder(kw, None)

    def test_returns_rows(self):
        result = self._call(prompt="trap beat", bpm=140)
        assert "rows" in result
        assert len(result["rows"]) >= 3  # at least Kick/Snare/Hat

    def test_each_row_has_16_steps(self):
        result = self._call(genre="trap")
        for row in result["rows"]:
            assert "steps" in row
            assert len(row["steps"]) == 16

    def test_each_row_has_name_and_color(self):
        result = self._call(genre="house")
        for row in result["rows"]:
            assert row.get("name")
            assert row.get("color", "").startswith("#")

    def test_steps_are_booleans(self):
        result = self._call(genre="lofi")
        for row in result["rows"]:
            for step in row["steps"]:
                assert isinstance(step, bool)

    def test_widget_field(self):
        result = self._call(prompt="trap beat 140 BPM")
        assert result.get("widget") == "beat_grid"

    def test_bpm_returned(self):
        result = self._call(bpm=130, genre="trap")
        assert result["bpm"] == 130

    def test_genre_detection_from_prompt(self):
        result = self._call(prompt="lo-fi chill beat 80 BPM", bpm=80)
        assert result.get("genre") in ("lo-fi", "lofi", "generic")

    def test_inherits_bpm_from_context(self):
        _rh._global_context["bpm"] = 95
        result = self._call(prompt="chill beat")
        assert result["bpm"] == 95

    def test_genres(self):
        for genre in ("trap", "house", "lofi", "dnb", "generic"):
            result = self._call(genre=genre)
            assert "rows" in result


# ── RegenerateBar tests (A1) ──────────────────────────────────────────────────

class TestRegenerateBar:
    """Minimal smoke tests — full coverage is in test_compose_agent.py."""

    def test_returns_midi_path(self):
        result = _rh._regenerate_bar(
            {"session_id": "test-session", "part_name": "Melody",
             "bar_index": 0, "role": "melody", "key": "C", "scale": "major", "bpm": 120},
            None,
        )
        assert "midi_path" in result
        assert Path(result["midi_path"]).exists()

    def test_note_count_positive(self):
        result = _rh._regenerate_bar(
            {"session_id": "test-session", "part_name": "Bass",
             "bar_index": 1, "role": "bass", "key": "F", "scale": "minor", "bpm": 90},
            None,
        )
        assert result.get("note_count", 0) > 0

    def test_bar_index_echo(self):
        result = _rh._regenerate_bar(
            {"session_id": "test-session", "part_name": "Chords",
             "bar_index": 2, "role": "chords", "key": "G", "scale": "major", "bpm": 100},
            None,
        )
        assert result.get("bar_index") == 2

    def test_note_summary_grouped_by_bar(self):
        result = _rh._regenerate_bar(
            {"session_id": "test-session", "part_name": "Melody",
             "bar_index": 0, "role": "melody", "key": "A", "scale": "minor", "bpm": 120},
            None,
        )
        assert "note_summary" in result
