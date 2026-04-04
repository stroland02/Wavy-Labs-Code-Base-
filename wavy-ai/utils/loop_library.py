"""
loop_library.py — Real MIDI loop browser backed by open-source datasets.

Data sources:
  - Drums:    Groove MIDI Dataset v1.0.0 (CC BY 4.0)
              Auto-downloaded ~3.1 MB zip on first use.
              1,150 human-played drum performances across 18 genres.
  - Pitched:  Locally generated + cached loops using the harmonic engine.
              Generated on first access per genre/role, cached permanently.

Loop ID formats:
  groove:{relative_path}        e.g. "groove:drummer1/session1/beat_120.mid"
  gen:{genre}:{role}:{seed_hex} e.g. "gen:lofi:bass:a1b2c3d4"
"""
from __future__ import annotations

import csv
import json
import random as _random
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import mido
from loguru import logger

import config
from utils.music_theory import (
    chord_schedule,
    chord_progression_from_schedule,
    bass_line_harmonic,
    melody_line_harmonic,
    detect_key_from_notes,
    _SEMITONE_MAP,
)

# ── Dataset URLs ───────────────────────────────────────────────────────────────

GROOVE_ZIP_URL = (
    "https://storage.googleapis.com/magentadata/datasets/groove/"
    "groove-v1.0.0-midionly.zip"
)
GROOVE_CACHE   = config.MIDI_LIBRARY_DIR / "groove"
WAVY_LOOPS_DIR = config.MIDI_LIBRARY_DIR / "wavy_loops"

# ── Genre defaults ─────────────────────────────────────────────────────────────

_GENRE_BPM_DEFAULTS: dict[str, int] = {
    "lofi":    82,
    "trap":    140,
    "house":   124,
    "jazz":    110,
    "ambient": 80,
    "dnb":     174,
    "rnb":     92,
}

_GENRE_KEY_DEFAULTS: dict[str, tuple[str, str]] = {
    "lofi":    ("F",  "minor"),
    "trap":    ("C",  "minor"),
    "house":   ("A",  "minor"),
    "jazz":    ("F",  "major"),
    "ambient": ("C",  "major"),
    "dnb":     ("D",  "minor"),
    "rnb":     ("Bb", "minor"),
}

# ── Instrument / preset mapping ────────────────────────────────────────────────

_PRESET_FOR_ROLE: dict[str, tuple[str, str]] = {
    "bass":   ("LB302",            "LB302/AcidLead.xpf"),
    "chords": ("TripleOscillator", "TripleOscillator/WarmStack.xpf"),
    "melody": ("TripleOscillator", "TripleOscillator/LovelyDream.xpf"),
    "lead":   ("BitInvader",       "BitInvader/epiano.xpf"),
    "pad":    ("Organic",          "Organic/pad_rich.xpf"),
}

_PRESET_FOR_GENRE_ROLE: dict[str, dict[str, tuple[str, str]]] = {
    "lofi": {
        "bass":   ("LB302",      "LB302/AcidLead.xpf"),
        "chords": ("Organic",    "Organic/pad_rich.xpf"),
        "melody": ("BitInvader", "BitInvader/soft_pad.xpf"),
        "lead":   ("BitInvader", "BitInvader/soft_pad.xpf"),
        "pad":    ("Organic",    "Organic/pad_rich.xpf"),
    },
    "trap": {
        "bass":   ("LB302",            "LB302/AcidLead.xpf"),
        "chords": ("TripleOscillator", "TripleOscillator/WarmStack.xpf"),
        "melody": ("BitInvader",       "BitInvader/epiano.xpf"),
        "lead":   ("BitInvader",       "BitInvader/wah_synth.xpf"),
        "pad":    ("Organic",          "Organic/pad_rich.xpf"),
    },
    "jazz": {
        "bass":   ("LB302",   "LB302/AcidLead.xpf"),
        "chords": ("OpulenZ", "OpulenZ/Epiano.xpf"),
        "melody": ("OpulenZ", "OpulenZ/Epiano.xpf"),
        "lead":   ("OpulenZ", "OpulenZ/Epiano.xpf"),
        "pad":    ("Organic", "Organic/pad_rich.xpf"),
    },
    "house": {
        "bass":   ("LB302",            "LB302/AcidLead.xpf"),
        "chords": ("TripleOscillator", "TripleOscillator/WarmStack.xpf"),
        "melody": ("TripleOscillator", "TripleOscillator/LovelyDream.xpf"),
        "lead":   ("BitInvader",       "BitInvader/wah_synth.xpf"),
        "pad":    ("Organic",          "Organic/pad_rich.xpf"),
    },
    "dnb": {
        "bass":   ("LB302",      "LB302/AcidLead.xpf"),
        "chords": ("BitInvader", "BitInvader/soft_pad.xpf"),
        "melody": ("BitInvader", "BitInvader/epiano.xpf"),
        "lead":   ("BitInvader", "BitInvader/wah_synth.xpf"),
        "pad":    ("Organic",    "Organic/pad_rich.xpf"),
    },
}

