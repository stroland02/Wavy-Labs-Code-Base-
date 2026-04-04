"""
midi_library.py — BitMidi MIDI downloader, role extractor, and transposer.

For each compose request:
  1. Search BitMidi by genre + prompt keywords
  2. Download and cache the MIDI file
  3. Extract the role-appropriate track (bass / melody / chords / drums)
  4. Transpose to the requested key
  5. Trim to the requested bar count
  6. Return the processed path as the actual track output (no LLM needed)

All network failures are silently caught — callers get None on error.
"""

from __future__ import annotations

import math
import random
import re
import shutil
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import httpx
import mido
from loguru import logger

import config
from utils.music_theory import detect_key_from_notes


# ── Key / transposition helpers ──────────────────────────────────────────────

_NOTE_TO_PC: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def key_interval(from_key: str, to_key: str) -> int:
    """Semitones needed to transpose from from_key to to_key (range ±6)."""
    from_pc = _NOTE_TO_PC.get(from_key, 0)
    to_pc   = _NOTE_TO_PC.get(to_key,   0)
    diff    = (to_pc - from_pc) % 12
    if diff > 6:
        diff -= 12   # prefer shorter interval (e.g. -5 instead of +7)
    return diff


# ── Genre → BitMidi page offset mapping ──────────────────────────────────────
# BitMidi's ?q= search parameter is JavaScript-rendered and ignored server-side.
# We use pagination instead: each genre maps to a different page range so
# different genres pull from different slices of the catalog for variety.

_GENRE_PAGE_OFFSETS: dict[str, int] = {
    "lofi":    0,
    "trap":    2,
    "house":   4,
    "jazz":    6,
    "ambient": 8,
    "default": 10,
}

# ── Artist name lookup (for LLM context / logging only, not for search) ───────
_GENRE_ARTIST_QUERIES: dict[str, list[str]] = {
    "lofi":    ["nujabes", "j dilla", "bill evans", "chet baker"],
    "trap":    ["timbaland", "dr dre", "snoop dogg", "jay z"],
    "house":   ["daft punk", "kraftwerk", "frankie knuckles", "larry heard"],
    "jazz":    ["miles davis", "bill evans", "john coltrane", "duke ellington"],
    "ambient": ["brian eno", "tangerine dream", "harold budd", "enigma"],
    "default": ["beethoven", "mozart", "chopin", "bach"],
}

# Words to strip from a user prompt before extracting keywords for logging
_QUERY_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "will", "have", "are",
    "its", "use", "add", "make", "create", "generate", "please", "bars", "bpm",
    "bar", "beat", "beats", "tempo", "key", "scale", "major", "minor", "notes",
    "note", "track", "tracks", "smooth", "nice", "good", "cool", "great",
})


def genre_to_query(genre: str, prompt: str = "") -> str:
    """Return a human-readable genre label for logging purposes.

    Note: BitMidi text search is not functional (JavaScript-rendered).
    This function is kept for compatibility and LLM context logging.
    """
    if prompt:
        cleaned = re.sub(
            r'\b\d+\s*bpm\b|\b\d+\s*bars?\b|[A-G][#b]?\s+(?:major|minor)\b',
            " ", prompt, flags=re.IGNORECASE,
        )
        words = re.findall(r"[a-zA-Z&]{2,}", cleaned)
        useful = [
            w.lower() for w in words
            if w.lower() not in _QUERY_STOP_WORDS
        ][:4]
        if useful:
            return " ".join(useful)

    return _GENRE_ARTIST_QUERIES.get(genre, _GENRE_ARTIST_QUERIES["default"])[0]


# ── HTML Parsers ──────────────────────────────────────────────────────────────

class _BitMidiSearchParser(HTMLParser):
    """
    Collect (slug, title) pairs from BitMidi search results page.
    Looks for <a href="/some-song-title-mid"> links.
    """

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._in_link = False
        self._current_href = ""
        self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_dict = dict(attrs)
        href = attr_dict.get("href", "") or ""
        # BitMidi song pages: /slug-mid (starts with "/" ends with "-mid")
        if href.startswith("/") and href.endswith("-mid") and href.count("/") == 1:
            self._in_link = True
            self._current_href = href
            self._current_text = ""

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._current_text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            slug  = self._current_href.lstrip("/")
            title = self._current_text.strip()
            if slug and title:
                self.results.append({"slug": slug, "title": title})
            self._in_link = False
            self._current_href = ""
            self._current_text = ""


class _BitMidiDownloadParser(HTMLParser):
    """
    Extract the direct /uploads/NNNNN.mid URL from a BitMidi song page.
    Looks for <a href="/uploads/...mid"> or an audio/source src attribute.
    """

    def __init__(self) -> None:
        super().__init__()
        self.download_url: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.download_url:
            return
        attr_dict = dict(attrs)
        for attr_name in ("href", "src", "data-src"):
            val = attr_dict.get(attr_name, "") or ""
            if val and "/uploads/" in val and val.endswith(".mid"):
                self.download_url = val
                return


# ── Network helpers ───────────────────────────────────────────────────────────

