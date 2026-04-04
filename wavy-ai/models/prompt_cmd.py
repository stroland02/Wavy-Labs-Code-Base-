"""
Prompt Commands handler — Mistral 7B / Llama 3.1 8B via llama-cpp-python.
Parses natural-language DAW commands into structured JSON action lists.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from .base import BaseModel

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Wavy, an expert AI music production assistant built into Wavy Labs — a professional \
DAW based on LMMS. You are deeply knowledgeable about LMMS, music theory, sound design, \
beatmaking, mixing, and mastering. You are friendly, concise, and genuinely helpful.

You can have natural conversations AND control the DAW. Always respond with ONLY a JSON \
object — no markdown, no code fences — with exactly two fields:
  "actions"     : list of DAW action objects, or [] if no action is needed
  "explanation" : your conversational reply (friendly, expert, 1-3 sentences)

For greetings, questions, or advice: return actions=[] and a helpful reply.
For DAW commands: return the action(s) AND explain what you did.
You can mix both in one response — give advice and trigger an action at the same time.

LMMS EXPERTISE:
- Song Editor: arrange patterns/clips on the timeline; each track has segments at bar positions
- Beat+Bassline (BB) editor: step-sequencer for drums/percussion; 16 steps per bar
- Instrument tracks: MIDI instruments (ZynAddSubFX, TripleOscillator, SF2 Player, BitInvader)
- Sample tracks: for audio clips, loops, and recorded audio
- Automation tracks: automate any knob/parameter over time
- FX Mixer: 64 channels, each with an effects chain (EQ, compressor, reverb, delay, limiter)
- Piano Roll: edit MIDI notes, velocities, pitch bend, modulation
- Tempo: 20–300 BPM; time signatures: 4/4 (common), 3/4, 6/8, 5/4 etc.
- Keys: C C# D D# E F F# G G# A A# B — major or minor (natural/harmonic/melodic)
- ZynAddSubFX: powerful synth with additive/subtractive/FM synthesis
- Common drum sounds: kick (C2), snare (D2), hi-hat closed (F#2), hi-hat open (A#2), clap (D#2)
- Layering: stack multiple instrument tracks for rich sounds
- Sidechaining: route kick to compressor sidechain on bass for pumping effect
- Humanisation: vary MIDI note velocities slightly (±10%) for natural feel

DAW action schema (include only what is needed):
  {"type": "add_track",          "track_type": "beat|sample|automation|bb", "name": str}
  {"type": "delete_track",       "track_index": int}
  {"type": "duplicate_track",    "track_index": int}
  {"type": "set_tempo",          "bpm": int}
  {"type": "set_volume",         "track_index": int, "volume": float}   // 0.0–1.0
  {"type": "set_pan",            "track_index": int, "pan": float}      // -1.0 left, 1.0 right
  {"type": "transpose_clip",     "track_index": int, "clip_index": int, "semitones": int}
  {"type": "add_pattern",        "track_index": int, "bar": int, "length_bars": int}
  {"type": "set_reverb",         "channel": int, "amount": float}       // 0.0–1.0
  {"type": "set_key",            "key": str, "scale": "major|minor"}
  {"type": "set_time_signature", "numerator": int, "denominator": int}
  {"type": "generate_music",     "prompt": str, "duration": float}
  {"type": "split_stems",        "track_index": int, "stems": int}

Return ONLY valid JSON. No extra text.\
"""


class PromptCmdModel(BaseModel):
    MODEL_ID = "mistral-7b-instruct"

    def _load(self) -> None:
        logger.info("Loading Mistral 7B for prompt commands …")
        try:
            from llama_cpp import Llama  # type: ignore
            model_path = self._find_gguf()
            if model_path is None:
                logger.warning(
                    "Mistral/Llama GGUF model not found in models directory. "
                    "Download from HuggingFace and place in the models folder."
                )
                self._llm = None
            else:
                n_gpu = -1 if self._device == "cuda" else 0
                self._llm = Llama(
                    model_path=str(model_path),
                    n_ctx=2048,
                    n_gpu_layers=n_gpu,
                    verbose=False,
                )
                self._loaded = True
                logger.info(f"LLM loaded from {model_path.name}")
        except ImportError:
            logger.warning("llama-cpp-python not installed. "
                           "Run: pip install llama-cpp-python")
            self._llm = None
        except Exception as exc:
            logger.error(f"LLM load failed: {exc}")
            self._llm = None

    def _find_gguf(self) -> Path | None:
        for candidate in self._model_dir.glob("*.gguf"):
            return candidate
        return None

    def parse_command(
        self,
        prompt: str,
        daw_context: Dict[str, Any] | None = None,
        history: List[Dict[str, str]] | None = None,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        if self._llm is None:
            raise RuntimeError("Prompt command LLM is not loaded. "
                               "Download a Mistral or Llama GGUF model.")

        context_str = ""
        if daw_context:
            context_str = f"\nCurrent DAW state:\n{json.dumps(daw_context, indent=2)}\n"

        user_msg = f"{context_str}{prompt}"

        logger.info(f"Prompt command: {prompt!r}")

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Inject prior conversation turns for context (cap at last 10 turns)
        for turn in (history or [])[-10:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_msg})

        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=512,
            temperature=0.2,
            stop=["</s>", "<|eot_id|>"],
        )

        raw = response["choices"][0]["message"]["content"].strip()
        logger.debug(f"LLM raw output: {raw}")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Attempt to extract JSON substring
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None

        if parsed is None:
            # Model returned prose instead of JSON — treat as a conversational reply
            logger.debug(f"LLM returned prose, wrapping as explanation: {raw[:80]}")
            return {"actions": [], "explanation": raw[:300]}

        actions: List[dict] = parsed.get("actions", [])
        explanation: str    = parsed.get("explanation", "")

        return {"actions": actions, "explanation": explanation}
