"""discord-cli — CLI entry point."""

import logging
import os
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .data import data_group
from .discord_cmds import discord_group
from ._output import (
    emit_ambient_context,
    emit_structured,
    error_payload,
    fields_option,
    full_option,
    structured_output_options,
    success_payload,
)
from .query import query_group

console = Console(stderr=True)


def _discord_user_payload(user: dict) -> dict[str, object]:
    """Normalize Discord user info for structured agent output."""
    return {
        "id": user.get("id", ""),
        "name": user.get("global_name") or user.get("username", ""),
        "username": user.get("username", ""),
        "global_name": user.get("global_name") or "",
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "mfa_enabled": bool(user.get("mfa_enabled", False)),
        "premium_type": user.get("premium_type", 0),
        "created_at": user.get("created_at", ""),
    }


@click.group(invoke_without_command=True)
@click.version_option(package_name="kabi-discord-cli")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool):
    """discord — CLI for fetching Discord chat history and searching messages."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s: %(message)s")

    # Content-first default: if no subcommand, show ambient context
    if ctx.invoked_subcommand is None:
        _show_ambient_context()
        ctx.exit(0)


def _show_ambient_context() -> None:
    """Show ambient context dashboard when running with no arguments."""
    from ..config import get_token
    from ..db import MessageDB
    from ..exceptions import NotAuthenticatedError

    as_json = os.getenv("OUTPUT", "auto").strip().lower() == "json"
    as_yaml = os.getenv("OUTPUT", "auto").strip().lower() == "yaml"
    as_toon = os.getenv("OUTPUT", "auto").strip().lower() == "toon"

    try:
        token = get_token()
    except NotAuthenticatedError:
        emit_ambient_context(
            authenticated=False,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
        )
        return

    # Get user info
    import httpx

    user_info = None
    try:
        resp = httpx.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": token},
            timeout=5.0,
        )
        if resp.status_code == 200:
            user_info = resp.json()
    except Exception:
        pass

    # Get stats from local DB
    guilds_count = 0
    channels_tracked = 0
    messages_stored = 0
    recent_messages = None

    try:
        with MessageDB() as db:
            channels = db.get_channels()
            channels_tracked = len(channels)
            messages_stored = db.count()
            guilds = set(c.get("guild_name") for c in channels if c.get("guild_name"))
            guilds_count = len(guilds)

            # Get recent messages for ambient context
            recent = db.get_latest(limit=3)
            if recent:
                recent_messages = [
                    {
                        "channel": f"#{m.get('channel_name', 'unknown')}",
                        "sender": m.get("sender_name", "Unknown"),
                        "content": (m.get("content") or "")[:100],
                        "timestamp": str(m.get("timestamp", ""))[:19],
                    }
                    for m in recent
                ]
    except Exception:
        pass

    emit_ambient_context(
        authenticated=bool(user_info),
        user=user_info,
        guilds_count=guilds_count,
        channels_tracked=channels_tracked,
        messages_stored=messages_stored,
        recent_messages=recent_messages,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
    )


@cli.command("auth")
@click.option("--save", is_flag=True, help="Save found token to .env automatically")
def auth(save: bool):
    """Extract Discord token from local browser/Discord client."""
    import httpx

    from ..auth import find_tokens, save_token_to_env

    console.print(
        "[yellow]Warning:[/yellow] discord-cli uses a Discord user token from your local "
        "session. This may violate Discord's terms or trigger account restrictions. "
        "Use it only on accounts you control and at your own risk."
    )
    console.print("[dim]Scanning for Discord tokens...[/dim]")
    results = find_tokens()

    if not results:
        console.print("[red]No tokens found.[/red]")
        console.print(
            "[dim]Make sure Discord desktop app or browser is logged in.[/dim]"
        )
        return

    console.print(f"[dim]Found {len(results)} candidate token(s), validating...[/dim]")

    # Validate each token against the API
    valid_token = None
    valid_source = None
    user_info = None

    for r in results:
        token = r["token"]
        try:
            resp = httpx.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": token},
                timeout=10.0,
            )
            if resp.status_code == 200:
                user_info = resp.json()
                valid_token = token
                valid_source = r["source"]
                break
        except Exception:
            continue

    if not valid_token or not user_info:
        console.print("[red]No valid token found. All tokens returned 401.[/red]")
        console.print("[dim]Try logging into Discord in your browser and retry.[/dim]")
        return

    masked = f"{valid_token[:8]}...{valid_token[-8:]}"
    username = user_info.get("username", "?")
    global_name = user_info.get("global_name") or username
    console.print(
        f"[green]✓[/green] Valid token from [cyan]{valid_source}[/cyan]: {masked}"
    )
    console.print(
        f"  Logged in as: [bold]{global_name}[/bold] (@{username})"
    )

    if save:
        env_path = save_token_to_env(valid_token)
        console.print(f"[green]✓[/green] Saved to {env_path}")
    else:
        console.print(
            "\n[dim]Run with --save to auto-save to .env[/dim]"
        )


@cli.command("status")
@structured_output_options
@fields_option
def status(as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None):
    """Check if Discord token is valid."""
    import httpx

    from ..config import get_token
    from ..exceptions import NotAuthenticatedError

    field_list = fields.split(",") if fields else None

    try:
        token = get_token()
    except NotAuthenticatedError as e:
        if emit_structured(
            error_payload("not_authenticated", str(e)),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to authenticate"],
        ):
            sys.exit(1)
        console.print(f"[red]✗[/red] {e}")
        sys.exit(1)

    try:
        resp = httpx.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": token},
            timeout=10.0,
        )
        if resp.status_code == 200:
            user = resp.json()
            payload = success_payload(
                {
                    "authenticated": True,
                    "user": _discord_user_payload(user),
                }
            )
            if emit_structured(
                payload,
                as_json=as_json,
                as_yaml=as_yaml,
                as_toon=as_toon,
                fields=field_list,
                help_hints=["Run 'discord whoami --yaml' for full profile"],
            ):
                sys.exit(0)
            name = user.get("global_name") or user.get("username", "?")
            console.print(f"[green]✓[/green] Authenticated as [bold]{name}[/bold] (@{user.get('username')})")
            sys.exit(0)
        else:
            if emit_structured(
                error_payload(
                    "invalid_token",
                    f"Token invalid (HTTP {resp.status_code})",
                    details={"status_code": resp.status_code},
                ),
                as_json=as_json,
                as_yaml=as_yaml,
                as_toon=as_toon,
                help_hints=["Run 'discord auth --save' to re-authenticate"],
            ):
                sys.exit(1)
            console.print(f"[red]✗[/red] Token invalid (HTTP {resp.status_code})")
            sys.exit(1)
    except Exception as e:
        if emit_structured(
            error_payload("connection_error", str(e)),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            sys.exit(1)
        console.print(f"[red]✗[/red] Connection error: {e}")
        sys.exit(1)


@cli.command("whoami")
@structured_output_options
@fields_option
@full_option
def whoami(as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """Show detailed profile of the current user."""
    import asyncio

    from ..client import get_client, get_me

    field_list = fields.split(",") if fields else None

    async def _run():
        async with get_client() as client:
            return await get_me(client)

    try:
        info = asyncio.run(_run())
    except Exception as exc:
        if emit_structured(
            error_payload("auth_error", str(exc)),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to re-authenticate"],
        ):
            raise SystemExit(1) from None
        raise click.ClickException(str(exc)) from exc

    payload = success_payload({"user": _discord_user_payload(info)})
    if emit_structured(
        payload,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        help_hints=["Run 'discord status --yaml' for quick auth check"],
    ):
        return

    premium_names = {0: "None", 1: "Nitro Classic", 2: "Nitro", 3: "Nitro Basic"}
    table = Table(title="Discord Profile", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Username", f"@{info['username']}")
    if info.get("global_name"):
        table.add_row("Display Name", info["global_name"])
    table.add_row("ID", info["id"])
    if info.get("email"):
        table.add_row("Email", info["email"])
    if info.get("phone"):
        table.add_row("Phone", info["phone"])
    table.add_row("MFA", "✓" if info.get("mfa_enabled") else "✗")
    table.add_row("Nitro", premium_names.get(info.get("premium_type", 0), "?"))
    table.add_row("Created", info.get("created_at", "?")[:10])

    console.print(table)

@cli.command("hook")
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish", "auto"]),
    default="auto",
    help="Target shell for hook installation",
)
@click.option(
    "--force",
    is_flag=True,
    help="Install hooks without prompting",
)
def hook(shell: str, force: bool):
    """Install session hook for ambient context at agent startup."""
    import json
    import platform

    if shell == "auto":
        shell = os.environ.get("SHELL", "").split("/")[-1]
        if shell not in ("bash", "zsh", "fish"):
            shell = "bash"

    # Determine hook directories
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        claude_dir = base / "Claude"
        codex_dir = base / "Codex"
        opencode_dir = base / "opencode"
    else:
        base = Path.home() / ".config"
        claude_dir = base / "claude"
        codex_dir = base / "codex"
        opencode_dir = base / "opencode"

    # The discord binary path (uv tool install puts it in ~/.local/bin)
    discord_bin = shutil.which("discord") or str(Path.home() / ".local" / "bin" / "discord")
    if not Path(discord_bin).exists():
        discord_bin = "discord"  # Fallback to PATH

    installed = []

    def should_install(path: Path) -> bool:
        """Check if we should install hook for this path."""
        if force:
            return True
        if path.exists():
            return True
        return False

    # Claude Code: SessionStart hook
    if should_install(claude_dir):
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings = claude_dir / "settings.json"
        if settings.exists():
            with open(settings) as f:
                data = json.load(f)
        else:
            data = {}
        hooks = data.setdefault("hooks", {})
        session_start = hooks.setdefault("SessionStart", [])
        # Remove existing discord hooks
        session_start[:] = [h for h in session_start if "discord" not in str(h)]
        session_start.append({
            "type": "command",
            "command": f"{discord_bin} 2>/dev/null || true",
            "description": "Discord CLI ambient context",
        })
        with open(settings, "w") as f:
            json.dump(data, f, indent=2)
        installed.append(f"Claude Code: {settings}")

    # Codex: hooks.json
    if should_install(codex_dir):
        codex_dir.mkdir(parents=True, exist_ok=True)
        hooks_file = codex_dir / "hooks.json"
        if hooks_file.exists():
            with open(hooks_file) as f:
                data = json.load(f)
        else:
            data = {"hooks": {}}
        session_start = data["hooks"].setdefault("sessionStart", [])
        session_start[:] = [h for h in session_start if "discord" not in str(h)]
        session_start.append({
            "command": discord_bin,
            "args": [],
            "description": "Discord CLI ambient context",
        })
        with open(hooks_file, "w") as f:
            json.dump(data, f, indent=2)
        installed.append(f"Codex: {hooks_file}")

    # OpenCode: plugin (managed plugin)
    if should_install(opencode_dir):
        opencode_dir.mkdir(parents=True, exist_ok=True)
        plugins_dir = opencode_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        plugin_dir = plugins_dir / "discord-cli"
        plugin_dir.mkdir(exist_ok=True)
        manifest = {
            "name": "discord-cli",
            "version": "0.1.0",
            "description": "Discord CLI ambient context",
            "hooks": {
                "sessionStart": [
                    {"command": discord_bin, "args": []}
                ]
            },
        }
        with open(plugin_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        installed.append(f"OpenCode: {plugin_dir}/manifest.json")

    if installed:
        for item in installed:
            console.print(f"[green]✓[/green] Installed: {item}")
    else:
        console.print("[yellow]No hooks installed.[/yellow]")
        console.print("Run 'discord hook --force' to install for all supported agents.")


@cli.command("update")
@click.option("--check", is_flag=True, help="Check without installing")
@click.option("--json", "json_output", is_flag=True, help="Emit update status as JSON")
def update_command(check: bool, json_output: bool) -> None:
    """Update this CLI through the package manager that owns it."""
    from ..updater import run_update

    args = (["--check"] if check else []) + (["--json"] if json_output else [])
    raise click.exceptions.Exit(
        run_update(args, application="discord", package="kabi-discord-cli")
    )
cli.add_command(update_command, "upgrade")
# Register sub-groups
cli.add_command(discord_group, "dc")

# Register top-level query commands
for name, cmd in query_group.commands.items():
    cli.add_command(cmd, name)

# Register top-level data commands
for name, cmd in data_group.commands.items():
    cli.add_command(cmd, name)