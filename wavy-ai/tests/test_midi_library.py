"""
Tests for utils/midi_library.py — BitMidi seed MIDI downloader/analyzer.
All network calls are mocked; real mido objects are used for MIDI generation.
"""

from __future__ import annotations

import io
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import mido

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Stubs (only if not already registered — conftest.py may have pre-loaded real config) ──
_TMP = Path(tempfile.mkdtemp())

if "loguru" not in sys.modules:
    loguru_stub = types.ModuleType("loguru")
    loguru_stub.logger = MagicMock()
    sys.modules["loguru"] = loguru_stub

# Now import the module under test; it will use whatever config is in sys.modules
from utils.midi_library import (
    genre_to_query,
    _BitMidiSearchParser,
    _BitMidiDownloadParser,
    search_bitmidi,
    download_midi,
    analyze_midi,
    trim_midi_to_bars,
    find_seed,
)
import utils.midi_library as _midi_lib_mod

# Reference to the config that midi_library actually uses
_ml_config = _midi_lib_mod.config


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_midi_bytes(bpm: int = 120, pitches: list[int] | None = None,
                     ticks_per_beat: int = 480) -> bytes:
    """Build a minimal valid MIDI file in memory and return its bytes."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    if pitches is None:
        pitches = [60, 64, 67]  # C major chord
    for i, p in enumerate(pitches):
        track.append(mido.Message("note_on",  note=p, velocity=80, channel=0, time=i * 480))
        track.append(mido.Message("note_off", note=p, velocity=0,  channel=0, time=240))
    track.append(mido.MetaMessage("end_of_track", time=0))
    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()


def _save_midi_file(path: Path, bpm: int = 120,
                    pitches: list[int] | None = None) -> Path:
    """Write a minimal MIDI file to disk and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_midi_bytes(bpm=bpm, pitches=pitches))
    return path


# ── TestGenreToQuery ──────────────────────────────────────────────────────────

class TestGenreToQuery:
    def test_trap(self):
        # Fallback is now artist-based: "timbaland"
        q = genre_to_query("trap")
        assert "timbaland" in q.lower()

    def test_lofi(self):
        # Fallback is now artist-based: "nujabes"
        q = genre_to_query("lofi")
        assert "nujabes" in q.lower()

    def test_house(self):
        # Fallback is now artist-based: "daft punk"
        q = genre_to_query("house")
        assert "daft" in q.lower() or "punk" in q.lower()

    def test_jazz(self):
        # Fallback is now artist-based: "miles davis"
        q = genre_to_query("jazz")
        assert "miles" in q.lower() or "davis" in q.lower()

    def test_ambient(self):
        # Fallback is now artist-based: "brian eno"
        q = genre_to_query("ambient")
        assert "brian" in q.lower() or "eno" in q.lower()

    def test_dnb(self):
        # Fallback is now artist-based: "goldie"
        q = genre_to_query("dnb")
        assert "goldie" in q.lower()

    def test_default(self):
        q = genre_to_query("default")
        assert isinstance(q, str) and len(q) > 0

    def test_rnb_genre(self):
        # Fallback is now artist-based: "marvin gaye"
        q = genre_to_query("rnb")
        assert "marvin" in q.lower() or "gaye" in q.lower()

    def test_unknown_genre_returns_default(self):
        q = genre_to_query("polka")
        # Should return something (the default artist query)
        assert isinstance(q, str) and len(q) > 0

    def test_prompt_keywords_override_genre_query(self):
        # Prompt keywords should be used instead of artist fallback
        q = genre_to_query("lofi", prompt="r&b smooth bass funk groove")
        # Should contain words from the prompt, not artist fallback
        assert "r&b" in q.lower() or "bass" in q.lower() or "funk" in q.lower()

    def test_prompt_strips_bpm_bars_key(self):
        # BPM/bars/key info should be stripped from query
        q = genre_to_query("rnb", prompt="R&B smooth bass, G minor, 80 BPM, 4 bars")
        assert "bpm" not in q.lower()
        assert "bars" not in q.lower()
        assert "minor" not in q.lower()

    def test_empty_prompt_uses_genre_fallback(self):
        # Empty prompt → artist-based fallback for jazz: "miles davis"
        q = genre_to_query("jazz", prompt="")
        assert "miles" in q.lower() or "davis" in q.lower()


# ── TestSearchParser ──────────────────────────────────────────────────────────