def search_bitmidi(genre: str, limit: int = 5, prompt: str = "", page: int | None = None) -> list[dict]:
    """
    Fetch MIDI candidates from BitMidi using genre-mapped pagination.

    BitMidi's ?q= search is JavaScript-rendered and does not work server-side.
    We browse a genre-specific page range instead, giving each genre a different
    slice of the catalog for variety.

    When `page` is given (1-based), that exact page is fetched (used for
    deterministic "Load More" pagination).  Otherwise a random page in the
    genre's range is chosen for variety.

    Returns a list of {slug, title} dicts (up to `limit`).
    Returns [] on any network/parse failure.
    """
    try:
        base_page = _GENRE_PAGE_OFFSETS.get(genre, _GENRE_PAGE_OFFSETS["default"])
        if page is not None:
            target_page = page
        else:
            target_page = base_page + random.randint(1, 3)
        page = target_page
        url  = f"https://bitmidi.com/?page={page}"
        headers = {
            "User-Agent": "WavyLabs/1.0 (AI DAW; MIDI seed fetch; +https://wavylabs.com)",
        }
        resp = httpx.get(url, timeout=8.0, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        parser = _BitMidiSearchParser()
        parser.feed(resp.text)
        # Shuffle so repeated calls to the same page give different ordering
        results = parser.results[:]
        random.shuffle(results)
        results = results[:limit]
        logger.debug(f"  midi_library: browse page {page} (genre={genre}) → {len(results)} results: "
                     + ", ".join(r["title"] for r in results))
        return results
    except Exception as exc:
        logger.warning(f"  midi_library: search_bitmidi failed: {exc}")
        return []


def download_midi(slug: str, title: str) -> Optional[Path]:
    """
    Download a MIDI file from BitMidi given its slug.

    1. Fetches the song page to find the direct upload URL.
    2. Downloads the .mid file.
    3. Validates the MThd header.
    4. Caches to MIDI_LIBRARY_DIR/<safe_slug>.mid.

    Returns the cached Path, or None on any failure.
    """
    try:
        # Check cache first
        safe_slug = re.sub(r"[^\w\-]", "_", slug)[:80]
        cache_path = config.MIDI_LIBRARY_DIR / f"{safe_slug}.mid"
        if cache_path.exists() and cache_path.stat().st_size > 20:
            logger.debug(f"  midi_library: cache hit {cache_path.name}")
            return cache_path

        headers = {
            "User-Agent": "WavyLabs/1.0 (AI DAW; MIDI seed fetch; +https://wavylabs.com)",
        }

        # Step 1: Fetch song page to find download URL
        page_url = f"https://bitmidi.com/{slug}"
        page_resp = httpx.get(page_url, timeout=8.0, headers=headers, follow_redirects=True)
        page_resp.raise_for_status()

        dl_parser = _BitMidiDownloadParser()
        dl_parser.feed(page_resp.text)
        download_url = dl_parser.download_url

        if not download_url:
            logger.warning(f"  midi_library: no download URL found on page {page_url}")
            return None

        # Resolve relative URL
        if download_url.startswith("/"):
            download_url = f"https://bitmidi.com{download_url}"

        # Step 2: Download MIDI binary
        midi_resp = httpx.get(download_url, timeout=15.0, headers=headers, follow_redirects=True)
        midi_resp.raise_for_status()

        # Step 3: Validate MIDI header ("MThd")
        content = midi_resp.content
        if not content[:4] == b"MThd":
            logger.warning(f"  midi_library: {slug} — not a valid MIDI file (no MThd header)")
            return None

        # Step 4: Cache to disk
        config.MIDI_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        logger.info(f"  midi_library: downloaded '{title}' → {cache_path.name} ({len(content)} bytes)")
        return cache_path

    except Exception as exc:
        logger.warning(f"  midi_library: download_midi({slug}) failed: {exc}")
        return None


# ── MIDI analysis ─────────────────────────────────────────────────────────────

def analyze_midi(midi_path: Path) -> dict:
    """
    Analyze a MIDI file and return:
      bpm, pitches (non-drum), key, scale,
      total_ticks, ticks_per_beat, track_count

    Returns safe defaults on any parse failure.
    """
    defaults = {
        "bpm": 120,
        "pitches": [],
        "key": "C",
        "scale": "major",
        "total_ticks": 0,
        "ticks_per_beat": 480,
        "track_count": 0,
    }
    try:
        mid = mido.MidiFile(str(midi_path))
        ticks_per_beat = mid.ticks_per_beat or 480

        bpm = 120
        pitches: list[int] = []
        total_ticks = 0

        for track_idx, track in enumerate(mid.tracks):
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "set_tempo":
                    bpm = round(mido.tempo2bpm(msg.tempo))
                # Collect pitched notes (exclude channel 9 = drums)
                if msg.type == "note_on" and msg.velocity > 0:
                    if getattr(msg, "channel", 0) != 9:
                        pitches.append(msg.note)
            total_ticks = max(total_ticks, abs_tick)

        key, scale = "C", "major"
        if pitches:
            key, scale = detect_key_from_notes(pitches)

        return {
            "bpm":          bpm,
            "pitches":      pitches,
            "key":          key,
            "scale":        scale,
            "total_ticks":  total_ticks,
            "ticks_per_beat": ticks_per_beat,
            "track_count":  len(mid.tracks),
        }
    except Exception as exc:
        logger.warning(f"  midi_library: analyze_midi({midi_path.name}) failed: {exc}")
        return defaults


# ── MIDI trimming ─────────────────────────────────────────────────────────────

def trim_midi_to_bars(midi_path: Path, bars: int, bpm: int, output_path: Path) -> Path:
    """
    Trim a MIDI file to `bars` bars (4/4 time).

    Events at or after max_ticks are dropped. An end_of_track meta is appended.
    If the source file is shorter than bars, all notes are kept unchanged.
    Falls back to copying the original on any parse error.

    Returns output_path.
    """
    try:
        mid   = mido.MidiFile(str(midi_path))
        tpb   = mid.ticks_per_beat or 480
        max_ticks = tpb * 4 * bars  # 4/4 time: 4 beats * bars

        new_mid = mido.MidiFile(ticks_per_beat=tpb, type=mid.type)

        for track in mid.tracks:
            new_track = mido.MidiTrack()
            abs_tick  = 0
            prev_kept_abs = 0  # abs tick of the last kept event

            for msg in track:
                abs_tick += msg.time
                if abs_tick >= max_ticks:
                    break
                # Re-compute delta relative to last kept event
                delta = abs_tick - prev_kept_abs
                new_msg = msg.copy(time=delta)
                new_track.append(new_msg)
                prev_kept_abs = abs_tick

            # Append end_of_track at exactly max_ticks (clamped to ≥ prev_kept_abs)
            eot_delta = max(0, max_ticks - prev_kept_abs)
            new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))
            new_mid.tracks.append(new_track)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        logger.debug(f"  midi_library: trimmed to {bars} bars → {output_path.name}")
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: trim_midi_to_bars failed: {exc}; copying original")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(midi_path), str(output_path))
        return output_path


