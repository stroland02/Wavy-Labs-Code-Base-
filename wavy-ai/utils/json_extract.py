"""Shared JSON extraction helpers for LLM output parsing."""
from __future__ import annotations

import json
import re


def extract_json(raw: str) -> dict | None:
    """Extract the first JSON object from an LLM response string.

    Tolerates markdown code fences, surrounding prose, and minor formatting
    issues.  Returns ``None`` on parse failure instead of raising.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first complete JSON object in surrounding text
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return None


def extract_json_strict(raw: str, *, source: str = "LLM") -> dict:
    """Like :func:`extract_json` but raises :class:`ValueError` on failure."""
    result = extract_json(raw)
    if result is None:
        raise ValueError(f"{source} did not return valid JSON: {raw!r}")
    return result
