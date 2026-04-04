"""Library / dataset browser RPC handlers."""
from __future__ import annotations

from pathlib import Path

import mido
from loguru import logger
from models.registry import ModelRegistry
import config
from rpc.helpers import _ensure_wav

def _get_bitmidi_inspirations(params: dict, registry: ModelRegistry) -> dict:
    """Fetch real BitMidi {title, slug} pairs for inspiration cards.

    params: {genre: str}
    returns: {items: [{title, slug}]}  — slug is used to download the exact file
    """
    from utils.midi_library import search_bitmidi
    genre = params.get("genre", "default")
    results = search_bitmidi(genre, limit=8)
    items = [{"title": r["title"], "slug": r["slug"]}
             for r in results if r.get("title") and r.get("slug")]
    return {"items": items}



def _database_tips(params: dict, registry: ModelRegistry) -> dict:
    """Return LLM workflow tips for a MIDI database.
    params: {db: str}
    returns: {tips: str, db: str}
    """
    db_name = params.get("db", "")

    _FALLBACK: dict[str, str] = {
        "MAESTRO":     "\u2022 Download from magenta.tensorflow.org \u2014 .mid + .wav pairs aligned to sample level.\n\u2022 Study velocity curves and phrasing: MAESTRO performances are never quantized.\n\u2022 Use as piano-roll reference: import a .mid, solo a section, adapt chord shapes.\n\u2022 Filter by year and composer via the bundled CSV for style-specific material.",
        "Groove MIDI": "\u2022 Load drum .mid files directly into LMMS Beat+Bassline \u2014 do NOT quantize them.\n\u2022 Groove\u2019s humanized timing is the whole point: it makes your drums feel live.\n\u2022 Filter by style (jazz, funk, rock) and BPM range using the companion CSV.\n\u2022 Layer a Groove pattern under your existing beat for an instant feel upgrade.",
        "Slakh2100":   "\u2022 Each song has clean per-instrument stems \u2014 grab just bass.mid or piano.mid.\n\u2022 Instruments follow GM numbering \u2014 pair with Sf2Player + GeneralUser_GS soundfont.\n\u2022 Use a stem as a harmonic skeleton, then compose your own melody on top.\n\u2022 2.1k multi-track songs \u00d7 10+ stems = massive variety for arrangement study.",
        "Lakh MIDI":   "\u2022 170k files = the broadest style coverage of any MIDI dataset.\n\u2022 Run it through Wavy\u2019s MIDI import to auto-assign instruments via SF2 player.\n\u2022 Transpose to your project key before importing (Wavy handles this via key_interval).\n\u2022 Pair with MidiCaps: find a Lakh file that matches a MidiCaps caption you like.",
        "MidiCaps":    "\u2022 Captions describe genre, mood, tempo, key \u2014 use them as a semantic search filter.\n\u2022 Download a matched MIDI and use it as a chord or melody starting point.\n\u2022 Bridge to text2midi: describe a style in natural language, find a real reference file.\n\u2022 Each caption is ~20 words \u2014 feed directly into your LLM prompt as style context.",
        "GiantMIDI":   "\u2022 10k+ transcribed from real recordings \u2014 includes rubato, dynamics, and expressive timing.\n\u2022 Import into piano roll and study the voicings for jazz, classical, or pop.\n\u2022 Filter by composer in the CSV; Chopin and Beethoven files are excellent for harmonic ideas.\n\u2022 Combine with MAESTRO for a broad real-performance piano corpus (20k+ files total).",
    }

    system = (
        "You are an expert music producer and music theorist helping a user of Wavy Labs AI DAW. "
        "Give practical, specific advice about integrating this MIDI dataset into a DAW production workflow. "
        "Format as exactly 4 bullet points starting with \u2022. Each bullet under 20 words. No preamble or title."
    )
    user = f"How do I use the {db_name} dataset in my music production workflow?"

    return {"tips": _FALLBACK.get(db_name, "Visit the dataset documentation for workflow tips."), "db": db_name}


# ── Library Dataset Browser ───────────────────────────────────────────────────

_BROWSER_CLASSES = {
    "MidiWorld":     "MidiWorldBrowser",
    "MidiCaps":      "MidiCapsBrowser",
    "MAESTRO":       "MaestroReader",
    "Groove MIDI":   "GrooveBrowser",
    "BitMidi":       "BitMidiBrowser",
    "Mutopia":       "MutopiaOrgBrowser",
    "VGMusic":       "VGMusicBrowser",
    "GigaMIDI":      "GigaMidiBrowser",
    "Piano-midi.de": "PianoMidiDeBrowser",
    # New producer-focused browsers
    "Discover MIDI":  "DiscoverMidiBrowser",
    "Freesound":      "FreesoundBrowser",
    "WaivOps Drums":  "WaivOpsBrowser",
    "HookTheory":     "HookTheoryBrowser",
    "ldrolez Chords": "LdrolezChordBrowser",
    "Jamendo":        "JamendoBrowser",
    "SoundCloud":     "SoundCloudBrowser",
}

