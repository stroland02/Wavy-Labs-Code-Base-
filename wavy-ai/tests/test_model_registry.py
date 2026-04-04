"""
Tests for the ModelRegistry — lazy-loading and error handling.
These tests mock the underlying model classes to avoid GPU/download requirements.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.registry import ModelRegistry, MODEL_CATALOG


class TestModelRegistry:
    def test_catalog_has_all_expected_models(self):
        expected = {"demucs", "mixer", "prompt_cmd", "code_to_music"}
        assert expected == set(MODEL_CATALOG.keys())

    def test_unknown_model_raises(self):
        reg = ModelRegistry()
        with pytest.raises(ValueError, match="Unknown model"):
            reg.load("nonexistent_model")

    def test_load_creates_instance(self):
        reg = ModelRegistry()
        fake = MagicMock()
        fake_cls = MagicMock(return_value=fake)
        with patch.dict(MODEL_CATALOG, {"test_model": ("models.test", "TestModel", 1.0)}):
            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.TestModel = fake_cls
                mock_import.return_value = mock_module
                reg.load("test_model")
                assert "test_model" in reg.loaded_model_names()

    def test_get_triggers_load(self):
        reg = ModelRegistry()
        with patch.object(reg, "load") as mock_load:
            mock_load.side_effect = lambda n: reg._instances.__setitem__(n, MagicMock())
            reg.get("demucs")
            mock_load.assert_called_once_with("demucs")

    def test_get_does_not_reload_if_present(self):
        reg = ModelRegistry()
        reg._instances["demucs"] = MagicMock()
        with patch.object(reg, "load") as mock_load:
            reg.get("demucs")
            mock_load.assert_not_called()

    def test_unload_calls_model_unload(self):
        reg = ModelRegistry()
        mock_model = MagicMock()
        reg._instances["demucs"] = mock_model
        reg.unload("demucs")
        mock_model.unload.assert_called_once()
        assert "demucs" not in reg._instances

    def test_unload_nonexistent_is_noop(self):
        reg = ModelRegistry()
        reg.unload("not_loaded")   # should not raise

    def test_model_status_returns_all(self):
        reg = ModelRegistry()
        status = reg.model_status()
        assert len(status) == len(MODEL_CATALOG)
        for s in status:
            assert "name" in s and "loaded" in s and "vram_gb" in s