_ROLE_COLORS: dict[str, str] = {
    "drums":  "#e74c3c",
    "bass":   "#2ecc71",
    "chords": "#3498db",
    "melody": "#9b59b6",
    "lead":   "#f39c12",
    "pad":    "#1abc9c",
}

# ── Groove genre mapping ───────────────────────────────────────────────────────
# Maps wavy genre names → Groove style substrings to match

_GROOVE_GENRE_ALIASES: dict[str, list[str]] = {
    "lofi":    ["hiphop", "funk", "soul"],
    "trap":    ["hiphop"],
    "house":   ["funk", "electronic", "dance"],
    "jazz":    ["jazz"],
    "ambient": ["soul", "country"],
    "dnb":     ["electronic", "funk"],
    "rnb":     ["soul", "rnb", "funk"],
}

# How many loops to pre-generate per genre/role on first access
_LOOPS_PER_ROLE = 12


def _groove_matches(entry_genre: str, entry_style: str, target_genre: str) -> bool:
    aliases = _GROOVE_GENRE_ALIASES.get(target_genre, [])
    if not aliases:
        return True
    style_lower = entry_style.lower()
    return any(a in style_lower or a == entry_genre for a in aliases)


# ── Groove index cache ─────────────────────────────────────────────────────────

_groove_index: list[dict] | None = None


def _get_groove_index() -> list[dict]:
    global _groove_index
    if _groove_index is not None:
        return _groove_index

    idx_path = GROOVE_CACHE / "index.json"
    if idx_path.exists():
        try:
            _groove_index = json.loads(idx_path.read_text())
            logger.info(f"[loop_library] Groove index loaded ({len(_groove_index)} entries)")
            return _groove_index
        except Exception:
            pass

    # First run — download & build index
    _ensure_groove_downloaded()
    _groove_index = _build_groove_index()
    return _groove_index


def _ensure_groove_downloaded() -> None:
    """Download and extract the Groove MIDI zip (~3.1 MB), one-time."""
    if (GROOVE_CACHE / "info.csv").exists():
        return

    GROOVE_CACHE.mkdir(parents=True, exist_ok=True)
    zip_path = GROOVE_CACHE / "groove.zip"

    if not zip_path.exists():
        logger.info("[loop_library] Downloading Groove MIDI Dataset (~3.1 MB)…")
        try:
            import httpx
            with httpx.stream("GET", GROOVE_ZIP_URL, follow_redirects=True,
                              timeout=120) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_bytes(65536):
                        f.write(chunk)
            logger.info("[loop_library] Groove download complete")
        except Exception as exc:
            logger.error(f"[loop_library] Groove download failed: {exc}")
            return

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(GROOVE_CACHE)
        logger.info(f"[loop_library] Groove extracted to {GROOVE_CACHE}")
    except Exception as exc:
        logger.error(f"[loop_library] Groove extract failed: {exc}")


