# Installation

## Windows

1. Download `WavyLabs-Setup-x64.exe` from the [Releases page](https://github.com/wavy-labs/wavy-labs/releases).
2. Run the installer. It installs the application and registers the file associations (`.mmp`, `.mmpz`).
3. On first launch, the **Model Manager** opens automatically and downloads the required AI models (~8 GB).
4. Once the download is complete, you're ready to make music.

!!! tip "CUDA support"
    If you have an NVIDIA GPU, install [CUDA 12](https://developer.nvidia.com/cuda-downloads) before
    running Wavy Labs for maximum AI performance.

## macOS

1. Download `WavyLabs-macOS.dmg` from the [Releases page](https://github.com/wavy-labs/wavy-labs/releases).
2. Open the DMG and drag Wavy Labs to your Applications folder.
3. Right-click → Open on first launch to bypass Gatekeeper.
4. The Model Manager will download models on first run.

!!! note "Apple Silicon"
    The macOS build is a universal binary (arm64 + x86-64). CoreML acceleration is
    enabled automatically on Apple Silicon — no additional setup required.

## Linux (AppImage)

```bash
# Download
wget https://github.com/wavy-labs/wavy-labs/releases/latest/download/WavyLabs-x86_64.AppImage

# Make executable
chmod +x WavyLabs-x86_64.AppImage

# Run
./WavyLabs-x86_64.AppImage
```

For NVIDIA GPU support on Linux, ensure `libcuda.so` is on your `LD_LIBRARY_PATH`.

## Building from Source

See [Building from Source](../dev/building.md) for the full developer build guide.

---

## AI Model Download

Models are downloaded from [Hugging Face Hub](https://huggingface.co) on first launch.
They are stored in:

| OS | Default path |
|----|-------------|
| Windows | `%APPDATA%\WavyLabs\models\` |
| macOS | `~/Library/Application Support/WavyLabs/models/` |
| Linux | `~/.local/share/WavyLabs/models/` |

You can change the model directory in **Settings → AI → Model Path**.

### Model sizes

| Model | Size on disk |
|-------|-------------|
| ACE-Step 1.5 | ~3.5 GB |
| DiffRhythm 2 | ~4.2 GB |
| Demucs v4 htdemucs_ft | ~0.8 GB |
| Bark | ~2.0 GB |
| ONNX mixing pipeline | ~0.3 GB |
| Mistral 7B Q4_K_M (GGUF) | ~4.1 GB |

!!! info "Selective download"
    You only need to download models for features you plan to use.
    The Model Manager lets you choose which models to install.