# ── Dense-window helper ───────────────────────────────────────────────────────

def _find_densest_window_start(note_abs_ticks: list[int], bar_ticks: int, bars: int) -> int:
    """
    Return the absolute tick of the bar boundary that starts the densest
    `bars`-bar window in the note sequence.

    Scans at bar-level granularity.  Falls back to 0 when the file is shorter
    than the requested window.
    """
    if not note_abs_ticks:
        return 0
    window_ticks = bar_ticks * bars
    max_tick     = max(note_abs_ticks)
    n_start_bars = max(1, int(max_tick // bar_ticks) - bars + 2)

    best_start = 0
    best_count = -1
    for bar_idx in range(n_start_bars):
        start = bar_idx * bar_ticks
        end   = start + window_ticks
        count = sum(1 for t in note_abs_ticks if start <= t < end)
        if count > best_count:
            best_count = count
            best_start = start
    return best_start


# ── Melody extraction ─────────────────────────────────────────────────────────

def extract_melody_midi(midi_path: Path, bars: int, output_path: Path) -> Path:
    """
    Extract the single best melodic track from a multi-track MIDI and write
    a clean one-track MIDI trimmed to `bars` bars.

    Selection criteria (ranked):
      1. Exclude channel 9 (drums) completely
      2. Among remaining tracks, pick the one with the highest score:
         score = 75th-percentile pitch + log(note_count)   (whole-file scoring)
      3. From that track, extract the DENSEST `bars`-bar window
         (avoids sparse intros — most real songs have a quiet intro)
      4. Re-index delta times and write a fresh Type-0 MIDI

    Falls back to copying the original on any parse error.
    """
    try:
        mid       = mido.MidiFile(str(midi_path))
        tpb       = mid.ticks_per_beat or 480
        bar_ticks = tpb * 4

        # ── Pass 1: score every track across the WHOLE file ──────────────────
        best_track      = None
        best_score      = -1.0
        best_p75_pitch  = 0

        for track in mid.tracks:
            pitches: list[int] = []
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                    if getattr(msg, "channel", 0) != 9:
                        pitches.append(msg.note)
            if not pitches:
                continue
            pitches_sorted = sorted(pitches)
            p75_idx   = int(len(pitches_sorted) * 0.75)
            p75_pitch = pitches_sorted[p75_idx]
            score = p75_pitch + math.log(len(pitches) + 1)
            if score > best_score:
                best_score     = score
                best_p75_pitch = p75_pitch
                best_track     = track

        if best_track is None:
            return trim_midi_to_bars(midi_path, bars, 120, output_path)

        # ── Pass 2: collect abs-tick note_on events from best track ──────────
        note_abs: list[int] = []
        abs_tick = 0
        for msg in best_track:
            abs_tick += msg.time
            if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                if getattr(msg, "channel", 0) != 9:
                    note_abs.append(abs_tick)

        # ── Pass 3: find densest window start ────────────────────────────────
        win_start = _find_densest_window_start(note_abs, bar_ticks, bars)
        win_end   = win_start + bar_ticks * bars

        # ── Pass 4: extract events from that window ───────────────────────────
        track_msgs: list = []
        abs_tick2 = 0
        prev_kept = win_start
        for msg in best_track:
            abs_tick2 += msg.time
            if abs_tick2 < win_start:
                continue
            if abs_tick2 >= win_end:
                break
            if getattr(msg, "channel", 0) == 9:
                continue
            delta = abs_tick2 - prev_kept
            track_msgs.append(msg.copy(time=delta))
            prev_kept = abs_tick2

        if not track_msgs:
            return trim_midi_to_bars(midi_path, bars, 120, output_path)

        # Write a fresh single-track Type-0 MIDI
        new_mid   = mido.MidiFile(ticks_per_beat=tpb, type=0)
        new_track = mido.MidiTrack()
        new_mid.tracks.append(new_track)
        new_track.extend(track_msgs)
        eot_delta = max(0, win_end - (win_start + sum(m.time for m in track_msgs)))
        new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        note_count = sum(1 for m in track_msgs if m.type == "note_on" and getattr(m, "velocity", 0) > 0)
        bar_offset = win_start // bar_ticks
        logger.info(
            f"  midi_library: melody extracted → {note_count} notes,"
            f" p75={best_p75_pitch} bar_offset={bar_offset} → {output_path.name}"
        )
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: extract_melody_midi failed: {exc}; falling back to trim")
        return trim_midi_to_bars(midi_path, bars, 120, output_path)


def extract_full_pitched_midi(midi_path: Path, bars: int, output_path: Path) -> Path:
    """
    Merge ALL pitched (non-drum) tracks from the DENSEST `bars`-bar window
    into a single MIDI.

    Finds the bar offset with the most notes across all tracks (avoids sparse
    intros) then merges every non-drum note/note_off from that window.
    Falls back to trim_midi_to_bars on error.
    """
    try:
        mid       = mido.MidiFile(str(midi_path))
        tpb       = mid.ticks_per_beat or 480
        bar_ticks = tpb * 4

        # ── Pass 1: collect ALL non-drum note_on abs ticks (for window search) ──
        all_note_ons: list[int] = []
        # Also collect every non-drum event with abs tick (for extraction)
        all_events: list[tuple[int, object]] = []

        for track in mid.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if getattr(msg, "channel", 0) == 9:
                    continue  # skip drum channel
                if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                    all_note_ons.append(abs_tick)
                if msg.type in ("note_on", "note_off", "set_tempo"):
                    all_events.append((abs_tick, msg))

        if not all_events:
            return trim_midi_to_bars(midi_path, bars, 120, output_path)

        # ── Pass 2: find densest window ───────────────────────────────────────
        win_start = _find_densest_window_start(all_note_ons, bar_ticks, bars)
        win_end   = win_start + bar_ticks * bars

        # ── Pass 3: filter + sort events in that window ───────────────────────
        window_events = [
            (t, m) for t, m in all_events if win_start <= t < win_end
        ]
        if not window_events:
            return trim_midi_to_bars(midi_path, bars, 120, output_path)

        window_events.sort(key=lambda x: x[0])

        new_mid   = mido.MidiFile(ticks_per_beat=tpb, type=0)
        new_track = mido.MidiTrack()
        new_mid.tracks.append(new_track)
        prev_abs = win_start
        for abs_t, msg in window_events:
            new_track.append(msg.copy(time=abs_t - prev_abs))
            prev_abs = abs_t
        eot_delta = max(0, win_end - prev_abs)
        new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        n = sum(1 for _, m in window_events if m.type == "note_on" and getattr(m, "velocity", 0) > 0)
        bar_offset = win_start // bar_ticks
        logger.info(
            f"  midi_library: full pitched merge → {n} notes"
            f" (bar {bar_offset}) → {output_path.name}"
        )
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: extract_full_pitched_midi failed: {exc}; falling back")
        return trim_midi_to_bars(midi_path, bars, 120, output_path)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def find_seed(genre: str, bars: int, bpm: int, prompt: str = "") -> Optional[dict]:
    """
    Search BitMidi for a seed MIDI, download, analyze, and trim it.

    Uses prompt keywords for a more specific search when provided.
    Returns {title, midi_path (str), key, scale, bpm} or None on failure.
    """
    candidates = search_bitmidi(genre)
    if not candidates:
            logger.info(f"  midi_library: no candidates for genre '{genre}'")
            return None

    candidates = list(candidates)
    # Use results in relevance order (BitMidi returns best matches first).
    # No shuffle — consistent, prompt-matched results are more useful than variety.

    for candidate in candidates:
        slug  = candidate["slug"]
        title = candidate["title"]

        # Download (with cache)
        midi_path = download_midi(slug, title)
        if not midi_path:
            continue

        # Analyze
        info = analyze_midi(midi_path)
        if not info["pitches"]:
            logger.info(f"  midi_library: '{title}' has no pitched notes (drums only?), skipping")
            continue

        # Extract single best melodic track, trimmed to requested length
        trimmed_name = f"seed_{re.sub(r'[^\\w]', '_', slug)[:40]}_{uuid.uuid4().hex[:6]}.mid"
        trimmed_path = config.GENERATION_DIR / trimmed_name
        extract_melody_midi(midi_path, bars, trimmed_path)

        result = {
            "title":      title,
            "midi_path":  str(trimmed_path),
            "key":        info["key"],
            "scale":      info["scale"],
            "bpm":        info["bpm"],
        }
        logger.info(
            f"  midi_library: seed selected '{title}' "
            f"→ {info['key']} {info['scale']}, {info['bpm']} BPM"
        )
        return result

    logger.info(f"  midi_library: all {len(candidates)} candidates failed for genre '{genre}'")
    return _find_midi_for_role_from_cache("melody", bars, "", "", bpm)


# ── Role-aware extraction ─────────────────────────────────────────────────────

def extract_bass_midi(midi_path: Path, bars: int, output_path: Path) -> Path:
    """
    Extract the bass track from a multi-track MIDI.

    Selection: track whose 25th-percentile pitch is lowest (opposite of
    extract_melody_midi) while excluding channel 9 (drums).
    Falls back to trim_midi_to_bars on failure.
    """
    try:
        mid     = mido.MidiFile(str(midi_path))
        tpb     = mid.ticks_per_beat or 480
        max_ticks = tpb * 4 * bars

        best_track_msgs: list  = []
        best_score: float      = float("inf")  # lower p25 = more bass-like

        for track in mid.tracks:
            pitches: list[int] = []
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    if getattr(msg, "channel", 0) != 9:
                        pitches.append(msg.note)
            if not pitches:
                continue
            pitches_sorted = sorted(pitches)
            p25_idx   = max(0, int(len(pitches_sorted) * 0.25) - 1)
            p25_pitch = pitches_sorted[p25_idx]
            score     = p25_pitch - math.log(len(pitches) + 1)  # penalise sparse tracks
            if score < best_score:
                best_score = score
                best_track_msgs = []
                abs_tick2  = 0
                prev_kept  = 0
                for msg in track:
                    abs_tick2 += msg.time
                    if abs_tick2 >= max_ticks:
                        break
                    if getattr(msg, "channel", 0) == 9:
                        continue
                    delta = abs_tick2 - prev_kept
                    best_track_msgs.append(msg.copy(time=delta))
                    prev_kept = abs_tick2

        if not best_track_msgs:
            return trim_midi_to_bars(midi_path, bars, 120, output_path)

        new_mid   = mido.MidiFile(ticks_per_beat=tpb, type=0)
        new_track = mido.MidiTrack()
        new_mid.tracks.append(new_track)
        new_track.extend(best_track_msgs)
        eot_delta = max(0, max_ticks - sum(m.time for m in best_track_msgs))
        new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        note_count = sum(1 for m in best_track_msgs if m.type == "note_on" and m.velocity > 0)
        logger.info(
            f"  midi_library: bass extracted → {note_count} notes,"
            f" p25_pitch={int(best_score + math.log(2))} → {output_path.name}"
        )
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: extract_bass_midi failed: {exc}; falling back to trim")
        return trim_midi_to_bars(midi_path, bars, 120, output_path)


def extract_chords_midi(midi_path: Path, bars: int, output_path: Path) -> Path:
    """
    Extract the most polyphonic track from a multi-track MIDI (chords/pad).

    Selection: track with the highest fraction of time-steps that have ≥2
    simultaneous note_on events.  Falls back to trim_midi_to_bars on failure.
    """
    try:
        mid     = mido.MidiFile(str(midi_path))
        tpb     = mid.ticks_per_beat or 480
        max_ticks = tpb * 4 * bars

        best_track_msgs: list = []
        best_poly_score: float = -1.0

        for track in mid.tracks:
            note_starts: dict[int, int] = {}
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    if getattr(msg, "channel", 0) != 9:
                        note_starts[abs_tick] = note_starts.get(abs_tick, 0) + 1
            if not note_starts:
                continue
            max_sim = max(note_starts.values())
            if max_sim < 2:
                continue   # monophonic — not a chords track
            poly_count = sum(1 for c in note_starts.values() if c >= 2)
            poly_score = poly_count / len(note_starts)
            if poly_score > best_poly_score:
                best_poly_score = poly_score
                best_track_msgs = []
                abs_tick2 = 0
                prev_kept = 0
                for msg in track:
                    abs_tick2 += msg.time
                    if abs_tick2 >= max_ticks:
                        break
                    if getattr(msg, "channel", 0) == 9:
                        continue
                    delta = abs_tick2 - prev_kept
                    best_track_msgs.append(msg.copy(time=delta))
                    prev_kept = abs_tick2

        if not best_track_msgs:
            # No polyphonic track found — fall back to melody extraction
            return extract_melody_midi(midi_path, bars, output_path)

        new_mid   = mido.MidiFile(ticks_per_beat=tpb, type=0)
        new_track = mido.MidiTrack()
        new_mid.tracks.append(new_track)
        new_track.extend(best_track_msgs)
        eot_delta = max(0, max_ticks - sum(m.time for m in best_track_msgs))
        new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        note_count = sum(1 for m in best_track_msgs if m.type == "note_on" and m.velocity > 0)
        logger.info(
            f"  midi_library: chords extracted → {note_count} notes,"
            f" poly_score={best_poly_score:.2f} → {output_path.name}"
        )
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: extract_chords_midi failed: {exc}; falling back to trim")
        return trim_midi_to_bars(midi_path, bars, 120, output_path)


def extract_drums_midi(midi_path: Path, bars: int, output_path: Path) -> Path:
    """
    Extract channel-9 (GM drum) events from a MIDI file and trim to bars.

    Falls back to copying the original on failure.
    """
    try:
        mid     = mido.MidiFile(str(midi_path))
        tpb     = mid.ticks_per_beat or 480
        max_ticks = tpb * 4 * bars

        new_mid   = mido.MidiFile(ticks_per_beat=tpb, type=0)
        new_track = mido.MidiTrack()
        new_mid.tracks.append(new_track)

        drum_msgs: list = []
        for track in mid.tracks:
            abs_tick = 0
            prev_kept = 0
            for msg in track:
                abs_tick += msg.time
                if abs_tick >= max_ticks:
                    break
                if msg.type in ("note_on", "note_off") and getattr(msg, "channel", 0) == 9:
                    delta = abs_tick - prev_kept
                    drum_msgs.append(msg.copy(time=delta))
                    prev_kept = abs_tick
                elif msg.type not in ("note_on", "note_off"):
                    # Keep meta/control messages
                    delta = abs_tick - prev_kept
                    drum_msgs.append(msg.copy(time=delta))
                    prev_kept = abs_tick

        if not drum_msgs:
            logger.info("  midi_library: no drum channel found in MIDI")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(midi_path), str(output_path))
            return output_path

        new_track.extend(drum_msgs)
        eot_delta = max(0, max_ticks - sum(m.time for m in drum_msgs))
        new_track.append(mido.MetaMessage("end_of_track", time=eot_delta))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        note_count = sum(1 for m in drum_msgs if m.type == "note_on" and m.velocity > 0)
        logger.info(f"  midi_library: drums extracted → {note_count} hits → {output_path.name}")
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: extract_drums_midi failed: {exc}; copying original")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(midi_path), str(output_path))
        return output_path


def extract_role_midi(midi_path: Path, role: str, bars: int, output_path: Path) -> Path:
    """Dispatch to the correct extractor for the given role."""
    if role in ("melody", "lead", "counter"):
        return extract_melody_midi(midi_path, bars, output_path)
    if role == "bass":
        return extract_bass_midi(midi_path, bars, output_path)
    if role in ("chords", "pad"):
        return extract_chords_midi(midi_path, bars, output_path)
    if role == "drums":
        return extract_drums_midi(midi_path, bars, output_path)
    return trim_midi_to_bars(midi_path, bars, 120, output_path)


def transpose_midi(midi_path: Path, semitones: int, output_path: Path) -> Path:
    """
    Shift all pitched notes (non-drum channels) by `semitones`.

    Channel 9 (drums) is left untouched.  Returns output_path.
    """
    if semitones == 0:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(midi_path), str(output_path))
        return output_path
    try:
        mid     = mido.MidiFile(str(midi_path))
        new_mid = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat, type=mid.type)

        for track in mid.tracks:
            new_track = mido.MidiTrack()
            for msg in track:
                if msg.type in ("note_on", "note_off") and getattr(msg, "channel", 0) != 9:
                    new_note = max(0, min(127, msg.note + semitones))
                    new_track.append(msg.copy(note=new_note))
                else:
                    new_track.append(msg.copy())
            new_mid.tracks.append(new_track)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_mid.save(str(output_path))
        logger.debug(
            f"  midi_library: transposed {semitones:+d} semitones → {output_path.name}"
        )
        return output_path

    except Exception as exc:
        logger.warning(f"  midi_library: transpose_midi failed: {exc}; copying original")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(midi_path), str(output_path))
        return output_path


