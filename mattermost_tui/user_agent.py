"""Default User-Agent for Mattermost HTTP clients."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, metadata, version

# Used when the distribution is not installed (e.g. running modules without uv/pip install).
_FALLBACK_REPOSITORY_URL = "https://github.com/aaronsdevera/mattermost-tui"


def mattermost_tui_user_agent() -> str:
    """Return ``mattermost-tui/<version> (+<repository URL>)``."""
    ver = "0.dev"
    url = _FALLBACK_REPOSITORY_URL
    try:
        ver = version("mattermost-tui")
    except PackageNotFoundError:
        pass
    try:
        md = metadata("mattermost-tui")
        for entry in md.get_all("Project-URL") or ():
            key, sep, val = entry.partition(", ")
            if sep and key.strip().lower() == "repository":
                url = val.strip()
                break
    except PackageNotFoundError:
        pass
    return f"mattermost-tui/{ver} (+{url})"
