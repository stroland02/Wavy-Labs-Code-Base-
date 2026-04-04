"""MIDI RPC handlers."""
from __future__ import annotations

import uuid
from pathlib import Path

import mido
import numpy as np
import soundfile as sf
from loguru import logger
from models.registry import ModelRegistry
import config
from rpc.core import _global_context

# ── Audio to MIDI ─────────────────────────────────────────────────────────────

def _audio_to_midi(params: dict, registry: ModelRegistry) -> dict:
    """
    params: audio_path, min_note_dur (default 0.05), hop_length (default 512)
    returns: {"midi_path": str, "note_count": int}
    """
    audio_path = params.get("audio_path", "")
    if not audio_path or not Path(audio_path).is_file():
        return {"error": f"audio_path not found: {audio_path!r}"}
    audio, sr = sf.read(audio_path, always_2d=True)
    mono = audio.mean(axis=1).astype(np.float32)
    hop = int(params.get("hop_length", 512))
    min_dur = float(params.get("min_note_dur", 0.05))
    frame_len = 2048
    pitches = []
    for i in range(0, len(mono) - frame_len, hop):
        frame = mono[i:i + frame_len]
        corr = np.correlate(frame, frame, mode="full")[frame_len - 1:]
        d = np.diff(corr)
        starts = np.where((d[:-1] < 0) & (d[1:] >= 0))[0]
        if len(starts) > 0 and corr[starts[0]] > 0.1:
            period = starts[0] + 1
            freq = sr / period
            if 50 < freq < 4000:
                pitches.append(int(round(12 * np.log2(freq / 440) + 69)))
            else:
                pitches.append(0)
        else:
            pitches.append(0)
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    tpf = int(480 * hop / sr)  # ticks per frame @ 120 BPM
    min_frames = max(1, int(min_dur * sr / hop))
    prev, count = 0, 0
    for pitch in pitches + [0]:
        if pitch == prev:
            count += 1
        else:
            if prev != 0 and count >= min_frames:
                track.append(mido.Message("note_on",  note=prev, velocity=80, time=0))
                track.append(mido.Message("note_off", note=prev, velocity=0,  time=tpf * count))
            elif prev == 0:
                track.append(mido.Message("note_off", note=0, velocity=0, time=tpf * count))
            prev, count = pitch, 1
    out_path = str(Path(audio_path).parent / f"midi_{uuid.uuid4().hex[:8]}.mid")
    mid.save(out_path)
    note_count = sum(1 for m in track if m.type == "note_on")
    return {"midi_path": out_path, "note_count": note_count}


# ── Prompt to MIDI ────────────────────────────────────────────────────────────

