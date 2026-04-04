"""SoundFont manager — download and manage free GM SoundFont packs."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

import httpx
from loguru import logger

# ── Available SoundFont packs ────────────────────────────────────────────────

SOUNDFONTS: dict[str, dict] = {
    "GeneralUser GS": {
        "url": "https://storage.googleapis.com/google-code-archive-downloads/v2/code.google.com/generaluser-gs/GeneralUser_GS_v1.47.sf2",
        "filename": "GeneralUser_GS.sf2",
        "size_mb": 30,
        "license": "Free redistribution",
        "description": "Best quality/size ratio. Great for GM MIDI playback.",
    },
    "FluidR3 GM": {
        "url": "https://github.com/urish/cinto/raw/master/FluidR3%20GM2-2.sf2",
        "filename": "FluidR3_GM.sf2",
        "size_mb": 141,
        "license": "MIT",
        "description": "Full General MIDI 2 soundfont. High quality, large file.",
    },
    "MuseScore General": {
        "url": "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf2",
        "filename": "MuseScore_General.sf2",
        "size_mb": 36,
        "license": "MIT",
        "description": "MuseScore's default GM soundfont. Well-balanced.",
    },
}

# Default SF2 directory (inside LMMS data tree)
_DEFAULT_SF2_DIR = Path(__file__).resolve().parents[2] / "data" / "soundfonts"


def _sf2_dir() -> Path:
    """Return the soundfont storage directory, creating it if needed."""
    d = _DEFAULT_SF2_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_installed(sf_dir: str | Path | None = None) -> list[dict]:
    """Return list of available SF2 packs with install status.

    Returns: [{name, filename, size_mb, license, description, installed, path}]
    """
    d = Path(sf_dir) if sf_dir else _sf2_dir()
    result = []
    for name, info in SOUNDFONTS.items():
        filepath = d / info["filename"]
        result.append({
            "name": name,
            "filename": info["filename"],
            "size_mb": info["size_mb"],
            "license": info["license"],
            "description": info["description"],
            "installed": filepath.is_file(),
            "path": str(filepath) if filepath.is_file() else "",
        })
    return result


def download_soundfont(
    name: str,
    sf_dir: str | Path | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> str:
    """Download a soundfont by name. Returns the local file path.

    Raises ValueError if name is unknown, RuntimeError on download failure.
    """
    if name not in SOUNDFONTS:
        raise ValueError(f"Unknown soundfont: {name!r}. Available: {list(SOUNDFONTS)}")

    info = SOUNDFONTS[name]
    d = Path(sf_dir) if sf_dir else _sf2_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / info["filename"]

    # Already downloaded
    if dest.is_file() and dest.stat().st_size > 100_000:
        logger.info(f"[soundfont] {name} already installed at {dest}")
        return str(dest)

    url = info["url"]
    logger.info(f"[soundfont] downloading {name} from {url}")

    # Download to temp file, then move atomically
    tmp = tempfile.NamedTemporaryFile(
        dir=str(d), suffix=".sf2.part", delete=False
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(downloaded / total)

        # Move to final destination
        shutil.move(str(tmp_path), str(dest))
        logger.info(f"[soundfont] {name} saved to {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
        return str(dest)

    except Exception:
        # Clean up partial download
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
