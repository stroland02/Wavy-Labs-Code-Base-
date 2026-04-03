# Prompt Commands

Control the DAW with natural language. Wavy Labs understands your intent and
translates it into LMMS actions.

!!! note "Studio feature"
    Prompt Commands require a **Studio** subscription ($24.99/mo).

## Opening the Prompt Bar

Press **Ctrl+K** (or **Cmd+K** on macOS) from anywhere in the application.

The prompt bar appears at the bottom of the window.

---

## Example Commands

### Track Management

```
Add a 4-bar drum loop at 120 BPM
Duplicate track "Lead Synth" and pan it hard right
Delete the selected track
Rename track 3 to "Strings"
```

### Clip Editing

```
Transpose the selected clip up 3 semitones
Loop the selection 4 times
Split the clip at the playhead
Quantize notes to 1/16
```

### Mixer Controls

```
Set the reverb send on channel 2 to 40%
Mute the drums bus
Set master volume to 80%
Solo track "Vocals"
```

### Arrangement

```
Create a verse-chorus-verse-bridge-chorus arrangement
Add 8 bars of silence before bar 16
Move all tracks 4 bars to the right
```

### AI Actions

```
Generate a 30-second lo-fi beat and add it as a new track
Split the stems of the first SampleTrack
Master the current song
```

---

## How It Works

1. Your command is sent to the local **Mistral 7B** model.
2. Mistral parses the intent into a structured JSON action:
   ```json
   { "type": "set_volume", "track": 3, "value": 0.8 }
   ```
3. The C++ **ActionDispatcher** maps the JSON to the corresponding LMMS Engine API call.
4. The result appears immediately in the DAW.

All processing is local — the command never leaves your machine.

---

## Action Schema

Full reference of supported action types:

| Action type | Parameters |
|------------|------------|
| `add_track` | `name`, `type` (sample/instrument/automation) |
| `delete_track` | `track` (id or name) |
| `rename_track` | `track`, `name` |
| `duplicate_track` | `track` |
| `set_volume` | `track` or `channel`, `value` (0.0–1.0) |
| `set_pan` | `track` or `channel`, `value` (–1.0 to 1.0) |
| `set_mute` | `track`, `muted` (bool) |
| `set_solo` | `track`, `solo` (bool) |
| `set_reverb` | `channel`, `send` (0.0–1.0) |
| `transpose_clip` | `semitones` |
| `quantize_notes` | `division` (e.g. `"1/16"`) |
| `generate_music` | `prompt`, `duration`, `tempo` |
| `split_stems` | `track`, `num_stems` |
| `master_audio` | `target_lufs` |

---

## Model

**Mistral 7B Instruct v0.3 (GGUF Q4_K_M)** via llama-cpp-python — 8 GB VRAM.
Typical response time: 1–2 seconds on a modern GPU.
