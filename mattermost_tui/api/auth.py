"""Login and token acquisition for Mattermost."""

from __future__ import annotations

import json
from typing import Any

import httpx

from mattermost_tui.api.client import _error_from_response, _normalize_base_url
from mattermost_tui.api.errors import MattermostAPIError
from mattermost_tui.user_agent import mattermost_tui_user_agent


def _token_from_response(resp: httpx.Response) -> str | None:
    token = resp.headers.get("Token") or resp.headers.get("token")
    if token:
        return token.strip()
    try:
        body = resp.json()
        if isinstance(body, dict):
            t = body.get("token")
            if isinstance(t, str) and t:
                return t
    except (json.JSONDecodeError, ValueError):
        pass
    return None


async def login(
    base_url: str,
    login_id: str,
    password: str,
    *,
    verify: bool | str = True,
    timeout: float = 60.0,
    proxy: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Perform ``POST /api/v4/users/login``.

    Returns ``(token, user_json)`` as returned by the server.
    """
    base = _normalize_base_url(base_url)
    lid = login_id.strip()
    pw = password.strip()
    if not lid or not pw:
        raise MattermostAPIError("login_id and password must be non-empty", status_code=None)
    async with httpx.AsyncClient(
        timeout=timeout,
        verify=verify,
        proxy=proxy,
        headers={"User-Agent": mattermost_tui_user_agent()},
    ) as client:
        resp = await client.post(
            f"{base}/api/v4/users/login",
            json={"login_id": lid, "password": pw},
        )
    if resp.status_code >= 400:
        raise _error_from_response(resp)
    token = _token_from_response(resp)
    if not token:
        raise MattermostAPIError("Login succeeded but no token was returned", status_code=resp.status_code)
    try:
        user = resp.json()
    except json.JSONDecodeError as e:
        raise MattermostAPIError("Invalid JSON in login response") from e
    if not isinstance(user, dict):
        raise MattermostAPIError("Unexpected login response shape")
    return token, user
