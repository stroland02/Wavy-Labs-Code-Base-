# AI Mix & Master

Automatically analyze, balance, and master your tracks using the ONNX mixing pipeline.

!!! note "Pro feature"
    AI Mix & Master requires a **Pro** subscription ($9.99/mo).

## AI Mix Assist

Analyzes all audio clips routed to a mixer channel and suggests EQ, compression,
and reverb adjustments. Suggestions are applied as **LMMS Automation Patterns**
so they are fully editable and non-destructive.

### How to Use

1. In the FX Mixer, right-click a channel.
2. Go to **Wavy Labs AI → AI Mix Assist…**
3. The AI analyzes the tracks and applies automation suggestions.
4. Open the **Automation Editor** to review, adjust, or revert any suggestion.

### From the AI Panel

1. Open the AI Panel and go to the **🎚 Mix / Master** tab.
2. Click **🔬 Analyze Mix** and select a reference audio file (optional — enables
   reference-track matching mode).

---

## AI Master Channel

Applies loudness normalization, multiband compression, limiting, and stereo
enhancement to produce a broadcast-ready master.

### How to Use

1. Right-click a mixer channel → **Wavy Labs AI → AI Master Channel…**
2. Processing runs in the background.
3. The mastered file is inserted as a new SampleTrack with an electric-blue header.

### From the AI Panel

Click **🏆 Master Audio** in the **Mix / Master** tab and select the file to master.

### Target loudness

Default target: **–14 LUFS** (streaming standard for Spotify, Apple Music, YouTube).

---

## Reference Track Mode

Supply a reference `.wav` or `.mp3` to make your mix match the spectral profile
and loudness of a commercial release:

1. Click **🔬 Analyze Mix** in the AI Panel.
2. When the file picker opens, select your reference track.
3. The AI attempts to match the tonal balance, stereo width, and dynamics.

---

## What the ONNX Pipeline Does

| Stage | Description |
|-------|-------------|
| Spectral analysis | Measures frequency balance, dynamics, stereo field |
| EQ matching | Applies shelf/peak EQ to match target curve |
| Dynamic control | Sets compression ratio, attack, release per band |
| Reverb estimation | Suggests room size/send level |
| Loudness | Integrated loudness normalization + true-peak limiting |
