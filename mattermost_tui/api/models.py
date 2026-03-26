"""Lightweight models for Mattermost API payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    display_name: str
    team_id: str
    type: str
    delete_at: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Channel:
        return cls(
            id=data["id"],
            name=str(data.get("name") or ""),
            display_name=str(data.get("display_name") or ""),
            team_id=str(data.get("team_id") or ""),
            type=str(data.get("type") or "O").upper(),
            delete_at=int(data.get("delete_at") or 0),
        )

    @property
    def is_deleted(self) -> bool:
        return self.delete_at > 0


@dataclass(frozen=True)
class Team:
    id: str
    display_name: str
    name: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Team:
        return cls(
            id=data["id"],
            display_name=str(data.get("display_name") or ""),
            name=str(data.get("name") or ""),
        )


@dataclass(frozen=True)
class User:
    id: str
    username: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> User:
        return cls(
            id=data["id"],
            username=str(data.get("username") or ""),
        )


@dataclass(frozen=True)
class Post:
    id: str
    user_id: str
    message: str
    create_at: int
    post_type: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Post:
        return cls(
            id=data["id"],
            user_id=str(data.get("user_id") or ""),
            message=str(data.get("message") or ""),
            create_at=int(data.get("create_at") or 0),
            post_type=str(data.get("type") or ""),
        )

    @property
    def is_system_message(self) -> bool:
        """True for Mattermost-generated posts (joins, adds, leaves, header changes, etc.)."""
        return self.post_type.startswith("system_")
