# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Commands

```bash
# Install dependencies
uv sync

# Run tests
make test

# Run the app (token auth)
uv run mattermost-tui --url https://chat.example.com --token mm_token_...

# Run the app (password auth — prompts for password)
uv run mattermost-tui --url https://chat.example.com --login-id user@example.com

# Shorthand alias
uv run mmt --url https://chat.example.com --token mm_token_...
```

## Architecture

Three-layer pipeline: **CLI → TUI → API client**

- `cli.py` — Click entry point. Loads `.env` (searched upward from CWD), validates the base
  URL, handles auth (token or password via env/prompt — no `--password` flag), then calls
  `asyncio.run()` and launches the TUI.
- `tui_app.py` — Textual app with a 3-pane layout: channel sidebar | message thread |
  composer. `ChannelOptionList` provides type-ahead channel search. `ChannelSearchModal`
  filters messages in the current channel. Keyboard bindings are platform-aware:
  `_main_hotkey()` returns `ctrl+letter` on macOS and `ctrl+shift+letter` on Windows/Linux
  to avoid terminal conflicts.
- `api/` — Async REST wrapper over Mattermost API v4 using `httpx.AsyncClient`.
  - `client.py` — `MattermostClient`: all API calls (channels, posts, users, create post,
    mark viewed)
  - `auth.py` — `login()`: `POST /api/v4/users/login`, returns `(token, user_json)`
  - `models.py` — Frozen dataclasses: `User`, `Team`, `Channel`, `Post`, each with
    `from_api()` constructor
  - `channel_labels.py` — Resolves human-readable names for DM (other user's username) and
    group channels (sorted comma-separated member list)
  - `errors.py` — `MattermostAPIError` with `status_code` and `detail`

## Configuration

Copy `.env.example` to `.env` (searched upward from CWD). Variables in `.env` override the
same names already set in the shell environment.

```text
MATTERMOST_URL=https://chat.example.com
MATTERMOST_TOKEN=mm_token_...         # token auth
MATTERMOST_LOGIN=user@example.com     # password auth
MATTERMOST_PASSWORD=...
MATTERMOST_PROXY=http://proxy:8080    # optional
MATTERMOST_POLL_INTERVAL=5            # seconds, default 5
MATTERMOST_MESSAGES_LINE_MODE=wrap    # wrap or scroll
```

CLI args override env vars. Disable SSL verification with `--no-verify-ssl`.

## Keyboard shortcuts (macOS)

| Key | Action |
| --- | --- |
| `Ctrl+E` | Reload channel list |
| `Ctrl+Y` | Reload messages |
| `Ctrl+Shift+F` | Search messages (`Ctrl+F` is the composer's word-delete) |
| `Ctrl+U` | Toggle unread filter |
| `Ctrl+O` | Channel info |
| `Ctrl+H` | Toggle wrap/scroll |
| `Ctrl+T` | Next team |
| `Ctrl+M` | Toggle channels/DMs sidebar |
| `Ctrl+R` | Toggle channel sort (alpha / unread-first) |
| `Tab` | Focus composer |
| `Enter` | Send message |

On Windows/Linux the same actions use `Ctrl+Shift+` with letters C, M, S, U, I, H, R
respectively.
