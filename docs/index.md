# Wavy Labs

> **The DAW that listens to you.**

Wavy Labs is an AI-powered Digital Audio Workstation built on top of LMMS.
It layers AI music generation, stem splitting, vocal synthesis, and intelligent
mixing tools directly into a full-featured desktop DAW — with all AI running
**100% locally**. No data leaves your machine. No ongoing API costs.

---

## Key Features

| Feature | Description | Tier |
|---------|-------------|------|
| **AI Music Generation** | Text prompt → full audio track in ~20 s | Free (5/day) |
| **Stem Splitting** | Separate a track into vocals, drums, bass, and more | Free (2-stem) |
| **Vocal Generation** | Lyrics text → sung/spoken vocal track | Pro |
| **AI Mix & Master** | Automatic EQ, compression, and loudness normalization | Pro |
| **Prompt Commands** | Natural language DAW control ("add a 4-bar drum loop") | Studio |
| **Code to Music** | Python/JSON data → music via a live code editor | Studio |

---

## Why Wavy Labs?

- **Private by design** — all AI models run locally via ONNX Runtime
- **Full traditional DAW** — built on LMMS: piano roll, automation, mixer, plugins
- **Open-source core** — GPL-2.0; the AI backend is a separate process
- **Works without a GPU** — CPU fallback mode for every feature
- **Tiered pricing** — free tier is genuinely useful, not crippled

---

## Quick Start

```bash
# 1. Download and run the installer from the releases page.
# 2. On first launch, Wavy Labs downloads the AI models (~8 GB total).
# 3. Open the AI panel (toolbar ⚡ button or Ctrl+Shift+A).
# 4. Type a music description and click Generate.
```

See [Installation](getting-started/installation.md) for detailed setup steps.

---

## Architecture Overview

```
┌──────────────────────────────────────────┐
│  Wavy Labs UI (C++/Qt6)                  │
│  ┌────────────┐  ┌────────────────────┐  │
│  │ LMMS Core  │  │  AI Panels         │  │
│  │ (Song Ed.) │  │  (MDI SubWindows)  │  │
│  └────────────┘  └────────────────────┘  │
│            │  ZeroMQ JSON-RPC             │
└────────────┼─────────────────────────────┘
             │ tcp://127.0.0.1:5555
┌────────────┼─────────────────────────────┐
│  AI Backend (Python)                     │
│  ┌─────────┐ ┌────────┐ ┌─────────────┐ │
│  │ACE-Step │ │Demucs  │ │Mistral 7B   │ │
│  │DiffRhythm│ │v4      │ │ONNX mixer   │ │
│  └─────────┘ └────────┘ └─────────────┘ │
└──────────────────────────────────────────┘
```

[Get Started →](getting-started/installation.md){ .md-button .md-button--primary }
[View on GitHub →](https://github.com/wavy-labs/wavy-labs){ .md-button }
