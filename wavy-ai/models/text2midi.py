"""
Text2MIDI wrapper — amaai-lab/text2midi (AAAI 2025)

Downloads ~902 MB on first use (pytorch_model.bin + vocab_remi.pkl +
transformer_model.py from HuggingFace). Runs on GPU or CPU.

Optional install required:
    pip install miditok>=3.0.0 sentencepiece>=0.1.99

Architecture: FLAN-T5 text encoder → 18-layer autoregressive Transformer decoder
               with REMI tokenization. Output: .mid file.
"""

from __future__ import annotations

import importlib.util
import pickle
from pathlib import Path
from typing import Any

from loguru import logger

from models.base import BaseModel

_REPO_ID  = "amaai-lab/text2midi"
_T5_MODEL = "google/flan-t5-base"


class Text2MidiModel(BaseModel):
    MODEL_ID = _REPO_ID

    def _load(self) -> None:
        logger.info("[Text2MIDI] Loading model …")
        try:
            import torch
            import torch.nn as nn
            from transformers import T5Tokenizer
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            logger.error(f"[Text2MIDI] Missing core dependency: {exc}")
            raise

        try:
            import miditok  # noqa: F401
        except ImportError:
            raise ImportError(
                "[Text2MIDI] miditok not installed. "
                "Run: pip install miditok>=3.0.0 sentencepiece>=0.1.99"
            )

        try:
            # ── Download artifacts from HuggingFace ───────────────────────────
            logger.info("[Text2MIDI] Downloading weights …")
            model_path = hf_hub_download(repo_id=_REPO_ID, filename="pytorch_model.bin")
            vocab_path = hf_hub_download(repo_id=_REPO_ID, filename="vocab_remi.pkl")
            arch_path  = hf_hub_download(repo_id=_REPO_ID, filename="transformer_model.py")

            # ── Dynamically load Transformer class from repo file ─────────────
            spec   = importlib.util.spec_from_file_location("_t2m_transformer", arch_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            Transformer = module.Transformer

            # ── REMI tokenizer (pickled miditok object) ───────────────────────
            with open(vocab_path, "rb") as f:
                self._r_tokenizer = pickle.load(f)

            # miditok 3.x compat: the pickle was saved with an older miditok that
            # lacked ~19 fields added in 3.0.x. Apply all missing field defaults
            # from TokenizerConfig.__init__ so decode() doesn't AttributeError.
            import inspect
            from miditok.classes import TokenizerConfig as _TC
            cfg = self._r_tokenizer.config
            sig = inspect.signature(_TC.__init__)
            for name, param in sig.parameters.items():
                if name == "self":
                    continue
                if not hasattr(cfg, name) and param.default is not inspect.Parameter.empty:
                    setattr(cfg, name, param.default)
            # num_velocities>0 means velocities are used (old bool → new int migration)
            if not hasattr(cfg, "use_velocities"):
                cfg.use_velocities = getattr(cfg, "num_velocities", 0) > 0

            vocab_size = len(self._r_tokenizer)

            # ── Device ────────────────────────────────────────────────────────
            device = self._device
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
            self._device_str = device

            # ── Model: (vocab, d_model, heads, ff_dim, layers, max_seq, bool, num_heads, device)
            self._model = Transformer(
                vocab_size, 768, 8, 2048, 18, 1024, False, 8, device=device
            )
            self._model.load_state_dict(
                torch.load(model_path, map_location=device, weights_only=True)
            )
            self._model.eval()

            # ── T5 text tokenizer ─────────────────────────────────────────────
            self._t5_tokenizer = T5Tokenizer.from_pretrained(_T5_MODEL)

            self._nn    = nn
            self._torch = torch
            self._loaded = True
            logger.info(f"[Text2MIDI] Loaded on {device}.")

        except Exception as exc:
            logger.error(f"[Text2MIDI] Load failed: {exc}")
            raise

    def generate(self, prompt: str, max_len: int = 2000, temperature: float = 1.0) -> str:
        """Generate a MIDI file from *prompt*. Returns path to written .mid file."""
        if not self._loaded:
            raise RuntimeError("Text2MIDI model not loaded.")

        logger.info(f"[Text2MIDI] Generating for: {prompt!r}")

        inputs = self._t5_tokenizer(
            prompt, return_tensors="pt", padding=True, truncation=True
        )
        input_ids = self._nn.utils.rnn.pad_sequence(
            inputs.input_ids, batch_first=True, padding_value=0
        ).to(self._device_str)
        attention_mask = self._nn.utils.rnn.pad_sequence(
            inputs.attention_mask, batch_first=True, padding_value=0
        ).to(self._device_str)

        with self._torch.no_grad():
            output = self._model.generate(
                input_ids, attention_mask,
                max_len=max_len,
                temperature=temperature,
            )

        output_list    = output[0].tolist()
        generated_midi = self._r_tokenizer.decode(output_list)

        out_path = self._unique_path("text2midi", ".mid")
        generated_midi.dump_midi(str(out_path))
        logger.info(f"[Text2MIDI] Written → {out_path}")
        return str(out_path)

    def unload(self) -> None:
        if self._loaded:
            try:
                self._model.cpu()
                del self._model
                del self._r_tokenizer
                del self._t5_tokenizer
                self._torch.cuda.empty_cache()
            except Exception:
                pass
            self._loaded = False
            logger.info("[Text2MIDI] Unloaded.")
