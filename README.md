# mattermost-tui

A keyboard-driven terminal UI for [Mattermost](https://mattermost.com/) built on top of the
REST API. Works with any server you can sign into — personal access token or
username/password. Built with [uv](https://docs.astral.sh/uv/),
[Click](https://click.palletsprojects.com/), [httpx](https://www.python-httpx.org/), and
[Textual](https://textual.textualize.io/).

**Latest release: [v0.2.0](https://github.com/aaronsdevera/mattermost-tui/releases/tag/v0.2.0)**
— adds channel sorting by unread count (`Ctrl+R`).

## Requirements (source only)

- [uv](https://docs.astral.sh/uv/)
- Python 3.14+ (see `.python-version`)

## Install

### From a release binary (recommended)

Download the latest release from the
[Releases](https://github.com/aaronsdevera/mattermost-tui/releases/tag/v0.2.0) page and
pick the archive for your platform:

| Platform | Archive |
| --- | --- |
| Windows x64 | `.zip` |
| Linux x64 | `.tar.gz` |
| macOS Apple Silicon | `mattermost-tui-macos-arm64.tar.gz` |
| macOS Intel x64 | `mattermost-tui-macos-amd64.tar.gz` |

Extract and install (macOS / Linux example):

```bash
gzip -d mattermost-tui-macos-arm64.tar.gz
tar -xvf mattermost-tui-macos-arm64.tar
chmod +x mattermost-tui
mv mattermost-tui /usr/local/bin/
```

Then run it directly — no Python or `uv` required:

```bash
mattermost-tui --url https://your-server.example.com --login-id user@example.com
```

### From source

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+ (see `.python-version`).

From the repository root:

```bash
uv sync
```

This installs dependencies and registers the `mattermost-tui` (and `mmt`) console scripts
into the project virtualenv.

### Build a binary locally

```bash
uv sync --group build-binary
uv run pyinstaller mattermost-tui.spec
```

GitHub Actions also builds binaries automatically — pull requests and manual runs of the
**Binary builds** workflow attach artifacts under the run's **Artifacts** section.

## Usage

`--url` is required. It must be the **server base URL** — no `/api/v4` suffix.

| Form | Example |
| --- | --- |
| Root-hosted | `https://chat.example.com` |
| Path-hosted | `https://example.com/chat` |

The examples below use the binary directly. If running from source, prefix commands with
`uv run` (e.g. `uv run mattermost-tui ...`).

### Personal access token (recommended)

Create a token in Mattermost:
**Profile → Account Settings → Security → Personal Access Tokens**.

```bash
mattermost-tui --url https://your-server.example.com --token mm_token_...
```

Prefer the `MATTERMOST_TOKEN` environment variable over `--token` so the token does not
appear in shell history or `ps` output.

### Username and password

Omit `--token` to use `POST /api/v4/users/login`. You will be prompted for your password
unless it is supplied via an environment variable. The password is **never accepted as a CLI
flag** — use `MATTERMOST_PASSWORD`, a `.env` file, or the interactive prompt.

```bash
mattermost-tui --url https://your-server.example.com --login-id user@example.com
```

### Environment variables

On startup the CLI searches for a **`.env`** file starting from your current working
directory and walking up through parent directories. Copy `.env.example` to `.env`, fill in
your values, and keep the file out of version control.

Variables in `.env` **override** the same names already exported in your shell, so a stale
empty `MATTERMOST_PASSWORD` in your environment will not block the value from `.env`.

| Variable | CLI equivalent | Purpose |
| --- | --- | --- |
| `MATTERMOST_URL` | `--url` | Server base URL |
| `MATTERMOST_TOKEN` | `--token` | Personal access token |
| `MATTERMOST_LOGIN` | `--login-id` | Username or email for password login |
| `MATTERMOST_USERNAME` | `--login-id` | Alias for `MATTERMOST_LOGIN` |
| `MATTERMOST_PASSWORD` | _(prompt only)_ | Password for password login |
| `MATTERMOST_PROXY` | `--proxy` | HTTP or SOCKS proxy URL |
| `MATTERMOST_POLL_INTERVAL` | `--poll-interval` | Seconds between checks (default: 5) |
| `MATTERMOST_MESSAGES_LINE_MODE` | `--messages-line-mode` | `wrap` or `scroll` |

Example using only environment variables:

```bash
export MATTERMOST_URL=https://your-server.example.com
export MATTERMOST_TOKEN=mm_token_...
mattermost-tui
```

### TLS and proxies

Disable TLS verification for self-signed certificates (local/lab use only):

```bash
mattermost-tui --url https://localhost:8065 --no-verify-ssl --token mm_token_...
```

Route traffic through an HTTP or SOCKS proxy:

```bash
mattermost-tui --url https://your-server.example.com \
  --proxy socks5://127.0.0.1:1080 --token mm_token_...
```

### Help

```bash
mattermost-tui --help
```

## Keyboard shortcuts

The footer bar always shows the active key for each action. Bindings differ slightly by
platform because some `Ctrl` chords are reserved by terminals or by Textual's composer
widget.

| Action | macOS | Windows / Linux |
| --- | --- | --- |
| Reload channel list | `Ctrl+E` | `Ctrl+Shift+C` |
| Reload messages | `Ctrl+Y` | `Ctrl+Shift+M` |
| Search messages | `Ctrl+Shift+F` | `Ctrl+Shift+S` |
| Toggle unread filter | `Ctrl+U` | `Ctrl+Shift+U` |
| Channel info | `Ctrl+O` | `Ctrl+Shift+I` |
| Toggle wrap / scroll | `Ctrl+H` | `Ctrl+Shift+H` |
| Next team | `Ctrl+T` | `Ctrl+T` |
| Toggle channels / DMs | `Ctrl+M` | `Ctrl+M` |
| Focus composer | `Tab` | `Tab` |
| Send message | `Enter` | `Enter` |
| Unfocus composer | `Escape` | `Escape` |
| Quit | `Ctrl+Q` | `Ctrl+Q` |

Navigation inside the channel list uses arrow keys or mouse clicks. The message thread
updates immediately when a channel is highlighted.

## Project layout

```text
mattermost_tui/
├── cli.py            — Click entry point, env loading, auth
├── tui_app.py        — Textual 3-pane UI (sidebar | thread | composer)
└── api/
    ├── client.py     — MattermostClient: all API calls
    ├── auth.py       — login() via POST /api/v4/users/login
    ├── models.py     — Frozen dataclasses (User, Team, Channel, Post)
    ├── channel_labels.py — Human-readable DM/group channel names
    └── errors.py     — MattermostAPIError
```
