"""
Demucs v4 (htdemucs_ft) wrapper — stem splitting (MIT).
https://github.com/facebookresearch/demucs

Uses demucs.pretrained + demucs.apply directly.  Avoids demucs.audio and
demucs.separate because they import `lameenc` which has no wheel for
Python 3.14+.  Audio I/O uses soundfile + pedalboard (bundled codecs) to
avoid torchaudio/torchcodec's FFmpeg dependency on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from .base import BaseModel

# Stem configurations per stem-count selection
# htdemucs_ft = fine-tuned version; significantly better separation than base htdemucs
STEM_CONFIGS: Dict[int, Dict[str, str]] = {
    2: {"model": "htdemucs_ft", "stems": ["vocals", "drums", "bass", "other"]},  # vocals + sum rest
    4: {"model": "htdemucs_ft", "stems": ["vocals", "drums", "bass", "other"]},
    6: {"model": "htdemucs_6s", "stems": ["vocals", "drums", "bass", "piano", "guitar", "other"]},
}


class DemucsModel(BaseModel):
    MODEL_ID = "demucs"

    def _load(self) -> None:
        logger.info("Loading Demucs v4 …")
        try:
            import demucs.pretrained  # noqa: F401
            import demucs.apply       # noqa: F401
            import torch              # noqa: F401
            import soundfile          # noqa: F401
            self._loaded = True
            logger.info("Demucs v4 ready.")
        except ImportError as exc:
            logger.warning(f"demucs dependency missing: {exc}. "
                           "Run: pip install demucs julius einops openunmix torchaudio")
            self._loaded = False

    def split(
        self,
        audio_path: str,
        stems: int = 4,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        if not self._loaded:
            raise RuntimeError("Demucs model is not loaded.")

        if stems not in STEM_CONFIGS:
            raise ValueError(f"stems must be 2, 4, or 6; got {stems}")

        cfg = STEM_CONFIGS[stems]
        model_name = cfg["model"]
        stem_names: List[str] = cfg["stems"]

        # Normalise path — soundfile on Windows rejects backslashes
        audio_path = str(Path(audio_path).resolve())

        logger.info(f"Splitting {audio_path!r} into {stems} stems using {model_name} …")

        import torch
        import soundfile as sf
        import numpy as np
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        # MP3 encoding artifacts (ringing, spectral smearing) cause Demucs to
        # dump unclear energy into "other".  Convert to clean PCM WAV first.
        # Use pedalboard (bundled codecs) — avoids torchaudio/torchcodec FFmpeg dependency.
        if Path(audio_path).suffix.lower() in (".mp3", ".aac", ".ogg", ".m4a"):
            from pedalboard.io import AudioFile
            wav_tmp = Path(audio_path).with_suffix(".wav")
            with AudioFile(audio_path) as f:
                audio_data = f.read(f.frames)  # (channels, samples) float32
                sr_tmp = int(f.samplerate)
            sf.write(str(wav_tmp), audio_data.T, sr_tmp)
            logger.info(f"Converted {Path(audio_path).suffix} → WAV for Demucs: {wav_tmp.name}")
            audio_path = str(wav_tmp)

        out_dir = self._ensure_output_dir("stems")
        device = self._device if self._device else "cpu"

        # Set torch hub dir to a simple path to avoid Windows MAX_PATH issues
        import os
        hub_dir = str(Path(os.environ.get("USERPROFILE", Path.home())) / ".cache" / "demucs")
        torch.hub.set_dir(hub_dir)

        try:
            model = get_model(model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load demucs model '{model_name}'. "
                f"It may need to download first (~400 MB). Error: {exc}"
            ) from exc
        model.to(device)
        model.eval()

        # Load audio with soundfile (handles wav, mp3 via libsndfile)
        data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        # data shape: (samples, channels) → convert to (channels, samples) tensor
        wav = torch.from_numpy(data.T)

        # Resample if needed
        if sr != model.samplerate:
            import torchaudio
            wav = torchaudio.functional.resample(wav, sr, model.samplerate)

        # Ensure correct channel count
        if wav.shape[0] == 1 and model.audio_channels == 2:
            wav = wav.repeat(2, 1)
        elif wav.shape[0] > model.audio_channels:
            wav = wav[:model.audio_channels]

        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()
        wav = wav.to(device)

        with torch.no_grad():
            sources = apply_model(model, wav[None], device=device, shifts=1,
                                  split=True, overlap=0.25, progress=False)

        sources = sources * ref.std() + ref.mean()
        sources = sources[0].cpu()  # remove batch dim

        # Build a dict of all sources by name for easy access
        source_dict: Dict[str, Any] = {
            name: src for src, name in zip(sources, model.sources)
        }

        logger.info(f"model.sources: {model.sources}")
        logger.info(f"source_dict keys: {list(source_dict.keys())}")
        logger.info(f"stem_names filter: {stem_names}")
        logger.info(f"out_dir: {out_dir}")
        logger.info(f"sources shape: {sources.shape}, dtype: {sources.dtype}, device: {sources.device}")

        stem_paths: Dict[str, str] = {}

        if stems == 2:
            # 2-stem: vocals + everything else summed into "backing"
            vocals_src = source_dict.get("vocals")
            backing_srcs = [src for name, src in source_dict.items() if name != "vocals"]

            if vocals_src is not None:
                stem_path = out_dir / f"{Path(audio_path).stem}_vocals.wav"
                logger.info(f"  writing vocals → {stem_path}")
                sf.write(str(stem_path), vocals_src.numpy().T, model.samplerate)
                stem_paths["vocals"] = str(stem_path)
                logger.info(f"  → vocals: {stem_path.name}")

            if backing_srcs:
                backing = sum(backing_srcs)
                stem_path = out_dir / f"{Path(audio_path).stem}_backing.wav"
                logger.info(f"  writing backing → {stem_path}")
                sf.write(str(stem_path), backing.numpy().T, model.samplerate)
                stem_paths["backing"] = str(stem_path)
                logger.info(f"  → backing: {stem_path.name}")
        else:
            logger.info(f"4-stem loop: iterating {len(source_dict)} sources")
            for name, src in source_dict.items():
                in_filter = name in stem_names
                logger.info(f"  source '{name}': shape={src.shape}, in_filter={in_filter}")
                if not in_filter:
                    continue
                stem_path = out_dir / f"{Path(audio_path).stem}_{name}.wav"
                logger.info(f"  writing {name} → {stem_path}")
                try:
                    sf.write(str(stem_path), src.numpy().T, model.samplerate)
                    stem_paths[name] = str(stem_path)
                    logger.info(f"  → {name}: {stem_path.name} ✓")
                except Exception as write_exc:
                    logger.error(f"  sf.write FAILED for {name}: {write_exc}")
                    raise

        logger.info(f"stem_paths result ({len(stem_paths)}): {list(stem_paths.keys())}")
        return {"stems": stem_paths, "sample_rate": model.samplerate}
