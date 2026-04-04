# RPC Methods Reference

All methods follow the [IPC Protocol](ipc-protocol.md) (JSON-RPC 2.0 over ZeroMQ).

---

## `health`

Check backend connectivity and model status.

**Params:** _(none)_

**Result:**
```json
{
  "status": "ok",
  "models": {
    "ace_step": "loaded",
    "demucs": "idle",
    "bark": "not_downloaded"
  }
}
```

---

## `generate_music`

Generate an audio track from a text prompt.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | yes | Music description |
| `model` | string | no | `"ace_step"` (default) or `"diffrhythm"` |
| `duration` | number | no | Target duration in seconds (default: 30) |
| `tempo` | integer | no | BPM hint (default: 120) |
| `genre` | string | no | Genre tag |
| `key` | string | no | Key/mode (e.g. `"C minor"`) |
| `seed` | integer | no | Random seed for reproducibility |

**Result:**
```json
{
  "audio_path": "/tmp/wavy/gen_xxx.wav",
  "duration": 30.4,
  "model_used": "ace_step"
}
```

---

## `split_stems`

Separate an audio file into instrument stems.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio_path` | string | yes | Path to source audio file |
| `stems` | integer | no | Number of stems: 2, 4, or 6 (default: 4) |

**Result:**
```json
{
  "stems": {
    "vocals": "/tmp/wavy/stems/vocals.wav",
    "drums":  "/tmp/wavy/stems/drums.wav",
    "bass":   "/tmp/wavy/stems/bass.wav",
    "other":  "/tmp/wavy/stems/other.wav"
  }
}
```

---

## `generate_vocal`

Synthesize a vocal track from lyrics.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lyrics` | string | yes | Lyrics text |
| `voice_preset` | string | no | Bark speaker ID (e.g. `"v2/en_speaker_6"`) |
| `temperature` | number | no | Synthesis temperature, 0.1–1.0 (default: 0.7) |

**Result:**
```json
{
  "audio_path": "/tmp/wavy/vocal_xxx.wav",
  "duration": 14.2
}
```

---

## `mix_analyze`

Analyze audio tracks and return mixing suggestions.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `track_paths` | array | yes | List of audio file paths to analyze |
| `reference_path` | string | no | Reference track for tonal matching |

**Result:**
```json
{
  "suggestions": [
    { "type": "set_volume", "track": "drums", "value": 0.75 },
    { "type": "set_reverb", "channel": 3, "send": 0.2 }
  ],
  "loudness_lufs": -18.4
}
```

---

## `master_audio`

Apply mastering chain to an audio file.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio_path` | string | yes | Input audio path |
| `target_lufs` | number | no | Target loudness (default: –14.0) |

**Result:**
```json
{
  "output_path": "/tmp/wavy/mastered_xxx.wav",
  "input_lufs": -18.4,
  "output_lufs": -14.0
}
```

---

## `prompt_command`

Parse and execute a natural language DAW command.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | yes | Natural language instruction |
| `context` | object | no | Current DAW state (tracks, bpm, etc.) |

**Result:**
```json
{
  "actions": [
    { "type": "add_track", "name": "Drums", "track_type": "sample" }
  ],
  "explanation": "Added a new SampleTrack named 'Drums'."
}
```

---

## `code_to_music`

Parse and execute a Wavy DSL script.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | yes | Wavy DSL or Python sonification script |
| `mode` | string | no | `"dsl"` (default), `"python"`, or `"midi"` |

**Result:**
```json
{
  "tracks": [
    { "name": "drums", "audio_path": "/tmp/wavy/drums.wav", "midi_path": null },
    { "name": "bass",  "audio_path": "/tmp/wavy/bass.wav",  "midi_path": null }
  ],
  "bpm": 140,
  "duration": 16.0
}
```

---

## `list_models`

List all available models and their load state.

**Params:** _(none)_

**Result:**
```json
{
  "models": [
    { "id": "ace_step",   "state": "loaded",   "vram_mb": 4096 },
    { "id": "diffrhythm", "state": "idle",      "vram_mb": 8192 },
    { "id": "demucs",     "state": "loaded",    "vram_mb": 4096 },
    { "id": "bark",       "state": "not_found", "vram_mb": 6144 }
  ]
}
```

---

## `load_model` / `unload_model`

Explicitly load or unload a model.

**Params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | yes | Model identifier (see `list_models`) |

**Result:**
```json
{ "status": "ok", "model_id": "bark" }
```