def count_notes(midi_path: Path) -> int:
    """Return the number of note_on (velocity>0) messages in a MIDI file."""
    try:
        mid = mido.MidiFile(str(midi_path))
        return sum(
            1 for track in mid.tracks
            for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        )
    except Exception:
        return 0


# ── Local cache fallback ──────────────────────────────────────────────────────

def _find_midi_for_role_from_cache(
    role: str,
    bars: int,
    target_key: str,
    target_scale: str,
    bpm: int,
    full_mix: bool = False,
) -> Optional[dict]:
    """
    When BitMidi search/download fails (network down, 502, etc.), try any MIDI
    file already cached in MIDI_LIBRARY_DIR.  This keeps the app producing real
    MIDI content even when BitMidi is temporarily unavailable.
    """
    cached = sorted(config.MIDI_LIBRARY_DIR.glob("*.mid"))
    if not cached:
        logger.info("  midi_library: MIDI_LIBRARY_DIR empty — no offline fallback available")
        return None

    logger.info(
        f"  midi_library: offline cache fallback — trying {len(cached)} cached files "
        f"for role={role}"
    )
    for midi_path in cached:
        try:
            info = analyze_midi(midi_path)
            if not info["pitches"] and role != "drums":
                continue

            slug_tag  = re.sub(r"[^\w]", "_", midi_path.stem)[:40]
            out_name  = f"{role}_{slug_tag}_{uuid.uuid4().hex[:6]}.mid"
            extracted = config.GENERATION_DIR / out_name
            if full_mix and role != "drums":
                extract_full_pitched_midi(midi_path, bars, extracted)
            else:
                extract_role_midi(midi_path, role, bars, extracted)

            orig_key  = info["key"]
            semitones = key_interval(orig_key, target_key) if target_key and orig_key != target_key else 0
            if semitones:
                trans_name = f"t{semitones:+d}_{out_name}"
                transposed = config.GENERATION_DIR / trans_name
                transpose_midi(extracted, semitones, transposed)
                extracted  = transposed

            n = count_notes(extracted)
            if n == 0:
                continue

            logger.info(
                f"  midi_library: offline cache → '{midi_path.stem}'"
                f" role={role} ({orig_key}→{target_key or orig_key}, {semitones:+d}st)"
                f" {n} notes → {extracted.name}"
            )
            return {
                "title":       midi_path.stem,
                "midi_path":   str(extracted),
                "source_midi": str(midi_path),
                "key":         target_key or orig_key,
                "scale":       target_scale or info["scale"],
                "bpm":         info["bpm"],
                "note_count":  n,
            }
        except Exception as exc:
            logger.debug(f"  midi_library: cache fallback skip {midi_path.name}: {exc}")
            continue

    logger.info(f"  midi_library: cache fallback exhausted for role={role}")
    return None


