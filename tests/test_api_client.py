"""API client helper tests."""

from __future__ import annotations

from mattermost_tui.api.client import _normalize_base_url


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert _normalize_base_url("https://mm.example.com/") == "https://mm.example.com"


def test_normalize_base_url_unchanged_without_slash() -> None:
    assert _normalize_base_url("https://mm.example.com") == "https://mm.example.com"
