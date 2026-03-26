"""Textual terminal UI for Mattermost."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from rich.markup import escape
from textual import events, on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, Input, OptionList, RichLog, Static

from mattermost_tui.api import MattermostAPIError
from mattermost_tui.api.channel_labels import build_channel_labels
from mattermost_tui.api.client import MattermostClient
from mattermost_tui.api.models import Channel, Post, Team


def _format_ts(ms: int) -> str:
    if not ms:
        return "?"
    dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M")


def _format_post_line(p: Post, username: str, *, highlight: bool = False) -> str:
    ts = f"[dim]{_format_ts(p.create_at)}[/dim]"
    if p.is_system_message:
        line = f"{ts} [italic bright_black]{escape(p.message)}[/italic bright_black]"
    else:
        line = f"{ts} [cyan]{escape(username)}[/cyan]: {escape(p.message)}"
    if highlight:
        return f"[bold bright_yellow]▌[/bold bright_yellow] {line}"
    return line


_POSTS_VIEW_ACTIONS = frozenset({"search_posts", "channel_info", "toggle_unread_filter"})

PostsViewFilter = Literal["all", "unread"]

MessageLineMode = Literal["wrap", "scroll"]


def _main_hotkey(
    darwin_letter: str,
    win_linux_letter: str,
    *,
    darwin_shift: bool = False,
) -> str:
    """Primary modifier chord: macOS uses Ctrl+letter; Windows and Linux use Ctrl+Shift+letter.

    Plain Shift+letter is unreliable in many terminals. ``ctrl+c`` / ``ctrl+m`` are avoided on
    macOS (interrupt / already bound to Chats). Letters differ by platform only when needed.

    Some Ctrl chords must use Ctrl+Shift on macOS too because Textual's ``Input`` (the composer)
    reserves them — e.g. ``ctrl+f`` is "delete word right" in the message field.
    """
    if sys.platform == "darwin":
        if darwin_shift:
            return f"ctrl+shift+{darwin_letter}"
        return f"ctrl+{darwin_letter}"
    return f"ctrl+shift+{win_linux_letter}"


class CommandsModal(ModalScreen[None]):
    """All app commands in a scrollable list (no search)."""

    BINDINGS = [
        Binding("escape", "dismiss", "", show=False),
    ]

    DEFAULT_CSS = """
    CommandsModal > Vertical {
        align: center middle;
        width: 76%;
        max-width: 84;
        height: auto;
        max-height: 70%;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    CommandsModal #commands-modal-list {
        height: auto;
        max-height: 22;
        border: none;
    }
    """

    def __init__(self, commands: list[SystemCommand]) -> None:
        super().__init__()
        self._commands = sorted(commands, key=lambda c: c.title.lower())

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "Commands — ↑↓ move · Enter run · Esc close",
                id="commands-modal-hint",
            )
            yield OptionList(id="commands-modal-list")

    def on_mount(self) -> None:
        ol = self.query_one("#commands-modal-list", OptionList)
        for cmd in self._commands:
            ol.add_option(cmd.title)
        ol.focus()

    @on(OptionList.OptionSelected, "#commands-modal-list")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        cmd = self._commands[event.option_index]
        self.dismiss()
        self.app.call_later(cmd.callback)


class ChannelSearchModal(ModalScreen[str | None]):
    """Filter loaded messages by substring; Enter on empty clears the filter."""

    BINDINGS = [
        Binding("escape", "dismiss", "", show=False),
    ]

    DEFAULT_CSS = """
    ChannelSearchModal > Vertical {
        align: center middle;
        width: 70%;
        max-width: 72;
        height: auto;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Filter messages (empty + Enter clears filter)", id="search-hint")
            yield Input(placeholder="Substring…", id="search-input")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    @on(Input.Submitted, "#search-input")
    def _submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


SidebarMode = Literal["channels", "dms"]

_TYPEAHEAD_IDLE_SEC = 1.0


class ChannelOptionList(OptionList):
    """Channel sidebar with type-to-select (prefix jump)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._typeahead_labels: list[str] = []
        self._typeahead: str = ""
        self._typeahead_timer: Timer | None = None

    def set_typeahead_labels(self, labels: list[str]) -> None:
        self._typeahead_labels = labels
        self._clear_typeahead()

    def _cancel_typeahead_timer(self) -> None:
        if self._typeahead_timer is not None:
            self._typeahead_timer.stop()
            self._typeahead_timer = None

    def _clear_typeahead(self) -> None:
        self._cancel_typeahead_timer()
        self._typeahead = ""

    def _arm_typeahead_timer(self) -> None:
        self._cancel_typeahead_timer()
        self._typeahead_timer = self.set_timer(
            _TYPEAHEAD_IDLE_SEC,
            self._on_typeahead_idle,
            name="channel_typeahead",
        )

    def _on_typeahead_idle(self) -> None:
        self._typeahead = ""
        self._typeahead_timer = None

    def _apply_typeahead(self) -> None:
        if not self._typeahead or not self._typeahead_labels:
            return
        prefix = self._typeahead.lower()
        for i, lab in enumerate(self._typeahead_labels):
            if lab.lower().startswith(prefix):
                self.highlighted = i
                return

    async def on_key(self, event: events.Key) -> None:
        nav_keys = frozenset(
            {"up", "down", "home", "end", "pageup", "pagedown", "enter"}
        )
        if event.key in nav_keys:
            self._clear_typeahead()
            return

        if event.key == "escape":
            if self._typeahead:
                self._clear_typeahead()
                event.stop()
            return

        if event.key == "backspace":
            if self._typeahead:
                self._typeahead = self._typeahead[:-1]
                self._apply_typeahead()
                self._arm_typeahead_timer()
                event.stop()
            return

        if not self._typeahead_labels:
            return

        if (
            event.is_printable
            and event.character is not None
            and len(event.character) == 1
            and event.character.isprintable()
        ):
            if "ctrl+" in event.key or "meta+" in event.key:
                return
            self._typeahead += event.character.lower()
            self._apply_typeahead()
            self._arm_typeahead_timer()
            event.stop()


class MattermostTui(App[None]):
    """Channel list, post thread, and composer."""

    CSS = """
    Horizontal {
        height: 1fr;
    }
    #channels {
        width: 30%;
        min-width: 16;
        border-right: tall $primary;
    }
    #main {
        width: 1fr;
    }
    #log {
        height: 1fr;
        border: none;
        background: $surface;
    }
    #composer {
        height: 3;
        border-top: tall $primary-darken-2;
    }
    Footer {
        align-horizontal: right;
    }
    """

    BINDINGS = [
        Binding(_main_hotkey("e", "c"), "reload_channels", "Channels", show=True),
        Binding(_main_hotkey("y", "m"), "reload_posts", "Messages", show=True),
        Binding(_main_hotkey("f", "s", darwin_shift=True), "search_posts", "Search", show=True),
        Binding(_main_hotkey("u", "u"), "toggle_unread_filter", "Unread", show=True),
        Binding(_main_hotkey("o", "i"), "channel_info", "Channel info", show=True),
        Binding(_main_hotkey("h", "h"), "toggle_message_line_mode", "Wrap/scroll", show=True),
        Binding("ctrl+t", "next_team", "Team", show=True),
        Binding("ctrl+m", "toggle_sidebar", "Chats", show=True),
        Binding("escape", "blur_input", "Unfocus", show=False),
        Binding(
            "ctrl+p",
            "command_palette",
            "Commands",
            show=False,
            priority=True,
            tooltip="List all commands",
        ),
    ]

    def __init__(
        self,
        client: MattermostClient,
        *,
        poll_interval: float = 5.0,
        message_line_mode: MessageLineMode = "wrap",
    ) -> None:
        super().__init__()
        self._mm = client
        self._poll_interval = poll_interval
        self._message_line_mode: MessageLineMode = message_line_mode
        self._teams: list[Team] = []
        self._current_team_id: str | None = None
        self._sidebar_mode: SidebarMode = "channels"
        self._channels: list[Channel] = []
        self._channel_index: dict[int, str] = {}
        self._current_channel_id: str | None = None
        self._usernames: dict[str, str] = {}
        self._channel_labels: dict[str, str] = {}
        self._last_posts: list[Post] = []
        self._last_posts_channel_id: str | None = None
        self._post_filter: str = ""
        self._post_view_filter: PostsViewFilter = "all"
        self._unread_waterline: dict[str, int] = {}
        self._highlight_post_ids: set[str] = set()
        self._my_user_id: str | None = None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in _POSTS_VIEW_ACTIONS:
            return bool(self._current_channel_id)
        return True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield ChannelOptionList(id="channels")
            with Vertical(id="main"):
                yield RichLog(
                    id="log",
                    highlight=True,
                    markup=True,
                    wrap=self._message_line_mode == "wrap",
                    min_width=0 if self._message_line_mode == "wrap" else 78,
                )
                yield Input(placeholder="Message (Enter to send)…", id="composer")
        yield Footer(compact=True)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)

        def make_runner(act: str):
            async def _runner() -> None:
                await self.run_action(act)

            return _runner

        specs: list[tuple[str, str, str]] = [
            (
                "Focus channel list",
                "reload_channels",
                "Sidebar: move focus here; type letters to jump by channel name.",
            ),
            (
                "Focus messages",
                "reload_posts",
                "Message pane: scroll and read the current channel.",
            ),
            (
                "Filter messages in channel",
                "search_posts",
                "Search within loaded messages (opens filter prompt).",
            ),
            (
                "Toggle unread-only messages",
                "toggle_unread_filter",
                "Switch between all messages and unread-only in this channel.",
            ),
            (
                "Show channel info",
                "channel_info",
                "Open channel metadata (name, type, team, id).",
            ),
            (
                "Toggle message wrap / horizontal scroll",
                "toggle_message_line_mode",
                "Message pane: wrap long lines or fixed width with sideways scroll.",
            ),
            (
                "Next Mattermost team",
                "next_team",
                "Rotate team and reload the channel sidebar.",
            ),
            (
                "Toggle channels / direct messages",
                "toggle_sidebar",
                "Sidebar: team channels versus direct and group messages.",
            ),
        ]
        for title, action, blurb in specs:
            key = self._key_display_for_action(screen, action)
            help_line = f"{blurb} Shortcut: {key}." if key else f"{blurb}"
            yield SystemCommand(title, help_line, make_runner(action))

    @staticmethod
    def _key_display_for_action(screen: Screen, action: str) -> str:
        for _node, binding, _enabled, _tooltip in screen.active_bindings.values():
            if binding.action == action and binding.show:
                return str(screen.app.get_key_display(binding))
        return ""

    def action_command_palette(self) -> None:
        if not self.use_command_palette or isinstance(self.screen, CommandsModal):
            return
        self.push_screen(CommandsModal(list(self.get_system_commands(self.screen))))

    async def on_mount(self) -> None:
        if self._poll_interval > 0:
            self.set_interval(self._poll_interval, self._poll_new_posts)
        self._load_channels()

    @work(exclusive=True, group="mattermost-channels")
    async def _load_channels(self) -> None:
        self._current_channel_id = None
        self.refresh_bindings()
        ol = self.query_one("#channels", ChannelOptionList)
        # Clear the sidebar immediately so highlight events during the awaits below
        # cannot resolve against stale _channel_index (would load the wrong channel
        # while the new list is still fetching — e.g. team channel + DM sidebar).
        ol.clear_options()
        self._channel_index.clear()
        ol.set_typeahead_labels([])
        log = self.query_one("#log", RichLog)
        log.clear()
        self._last_posts = []
        self._last_posts_channel_id = None
        self._post_filter = ""
        self._highlight_post_ids.clear()
        try:
            me = await self._mm.get_me()
            self._my_user_id = me.id
            self._usernames[me.id] = me.username
        except MattermostAPIError as e:
            self.notify(str(e), severity="error")
            return

        try:
            teams = sorted(
                await self._mm.get_my_teams(),
                key=lambda t: (t.display_name or t.name or "").lower(),
            )
        except MattermostAPIError as e:
            self.notify(str(e), severity="error")
            return

        self._teams = teams
        if not teams:
            self.notify("No teams found for this account", severity="error")
            return

        valid_ids = {t.id for t in teams}
        if self._current_team_id not in valid_ids:
            self._current_team_id = teams[0].id

        team = next(t for t in teams if t.id == self._current_team_id)
        team_label = (team.display_name or team.name).strip() or team.id

        if self._sidebar_mode == "channels":
            self.title = team_label
            self.sub_title = "Channels"
            try:
                raw = await self._mm.get_user_team_channels(me.id, team.id)
            except MattermostAPIError as e:
                self.notify(str(e), severity="error")
                return
            raw = [c for c in raw if c.type in ("O", "P") and not c.is_deleted]
        else:
            self.title = "Direct messages"
            self.sub_title = team_label
            try:
                raw = await self._mm.get_my_channels()
            except MattermostAPIError as e:
                self.notify(str(e), severity="error")
                return
            raw = [c for c in raw if c.type in ("D", "G") and not c.is_deleted]

        labels = await build_channel_labels(self._mm, raw, me.id)
        enriched = list(zip(raw, labels, strict=True))
        enriched.sort(key=lambda x: x[1].lower())
        self._channels = [e[0] for e in enriched]
        self._channel_labels = {ch.id: lab for ch, lab in enriched}
        ol.clear_options()
        self._channel_index.clear()
        for i, ch in enumerate(self._channels):
            ol.add_option(self._channel_labels[ch.id])
            self._channel_index[i] = ch.id

        ol.set_typeahead_labels([self._channel_labels[ch.id] for ch in self._channels])

        mode = "channels" if self._sidebar_mode == "channels" else "DMs"
        self.notify(f"{len(self._channels)} {mode}", severity="information")
        if self._channels:
            ol.highlighted = 0
        self.refresh_bindings()

    def action_reload_channels(self) -> None:
        self._load_channels()

    def action_reload_posts(self) -> None:
        if self._current_channel_id:
            self._load_posts(self._current_channel_id)

    def action_toggle_unread_filter(self) -> None:
        if not self._current_channel_id:
            self.notify("Select a channel first", severity="warning")
            return
        self._post_view_filter = "all" if self._post_view_filter == "unread" else "unread"
        self._rerender_posts_log()
        self.notify(
            "Message list: unread only" if self._post_view_filter == "unread" else "Message list: all",
            severity="information",
        )

    def action_next_team(self) -> None:
        if not self._teams:
            self.notify("Teams not loaded yet", severity="warning")
            return
        if len(self._teams) < 2:
            self.notify("Only one team on this account", severity="information")
            return
        assert self._current_team_id is not None
        idx = next(i for i, t in enumerate(self._teams) if t.id == self._current_team_id)
        nxt = self._teams[(idx + 1) % len(self._teams)]
        self._current_team_id = nxt.id
        label = (nxt.display_name or nxt.name).strip() or nxt.id
        self.notify(f"Team: {label}", severity="information")
        self._load_channels()

    def action_toggle_sidebar(self) -> None:
        self._sidebar_mode = "dms" if self._sidebar_mode == "channels" else "channels"
        self.notify(
            "Sidebar: channels (this team)" if self._sidebar_mode == "channels" else "Sidebar: direct messages",
            severity="information",
        )
        self._load_channels()

    def action_blur_input(self) -> None:
        self.set_focus(self.query_one("#channels", ChannelOptionList))

    def action_toggle_message_line_mode(self) -> None:
        self._message_line_mode = "scroll" if self._message_line_mode == "wrap" else "wrap"
        self._apply_message_line_mode_to_log()
        self.notify(
            "Long lines: word wrap"
            if self._message_line_mode == "wrap"
            else "Long lines: horizontal scroll (focus messages, scroll right for end of line)",
            severity="information",
        )

    def _apply_message_line_mode_to_log(self) -> None:
        log = self.query_one("#log", RichLog)
        wrap = self._message_line_mode == "wrap"
        log.wrap = wrap
        log.min_width = 0 if wrap else 78
        cid = self._current_channel_id
        if cid and cid == self._last_posts_channel_id and self._last_posts:
            self._render_posts_into_log(cid, self._last_posts)
        else:
            log.clear()

    def _filtered_posts(self, posts: list[Post]) -> list[Post]:
        out = posts
        cid = self._current_channel_id
        if self._post_view_filter == "unread" and cid:
            w = self._unread_waterline.get(cid)
            if w is not None:
                my = self._my_user_id

                def _is_unread(p: Post) -> bool:
                    if p.create_at <= w:
                        return False
                    if my and p.user_id == my:
                        return False
                    return True

                out = [p for p in out if _is_unread(p)]
        if self._post_filter:
            out = [p for p in out if self._post_filter in p.message.lower()]
        return out

    def _render_posts_into_log(self, channel_id: str, posts: list[Post]) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        ch = next((c for c in self._channels if c.id == channel_id), None)
        title = self._channel_labels.get(channel_id) or (
            (ch.display_name or ch.name) if ch else channel_id
        )
        log.write(f"[bold]#{escape(title)}[/bold]")
        if self._post_view_filter == "unread":
            log.write("[dim]Showing unread only (waterline from when you opened this channel).[/dim]")
        for p in self._filtered_posts(posts):
            user = self._usernames.get(p.user_id, p.user_id[:8] if p.user_id else "?")
            hi = p.id in self._highlight_post_ids
            log.write(_format_post_line(p, user, highlight=hi))

    def _rerender_posts_log(self) -> None:
        cid = self._current_channel_id
        if not cid or cid != self._last_posts_channel_id:
            self.notify("No messages loaded for this channel", severity="warning")
            return
        self._render_posts_into_log(cid, self._last_posts)

    async def action_search_posts(self) -> None:
        if not self._current_channel_id:
            return
        result = await self.push_screen_wait(ChannelSearchModal())
        if result is None:
            return
        self._post_filter = result.lower()
        self._rerender_posts_log()
        if self._post_filter:
            n = len(self._filtered_posts(self._last_posts))
            self.notify(f"{n} matching message(s)", severity="information")

    def action_channel_info(self) -> None:
        cid = self._current_channel_id
        if not cid:
            return
        ch = next((c for c in self._channels if c.id == cid), None)
        if not ch:
            self.notify(f"Channel id: {cid}", severity="information")
            return
        label = self._channel_labels.get(cid) or (ch.display_name or ch.name or cid)
        type_names = {"O": "Open", "P": "Private", "D": "Direct", "G": "Group"}
        kind = type_names.get(ch.type, ch.type)
        team = next((t for t in self._teams if t.id == ch.team_id), None)
        team_line = (
            (team.display_name or team.name).strip() or ch.team_id
            if team
            else ch.team_id
        )
        body = (
            f"Label: {label}\n"
            f"Name: {ch.name or '—'}\n"
            f"Display name: {ch.display_name or '—'}\n"
            f"Type: {kind}\n"
            f"Team: {team_line}\n"
            f"Id: {ch.id}"
        )
        self.notify(body, title="Channel", severity="information", timeout=12)

    @on(OptionList.OptionHighlighted, "#channels")
    async def _channel_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        idx = event.option_index
        cid = self._channel_index.get(idx)
        if not cid or cid == self._current_channel_id:
            return
        prev = self._current_channel_id
        self._current_channel_id = cid
        self.refresh_bindings()
        self._load_posts(cid, prev_channel_id=prev)

    @work(exclusive=True, group="mattermost-posts")
    async def _load_posts(self, channel_id: str, prev_channel_id: str | None = None) -> None:
        last_viewed = 0
        try:
            member = await self._mm.get_channel_member_me(channel_id)
            last_viewed = int(member.get("last_viewed_at") or 0)
        except MattermostAPIError:
            pass
        self._unread_waterline[channel_id] = last_viewed

        try:
            posts = list(reversed(await self._mm.get_posts(channel_id)))
        except MattermostAPIError as e:
            self.notify(str(e), severity="error")
            return
        user_ids = list({p.user_id for p in posts if p.user_id})
        try:
            users = await self._mm.get_users_by_ids(user_ids)
        except MattermostAPIError:
            users = {}
        for uid, u in users.items():
            self._usernames[uid] = u.username

        self._last_posts = posts
        self._last_posts_channel_id = channel_id
        self._post_filter = ""
        self._highlight_post_ids.clear()

        try:
            await self._mm.mark_channel_viewed(channel_id, prev_channel_id=prev_channel_id)
        except MattermostAPIError:
            pass

        self._render_posts_into_log(channel_id, posts)
        self.refresh_bindings()

    @work(exclusive=True, group="mattermost-poll")
    async def _poll_new_posts(self) -> None:
        cid = self._current_channel_id
        if not cid or cid != self._last_posts_channel_id or not self._last_posts:
            return
        since_ms = max(p.create_at for p in self._last_posts)
        try:
            batch = await self._mm.get_posts(cid, since=since_ms, per_page=200)
        except MattermostAPIError:
            return
        existing = {p.id for p in self._last_posts}
        truly_new = [p for p in batch if p.id not in existing]
        if not truly_new:
            return
        truly_new.sort(key=lambda p: p.create_at)
        new_uids = list({p.user_id for p in truly_new if p.user_id and p.user_id not in self._usernames})
        if new_uids:
            try:
                users = await self._mm.get_users_by_ids(new_uids)
            except MattermostAPIError:
                users = {}
            for uid, u in users.items():
                self._usernames[uid] = u.username

        self._last_posts.extend(truly_new)
        for p in truly_new:
            self._highlight_post_ids.add(p.id)
        self._render_posts_into_log(cid, self._last_posts)

    @on(Input.Submitted, "#composer")
    async def _send(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text or not self._current_channel_id:
            if not self._current_channel_id:
                self.notify("Select a channel first", severity="warning")
            return
        self._worker_send_post(self._current_channel_id, text)

    @work(exclusive=True, group="mattermost-send")
    async def _worker_send_post(self, channel_id: str, text: str) -> None:
        log = self.query_one("#log", RichLog)
        try:
            post = await self._mm.create_post(channel_id, text)
        except MattermostAPIError as e:
            self.notify(str(e), severity="error")
            return
        user = self._usernames.get(post.user_id, post.user_id[:8] if post.user_id else "?")
        if channel_id == self._last_posts_channel_id:
            self._last_posts.append(post)
        if self._post_view_filter == "all" and not self._post_filter:
            log.write(_format_post_line(post, user, highlight=False))
        else:
            self._rerender_posts_log()
