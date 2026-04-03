#!/usr/bin/env python3
"""
download_models.py — pre-download all Wavy Labs AI model weights.

Run this script ONCE before launching the app for the first time.
Models are stored in the WavyLabs user-data directory and the HuggingFace cache.

Approximate download sizes:
  Demucs htdemucs_ft      ~400 MB  (stem splitting — required)
  Mistral 7B Q4_K_M GGUF ~4.1 GB  (local prompt commands — optional)

Usage:
    python download_models.py [--skip-demucs] [--skip-mistral]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _model_dir() -> Path:
    try:
        import appdirs
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "appdirs", "-q"])
        import appdirs  # type: ignore
    p = Path(appdirs.user_data_dir("WavyLabs", "WavyLabs")) / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def download_demucs() -> None:
    """Trigger Demucs htdemucs_ft download (~400 MB). Demucs caches in torch hub."""
    print("\n[1/3] Demucs htdemucs_ft (~400 MB) ...")
    try:
        from demucs.pretrained import get_model  # type: ignore
        model = get_model("htdemucs_ft")
        print(f"  [OK] Demucs ready -{type(model).__name__}")
    except ImportError:
        print("  [FAIL] demucs not installed. Run: pip install demucs")
    except Exception as exc:
        print(f"  [FAIL] Demucs download failed: {exc}")


def download_mistral(model_dir: Path) -> None:
    """Download Mistral 7B Instruct Q4_K_M GGUF (~4.1 GB) into model_dir."""
    print(f"\n[2/3] Mistral 7B GGUF (~4.1 GB) → {model_dir}")

    # Check if already present
    existing = list(model_dir.glob("*.gguf"))
    if existing:
        print(f"  [OK] GGUF already present: {existing[0].name}")
        return

    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "huggingface_hub", "-q"])
        from huggingface_hub import hf_hub_download  # type: ignore

    REPO  = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
    FNAME = "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    print(f"  Downloading {FNAME} from {REPO} ...")
    try:
        path = hf_hub_download(
            repo_id=REPO,
            filename=FNAME,
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
        )
        print(f"  [OK] Saved to {path}")
    except Exception as exc:
        print(f"  [FAIL] Mistral download failed: {exc}")
        print(f"  Alternatively, download manually from https://huggingface.co/{REPO}")
        print(f"  and place the .gguf file in: {model_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Wavy Labs AI model weights.")
    parser.add_argument("--skip-demucs",  action="store_true", help="Skip Demucs (~400 MB)")
    parser.add_argument("--skip-mistral", action="store_true", help="Skip Mistral 7B GGUF (~4.1 GB)")
    args = parser.parse_args()

    model_dir = _model_dir()
    print(f"Wavy Labs model download — target directory: {model_dir}")
    print("=" * 60)

    if not args.skip_demucs:
        download_demucs()

    if not args.skip_mistral:
        download_mistral(model_dir)

    print("\n" + "=" * 60)
    print("Done. Launch the AI backend with: python server.py")


if __name__ == "__main__":
    main()