# Default LMMS instrument plugin per database
# sf2player = GM soundfont playback (good for melodic MIDI)
# kicker    = drum machine (good for pure drum MIDI)
_DB_INSTRUMENTS: dict[str, str] = {
    "Groove MIDI": "sf2player-drums",
}

_GM_PROGRAM_NAMES: dict[int, str] = {
    0: "Piano", 1: "Bright Piano", 2: "E.Piano", 3: "Honky-Tonk",
    4: "E.Piano 1", 5: "E.Piano 2", 6: "Harpsichord", 7: "Clavinet",
    8: "Celesta", 9: "Glockenspiel", 16: "Organ", 17: "Perc.Organ",
    18: "Rock Organ", 19: "Church Organ", 24: "Nylon Gtr", 25: "Steel Gtr",
    26: "Jazz Gtr", 27: "Clean Gtr", 29: "Overdrive Gtr", 30: "Dist.Gtr",
    32: "Acoustic Bass", 33: "Finger Bass", 34: "Pick Bass", 35: "Fretless Bass",
    36: "Slap Bass", 38: "Synth Bass", 40: "Violin", 41: "Viola",
    42: "Cello", 48: "Strings", 50: "Synth Strings", 52: "Choir",
    53: "Voice", 56: "Trumpet", 57: "Trombone", 60: "French Horn",
    61: "Brass", 64: "Sax", 65: "Alto Sax", 66: "Tenor Sax",
    73: "Flute", 80: "Lead Synth", 88: "Pad", 128: "Drums",
}

_CHANNEL_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
]


def _get_browser_cls(name: str):
    from utils.midi_browser import (
        MidiWorldBrowser,
        MidiCapsBrowser, MaestroReader, GrooveBrowser,
        BitMidiBrowser, MutopiaOrgBrowser, VGMusicBrowser,
        GigaMidiBrowser, PianoMidiDeBrowser,
        DiscoverMidiBrowser, FreesoundBrowser, WaivOpsBrowser,
        HookTheoryBrowser, LdrolezChordBrowser,
        JamendoBrowser, SoundCloudBrowser,
    )
    return {
        "MidiWorldBrowser":   MidiWorldBrowser,
        "MidiCapsBrowser":    MidiCapsBrowser,
        "MaestroReader":      MaestroReader,
        "GrooveBrowser":      GrooveBrowser,
        "BitMidiBrowser":     BitMidiBrowser,
        "MutopiaOrgBrowser":  MutopiaOrgBrowser,
        "VGMusicBrowser":     VGMusicBrowser,
        "GigaMidiBrowser":    GigaMidiBrowser,
        "PianoMidiDeBrowser": PianoMidiDeBrowser,
        "DiscoverMidiBrowser": DiscoverMidiBrowser,
        "FreesoundBrowser":    FreesoundBrowser,
        "WaivOpsBrowser":      WaivOpsBrowser,
        "HookTheoryBrowser":   HookTheoryBrowser,
        "LdrolezChordBrowser": LdrolezChordBrowser,
        "JamendoBrowser":      JamendoBrowser,
        "SoundCloudBrowser":   SoundCloudBrowser,
    }.get(name)


def _browse_dataset(params: dict, registry: ModelRegistry) -> dict:
    """Browse a supported MIDI dataset with optional text search and pagination.

    params: {db, query, offset, limit}
    returns: {items: [item], total: int, has_more: bool}  — or {unsupported: True}
    """
    db     = params.get("db", "")
    query  = params.get("query", "")
    offset = int(params.get("offset", 0))
    limit  = int(params.get("limit", 20))
    cls_name = _BROWSER_CLASSES.get(db)
    if not cls_name:
        return {"items": [], "total": 0, "has_more": False, "unsupported": True}
    cls = _get_browser_cls(cls_name)
    if cls is None:
        return {"items": [], "total": 0, "has_more": False, "unsupported": True}
    return cls().search(query, offset, limit)