def _build_groove_index() -> list[dict]:
    """Parse Groove info.csv and build + cache index.json."""
    csv_candidates = list(GROOVE_CACHE.rglob("info.csv"))
    if not csv_candidates:
        logger.warning("[loop_library] Groove info.csv not found after download")
        return []

    csv_path = csv_candidates[0]
    entries: list[dict] = []

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                midi_rel = row.get("midi_filename", "").strip()
                if not midi_rel:
                    continue
                midi_abs = csv_path.parent / midi_rel
                if not midi_abs.exists():
                    continue

                style = row.get("style", "").strip().lower()
                primary_genre = style.split("/")[0].replace("-", "").strip()
                try:
                    bpm = round(float(row.get("bpm", 0) or 0), 1)
                except ValueError:
                    bpm = 0.0

                stem = Path(midi_rel).stem.replace("_", " ")
                title = f"{style.split('/')[0].capitalize()} Beat — {stem[:30]}"

                entries.append({
                    "id":     "groove:" + midi_rel,
                    "title":  title,
                    "genre":  primary_genre,
                    "style":  style,
                    "role":   "drums",
                    "bpm":    bpm,
                    "bars":   4,
                    "source": "Groove MIDI Dataset",
                })
    except Exception as exc:
        logger.error(f"[loop_library] Groove CSV parse error: {exc}")

    idx_path = GROOVE_CACHE / "index.json"
    try:
        idx_path.write_text(json.dumps(entries, indent=2))
    except Exception:
        pass

    logger.info(f"[loop_library] Groove index built: {len(entries)} entries")
    return entries


# ── Generated loop cache ────────────────────────────────────────────────────────

def _gen_loop_dir(genre: str, role: str) -> Path:
    return WAVY_LOOPS_DIR / genre / role


def _write_gen_midi(notes: list[dict], bpm: int, out_path: Path) -> int:
    """Write note dicts to MIDI with humanization. Returns note count."""
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    events: list[tuple[int, str, int, int]] = []
    rng = _random.Random(str(out_path))

    for n in notes:
        pitch    = max(0, min(127, int(n.get("pitch", 60))))
        beat     = float(n.get("beat", 0.0))
        dur      = float(n.get("duration", 0.5))
        velocity = max(1, min(127, int(n.get("velocity", 80))))
        start_t  = int(beat * 480)
        end_t    = int((beat + dur) * 480)
        events.append((start_t, "note_on",  pitch, velocity))
        events.append((end_t,   "note_off", pitch, 0))

    # Humanization: timing jitter ±8 ticks + velocity ±8
    humanized: list[tuple[int, str, int, int]] = []
    for tick, mtype, pitch, vel in events:
        jitter = rng.randint(-8, 8)
        if mtype == "note_on":
            humanized.append((max(0, tick + jitter), mtype, pitch,
                               max(1, min(127, vel + rng.randint(-8, 8)))))
        else:
            humanized.append((max(0, tick + jitter), mtype, pitch, vel))
    humanized.sort(key=lambda x: x[0])

    prev_tick = 0
    for tick, msg_type, pitch, vel in humanized:
        delta = max(0, tick - prev_tick)
        track.append(mido.Message(msg_type, note=pitch, velocity=vel,
                                  channel=0, time=delta))
        prev_tick = tick

    mid.save(str(out_path))
    return len([e for e in humanized if e[1] == "note_on"])


