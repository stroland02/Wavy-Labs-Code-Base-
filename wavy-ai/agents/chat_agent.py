"""
chat_agent.py — Chat tab generation pipeline.

Always generates audio via MusicGen (facebook/musicgen-small).
LLM (Groq first, Anthropic fallback) is used only for intent parsing
(~50 tokens), NOT for note generation.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

import config


# ── Intent system prompt ──────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are a music intent parser. Given a user prompt, extract musical intent and
return ONLY a JSON object (no markdown, no extra text) with these fields:
{
  "key": "C",
  "scale": "minor",
  "bpm": 90,
  "genre": "lofi",
  "mood": "chill",
  "musicgen_prompt": "lofi piano chill hop 85bpm atmospheric"
}
Rules:
- musicgen_prompt: rich, descriptive text for MusicGen (10-20 words). Include genre, mood, instrumentation, tempo feel.
- bpm: integer 60-200. Default 90 if uncertain.
- key: single root note letter e.g. "C", "F#", "Bb". Default "C".
- scale: "major" or "minor". Default "minor".
- genre: one of lofi, trap, house, jazz, ambient, dnb, rnb, classical, pop, rock. Default "lofi".
- mood: short adjective e.g. "chill", "dark", "energetic", "melancholic".
"""


# ── Genre keyword detection ───────────────────────────────────────────────────

_GENRE_KEYWORDS: dict[str, list[str]] = {
    "lofi":            ["lofi", "lo-fi", "chill hop", "chillhop", "study"],
    "trap":            ["trap", "drill", "808"],
    "house":           ["house", "techno", "edm", "dance"],
    "jazz":            ["jazz", "swing", "bebop", "blues"],
    "ambient":         ["ambient", "atmosphere", "dark ambient", "drone"],
    "dnb":             ["dnb", "drum and bass", "jungle", "neurofunk"],
    "rnb":             ["r&b", "rnb", "soul", "neo soul"],
    "classical":       ["classical", "orchestral", "symphony"],
    "pop":             ["pop", "indie pop"],
    "rock":            ["rock", "metal", "punk"],
    # NCS / Electronic genres (v0.9.9)
    "ncs_future_bass": ["ncs future bass", "ncs futurebass", "future bass ncs",
                        "ncs anthem", "ncs drop"],
    "melodic_dubstep": ["melodic dubstep", "melodic dub", "halftime dubstep",
                        "emotive dubstep", "emotional dubstep"],
    "ncs_big_room":    ["ncs big room", "big room ncs", "festival edm",
                        "festival drop", "big room house ncs"],
    "future_bass":     ["future bass", "futurebass", "supersaw", "vocal chop edm"],
    "big_room":        ["big room", "festival house", "mainstage edm"],
}


# ── ChatAgent ─────────────────────────────────────────────────────────────────