class TestSearchParser:
    _SAMPLE_HTML = """
    <html><body>
      <a href="/bohemian-rhapsody-mid">Bohemian Rhapsody</a>
      <a href="/jazzy-piano-mid">Jazzy Piano</a>
      <a href="https://example.com/other">External</a>
      <a href="/not-matching">No suffix</a>
      <a href="/one/two-mid">Two slashes — skip</a>
    </body></html>
    """

    def test_finds_two_results(self):
        p = _BitMidiSearchParser()
        p.feed(self._SAMPLE_HTML)
        assert len(p.results) == 2

    def test_slug_stripped(self):
        p = _BitMidiSearchParser()
        p.feed(self._SAMPLE_HTML)
        slugs = [r["slug"] for r in p.results]
        assert "bohemian-rhapsody-mid" in slugs
        assert "jazzy-piano-mid" in slugs

    def test_title_extracted(self):
        p = _BitMidiSearchParser()
        p.feed(self._SAMPLE_HTML)
        titles = [r["title"] for r in p.results]
        assert "Bohemian Rhapsody" in titles
        assert "Jazzy Piano" in titles

    def test_empty_html(self):
        p = _BitMidiSearchParser()
        p.feed("<html></html>")
        assert p.results == []

    def test_no_mid_suffix_ignored(self):
        p = _BitMidiSearchParser()
        p.feed('<a href="/some-song">No suffix</a>')
        assert p.results == []


# ── TestDownloadParser ────────────────────────────────────────────────────────

class TestDownloadParser:
    def test_finds_href_upload(self):
        html = '<a href="/uploads/12345.mid">Download</a>'
        p = _BitMidiDownloadParser()
        p.feed(html)
        assert p.download_url == "/uploads/12345.mid"

    def test_finds_src_attribute(self):
        html = '<source src="/uploads/67890.mid" type="audio/midi">'
        p = _BitMidiDownloadParser()
        p.feed(html)
        assert p.download_url == "/uploads/67890.mid"

    def test_empty_page(self):
        p = _BitMidiDownloadParser()
        p.feed("<html></html>")
        assert p.download_url == ""

    def test_non_midi_link_ignored(self):
        html = '<a href="/uploads/67890.mp3">MP3</a>'
        p = _BitMidiDownloadParser()
        p.feed(html)
        assert p.download_url == ""

    def test_stops_after_first_match(self):
        html = (
            '<a href="/uploads/1.mid">First</a>'
            '<a href="/uploads/2.mid">Second</a>'
        )
        p = _BitMidiDownloadParser()
        p.feed(html)
        assert p.download_url == "/uploads/1.mid"


# ── TestSearchBitmidi ─────────────────────────────────────────────────────────