def _download_library_file(params: dict, registry: ModelRegistry) -> dict:
    """Download a single MIDI file from a supported dataset to local cache.

    params: {db, file_id, plugin?}
      plugin — optional LMMS plugin override sent from the browse item metadata.
               Falls back to _DB_INSTRUMENTS[db] then "sf2player".
    returns: {midi_path: str, instrument: str}  — or {error: str}
    """
    db      = params.get("db", "")
    file_id = params.get("file_id", "")
    plugin  = params.get("plugin", "")   # hint from browse item (_gm_to_plugin result)
    cls_name = _BROWSER_CLASSES.get(db)
    if not cls_name:
        return {"error": f"Download not supported for {db!r}"}
    if not file_id:
        return {"error": "file_id is required"}
    cls = _get_browser_cls(cls_name)
    if cls is None:
        return {"error": f"Browser class not found for {db!r}"}
    try:
        path = cls().download(file_id)

        # ── Route audio files (WAV/MP3) via add_audio_track action ───────────
        if Path(path).suffix.lower() in (".wav", ".mp3", ".flac"):
            # Convert MP3/FLAC → WAV so LMMS can decode without libmpg123
            final_path = _ensure_wav(path)
            return {"audio_path": str(final_path), "track_name": Path(final_path).stem}

        # ── Try per-channel split for richer GM MIDI (e.g. MidiCaps) ─────────
        try:
            from utils.midi_library import split_midi_by_channel
            from utils.midi_browser import _gm_to_plugin
            channels = split_midi_by_channel(path)
        except Exception as split_err:
            logger.warning(f"[download_library_file] channel split failed: {split_err}")
            channels = []

        if len(channels) >= 1:
            parts = []
            midi_bpm = channels[0].get("bpm", 0)
            for ch in channels:
                ch_num = ch["channel"]
                prog   = ch["program"]
                if ch_num == 9:
                    instr    = "kicker"
                    category = "drums"
                    ch_name  = "Drums"
                    color    = _CHANNEL_COLORS[0]
                else:
                    gm_info = _gm_to_plugin([prog])
                    # Use plugin hint only if it's a real selection (not sf2player stale default)
                    instr   = (plugin if plugin and plugin != "sf2player" else None) or gm_info["plugin"]
                    category = gm_info["category"]
                    ch_name = _GM_PROGRAM_NAMES.get(prog, f"Ch {ch_num + 1}")
                    color   = _CHANNEL_COLORS[ch_num % len(_CHANNEL_COLORS)]
                parts.append({
                    "name":       ch_name,
                    "midi_path":  ch["midi_path"],
                    "instrument": instr,
                    "category":   category,
                    "gm_program": prog,
                    "color":      color,
                    "bars":       ch["bars"],
                    "note_count": ch["note_count"],
                })
            result = {"parts": parts}
            if midi_bpm and midi_bpm > 0:
                result["bpm"] = midi_bpm
            return result

        # ── Single-track fallback (split failed entirely) ────────────────────
        _plugin_hint = plugin if plugin and plugin != "sf2player" else None
        instrument = _plugin_hint or _DB_INSTRUMENTS.get(db) or "tripleoscillator"
        _fallback_bpm = 0
        try:
            import mido as _mido, math as _math
            _mid = _mido.MidiFile(str(path))
            _tpb = _mid.ticks_per_beat or 480
            _max_tick = max((sum(msg.time for msg in t) for t in _mid.tracks), default=0)
            _bars = max(1, _math.ceil(_max_tick / _tpb / 4))
            for _t in _mid.tracks:
                for _m in _t:
                    if _m.type == "set_tempo":
                        _fallback_bpm = round(_mido.tempo2bpm(_m.tempo))
                        break
                if _fallback_bpm:
                    break
        except Exception:
            _bars = 8
        result = {"midi_path": str(path), "instrument": instrument, "bars": _bars}
        if _fallback_bpm > 0:
            result["bpm"] = _fallback_bpm
        return result

    except Exception as exc:
        logger.error(f"[download_library_file] {db}/{file_id}: {exc}")
        return {"error": str(exc)}


def _midicaps_library_status(params: dict, registry: ModelRegistry) -> dict:
    """Return the current MidiCaps archive download status.

    returns: {status, progress, files_extracted, bytes_downloaded, total_bytes, error}
    """
    from utils.midi_browser import MidiCapsBrowser
    return MidiCapsBrowser.get_status()


def _start_midicaps_download(params: dict, registry: ModelRegistry) -> dict:
    """Start the MidiCaps archive download in a background thread.

    returns: {status, progress, files_extracted, bytes_downloaded, total_bytes}
    """
    from utils.midi_browser import MidiCapsBrowser
    return MidiCapsBrowser.start_download()


# ── Database Connection Test ───────────────────────────────────────────────────

_TEST_DBS = [
    ("Groove MIDI",   "GrooveBrowser",      ""),
    ("BitMidi",       "BitMidiBrowser",     "default"),
    ("WaivOps Drums", "WaivOpsBrowser",     "trap"),
    ("HookTheory",    "HookTheoryBrowser",  "trap"),
    ("ldrolez Chords","LdrolezChordBrowser","trap"),
]


def _test_databases(params: dict, registry: ModelRegistry) -> dict:
    """Probe each active Library database with a quick search and report results.

    returns: {results: [{name, ok, count, ms, error}]}
    """
    import time
    results = []
    for db_name, cls_name, query in _TEST_DBS:
        cls = _get_browser_cls(cls_name)
        if cls is None:
            results.append({"name": db_name, "ok": False, "count": 0,
                            "ms": 0, "error": "class not found"})
            continue
        t0 = time.monotonic()
        try:
            out = cls().search(query, 0, 1)
            ms  = int((time.monotonic() - t0) * 1000)
            err = out.get("error", "")
            cnt = out.get("total", len(out.get("items", [])))
            results.append({"name": db_name, "ok": not err, "count": cnt,
                            "ms": ms, "error": err or ""})
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            results.append({"name": db_name, "ok": False, "count": 0,
                            "ms": ms, "error": _clean_str(exc)})
    return {"results": results}

