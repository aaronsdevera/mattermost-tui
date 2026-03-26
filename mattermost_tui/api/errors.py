"""Errors raised by the Mattermost API layer."""


class MattermostAPIError(Exception):
    """HTTP or API-level failure from a Mattermost server."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