def _generate_single_loop(
    genre: str,
    role: str,
    seed: int,
    bars: int = 8,
) -> Path | None:
    """Generate one MIDI loop for a given genre/role using the harmonic engine."""
    key, scale = _GENRE_KEY_DEFAULTS.get(genre, ("C", "minor"))
    bpm        = _GENRE_BPM_DEFAULTS.get(genre, 120)

    # Use seed to vary chord progression
    rng = _random.Random(seed)
    # Shift key by a random amount within the scale for variety
    key_shift = rng.choice([0, 2, 5, 7, 9])
    note_names = ["C", "D", "Eb", "E", "F", "G", "Ab", "A", "Bb", "B"]
    semitone_key = _SEMITONE_MAP.get(key, 0)
    shifted_idx  = (semitone_key + key_shift) % 12
    varied_key   = note_names[shifted_idx % len(note_names)]

    try:
        cs = chord_schedule(varied_key, scale, genre, bars)
    except Exception as exc:
        logger.warning(f"[loop_library] chord_schedule failed for {genre}/{role}: {exc}")
        return None

    try:
        if role == "bass":
            notes = bass_line_harmonic(cs, genre, bars)
        elif role in ("melody", "lead"):
            notes = melody_line_harmonic(cs, varied_key, scale, genre, bars)
        elif role == "chords":
            # chord_progression_from_schedule already returns individual note dicts
            notes = chord_progression_from_schedule(cs, genre)
        elif role == "pad":
            # Pads = sparse, lower velocity version of chords
            raw = chord_progression_from_schedule(cs, genre)
            notes = []
            # Group by beat to pick only top 3 voices per chord
            beat_groups: dict[float, list[dict]] = {}
            for n in raw:
                b = float(n.get("beat", 0.0))
                beat_groups.setdefault(b, []).append(n)
            for b_notes in beat_groups.values():
                # Sort by pitch, keep top 3
                b_notes.sort(key=lambda x: x.get("pitch", 0))
                for n in b_notes[-3:]:
                    notes.append({
                        "pitch":    n.get("pitch", 60),
                        "beat":     n.get("beat", 0.0),
                        "duration": n.get("duration", 4.0) * 0.9,
                        "velocity": max(1, min(127, int(n.get("velocity", 68)) - 10 + rng.randint(-5, 5))),
                    })
        else:
            notes = melody_line_harmonic(cs, varied_key, scale, genre, bars)

    except Exception as exc:
        logger.warning(f"[loop_library] harmonic generation failed {genre}/{role}: {exc}")
        return None

    if not notes:
        return None

    out_dir  = _gen_loop_dir(genre, role)
    out_dir.mkdir(parents=True, exist_ok=True)
    hex_seed = format(seed & 0xFFFFFFFF, "08x")
    out_path = out_dir / f"{hex_seed}.mid"

    try:
        count = _write_gen_midi(notes, bpm, out_path)
        if count == 0:
            out_path.unlink(missing_ok=True)
            return None
    except Exception as exc:
        logger.error(f"[loop_library] MIDI write failed: {exc}")
        return None

    return out_path


def _ensure_generated_loops(
    genre: str,
    role: str,
    count: int = _LOOPS_PER_ROLE,
) -> list[Path]:
    """Ensure at least `count` generated loops exist for genre/role. Return their paths."""
    out_dir = _gen_loop_dir(genre, role)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(out_dir.glob("*.mid"))
    if len(existing) >= count:
        return existing[:count]

    needed = count - len(existing)
    # Deterministic seeds so same loops appear consistently
    base_seed = abs(hash(f"{genre}:{role}"))
    for i in range(needed):
        seed  = (base_seed + len(existing) + i) % (2**32)
        path  = _generate_single_loop(genre, role, seed)
        if path:
            existing.append(path)
        if len(existing) >= count:
            break

    return existing[:count]


def _list_generated_loops(
    genre: str,
    role: str,
    bpm_target: float | None,
    limit: int,
) -> list[dict]:
    bpm_ref  = bpm_target or _GENRE_BPM_DEFAULTS.get(genre, 120)
    key, _sc = _GENRE_KEY_DEFAULTS.get(genre, ("C", "minor"))

    paths = _ensure_generated_loops(genre, role, max(limit, _LOOPS_PER_ROLE))
    note_names = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

    results: list[dict] = []
    for idx, path in enumerate(paths[:limit]):
        hex_seed = path.stem
        seed_int = int(hex_seed, 16) if all(c in "0123456789abcdef" for c in hex_seed) else 0
        rng      = _random.Random(seed_int)
        key_shift = rng.choice([0, 2, 5, 7, 9])
        semitone_key = _SEMITONE_MAP.get(key, 0)
        shifted_key  = note_names[(semitone_key + key_shift) % 12]

        results.append({
            "id":     f"gen:{genre}:{role}:{hex_seed}",
            "title":  f"{genre.capitalize()} {role.capitalize()} {idx + 1:02d}",
            "genre":  genre,
            "role":   role,
            "bpm":    bpm_ref,
            "key":    shifted_key,
            "bars":   8,
            "source": "Wavy AI",
        })

    return results


# ── MIDI helpers ───────────────────────────────────────────────────────────────