# ── Simple raw MIDI fetch (no extraction / transposition) ─────────────────────

def find_midi_raw(genre: str, prompt: str = "") -> Optional[Path]:
    """Search BitMidi and return the raw downloaded MIDI path — no extraction.

    Used by the import_midi_file action path so that ImportFilter (MidiImport
    plugin + SF2Player) handles all the heavy lifting, just like File → Import.
    Returns None on any failure.
    """
    # Browse the genre's page range; retry once on empty result
    candidates = search_bitmidi(genre)
    if not candidates:
        candidates = search_bitmidi(genre)
    # Fall back to local cache
    if not candidates:
        cached = sorted(config.MIDI_LIBRARY_DIR.glob("*.mid"))
        return cached[0] if cached else None
    for c in candidates:
        path = download_midi(c["slug"], c["title"])
        if path:
            logger.info(f"  midi_library: raw MIDI → '{c['title']}' {path.name}")
            return path
    return None


# ── Main public API ────────────────────────────────────────────────────────────

def find_midi_for_role(
    genre: str,
    role: str,
    bars: int,
    bpm: int,
    prompt: str = "",
    target_key: str = "",
    target_scale: str = "",
    source_midi: Optional[Path] = None,
    source_key: str = "",
    full_mix: bool = False,
) -> Optional[dict]:
    """
    Return a ready-to-use MIDI file for the requested role.

    Pipeline:
      1. If source_midi supplied (session reuse), skip search/download.
         Otherwise: search BitMidi → download.
      2. Analyze original key.
      3. extract_role_midi() — picks the right track (bass/melody/chords/drums).
      4. transpose_midi()    — shifts to target_key if different.
      5. Return {title, midi_path, source_midi, key, scale, bpm, note_count}.

    Returns None if all candidates fail or the file has no notes.
    """
    # ── Reuse session source MIDI ─────────────────────────────────────────────
    if source_midi and source_midi.exists() and source_key:
        slug_tag = re.sub(r"[^\w]", "_", source_midi.stem)[:30]
        out_name = f"{role}_{slug_tag}_{uuid.uuid4().hex[:6]}.mid"
        extracted = config.GENERATION_DIR / out_name
        if full_mix and role != "drums":
            extract_full_pitched_midi(source_midi, bars, extracted)
        else:
            extract_role_midi(source_midi, role, bars, extracted)
        semitones = key_interval(source_key, target_key) if target_key and source_key != target_key else 0
        if semitones:
            trans_name = f"t{semitones:+d}_{out_name}"
            transposed = config.GENERATION_DIR / trans_name
            transpose_midi(extracted, semitones, transposed)
            extracted = transposed
        n = count_notes(extracted)
        if n > 0:
            return {
                "title":        source_midi.stem,
                "midi_path":    str(extracted),
                "source_midi":  str(source_midi),
                "key":          target_key or source_key,
                "scale":        target_scale,
                "bpm":          bpm,
                "note_count":   n,
            }

    # ── Search and download ───────────────────────────────────────────────────
    logger.info(f"  midi_library: browsing BitMidi — genre={genre} role={role}")
    candidates = search_bitmidi(genre)
    if not candidates:
        return _find_midi_for_role_from_cache(role, bars, target_key, target_scale, bpm, full_mix=full_mix)

    for candidate in candidates:
        slug  = candidate["slug"]
        title = candidate["title"]

        midi_path = download_midi(slug, title)
        if not midi_path:
            continue

        info = analyze_midi(midi_path)
        # Drums-only files are fine for the drums role; skip for pitched roles
        if not info["pitches"] and role != "drums":
            logger.info(f"  midi_library: '{title}' — no pitched notes, skipping for role={role}")
            continue

        # ── Extract role track ────────────────────────────────────────────────
        slug_tag  = re.sub(r"[^\w]", "_", slug)[:40]
        out_name  = f"{role}_{slug_tag}_{uuid.uuid4().hex[:6]}.mid"
        extracted = config.GENERATION_DIR / out_name
        if full_mix and role != "drums":
            extract_full_pitched_midi(midi_path, bars, extracted)
        else:
            extract_role_midi(midi_path, role, bars, extracted)

        # ── Transpose to target key ───────────────────────────────────────────
        orig_key  = info["key"]
        semitones = key_interval(orig_key, target_key) if target_key and orig_key != target_key else 0
        if semitones:
            trans_name = f"t{semitones:+d}_{out_name}"
            transposed = config.GENERATION_DIR / trans_name
            transpose_midi(extracted, semitones, transposed)
            extracted  = transposed

        n = count_notes(extracted)
        if n == 0:
            logger.info(f"  midi_library: '{title}' — 0 notes after extraction for role={role}, skipping")
            continue

        logger.info(
            f"  midi_library: role={role} → '{title}'"
            f" ({orig_key} → {target_key or orig_key}, {semitones:+d} st)"
            f"  {n} notes → {extracted.name}"
        )
        return {
            "title":       title,
            "midi_path":   str(extracted),
            "source_midi": str(midi_path),   # original downloaded file (for session reuse)
            "key":         target_key or orig_key,
            "scale":       target_scale or info["scale"],
            "bpm":         info["bpm"],
            "note_count":  n,
        }

    logger.info(f"  midi_library: all candidates failed for genre='{genre}' role='{role}' — trying cache")
    return _find_midi_for_role_from_cache(role, bars, target_key, target_scale, bpm, full_mix=full_mix)


