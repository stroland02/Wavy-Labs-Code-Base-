# FAQ

## General

### Is Wavy Labs really free?

Yes — the full LMMS-based DAW is free forever with no limitations. The AI features
have a free tier (5 music generations per day, 2-stem split). Advanced AI features
(vocal gen, mastering, prompt commands, code to music) require a Pro or Studio subscription.

### Does the AI send my data to the internet?

No. All AI inference runs locally on your machine using ONNX Runtime. Your audio,
lyrics, and prompts never leave your computer.

### What happens when I'm offline?

The AI features work fully offline. The only online requirement is the initial model
download and license re-validation every 7 days. If you're offline at re-validation
time, a 7-day grace period keeps your tier active.

---

## Installation

### The Model Manager says "Download failed"

- Check your internet connection.
- Ensure you have at least 15 GB of free disk space.
- Try disabling your VPN or firewall temporarily.
- If on a corporate network, you may need to configure a proxy in Settings → Network.

### The app crashes on launch on Windows

Install the [Visual C++ Redistributable 2022](https://aka.ms/vs/17/release/vc_redist.x64.exe)
if not already present.

### How do I move my models to a different drive?

Go to **Settings → AI → Model Path**, change the directory, and click **Move Models**.
Wavy Labs will copy (not move) the files, then switch to the new location.

---

## AI Features

### Generation is very slow

- Enable GPU acceleration: check **Settings → AI → Inference Device**.
- If you have an NVIDIA GPU, ensure CUDA 12 is installed.
- On macOS with Apple Silicon, CoreML is enabled automatically.
- CPU mode is supported but significantly slower (~3–10× for music generation).

### The generated music doesn't match my prompt

- Be more specific: include tempo, key, mood, instrumentation details.
- Try different seeds using "Best of 3".
- Switch models (ACE-Step vs DiffRhythm) to see which suits your prompt style.

### Stem splitting quality is poor

- Use lossless source audio (WAV or FLAC) rather than compressed MP3.
- The 6-stem model (Pro) generally produces cleaner results than 2-stem.
- For heavily processed/mastered tracks, separation quality may be limited.

### Can I fine-tune the AI models on my own music?

Not in v1. Fine-tuning support is on the roadmap for a future Studio tier feature.

---

## Licensing

### I entered my license key but it shows "Invalid"

- Check for typos; keys are case-sensitive.
- Keys start with `PRO-` (Pro) or `STU-` (Studio).
- If you purchased via Stripe, check your email for the key (sometimes in spam).
- Contact support at support@wavylabs.io.

### Can I use one license on multiple machines?

Yes — each license allows activation on up to **2 machines simultaneously**.
Deactivate a machine via **Settings → License → Deactivate** before activating on a new one.

### What happens when my subscription expires?

Your account reverts to the Free tier automatically. Your project files and
previously generated audio are unaffected.

---

## Open Source

### Why is the core open source but AI gated by subscription?

The LMMS core is GPL-2.0, which requires distribution under the same license.
The AI backend runs as a separate process (no GPL contamination) and is how we
fund ongoing model research and hosting. We believe the free tier is genuinely
useful without a subscription.

### Can I build my own version with all features unlocked?

The source code is public. You can build from source and use the free tier
features without any subscription. The Pro/Studio feature gate is checked via
the `LicenseManager` class — you can remove it for personal use, but you may
not distribute a modified version that bypasses license checking under our
trademark.
