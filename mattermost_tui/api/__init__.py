"""Mattermost REST API helpers."""

from mattermost_tui.api.auth import login
from mattermost_tui.api.client import MattermostClient
from mattermost_tui.api.errors import MattermostAPIError
from mattermost_tui.api.models import Channel, Post, Team, User

__all__ = [
    "Channel",
    "MattermostAPIError",
    "MattermostClient",
    "Post",
    "Team",
    "User",
    "login",
]