def _prompt_to_midi(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, tempo (default 120), bars (default 4)
    returns: {"midi_path": str, "note_count": int, "tempo": int}
    """
    from cloud.router import get_command_provider
    import json as _json
    import re as _re
    prompt = params.get("prompt", "")
    tempo  = int(params.get("tempo", 120))
    bars   = int(params.get("bars", 4))
    MIDI_PROMPT = (
        "Convert this musical description to a JSON list of MIDI notes. "
        "Return ONLY valid JSON: {\"notes\": [{\"pitch\": 60, \"start_beat\": 0, "
        "\"duration_beats\": 1, \"velocity\": 80}, ...]}. "
        f"Description: {prompt}. Tempo: {tempo} BPM, {bars} bars."
    )
    notes = []
    provider = get_command_provider()
    if provider:
        try:
            raw = provider.parse_command(MIDI_PROMPT, {})
            explanation = raw.get("explanation", "")
            m = _re.search(r'\{[^{}]*"notes"[^{}]*\[.*?\]\s*\}', explanation, _re.DOTALL)
            if m:
                notes = _json.loads(m.group())["notes"]
        except Exception as exc:
            logger.warning(f"prompt_to_midi: parse failed ({exc}), using fallback")
    if not notes:
        # C major scale fallback
        pitches = [60, 62, 64, 65, 67, 69, 71, 72]
        notes = [{"pitch": p, "start_beat": i, "duration_beats": 1, "velocity": 80}
                 for i, p in enumerate(pitches)]
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0))
    events = []
    for n in notes:
        start = int(n["start_beat"] * 480)
        end   = int((n["start_beat"] + n["duration_beats"]) * 480)
        events.append((start, "note_on",  int(n["pitch"]), int(n.get("velocity", 80))))
        events.append((end,   "note_off", int(n["pitch"]), 0))
    events.sort(key=lambda x: x[0])
    prev_tick = 0
    for tick, msg_type, pitch, vel in events:
        track.append(mido.Message(msg_type, note=pitch, velocity=vel, time=tick - prev_tick))
        prev_tick = tick
    config.GENERATION_DIR.mkdir(parents=True, exist_ok=True)
    out_path = str(config.GENERATION_DIR / f"prompt_midi_{uuid.uuid4().hex[:8]}.mid")
    mid.save(out_path)
    return {"midi_path": out_path, "note_count": len(notes), "tempo": tempo}


# ── Chord Suggestions (A2) ────────────────────────────────────────────────────

def _chord_suggestions(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, key, scale, num_chords (default 4), style
    Merges _global_context for key/scale/style when not provided.
    returns: {chords:[{name,root,quality,function,color,notes:[int]}], key, scale, widget:"chords"}
    """
    import json as _json
    import re as _re
    from cloud.router import get_command_provider

    prompt     = params.get("prompt", "")
    key        = params.get("key")   or _global_context.get("key",   "C")
    scale      = params.get("scale") or _global_context.get("scale", "minor")
    num_chords = int(params.get("num_chords", 4))
    style      = params.get("style") or _global_context.get("style", "default")

    CHORD_SYSTEM = (
        "You are a music theory expert. Return ONLY valid JSON with this structure:\n"
        '{"chords": [{"name": "Cm", "root": "C", "quality": "minor", '
        '"function": "tonic", "color": "#3498db"}, ...]}\n'
        f"Include exactly {num_chords} chords. "
        "quality must be one of: major, minor, dom7, maj7, min7, sus2, sus4\n"
        "No extra text."
    )

    chords: list[dict] = []
    provider = get_command_provider()
    if provider:
        try:
            user_msg = (
                f"Chord progression for: {prompt}. "
                f"Key: {key} {scale}. Style: {style}. "
                f"Give {num_chords} chords."
            )
            raw = provider.parse_command(f"{CHORD_SYSTEM}\n\nUser: {user_msg}", {})
            explanation = raw.get("explanation", "")
            m = _re.search(r'\{[^{}]*"chords"\s*:\s*\[.*?\]\s*\}', explanation, _re.DOTALL)
            if m:
                chords = _json.loads(m.group()).get("chords", [])
        except Exception as exc:
            logger.warning(f"_chord_suggestions LLM failed: {exc}")

    if not chords:
        from utils.music_theory import (_SEMITONE_MAP, _COMMON_PROGRESSIONS)
        root_semitone = _SEMITONE_MAP.get(key, 0)
        prog_key = scale.lower() if scale.lower() in _COMMON_PROGRESSIONS else "minor"
        progression = _COMMON_PROGRESSIONS[prog_key]
        inv_map = {v: k for k, v in _SEMITONE_MAP.items()}
        _colors = ["#3498db", "#9b59b6", "#e74c3c", "#2ecc71"]
        _funcs  = ["tonic", "subdominant", "mediant", "dominant"]
        for i, (offset, quality) in enumerate(progression[:num_chords]):
            semitone = (root_semitone + offset) % 12
            root_name = inv_map.get(semitone, "C")
            suffix = "" if quality == "major" else "m" if quality == "minor" else quality
            chords.append({
                "name":     root_name + suffix,
                "root":     root_name,
                "quality":  quality,
                "function": _funcs[i % 4],
                "color":    _colors[i % 4],
            })

    # Add MIDI voicing to each chord
    from utils.music_theory import chord_voicing
    for chord in chords:
        voicing = chord_voicing(chord.get("root", "C"), chord.get("quality", "major"), octave=4)
        chord["notes"] = [n["pitch"] for n in voicing]

    return {
        "chords": chords,
        "key":    key,
        "scale":  scale,
        "widget": "chords",
    }


# ── Beat Builder (A3) ─────────────────────────────────────────────────────────

def _beat_builder(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, genre, bpm, bars (default 1)
    Merges _global_context for bpm.
    returns: {rows:[{name,color,steps:[bool×16]}], bpm, bars, genre, widget:"beat_grid"}
    """
    import json as _json
    import re as _re
    from cloud.router import get_command_provider

    prompt = params.get("prompt", "")
    genre  = params.get("genre", "")
    bpm    = int(params.get("bpm") or _global_context.get("bpm", 120))
    bars   = int(params.get("bars", 1))

    # Detect genre from prompt
    if not genre:
        prompt_lower = prompt.lower()
        for g in ("trap", "lo-fi", "lofi", "house", "dnb", "drum and bass"):
            if g in prompt_lower:
                genre = g
                break
        if not genre:
            genre = "generic"

    rows: list[dict] | None = None
    provider = get_command_provider()
    if provider:
        BEAT_SYSTEM = (
            "You are a drum machine programmer. Given a genre/prompt, output a 16-step drum pattern.\n"
            "Output ONLY valid JSON:\n"
            '{"rows": [{"name": "Kick", "color": "#e74c3c", '
            '"steps": [true,false,false,false,true,false,false,false,'
            'true,false,false,false,true,false,false,false]}, ...], "bpm": 120}\n'
            "Include Kick, Snare, Hi-Hat, Clap rows. "
            "steps: exactly 16 booleans (16th notes, 1 bar). No extra text."
        )
        try:
            raw = provider.parse_command(
                f"{BEAT_SYSTEM}\n\nUser: {prompt} genre={genre} bpm={bpm}", {})
            explanation = raw.get("explanation", "")
            m = _re.search(r'\{[\s\S]*?"rows"\s*:\s*\[[\s\S]*?\]\s*[\s\S]*?\}', explanation)
            if m:
                parsed = _json.loads(m.group())
                rows = parsed.get("rows")
                if parsed.get("bpm"):
                    bpm = int(parsed["bpm"])
        except Exception as exc:
            logger.warning(f"_beat_builder LLM failed: {exc}")

    if not rows:
        from utils.music_theory import drum_pattern_to_steps
        rows = drum_pattern_to_steps(genre, bars=1)

    return {
        "rows":   rows,
        "bpm":    bpm,
        "bars":   bars,
        "genre":  genre,
        "prompt": prompt,
        "widget": "beat_grid",
    }


# ── Regenerate Bar (A1) ───────────────────────────────────────────────────────

def _regenerate_bar(params: dict, registry: ModelRegistry) -> dict:
    """
    params: session_id, part_name, bar_index, role (optional), key, scale, bpm
    returns: {midi_path, note_count, notes, note_summary, bar_index, part_name}
    """
    from agents.compose_agent import ComposeAgent
    return ComposeAgent().regenerate_bar(params, registry)


# ── Instrument Choices ────────────────────────────────────────────────────────

def _get_instrument_choices(params: dict, registry: ModelRegistry) -> dict:
    """Return the user-selectable instrument catalog per role."""
    from agents.compose_agent import _INSTRUMENT_CHOICES
    return {"choices": _INSTRUMENT_CHOICES}


# ── Compose Agent ─────────────────────────────────────────────────────────────

def _compose(params: dict, registry: ModelRegistry) -> dict:
    """
    params: prompt, mode ("fill"|"arrange"), session_id, daw_context, bars, bpm
    returns:
      mode=="arrange": {mode, parts:[{name,midi_path,color,note_count}], explanation, session_id, bpm, key, bars}
      mode=="fill":    {mode, midi_path, note_count, explanation, session_id}
    Uses text2midi (amaai-lab/text2midi) for generation.
    """
    import traceback
    try:
        prompt = params.get("prompt", "").strip() or "lofi hip hop melody"
        mode   = params.get("mode", "arrange")
        sid    = params.get("session_id", "")
        bpm    = int(params.get("bpm", 90))
        bars   = int(params.get("bars", 4))

        logger.info(f"[compose] text2midi mode={mode!r} prompt={prompt[:80]!r}")

        model     = registry.get("text2midi")
        midi_path = model.generate(prompt, max_len=1024)

        # Count notes via mido
        note_count = 0
        try:
            import mido
            mid = mido.MidiFile(midi_path)
            note_count = sum(
                1 for t in mid.tracks
                for m in t if m.type == "note_on" and m.velocity > 0
            )
        except Exception:
            pass

        explanation = f"Generated MIDI: {prompt[:60]}"
        logger.info(f"[compose] done — {note_count} notes → {midi_path}")

        if mode == "fill":
            return {
                "mode":        "fill",
                "midi_path":   midi_path,
                "note_count":  note_count,
                "explanation": explanation,
                "session_id":  sid,
            }
        else:
            return {
                "mode": "arrange",
                "parts": [{
                    "name":       "AI Composition",
                    "midi_path":  midi_path,
                    "color":      "#9b59b6",
                    "note_count": note_count,
                    "instrument": "tripleoscillator",
                }],
                "explanation": explanation,
                "session_id":  sid,
                "bpm":         bpm,
                "key":         "C",
                "bars":        bars,
            }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error(f"[compose] FAILED: {exc}\n{tb}")
        raise


# ── MIDI Extend (v0.12.0) ──────────────────────────────────────────────────────

def _midi_extend(params: dict, registry: ModelRegistry) -> dict:
    """Extend an existing MIDI file by generating continuation bars.

    params:
        midi_path    : str — path to existing MIDI file
        bars_to_add  : int — number of bars to append (default 4)
        prompt       : str — style hint for continuation
        bpm          : int — BPM (default 120)
    returns:
        {midi_path, note_count, bars}
    """
    midi_path = params.get("midi_path", "")
    if not midi_path or not Path(midi_path).is_file():
        return {"error": f"midi_path not found: {midi_path!r}"}

    bars_to_add = int(params.get("bars_to_add", 4))
    prompt = params.get("prompt", "")
    bpm = int(params.get("bpm", 120))

    # Read existing MIDI to extract context
    orig = mido.MidiFile(midi_path)
    tpb = orig.ticks_per_beat or 480
    bar_ticks = tpb * 4  # 4/4 time

    # Collect all notes and find total length
    all_notes = []
    max_tick = 0
    for track in orig.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                all_notes.append((abs_tick, msg.note, msg.velocity))
            max_tick = max(max_tick, abs_tick)

    existing_bars = max(1, (max_tick + bar_ticks - 1) // bar_ticks)

    # Build context description from existing notes
    if all_notes:
        pitches = sorted(set(n[1] for n in all_notes))
        pitch_str = ", ".join(str(p) for p in pitches[:12])
        context_prompt = f"Continue this MIDI piece. Existing pitches: {pitch_str}. "
    else:
        context_prompt = "Generate a MIDI continuation. "

    if prompt:
        context_prompt += f"Style: {prompt}. "
    context_prompt += f"{bpm} BPM, {bars_to_add} bars."

    # Generate continuation via text2midi
    try:
        model = registry.get("text2midi")
        gen_path = model.generate(context_prompt, max_len=1024)
    except Exception as exc:
        logger.warning(f"[midi_extend] text2midi failed: {exc}, using simple extension")
        # Fallback: repeat last N bars
        gen_path = None

    if gen_path and Path(gen_path).is_file():
        gen_mid = mido.MidiFile(gen_path)
        # Merge: append generated notes after existing end
        result_mid = mido.MidiFile(ticks_per_beat=tpb)
        result_track = mido.MidiTrack()
        result_mid.tracks.append(result_track)
        result_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

        # Copy original notes
        for track in orig.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type in ("note_on", "note_off"):
                    result_track.append(msg.copy())

        # Append generated notes offset by existing length
        offset_tick = existing_bars * bar_ticks
        gen_tpb = gen_mid.ticks_per_beat or 480
        scale = tpb / gen_tpb
        for track in gen_mid.tracks:
            abs_tick = 0
            first_note = True
            for msg in track:
                abs_tick += msg.time
                if msg.type in ("note_on", "note_off"):
                    scaled_time = int(msg.time * scale)
                    if first_note:
                        # Add offset to first note
                        new_msg = msg.copy(time=offset_tick + int(abs_tick * scale))
                        first_note = False
                    else:
                        new_msg = msg.copy(time=scaled_time)
                    result_track.append(new_msg)

        out_path = str(Path(midi_path).parent / f"extended_{uuid.uuid4().hex[:8]}.mid")
        result_mid.save(out_path)
    else:
        # Fallback: duplicate last bars
        result_mid = mido.MidiFile(ticks_per_beat=tpb)
        result_track = mido.MidiTrack()
        result_mid.tracks.append(result_track)
        result_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

        # Copy all original events
        for track in orig.tracks:
            for msg in track:
                if msg.type in ("note_on", "note_off"):
                    result_track.append(msg.copy())

        # Repeat last 4 bars (or all if fewer)
        repeat_start = max(0, (existing_bars - min(4, existing_bars))) * bar_ticks
        for track in orig.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type in ("note_on", "note_off") and abs_tick >= repeat_start:
                    offset = existing_bars * bar_ticks + (abs_tick - repeat_start)
                    result_track.append(msg.copy(time=int(msg.time)))

        out_path = str(Path(midi_path).parent / f"extended_{uuid.uuid4().hex[:8]}.mid")
        result_mid.save(out_path)

    note_count = sum(1 for t in mido.MidiFile(out_path).tracks
                     for m in t if m.type == "note_on" and m.velocity > 0)
    return {
        "midi_path": out_path,
        "note_count": note_count,
        "bars": existing_bars + bars_to_add,
    }


# ── MIDI Recompose (v0.12.0) ──────────────────────────────────────────────────

def _midi_recompose(params: dict, registry: ModelRegistry) -> dict:
    """Recompose a section of a MIDI file with a new style.

    params:
        midi_path   : str — path to MIDI file
        style       : str — target style/genre/feel
        start_bar   : int — start bar (0-indexed, default 0)
        end_bar     : int — end bar (exclusive, default 4)
        bpm         : int — BPM (default 120)
    returns:
        {midi_path, note_count}
    """
    midi_path = params.get("midi_path", "")
    if not midi_path or not Path(midi_path).is_file():
        return {"error": f"midi_path not found: {midi_path!r}"}

    style = params.get("style", "")
    start_bar = int(params.get("start_bar", 0))
    end_bar = int(params.get("end_bar", 4))
    bpm = int(params.get("bpm", 120))

    orig = mido.MidiFile(midi_path)
    tpb = orig.ticks_per_beat or 480
    bar_ticks = tpb * 4

    start_tick = start_bar * bar_ticks
    end_tick = end_bar * bar_ticks
    bars_to_replace = end_bar - start_bar

    # Collect notes outside the replacement range
    kept_notes = []
    replaced_notes = []
    for track in orig.tracks:
        abs_tick = 0
        active = {}
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active[msg.note] = (abs_tick, msg.velocity)
            elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
                if msg.note in active:
                    on_tick, vel = active.pop(msg.note)
                    note_data = (on_tick, abs_tick - on_tick, msg.note, vel)
                    if on_tick >= start_tick and on_tick < end_tick:
                        replaced_notes.append(note_data)
                    else:
                        kept_notes.append(note_data)

    # Build prompt for replacement section
    context = f"Recompose {bars_to_replace} bars"
    if style:
        context += f" in {style} style"
    context += f", {bpm} BPM"
    if replaced_notes:
        orig_pitches = sorted(set(n[2] for n in replaced_notes))
        context += f", original pitches: {orig_pitches[:8]}"

    # Generate replacement via text2midi
    try:
        model = registry.get("text2midi")
        gen_path = model.generate(context, max_len=1024)
    except Exception as exc:
        logger.warning(f"[midi_recompose] text2midi failed: {exc}")
        return {"error": f"Generation failed: {_clean_str(exc)}"}

    # Build result: kept notes + generated notes in the replacement range
    result_mid = mido.MidiFile(ticks_per_beat=tpb)
    result_track = mido.MidiTrack()
    result_mid.tracks.append(result_track)
    result_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # Add kept notes
    events = []
    for on_tick, dur, pitch, vel in kept_notes:
        events.append((on_tick, "note_on", pitch, vel))
        events.append((on_tick + dur, "note_off", pitch, 0))

    # Add generated notes offset to replacement range
    if gen_path and Path(gen_path).is_file():
        gen_mid = mido.MidiFile(gen_path)
        gen_tpb = gen_mid.ticks_per_beat or 480
        scale = tpb / gen_tpb
        for track in gen_mid.tracks:
            abs_tick = 0
            gen_active = {}
            for msg in track:
                abs_tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    gen_active[msg.note] = (abs_tick, msg.velocity)
                elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
                    if msg.note in gen_active:
                        on_t, vel = gen_active.pop(msg.note)
                        # Clamp to replacement range
                        mapped_on = start_tick + int(on_t * scale)
                        mapped_dur = int((abs_tick - on_t) * scale)
                        if mapped_on < end_tick:
                            mapped_dur = min(mapped_dur, end_tick - mapped_on)
                            events.append((mapped_on, "note_on", msg.note, vel))
                            events.append((mapped_on + mapped_dur, "note_off", msg.note, 0))

    events.sort(key=lambda x: x[0])
    prev_tick = 0
    for tick, msg_type, pitch, vel in events:
        result_track.append(mido.Message(msg_type, note=pitch, velocity=vel, time=tick - prev_tick))
        prev_tick = tick

    out_path = str(Path(midi_path).parent / f"recomposed_{uuid.uuid4().hex[:8]}.mid")
    result_mid.save(out_path)
    note_count = sum(1 for m in result_track if m.type == "note_on" and m.velocity > 0)
    return {"midi_path": out_path, "note_count": note_count}


# ── MIDI Layering (v0.12.0) ──────────────────────────────────────────────────

def _midi_layer(params: dict, registry: ModelRegistry) -> dict:
    """Generate a complementary MIDI layer for an existing track.

    params:
        midi_path   : str — path to source MIDI file
        layer_type  : str — "harmony"|"counter_melody"|"arpeggio"|"bass"
        bpm         : int — BPM (default 120)
        key         : str — key (default "C")
        scale       : str — scale (default "minor")
    returns:
        {midi_path, note_count, role}
    """
    midi_path = params.get("midi_path", "")
    if not midi_path or not Path(midi_path).is_file():
        return {"error": f"midi_path not found: {midi_path!r}"}

    layer_type = params.get("layer_type", "harmony")
    bpm = int(params.get("bpm", 120))
    key = params.get("key", "C")
    scale = params.get("scale", "minor")

    # Analyze source MIDI
    orig = mido.MidiFile(midi_path)
    pitches = set()
    for track in orig.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                pitches.add(msg.note)

    pitch_list = sorted(pitches)[:12]

    # Build generation prompt
    role_prompts = {
        "harmony": f"Generate a harmony part that complements pitches {pitch_list}. "
                   f"Use thirds and sixths intervals. Key: {key} {scale}.",
        "counter_melody": f"Generate a counter-melody against pitches {pitch_list}. "
                          f"Use contrary motion and passing tones. Key: {key} {scale}.",
        "arpeggio": f"Generate arpeggiated patterns based on chords implied by {pitch_list}. "
                    f"Use 16th note arpeggios. Key: {key} {scale}.",
        "bass": f"Generate a bass line that supports pitches {pitch_list}. "
                f"Use root notes and fifths, octave below. Key: {key} {scale}.",
    }
    prompt = role_prompts.get(layer_type, role_prompts["harmony"])
    prompt += f" {bpm} BPM."

    try:
        model = registry.get("text2midi")
        gen_path = model.generate(prompt, max_len=1024)
    except Exception as exc:
        logger.warning(f"[midi_layer] text2midi failed: {exc}")
        return {"error": f"Layer generation failed: {_clean_str(exc)}"}

    # For bass layer, transpose down an octave
    if layer_type == "bass" and gen_path and Path(gen_path).is_file():
        gen_mid = mido.MidiFile(gen_path)
        for track in gen_mid.tracks:
            for msg in track:
                if msg.type in ("note_on", "note_off") and msg.note > 0:
                    msg.note = max(24, msg.note - 12)
        out_path = str(Path(midi_path).parent / f"layer_{layer_type}_{uuid.uuid4().hex[:8]}.mid")
        gen_mid.save(out_path)
    else:
        out_path = gen_path or ""

    if not out_path or not Path(out_path).is_file():
        return {"error": "Layer generation produced no output"}

    note_count = sum(1 for t in mido.MidiFile(out_path).tracks
                     for m in t if m.type == "note_on" and m.velocity > 0)

    role_names = {
        "harmony": "Harmony",
        "counter_melody": "Counter-Melody",
        "arpeggio": "Arpeggio",
        "bass": "Bass Line",
    }

    return {
        "midi_path": out_path,
        "note_count": note_count,
        "role": role_names.get(layer_type, "Layer"),
    }

