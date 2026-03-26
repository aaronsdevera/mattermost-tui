"""Click CLI entry points for Mattermost TUI."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

import click
from dotenv import find_dotenv, load_dotenv

from mattermost_tui.api.auth import login
from mattermost_tui.api.client import MattermostClient
from mattermost_tui.tui_app import MattermostTui, MessageLineMode

# Installed wheels place this module under site-packages; __file__ is not the git root.
# Walk upward from the process cwd so `uv run mmt` from the repo finds ./.env.
# override=True: repo .env wins over stale exports (e.g. empty MATTERMOST_PASSWORD in shell).
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path, override=True)


def _stripped(value: str | None) -> str | None:
    if value is None:
        return None
    t = value.strip()
    return t or None


def _validate_base_url(url: str) -> None:
    """Reject malformed URLs; warn when using cleartext HTTP against non-loopback hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise click.BadParameter("URL must start with http:// or https://", param_hint="--url")
    if not parsed.netloc:
        raise click.BadParameter("URL must include a host (e.g. https://chat.example.com)", param_hint="--url")
    if parsed.scheme != "http":
        return
    host = (parsed.hostname or "").lower()
    loopback = host in ("localhost", "127.0.0.1", "::1")
    if not loopback:
        click.secho(
            "Warning: HTTP sends credentials and message content in cleartext over the network. Prefer HTTPS.",
            fg="yellow",
            err=True,
        )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="mattermost-tui")
@click.option(
    "--url",
    envvar="MATTERMOST_URL",
    required=True,
    help="Mattermost server base URL (e.g. https://chat.example.com).",
)
@click.option(
    "--token",
    envvar="MATTERMOST_TOKEN",
    default=None,
    help=(
        "Personal access token (skips username/password login). "
        "Prefer MATTERMOST_TOKEN in the environment so the token is not visible in process listings."
    ),
)
@click.option(
    "--login-id",
    envvar=["MATTERMOST_LOGIN", "MATTERMOST_USERNAME"],
    default=None,
    help="Username or email for password login (if --token is not set).",
)
@click.option(
    "--no-verify-ssl",
    is_flag=True,
    default=False,
    help="Disable TLS certificate verification (local/dev only).",
)
@click.option(
    "--proxy",
    envvar="MATTERMOST_PROXY",
    default=None,
    help=(
        "HTTP or SOCKS proxy URL for all API traffic (e.g. http://host:8080, "
        "socks5://127.0.0.1:1080). When unset, HTTP(S)_PROXY / ALL_PROXY are "
        "used if defined (httpx trust_env)."
    ),
)
@click.option(
    "--poll-interval",
    type=float,
    default=5.0,
    show_default=True,
    envvar="MATTERMOST_POLL_INTERVAL",
    help=(
        "Seconds between checks for new posts in the open channel (0 disables). "
        "New messages are highlighted in the thread."
    ),
)
@click.option(
    "--messages-line-mode",
    type=click.Choice(["wrap", "scroll"], case_sensitive=False),
    default="wrap",
    show_default=True,
    envvar="MATTERMOST_MESSAGES_LINE_MODE",
    help=(
        "wrap: break long message lines at the pane edge. "
        "scroll: one line per post with horizontal scroll to read the tail."
    ),
)
def main(
    url: str,
    token: str | None,
    login_id: str | None,
    no_verify_ssl: bool,
    proxy: str | None,
    poll_interval: float,
    messages_line_mode: str,
) -> None:
    """Browse channels and send messages in the terminal."""
    url = (url or "").strip()
    _validate_base_url(url)
    token = _stripped(token)
    login_id = _stripped(login_id)
    password = _stripped(os.environ.get("MATTERMOST_PASSWORD"))
    verify = not no_verify_ssl
    proxy_url = _stripped(proxy)

    async def resolve_token() -> str:
        if token:
            return token
        lid = (login_id or click.prompt("Login ID (username or email)")).strip()
        pw = (password or click.prompt("Password", hide_input=True)).strip()
        t, _user = await login(url, lid, pw, verify=verify, proxy=proxy_url)
        return t

    access_token = asyncio.run(resolve_token())
    client = MattermostClient(url, access_token, verify=verify, proxy=proxy_url)
    poll_sec = 0.0 if poll_interval <= 0 else poll_interval

    msg_line_mode: MessageLineMode = (
        "scroll" if messages_line_mode.lower() == "scroll" else "wrap"
    )

    async def run_app() -> None:
        app = MattermostTui(
            client,
            poll_interval=poll_sec,
            message_line_mode=msg_line_mode,
        )
        try:
            await app.run_async()
        finally:
            await client.aclose()

    asyncio.run(run_app())


if __name__ == "__main__":
    main()
