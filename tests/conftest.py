"""Pytest hooks and fixtures for richer test-run logging."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

_log = logging.getLogger("mattermost_tui.tests")


def pytest_sessionstart(session: pytest.Session) -> None:
    root = Path(session.config.rootpath)
    _log.info("pytest session start (root=%s, python=%s)", root, sys.version.split()[0])


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _log.info("pytest session finish (exit status=%s)", exitstatus)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    _log.info("setup %s", item.nodeid)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    _log.info("teardown %s", item.nodeid)
