"""
Tests for model_check.py — first-run download helper.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from model_check import check_and_download, _is_downloaded, MODEL_MANIFEST


class TestIsDownloaded:
    def test_empty_files_list_always_downloaded(self):
        # Models like demucs/bark are managed externally
        assert _is_downloaded("demucs", []) is True

    def test_returns_false_when_files_missing(self, tmp_path):
        with patch("model_check.MODEL_DIR", tmp_path):
            assert _is_downloaded("mixer", ["mixer_v1.onnx"]) is False

    def test_returns_true_when_all_files_present(self, tmp_path):
        model_dir = tmp_path / "mixer"
        model_dir.mkdir()
        (model_dir / "mixer_v1.onnx").touch()
        with patch("model_check.MODEL_DIR", tmp_path):
            assert _is_downloaded("mixer", ["mixer_v1.onnx"]) is True


class TestCheckAndDownload:
    def test_skips_optional_when_required_only(self):
        optional = [m["name"] for m in MODEL_MANIFEST if not m["required"]]
        if not optional:
            pytest.skip("No optional models in manifest")

        with patch("model_check.download_model") as mock_dl:
            mock_dl.return_value = True
            # Patch _is_downloaded to say nothing is downloaded
            with patch("model_check._is_downloaded", return_value=False):
                results = check_and_download(required_only=True)
            # None of the optional models should be in results
            for name in optional:
                assert name not in results

    def test_downloads_missing_required(self):
        required = [m["name"] for m in MODEL_MANIFEST if m["required"] and m["files"]]
        if not required:
            pytest.skip("No required models with files in manifest")

        with patch("model_check.download_model", return_value=True) as mock_dl:
            with patch("model_check._is_downloaded", return_value=False):
                results = check_and_download(required_only=True)
            for name in required:
                assert results.get(name) is True

    def test_names_filter(self):
        with patch("model_check.download_model", return_value=True):
            with patch("model_check._is_downloaded", return_value=False):
                results = check_and_download(required_only=False, names=["demucs"])
        assert set(results.keys()) == {"demucs"}

    def test_already_downloaded_skipped(self):
        with patch("model_check.download_model") as mock_dl:
            with patch("model_check._is_downloaded", return_value=True):
                results = check_and_download(required_only=True)
            mock_dl.assert_not_called()
            for v in results.values():
                assert v is True
