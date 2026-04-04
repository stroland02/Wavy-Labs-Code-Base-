# AI Music Generation

Generate complete audio tracks from a text description in seconds.

## Models

| Model | VRAM | Speed | Best for |
|-------|------|-------|---------|
| **ACE-Step 1.5** | 4 GB | ~20 s / 4 min song | Quality, nuance, complex arrangements |
| **DiffRhythm 2** | 8 GB | ~10 s / full song | Speed, iterating quickly, demos |

Both models are commercially licensed (Apache 2.0) and run entirely locally.

## Parameters

### Prompt
A free-text description of the music you want. Be specific for best results:

```
Cinematic orchestral piece, building tension with strings and brass,
resolving into a triumphant major key theme. No drums. 90 BPM.
```

### Genre
An optional genre hint. When set, it conditions the model's style token.
Select `(none)` to let the prompt guide style freely.

### Key
Key and mode selector. Useful when the generated track needs to fit an existing
project in a specific key.

### Tempo
BPM hint passed to the model. The model may deviate slightly; use the **Tempo
Detection** tool in the Song Editor if you need a precise tempo.

### Duration
Target length in seconds (10 – 240 s). Longer durations take proportionally more time.

---

## Modes

### Single Generation (⚡ Generate)
Runs one inference pass and inserts the result directly into the Song Editor.
Consumes **1** daily generation on the free tier.

### Best of 3 (⚡×3 Best of 3)
Runs three inference passes in parallel, each with a different random seed,
producing three distinct variations. A comparison dialog opens so you can
preview each one (via your default audio player) and pick the best.

Consumes **3** daily generations on the free tier.

!!! tip
    Use different seeds explicitly via the prompt (`seed=42`) if you want
    reproducible results.

---

## Inserting into the Project

Generated audio is inserted as a **SampleTrack** at bar 1 of the Song Editor.
Drag the clip, trim it, or use it as a stem-splitting input right away.

---

## Free Tier Limits

Free accounts receive **5 AI generations per day** (resets at midnight local time).
Each "Best of 3" attempt counts as 3 generations.

Upgrade to **Pro** for unlimited generations.
