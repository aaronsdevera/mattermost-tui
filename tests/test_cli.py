"""CLI and URL validation tests."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from mattermost_tui.cli import _validate_base_url, main


def test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Browse channels" in result.output


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "https://",
        "not-a-url",
        "",
    ],
)
def test_validate_base_url_rejects_bad_urls(url: str) -> None:
    with pytest.raises(click.BadParameter):
        _validate_base_url(url)


def test_validate_base_url_accepts_https() -> None:
    _validate_base_url("https://chat.example.com")


def test_validate_base_url_accepts_http_localhost() -> None:
    _validate_base_url("http://localhost:8065")
