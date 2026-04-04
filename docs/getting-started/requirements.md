# System Requirements

## Minimum (CPU-only mode)

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10 64-bit / macOS 12 / Ubuntu 22.04 |
| **CPU** | x86-64 with SSE4.2 (2015 or newer) |
| **RAM** | 8 GB |
| **Disk** | 15 GB free (models + project files) |
| **GPU** | Not required (CPU fallback active) |

!!! warning "CPU-only performance"
    Music generation in CPU mode takes 3–10× longer than GPU mode.
    Stem splitting and mastering are more manageable (~2× real-time on a modern CPU).

## Recommended (GPU-accelerated)

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10/11 64-bit / macOS 13+ / Ubuntu 22.04+ |
| **CPU** | 8-core, 3 GHz+ |
| **RAM** | 16 GB |
| **VRAM** | 8 GB (NVIDIA RTX 3060+ / AMD RX 6700+) |
| **Disk** | 25 GB free |
| **GPU driver** | CUDA 12+ (NVIDIA) or ROCm 5.7+ (AMD Linux) |

## macOS (Apple Silicon)

Apple Silicon (M1/M2/M3) uses **CoreML** acceleration via ONNX Runtime.
Performance is excellent — comparable to a mid-range NVIDIA GPU.

| Chip | Effective VRAM |
|------|---------------|
| M1 / M2 (8 GB) | Sufficient for all features except simultaneous loading |
| M1 Pro / M2 Pro+ (16 GB+) | All features, all models simultaneously |

## Model VRAM Requirements

| Model | VRAM |
|-------|------|
| ACE-Step 1.5 (music gen) | 4 GB |
| DiffRhythm 2 (fast music gen) | 8 GB |
| Demucs v4 (stem split) | 4 GB |
| Bark (vocal gen) | 6 GB |
| ONNX mixing pipeline | 2 GB |
| Mistral 7B GGUF (prompt commands) | 8 GB |

Models are loaded on demand and unloaded when idle to stay within your VRAM budget.
