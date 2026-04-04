"""Instrument catalog — search, browse, and manage instrument entries."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import httpx
from loguru import logger

# ── Catalog location ─────────────────────────────────────────────────────────
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "instrument_catalog.json"
_SF2_DIR = Path(__file__).resolve().parents[2] / "data" / "soundfonts"

# ── Downloadable packs ───────────────────────────────────────────────────────
INSTRUMENT_PACKS: dict[str, dict] = {
    "Salamander Piano": {
        "url": "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPianoV3+20161209_48khz24bit.sf2",
        "filename": "SalamanderGrandPiano.sf2",
        "size_mb": 15,
        "license": "CC-BY-3.0",
        "description": "Concert grand piano -- 16 velocity layers, Public Domain samples",
        "category": "piano",
    },
    "Hydrogen GMkit": {
        "url": "https://github.com/hydrogen-music/hydrogen/releases/download/1.2.3/GMkit.h2drumkit",
        "filename": "GMkit.h2drumkit",
        "size_mb": 15,
        "license": "GPL-2.0",
        "description": "Full GM drum kit -- multi-velocity acoustic drums",
        "category": "drums",
    },
}

# ── Catalog cache ────────────────────────────────────────────────────────────
_catalog_cache: list[dict] | None = None


def load_catalog() -> list[dict]:
    """Load the instrument catalog, enriching with installed status."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    if not _CATALOG_PATH.exists():
        logger.warning(f"[instrument_catalog] catalog not found at {_CATALOG_PATH}")
        return []

    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    # Enrich with installed status
    sf2_dir = _SF2_DIR
    for entry in entries:
        if entry["source"] == "external":
            pack_name = entry.get("pack", "")
            pack_info = INSTRUMENT_PACKS.get(pack_name, {})
            if pack_info:
                filepath = sf2_dir / pack_info.get("filename", "")
                entry["installed"] = filepath.is_file()
            else:
                entry["installed"] = False
        elif entry["source"] == "gm_soundfont":
            # Installed if any GM soundfont exists
            entry["installed"] = any(
                (sf2_dir / fn).is_file()
                for fn in ("GeneralUser_GS.sf2", "FluidR3_GM.sf2", "MuseScore_General.sf2")
            ) if sf2_dir.exists() else False
        elif entry["source"] == "vst3_reference":
            entry["installed"] = False  # We can't detect VST3 installs easily
        else:
            entry["installed"] = True  # Built-in presets/samples are always available

    _catalog_cache = entries
    logger.info(f"[instrument_catalog] loaded {len(entries)} entries")
    return entries


def invalidate_cache():
    """Clear the catalog cache so next load_catalog() re-reads from disk."""
    global _catalog_cache
    _catalog_cache = None


def search_instruments(
    query: str = "",
    category: str = "",
    source: str = "",
    tags: list[str] | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Search instruments with optional filters.

    Returns: {items: [...], total: int, has_more: bool}
    """
    catalog = load_catalog()
    results = catalog

    # Filter by query (name + description)
    if query:
        ql = query.lower()
        results = [
            e for e in results
            if ql in e["name"].lower() or ql in (e.get("description") or "").lower()
        ]

    # Filter by category
    if category:
        results = [e for e in results if e["category"] == category]

    # Filter by source
    if source:
        results = [e for e in results if e["source"] == source]

    # Filter by tags
    if tags:
        tag_set = set(t.lower() for t in tags)
        results = [
            e for e in results
            if tag_set.intersection(t.lower() for t in e.get("tags", []))
        ]

    total = len(results)
    page = results[offset:offset + limit]
    return {
        "items": page,
        "total": total,
        "has_more": (offset + limit) < total,
    }


def get_instrument_details(instrument_id: str) -> dict | None:
    """Get full details for a specific instrument by ID."""
    catalog = load_catalog()
    for entry in catalog:
        if entry["id"] == instrument_id:
            return entry
    return None


def download_instrument_pack(
    pack_name: str,
    progress_cb: Callable[[float], None] | None = None,
) -> str:
    """Download an instrument pack. Returns the local file path."""
    if pack_name not in INSTRUMENT_PACKS:
        raise ValueError(
            f"Unknown pack: {pack_name!r}. Available: {list(INSTRUMENT_PACKS)}"
        )

    info = INSTRUMENT_PACKS[pack_name]
    dest_dir = _SF2_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / info["filename"]

    # Already downloaded
    if dest.is_file() and dest.stat().st_size > 100_000:
        logger.info(f"[instrument_pack] {pack_name} already installed at {dest}")
        return str(dest)

    url = info["url"]
    logger.info(f"[instrument_pack] downloading {pack_name} from {url}")

    tmp = tempfile.NamedTemporaryFile(
        dir=str(dest_dir), suffix=".part", delete=False
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

        shutil.move(str(tmp_path), str(dest))
        invalidate_cache()
        logger.info(
            f"[instrument_pack] {pack_name} saved to {dest} "
            f"({dest.stat().st_size / 1e6:.1f} MB)"
        )
        return str(dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def list_packs() -> list[dict]:
    """Return available instrument packs with install status."""
    dest_dir = _SF2_DIR
    result = []
    for name, info in INSTRUMENT_PACKS.items():
        filepath = dest_dir / info["filename"]
        result.append({
            "name": name,
            "filename": info["filename"],
            "size_mb": info["size_mb"],
            "license": info["license"],
            "description": info["description"],
            "category": info["category"],
            "installed": filepath.is_file(),
            "path": str(filepath) if filepath.is_file() else "",
        })
    return result
