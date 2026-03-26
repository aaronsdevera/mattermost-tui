"""Async HTTP client for Mattermost REST API v4."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from mattermost_tui.api.errors import MattermostAPIError
from mattermost_tui.api.models import Channel, Post, Team, User
from mattermost_tui.user_agent import mattermost_tui_user_agent


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def _error_from_response(resp: httpx.Response) -> MattermostAPIError:
    detail: str | None = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            idata = body.get("id")
            msg = body.get("message") or body.get("detailed_error")
            if msg:
                detail = str(msg)
            if idata:
                detail = f"{detail or ''} ({idata})".strip()
    except (json.JSONDecodeError, ValueError):
        detail = resp.text[:500] if resp.text else None
    message = detail or resp.reason_phrase or f"HTTP {resp.status_code}"
    return MattermostAPIError(message, status_code=resp.status_code, detail=detail)


class MattermostClient:
    """Authenticated client; call :meth:`aclose` when done."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        verify: bool | str = True,
        timeout: float = 60.0,
        proxy: str | None = None,
    ) -> None:
        self._base = _normalize_base_url(base_url)
        self._client = httpx.AsyncClient(
            base_url=f"{self._base}/api/v4",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": mattermost_tui_user_agent(),
            },
            timeout=timeout,
            verify=verify,
            proxy=proxy,
        )

    @property
    def base_url(self) -> str:
        return self._base

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise _error_from_response(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def get_me(self) -> User:
        data = await self._request("GET", "/users/me")
        assert isinstance(data, dict)
        return User.from_api(data)

    async def get_my_teams(self) -> list[Team]:
        data = await self._request("GET", "/users/me/teams")
        if not isinstance(data, list):
            return []
        return [Team.from_api(t) for t in data if isinstance(t, dict)]

    async def get_my_channels(self) -> list[Channel]:
        data = await self._request("GET", "/users/me/channels")
        if not isinstance(data, list):
            return []
        return [Channel.from_api(c) for c in data if isinstance(c, dict)]

    async def get_user_team_channels(self, user_id: str, team_id: str) -> list[Channel]:
        data = await self._request("GET", f"/users/{user_id}/teams/{team_id}/channels")
        if not isinstance(data, list):
            return []
        return [Channel.from_api(c) for c in data if isinstance(c, dict)]

    async def get_channel_members(self, channel_id: str) -> list[str]:
        page = 0
        per_page = 200
        user_ids: list[str] = []
        while True:
            data = await self._request(
                "GET",
                f"/channels/{channel_id}/members",
                params={"page": page, "per_page": per_page},
            )
            if not isinstance(data, list) or not data:
                break
            for m in data:
                if isinstance(m, dict) and m.get("user_id"):
                    user_ids.append(str(m["user_id"]))
            if len(data) < per_page:
                break
            page += 1
        return user_ids

    async def get_user(self, user_id: str) -> User:
        data = await self._request("GET", f"/users/{user_id}")
        assert isinstance(data, dict)
        return User.from_api(data)

    async def get_posts(
        self,
        channel_id: str,
        *,
        page: int = 0,
        per_page: int = 60,
        since: int | None = None,
    ) -> list[Post]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if since is not None:
            params["since"] = since
        data = await self._request("GET", f"/channels/{channel_id}/posts", params=params)
        if not isinstance(data, dict):
            return []
        posts_map = data.get("posts")
        order = data.get("order")
        if not isinstance(posts_map, dict) or not isinstance(order, list):
            return []
        out: list[Post] = []
        for pid in order:
            raw = posts_map.get(pid)
            if isinstance(raw, dict):
                out.append(Post.from_api(raw))
        return out

    async def get_channel_member_me(self, channel_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/channels/{channel_id}/members/me")
        if not isinstance(data, dict):
            return {}
        return data

    async def get_channel_members_me_bulk(
        self, channel_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Fetch channel member info for the current user for multiple channels in parallel.

        Returns a mapping of channel_id → member dict (same shape as get_channel_member_me).
        Channels that fail (e.g. no access) are omitted from the result.
        """
        if not channel_ids:
            return {}

        async def _fetch(cid: str) -> tuple[str, dict[str, Any]] | None:
            try:
                return cid, await self.get_channel_member_me(cid)
            except MattermostAPIError:
                return None

        results = await asyncio.gather(*(_fetch(cid) for cid in channel_ids))
        return {cid: member for r in results if r is not None for cid, member in [r]}

    async def mark_channel_viewed(
        self, channel_id: str, *, prev_channel_id: str | None = None
    ) -> None:
        payload: dict[str, Any] = {"channel_id": channel_id}
        if prev_channel_id:
            payload["prev_channel_id"] = prev_channel_id
        await self._request("POST", "/channels/members/me/view", json=payload)

    async def create_post(self, channel_id: str, message: str) -> Post:
        payload = {"channel_id": channel_id, "message": message}
        data = await self._request("POST", "/posts", json=payload)
        assert isinstance(data, dict)
        return Post.from_api(data)

    async def get_users_by_ids(self, user_ids: list[str]) -> dict[str, User]:
        if not user_ids:
            return {}
        data = await self._request("POST", "/users/ids", json=user_ids)
        if not isinstance(data, list):
            return {}
        out: dict[str, User] = {}
        for item in data:
            if isinstance(item, dict) and "id" in item:
                u = User.from_api(item)
                out[u.id] = u
        return out
