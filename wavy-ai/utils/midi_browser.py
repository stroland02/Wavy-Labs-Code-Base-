"""Wavy Labs — MIDI Database Browsers

Nine classes with a common search() + download() interface:
  - MidiWorldBrowser   (MidiWorld.com — importable genre MIDI: pop/jazz/rock/blues…)
  - MidiCapsBrowser    (HuggingFace datasets-server API — browse metadata only)
  - MaestroReader      (Google Storage JSON metadata)
  - GrooveBrowser      (Google Storage MIDI-only zip, cached locally)
  - BitMidiBrowser     (BitMidi genre-browse via pagination)
  - MutopiaOrgBrowser  (Mutopia Project CGI search — ~2,400 classical files)
  - VGMusicBrowser     (VGMusic.com by platform section)
  - GigaMidiBrowser    (HuggingFace Metacreation/GigaMIDI — 2.1M files)
  - PianoMidiDeBrowser (piano-midi.de — curated classical piano per composer)
"""

from __future__ import annotations

import csv
import io
import json
import tarfile
import threading
import zipfile
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

import config

_TIMEOUT_FAST   = 15.0   # metadata rows / small requests
_TIMEOUT_SEARCH = 30.0   # HF full-text search (can be slow)
_TIMEOUT_DL     = 60.0   # file + zip downloads

import random
import re as _re


def _as_str(v: object) -> str:
    """Coerce any value (including lists) to a plain lowercase-able string."""
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v)


# ── GM program → LMMS plugin mapping ─────────────────────────────────────────

# GM program ranges (0-indexed, 0-127):
#   0-7   Piano        8-15  Chromatic Perc  16-23 Organ       24-31 Guitar
#  32-39  Bass        40-47  Strings         48-55 Ensemble    56-63 Brass
#  64-71  Reed        72-79  Pipe            80-87 Synth Lead  88-95 Synth Pad
#  96-103 Synth FX   104-111 Ethnic         112-119 Percussive 120-127 SFX
# 128 = General MIDI drums (channel 10)

def _gm_program_to_category(program: int) -> str:
    """Map a single GM program number (0-127, or 128 for drums) to a category string."""
    if program == 128:          return "drums"
    if program < 0:             return "other"
    if program <=  7:           return "piano"
    if program <= 15:           return "chromatic_perc"
    if program <= 23:           return "organ"
    if program <= 31:           return "guitar"
    if program <= 39:           return "bass"
    if program <= 55:           return "strings"      # strings + ensemble
    if program <= 63:           return "brass"
    if program <= 79:           return "woodwind"      # reed + pipe
    if program <= 87:           return "synth_lead"
    if program <= 103:          return "synth_pad"     # synth pad + synth fx
    if program <= 111:          return "other"          # ethnic
    if program <= 119:          return "drums"          # percussive
    return "other"                                      # sfx 120-127


def _gm_to_plugin(programs: list[int]) -> dict:
    """Return {plugin, category, gm_program} for a list of GM programs.

    The plugin field is a basic default — the C++ side uses `category`
    to resolve the genre-specific plugin + preset + reverb.

    Category mapping (12 categories matching C++ GmCategory enum):
      0-7 piano, 8-15 chromatic_perc, 16-23 organ, 24-31 guitar,
      32-39 bass, 40-55 strings, 56-63 brass, 64-79 woodwind,
      80-87 synth_lead, 88-103 synth_pad, 104-111 other,
      112-119 drums, 120-127 other, 128 drums
    """
    if not programs:
        return {"plugin": "tripleoscillator", "category": "other", "gm_program": -1}

    non_drum = [p for p in programs if p != 128]

    # Pure drum file
    if not non_drum:
        return {"plugin": "kicker", "category": "drums", "gm_program": 128}

    # Use first non-drum program for category classification
    p = non_drum[0]
    cat = _gm_program_to_category(p)

    # Basic plugin default (C++ overrides with genre-specific mapping)
    _CAT_PLUGINS = {
        "piano": "opulenz", "chromatic_perc": "opulenz", "organ": "opulenz",
        "guitar": "tripleoscillator", "bass": "lb302", "strings": "organic",
        "brass": "tripleoscillator", "woodwind": "tripleoscillator",
        "synth_lead": "tripleoscillator", "synth_pad": "organic",
        "drums": "kicker", "other": "tripleoscillator",
    }
    plugin = _CAT_PLUGINS.get(cat, "tripleoscillator")

    return {"plugin": plugin, "category": cat, "gm_program": p}


# ── MidiCaps quality / popularity score ───────────────────────────────────────

def _midicaps_quality_score(row: dict) -> float:
    """Heuristic quality score for a MidiCaps metadata row.

    Higher = richer, more complete track.  Used to sort browse results
    when no search query is active so the best tracks appear first.
    """
    score = 0.0
    dur = float(row.get("duration") or 0)
    # Prefer full songs (30 s – 5 min)
    if 30 <= dur <= 300:
        score += 3.0
    elif 10 <= dur < 30:
        score += 1.0
    elif dur > 300:
        score += 2.0
    # Reward harmonic richness (chord variety)
    chords = row.get("chord_summary") or []
    score += min(len(chords), 6) * 0.4
    # Reward instrument variety (but cap at 5)
    instruments = row.get("instrument_summary") or []
    score += min(len(instruments), 5) * 0.5
    # High-confidence genre label
    genre_probs = row.get("genre_prob") or []
    if genre_probs:
        score += float(genre_probs[0]) * 2.0
    # Penalise test-set files slightly (held-out = unusual content)
    if row.get("test_set"):
        score -= 0.5
    return score


def _is_md5(s: str) -> bool:
    """Return True if s is just a 32-char hex digest (MD5 filename with no meaning)."""
    return bool(_re.fullmatch(r"[0-9a-f]{32}", s.lower()))


def _title_from_caption(caption: str) -> str:
    """Derive a short human-readable title from a MidiCaps caption string.

    Strategy: strip the leading article ("A "/"An "), take the first clause
    up to the first comma or period, and cap at 60 characters.
    """
    if not caption:
        return "MIDI File"
    # Strip leading "A " / "An "
    text = _re.sub(r"^An? ", "", caption.strip(), flags=_re.IGNORECASE)
    # Take up to the first sentence-ending boundary
    clause = _re.split(r"[,.]", text)[0].strip()
    if not clause:
        clause = text
    # Capitalise first letter
    clause = clause[0].upper() + clause[1:] if clause else clause
    return clause[:60] + ("…" if len(clause) > 60 else "")


# ── MidiCaps genre alias map ──────────────────────────────────────────────────
# Maps short/slang genre terms to longer phrases that appear in MidiCaps captions
_MIDICAPS_GENRE_ALIAS: dict[str, str] = {
    "rnb":         "soul rhythm blues funk",
    "r&b":         "soul rhythm blues funk",
    "trap":        "trap hip-hop 808",
    "hiphop":      "hip-hop rap beat",
    "lofi":        "lo-fi chill downtempo",
    "future bass": "electronic synth future",
    "drill":       "drill dark minor",
    "drums":       "drums percussion groove",
    "neo-soul":    "soul neo funk groove",
}


# ── MidiCaps ─────────────────────────────────────────────────────────────────

