"""
Anthropic Claude provider — prompt command parsing.

Activated when ANTHROPIC_API_KEY is set (Phase 2).
Uses claude-sonnet-4-6 for best instruction-following and JSON reliability.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from loguru import logger

import config
from models.prompt_cmd import SYSTEM_PROMPT

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore


from utils.json_extract import extract_json_strict


def _extract_json_actions(raw: str) -> dict:
    return extract_json_strict(raw, source="Claude")


class AnthropicCommandProvider:
    MODEL = "claude-sonnet-4-6"

    def parse_command(
        self,
        prompt: str,
        daw_context: Dict[str, Any] | None = None,
        history: list | None = None,
        **_kwargs,
    ) -> dict:
        if anthropic is None:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        context_str = ""
        if daw_context:
            context_str = f"\nCurrent DAW state:\n{json.dumps(daw_context, indent=2)}\n"
        user_msg = f"{context_str}{prompt}"

        logger.info(f"Anthropic prompt command ({self.MODEL}): {prompt!r}")

        # Build messages with conversation history (cap at last 10 turns)
        messages = []
        for turn in (history or [])[-10:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_msg})

        message = client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            temperature=0.3,
        )

        raw = message.content[0].text
        logger.debug(f"Anthropic raw output: {raw}")

        try:
            parsed = _extract_json_actions(raw)
        except (ValueError, json.JSONDecodeError):
            # Claude occasionally replies conversationally — wrap it
            return {"actions": [], "explanation": raw[:500]}

        return {
            "actions":     parsed.get("actions", []),
            "explanation": parsed.get("explanation", ""),
        }
