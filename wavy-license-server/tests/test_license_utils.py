"""Unit tests for license key generation and HMAC validation."""

from __future__ import annotations

import pytest

from license_utils import generate_key, validate_key


class TestGenerateKey:
    def test_pro_key_prefix(self):
        key = generate_key("pro")
        assert key.startswith("PRO-")

    def test_studio_key_prefix(self):
        key = generate_key("studio")
        assert key.startswith("STU-")

    def test_key_format_three_parts(self):
        key = generate_key("pro")
        parts = key.split("-")
        assert len(parts) == 3, f"Expected 3 dash-separated parts, got: {key}"

    def test_random_part_length(self):
        key = generate_key("pro")
        random_part = key.split("-")[1]
        assert len(random_part) == 16

    def test_hmac_part_length(self):
        key = generate_key("pro")
        hmac_part = key.split("-")[2]
        assert len(hmac_part) == 8

    def test_keys_are_unique(self):
        keys = {generate_key("pro") for _ in range(50)}
        assert len(keys) == 50


class TestValidateKey:
    def test_valid_pro_key(self):
        key = generate_key("pro")
        valid, tier = validate_key(key)
        assert valid is True
        assert tier == "pro"

    def test_valid_studio_key(self):
        key = generate_key("studio")
        valid, tier = validate_key(key)
        assert valid is True
        assert tier == "studio"

    def test_tampered_hmac(self):
        key = generate_key("pro")
        parts = key.split("-")
        tampered = f"{parts[0]}-{parts[1]}-xxxxxxxx"
        valid, _ = validate_key(tampered)
        assert valid is False

    def test_tampered_random_part(self):
        key = generate_key("pro")
        parts = key.split("-")
        tampered = f"{parts[0]}-AAAAAAAAAAAAAAAA-{parts[2]}"
        valid, _ = validate_key(tampered)
        assert valid is False

    def test_too_few_parts(self):
        valid, tier = validate_key("PRO-ONLYONEPART")
        assert valid is False
        assert tier == ""

    def test_wrong_prefix(self):
        key = generate_key("pro")
        parts = key.split("-")
        broken = f"FREE-{parts[1]}-{parts[2]}"
        valid, tier = validate_key(broken)
        assert valid is False

    def test_empty_key(self):
        valid, tier = validate_key("")
        assert valid is False

    def test_case_insensitive_hmac(self):
        """The HMAC comparison should be case-insensitive."""
        key = generate_key("pro")
        parts = key.split("-")
        upper = f"{parts[0]}-{parts[1]}-{parts[2].upper()}"
        valid, _ = validate_key(upper)
        assert valid is True