class ChatAgent:
    """Stateless chat generation agent. Always generates audio via MusicGen."""

    # ── Intent parsing ────────────────────────────────────────────────────────

    def _detect_genre(self, prompt: str) -> str:
        """Return genre keyword found in prompt, or 'lofi'."""
        lower = prompt.lower()
        for genre, keywords in _GENRE_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return genre
        return "lofi"

    def _extract_bpm(self, prompt: str) -> int:
        """Try to extract an explicit BPM from prompt text."""
        m = re.search(r'\b(\d{2,3})\s*bpm\b', prompt, re.IGNORECASE)
        if m:
            return max(60, min(200, int(m.group(1))))
        # Genre-based defaults
        genre = self._detect_genre(prompt)
        _GENRE_BPM = {
            "trap": 140, "house": 128, "dnb": 174, "rnb": 90,
            "jazz": 100, "ambient": 75, "classical": 80,
            "lofi": 85, "pop": 110, "rock": 120,
        }
        return _GENRE_BPM.get(genre, 90)

    def _fallback_intent(self, prompt: str) -> dict:
        """Build intent dict from keywords when all LLMs are unavailable."""
        genre = self._detect_genre(prompt)
        bpm = self._extract_bpm(prompt)
        return {
            "key":            "C",
            "scale":          "minor",
            "bpm":            bpm,
            "genre":          genre,
            "mood":           "",
            "musicgen_prompt": f"{genre} {prompt[:60]}",
        }

    def _call_llm_intent(self, prompt: str) -> dict | None:
        """Try Groq (free, fast), then Anthropic. Returns parsed dict or None."""
        user_msg = f"Music prompt: {prompt}"

        # ── Groq ──────────────────────────────────────────────────────────────
        if config.GROQ_API_KEY:
            print(f"[ChatAgent] Trying Groq intent parse ...", flush=True)
            try:
                from groq import Groq
                client = Groq(api_key=config.GROQ_API_KEY)
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": _INTENT_SYSTEM},
                        {"role": "user",   "content": user_msg},
                    ],
                    max_tokens=128,
                    temperature=0.2,
                )
                raw = resp.choices[0].message.content.strip()
                print(f"[ChatAgent] Groq raw response: {raw!r}", flush=True)
                m = re.search(r'\{[\s\S]*\}', raw)
                if m:
                    parsed = json.loads(m.group())
                    print(f"[ChatAgent] Groq parsed intent: {parsed}", flush=True)
                    return parsed
                else:
                    print(f"[ChatAgent] Groq response had no JSON object", flush=True)
            except Exception as exc:
                print(f"[ChatAgent] Groq intent FAILED: {exc}", flush=True)
                logger.warning(f"[ChatAgent] Groq intent failed: {exc}")
        else:
            print(f"[ChatAgent] No GROQ_API_KEY — skipping Groq", flush=True)

        # ── Anthropic ─────────────────────────────────────────────────────────
        if config.ANTHROPIC_API_KEY:
            print(f"[ChatAgent] Trying Anthropic intent parse ...", flush=True)
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=128,
                    system=_INTENT_SYSTEM,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = resp.content[0].text.strip()
                print(f"[ChatAgent] Anthropic raw response: {raw!r}", flush=True)
                m = re.search(r'\{[\s\S]*\}', raw)
                if m:
                    parsed = json.loads(m.group())
                    print(f"[ChatAgent] Anthropic parsed intent: {parsed}", flush=True)
                    return parsed
            except Exception as exc:
                print(f"[ChatAgent] Anthropic intent FAILED: {exc}", flush=True)
                logger.warning(f"[ChatAgent] Anthropic intent failed: {exc}")
        else:
            print(f"[ChatAgent] No ANTHROPIC_API_KEY — skipping Anthropic", flush=True)

        print(f"[ChatAgent] All LLMs failed — using keyword fallback", flush=True)
        return None

    def _parse_intent(self, prompt: str) -> dict:
        """Parse prompt → intent dict."""
        llm_result = self._call_llm_intent(prompt)
        if llm_result is None:
            print(f"[ChatAgent] Using fallback intent", flush=True)
        intent = llm_result or self._fallback_intent(prompt)
        # Ensure required fields have sane defaults
        intent.setdefault("key",   "C")
        intent.setdefault("scale", "minor")
        intent.setdefault("bpm",   self._extract_bpm(prompt))
        intent.setdefault("genre", self._detect_genre(prompt))
        intent.setdefault("musicgen_prompt", f"{intent.get('genre','lofi')} {prompt[:60]}")
        print(f"[ChatAgent] Final intent: {intent}", flush=True)
        return intent

    # ── Audio generation ──────────────────────────────────────────────────────

    def _generate_audio(self, intent: dict, registry: Any) -> dict:
        """Generate audio using MusicGen."""
        mg_prompt = intent.get("musicgen_prompt", "")
        if not mg_prompt:
            genre = intent.get("genre", "lofi")
            mood  = intent.get("mood", "chill")
            key   = intent.get("key", "C")
            bpm   = intent.get("bpm", 90)
            mg_prompt = f"{genre} {mood} music in {key}, {bpm} BPM"

        try:
            model = registry.get("musicgen")
            wav_path = model.generate(mg_prompt, duration=15.0)
        except Exception as exc:
            logger.error(f"[ChatAgent] MusicGen failed: {exc}")
            return {"error": f"Audio generation failed: {exc}"}

        title = intent.get("genre", "AI") + " track"
        explanation = f"Generated ~15s audio: {mg_prompt}"
        return {
            "mode":        "audio",
            "audio_parts": [{"path": wav_path, "title": title}],
            "explanation": explanation,
        }

    # ── Main entry point ──────────────────────────────────────────────────────

    def generate(self, params: dict, registry: Any = None) -> dict:
        """
        params:
            prompt     : str  — user's chat message
            session_id : str  — optional session context
        returns:
            mode=="audio": {mode, audio_parts:[{path, title}], explanation}
        """
        import traceback
        prompt = params.get("prompt", "").strip()
        print(f"\n{'='*60}", flush=True)
        print(f"[ChatAgent] generate() called", flush=True)
        print(f"[ChatAgent] params={params}", flush=True)
        if not prompt:
            print(f"[ChatAgent] ERROR: empty prompt", flush=True)
            return {"error": "Empty prompt."}

        logger.info(f"[ChatAgent] prompt={prompt!r}")
        print(f"[ChatAgent] prompt={prompt!r}", flush=True)

        if registry is None:
            print(f"[ChatAgent] ERROR: MusicGen backend not available", flush=True)
            return {"error": "MusicGen backend not available."}

        try:
            intent = self._parse_intent(prompt)
        except Exception as exc:
            print(f"[ChatAgent] _parse_intent FAILED: {exc}", flush=True)
            traceback.print_exc()
            return {"error": f"Intent parse error: {exc}"}

        logger.info(f"[ChatAgent] intent={intent}")
        print(f"[ChatAgent] -> MusicGen", flush=True)

        try:
            result = self._generate_audio(intent, registry)
        except Exception as exc:
            print(f"[ChatAgent] generation FAILED: {exc}", flush=True)
            traceback.print_exc()
            return {"error": f"Generation error: {exc}"}

        print(f"[ChatAgent] result keys: {list(result.keys())}", flush=True)
        if "error" in result:
            print(f"[ChatAgent] ERROR in result: {result['error']}", flush=True)
        print(f"{'='*60}\n", flush=True)
        return result
