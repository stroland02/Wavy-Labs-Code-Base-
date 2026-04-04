"""
Code-to-Music converter.
Supports four input modes:
  - "dsl"         → Wavy Labs DSL (track/melody/pattern functions)
  - "csv"         → CSV data sonification
  - "json_data"   → JSON array sonification
  - "python"      → Evaluate Python snippet in sandboxed namespace
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import mido
import numpy as np
import soundfile as sf
from loguru import logger
from lark import Lark, Transformer, v_args  # type: ignore

from .base import BaseModel

# ── Wavy DSL grammar ──────────────────────────────────────────────────────────

DSL_GRAMMAR = r"""
start: statement+

statement: track_stmt
         | tempo_stmt
         | key_stmt

tempo_stmt : "tempo" "(" NUMBER ")"
key_stmt   : "key" "(" STRING ")"
track_stmt : "track" "(" STRING ")" "." track_call

track_call : pattern_call
           | melody_call
           | generate_call

pattern_call : "pattern" "(" list_ ["," kv_args] ")"
melody_call  : "melody"  "(" list_ ["," kv_args] ")"
generate_call: "generate" "(" STRING ["," kv_args] ")"

kv_args : kv ("," kv)*
kv      : NAME "=" value

list_   : "[" [value ("," value)*] "]"
value   : NUMBER | STRING | NAME