# ── Multi-channel MIDI splitter ───────────────────────────────────────────────

from math import ceil as _ceil

_GM_PROGRAM_NAMES: dict[int, str] = {
    # Piano
    0: "Piano", 1: "Bright Piano", 2: "Electric Piano", 3: "Honky-Tonk",
    4: "E. Piano 1", 5: "E. Piano 2", 6: "Harpsichord", 7: "Clavinet",
    # Chromatic Perc
    8: "Celesta", 9: "Glockenspiel", 10: "Music Box", 11: "Vibraphone",
    12: "Marimba", 13: "Xylophone", 14: "Tubular Bells", 15: "Dulcimer",
    # Organ
    16: "Organ", 17: "Perc Organ", 18: "Rock Organ", 19: "Church Organ",
    20: "Reed Organ", 21: "Accordion", 22: "Harmonica", 23: "Bandoneon",
    # Guitar
    24: "Nylon Guitar", 25: "Steel Guitar", 26: "Jazz Guitar", 27: "Clean Guitar",
    28: "Muted Guitar", 29: "Overdrive Guitar", 30: "Distortion Guitar", 31: "Guitar Harmonics",
    # Bass
    32: "Acoustic Bass", 33: "Finger Bass", 34: "Pick Bass", 35: "Fretless Bass",
    36: "Slap Bass 1", 37: "Slap Bass 2", 38: "Synth Bass 1", 39: "Synth Bass 2",
    # Strings
    40: "Violin", 41: "Viola", 42: "Cello", 43: "Contrabass",
    44: "Tremolo Strings", 45: "Pizzicato Strings", 46: "Harp", 47: "Timpani",
    # Ensemble
    48: "Strings", 49: "Slow Strings", 50: "Synth Strings 1", 51: "Synth Strings 2",
    52: "Choir Aahs", 53: "Voice Oohs", 54: "Synth Voice", 55: "Orchestra Hit",
    # Brass
    56: "Trumpet", 57: "Trombone", 58: "Tuba", 59: "Muted Trumpet",
    60: "French Horn", 61: "Brass Section", 62: "Synth Brass 1", 63: "Synth Brass 2",
    # Reed
    64: "Soprano Sax", 65: "Alto Sax", 66: "Tenor Sax", 67: "Baritone Sax",
    68: "Oboe", 69: "English Horn", 70: "Bassoon", 71: "Clarinet",
    # Pipe
    72: "Piccolo", 73: "Flute", 74: "Recorder", 75: "Pan Flute",
    76: "Blown Bottle", 77: "Shakuhachi", 78: "Whistle", 79: "Ocarina",
    # Synth Lead
    80: "Synth Lead 1", 81: "Synth Lead 2", 82: "Synth Lead 3", 83: "Synth Lead 4",
    84: "Synth Lead 5", 85: "Synth Lead 6", 86: "Synth Lead 7", 87: "Synth Lead 8",
    # Synth Pad
    88: "Pad", 89: "Warm Pad", 90: "Polysynth", 91: "Choir Pad",
    92: "Bowed Pad", 93: "Metallic Pad", 94: "Halo Pad", 95: "Sweep Pad",
    # Misc
    96: "Rain FX", 104: "Sitar", 105: "Banjo", 106: "Shamisen",
    107: "Koto", 112: "Tinkle Bell", 116: "Taiko", 117: "Melodic Tom",
    118: "Synth Drum", 128: "Drums",  # 128 = sentinel for ch 9
}

