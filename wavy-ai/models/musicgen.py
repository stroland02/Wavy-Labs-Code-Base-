"""
MusicGen wrapper — facebook/musicgen-small via HuggingFace transformers.
Auto-downloads ~300 MB on first use; requires ~2 GB VRAM.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

import config
from models.base import BaseModel


class MusicGenModel(BaseModel):
    MODEL_ID = "facebook/musicgen-small"

    def _load(self) -> None:
        logger.info(f"[MusicGen] Loading {self.MODEL_ID} …")
        try:
            from transformers import (
                AutoProcessor,
                MusicgenForConditionalGeneration,
                MusicgenConfig,
            )
            import torch

            # transformers 5.x bug: config_class was set to MusicgenDecoderConfig
            # instead of MusicgenConfig, causing from_pretrained to pass the wrong
            # sub-config to __init__.  Patch it back before loading.
            MusicgenForConditionalGeneration.config_class = MusicgenConfig

            self._processor = AutoProcessor.from_pretrained(self.MODEL_ID)
            self._model = MusicgenForConditionalGeneration.from_pretrained(
                self.MODEL_ID
            )
            device = self._device
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
            self._model = self._model.to(device)
            self._torch = torch
            self._loaded = True
            logger.info(f"[MusicGen] Loaded on {device}.")
        except Exception as exc:
            logger.error(f"[MusicGen] Load failed: {exc}")
            raise

    def generate(self, prompt: str, duration: float = 15.0) -> str:
        """Generate audio for *prompt* of roughly *duration* seconds.

        Returns the path to the written WAV file.
        """
        if not self._loaded:
            raise RuntimeError("MusicGen model not loaded.")

        import soundfile as sf

        # musicgen-small produces ~50 tokens/s; max_new_tokens controls length
        max_new_tokens = max(50, int(duration * 50))

        logger.info(f"[MusicGen] Generating {duration:.1f}s for prompt: {prompt!r}")

        inputs = self._processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        with self._torch.no_grad():
            audio_values = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                guidance_scale=3.0,
            )

        # audio_values shape: [batch, channels, samples]
        sr = self._model.config.audio_encoder.sampling_rate
        audio_np = audio_values[0, 0].cpu().numpy()

        out_path = self._unique_path("musicgen", ".wav")
        sf.write(str(out_path), audio_np, sr)
        logger.info(f"[MusicGen] Written → {out_path}")
        return str(out_path)

    def unload(self) -> None:
        if self._loaded:
            try:
                import torch
                self._model.cpu()
                del self._model
                del self._processor
                torch.cuda.empty_cache()
            except Exception:
                pass
            self._loaded = False
            logger.info("[MusicGen] Unloaded.")
