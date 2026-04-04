# Wavy Labs — Free, Open-Source AI-Powered DAW

> **"The DAW that listens to you."**

Wavy Labs is a **free, open-source** AI-powered Digital Audio Workstation forked from
[LMMS](https://lmms.io) (GPL-2.0). It layers powerful AI features on top of a
full-featured desktop DAW — powered by ElevenLabs, Anthropic Claude, and Groq,
with local models for offline use. **You bring your own API keys.**

[![License: GPL-2.0](https://img.shields.io/badge/License-GPL--2.0-blue.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/stroland02/Wavy-Labs-Code-Base-)](https://github.com/stroland02/Wavy-Labs-Code-Base-/releases)

---

## Download

**[Download for Windows (v0.15.0)](https://github.com/stroland02/Wavy-Labs-Code-Base-/releases/latest)**

System requirements: Windows 10/11 (64-bit), 8 GB RAM, 4 GB disk space.
Optional: NVIDIA GPU for GPU-accelerated stem splitting and local models.

---

## Features

- **Full DAW** — complete LMMS fork with MIDI piano roll, Song editor, pattern editor, 30+ synth plugins
- **AI Music Generation** — ElevenLabs cloud or local DiffRhythm/ACE-Step models
- **Stem Splitting** — Demucs v4 (2/4/6-stem) on any audio
- **TTS / SFX / Voice Clone** — ElevenLabs voice tools
- **Vocal Processing** — voice isolation, transcription, forced alignment, dubbing
- **Prompt Commands** — natural-language DAW control via Claude / Groq
- **AI Mix & Master** — automatic mix analysis and mastering
- **Instrument Library** — 570+ searchable presets, samples, GM patches, VST3 references
- **Genre Modes** — 8 genre presets with automatic instrument + drum kit configuration
- **Code to Music** — generate audio/MIDI from a Python DSL

All features are included — no subscription required. Add your own API keys to enable cloud AI.

---

## Quick Start

### 1. Download & Install

Download the installer from [Releases](https://github.com/stroland02/Wavy-Labs-Code-Base-/releases/latest) and run it.
The installer bundles an embedded Python runtime and installs all dependencies automatically.

### 2. Configure API Keys

On first launch, the setup wizard will prompt for API keys. You can also add them later via **Edit → Settings**:

| Key | Purpose | Get it at |
|-----|---------|-----------|
| **Anthropic** | Claude — prompt commands, chat | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| **Groq** | llama-3.3-70b — free LLM fallback | [console.groq.com/keys](https://console.groq.com/keys) |
| **ElevenLabs** | Music, TTS, SFX, voice tools | [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys) |
| **Freesound** | Browse/download sound effects | [freesound.org/apiv2/apply](https://freesound.org/apiv2/apply) |

Keys are stored encrypted on your machine (Windows DPAPI) and never sent to Wavy Labs.

---

## Build from Source

### Prerequisites

- Qt 6.9.x (with Quick, QuickControls2, Svg, Sql, Network)
- MSVC 2022 (Windows) or GCC 13+ (Linux)
- CMake 3.22+, Ninja
- Python 3.10+ with pip
- ZeroMQ 4.x + cppzmq

### Windows (MSVC)

```bat
git clone https://github.com/stroland02/Wavy-Labs-Code-Base-.git WL
cd WL
git submodule update --init --recursive

# Configure (edit paths in do_configure.bat first)
do_configure.bat

# Build
do_build_lmms.bat

# Run
build\lmms.exe
```

### Python backend

```bash
cd wavy-ai
pip install -r requirements.txt

# Optional: GPU-accelerated torch (NVIDIA RTX)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126

python server.py
```

The C++ app will launch the Python backend automatically. For development,
start it manually first — the app detects an existing backend and skips auto-launch.

---

## Repository Structure

```
WL/
├── lmms-core/          # Git submodule: forked LMMS (Qt6, branch wavy-patches)
├── wavy-ui/            # C++/Qt6 panels (static lib wavy_ui)
│   ├── AIPanel/        # Legacy AI generation panel
│   ├── QML/            # AIBackend + QML bindings (MainPanel.qml)
│   ├── Shell/          # WavyShell — top-level window replacing LMMS MDI
│   ├── Transport/      # Transport bar + genre config popup
│   ├── LicenseGate/    # LicenseManager (tier=Studio always), ApiKeySettings
│   └── IPC/            # ZeroMQ JSON-RPC client (AIClient) + BackendLauncher
├── wavy-ai/            # Python AI backend (ZeroMQ JSON-RPC server)
│   ├── server.py       # Entry point
│   ├── rpc_handlers.py # Method → handler registry
│   ├── rpc/            # Domain handlers (core, audio, midi, library, fx, …)
│   ├── cloud/          # Cloud provider wrappers (ElevenLabs, Anthropic, Groq)
│   ├── models/         # Local model wrappers (Demucs, DiffRhythm, ACE-Step)
│   └── data/           # instrument_catalog.json, soundfonts
├── wavy-installer/     # NSIS Windows installer
├── wavy-license-server/# Optional: open-source license server (FastAPI)
├── data/               # QML, QSS themes, icons, resources.qrc
└── src/main.cpp        # Wavy entry point (bypasses lmms-core main.cpp)
```

---

## IPC Protocol

```
C++ (AIClient)  ──JSON-RPC over ZeroMQ──►  Python (server.py)
                   tcp://127.0.0.1:5555
```

All methods use: `{"id": N, "method": "method_name", "params": {...}}`

Key RPC methods: `health`, `generate_music`, `split_stems`, `prompt_command`,
`compose`, `elevenlabs_tts`, `elevenlabs_sfx`, `elevenlabs_voice_clone`,
`update_api_keys`, `list_instruments`, `browse_dataset`, and 40+ more.

---

## Contributing

1. Fork the repo and create a branch
2. Make your changes (follow existing code patterns)
3. Test: `do_build_lmms.bat` → `build\lmms.exe`
4. Open a pull request

Bug reports and feature requests: [GitHub Issues](https://github.com/stroland02/Wavy-Labs-Code-Base-/issues)

---

## License

- **DAW core (lmms-core/):** GPL-2.0 (same as LMMS upstream)
- **wavy-ui/, wavy-ai/, wavy-license-server/:** GPL-2.0
- **AI model weights:** see individual model licenses (Demucs: MIT, DiffRhythm: Apache 2.0, etc.)
- **Instrument samples:** see `wavy-ai/data/instrument_catalog.json` for per-entry licenses