def _midi_pitches(path: Path) -> list[int]:
    pitches: list[int] = []
    try:
        mid = mido.MidiFile(str(path))
        for track in mid.tracks:
            for msg in track:
                if msg.type == "note_on" and msg.velocity > 0:
                    pitches.append(msg.note)
    except Exception:
        pass
    return pitches


def _key_diff(src_key: str, dst_key: str) -> int:
    """Semitones to transpose from src_key to dst_key (smallest interval)."""
    s = _SEMITONE_MAP.get(src_key, 0)
    d = _SEMITONE_MAP.get(dst_key, 0)
    diff = (d - s) % 12
    return diff if diff <= 6 else diff - 12


def _resolve_preset(genre: str, role: str) -> tuple[str, str]:
    genre_map = _PRESET_FOR_GENRE_ROLE.get(genre, _PRESET_FOR_GENRE_ROLE.get("lofi", {}))
    return genre_map.get(role, _PRESET_FOR_ROLE.get(role, ("TripleOscillator", "")))


# ── Public API ─────────────────────────────────────────────────────────────────

class LoopLibrary:
    """Static-only class for loop browsing and preparation."""

    @classmethod
    def list_loops(
        cls,
        genre: str,
        role: str,
        bpm_target: float | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Return loop metadata (no download). Sorted by BPM proximity.

        Returns [{id, title, genre, role, bpm, key, bars, source}]
        """
        genre_norm = genre.lower().strip()
        role_norm  = role.lower().strip()

        if role_norm == "drums":
            return cls._list_groove_loops(genre_norm, bpm_target, limit)
        else:
            return _list_generated_loops(genre_norm, role_norm, bpm_target, limit)

    @classmethod
    def prepare_loop(
        cls,
        loop_id: str,
        role: str,
        genre: str,
        target_key: str,
        target_bpm: int,
        bars: int,
    ) -> list[dict] | dict | None:
        """
        Download (if needed) + prepare MIDI for LMMS import.

        Returns a single part dict (pitched) or a list of part dicts (drums).
        Same format as compose_agent parts:
          {name, role, midi_path, instrument, preset_name, color, note_count,
           bars, start_bar}
        """
        if loop_id.startswith("groove:"):
            return cls._prepare_groove_loop(loop_id, genre, target_bpm, bars)
        elif loop_id.startswith("gen:"):
            return cls._prepare_generated_loop(
                loop_id, role, genre, target_key, target_bpm, bars
            )
        else:
            logger.warning(f"[loop_library] Unknown loop_id format: {loop_id!r}")
            return None

    # ── Groove (drums) ─────────────────────────────────────────────────────────

    @classmethod
    def _list_groove_loops(
        cls,
        genre: str,
        bpm_target: float | None,
        limit: int,
    ) -> list[dict]:
        try:
            index = _get_groove_index()
        except Exception as exc:
            logger.error(f"[loop_library] Groove index error: {exc}")
            return []

        matching = [
            e for e in index
            if _groove_matches(e.get("genre", ""), e.get("style", ""), genre)
        ]
        if not matching:
            matching = index  # fallback: all entries

        if bpm_target is not None:
            matching = sorted(matching, key=lambda e: abs(e.get("bpm", 120) - bpm_target))

        return matching[:limit]

    @classmethod
    def _prepare_groove_loop(
        cls,
        loop_id: str,
        genre: str,
        target_bpm: int,
        bars: int,
    ) -> list[dict] | None:
        """Read a Groove MIDI file, parse notes, split into per-voice drum parts."""
        midi_rel = loop_id.removeprefix("groove:")

        # Locate info.csv to find the base dir
        csv_candidates = list(GROOVE_CACHE.rglob("info.csv"))
        if not csv_candidates:
            _ensure_groove_downloaded()
            csv_candidates = list(GROOVE_CACHE.rglob("info.csv"))

        if not csv_candidates:
            logger.error("[loop_library] Groove data unavailable")
            return None

        midi_path = csv_candidates[0].parent / midi_rel
        if not midi_path.exists():
            logger.warning(f"[loop_library] Groove MIDI not found: {midi_path}")
            return None

        # Parse drum notes from MIDI
        try:
            mid = mido.MidiFile(str(midi_path))
            tpb = mid.ticks_per_beat or 480
            notes: list[dict] = []
            for track in mid.tracks:
                abs_tick = 0
                for msg in track:
                    abs_tick += msg.time
                    if msg.type == "note_on" and msg.velocity > 0:
                        beat = abs_tick / tpb
                        notes.append({
                            "pitch":    msg.note,
                            "beat":     beat,
                            "duration": 0.1,
                            "velocity": msg.velocity,
                        })
        except Exception as exc:
            logger.error(f"[loop_library] Groove MIDI parse error {midi_path}: {exc}")
            return None

        if not notes:
            return None

        try:
            from agents.compose_agent import _split_drum_voices
            split = _split_drum_voices(notes, target_bpm, genre)
        except Exception as exc:
            logger.error(f"[loop_library] _split_drum_voices failed: {exc}")
            return None

        if not split:
            return None

        # Prefix names with "Groove" so tracks are distinguishable from
        # algorithmically generated ones in the LMMS Song Editor.
        # Also include the groove style from the filename for extra context.
        path_parts = Path(midi_rel).parts
        style_hint = path_parts[0].replace("drummer", "Groove") if path_parts else "Groove"
        for part in split:
            voice = part.get("name", "Drum")
            part["name"] = f"{style_hint}: {voice}"
            part.setdefault("bars", bars)
            part.setdefault("start_bar", 0)

        return split

    # ── Generated loops (pitched) ──────────────────────────────────────────────

    @classmethod
    def _prepare_generated_loop(
        cls,
        loop_id: str,
        role: str,
        genre: str,
        target_key: str,
        target_bpm: int,
        bars: int,
    ) -> dict | None:
        """Locate a cached generated loop, transpose if needed, return part dict."""
        # Parse: "gen:{genre}:{role}:{hex_seed}"
        parts = loop_id.removeprefix("gen:").split(":")
        if len(parts) < 3:
            logger.warning(f"[loop_library] Malformed gen id: {loop_id!r}")
            return None

        gen_genre, gen_role, hex_seed = parts[0], parts[1], parts[2]
        out_dir   = _gen_loop_dir(gen_genre, gen_role)
        src_path  = out_dir / f"{hex_seed}.mid"

        # Re-generate if missing (e.g., cache was cleared)
        if not src_path.exists():
            try:
                seed = int(hex_seed, 16)
            except ValueError:
                seed = abs(hash(hex_seed))
            _generate_single_loop(gen_genre, gen_role, seed)
            if not src_path.exists():
                logger.warning(f"[loop_library] Generated loop missing: {src_path}")
                return None

        # Detect source key for transposition
        try:
            pitches = _midi_pitches(src_path)
            src_key, _ = detect_key_from_notes(pitches) if pitches else ("C", "minor")
        except Exception:
            src_key = "C"

        # Transpose to target key
        semitones  = _key_diff(src_key, target_key)
        hex8       = uuid.uuid4().hex[:8]
        work_path  = src_path

        if semitones != 0:
            transposed = out_dir / f"{hex_seed}_trans_{target_key}_{hex8}.mid"
            try:
                from utils.midi_library import transpose_midi
                transpose_midi(src_path, semitones, transposed)
                work_path = transposed
            except Exception as exc:
                logger.warning(f"[loop_library] transpose failed ({exc}) — using original")

        # Trim to bars
        trimmed = out_dir / f"{hex_seed}_trim_{bars}b_{hex8}.mid"
        try:
            from utils.midi_library import trim_midi_to_bars
            trim_midi_to_bars(work_path, bars, target_bpm, trimmed)
            work_path = trimmed
        except Exception as exc:
            logger.warning(f"[loop_library] trim failed ({exc}) — using transposed")

        note_count = len(_midi_pitches(work_path))
        instr, preset = _resolve_preset(genre, role)

        return {
            "name":        f"{genre.capitalize()} {role.capitalize()}",
            "role":        role,
            "midi_path":   str(work_path),
            "instrument":  instr,
            "preset_name": preset,
            "color":       _ROLE_COLORS.get(role, "#95a5a6"),
            "note_count":  note_count,
            "bars":        bars,
            "start_bar":   0,
        }
