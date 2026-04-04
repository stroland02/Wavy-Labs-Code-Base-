# Vocal Generation

Generate sung or spoken vocals from lyrics text using Bark (Suno AI, MIT license).

!!! note "Pro feature"
    Vocal Generation requires a **Pro** subscription ($9.99/mo).

## How to Use

1. Open the AI Panel (**Ctrl+Shift+A**) and switch to the **🎤 Vocal** tab.
2. Enter your lyrics in the text field.
3. Select a **Voice Preset** from the dropdown.
4. Adjust the **Temperature** slider (higher = more expressive / less stable).
5. Click **🎤 Generate Vocal**.
6. The resulting `.wav` is inserted as a new SampleTrack.

---

## Voice Presets

| Preset | Character |
|--------|-----------|
| Speaker 0 | Deep male |
| Speaker 1 | Male |
| Speaker 2 | Warm male |
| Speaker 3 | High female |
| Speaker 4 | Warm female |
| Speaker 5 | Narrator |
| Speaker 6 | Breathy |
| Speaker 7 | Elderly male |
| Speaker 8 | Young female |
| Speaker 9 | Whisper |

## Temperature

Controls randomness in the synthesis:

| Value | Effect |
|-------|--------|
| 0.1 – 0.4 | Stable, consistent, less expressive |
| 0.5 – 0.7 | Balanced (recommended) |
| 0.8 – 1.0 | More expressive, may introduce artifacts |

---

## Tips

- Keep lyrics under ~200 words for best coherence.
- Add `[laughs]`, `[sighs]`, `[clears throat]` to inject non-verbal sounds.
- Use line breaks to control phrasing and natural pauses.
- Run multiple generations with slightly different temperatures to pick the best take.

---

## Model

**Bark** (Suno AI, MIT license) — 6 GB VRAM recommended.
CPU fallback is available but slow (~5–15 min per generation).