NAME    : /[a-zA-Z_][a-zA-Z0-9_#]*/
STRING  : /\"[^\"]*\"|\'[^\']*\'/
NUMBER  : /[+-]?[0-9]+(\.[0-9]+)?/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""


@v_args(inline=True)
class DSLTransformer(Transformer):
    """Transforms a parsed DSL tree into a list of track definition dicts."""

    def start(self, *stmts):
        result = {"tracks": [], "tempo": 120, "key": "C major"}
        for stmt in stmts:
            if isinstance(stmt, dict) and stmt.get("__type__") == "tempo":
                result["tempo"] = stmt["bpm"]
            elif isinstance(stmt, dict) and stmt.get("__type__") == "key":
                result["key"] = stmt["key"]
            elif isinstance(stmt, dict) and "track" in stmt:
                result["tracks"].append(stmt)
        return result

    def tempo_stmt(self, n):
        return {"__type__": "tempo", "bpm": int(float(n))}

    def key_stmt(self, s):
        return {"__type__": "key", "key": str(s).strip("'\"")}

    def statement(self, child):
        return child

    def track_call(self, call):
        return call

    def track_stmt(self, name, call):
        call["track"] = str(name).strip("'\"")
        return call

    def pattern_call(self, lst, *kvs):
        kv_dict = {}
        for k in kvs:
            if k is not None:
                kv_dict.update(k)
        return {"type": "pattern", "data": lst, **kv_dict}

    def melody_call(self, lst, *kvs):
        kv_dict = {}
        for k in kvs:
            if k is not None:
                kv_dict.update(k)
        return {"type": "melody", "notes": lst, **kv_dict}

    def generate_call(self, prompt, *kvs):
        kv_dict = {}
        for k in kvs:
            if k is not None:
                kv_dict.update(k)
        return {"type": "generate", "prompt": str(prompt).strip("'\""), **kv_dict}

    def kv_args(self, *kvs):
        result = {}
        for k in kvs:
            result.update(k)
        return result

    def kv(self, name, val):
        return {str(name): val}

    def list_(self, *vals):
        return list(vals)

    def value(self, v):
        s = str(v)
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return s.strip("'\"")

    def NAME(self, s):   return str(s)
    def STRING(self, s): return str(s)
    def NUMBER(self, n): return float(n)


_PARSER = Lark(DSL_GRAMMAR, parser="lalr", transformer=DSLTransformer())

# ── Note name → MIDI number ───────────────────────────────────────────────────

NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
OCTAVE_DEFAULT = 4

def note_to_midi(name: str) -> int:
    name = name.upper().strip()
    if not name:
        return 60
    note_part = ""
    octave_part = ""
    for ch in name:
        if ch.isalpha() or ch == "#" or ch == "B":
            note_part += ch
        else:
            octave_part += ch
    base = NOTE_NAMES.get(note_part[:1], 0)
    if "#" in note_part:
        base += 1
    octave = int(octave_part) if octave_part else OCTAVE_DEFAULT
    return (octave + 1) * 12 + base


# ── Simple numpy synthesizer ──────────────────────────────────────────────────
# Renders each DSL track to a WAV without external dependencies.
# Quality is intentionally simple — accurate pitch and timing matter more than timbre.

SYNTH_SR = 44100  # sample rate for all synthesized audio


def _midi_to_hz(pitch: int) -> float:
    return 440.0 * 2.0 ** ((pitch - 69) / 12.0)


def _drum_sample(pitch: int, sr: int = SYNTH_SR) -> np.ndarray:
    """Generate a short drum sound based on MIDI pitch."""
    if pitch in (35, 36):           # bass drum
        dur = 0.4
        t = np.linspace(0, dur, int(dur * sr), endpoint=False)
        env = np.exp(-12.0 * t)
        sig = np.sin(2 * np.pi * 80.0 * t * np.exp(-18.0 * t)) * env
    elif pitch in (38, 40):         # snare
        dur = 0.25
        t = np.linspace(0, dur, int(dur * sr), endpoint=False)
        env = np.exp(-22.0 * t)
        sig = np.random.default_rng(pitch).normal(0, 1, len(t)) * env * 0.6
    elif pitch in (42, 44, 46):     # hi-hat
        dur = 0.08
        t = np.linspace(0, dur, int(dur * sr), endpoint=False)
        env = np.exp(-60.0 * t)
        sig = np.random.default_rng(pitch).normal(0, 1, len(t)) * env * 0.4
    else:                           # generic perc
        dur = 0.2
        t = np.linspace(0, dur, int(dur * sr), endpoint=False)
        env = np.exp(-25.0 * t)
        sig = np.random.default_rng(pitch).normal(0, 1, len(t)) * env * 0.5
    return sig.astype(np.float32)


def _tone_sample(pitch: int, duration: float, waveform: str = "sawtooth",
                 sr: int = SYNTH_SR) -> np.ndarray:
    """Render a single note as a simple synthesized tone."""
    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = _midi_to_hz(pitch)

    if waveform == "sine":
        sig = np.sin(2 * np.pi * freq * t)
    elif waveform == "square":
        sig = np.sign(np.sin(2 * np.pi * freq * t))
    else:                           # sawtooth (default — good for bass/synth)
        sig = 2.0 * (t * freq % 1.0) - 1.0

    # Simple ADSR: short attack, decay to 0.7, sustain, release in last 10%
    attack = min(int(0.01 * sr), n)
    release = min(int(0.1 * n), n)
    env = np.ones(n)
    env[:attack] = np.linspace(0, 1, attack)
    env[n - release:] = np.linspace(1, 0, release)
    return (sig * env * 0.5).astype(np.float32)


def _synth_track_to_wav(track_def: dict, tempo: float,
                         out_path: Path, sr: int = SYNTH_SR) -> None:
    """
    Render a single DSL track definition to a mono WAV file.
    track_def keys: track (name), type (pattern|melody), data/notes, duration
    """
    t_type = track_def.get("type")
    is_drum = track_def.get("track", "").lower() in ("drums", "drum", "kick", "percussion", "perc")
    # Choose waveform per track name
    name = track_def.get("track", "").lower()
    waveform = "sine" if "synth" in name or "pad" in name or "lead" in name else "sawtooth"

    beat_dur = 60.0 / tempo
    buffer: List[np.ndarray] = []

    if t_type == "pattern":
        steps = track_def.get("data", [])
        step_dur = beat_dur / 2.0   # 16th-note steps
        total = len(steps) * step_dur
        buf = np.zeros(int(total * sr), dtype=np.float32)
        pitch = 36 if is_drum else 60
        for i, step in enumerate(steps):
            if step:
                sample = _drum_sample(pitch, sr) if is_drum else _tone_sample(pitch, step_dur * 0.9, waveform, sr)
                start = int(i * step_dur * sr)
                end = start + len(sample)
                if end <= len(buf):
                    buf[start:end] += sample
                else:
                    buf[start:] += sample[:len(buf) - start]
        buffer.append(buf)

    elif t_type == "melody":
        notes = track_def.get("notes", [])
        dur_map = {"whole": 4.0, "half": 2.0, "quarter": 1.0,
                   "eighth": 0.5, "sixteenth": 0.25}
        dur_str = str(track_def.get("duration", "quarter"))
        note_beats = dur_map.get(dur_str, 1.0)
        note_dur = note_beats * beat_dur
        total = len(notes) * note_dur
        buf = np.zeros(int(total * sr) + sr, dtype=np.float32)  # +1s padding
        ts = 0
        for n in notes:
            pitch = note_to_midi(str(n)) if isinstance(n, str) else int(n)
            sample = _tone_sample(pitch, note_dur * 0.9, waveform, sr)
            end = ts + len(sample)
            if end <= len(buf):
                buf[ts:end] += sample
            else:
                buf[ts:] += sample[:len(buf) - ts]
            ts += int(note_dur * sr)
        buffer.append(buf[:ts])

    if not buffer:
        return

    audio = np.concatenate(buffer)
    # Normalise to -3 dBFS
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.7
    sf.write(str(out_path), audio, sr, subtype="PCM_16")


class CodeToMusicModel(BaseModel):
    MODEL_ID = "wavy-labs/code-to-music"

    def _load(self) -> None:
        self._loaded = True
        logger.info("Code-to-Music converter ready.")

    def convert(
        self,
        code: str = "",
        mode: str = "dsl",
        csv_data: str = "",
        json_data: str = "",
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        if mode == "dsl":
            return self._from_dsl(code)
        elif mode == "python":
            return self._from_python(code)
        elif mode == "csv":
            return self._from_csv(csv_data or code)
        elif mode == "json_data":
            return self._from_json(json_data or code)
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

    # ── DSL ───────────────────────────────────────────────────────────────────

    def _from_dsl(self, code: str) -> Dict[str, Any]:
        logger.info("Parsing Wavy DSL …")
        song = _PARSER.parse(code)
        return self._song_to_midi(song)

    # ── Python snippet ────────────────────────────────────────────────────────

    def _from_python(self, code: str) -> Dict[str, Any]:
        """Execute Python in a sandboxed namespace that exposes the Wavy DSL API."""
        logger.info("Evaluating Python code-to-music snippet …")
        tracks_collected: List[dict] = []
        meta = {"tempo": 120, "key": "C major"}

        def track(name: str):
            class _TrackBuilder:
                def __init__(self, n): self._n = n
                def pattern(self, data, bpm=120, **kw):
                    meta["tempo"] = bpm
                    tracks_collected.append({"track": self._n, "type": "pattern",
                                             "data": data, **kw})
                    return self
                def melody(self, notes, duration="quarter", **kw):
                    tracks_collected.append({"track": self._n, "type": "melody",
                                             "notes": notes, "duration": duration, **kw})
                    return self
                def generate(self, prompt, **kw):
                    tracks_collected.append({"track": self._n, "type": "generate",
                                             "prompt": prompt, **kw})
                    return self
            return _TrackBuilder(name)

        # Expose note constants (C3, D4, etc.) into namespace
        note_ns: dict = {}
        for note, _ in NOTE_NAMES.items():
            for oct_ in range(0, 9):
                note_ns[f"{note}{oct_}"] = f"{note}{oct_}"

        # Restrict builtins to a safe whitelist — prevents import/open/exec escapes.
        _SAFE_BUILTINS = {
            b: __builtins__[b]  # type: ignore[index]
            for b in ("range", "len", "list", "dict", "int", "float", "str",
                      "bool", "abs", "min", "max", "round", "zip", "enumerate",
                      "print", "True", "False", "None")
            if b in (
                __builtins__ if isinstance(__builtins__, dict)  # type: ignore[arg-type]
                else vars(__builtins__)
            )
        }
        namespace = {"track": track, "__builtins__": _SAFE_BUILTINS, **note_ns}
        exec(compile(code, "<wavy-dsl>", "exec"), namespace)  # noqa: S102

        song = {"tracks": tracks_collected, **meta}
        return self._song_to_midi(song)

    # ── CSV ───────────────────────────────────────────────────────────────────

    def _from_csv(self, csv_text: str) -> Dict[str, Any]:
        logger.info("Sonifying CSV data …")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV is empty.")

        cols = list(rows[0].keys())
        pitch_col = cols[0]
        vel_col   = cols[1] if len(cols) > 1 else None
        dur_col   = cols[2] if len(cols) > 2 else None

        notes = []
        vals  = [float(r.get(pitch_col, 60)) for r in rows]
        lo, hi = min(vals), max(vals)
        rng = hi - lo if hi != lo else 1.0

        for row in rows:
            pitch = int(36 + 60 * (float(row.get(pitch_col, 60)) - lo) / rng)
            vel   = int(float(row.get(vel_col, 80))) if vel_col else 80
            dur   = float(row.get(dur_col, 0.5)) if dur_col else 0.5
            notes.append((pitch, vel, dur))

        return self._notes_to_midi(notes, track_name="csv_data")

    # ── JSON ──────────────────────────────────────────────────────────────────

    def _from_json(self, json_text: str) -> Dict[str, Any]:
        logger.info("Sonifying JSON data …")
        data = json.loads(json_text)
        if not isinstance(data, list):
            data = list(data.values()) if isinstance(data, dict) else [data]

        vals = [float(v) if not isinstance(v, dict) else float(list(v.values())[0])
                for v in data]
        lo, hi = min(vals), max(vals)
        rng = hi - lo if hi != lo else 1.0

        notes = [
            (int(36 + 60 * (v - lo) / rng), 80, 0.25)
            for v in vals
        ]
        return self._notes_to_midi(notes, track_name="json_data")

    # ── MIDI helpers ──────────────────────────────────────────────────────────

    def _song_to_midi(self, song: dict) -> Dict[str, Any]:
        tempo = float(song.get("tempo", 120))
        track_defs = []
        generate_requests = []

        mid = mido.MidiFile(type=1, ticks_per_beat=480)
        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage(
            "set_tempo", tempo=mido.bpm2tempo(tempo), time=0))
        mid.tracks.append(tempo_track)

        ticks_per_beat = mid.ticks_per_beat
        for t in song.get("tracks", []):
            t_type = t.get("type")
            name   = t.get("track", "unnamed")

            if t_type == "generate":
                generate_requests.append({"track": name, "prompt": t["prompt"]})
                continue

            track = mido.MidiTrack()
            track.append(mido.MetaMessage("track_name", name=name, time=0))
            events: list = []

            if t_type == "pattern":
                steps = t.get("data", [])
                step_ticks = int(ticks_per_beat / 2)
                pitch = 36 if name.lower() in ("drums", "drum", "kick") else 60
                for i, step in enumerate(steps):
                    if step:
                        events.append((i * step_ticks, "on",  pitch, 80))
                        events.append((int((i + 0.9) * step_ticks), "off", pitch, 0))

            elif t_type == "melody":
                raw_notes = t.get("notes", [])
                dur_str   = str(t.get("duration", "quarter"))
                note_beats = {"whole": 4.0, "half": 2.0, "quarter": 1.0,
                              "eighth": 0.5, "sixteenth": 0.25}.get(dur_str, 1.0)
                note_ticks = int(ticks_per_beat * note_beats)
                ts_ticks = 0
                for n in raw_notes:
                    pitch = note_to_midi(str(n)) if isinstance(n, str) else int(n)
                    events.append((ts_ticks, "on",  pitch, 80))
                    events.append((ts_ticks + int(note_ticks * 0.9), "off", pitch, 0))
                    ts_ticks += note_ticks

            # Sort events by tick and convert to delta-time messages
            events.sort(key=lambda e: e[0])
            last_tick = 0
            for tick, kind, pitch, vel in events:
                delta = tick - last_tick
                msg_type = "note_on" if kind == "on" else "note_off"
                track.append(mido.Message(msg_type, note=pitch,
                                          velocity=vel, time=max(0, delta)))
                last_tick = tick

            mid.tracks.append(track)
            track_defs.append({"track": name, "type": t_type})

        out_dir  = self._ensure_output_dir("code_to_music")
        uid      = uuid.uuid4().hex[:8]
        mid_path = out_dir / f"ctm_{uid}.mid"
        mid.save(str(mid_path))

        logger.info(f"MIDI written: {mid_path}")

        # Synthesize each DSL track to a separate WAV so the timeline gets
        # individual stems instead of a single mixed blob.
        audio_paths: List[str] = []
        for t in song.get("tracks", []):
            if t.get("type") == "generate":
                continue  # handled via ElevenLabs; no local synth needed
            track_name = t.get("track", "unnamed")
            wav_path = out_dir / f"ctm_{uid}_{track_name}.wav"
            try:
                _synth_track_to_wav(t, float(song.get("tempo", 120)), wav_path)
                audio_paths.append(str(wav_path))
                logger.info(f"  Synthesized stem: {wav_path.name}")
            except Exception as exc:
                logger.warning(f"  Synth failed for track {track_name!r}: {exc}")

        return {
            "midi_path":          str(mid_path),
            "audio_paths":        audio_paths,
            "track_defs":         track_defs,
            "generate_requests":  generate_requests,
        }

    def _notes_to_midi(self, notes: List[tuple], track_name: str) -> Dict[str, Any]:
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=track_name, time=0))
        tpb = mid.ticks_per_beat
        # 120 BPM → 1 beat = 0.5 s; ticks per second = tpb * 2
        tps = tpb * 2.0
        last_tick = 0
        events: list = []
        for pitch, vel, dur in notes:
            on_tick  = last_tick
            off_tick = last_tick + int(dur * 0.9 * tps)
            last_tick += int(dur * tps)
            events.append((on_tick,  "on",  pitch, min(127, max(1, vel))))
            events.append((off_tick, "off", pitch, 0))
        events.sort(key=lambda e: e[0])
        cur = 0
        for tick, kind, pitch, vel in events:
            msg_type = "note_on" if kind == "on" else "note_off"
            track.append(mido.Message(msg_type, note=min(127, max(0, pitch)),
                                      velocity=vel, time=max(0, tick - cur)))
            cur = tick
        mid.tracks.append(track)

        out_dir  = self._ensure_output_dir("code_to_music")
        uid      = uuid.uuid4().hex[:8]
        mid_path = out_dir / f"ctm_{track_name}_{uid}.mid"
        mid.save(str(mid_path))

        return {
            "midi_path":         str(mid_path),
            "audio_paths":       [],
            "track_defs":        [{"track": track_name, "type": "data"}],
            "generate_requests": [],
        }