class MidiCapsBrowser:
    _BASE        = "https://datasets-server.huggingface.co"
    _ARCHIVE_URL = "https://huggingface.co/datasets/amaai-lab/MidiCaps/resolve/main/midicaps.tar.gz"
    _CACHE_DIR   = config.MIDI_LIBRARY_DIR / "midicaps"
    _SENTINEL    = config.MIDI_LIBRARY_DIR / "midicaps_complete.sentinel"

    # Class-level download state (shared across all instances in one process)
    _dl_lock:  threading.Lock       = threading.Lock()
    _dl_state: dict[str, object]    = {
        "status":           "idle",   # idle | downloading | complete | error
        "progress":         0.0,
        "files_extracted":  0,
        "bytes_downloaded": 0,
        "total_bytes":      0,
        "error":            "",
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @classmethod
    def get_status(cls) -> dict:
        """No-op — MidiCaps files are now fetched on-demand from HuggingFace."""
        return {
            "status": "complete", "progress": 1.0,
            "files_extracted": 0, "bytes_downloaded": 0,
            "total_bytes": 0, "error": "",
        }

    @classmethod
    def start_download(cls) -> dict:
        """No-op — MidiCaps files are now fetched on-demand from HuggingFace."""
        return cls.get_status()

    @classmethod
    def _download_worker(cls) -> None:
        """Stream-download midicaps.tar.gz and extract every .mid file."""
        try:
            cls._CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info("[MidiCaps] starting archive download from HuggingFace…")

            with httpx.stream("GET", cls._ARCHIVE_URL,
                              timeout=httpx.Timeout(None, connect=30.0),
                              follow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                with cls._dl_lock:
                    cls._dl_state["total_bytes"] = total

                # _ChunkReader adapts the HTTP stream to a file-like object
                # that tarfile can read sequentially (r|gz pipe mode).
                class _ChunkReader(io.RawIOBase):
                    def __init__(self) -> None:
                        self._iter  = response.iter_bytes(chunk_size=65_536)
                        self._buf   = b""
                        self._bytes = 0

                    def readinto(self, b: bytearray) -> int:  # type: ignore[override]
                        want = len(b)
                        while len(self._buf) < want:
                            try:
                                chunk = next(self._iter)
                                self._buf   += chunk
                                self._bytes += len(chunk)
                                with cls._dl_lock:
                                    cls._dl_state["bytes_downloaded"] = self._bytes
                                    if total > 0:
                                        cls._dl_state["progress"] = min(
                                            self._bytes / total, 0.99)
                            except StopIteration:
                                break
                        n = min(want, len(self._buf))
                        b[:n] = self._buf[:n]
                        self._buf = self._buf[n:]
                        return n

                    def readable(self) -> bool:
                        return True

                reader = io.BufferedReader(_ChunkReader(), buffer_size=65_536)
                with tarfile.open(fileobj=reader, mode="r|gz") as tar:
                    for member in tar:
                        if member.isfile() and member.name.endswith(".mid"):
                            flat_name = member.name.replace("/", "_")
                            out_path  = cls._CACHE_DIR / flat_name
                            if not out_path.exists():
                                fobj = tar.extractfile(member)
                                if fobj:
                                    out_path.write_bytes(fobj.read())
                            with cls._dl_lock:
                                cls._dl_state["files_extracted"] += 1

            # Write sentinel for persistence across restarts
            sentinel_data = {
                "files_extracted":  cls._dl_state["files_extracted"],
                "bytes_downloaded": cls._dl_state["bytes_downloaded"],
                "total_bytes":      total,
            }
            cls._SENTINEL.write_text(json.dumps(sentinel_data))
            with cls._dl_lock:
                cls._dl_state["status"]   = "complete"
                cls._dl_state["progress"] = 1.0
            logger.info(
                f"[MidiCaps] archive extraction complete: "
                f"{cls._dl_state['files_extracted']} files"
            )

        except Exception as exc:
            logger.error(f"[MidiCaps] download worker failed: {exc}")
            with cls._dl_lock:
                cls._dl_state["status"] = "error"
                cls._dl_state["error"]  = str(exc)[:200]

    # ── Search (HF datasets-server API) ──────────────────────────────────────

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Apply genre alias map: expand short slang terms to caption-matching phrases
        search_query = query
        if query:
            search_query = _MIDICAPS_GENRE_ALIAS.get(query.lower().strip(), query)

        if search_query:
            # Full-text search endpoint (can be slow — 30 s timeout)
            try:
                params: dict[str, Any] = {
                    "dataset": "amaai-lab/MidiCaps",
                    "config":  "default",
                    "split":   "train",
                    "query":   search_query,
                    "offset":  offset,
                    "length":  limit,
                }
                r = httpx.get(f"{self._BASE}/search", params=params,
                              timeout=_TIMEOUT_SEARCH)
                r.raise_for_status()
                data  = r.json()
                rows  = data.get("rows", [])
                total = data.get("num_rows_total", len(rows))
                items = [i for i in (self._row_to_item(row.get("row", row)) for row in rows) if i]
                return {
                    "items":    items,
                    "total":    total,
                    "has_more": (offset + limit) < total,
                }
            except Exception as exc:
                logger.warning(f"[MidiCaps] /search failed ({exc}), trying multi-offset /rows sampling")

        # /rows with multi-offset sampling to cover the full 168k dataset
        try:
            total = 168_000  # approximate dataset size; real value returned below
            if search_query:
                # Sample 5 random windows spread across the dataset, 20 rows each
                # This gives ~100 candidates to client-filter for genre matches
                sample_offsets = random.sample(range(0, 160_000, 500), 5)
                raw_rows: list[dict] = []
                for soff in sample_offsets:
                    try:
                        params = {
                            "dataset": "amaai-lab/MidiCaps",
                            "config":  "default",
                            "split":   "train",
                            "offset":  soff,
                            "length":  20,
                        }
                        r = httpx.get(f"{self._BASE}/rows", params=params,
                                      timeout=_TIMEOUT_FAST)
                        r.raise_for_status()
                        data = r.json()
                        total = data.get("num_rows_total", total)
                        raw_rows.extend(row.get("row", row) for row in data.get("rows", []))
                    except Exception as e:
                        logger.debug(f"[MidiCaps] /rows at offset {soff} failed: {e}")
                # Client-side genre filter across all sampled candidates
                q_terms = search_query.lower().split()
                raw_rows = [
                    row for row in raw_rows
                    if any(
                        t in _as_str(row.get("caption")).lower()
                        or t in _as_str(row.get("genre")).lower()
                        or t in _as_str(row.get("instrument_summary")).lower()
                        for t in q_terms
                    )
                ]
            else:
                # No query — fetch a quality-sorted page at the requested offset
                fetch_len = limit * 4
                params = {
                    "dataset": "amaai-lab/MidiCaps",
                    "config":  "default",
                    "split":   "train",
                    "offset":  offset,
                    "length":  min(fetch_len, 100),
                }
                r = httpx.get(f"{self._BASE}/rows", params=params, timeout=_TIMEOUT_FAST)
                r.raise_for_status()
                data     = r.json()
                raw_rows = [row.get("row", row) for row in data.get("rows", [])]
                total    = data.get("num_rows_total", 0)
                raw_rows.sort(key=_midicaps_quality_score, reverse=True)

            items = [i for i in (self._row_to_item(row) for row in raw_rows[:limit]) if i]
            return {"items": items, "total": total,
                    "has_more": (offset + limit) < total}
        except Exception as exc:
            logger.error(f"[MidiCaps] /rows failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    _MIDI_EXTS = {".mid", ".midi"}

    def _row_to_item(self, row: dict) -> dict | None:
        location = row.get("location", row.get("midi_path", row.get("file_path", "")))
        if not location:
            return None
        # Skip non-MIDI extensions (.fmid, .midi.gz, etc.)
        if Path(location).suffix.lower() not in self._MIDI_EXTS:
            return None
        # Note: lmd_full/ paths are Lakh MIDI Dataset references (404 on HF direct download).
        # We include them in browse results for their rich metadata; download raises a clear error.
        stem     = Path(location).stem if location else _as_str(row.get("id", ""))
        caption  = _as_str(row.get("caption", row.get("text_description", "")))
        # MD5 hashes are meaningless as titles — derive one from the caption instead
        title    = _title_from_caption(caption) if _is_md5(stem) else (stem or "MIDI File")
        genre    = _as_str(row.get("genre", ""))
        bpm_val  = row.get("tempo", row.get("bpm", 0.0))
        key_name = _as_str(row.get("key_name", row.get("key", "")))
        key_mode = _as_str(row.get("key_mode", row.get("mode", "")))
        if key_mode and key_mode.lower() not in ("", "major"):
            key_str = f"{key_name}m" if key_mode.lower() == "minor" else f"{key_name} {key_mode}"
        else:
            key_str = key_name
        mood = _as_str(row.get("mood", row.get("moods", "")))

        # ── Instrument plugin selection ──────────────────────────────────────
        programs: list[int] = row.get("instrument_numbers_sorted") or []
        gm_info = _gm_to_plugin(programs)
        plugin = gm_info["plugin"]

        # ── Human-readable instrument summary for captions ───────────────────
        instr_names: list[str] = row.get("instrument_summary") or []
        tempo_word: str        = row.get("tempo_word", "") or ""
        # Build a richer caption line: instrument list + tempo word
        instr_str = ", ".join(instr_names[:4]) + ("…" if len(instr_names) > 4 else "")
        subtitle  = " · ".join(filter(None, [instr_str, tempo_word]))

        is_lmd = location.startswith("lmd_full/")
        return {
            "file_id":            _as_str(location),
            "title":              title,
            "caption":            caption,
            "subtitle":           subtitle,           # instrument list + tempo
            "genre":              genre,
            "bpm":                float(bpm_val) if bpm_val else 0.0,
            "key":                key_str,
            "mood":               mood,
            "plugin":             plugin,             # LMMS plugin to use on import
            "_download_available": not is_lmd,        # lmd_full/ = browse-only
        }

    # ── Download ─────────────────────────────────────────────────────────────

    def download(self, file_id: str) -> str:
        """Fetch a single MidiCaps MIDI file on-demand from HuggingFace.

        Note: The MidiCaps dataset references files from the Lakh MIDI Dataset
        (lmd_full/ paths).  These are NOT hosted on HuggingFace and return 404.
        Browse and filter work perfectly; download raises FileNotFoundError with
        a clear message directing the user to alternative databases.
        """
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if file_id.startswith("lmd_full/"):
            raise FileNotFoundError(
                "MidiCaps tracks are from the Lakh MIDI Dataset and are not "
                "available for individual download.\n"
                "Use the Groove MIDI, ldrolez Chords, or BitMidi databases "
                "for downloadable MIDI files."
            )
        filename = Path(file_id).name
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        url = f"https://huggingface.co/datasets/amaai-lab/MidiCaps/resolve/main/{file_id}"
        r = httpx.get(url, timeout=_TIMEOUT_DL, follow_redirects=True)
        if r.status_code == 404:
            raise FileNotFoundError(
                f"MidiCaps file not found on HuggingFace: {Path(file_id).name}. "
                f"Try a different result."
            )
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[MidiCaps] downloaded {filename} ({len(r.content)} bytes)")
        return str(cached)


# ── MAESTRO ───────────────────────────────────────────────────────────────────

class MaestroReader:
    # Correct bucket: magentadata (not magenta-datasets)
    _META_URL   = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.json"
    _FILE_BASE  = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/"
    _CACHE_DIR  = config.MIDI_LIBRARY_DIR / "maestro"
    _META_CACHE = config.MIDI_LIBRARY_DIR / "maestro_meta.json"

    def _load_meta(self) -> list[dict]:
        if self._META_CACHE.is_file():
            try:
                return json.loads(self._META_CACHE.read_text())
            except Exception:
                pass
        logger.info("[MAESTRO] downloading metadata JSON...")
        r = httpx.get(self._META_URL, timeout=_TIMEOUT_DL)
        r.raise_for_status()
        raw = r.json()
        # maestro-v3 JSON: {field: {str_idx: value}}
        if isinstance(raw, dict) and "midi_filename" in raw:
            midi_fn  = raw["midi_filename"]
            composer = raw.get("canonical_composer", {})
            title    = raw.get("canonical_title", {})
            year     = raw.get("year", {})
            split    = raw.get("split", {})
            records  = [
                {
                    "midi_filename":      midi_fn[k],
                    "canonical_composer": composer.get(k, ""),
                    "canonical_title":    title.get(k, ""),
                    "year":               str(year.get(k, "")),
                    "split":              split.get(k, ""),
                }
                for k in midi_fn
            ]
        elif isinstance(raw, list):
            records = raw
        else:
            records = []
        self._META_CACHE.write_text(json.dumps(records))
        logger.info(f"[MAESTRO] metadata cached: {len(records)} records")
        return records

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        try:
            records = self._load_meta()
        except Exception as exc:
            logger.error(f"[MAESTRO] metadata load failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}
        if query:
            q       = query.lower()
            records = [r for r in records
                       if q in r.get("canonical_composer", "").lower()
                       or q in r.get("canonical_title", "").lower()]
        total = len(records)
        page  = records[offset:offset + limit]
        return {
            "items":    [self._record_to_item(r) for r in page],
            "total":    total,
            "has_more": (offset + limit) < total,
        }

    def _record_to_item(self, r: dict) -> dict:
        fn       = r.get("midi_filename", "")
        composer = r.get("canonical_composer", "")
        title    = r.get("canonical_title", "")
        year     = str(r.get("year", ""))
        split    = r.get("split", "")
        display  = f"{composer} — {title}" if composer and title else (composer or title or fn)
        caption  = " · ".join(filter(None, [year, split]))
        return {
            "file_id": fn,
            "title":   display,
            "caption": caption,
            "genre":   "piano",
            "bpm":     0.0,
            "key":     "",
            "mood":    "",
        }

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id).name
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        url = self._FILE_BASE + file_id
        r   = httpx.get(url, timeout=_TIMEOUT_DL, follow_redirects=True)
        r.raise_for_status()
        data = r.content
        cached.write_bytes(data)
        logger.info(f"[MAESTRO] downloaded {filename} ({len(data)} bytes)")
        return str(cached)


# ── Groove MIDI ───────────────────────────────────────────────────────────────

class GrooveBrowser:
    # Correct bucket: magentadata (not magenta-datasets)
    # Individual files are NOT publicly accessible — use the MIDI-only zip (~6 MB)
    _ZIP_URL   = "https://storage.googleapis.com/magentadata/datasets/groove/groove-v1.0.0-midionly.zip"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "groove"
    _ZIP_CACHE = config.MIDI_LIBRARY_DIR / "groove.zip"
    _CSV_CACHE = config.MIDI_LIBRARY_DIR / "groove_meta.csv"

    def _ensure_zip(self) -> None:
        if self._ZIP_CACHE.is_file() and self._ZIP_CACHE.stat().st_size > 10_000:
            return
        logger.info("[Groove] downloading MIDI-only zip (~6 MB, one-time)...")
        r = httpx.get(self._ZIP_URL, timeout=120.0, follow_redirects=True)
        r.raise_for_status()
        self._ZIP_CACHE.write_bytes(r.content)
        logger.info(f"[Groove] zip cached ({self._ZIP_CACHE.stat().st_size:,} bytes)")

    def _load_meta(self) -> list[dict]:
        if self._CSV_CACHE.is_file():
            try:
                return list(csv.DictReader(self._CSV_CACHE.read_text().splitlines()))
            except Exception:
                pass
        self._ensure_zip()
        with zipfile.ZipFile(self._ZIP_CACHE) as zf:
            csv_name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
            if not csv_name:
                raise RuntimeError("info.csv not found in Groove MIDI zip")
            text = zf.read(csv_name).decode("utf-8")
        self._CSV_CACHE.write_text(text)
        records = list(csv.DictReader(text.splitlines()))
        logger.info(f"[Groove] metadata cached: {len(records)} records")
        return records

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        try:
            records = self._load_meta()
        except Exception as exc:
            logger.error(f"[Groove] metadata load failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}
        if query:
            # Parse multi-token query into independent style and type filters:
            # tokens matching "fill" or "beat" filter beat_type; others filter style/drummer
            style_q = type_q = None
            for token in query.lower().split():
                if token in ("fill", "beat"):
                    type_q = token
                elif token:
                    style_q = token
            if style_q:
                records = [r for r in records
                           if style_q in r.get("style",   "").lower()
                           or style_q in r.get("drummer", "").lower()]
            if type_q:
                records = [r for r in records
                           if type_q == r.get("beat_type", "").lower()]
        total = len(records)
        page  = records[offset:offset + limit]
        return {
            "items":    [self._record_to_item(r) for r in page],
            "total":    total,
            "has_more": (offset + limit) < total,
        }

    def _record_to_item(self, r: dict) -> dict:
        # Use midi_filename (full path with style/bpm suffix) as file_id so
        # download() can resolve it directly inside the zip.
        midi_fn  = r.get("midi_filename", r.get("id", ""))
        drummer  = r.get("drummer", "")
        style    = r.get("style",   "")
        subgenre = r.get("beat_type", "")  # "fill" or "beat"
        bpm_str  = r.get("bpm", "0")
        try:
            bpm_val = float(bpm_str)
        except (ValueError, TypeError):
            bpm_val = 0.0

        # Extract the sequential pattern number from the filename for a unique title.
        # Filename stem format: "1_funk-groove1_116_fill_4-4"  →  seq = "1"
        stem = Path(midi_fn).stem if midi_fn else ""
        first = stem.split("_")[0] if stem else ""
        seq   = first if first.isdigit() else ""

        # Build a unique, readable title: "jazz/funk — fill #1 (116 BPM)"
        if style and subgenre and seq and bpm_val:
            title = f"{style} — {subgenre} #{seq} ({int(bpm_val)} BPM)"
        elif style and subgenre and seq:
            title = f"{style} — {subgenre} #{seq}"
        else:
            title = f"{drummer} — {style}" if drummer and style else (drummer or style or midi_fn)

        caption = " · ".join(filter(None, [drummer, style, subgenre]))
        return {
            "file_id": midi_fn,
            "title":   title,
            "caption": caption,
            "genre":   "drums",
            "bpm":     bpm_val,
            "key":     "",
            "mood":    "",
        }

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # file_id is the midi_filename column value, e.g.
        # "drummer1/eval_session/1_funk-groove1_138_beat_4-4.mid"
        # In the zip it lives under "groove/<midi_filename>"
        safe_name = file_id.replace("/", "_")
        if not safe_name.endswith(".mid"):
            safe_name += ".mid"
        cached = self._CACHE_DIR / safe_name
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        self._ensure_zip()
        with zipfile.ZipFile(self._ZIP_CACHE) as zf:
            all_names = zf.namelist()
            # Primary: zip always stores files under "groove/" prefix
            primary = f"groove/{file_id}"
            if not primary.endswith(".mid"):
                primary += ".mid"
            data: bytes | None = None
            if primary in all_names:
                data = zf.read(primary)
            else:
                # Fallback: match by filename stem anywhere in zip
                stem = Path(file_id).stem
                matches = [n for n in all_names if Path(n).stem == stem]
                if matches:
                    data = zf.read(matches[0])
        if not data:
            raise FileNotFoundError(f"MIDI not found in Groove zip: {file_id!r}")
        cached.write_bytes(data)
        logger.info(f"[Groove] extracted {safe_name} ({len(data)} bytes)")
        return str(cached)


# ── Mutopia Project ───────────────────────────────────────────────────────────

from html.parser import HTMLParser as _HTMLParser


class _MutopiaTableParser(_HTMLParser):
    """Parse the HTML table returned by Mutopia's make-table.cgi.

    Each result row (class="even" or "odd") has 6 <td> cells:
      0: title + link to piece-info.cgi
      1: composer
      2: instrument
      3: style
      4: license
      5: MIDI download link (href ends in .mid)
    """

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._in_row  = False
        self._td_idx  = 0
        self._current: dict = {}
        self._buf     = ""
        self._href    = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        ad = dict(attrs)
        if tag == "tr" and ad.get("class", "") in ("even", "odd"):
            self._in_row = True
            self._td_idx = 0
            self._current = {}
        elif tag == "td" and self._in_row:
            self._buf  = ""
            self._href = ""
        elif tag == "a" and self._in_row:
            self._href = ad.get("href", "")

    def handle_data(self, data: str) -> None:
        if self._in_row:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_row:
            val = self._buf.strip()
            if self._td_idx == 0:
                self._current["title"] = val
            elif self._td_idx == 1:
                self._current["composer"] = val
            elif self._td_idx == 2:
                self._current["instrument"] = val
            elif self._td_idx == 3:
                self._current["style"] = val
            elif self._td_idx == 4:
                self._current["license"] = val
            elif self._td_idx == 5 and self._href.endswith(".mid"):
                self._current["midi_href"] = self._href
            self._td_idx += 1
        elif tag == "tr" and self._in_row:
            if self._current.get("midi_href") and self._current.get("title"):
                self.results.append(self._current)
            self._in_row = False


class MutopiaOrgBrowser:
    """Browse Mutopia Project — ~2,400 free-licensed classical MIDI files."""

    _BASE      = "https://www.mutopiaproject.org"
    _CGI       = "https://www.mutopiaproject.org/cgibin/make-table.cgi"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "mutopia"
    _HEADERS   = {"User-Agent": "WavyLabs/1.0 (MIDI browser; +https://wavylabs.com)"}

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        try:
            params = {
                "searchingfor": query,
                "request":      "Start",
                "timelimit":    0,
                "order":        "date",
            }
            r = httpx.get(self._CGI, params=params, timeout=_TIMEOUT_SEARCH,
                          headers=self._HEADERS, follow_redirects=True)
            r.raise_for_status()
            parser = _MutopiaTableParser()
            parser.feed(r.text)
            results = parser.results
            total   = len(results)
            page    = results[offset:offset + limit]
            return {
                "items":    [self._to_item(x) for x in page],
                "total":    total,
                "has_more": (offset + limit) < total,
            }
        except Exception as exc:
            logger.error(f"[Mutopia] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    def _to_item(self, r: dict) -> dict:
        href      = r.get("midi_href", "")
        file_id   = href if href.startswith("http") else (self._BASE + href if href else "")
        composer  = r.get("composer", "")
        title     = r.get("title",    "")
        display   = f"{composer} — {title}" if composer and title else (composer or title)
        instr     = r.get("instrument", "")
        style     = r.get("style", "")
        caption   = " · ".join(filter(None, [instr, style]))
        return {
            "file_id": file_id,
            "title":   display,
            "caption": caption,
            "genre":   style.lower() if style else "classical",
            "bpm":     0.0,
            "key":     "",
            "mood":    r.get("license", ""),
        }

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id.split("?")[0]).name or "mutopia.mid"
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        r = httpx.get(file_id, timeout=_TIMEOUT_DL, headers=self._HEADERS,
                      follow_redirects=True)
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[Mutopia] downloaded {filename} ({len(r.content)} bytes)")
        return str(cached)


# ── VGMusic ───────────────────────────────────────────────────────────────────

class _VGMusicParser(_HTMLParser):
    """Parse VGMusic.com section pages — extract <a href="*.mid"> links."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._href   = ""
        self._in_a   = False
        self._buf    = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "a":
            return
        ad   = dict(attrs)
        href = ad.get("href", "")
        if href and href.endswith(".mid") and not href.startswith("http"):
            self._href = href
            self._in_a = True
            self._buf  = ""

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a:
            title = self._buf.strip()
            if title and self._href:
                self.results.append({"href": self._href, "title": title})
            self._in_a = False
            self._href = ""
            self._buf  = ""


# Query hint → (display name, section URL)
_VGMUSIC_SECTIONS: dict[str, tuple[str, str]] = {
    "nes":     ("NES",          "https://vgmusic.com/music/console/nintendo/nes/"),
    "snes":    ("SNES",         "https://vgmusic.com/music/console/nintendo/snes/"),
    "n64":     ("Nintendo 64",  "https://vgmusic.com/music/console/nintendo/n64/"),
    "gba":     ("Game Boy",     "https://vgmusic.com/music/console/nintendo/gba/"),
    "ps1":     ("PlayStation",  "https://vgmusic.com/music/console/sony/psx/"),
    "ps2":     ("PS2",          "https://vgmusic.com/music/console/sony/ps2/"),
    "genesis": ("Sega Genesis", "https://vgmusic.com/music/console/sega/genesis/"),
    "pc":      ("PC / DOS",     "https://vgmusic.com/music/computer/pc/"),
    "arcade":  ("Arcade",       "https://vgmusic.com/music/arcade/"),
}
_VGMUSIC_DEFAULT = "nes"


class VGMusicBrowser:
    """Browse VGMusic.com — thousands of video-game MIDI files by platform."""

    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "vgmusic"
    _HEADERS   = {"User-Agent": "WavyLabs/1.0 (MIDI browser; +https://wavylabs.com)"}

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        key = query.strip().lower()
        if key not in _VGMUSIC_SECTIONS:
            key = _VGMUSIC_DEFAULT
        label, url = _VGMUSIC_SECTIONS[key]
        try:
            r = httpx.get(url, timeout=_TIMEOUT_FAST, headers=self._HEADERS,
                          follow_redirects=True)
            r.raise_for_status()
            parser = _VGMusicParser()
            parser.feed(r.text)
            results = parser.results
            total   = len(results)
            page    = results[offset:offset + limit]
            items = [
                {
                    "file_id": url + item["href"],
                    "title":   item["title"],
                    "caption": label,
                    "genre":   "game music",
                    "bpm":     0.0,
                    "key":     "",
                    "mood":    "",
                }
                for item in page
            ]
            return {
                "items":    items,
                "total":    total,
                "has_more": (offset + limit) < total,
            }
        except Exception as exc:
            logger.error(f"[VGMusic] browse failed ({key}): {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id.split("?")[0]).name or "vgmusic.mid"
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        r = httpx.get(file_id, timeout=_TIMEOUT_DL, headers=self._HEADERS,
                      follow_redirects=True)
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[VGMusic] downloaded {filename} ({len(r.content)} bytes)")
        return str(cached)


# ── BitMidi ───────────────────────────────────────────────────────────────────

# Valid genre hints for BitMidi pagination (maps to different page ranges)
_BITMIDI_GENRES = {"lofi", "trap", "house", "jazz", "ambient"}


class BitMidiBrowser:
    """Browse BitMidi by genre via pagination.

    BitMidi's ?q= search is JavaScript-rendered (server ignores it), so we use
    the genre → page-offset mapping from midi_library.py.  The query is treated
    as a genre hint; any unrecognised value falls back to "default".
    """

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        from utils.midi_library import search_bitmidi, _GENRE_PAGE_OFFSETS

        genre = query.strip().lower() if query.strip().lower() in _BITMIDI_GENRES else "default"

        # BitMidi pages contain ~15 items (not a round 20)
        bitmidi_page_size = 15
        page_num = offset // bitmidi_page_size  # 0-based page index
        base_page = _GENRE_PAGE_OFFSETS.get(genre, _GENRE_PAGE_OFFSETS["default"])
        target_page = base_page + page_num + 1  # BitMidi pages are 1-based

        results = search_bitmidi(genre, limit=limit, page=target_page)
        items = [
            {
                "file_id": r["slug"],
                "title":   r["title"],
                "caption": f"Genre hint: {genre}",
                "genre":   genre if genre != "default" else "",
                "bpm":     0.0,
                "key":     "",
                "mood":    "",
            }
            for r in results
        ]
        # BitMidi has thousands of pages — has_more is true if we got any results
        return {
            "items":    items,
            "total":    offset + len(items) + (100 if items else 0),
            "has_more": len(items) > 0,
        }

    def download(self, file_id: str) -> str:
        from utils.midi_library import download_midi

        # file_id is the slug, e.g. "thriller-mid"
        title = file_id.replace("-mid", "").replace("-", " ").title()
        path  = download_midi(file_id, title)
        if path is None:
            raise RuntimeError(f"BitMidi download failed for slug: {file_id!r}")
        return str(path)


# ── GigaMIDI ──────────────────────────────────────────────────────────────────

class GigaMidiBrowser:
    """Browse GigaMIDI (Metacreation/GigaMIDI) via HuggingFace datasets-server.

    2.1 million MIDI files with genre/artist metadata.  Text search uses
    HuggingFace's /search endpoint; plain browse uses /rows.
    Downloads are resolved via the HuggingFace repo blob URL.
    """

    _DATASET    = "Metacreation/GigaMIDI"
    _BASE       = "https://datasets-server.huggingface.co"
    _HF_RESOLVE = "https://huggingface.co/datasets/Metacreation/GigaMIDI/resolve/main"
    _CACHE_DIR  = config.MIDI_LIBRARY_DIR / "gigamidi"

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        try:
            if query:
                url    = f"{self._BASE}/search"
                params = {
                    "dataset": self._DATASET,
                    "config":  "default",
                    "split":   "train",
                    "query":   query,
                    "offset":  offset,
                    "length":  limit,
                }
            else:
                url    = f"{self._BASE}/rows"
                params = {
                    "dataset": self._DATASET,
                    "config":  "default",
                    "split":   "train",
                    "offset":  offset,
                    "length":  limit,
                }
            r = httpx.get(url, params=params, timeout=_TIMEOUT_SEARCH,
                          follow_redirects=True)
            r.raise_for_status()
            data  = r.json()
            rows  = data.get("rows", [])
            total = data.get("num_rows_total", len(rows))
            items = [i for i in (self._row_to_item(row) for row in rows) if i]
            return {
                "items":    items,
                "total":    total,
                "has_more": (offset + len(rows)) < total,
            }
        except Exception as exc:
            # 401 = dataset is gated on HuggingFace (requires HF token) — not a local error
            msg = str(exc)
            if "401" in msg:
                logger.debug(f"[GigaMIDI] dataset requires HuggingFace auth (gated): {msg}")
            else:
                logger.warning(f"[GigaMIDI] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False}

    def _row_to_item(self, row: dict) -> dict | None:
        r = row.get("row", row)  # datasets-server wraps: {"row": {...}, "row_idx": N}
        # Try multiple common field names for file path
        location = (r.get("location")
                    or r.get("midi_path")
                    or r.get("file_path")
                    or r.get("filename")
                    or r.get("path")
                    or "")
        if not location:
            return None
        # Metadata (field names vary by dataset version)
        title  = _as_str(r.get("title") or r.get("name") or "")
        if not title:
            title = Path(location).stem.replace("_", " ").replace("-", " ").title()
        artist = _as_str(r.get("artist") or r.get("artist_name") or r.get("composer") or "")
        genre  = _as_str(r.get("genre")  or r.get("style") or "")
        bpm    = 0.0
        try:
            bpm = float(r.get("bpm") or r.get("tempo") or 0)
        except (ValueError, TypeError):
            pass
        key = _as_str(r.get("key") or r.get("key_signature") or "")
        return {
            "file_id": location,
            "title":   f"{artist} — {title}" if artist else title,
            "caption": artist,
            "genre":   genre,
            "bpm":     bpm,
            "key":     key,
            "mood":    "",
        }

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id).name or "gigamidi.mid"
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        url  = f"{self._HF_RESOLVE}/{file_id}"
        r    = httpx.get(url, timeout=_TIMEOUT_DL, follow_redirects=True)
        r.raise_for_status()
        data = r.content
        if not data[:4] == b"MThd":
            raise ValueError(f"Not a valid MIDI file: {file_id!r}")
        cached.write_bytes(data)
        logger.info(f"[GigaMIDI] downloaded {filename} ({len(data)} bytes)")
        return str(cached)


# ── Piano-midi.de ─────────────────────────────────────────────────────────────

# Mapping of query key → (slug used in URL, display name)
_PIANOMIDI_COMPOSERS: dict[str, tuple[str, str]] = {
    "albeniz":      ("albeniz",      "Albéniz"),
    "bach":         ("bach",         "Bach"),
    "beethoven":    ("beethoven",    "Beethoven"),
    "brahms":       ("brahms",       "Brahms"),
    "chopin":       ("chopin",       "Chopin"),
    "debussy":      ("debussy",      "Debussy"),
    "grieg":        ("grieg",        "Grieg"),
    "handel":       ("handel",       "Handel"),
    "haydn":        ("haydn",        "haydn"),
    "liszt":        ("liszt",        "Liszt"),
    "mendelssohn":  ("mendels",      "Mendelssohn"),
    "mozart":       ("mozart",       "Mozart"),
    "mussorgsky":   ("mussorgs",     "Mussorgsky"),
    "rachmaninoff": ("rachm",        "Rachmaninoff"),
    "scarlatti":    ("scarlatti",    "Scarlatti"),
    "schumann":     ("schumann",     "Schumann"),
    "schubert":     ("schubert",     "Schubert"),
    "scriabin":     ("scriab",       "Scriabin"),
    "tchaikovsky":  ("tschai",       "Tchaikovsky"),
}
_PIANOMIDI_DEFAULT = "chopin"


class _PianoMidiDeParser(_HTMLParser):
    """Parse piano-midi.de composer pages — collect <a href="*.mid"> links."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._href  = ""
        self._in_a  = False
        self._buf   = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if href and ".mid" in href.lower():
            self._href = href
            self._in_a = True
            self._buf  = ""

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a:
            title = self._buf.strip()
            if title and self._href:
                self.results.append({"href": self._href, "title": title})
            self._in_a = False
            self._href = ""
            self._buf  = ""


class PianoMidiDeBrowser:
    """Browse piano-midi.de — high-quality curated classical piano MIDI.

    Each query is matched against the composer list; unrecognised queries
    default to Chopin.  Lists 50–100 pieces per composer.
    """

    _BASE      = "http://piano-midi.de"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "pianomidide"
    _HEADERS   = {"User-Agent": "WavyLabs/1.0 (MIDI browser; +https://wavylabs.com)"}

    def _match_composer(self, query: str) -> tuple[str, str]:
        """Return (slug, display_name) for the closest composer match."""
        q = query.strip().lower()
        for key, (slug, display) in _PIANOMIDI_COMPOSERS.items():
            if q in key or q in display.lower():
                return slug, display
        slug, display = _PIANOMIDI_COMPOSERS[_PIANOMIDI_DEFAULT]
        return slug, display

    def _fetch_composer(self, slug: str, display: str) -> list[dict]:
        url = f"{self._BASE}/{slug}.htm"
        r   = httpx.get(url, timeout=_TIMEOUT_SEARCH, headers=self._HEADERS,
                        follow_redirects=True)
        r.raise_for_status()
        parser = _PianoMidiDeParser()
        parser.feed(r.text)
        items = []
        for entry in parser.results:
            href = entry["href"]
            # Resolve relative hrefs
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = self._BASE + href
            else:
                full_url = f"{self._BASE}/midis/{slug}/{href}"
            items.append({
                "file_id": full_url,
                "title":   f"{display} — {entry['title']}",
                "caption": "Classical Piano",
                "genre":   "classical",
                "bpm":     0.0,
                "key":     "",
                "mood":    "",
            })
        return items

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        try:
            slug, display = self._match_composer(query) if query else \
                _PIANOMIDI_COMPOSERS[_PIANOMIDI_DEFAULT]
            items = self._fetch_composer(slug, display)
            total = len(items)
            return {
                "items":    items[offset:offset + limit],
                "total":    total,
                "has_more": (offset + limit) < total,
            }
        except Exception as exc:
            logger.error(f"[PianoMidiDe] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id.split("?")[0]).name or "pianomidide.mid"
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        r    = httpx.get(file_id, timeout=_TIMEOUT_DL, headers=self._HEADERS,
                         follow_redirects=True)
        r.raise_for_status()
        data = r.content
        if not data[:4] == b"MThd":
            raise ValueError(f"Not a valid MIDI file: {file_id!r}")
        cached.write_bytes(data)
        logger.info(f"[PianoMidiDe] downloaded {filename} ({len(data)} bytes)")
        return str(cached)


# ── Discover MIDI (HuggingFace) ────────────────────────────────────────────────

class DiscoverMidiBrowser:
    _HF_API   = "https://datasets-server.huggingface.co"
    _HF_REPO  = "projectlosangeles/Discover-MIDI-Dataset"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "discovermidi"

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if query:
                url = (f"{self._HF_API}/search"
                       f"?dataset={self._HF_REPO}&config=default&split=train"
                       f"&query={query}&offset={offset}&length={limit}")
                r = httpx.get(url, timeout=_TIMEOUT_SEARCH)
            else:
                url = (f"{self._HF_API}/rows"
                       f"?dataset={self._HF_REPO}&config=default&split=train"
                       f"&offset={offset}&length={limit}")
                r = httpx.get(url, timeout=_TIMEOUT_FAST)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning(f"[DiscoverMIDI] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False}

        rows  = data.get("rows", [])
        total = data.get("num_rows_total", len(rows))
        items = []
        for row in rows:
            rd = row.get("row", row)
            location = _as_str(
                rd.get("location") or rd.get("file_path") or rd.get("midi_path") or ""
            )
            if not location:
                continue
            title = _as_str(rd.get("title") or rd.get("artist") or Path(location).stem)
            genre = _as_str(rd.get("genre") or rd.get("style") or "")
            try:
                bpm_val = float(rd.get("bpm") or 0)
            except (TypeError, ValueError):
                bpm_val = 0.0
            quality = rd.get("quality_score") or rd.get("score") or ""
            subtitle_parts: list[str] = []
            if genre:        subtitle_parts.append(genre)
            if bpm_val > 0:  subtitle_parts.append(f"{int(bpm_val)} BPM")
            if quality:      subtitle_parts.append(f"score: {quality}")
            items.append({
                "title":    title,
                "file_id":  location,
                "genre":    genre,
                "bpm":      bpm_val,
                "plugin":   "sf2player",
                "subtitle": "  ·  ".join(subtitle_parts),
            })
        has_more = (offset + len(items)) < total
        return {"items": items, "total": total, "has_more": has_more}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file_id).name or "discover.mid"
        cached   = self._CACHE_DIR / filename
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        url = f"https://huggingface.co/datasets/{self._HF_REPO}/resolve/main/{file_id}"
        r = httpx.get(url, timeout=_TIMEOUT_DL, follow_redirects=True)
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[DiscoverMIDI] downloaded {filename} ({len(r.content)} bytes)")
        return str(cached)


# ── Freesound ──────────────────────────────────────────────────────────────────

class FreesoundBrowser:
    _API_BASE  = "https://freesound.org/apiv2"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "freesound"

    # Maps query terms → Freesound tags for better filtering
    _TAG_MAP: dict[str, str] = {
        "trap":         "trap",
        "drill":        "drill",
        "house":        "house",
        "techno":       "techno",
        "r&b":          "rnb",
        "rnb":          "rnb",
        "soul":         "soul",
        "funk":         "funk",
        "jazz":         "jazz",
        "blues":        "blues",
        "pop":          "pop",
        "rock":         "rock",
        "garage":       "garage",
        "bass":         "bass",
        "808":          "808",
        "loop":         "loop",
        "beat":         "beat",
        "sample":       "sample",
        "pad":          "pad",
        "synth":        "synth",
        "drum":         "drums",
        "vocal":        "vocals",
        "sfx":          "sfx",
        "texture":      "texture",
        "ambient":      "ambient",
        "lofi":         "lofi",
        "lo-fi":        "lofi",
        # NCS / Electronic tags (v0.9.9)
        "futurebass":   "future-bass",
        "future bass":  "future-bass",
        "supersaw":     "supersaw",
        "riser":        "riser",
        "downlifter":   "downlifter",
        "impact":       "impact",
        "vocalchop":    "vocal-chop",
        "vocal chop":   "vocal-chop",
        "edm":          "edm",
        "dubstep":      "dubstep",
        "melodic":      "melodic",
        "anthem":       "anthem",
        "festival":     "festival",
        "transition":   "transition",
        "crash":        "crash",
        "white noise":  "white-noise",
    }

    def _api_key(self) -> str:
        import config as _cfg
        return getattr(_cfg, "FREESOUND_API_KEY", "")

    def _headers(self) -> dict:
        key = self._api_key()
        return {"Authorization": f"Token {key}"} if key else {}

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not self._api_key():
            return {"items": [], "total": 0, "has_more": False,
                    "error": "FREESOUND_API_KEY not set"}
        q_lower = query.lower().strip()
        # Find a matching tag from our map
        tag = next((v for k, v in self._TAG_MAP.items() if k in q_lower), None)
        # Build filter: audio types only, optionally tag-filtered
        filter_parts = ["type:(wav OR mp3 OR aiff)"]
        if tag:
            filter_parts.append(f"tag:{tag}")
        params: dict[str, Any] = {
            "query":     query or "music loop",
            "filter":    " ".join(filter_parts),
            "fields":    "id,name,tags,license,previews,username,duration",
            "sort":      "rating_desc",
            "page_size": limit,
            "page":      (offset // limit) + 1,
        }
        try:
            r = httpx.get(f"{self._API_BASE}/search/text/",
                          params=params, headers=self._headers(),
                          timeout=_TIMEOUT_SEARCH)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning(f"[Freesound] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False}

        results = data.get("results", [])
        total   = data.get("count", len(results))
        items   = []
        for s in results:
            previews    = s.get("previews") or {}
            preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or ""
            dur = s.get("duration", 0)
            dur_str = f"{dur:.1f}s" if dur else ""
            items.append({
                "title":    s.get("name", ""),
                "file_id":  str(s.get("id", "")),
                "format":   "audio",
                "subtitle": "by " + s.get("username", ""),
                "caption":  " · ".join(s.get("tags", [])[:6]),
                "genre":    tag or "",
                "bpm":      0.0,
                "key":      dur_str,
                "plugin":   "",
                "_preview": preview_url,
                "_download_available": True,
            })
        has_more = data.get("next") is not None
        return {"items": items, "total": total, "has_more": has_more}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_mp3 = self._CACHE_DIR / f"freesound_{file_id}.mp3"
        cached_wav = self._CACHE_DIR / f"freesound_{file_id}.wav"
        for c in (cached_wav, cached_mp3):
            if c.is_file() and c.stat().st_size > 1024:
                return str(c)
        if not self._api_key():
            raise RuntimeError("FREESOUND_API_KEY not set")
        # Fetch sound detail
        r = httpx.get(f"{self._API_BASE}/sounds/{file_id}/",
                      headers=self._headers(), timeout=_TIMEOUT_FAST)
        r.raise_for_status()
        detail   = r.json()
        previews = detail.get("previews") or {}
        preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or ""
        if not preview_url:
            raise RuntimeError(f"No preview URL for Freesound {file_id}")
        r2 = httpx.get(preview_url, timeout=_TIMEOUT_DL, follow_redirects=True)
        r2.raise_for_status()
        cached_mp3.write_bytes(r2.content)
        logger.info(f"[Freesound] downloaded preview {file_id} ({len(r2.content)} bytes)")
        return str(cached_mp3)

    # NCS preset searches (v0.9.9)
    _NCS_PRESET_SEARCHES: dict[str, str] = {
        "808":         "808 bass sub",
        "risers":      "riser transition edm",
        "impacts":     "impact hit boom edm",
        "vocal_chops": "vocal chop edm future bass",
        "crashes":     "cymbal crash edm",
        "leads":       "synth lead edm future bass",
        "pads":        "supersaw pad synth",
        "transitions": "downlifter uplifter transition",
    }

    def ncs_toolkit_search(self, category: str, offset: int = 0,
                           limit: int = 20) -> dict:
        """Preset NCS-category search for the NCS Toolkit browser panel.

        category: One of "808", "risers", "impacts", "vocal_chops",
                  "crashes", "leads", "pads", "transitions".
        """
        query = self._NCS_PRESET_SEARCHES.get(
            category.lower().replace(" ", "_"),
            f"{category} edm"
        )
        return self.search(query=query, offset=offset, limit=limit)


# ── WaivOps Drums (GitHub raw / LFS — CC BY 4.0) ──────────────────────────────

class WaivOpsBrowser:
    _REPOS: dict[str, str] = {
        "trap":  "patchbanks/WaivOps-HH-TRP",
        "house": "patchbanks/WaivOps-EDM-HSE",
        "808":   "patchbanks/WaivOps-EDM-TR8",
    }
    _API_URL    = "https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
    _AUDIO_URL  = "https://raw.githubusercontent.com/{repo}/main/{path}"
    _CACHE_DIR  = config.MIDI_LIBRARY_DIR / "waivops"
    _META_TTL   = 86400  # 24h

    def _get_files(self, style: str) -> list[dict]:
        import time
        repo       = self._REPOS.get(style, self._REPOS["trap"])
        meta_cache = self._CACHE_DIR / f"tree_{style}.json"
        if meta_cache.is_file():
            try:
                if (time.time() - meta_cache.stat().st_mtime) < self._META_TTL:
                    return json.loads(meta_cache.read_text())
            except Exception:
                pass
        r = httpx.get(self._API_URL.format(repo=repo), timeout=_TIMEOUT_SEARCH,
                      headers={"Accept": "application/vnd.github.v3+json"})
        r.raise_for_status()
        tree  = r.json().get("tree", [])
        # Repos now ship .mp3 examples (no .wav in tree)
        files = [
            {"path": item["path"], "repo": repo}
            for item in tree
            if item.get("type") == "blob"
            and item["path"].lower().endswith((".wav", ".mp3", ".aiff"))
        ]
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Don't cache empty results — force a fresh API call next time
        if files:
            meta_cache.write_text(json.dumps(files))
        return files

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        q_lower = query.lower()
        style = next((s for s in ("house", "808", "trap") if s in q_lower), "trap")
        try:
            all_files = self._get_files(style)
        except Exception as exc:
            logger.warning(f"[WaivOps] listing failed for {style}: {exc}")
            return {"items": [], "total": 0, "has_more": False}
        if query and style not in q_lower:
            all_files = [f for f in all_files if q_lower in f["path"].lower()]
        page  = all_files[offset:offset + limit]
        items = []
        for f in page:
            name    = Path(f["path"]).stem
            file_id = f"{style}/{f['path']}"
            items.append({
                "title":    name,
                "file_id":  file_id,
                "format":   "audio",
                "genre":    style,
                "plugin":   "sf2player",
                "subtitle": style.upper() + " loop",
            })
        return {"items": items, "total": len(all_files),
                "has_more": (offset + limit) < len(all_files)}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        parts  = file_id.split("/", 1)
        style  = parts[0] if len(parts) > 1 else "trap"
        path   = parts[1] if len(parts) > 1 else file_id
        repo   = self._REPOS.get(style, self._REPOS["trap"])
        cached = self._CACHE_DIR / Path(path).name
        if cached.is_file() and cached.stat().st_size > 1024:
            return str(cached)
        url = self._AUDIO_URL.format(repo=repo, path=path)
        r   = httpx.get(url, timeout=_TIMEOUT_DL, follow_redirects=True)
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[WaivOps] downloaded {Path(path).name} ({len(r.content)} bytes)")
        return str(cached)


# ── HookTheory Chord Progressions → MIDI ──────────────────────────────────────

class HookTheoryBrowser:
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "hooktheory"

    _GENRE_PROGRESSIONS: dict[str, list[dict]] = {
        "trap":     [
            {"name": "Dark Minor (i–VII–VI–VII)",  "degrees": [1, 7, 6, 7], "mode": "minor"},
            {"name": "Rage Loop (i–VI–III–VII)",   "degrees": [1, 6, 3, 7], "mode": "minor"},
            {"name": "Sad Trap (i–v–VI–III)",      "degrees": [1, 5, 6, 3], "mode": "minor"},
        ],
        "rnb":      [
            {"name": "R&B Smooth (I–IV–ii–V)",     "degrees": [1, 4, 2, 5], "mode": "major"},
            {"name": "Soul Groove (I–vi–ii–V)",    "degrees": [1, 6, 2, 5], "mode": "major"},
            {"name": "ii–V–I",                     "degrees": [2, 5, 1],    "mode": "major"},
        ],
        "house":    [
            {"name": "Classic House (I–V–vi–IV)",  "degrees": [1, 5, 6, 4], "mode": "major"},
            {"name": "Club Loop (I–VI–IV–V)",      "degrees": [1, 6, 4, 5], "mode": "major"},
        ],
        "neo-soul": [
            {"name": "Neo-Soul Maj7 (I–IV–ii–V)",  "degrees": [1, 4, 2, 5], "mode": "major"},
            {"name": "Dreamy (vi–IV–I–V)",         "degrees": [6, 4, 1, 5], "mode": "major"},
        ],
        "pop":      [
            {"name": "Pop I–V–vi–IV",              "degrees": [1, 5, 6, 4], "mode": "major"},
            {"name": "Pop vi–IV–I–V",              "degrees": [6, 4, 1, 5], "mode": "major"},
        ],
        "drill":    [
            {"name": "UK Drill (i–VII–VI–v)",      "degrees": [1, 7, 6, 5], "mode": "minor"},
            {"name": "Drill Dark (i–VI–III–VII)",  "degrees": [1, 6, 3, 7], "mode": "minor"},
        ],
        "jazz":     [
            {"name": "ii–V–I (Jazz)",              "degrees": [2, 5, 1],    "mode": "major"},
            {"name": "I–vi–ii–V (Rhythm Changes)", "degrees": [1, 6, 2, 5], "mode": "major"},
        ],
    }

    _MINOR_INTERVALS = [0, 2, 3, 5, 7, 8, 10]
    _MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]

    def _degree_to_root(self, degree: int, mode: str, root_midi: int = 60) -> int:
        intervals = self._MINOR_INTERVALS if mode == "minor" else self._MAJOR_INTERVALS
        idx = (degree - 1) % 7
        octave = (degree - 1) // 7
        return root_midi + intervals[idx] + octave * 12

    def _make_chord(self, root: int, mode: str, degree: int) -> list[int]:
        minor_degrees = {1, 2, 4, 5} if mode == "minor" else {2, 3, 6}
        third = 3 if degree in minor_degrees else 4
        return [root, root + third, root + 7]

    def _progression_to_midi(self, prog: dict, key_root: int = 60) -> bytes:
        import mido
        import io as _io
        tpb   = 480
        tempo = int(60_000_000 / 120)  # 120 BPM (standard; LMMS ignores this anyway)
        chord_ticks = tpb * 4          # one chord = 4 beats
        mid   = mido.MidiFile(type=0, ticks_per_beat=tpb)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        track.append(mido.Message("program_change", channel=0, program=0, time=0))
        mode    = prog.get("mode", "major")
        degrees = prog.get("degrees", [1, 4, 5, 1])
        for deg in degrees:
            root  = self._degree_to_root(deg, mode, key_root)
            notes = self._make_chord(root, mode, deg)
            for i, n in enumerate(notes):
                track.append(mido.Message("note_on",  channel=0, note=n, velocity=80, time=0))
            for i, n in enumerate(notes):
                track.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                                          time=(chord_ticks if i == 0 else 0)))
        track.append(mido.MetaMessage("end_of_track", time=0))
        buf = _io.BytesIO()
        mid.save(file=buf)
        return buf.getvalue()

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        q_lower = query.lower()
        genre   = next(
            (g for g in self._GENRE_PROGRESSIONS if g in q_lower or q_lower in g),
            "trap"
        )
        progs = self._GENRE_PROGRESSIONS[genre]
        items = [
            {
                "title":    prog["name"],
                "file_id":  f"{genre}_{i}",
                "genre":    genre,
                "plugin":   "sf2player",
                "subtitle": f"{prog['mode'].capitalize()} · {len(prog['degrees'])} chords",
            }
            for i, prog in enumerate(progs)
        ]
        return {"items": items[offset:offset + limit],
                "total": len(items), "has_more": False}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = self._CACHE_DIR / f"{file_id.replace('/', '_')}.mid"
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        parts = file_id.rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid HookTheory file_id: {file_id!r}")
        genre, idx_str = parts
        try:
            idx = int(idx_str)
        except ValueError:
            raise ValueError(f"Invalid HookTheory file_id: {file_id!r}")
        progs = self._GENRE_PROGRESSIONS.get(genre)
        if not progs or idx >= len(progs):
            raise ValueError(f"Unknown progression: {file_id!r}")
        midi_bytes = self._progression_to_midi(progs[idx])
        cached.write_bytes(midi_bytes)
        logger.info(f"[HookTheory] generated {cached.name}")
        return str(cached)


# ── ldrolez Free MIDI Chords (GitHub releases — MIT license) ──────────────────
# The repo restructured: MIDI files are now only in release zips, organised as:
#   <key folder>/<len>/<Major|Minor>/<style> style/<key> - <chords> - <mood>.mid
# Style folders in the zip: hiphop2 style, pop style, pop2 style, soul style

class LdrolezChordBrowser:
    _API_RELEASES = "https://api.github.com/repos/ldrolez/free-midi-chords/releases/latest"
    _CACHE_DIR    = config.MIDI_LIBRARY_DIR / "ldrolez"
    _ZIP_CACHE    = config.MIDI_LIBRARY_DIR / "ldrolez_chords.zip"
    _INDEX_CACHE  = config.MIDI_LIBRARY_DIR / "ldrolez_index.json"
    _INDEX_TTL    = 86400 * 7  # 7 days

    # Maps query keyword → style folder base name (without " style" suffix)
    _STYLE_MAP: dict[str, str] = {
        "trap":    "hiphop2", "hip-hop": "hiphop2", "hiphop": "hiphop2",
        "r&b":     "soul",    "rnb":     "soul",     "soul":   "soul",
        "house":   "pop2",    "pop":     "pop",      "jazz":   "pop",
        "drill":   "hiphop2", "rage":    "hiphop2",
    }

    def _get_release_url(self) -> str:
        r = httpx.get(self._API_RELEASES, timeout=10,
                      headers={"Accept": "application/vnd.github.v3+json"})
        r.raise_for_status()
        for asset in r.json().get("assets", []):
            if "free-midi-chords" in asset["name"] and asset["name"].endswith(".zip"):
                return asset["browser_download_url"]
        raise RuntimeError("No chord zip found in latest ldrolez release")

    def _ensure_zip(self) -> None:
        if self._ZIP_CACHE.is_file() and self._ZIP_CACHE.stat().st_size > 1_000_000:
            return
        url = self._get_release_url()
        logger.info(f"[ldrolez] downloading release zip (~5 MB, one-time)…")
        r = httpx.get(url, timeout=120, follow_redirects=True)
        r.raise_for_status()
        self._ZIP_CACHE.write_bytes(r.content)
        logger.info(f"[ldrolez] zip cached ({self._ZIP_CACHE.stat().st_size:,} bytes)")

    def _load_index(self) -> list[str]:
        import time
        if self._INDEX_CACHE.is_file():
            try:
                if (time.time() - self._INDEX_CACHE.stat().st_mtime) < self._INDEX_TTL:
                    cached = json.loads(self._INDEX_CACHE.read_text())
                    if cached:
                        return cached
            except Exception:
                pass
        self._ensure_zip()
        with zipfile.ZipFile(self._ZIP_CACHE) as zf:
            files = [n for n in zf.namelist() if n.endswith(".mid")]
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._INDEX_CACHE.write_text(json.dumps(files))
        logger.info(f"[ldrolez] index built: {len(files)} files")
        return files

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            all_files = self._load_index()
        except Exception as exc:
            logger.warning(f"[ldrolez] index load failed: {exc}")
            return {"items": [], "total": 0, "has_more": False}
        q_lower = query.lower()
        style   = next((v for k, v in self._STYLE_MAP.items() if k in q_lower), None)
        needle  = (style + " style") if style else None
        if needle:
            filtered = [f for f in all_files if needle in f]
        elif query:
            filtered = [f for f in all_files if q_lower in f.lower()]
        else:
            filtered = [f for f in all_files if "hiphop2 style" in f]
        page  = filtered[offset:offset + limit]
        items = []
        for path in page:
            parts = path.split("/")
            # Extract style label from path segment ending in " style"
            style_label = next(
                (p.replace(" style", "") for p in parts if p.endswith(" style")), ""
            )
            # Key context: first path segment e.g. "01 - C Major - A minor"
            key_ctx = parts[0] if parts else ""
            items.append({
                "title":    Path(path).stem,
                "file_id":  path,
                "genre":    style_label,
                "plugin":   "sf2player",
                "subtitle": f"{style_label} · {key_ctx}" if style_label else key_ctx,
            })
        return {"items": items, "total": len(filtered),
                "has_more": (offset + limit) < len(filtered)}

    def download(self, file_id: str) -> str:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = self._CACHE_DIR / Path(file_id).name
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        self._ensure_zip()
        with zipfile.ZipFile(self._ZIP_CACHE) as zf:
            data = zf.read(file_id)
        cached.write_bytes(data)
        logger.info(f"[ldrolez] extracted {Path(file_id).name} ({len(data)} bytes)")
        return str(cached)


# ── Jamendo (600k CC-licensed tracks, free read API) ──────────────────────────

class JamendoBrowser:
    """Browse Jamendo — 600k Creative Commons tracks, no auth required.

    Returns streamable/downloadable MP3 URLs as file_id.
    Uses Jamendo's public read-only client_id (or env override).
    """
    _BASE      = "https://api.jamendo.com/v3.0"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "jamendo"

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        import config as _cfg
        client_id = getattr(_cfg, "JAMENDO_CLIENT_ID", "0de4e92c")
        params = {
            "client_id":   client_id,
            "format":      "json",
            "limit":       limit,
            "offset":      offset,
            "fuzzytags":   query or "music",
            "audioformat": "mp32",
            "include":     "musicinfo",
        }
        try:
            r = httpx.get(f"{self._BASE}/tracks/", params=params, timeout=_TIMEOUT_SEARCH)
            r.raise_for_status()
            data    = r.json()
            results = data.get("results", [])
            total   = data.get("headers", {}).get("results_count", len(results))
            items   = []
            for t in results:
                tags   = t.get("musicinfo", {}).get("tags", {})
                genres = tags.get("genres", [])
                audio_url = t.get("audiodownload") or t.get("audio", "")
                if not audio_url:
                    continue
                items.append({
                    "file_id":  audio_url,
                    "title":    t.get("name", ""),
                    "caption":  f"by {t.get('artist_name', '')}",
                    "subtitle": " · ".join(genres[:3]),
                    "genre":    genres[0] if genres else "",
                    "bpm":      0.0,
                    "key":      "",
                    "format":   "audio",
                    "_license": t.get("license_ccurl", ""),
                })
            return {"items": items, "total": total, "has_more": (offset + limit) < total}
        except Exception as exc:
            logger.warning(f"[Jamendo] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    def download(self, file_id: str) -> str:
        """Download a Jamendo track — file_id IS the audiodownload URL."""
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe    = _re.sub(r"[^a-zA-Z0-9_.-]", "_", file_id[-40:]) + ".mp3"
        cached  = self._CACHE_DIR / safe
        if cached.is_file() and cached.stat().st_size > 10_000:
            return str(cached)
        r = httpx.get(file_id, timeout=_TIMEOUT_DL, follow_redirects=True)
        r.raise_for_status()
        cached.write_bytes(r.content)
        logger.info(f"[Jamendo] downloaded {safe} ({len(r.content)} bytes)")
        return str(cached)


# ── SoundCloud (auto client_id extraction from JS bundle) ─────────────────────

class SoundCloudBrowser:
    """SoundCloud browser via the unofficial v2 API.

    Automatically extracts the current client_id from SoundCloud's web player
    JS bundle — no credentials or registration required. The extracted id is
    cached for 24 hours then refreshed automatically.
    """
    _BASE_V2    = "https://api-v2.soundcloud.com"
    _CACHE_DIR  = config.MIDI_LIBRARY_DIR / "soundcloud"
    _ID_CACHE   = config.MIDI_LIBRARY_DIR / "soundcloud" / "_client_id.txt"
    _ID_TTL     = 86_400   # 24 h
    _HEADERS    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

    # ── client_id management ──────────────────────────────────────────────────

    def _get_client_id(self) -> str:
        """Return a cached client_id, re-extracting from the JS bundle if stale."""
        import time
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Return from cache if fresh
        if self._ID_CACHE.is_file():
            try:
                if (time.time() - self._ID_CACHE.stat().st_mtime) < self._ID_TTL:
                    cid = self._ID_CACHE.read_text().strip()
                    if cid:
                        return cid
            except Exception:
                pass
        # Re-extract from web player JS
        cid = self._extract_client_id()
        if cid:
            self._ID_CACHE.write_text(cid)
        return cid

    def _extract_client_id(self) -> str:
        """Fetch SoundCloud homepage, find JS bundle URLs, search for client_id."""
        try:
            r = httpx.get("https://soundcloud.com", timeout=15,
                          headers=self._HEADERS, follow_redirects=True)
            bundle_urls = _re.findall(
                r'https://a-v2\.sndcdn\.com/assets/[^"]+\.js', r.text)
            for url in bundle_urls:
                try:
                    jr = httpx.get(url, timeout=15, headers=self._HEADERS)
                    m = _re.search(r'client_id:"([a-zA-Z0-9]{32})"', jr.text)
                    if m:
                        logger.info(f"[SoundCloud] extracted client_id from {url.split('/')[-1]}")
                        return m.group(1)
                except Exception:
                    continue
        except Exception as exc:
            logger.warning(f"[SoundCloud] client_id extraction failed: {exc}")
        return ""

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cid = self._get_client_id()
        if not cid:
            return {"items": [], "total": 0, "has_more": False,
                    "error": "Could not extract SoundCloud client_id"}
        try:
            r = httpx.get(
                f"{self._BASE_V2}/search/tracks",
                params={"q": query or "music", "client_id": cid,
                        "limit": limit, "offset": offset},
                headers=self._HEADERS,
                timeout=_TIMEOUT_SEARCH,
            )
            r.raise_for_status()
            data   = r.json()
            tracks = data.get("collection", [])
            total  = data.get("total_results", len(tracks))
        except Exception as exc:
            logger.warning(f"[SoundCloud] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False}

        items = []
        for t in tracks:
            dur_ms  = t.get("duration", 0)
            dur_str = f"{dur_ms // 60000}:{(dur_ms % 60000) // 1000:02d}"
            items.append({
                "file_id":  str(t.get("id", "")),
                "title":    t.get("title", ""),
                "subtitle": "by " + t.get("user", {}).get("username", ""),
                "caption":  t.get("description", "")[:80] if t.get("description") else "",
                "genre":    t.get("genre", ""),
                "bpm":      0.0,
                "key":      dur_str,
                "format":   "audio",
                "plugin":   "",
                "_download_available": True,
            })
        next_href = data.get("next_href")
        return {"items": items, "total": total,
                "has_more": next_href is not None}

    # ── download ──────────────────────────────────────────────────────────────

    def download(self, file_id: str) -> str:
        """Download a SoundCloud track as MP3 via the progressive stream."""
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = self._CACHE_DIR / f"sc_{file_id}.mp3"
        if cached.is_file() and cached.stat().st_size > 10_000:
            return str(cached)
        cid = self._get_client_id()
        if not cid:
            raise RuntimeError("SoundCloud client_id unavailable")
        # Fetch track detail
        r = httpx.get(f"{self._BASE_V2}/tracks/{file_id}",
                      params={"client_id": cid}, headers=self._HEADERS,
                      timeout=_TIMEOUT_FAST)
        r.raise_for_status()
        detail = r.json()
        transcodings = detail.get("media", {}).get("transcodings", [])
        # Prefer progressive MP3 (directly downloadable, no HLS parsing needed)
        prog = next(
            (t for t in transcodings
             if t.get("format", {}).get("protocol") == "progressive"),
            None,
        )
        if not prog:
            raise RuntimeError(f"No progressive stream for SoundCloud track {file_id}")
        # Resolve the CDN URL
        r2 = httpx.get(prog["url"], params={"client_id": cid},
                       headers=self._HEADERS, timeout=_TIMEOUT_FAST)
        r2.raise_for_status()
        cdn_url = r2.json().get("url", "")
        if not cdn_url:
            raise RuntimeError("Empty CDN URL from SoundCloud stream")
        # Download the full MP3
        r3 = httpx.get(cdn_url, timeout=_TIMEOUT_DL, follow_redirects=True,
                       headers=self._HEADERS)
        r3.raise_for_status()
        cached.write_bytes(r3.content)
        logger.info(f"[SoundCloud] downloaded {file_id} ({len(r3.content)} bytes)")
        return str(cached)


# ── MidiWorld.com (importable genre MIDI — pop, jazz, rock, blues…) ───────────

# Short genre alias → MidiWorld search term
_MIDIWORLD_GENRE_MAP: dict[str, str] = {
    "pop":       "pop",
    "jazz":      "jazz",
    "rock":      "rock",
    "rap":       "rap",
    "hiphop":    "hip-hop",
    "hip-hop":   "hip-hop",
    "blues":     "blues",
    "country":   "country",
    "dance":     "dance",
    "classical": "classic",
    "classic":   "classic",
    "punk":      "punk",
    # Approximate aliases for genres MidiWorld doesn't have natively
    "trap":      "rap",
    "rnb":       "hip-hop",
    "r&b":       "hip-hop",
    "house":     "dance",
    "lofi":      "pop",
    "soul":      "blues",
    "funk":      "blues",
}


class _MidiWorldListParser(_HTMLParser):
    """Parse MidiWorld.com search result pages.

    Each result is a <li> with title text followed by
    <a href="https://www.midiworld.com/download/NNN">download</a>.
    Text capture stops as soon as the download <a> tag is encountered,
    so the title is clean (no trailing "- download" noise).
    """

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._in_li     = False
        self._capturing = False
        self._buf       = ""
        self._dl_url    = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        ad = dict(attrs)
        if tag == "li":
            self._in_li     = True
            self._capturing = True
            self._buf       = ""
            self._dl_url    = ""
        elif tag == "a" and self._in_li:
            href = ad.get("href", "")
            if "/download/" in href:
                self._dl_url    = href
                self._capturing = False   # stop capturing — rest is link text + flash div

    def handle_data(self, data: str) -> None:
        if self._in_li and self._capturing:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self._in_li:
            if self._dl_url:
                title = self._buf.strip().rstrip("-– ").strip() or "MIDI File"
                m = _re.search(r"/download/(\d+)", self._dl_url)
                dl_id = m.group(1) if m else self._dl_url
                self.results.append({"title": title, "dl_id": dl_id})
            self._in_li     = False
            self._capturing = False
            self._buf       = ""
            self._dl_url    = ""


class MidiWorldBrowser:
    """Browse MidiWorld.com — genre-tagged MIDI with direct-download files.

    MidiWorld's search endpoint returns 30 results per page.
    Supports pop, jazz, rock, rap, hip-hop, blues, country, dance, classical, punk.
    All returned items are directly importable (no login, no archive needed).
    """

    _BASE      = "https://www.midiworld.com"
    _CACHE_DIR = config.MIDI_LIBRARY_DIR / "midiworld"
    _HEADERS   = {"User-Agent": "WavyLabs/1.0 (MIDI browser; +https://wavylabs.com)"}
    _PAGE_SIZE = 30

    def search(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        from urllib.parse import quote as _url_quote
        q_norm      = query.strip().lower()
        search_term = _MIDIWORLD_GENRE_MAP.get(q_norm, query.strip() or "pop")

        # Offset → page number (MidiWorld pages have 30 items each)
        page = offset // self._PAGE_SIZE + 1
        if page == 1:
            url = f"{self._BASE}/search/?q={_url_quote(search_term)}"
        else:
            url = f"{self._BASE}/search/{page}/?q={_url_quote(search_term)}"

        try:
            r = httpx.get(url, headers=self._HEADERS, timeout=_TIMEOUT_SEARCH,
                          follow_redirects=True)
            r.raise_for_status()
            parser = _MidiWorldListParser()
            parser.feed(r.text)
            results = parser.results

            # Estimate total from highest page number found in pagination links
            pages_found = _re.findall(r"/search/(\d+)/\?q=", r.text)
            max_page    = max((int(p) for p in pages_found), default=page)
            total_approx = max_page * self._PAGE_SIZE

            # Slice within this page for the requested offset window
            page_offset = offset % self._PAGE_SIZE
            page_items  = results[page_offset : page_offset + limit]

            items = [
                {
                    "file_id": item["dl_id"],
                    "title":   item["title"],
                    "caption": f"Genre: {search_term}",
                    "subtitle": "",
                    "genre":   search_term,
                    "bpm":     0.0,
                    "key":     "",
                    "mood":    "",
                    "plugin":  "sf2player",
                    "_download_available": True,
                }
                for item in page_items
            ]
            has_more = (len(results) >= self._PAGE_SIZE) or (page < max_page)
            return {"items": items, "total": total_approx, "has_more": has_more}

        except Exception as exc:
            logger.error(f"[MidiWorld] search failed: {exc}")
            return {"items": [], "total": 0, "has_more": False, "error": str(exc)}

    def download(self, file_id: str) -> str:
        """Download a MidiWorld MIDI file by its numeric download ID."""
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = f"midiworld_{file_id}.mid"
        cached    = self._CACHE_DIR / safe_name
        if cached.is_file() and cached.stat().st_size > 4:
            return str(cached)
        url  = f"{self._BASE}/download/{file_id}"
        r    = httpx.get(url, headers=self._HEADERS, timeout=_TIMEOUT_DL,
                         follow_redirects=True)
        r.raise_for_status()
        data = r.content
        if data[:4] != b"MThd":
            raise ValueError(f"Not a valid MIDI file from MidiWorld (id={file_id!r})")
        cached.write_bytes(data)
        logger.info(f"[MidiWorld] downloaded midiworld_{file_id}.mid ({len(data)} bytes)")
        return str(cached)
