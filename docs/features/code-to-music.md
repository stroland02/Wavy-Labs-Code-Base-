# Code to Music

Turn code, data, and structured notation into music directly from an embedded
code editor.

!!! note "Studio feature"
    Code to Music requires a **Studio** subscription ($24.99/mo).

## Opening the Editor

Go to **View → Code to Music** or press **Ctrl+Shift+C**.

A Monaco-based code editor opens as an MDI sub-window.

---

## Input Modes

### 1. Wavy DSL (default)

A simple domain-specific language for describing music programmatically:

```python
# Set global parameters
bpm(140)
key("C minor")

# Define patterns
track("drums").pattern([1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,0,0], bpm=140)
track("bass").melody([C3, G3, Bb3, G3], duration="quarter", velocity=90)
track("synth").generate("ambient pad, slow attack", key="C minor", duration=4)

# Repeat sections
section("verse", bars=8)
section("chorus", bars=4, repeat=2)
```

### 2. Python Data Sonification

Map any CSV or list data to musical parameters:

```python
import csv

# Load your data
data = [row for row in csv.reader(open("sales.csv"))]
values = [float(row[1]) for row in data[1:]]  # second column

# Map to pitch and velocity
track("data").sonify(
    values,
    pitch_range=(C3, C5),
    velocity_range=(40, 120),
    note_duration="eighth",
    bpm=120
)
```

### 3. MIDI Output Mode

Generate MIDI instead of audio — useful for feeding into virtual instruments:

```python
track("melody").midi([
    note(C4, duration="quarter", velocity=80),
    note(E4, duration="quarter", velocity=75),
    note(G4, duration="half",    velocity=90),
])
```

---

## Running Code

Click **▶ Run** or press **Ctrl+Enter**.

The backend:
1. Parses the DSL using the Lark grammar
2. Converts each track to MIDI + audio
3. Sends clips back to the LMMS Song Editor via the IPC layer

Errors are shown inline in the editor with line-number highlighting.

---

## Built-in Functions Reference

| Function | Description |
|----------|-------------|
| `bpm(value)` | Set global tempo |
| `key(name)` | Set global key (e.g. `"G major"`) |
| `track(name)` | Create/select a track |
| `.pattern(list)` | Euclidean/step pattern (1 = hit, 0 = rest) |
| `.melody(notes)` | List of pitches (use note names: `C4`, `Bb3`, etc.) |
| `.generate(prompt)` | AI text-to-audio for this track |
| `.sonify(data)` | Map numeric data to notes |
| `.midi(notes)` | Raw MIDI note list |
| `section(name, bars)` | Group tracks into an arrangement section |
| `note(pitch, ...)` | Create a single MIDI note |
