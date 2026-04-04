# Stem Splitting

Separate any audio file into individual instrument stems using Demucs v4.

## How to Use

### From the Song Editor (right-click)

1. Right-click any audio clip in the Song Editor.
2. Go to **Wavy Labs AI → Split Stems…** (2-stem, free) or
   **Split Stems (6-stem, Pro)…**
3. Processing runs in the background — a status message appears in the bottom bar.
4. When complete, each stem is inserted as a new SampleTrack, color-coded and
   named automatically.

### From the AI Panel

1. Open the AI Panel (**Ctrl+Shift+A**) and go to the **Mix / Master** tab.
2. Click **🔬 Analyze Mix** — this opens a file picker.
3. Select the audio file to split.

---

## Stem Sets

| Mode | Stems | Tier |
|------|-------|------|
| 2-stem | vocals, accompaniment | Free |
| 4-stem | vocals, drums, bass, other | Free |
| 6-stem | vocals, drums, bass, guitar, piano, other | Pro |

## Color Coding

Each stem is given a distinct track header color in the Song Editor:

| Stem | Color | Hex |
|------|-------|-----|
| Vocals | Red | `#ef5350` |
| Drums | Orange | `#ff9800` |
| Bass | Blue | `#42a5f5` |
| Guitar | Green | `#66bb6a` |
| Piano | Purple | `#ab47bc` |
| Other | Grey | `#90a4ae` |

---

## Model

**Demucs v4 — htdemucs_ft** (Meta AI, MIT license)

- 4 GB VRAM recommended; falls back to CPU (2–5× slower)
- Real-time or faster on a mid-range GPU

---

## Tips

- For best results, use lossless source audio (WAV/FLAC).
- The 6-stem model performs better on recordings with clearly separated instruments.
- After splitting, mute/solo individual stems to build a remix or isolate a part.
