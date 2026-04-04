"""
Base class for all Wavy Labs AI model wrappers.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

import appdirs
from loguru import logger


class BaseModel(ABC):
    """Common functionality: model directory, device selection, basic lifecycle."""

    #: Override in subclasses with the HuggingFace repo ID or local folder name.
    MODEL_ID: str = ""

    def __init__(self) -> None:
        self._device = self._pick_device()
        self._model_dir = self._resolve_model_dir()
        self._loaded = False
        self._load()

    # ── Device ───────────────────────────────────────────────────────────────

    @staticmethod
    def _pick_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    # ── Model directory ───────────────────────────────────────────────────────

    def _resolve_model_dir(self) -> Path:
        base = Path(appdirs.user_data_dir("WavyLabs", "WavyLabs")) / "models"
        base.mkdir(parents=True, exist_ok=True)
        return base

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def _load(self) -> None:
        """Load model weights into memory. Called once on construction."""

    def unload(self) -> None:
        """Release GPU/CPU memory. Override in subclasses if needed."""
        self._loaded = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ensure_output_dir(self, subfolder: str = "generations") -> Path:
        out = Path(appdirs.user_data_dir("WavyLabs", "WavyLabs")) / subfolder
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _unique_path(self, stem: str, suffix: str, subfolder: str = "generations") -> Path:
        import uuid
        out_dir = self._ensure_output_dir(subfolder)
        return out_dir / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
