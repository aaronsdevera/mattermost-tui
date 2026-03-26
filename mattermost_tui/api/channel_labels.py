"""Human-readable labels for Mattermost channels (DM / group / open)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

from mattermost_tui.api.client import MattermostClient
from mattermost_tui.api.models import Channel, User


def _humanize_slug(name: str) -> str:
    if not name:
        return ""
    return name.replace("-", " ").replace("_", " ").strip().title()


def _label_open_or_private(ch: Channel) -> str:
    d = ch.display_name.strip()
    if d:
        return d
    return _humanize_slug(ch.name) or ch.id[:8]


def _ids_from_dm_channel_name(name: str) -> list[str]:
    return [p for p in name.split("__") if p]


def _label_dm_from_name(ch: Channel, my_user_id: str, nick: Callable[[str], str]) -> str:
    parts = _ids_from_dm_channel_name(ch.name)
    if not parts:
        return _label_open_or_private(ch)
    others = [p for p in parts if p != my_user_id]
    if len(others) == 1:
        return nick(others[0])
    if len(parts) == 2:
        return nick(parts[0]) if parts[1] == my_user_id else nick(parts[1])
    return ", ".join(nick(p) for p in parts)


def _label_group_from_name(ch: Channel, nick: Callable[[str], str]) -> str:
    parts = _ids_from_dm_channel_name(ch.name)
    if not parts:
        d = ch.display_name.strip()
        return d or _humanize_slug(ch.name) or "Group"
    return ", ".join(sorted(nick(p) for p in parts))


async def build_channel_labels(
    client: MattermostClient,
    channels: Sequence[Channel],
    my_user_id: str,
) -> list[str]:
    """Return one display string per channel, same order as ``channels``."""
    dm_like = [c for c in channels if c.type in ("D", "G")]

    member_by_channel: dict[str, list[str]] = {}
    if dm_like:
        tasks = [client.get_channel_members(c.id) for c in dm_like]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ch, res in zip(dm_like, results, strict=True):
            if isinstance(res, list):
                member_by_channel[ch.id] = res
            else:
                member_by_channel[ch.id] = []

    need_ids: set[str] = set()
    for ch in dm_like:
        mids = member_by_channel.get(ch.id, [])
        need_ids.update(mids)
        if not mids:
            need_ids.update(_ids_from_dm_channel_name(ch.name))

    users: dict[str, User] = {}
    if need_ids:
        users = await client.get_users_by_ids(list(need_ids))

    def nick(uid: str) -> str:
        u = users.get(uid)
        if u is not None and u.username:
            return u.username
        return uid[:8] if uid else "?"

    labels: list[str] = []
    for ch in channels:
        t = ch.type
        if t in ("O", "P", ""):
            labels.append(_label_open_or_private(ch))
        elif t == "D":
            mids = [m for m in member_by_channel.get(ch.id, []) if m != my_user_id]
            if len(mids) == 1:
                labels.append(nick(mids[0]))
            elif len(mids) > 1:
                labels.append(", ".join(sorted(nick(m) for m in mids)))
            else:
                labels.append(_label_dm_from_name(ch, my_user_id, nick))
        elif t == "G":
            full = member_by_channel.get(ch.id, [])
            if full:
                labels.append(", ".join(sorted(nick(m) for m in full)))
            else:
                labels.append(_label_group_from_name(ch, nick))
        else:
            d = ch.display_name.strip()
            labels.append(d or _humanize_slug(ch.name) or ch.id[:8])
    return labels
