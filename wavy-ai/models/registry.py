"""
ModelRegistry — lazy-loads AI models on demand, tracks VRAM budget.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List

from loguru import logger


# Map: model name → (module path, class name, VRAM GB estimate)
MODEL_CATALOG: Dict[str, tuple[str, str, float]] = {
    "demucs":        ("models.demucs",        "DemucsModel",       4.0),
    "mixer":         ("models.mixer",         "MixerModel",        0.0),
    "prompt_cmd":    ("models.prompt_cmd",    "PromptCmdModel",    8.0),
    "code_to_music": ("models.code_to_music", "CodeToMusicModel",  0.0),
    # ── Optional models (see requirements.txt for install instructions) ───────
    "musicgen":      ("models.musicgen",      "MusicGenModel",     2.0),
    "text2midi":     ("models.text2midi",     "Text2MidiModel",    2.0),
}


class ModelRegistry:
    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}

    def get(self, name: str) -> Any:
        if name not in self._instances:
            self.load(name)
        return self._instances[name]

    def load(self, name: str) -> None:
        if name in self._instances:
            return
        if name not in MODEL_CATALOG:
            raise ValueError(f"Unknown model: {name!r}. "
                             f"Available: {list(MODEL_CATALOG)}")
        module_path, class_name, vram = MODEL_CATALOG[name]
        logger.info(f"Loading {name} (~{vram} GB VRAM) …")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        self._instances[name] = cls()
        logger.info(f"{name} loaded.")

    def unload(self, name: str) -> None:
        if name in self._instances:
            inst = self._instances.pop(name)
            if hasattr(inst, "unload"):
                inst.unload()
            logger.info(f"{name} unloaded.")

    def loaded_model_names(self) -> List[str]:
        return list(self._instances)

    def model_status(self) -> List[dict]:
        return [
            {
                "name": name,
                "loaded": name in self._instances,
                "vram_gb": vram,
            }
            for name, (_, _, vram) in MODEL_CATALOG.items()
        ]