_CHANNEL_COLORS = [
    "#e74c3c",  # red      — drums
    "#3498db",  # blue
    "#2ecc71",  # green
    "#f39c12",  # orange
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e67e22",  # dark orange
    "#34495e",  # dark grey
]


def split_midi_by_channel(
    midi_path: "str | Path",
    output_dir: "Path | None" = None,
) -> list[dict]:
    """Split a multi-channel MIDI file into per-channel single-track MIDI files.

    Returns a list of dicts (one per non-empty channel), drums (ch 9) first:
        [{channel, program, midi_path, note_count, bars}]
    """
    midi_path = Path(midi_path)
    out_dir = output_dir or (midi_path.parent / "split")
    out_dir.mkdir(parents=True, exist_ok=True)

    mid = mido.MidiFile(midi_path)
    tpb = mid.ticks_per_beat or 480

    # ── Extract BPM from first set_tempo meta message ─────────────────────────
    source_tempo_us = 500_000  # default 120 BPM
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                source_tempo_us = msg.tempo
                break
        if source_tempo_us != 500_000:
            break
    source_bpm = round(mido.tempo2bpm(source_tempo_us))

    # ── Pass 1: collect per-channel data ──────────────────────────────────────
    # channel → {program, notes: [(abs_tick_on, abs_tick_off, pitch, vel)]}
    ch_data: dict[int, dict] = {}

    for track in mid.tracks:
        abs_tick = 0
        active: dict[tuple, int] = {}  # (ch, pitch) → abs_tick_on

        for msg in track:
            abs_tick += msg.time
            if msg.type == "set_tempo":
                pass
            elif msg.type == "program_change":
                ch = msg.channel
                ch_data.setdefault(ch, {"program": 0, "notes": [], "max_tick": 0})
                ch_data[ch]["program"] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                ch = msg.channel
                ch_data.setdefault(ch, {"program": 0 if ch != 9 else 128, "notes": [], "max_tick": 0})
                active[(ch, msg.note)] = abs_tick
            elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
                ch = msg.channel
                key = (ch, msg.note)
                if key in active:
                    on_tick = active.pop(key)
                    ch_data.setdefault(ch, {"program": 0 if ch != 9 else 128, "notes": [], "max_tick": 0})
                    ch_data[ch]["notes"].append((on_tick, abs_tick, msg.note,
                                                  getattr(msg, "velocity", 64) or 64))
                    ch_data[ch]["max_tick"] = max(ch_data[ch]["max_tick"], abs_tick)

        # Close any hanging notes
        for (ch, pitch), on_tick in active.items():
            ch_data.setdefault(ch, {"program": 0, "notes": [], "max_tick": 0})
            ch_data[ch]["notes"].append((on_tick, abs_tick, pitch, 64))
            ch_data[ch]["max_tick"] = max(ch_data[ch]["max_tick"], abs_tick)

    # ── Pass 2: write per-channel MIDI files ──────────────────────────────────
    results = []
    stem = midi_path.stem

    for ch in sorted(ch_data.keys(), key=lambda c: (0 if c == 9 else 1, c)):
        info = ch_data[ch]
        notes = info["notes"]
        if not notes:
            continue

        # Calculate bars from max_tick (in ticks) and tpb
        max_tick = info["max_tick"]
        beats = max_tick / tpb
        bars = max(1, _ceil(beats / 4))

        # Write single-track MIDI
        new_mid = mido.MidiFile(type=0, ticks_per_beat=tpb)
        track = mido.MidiTrack()
        new_mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=source_tempo_us, time=0))
        prog = info["program"]
        if ch != 9:
            track.append(mido.Message("program_change", channel=0, program=prog, time=0))

        # Build events (absolute → delta), remap to channel 0 for clean single-track
        events: list[tuple] = []
        for on_t, off_t, pitch, vel in notes:
            events.append((on_t,  "note_on",  pitch, max(1, vel)))
            events.append((off_t, "note_off", pitch, 0))
        events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

        cur = 0
        for abs_t, etype, pitch, vel in events:
            delta = abs_t - cur
            cur = abs_t
            track.append(mido.Message(etype, channel=0, note=pitch,
                                      velocity=vel, time=delta))
        track.append(mido.MetaMessage("end_of_track", time=0))

        out_path = out_dir / f"{stem}_ch{ch:02d}.mid"
        new_mid.save(str(out_path))

        results.append({
            "channel":    ch,
            "program":    prog,
            "midi_path":  str(out_path),
            "note_count": len(notes),
            "bars":       bars,
            "bpm":        source_bpm,
        })

    return results
