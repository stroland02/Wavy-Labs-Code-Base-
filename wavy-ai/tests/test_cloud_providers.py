"""
Tests for cloud/anthropic_provider.py.
All external API calls are mocked — no real keys needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_actions_json(actions=None, explanation="ok"):
    return json.dumps({
        "actions":     actions or [],
        "explanation": explanation,
    })


# ── AnthropicCommandProvider ──────────────────────────────────────────────────

class TestAnthropicCommandProvider:

    def _make_provider(self):
        from cloud.anthropic_provider import AnthropicCommandProvider
        return AnthropicCommandProvider()

    def _mock_client(self, raw_text: str):
        """Return a mock anthropic.Anthropic client whose create() returns raw_text."""
        msg = MagicMock()
        msg.content = [MagicMock(text=raw_text)]
        client = MagicMock()
        client.messages.create.return_value = msg
        return client

    def test_parse_clean_json(self):
        provider = self._make_provider()
        raw = _make_actions_json(
            actions=[{"type": "set_tempo", "bpm": 128}],
            explanation="Set tempo to 128 BPM",
        )
        with patch("cloud.anthropic_provider.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = self._mock_client(raw)
            result = provider.parse_command("set tempo to 128", daw_context=None)

        assert result["actions"] == [{"type": "set_tempo", "bpm": 128}]
        assert "128" in result["explanation"]

    def test_parse_markdown_fenced_json(self):
        """Claude may wrap JSON in ```json ... ``` fences."""
        provider = self._make_provider()
        payload = _make_actions_json(
            actions=[{"type": "set_key", "key": "Am", "scale": "minor"}],
            explanation="Set key to A minor",
        )
        raw = f"```json\n{payload}\n```"
        with patch("cloud.anthropic_provider.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = self._mock_client(raw)
            result = provider.parse_command("change key to A minor")

        assert result["actions"][0]["type"] == "set_key"

    def test_parse_embedded_json(self):
        """Handles extra text before/after the JSON object."""
        provider = self._make_provider()
        payload = _make_actions_json(actions=[], explanation="nothing to do")
        raw = f"Here is the action:\n{payload}\nDone."
        with patch("cloud.anthropic_provider.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = self._mock_client(raw)
            result = provider.parse_command("do nothing")

        assert result["actions"] == []
        assert result["explanation"] == "nothing to do"

    def test_daw_context_included_in_user_message(self):
        provider = self._make_provider()
        raw = _make_actions_json()
        captured = {}

        def fake_create(**kwargs):
            captured["messages"] = kwargs["messages"]
            msg = MagicMock()
            msg.content = [MagicMock(text=raw)]
            return msg

        with patch("cloud.anthropic_provider.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = fake_create
            mock_anthropic.Anthropic.return_value = mock_client
            provider.parse_command(
                "add a drum track",
                daw_context={"tracks": 3, "tempo": 120},
            )

        user_content = captured["messages"][0]["content"]
        assert "tracks" in user_content
        assert "120" in user_content

    def test_missing_anthropic_package_raises_import_error(self):
        """ImportError is raised when anthropic is not installed."""
        import sys
        provider = self._make_provider()

        # Temporarily hide the anthropic module
        with patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic package not installed"):
                provider.parse_command("hello")

    def test_model_is_claude_sonnet(self):
        from cloud.anthropic_provider import AnthropicCommandProvider
        assert AnthropicCommandProvider.MODEL == "claude-sonnet-4-6"

