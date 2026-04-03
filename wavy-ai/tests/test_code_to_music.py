"""
Tests for the Code-to-Music converter — DSL parsing, Python exec, CSV/JSON sonification.
No GPU required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.code_to_music import CodeToMusicModel, note_to_midi


# ── Unit: note_to_midi ────────────────────────────────────────────────────────

class TestNoteToMidi:
    def test_middle_c(self):
        assert note_to_midi("C4") == 60

    def test_a4_concert_pitch(self):
        assert note_to_midi("A4") == 69

    def test_sharp(self):
        assert note_to_midi("C#4") == 61

    def test_low_bass(self):
        assert note_to_midi("C2") == 36

    def test_high_note(self):
        assert note_to_midi("G7") == 103

    def test_no_octave_defaults_to_4(self):
        # Should not raise
        val = note_to_midi("C")
        assert 0 <= val <= 127


# ── Integration: DSL parsing ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ctm():
    return CodeToMusicModel()


class TestDSLConvert:
    def test_basic_dsl(self, ctm, tmp_path):
        code = """
tempo(120)
key("C major")
track("drums").pattern([1,0,1,0,1,0,1,0], bpm=120)
"""
        result = ctm.convert(code=code, mode="dsl")
        assert "midi_path" in result
        assert Path(result["midi_path"]).exists()
        assert len(result["track_defs"]) == 1
        assert result["track_defs"][0]["track"] == "drums"

    def test_melody_dsl(self, ctm):
        code = """
track("lead").melody(["C4","E4","G4","C5"], duration="quarter")
"""
        result = ctm.convert(code=code, mode="dsl")
        assert Path(result["midi_path"]).exists()

    def test_generate_call_returns_request(self, ctm):
        code = 'track("synth").generate("ambient pad")'
        result = ctm.convert(code=code, mode="dsl")
        assert len(result["generate_requests"]) == 1
        assert result["generate_requests"][0]["prompt"] == "ambient pad"

    def test_multi_track(self, ctm):
        code = """
track("drums").pattern([1,0,0,1,0,0,1,0])
track("bass").melody(["C2","G2"])
"""
        result = ctm.convert(code=code, mode="dsl")
        assert len(result["track_defs"]) == 2


class TestPythonConvert:
    def test_python_snippet(self, ctm):
        code = """
track("drums").pattern([1,0,0,1,0,0,1,0], bpm=140)
track("bass").melody(["C3","E3","G3"], duration="quarter")
"""
        result = ctm.convert(code=code, mode="python")
        assert Path(result["midi_path"]).exists()
        assert len(result["track_defs"]) == 2


class TestCSVConvert:
    def test_csv_sonification(self, ctm):
        csv_text = "pitch,velocity,duration\n60,80,0.5\n64,70,0.5\n67,90,0.5\n72,80,0.5\n"
        result = ctm.convert(csv_data=csv_text, mode="csv")
        assert Path(result["midi_path"]).exists()
        assert len(result["track_defs"]) == 1

    def test_csv_single_column(self, ctm):
        csv_text = "value\n10\n20\n30\n40\n50\n"
        result = ctm.convert(csv_data=csv_text, mode="csv")
        assert Path(result["midi_path"]).exists()

    def test_csv_empty_raises(self, ctm):
        with pytest.raises(ValueError, match="empty"):
            ctm.convert(csv_data="", mode="csv")


class TestJSONConvert:
    def test_json_array(self, ctm):
        import json
        data = json.dumps([10, 50, 30, 70, 20, 80, 40, 60])
        result = ctm.convert(json_data=data, mode="json_data")
        assert Path(result["midi_path"]).exists()

    def test_json_object(self, ctm):
        import json
        data = json.dumps({"a": 1, "b": 5, "c": 3, "d": 7})
        result = ctm.convert(json_data=data, mode="json_data")
        assert Path(result["midi_path"]).exists()
