"""
Groq provider — prompt command parsing via Groq cloud API (free tier).

Activated when GROQ_API_KEY is set and ANTHROPIC_API_KEY is not.
Uses llama-3.3-70b-versatile for best instruction-following on Groq's free tier.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from loguru import logger

import config
from models.prompt_cmd import SYSTEM_PROMPT

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore


from utils.json_extract import extract_json_strict


def _extract_json(raw: str) -> dict:
    return extract_json_strict(raw, source="Groq")


class GroqCommandProvider:
    MODEL = "llama-3.3-70b-versatile"  # best quality on Groq free tier

    def parse_command(
        self,
        prompt: str,
        daw_context: Dict[str, Any] | None = None,
        history: list | None = None,
        **_kwargs,
    ) -> dict:
        if Groq is None:
            raise ImportError("groq package not installed. Run: pip install groq")

        client = Groq(api_key=config.GROQ_API_KEY)

        context_str = ""
        if daw_context:
            context_str = f"\nCurrent DAW state:\n{json.dumps(daw_context, indent=2)}\n"
        user_msg = f"{context_str}{prompt}"

        logger.info(f"Groq prompt command ({self.MODEL}): {prompt!r}")

        # Build messages: system prompt + conversation history (cap at 10 turns) + current
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in (history or [])[-10:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_msg})

        response = client.chat.completions.create(
            model=self.MODEL,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )

        raw = response.choices[0].message.content
        logger.debug(f"Groq raw output: {raw}")

        try:
            parsed = _extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            # Model replied conversationally — wrap as explanation
            return {"actions": [], "explanation": raw[:500]}

        return {
            "actions":     parsed.get("actions", []),
            "explanation": parsed.get("explanation", ""),
        }