class TestSearchBitmidi:
    def _mock_response(self, html: str):
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        return resp

    def test_returns_results_on_success(self):
        html = '<a href="/jazz-piano-mid">Jazz Piano</a>'
        with patch("utils.midi_library.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response(html)
            results = search_bitmidi("jazz")
        assert len(results) == 1
        assert results[0]["slug"] == "jazz-piano-mid"

    def test_returns_empty_on_network_error(self):
        with patch("utils.midi_library.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("timeout")
            results = search_bitmidi("jazz")
        assert results == []

    def test_limit_respected(self):
        links = "".join(
            f'<a href="/song-{i}-mid">Song {i}</a>' for i in range(10)
        )
        html = f"<html>{links}</html>"
        with patch("utils.midi_library.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response(html)
            results = search_bitmidi("jazz", limit=3)
        assert len(results) == 3

    def test_returns_empty_on_parse_failure(self):
        with patch("utils.midi_library.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response("")
            results = search_bitmidi("trap")
        assert results == []


# ── TestDownloadMidi ──────────────────────────────────────────────────────────

class TestDownloadMidi:
    def _mock_get(self, page_html: str, midi_bytes: bytes):
        """Return a side_effect callable for httpx.get that serves page then MIDI."""
        responses = iter([
            self._make_resp(text=page_html),
            self._make_resp(content=midi_bytes),
        ])
        return lambda *a, **kw: next(responses)

    @staticmethod
    def _make_resp(text: str = "", content: bytes = b""):
        resp = MagicMock()
        resp.text    = text
        resp.content = content
        resp.raise_for_status = MagicMock()
        return resp

    def test_downloads_and_caches(self, tmp_path):
        midi_lib_dir = tmp_path / "midi_lib"
        midi_lib_dir.mkdir()
        midi_bytes = _make_midi_bytes()
        page_html  = '<a href="/uploads/1234.mid">Download</a>'
        with (
            patch.object(_ml_config, "MIDI_LIBRARY_DIR", midi_lib_dir),
            patch("utils.midi_library.httpx") as mock_httpx,
        ):
            mock_httpx.get.side_effect = self._mock_get(page_html, midi_bytes)
            result = download_midi("some-song-mid", "Some Song")
        assert result is not None
        assert result.exists()
        assert result.read_bytes()[:4] == b"MThd"

    def test_cache_hit_skips_download(self, tmp_path):
        midi_lib_dir = tmp_path / "midi_lib"
        midi_lib_dir.mkdir()
        # Pre-create cached file
        slug      = "cached-song-mid"
        cache_path = midi_lib_dir / f"{slug}.mid"
        cache_path.write_bytes(_make_midi_bytes())
        with (
            patch.object(_ml_config, "MIDI_LIBRARY_DIR", midi_lib_dir),
            patch("utils.midi_library.httpx") as mock_httpx,
        ):
            result = download_midi(slug, "Cached Song")
            mock_httpx.get.assert_not_called()
        assert result == cache_path

    def test_returns_none_on_network_error(self, tmp_path):
        midi_lib_dir = tmp_path / "midi_lib"
        midi_lib_dir.mkdir()
        with (
            patch.object(_ml_config, "MIDI_LIBRARY_DIR", midi_lib_dir),
            patch("utils.midi_library.httpx") as mock_httpx,
        ):
            mock_httpx.get.side_effect = Exception("timeout")
            result = download_midi("error-slug-mid", "Error Song")
        assert result is None

    def test_returns_none_when_no_download_url(self, tmp_path):
        midi_lib_dir = tmp_path / "midi_lib"
        midi_lib_dir.mkdir()
        page_html = "<html>No download link here</html>"
        with (
            patch.object(_ml_config, "MIDI_LIBRARY_DIR", midi_lib_dir),
            patch("utils.midi_library.httpx") as mock_httpx,
        ):
            mock_httpx.get.return_value = self._make_resp(text=page_html)
            result = download_midi("no-link-mid", "No Link")
        assert result is None

    def test_returns_none_on_invalid_midi(self, tmp_path):
        midi_lib_dir = tmp_path / "midi_lib"
        midi_lib_dir.mkdir()
        page_html  = '<a href="/uploads/bad.mid">Download</a>'
        bad_bytes  = b"NOTMIDI_CONTENT"
        with (
            patch.object(_ml_config, "MIDI_LIBRARY_DIR", midi_lib_dir),
            patch("utils.midi_library.httpx") as mock_httpx,
        ):
            mock_httpx.get.side_effect = self._mock_get(page_html, bad_bytes)
            result = download_midi("bad-song-mid", "Bad Song")
        assert result is None


# ── TestAnalyzeMidi ───────────────────────────────────────────────────────────

class TestAnalyzeMidi:
    def test_detects_bpm(self, tmp_path):
        path = _save_midi_file(tmp_path / "bpm_test.mid", bpm=140)
        info = analyze_midi(path)
        # Allow small rounding differences
        assert abs(info["bpm"] - 140) <= 2

    def test_detects_pitches(self, tmp_path):
        pitches = [60, 64, 67, 69, 71]  # C major scale tones
        path = _save_midi_file(tmp_path / "pitch_test.mid", pitches=pitches)
        info = analyze_midi(path)
        assert len(info["pitches"]) > 0

    def test_detects_key(self, tmp_path):
        # C major chord tones across octaves
        pitches = [60, 64, 67] * 8  # C E G
        path = _save_midi_file(tmp_path / "key_test.mid", pitches=pitches)
        info = analyze_midi(path)
        assert info["key"] in ("C", "G", "F", "A", "E")  # plausible keys
        assert info["scale"] in ("major", "minor")

    def test_excludes_drum_channel(self, tmp_path):
        """Channel 9 notes should not contribute to pitch detection."""
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
        # Only drum channel 9 notes
        for i in range(8):
            track.append(mido.Message("note_on",  note=36, velocity=80, channel=9, time=480))
            track.append(mido.Message("note_off", note=36, velocity=0,  channel=9, time=240))
        track.append(mido.MetaMessage("end_of_track", time=0))
        path = tmp_path / "drums_only.mid"
        mid.save(str(path))
        info = analyze_midi(path)
        assert info["pitches"] == []

    def test_returns_defaults_on_bad_file(self, tmp_path):
        path = tmp_path / "garbage.mid"
        path.write_bytes(b"this is not a midi file at all")
        info = analyze_midi(path)
        assert info["bpm"] == 120
        assert info["key"] == "C"
        assert info["scale"] == "major"

    def test_default_bpm_when_no_tempo_event(self, tmp_path):
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message("note_on",  note=60, velocity=80, channel=0, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0,  channel=0, time=480))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        path = tmp_path / "no_tempo.mid"
        mid.save(str(path))
        info = analyze_midi(path)
        assert info["bpm"] == 120


# ── TestTrimMidi ──────────────────────────────────────────────────────────────

class TestTrimMidi:
    def _make_long_midi(self, tmp_path: Path, bars: int = 16, bpm: int = 120) -> Path:
        """Create a MIDI with 16 bars of notes."""
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
        for bar in range(bars):
            tick = bar * 480 * 4
            track.append(mido.Message("note_on",  note=60, velocity=80, channel=0, time=480 * 4 if bar > 0 else 0))
            track.append(mido.Message("note_off", note=60, velocity=0,  channel=0, time=240))
        track.append(mido.MetaMessage("end_of_track", time=0))
        path = tmp_path / "long.mid"
        mid.save(str(path))
        return path

    def test_trim_reduces_length(self, tmp_path):
        src = self._make_long_midi(tmp_path, bars=16)
        out = tmp_path / "trimmed.mid"
        trim_midi_to_bars(src, bars=4, bpm=120, output_path=out)
        assert out.exists()

    def test_output_is_valid_midi(self, tmp_path):
        src = self._make_long_midi(tmp_path, bars=8)
        out = tmp_path / "valid_trim.mid"
        trim_midi_to_bars(src, bars=2, bpm=120, output_path=out)
        # Should load without exception
        trimmed = mido.MidiFile(str(out))
        assert len(trimmed.tracks) > 0

    def test_trim_shorter_than_source_keeps_notes(self, tmp_path):
        """When trimming to fewer bars, notes in those bars should be kept."""
        src = self._make_long_midi(tmp_path, bars=8)
        out = tmp_path / "keep_notes.mid"
        result = trim_midi_to_bars(src, bars=4, bpm=120, output_path=out)
        assert result == out
        trimmed = mido.MidiFile(str(out))
        note_ons = sum(
            1 for t in trimmed.tracks for m in t if m.type == "note_on"
        )
        assert note_ons > 0

    def test_fallback_copies_on_bad_input(self, tmp_path):
        src = tmp_path / "bad.mid"
        src.write_bytes(b"NOT A MIDI")
        out = tmp_path / "fallback.mid"
        result = trim_midi_to_bars(src, bars=4, bpm=120, output_path=out)
        assert result == out
        assert out.exists()

    def test_returns_output_path(self, tmp_path):
        src = self._make_long_midi(tmp_path, bars=4)
        out = tmp_path / "returned.mid"
        result = trim_midi_to_bars(src, bars=2, bpm=120, output_path=out)
        assert result == out


# ── TestFindSeed ──────────────────────────────────────────────────────────────

class TestFindSeed:
    def _mock_search(self, results: list[dict]):
        return patch("utils.midi_library.search_bitmidi", return_value=results)

    def _mock_download(self, path: Path | None):
        return patch("utils.midi_library.download_midi", return_value=path)

    def _mock_analyze(self, info: dict):
        return patch("utils.midi_library.analyze_midi", return_value=info)

    def _mock_trim(self, path: Path):
        return patch("utils.midi_library.trim_midi_to_bars", return_value=path)

    def test_returns_seed_on_success(self, tmp_path):
        midi_path = _save_midi_file(tmp_path / "seed.mid", pitches=[60, 64, 67])
        trimmed   = tmp_path / "trimmed_seed.mid"
        trimmed.write_bytes(midi_path.read_bytes())

        with (
            self._mock_search([{"slug": "jazz-piano-mid", "title": "Jazz Piano"}]),
            self._mock_download(midi_path),
            self._mock_analyze({"pitches": [60, 64, 67], "key": "C", "scale": "major", "bpm": 120,
                                 "total_ticks": 1920, "ticks_per_beat": 480, "track_count": 1}),
            self._mock_trim(trimmed),
        ):
            result = find_seed("jazz", bars=4, bpm=120)

        assert result is not None
        assert result["key"] == "C"
        assert result["scale"] == "major"
        assert result["title"] == "Jazz Piano"
        assert "midi_path" in result

    def test_returns_none_when_no_search_results(self):
        with self._mock_search([]):
            result = find_seed("jazz", bars=4, bpm=120)
        assert result is None

    def test_skips_drums_only_candidate(self, tmp_path):
        midi_path = _save_midi_file(tmp_path / "drums.mid")
        with (
            self._mock_search([{"slug": "drums-mid", "title": "Drums Only"}]),
            self._mock_download(midi_path),
            self._mock_analyze({"pitches": [], "key": "C", "scale": "major", "bpm": 120,
                                 "total_ticks": 1920, "ticks_per_beat": 480, "track_count": 1}),
        ):
            result = find_seed("trap", bars=4, bpm=120)
        assert result is None

    def test_tries_next_candidate_on_download_failure(self, tmp_path):
        midi_path = _save_midi_file(tmp_path / "second.mid", pitches=[60, 64, 67])
        trimmed   = tmp_path / "trimmed_second.mid"
        trimmed.write_bytes(midi_path.read_bytes())

        candidates = [
            {"slug": "fail-mid",  "title": "Will Fail"},
            {"slug": "ok-mid",    "title": "Will Succeed"},
        ]
        download_side_effects = [None, midi_path]  # first fails, second succeeds

        with (
            self._mock_search(candidates),
            patch("utils.midi_library.download_midi", side_effect=download_side_effects),
            self._mock_analyze({"pitches": [60, 64, 67], "key": "C", "scale": "major", "bpm": 90,
                                 "total_ticks": 1920, "ticks_per_beat": 480, "track_count": 1}),
            self._mock_trim(trimmed),
        ):
            result = find_seed("lofi", bars=4, bpm=90)

        assert result is not None
        assert result["title"] == "Will Succeed"

    def test_returns_none_when_all_candidates_fail_and_no_cache(self, tmp_path):
        candidates = [{"slug": f"fail-{i}-mid", "title": f"Fail {i}"} for i in range(3)]
        # Also mock the cache fallback to return None (empty cache scenario)
        with (
            self._mock_search(candidates),
            patch("utils.midi_library.download_midi", return_value=None),
            patch("utils.midi_library._find_midi_for_role_from_cache", return_value=None),
        ):
            result = find_seed("house", bars=4, bpm=128)
        assert result is None

    def test_bpm_from_analyzed_file(self, tmp_path):
        midi_path = _save_midi_file(tmp_path / "bpm90.mid", bpm=90, pitches=[60, 64, 67])
        trimmed   = tmp_path / "trimmed_bpm90.mid"
        trimmed.write_bytes(midi_path.read_bytes())

        with (
            self._mock_search([{"slug": "bpm90-mid", "title": "BPM 90 Track"}]),
            self._mock_download(midi_path),
            self._mock_analyze({"pitches": [60, 64, 67], "key": "F", "scale": "minor", "bpm": 90,
                                 "total_ticks": 1920, "ticks_per_beat": 480, "track_count": 1}),
            self._mock_trim(trimmed),
        ):
            result = find_seed("lofi", bars=4, bpm=90)

        assert result is not None
        assert result["bpm"] == 90
        assert result["key"] == "F"
        assert result["scale"] == "minor"


# ── TestComposeWithBitMidi ────────────────────────────────────────────────────

class TestComposeWithSeed:
    """Integration-style tests: verify BitMidi pipeline is wired into ComposeAgent."""

    def setup_method(self):
        import importlib
        import agents.compose_agent as _ca
        importlib.reload(_ca)
        self.agent = _ca.ComposeAgent()
        self._sessions = _ca._sessions
        self._sessions.clear()

    def _bitmidi_result(self, role: str = "bass") -> dict:
        """Return a fake find_midi_for_role result dict with a real MIDI file."""
        midi_path = _ml_config.GENERATION_DIR / f"bitmidi_{role}_test.mid"
        src_path  = _ml_config.GENERATION_DIR / "bitmidi_source_test.mid"
        _save_midi_file(midi_path, pitches=[60, 64, 67])
        _save_midi_file(src_path,  pitches=[60, 64, 67])
        return {
            "title":       "Test Jazz Piano",
            "midi_path":   str(midi_path),
            "source_midi": str(src_path),
            "key":         "F",
            "scale":       "minor",
            "bpm":         85,
            "note_count":  3,
        }

    def test_arrange_all_parts_have_notes(self):
        """All arrange parts should have note_count > 0 (no is_seed placeholders)."""
        with (
            patch("agents.compose_agent._get_role_midi", return_value=None),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({
                "prompt": "lofi jazz study beats",
                "mode":   "arrange",
            })
        assert result["mode"] == "arrange"
        # No is_seed parts in new BitMidi pipeline
        seed_parts = [p for p in result["parts"] if p.get("is_seed")]
        assert len(seed_parts) == 0
        for part in result["parts"]:
            assert part["note_count"] > 0
            assert Path(part["midi_path"]).exists()

    def test_arrange_key_from_prompt(self):
        """Key/scale should come from prompt or LLM plan, not from BitMidi seed."""
        with (
            patch("agents.compose_agent._get_role_midi", return_value=None),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({
                "prompt": "G minor lofi 80 BPM",
                "mode":   "arrange",
            })
        # key comes from default (LLM returned empty → defaults) not from BitMidi
        assert isinstance(result["key"], str) and len(result["key"]) >= 1
        assert result["scale"] in ("major", "minor")

    def test_arrange_explanation_lists_parts(self):
        """Explanation should list track names, no 'Seeded from' prefix."""
        with (
            patch("agents.compose_agent._get_role_midi", return_value=None),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({
                "prompt": "lofi jazz",
                "mode":   "arrange",
            })
        assert "Created" in result["explanation"]
        assert "Seeded from" not in result["explanation"]

    def test_arrange_no_seed_parts(self):
        """No is_seed parts regardless of BitMidi result."""
        with (
            patch("agents.compose_agent._get_role_midi", return_value=None),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({"prompt": "lofi jazz", "mode": "arrange"})
        seed_parts = [p for p in result["parts"] if p.get("is_seed")]
        assert len(seed_parts) == 0
        assert "Seeded from" not in result["explanation"]

    def test_arrange_bitmidi_result_used_for_bass(self):
        """When _get_role_midi returns a result, that MIDI is used for bass/melody."""
        bm = self._bitmidi_result("bass")
        with (
            patch("agents.compose_agent._get_role_midi", return_value=bm),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({
                "prompt": "lofi jazz 4 bars",
                "mode":   "arrange",
            })
        # All non-drum pitched parts should reference the BitMidi path
        pitched_parts = [p for p in result["parts"] if p["role"] not in ("drums",)]
        bitmidi_parts = [p for p in pitched_parts if p["midi_path"] == bm["midi_path"]]
        assert len(bitmidi_parts) > 0

    def test_session_source_midi_stored_after_bitmidi(self):
        """First successful _get_role_midi call stores source_midi in session."""
        bm = self._bitmidi_result("melody")
        with (
            patch("agents.compose_agent._midi_find_role", return_value=bm),
            patch("agents.compose_agent._call_llm", return_value=""),
        ):
            result = self.agent.compose({
                "prompt": "bright melody",
                "mode":   "single",
                "role":   "melody",
            })
        sid = result["session_id"]
        seed_info = self._sessions.get(sid, {}).get("seed_info", {})
        assert seed_info.get("source_midi") == bm["source_midi"]

    def test_single_mode_inherits_session_key(self):
        """Single mode inherits key/scale from existing session."""
        sid = "sb-bitmidi-1"
        import agents.compose_agent as _ca
        _ca._sessions[sid] = {"key": "F", "scale": "minor", "bpm": 85, "genre": "lofi", "parts": []}
        with patch("agents.compose_agent._get_role_midi", return_value=None):
            result = self.agent.compose({
                "prompt": "bright melody",
                "mode":   "single",
                "role":   "melody",
                "session_id": sid,
            })
        assert result["key"] == "F"
        assert result["scale"] == "minor"

    def test_single_mode_drums_never_calls_bitmidi(self):
        """Drums are always deterministic — _get_role_midi is never called."""
        call_count = [0]

        def mock_role_midi(*a, **kw):
            call_count[0] += 1
            return None

        with patch("agents.compose_agent._get_role_midi", side_effect=mock_role_midi):
            self.agent.compose({
                "prompt": "drum pattern",
                "mode":   "single",
                "role":   "drums",
            })

        assert call_count[0] == 0  # drums never call BitMidi
