"""
model_check.py — First-run model download helper.

Run standalone before starting the server:
    python model_check.py

Or imported by server.py on startup to auto-download required models.

Uses huggingface_hub for reliable incremental downloads with resume support.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger
from tqdm import tqdm

from config import MODEL_DIR

# ── Model manifest ────────────────────────────────────────────────────────────
# Each entry: (name, hf_repo_id, required_files, required, min_size_mb)
MODEL_MANIFEST = [
    {
        "name":     "demucs",
        "repo":     "facebook/demucs",
        "files":    [],          # demucs manages its own cache via torch.hub
        "required": True,
        "notes":    "Installed via pip (demucs>=4.0.1) — no manual download needed.",
    },
    # Bark/DiffRhythm removed — ElevenLabs replaces local generation.
    {
        "name":     "mixer",
        "repo":     "wavy-labs/onnx-mixer-v1",
        "files":    ["mixer_v1.onnx"],
        "required": False,
        "notes":    "~200 MB. Optional — rule-based fallback active when not present.",
    },
]


def _model_cache_dir(name: str) -> Path:
    d = MODEL_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def uninstall_model(name: str) -> bool:
    """Delete the local model directory for the given model name.

    Returns True if the directory existed and was deleted, False if not found.
    """
    import shutil

    # Build path without creating it (avoid mkdir side-effect)
    path = MODEL_DIR / name
    if path.exists():
        shutil.rmtree(path)
        logger.info(f"Uninstalled model: {name} ({path})")
        return True
    logger.warning(f"uninstall_model: {name} not found at {path}")
    return False


def get_model_disk_size(name: str) -> float:
    """Return total size of MODEL_DIR/<name> in gigabytes (0.0 if not present)."""
    path = MODEL_DIR / name
    if not path.exists():
        return 0.0
    total_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total_bytes / (1024 ** 3), 3)


def _is_downloaded(name: str, files: list[str]) -> bool:
    if not files:
        return True   # managed externally (demucs/bark)
    cache = _model_cache_dir(name)
    return all((cache / f).exists() for f in files)


def download_model(name: str, repo: str, files: list[str],
                   snapshot: bool = False) -> bool:
    """Download files from HuggingFace Hub into MODEL_DIR/<name>/.

    When snapshot=True the entire repository is cloned via snapshot_download
    (needed for models that store weights in subdirectories, e.g. ACE-Step).
    """
    if not files:
        logger.info(f"  {name}: managed by library — skipping HF download.")
        return True

    try:
        if snapshot:
            from huggingface_hub import snapshot_download  # type: ignore
        else:
            from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        logger.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        return False

    cache = _model_cache_dir(name)

    if snapshot:
        try:
            logger.info(f"  Snapshot-downloading {repo} → {cache} …")
            snapshot_download(repo_id=repo, local_dir=str(cache))
            logger.info(f"  ✓ {name} snapshot complete.")
            return True
        except Exception as exc:
            logger.error(f"  ✗ Snapshot download failed for {name}: {exc}")
            return False

    success = True
    for fname in files:
        dest = cache / fname
        if dest.exists():
            logger.info(f"  {name}/{fname}: already present.")
            continue
        try:
            logger.info(f"  Downloading {repo}/{fname} …")
            path = hf_hub_download(
                repo_id=repo,
                filename=fname,
                local_dir=str(cache),
            )
            logger.info(f"  ✓ {fname} → {path}")
        except Exception as exc:
            logger.error(f"  ✗ Failed to download {fname}: {exc}")
            success = False

    return success


def check_and_download(
    required_only: bool = True,
    names: Optional[list[str]] = None,
) -> dict[str, bool]:
    """
    Check and download models.

    Args:
        required_only: Only download models marked required=True.
        names:         If given, only process these model names.

    Returns:
        dict mapping model name → success bool.
    """
    results: dict[str, bool] = {}

    for model in MODEL_MANIFEST:
        name = model["name"]

        if names and name not in names:
            continue
        if required_only and not model["required"]:
            logger.debug(f"Skipping optional model: {name}")
            continue

        if _is_downloaded(name, model["files"]):
            logger.info(f"✓ {name}: already downloaded.")
            results[name] = True
            continue

        logger.info(f"↓ {name} ({model['notes']})")
        results[name] = download_model(
            name, model["repo"], model["files"],
            snapshot=model.get("snapshot", False),
        )

    return results


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | {message}")

    logger.info("Wavy Labs — model check")
    logger.info(f"Model directory: {MODEL_DIR}")

    results = check_and_download(required_only="--all" not in sys.argv)

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.error(f"Failed to download: {failed}")
        sys.exit(1)

    logger.info("All required models ready.")


if __name__ == "__main__":
    main()
