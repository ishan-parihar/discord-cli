"""Discord subcommands — guilds, channels, history, sync, sync-all, search, members."""

import asyncio
from contextlib import suppress

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..client import (
    fetch_messages,
    get_client,
    get_guild_info,
    list_channels,
    list_guilds,
    list_members,
    resolve_guild_id,
    search_guild_messages,
)
from ..db import MessageDB
from ..exceptions import NotAuthenticatedError
from ._output import (
    build_help_hints,
    emit_error,
    emit_structured,
    fields_option,
    full_option,
    structured_output_options,
    truncate_content,
)

console = Console(stderr=True)


@click.group("dc")
def discord_group():
    """Discord operations — list servers, fetch history, sync."""
    pass


async def _fetch_channel_context(client, channel_id: str) -> dict[str, str | None]:
    """Resolve channel and guild names for a channel."""
    channel_name = None
    guild_name = None
    guild_id = None

    with suppress(Exception):
        response = await client.get(f"/channels/{channel_id}")
        if response.status_code == 200:
            data = response.json()
            channel_name = data.get("name")
            guild_id = data.get("guild_id")
            if guild_id:
                guild = await get_guild_info(client, guild_id)
                if guild:
                    guild_name = guild.get("name")

    return {
        "channel_name": channel_name,
        "guild_name": guild_name,
        "guild_id": guild_id,
    }


def _annotate_messages(messages: list[dict], context: dict[str, str | None]) -> list[dict]:
    """Attach channel and guild metadata to fetched messages."""
    for msg in messages:
        msg["guild_id"] = context.get("guild_id")
        msg["guild_name"] = context.get("guild_name")
        msg["channel_name"] = context.get("channel_name")
    return messages


def _format_message(msg: dict, *, include_channel: bool = False, full: bool = False) -> str:
    """Format a single message for console output."""
    ts = str(msg.get("timestamp", ""))[:19]
    sender = msg.get("sender_name") or "Unknown"
    content = msg.get("content") or ""
    content = content.replace("\n", " ")
    if not full:
        content = truncate_content(content, 300)
    channel_name = msg.get("channel_name") or ""
    prefix = f"[cyan]#{channel_name}[/cyan] | " if include_channel and channel_name else ""
    return f"[dim]{ts}[/dim] {prefix}[bold]{sender}[/bold]: {content}"


async def _tail_fetch_once(
    client,
    db: MessageDB,
    channel_id: str,
    *,
    after: str | None,
    fetch_limit: int,
    context: dict[str, str | None],
    store: bool,
) -> tuple[list[dict], str | None, int]:
    """Fetch a single incremental batch for tail mode."""
    messages = await fetch_messages(client, channel_id, limit=fetch_limit, after=after)
    if not messages:
        return [], after, 0

    _annotate_messages(messages, context)
    inserted = db.insert_batch(messages) if store else 0
    return messages, messages[-1]["msg_id"], inserted


def _minimal_guild(g: dict) -> dict:
    return {"id": g["id"], "name": g["name"], "owner": g.get("owner", False)}


def _minimal_channel(ch: dict) -> dict:
    return {"id": ch["id"], "name": ch["name"], "topic": ch.get("topic") or ""}


def _minimal_member(m: dict) -> dict:
    return {
        "id": m["id"],
        "username": m.get("username", ""),
        "display_name": m.get("global_name") or "",
        "nick": m.get("nick") or "",
        "bot": m.get("bot", False),
    }


def _minimal_message(msg: dict, full: bool = False) -> dict:
    content = msg.get("content") or ""
    if not full:
        content = truncate_content(content, 300)
    return {
        "msg_id": msg.get("msg_id") or msg.get("id", ""),
        "sender_name": msg.get("sender_name") or "Unknown",
        "content": content,
        "timestamp": str(msg.get("timestamp", ""))[:19],
    }


def _run_with_auth_error_handling(coro, as_json, as_yaml, as_toon, help_hints=None):
    """Run async coroutine with NotAuthenticatedError handling."""
    try:
        return asyncio.run(coro)
    except NotAuthenticatedError as e:
        if emit_error(
            "not_authenticated",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=help_hints or ["Run 'discord auth --save' to authenticate"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1) from None
    except Exception as e:
        if emit_error(
            "connection_error",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise SystemExit(1) from None


@discord_group.command("guilds")
@structured_output_options
@fields_option
@full_option
def dc_guilds(as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """List joined Discord servers."""

    async def _run():
        async with get_client() as client:
            return await list_guilds(client)

    guilds = _run_with_auth_error_handling(_run(), as_json, as_yaml, as_toon)
    field_list = fields.split(",") if fields else None

    if not guilds:
        console.print("guilds: 0 servers found")
        console.print("help: Run 'discord auth --save' to authenticate")
        return

    minimal = [_minimal_guild(g) for g in guilds]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=len(guilds),
        help_hints=build_help_hints("dc guilds"),
        command_name="dc guilds",
    ):
        return

    table = Table(title="Discord Servers")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Owner", justify="center")

    for g in guilds:
        table.add_row(g["id"], g["name"], "✓" if g["owner"] else "")

    console.print(table)
    console.print(f"\nTotal: {len(guilds)} servers")


@discord_group.command("channels")
@click.argument("guild")
@structured_output_options
@fields_option
@full_option
def dc_channels(guild: str, as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """List text channels in a GUILD (server ID or name)."""
    field_list = fields.split(",") if fields else None

    async def _run():
        async with get_client() as client:
            guild_id = await resolve_guild_id(client, guild)
            if not guild_id:
                return None, f"Guild '{guild}' not found."
            return await list_channels(client, guild_id), None

    try:
        channels, error = asyncio.run(_run())
    except NotAuthenticatedError as e:
        if emit_error(
            "not_authenticated",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to authenticate"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1) from None
    except Exception as e:
        if emit_error(
            "connection_error",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise SystemExit(1) from None

    if error:
        if emit_error(
            "guild_not_found",
            error,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord dc guilds --yaml' to list available servers"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]{error}[/red]")
        return

    if not channels:
        if emit_structured(
            [],
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            fields=field_list,
            total=0,
            help_hints=build_help_hints("dc channels", {"guild": guild}),
            command_name="dc channels",
        ):
            return
        console.print(f"channels: 0 text channels found in guild '{guild}'")
        console.print("help: Run 'discord dc guilds --yaml' to list available servers")
        return

    minimal = [_minimal_channel(ch) for ch in channels]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=len(channels),
        help_hints=build_help_hints("dc channels", {"guild": guild}),
        command_name="dc channels",
    ):
        return

    table = Table(title="Text Channels")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Topic", max_width=50)

    for ch in channels:
        table.add_row(ch["id"], f"#{ch['name']}", (ch.get("topic") or "")[:50])

    console.print(table)
    console.print(f"\nTotal: {len(channels)} text channels")


@discord_group.command("history")
@click.argument("channel")
@click.option("-n", "--limit", default=1000, help="Max messages to fetch")
@click.option("--guild-name", help="Guild name to store with messages")
@click.option("--channel-name", help="Channel name to store with messages")
@structured_output_options
@fields_option
@full_option
def dc_history(
    channel: str,
    limit: int,
    guild_name: str | None,
    channel_name: str | None,
    as_json: bool,
    as_yaml: bool,
    as_toon: bool,
    fields: str | None,
    full: bool,
):
    """Fetch historical messages from CHANNEL (channel ID)."""
    field_list = fields.split(",") if fields else None

    async def _run():
        with MessageDB() as db:
            async with get_client() as client:
                context = await _fetch_channel_context(client, channel)
                if channel_name:
                    context["channel_name"] = channel_name
                elif context.get("channel_name") is None:
                    context["channel_name"] = channel

                if guild_name:
                    context["guild_name"] = guild_name

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        f"Fetching messages from {context.get('channel_name') or channel}...",
                        total=None,
                    )
                    messages = await fetch_messages(client, channel, limit=limit)
                    progress.update(task, description=f"Fetched {len(messages)} messages")

                _annotate_messages(messages, context)

                inserted = db.insert_batch(messages)
                return messages, inserted, len(messages)

    messages, inserted, total = _run_with_auth_error_handling(_run(), as_json, as_yaml, as_toon)
    minimal = [_minimal_message(m, full) for m in messages]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=total,
        help_hints=build_help_hints("dc history"),
        command_name="dc history",
    ):
        return

    if not messages:
        console.print(f"messages: 0 messages fetched from channel '{channel}'")
        console.print("help: Run 'discord dc channels <guild_id>' to list available channels")
        return

    console.print(f"\n[green]✓[/green] Fetched {len(messages)} messages, stored {inserted} new")


@discord_group.command("sync")
@click.argument("channel")
@click.option("-n", "--limit", default=5000, help="Max messages per sync")
@structured_output_options
@fields_option
@full_option
def dc_sync(channel: str, limit: int, as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """Incremental sync — fetch only new messages from CHANNEL."""
    field_list = fields.split(",") if fields else None

    async def _run():
        with MessageDB() as db:
            last_id = db.get_last_msg_id(channel)
            if last_id:
                console.print(f"Syncing from msg_id > {last_id}...")

            async with get_client() as client:
                context = await _fetch_channel_context(client, channel)

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task_id = progress.add_task(
                        f"Syncing {context.get('channel_name') or channel}...",
                        total=None,
                    )
                    messages = await fetch_messages(client, channel, limit=limit, after=last_id)
                    progress.update(task_id, description=f"Fetched {len(messages)} new messages")

                _annotate_messages(messages, context)

                inserted = db.insert_batch(messages)
                return messages, inserted, len(messages)

    messages, inserted, total = _run_with_auth_error_handling(_run(), as_json, as_yaml, as_toon)
    minimal = [_minimal_message(m, full) for m in messages]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=total,
        help_hints=build_help_hints("dc sync"),
        command_name="dc sync",
    ):
        return

    if not messages:
        console.print(f"messages: 0 new messages synced from channel '{channel}'")
        return

    console.print(f"\n[green]✓[/green] Synced {len(messages)} messages, stored {inserted} new")


@discord_group.command("tail")
@click.argument("channel")
@click.option("-n", "--limit", default=20, help="Show last N messages before following")
@click.option("--interval", default=5.0, type=click.FloatRange(min=0.5), help="Polling interval in seconds")
@click.option("--poll-limit", default=100, type=click.IntRange(1, 100), help="Max new messages fetched per poll")
@click.option("--store/--no-store", default=True, help="Store tailed messages in local SQLite")
@click.option("--once", is_flag=True, help="Show initial snapshot and exit")
def dc_tail(channel: str, limit: int, interval: float, poll_limit: int, store: bool, once: bool):
    """Tail a channel and follow new messages."""

    async def _run():
        with MessageDB() as db:
            async with get_client() as client:
                context = await _fetch_channel_context(client, channel)
                channel_label = context.get("channel_name") or channel
                guild_label = context.get("guild_name")
                scope = f"{guild_label} > #{channel_label}" if guild_label else f"#{channel_label}"
                last_id = db.get_last_msg_id(channel)

                if limit > 0:
                    initial = await fetch_messages(client, channel, limit=limit)
                    _annotate_messages(initial, context)
                    if store and initial:
                        db.insert_batch(initial)
                    for msg in initial:
                        console.print(_format_message(msg))
                    if initial:
                        last_id = initial[-1]["msg_id"]
                elif last_id is None:
                    latest = await fetch_messages(client, channel, limit=1)
                    if latest:
                        _annotate_messages(latest, context)
                        if store:
                            db.insert_batch(latest)
                        last_id = latest[-1]["msg_id"]

                if once:
                    return

                console.print(
                    f"\n[green]Watching[/green] {scope} "
                    f"[dim](poll every {interval:g}s, Ctrl-C to stop)[/dim]"
                )

                while True:
                    messages, last_id, inserted = await _tail_fetch_once(
                        client,
                        db,
                        channel,
                        after=last_id,
                        fetch_limit=poll_limit,
                        context=context,
                        store=store,
                    )
                    for msg in messages:
                        console.print(_format_message(msg))
                    if messages and store:
                        console.print(f"[dim]+{inserted} stored[/dim]")
                    await asyncio.sleep(interval)

    try:
        _run_with_auth_error_handling(_run(), False, False, False)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped tailing.[/yellow]")


@discord_group.command("sync-all")
@click.option("-n", "--limit", default=5000, help="Max messages per channel")
def dc_sync_all(limit: int):
    """Sync ALL channels in the database."""

    async def _run():
        with MessageDB() as db:
            async with get_client() as client:
                guilds = await list_guilds(client)
                channels: list[dict[str, str | None]] = []
                for guild in guilds:
                    guild_channels = await list_channels(client, guild["id"])
                    for channel in guild_channels:
                        channels.append(
                            {
                                "guild_id": guild["id"],
                                "guild_name": guild["name"],
                                "channel_id": channel["id"],
                                "channel_name": channel["name"],
                            }
                        )

                if not channels:
                    console.print("[yellow]No text channels found for this account.[/yellow]")
                    return {}

                console.print(
                    f"Discovered {len(channels)} channels across {len(guilds)} guilds. Syncing..."
                )

                results: dict[str, int] = {}
                for ch in channels:
                    ch_id = ch["channel_id"]
                    ch_name = ch.get("channel_name") or ch_id
                    last_id = db.get_last_msg_id(ch_id)
                    try:
                        messages = await fetch_messages(client, ch_id, limit=limit, after=last_id)
                        for msg in messages:
                            msg["guild_name"] = ch.get("guild_name")
                            msg["channel_name"] = ch.get("channel_name")
                        inserted = db.insert_batch(messages)
                        results[ch_name] = inserted
                        if inserted > 0:
                            console.print(f"  [green]✓[/green] {ch_name}: +{inserted}")
                        else:
                            console.print(f"  [dim]✓ {ch_name}: no new messages[/dim]")
                    except Exception as e:
                        console.print(f"  [red]✗ {ch_name}: {e}[/red]")
                        results[ch_name] = 0
                return results

    try:
        results = _run_with_auth_error_handling(_run(), False, False, False)
    except SystemExit:
        raise

    total_new = sum(results.values())
    console.print(f"\n[green]✓[/green] Synced {total_new} new messages across {len(results)} channels")


@discord_group.command("search")
@click.argument("guild")
@click.argument("keyword")
@click.option("-c", "--channel", help="Filter by channel ID")
@click.option("-n", "--limit", default=25, help="Max results")
@structured_output_options
@fields_option
@full_option
def dc_search(
    guild: str,
    keyword: str,
    channel: str | None,
    limit: int,
    as_json: bool,
    as_yaml: bool,
    as_toon: bool,
    fields: str | None,
    full: bool,
):
    """Search messages in a GUILD by KEYWORD (Discord native search)."""
    field_list = fields.split(",") if fields else None

    async def _run():
        async with get_client() as client:
            guild_id = await resolve_guild_id(client, guild)
            if not guild_id:
                return None, f"Guild '{guild}' not found."
            return await search_guild_messages(client, guild_id, keyword, channel_id=channel, limit=limit), None

    try:
        results, error = asyncio.run(_run())
    except NotAuthenticatedError as e:
        if emit_error(
            "not_authenticated",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to authenticate"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1) from None
    except Exception as e:
        if emit_error(
            "connection_error",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise SystemExit(1) from None

    if error:
        if emit_error(
            "guild_not_found",
            error,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord dc guilds --yaml' to list available servers"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]{error}[/red]")
        return

    if not results:
        if emit_structured(
            [],
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            fields=field_list,
            total=0,
            help_hints=build_help_hints("dc search"),
            command_name="dc search",
        ):
            return
        console.print("[yellow]No messages found.[/yellow]")
        return

    minimal = [_minimal_message(m, full) for m in results]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=len(results),
        help_hints=build_help_hints("dc search"),
        command_name="dc search",
    ):
        return

    for msg in results:
        ts = str(msg.get("timestamp", ""))[:19]
        sender = msg.get("sender_name") or "Unknown"
        content = (msg.get("content") or "")[:200]
        console.print(f"[dim]{ts}[/dim] [bold]{sender}[/bold]: {content}")

    console.print(f"\n[dim]Found {len(results)} messages[/dim]")


@discord_group.command("members")
@click.argument("guild")
@click.option("-n", "--max", "limit", default=50, help="Max members to list")
@structured_output_options
@fields_option
@full_option
def dc_members(guild: str, limit: int, as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """List members of a GUILD (server)."""
    field_list = fields.split(",") if fields else None

    async def _run():
        async with get_client() as client:
            guild_id = await resolve_guild_id(client, guild)
            if not guild_id:
                return None, f"Guild '{guild}' not found."
            return await list_members(client, guild_id, limit=limit), None

    try:
        members, error = asyncio.run(_run())
    except NotAuthenticatedError as e:
        if emit_error(
            "not_authenticated",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to authenticate"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1) from None
    except Exception as e:
        if emit_error(
            "connection_error",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise SystemExit(1) from None

    if error:
        if emit_error(
            "guild_not_found",
            error,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord dc guilds --yaml' to list available servers"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]{error}[/red]")
        return

    if not members:
        if emit_structured(
            [],
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            fields=field_list,
            total=0,
            help_hints=build_help_hints("dc members", {"guild": guild}),
            command_name="dc members",
        ):
            return
        console.print("[yellow]No members found (may require Privileged Intents).[/yellow]")
        return

    minimal = [_minimal_member(m) for m in members]

    if emit_structured(
        minimal,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        total=len(members),
        help_hints=build_help_hints("dc members", {"guild": guild}),
        command_name="dc members",
    ):
        return

    table = Table(title=f"Members ({len(members)})")
    table.add_column("ID", style="dim")
    table.add_column("Username", style="bold")
    table.add_column("Display", style="cyan")
    table.add_column("Nick", style="green")
    table.add_column("Bot", justify="center")

    for m in members:
        display = m.get("global_name") or ""
        table.add_row(
            m["id"],
            f"@{m['username']}" if m.get("username") else "—",
            display,
            m.get("nick") or "",
            "🤖" if m.get("bot") else "",
        )

    console.print(table)


@discord_group.command("info")
@click.argument("guild")
@structured_output_options
@fields_option
@full_option
def dc_info(guild: str, as_json: bool, as_yaml: bool, as_toon: bool, fields: str | None, full: bool):
    """Show detailed info about a GUILD (server)."""
    field_list = fields.split(",") if fields else None

    async def _run():
        async with get_client() as client:
            guild_id = await resolve_guild_id(client, guild)
            if not guild_id:
                return None, f"Could not find guild: {guild}"
            return await get_guild_info(client, guild_id), None

    try:
        info, error = asyncio.run(_run())
    except NotAuthenticatedError as e:
        if emit_error(
            "not_authenticated",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord auth --save' to authenticate"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(1) from None
    except Exception as e:
        if emit_error(
            "connection_error",
            str(e),
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Check your internet connection"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise SystemExit(1) from None

    if error:
        if emit_error(
            "guild_not_found",
            error,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord dc guilds --yaml' to list available servers"],
        ):
            raise SystemExit(1) from None
        console.print(f"[red]{error}[/red]")
        return

    if not info:
        console.print(f"[red]Could not find guild: {guild}[/red]")
        return

    if emit_structured(
        info,
        as_json=as_json,
        as_yaml=as_yaml,
        as_toon=as_toon,
        fields=field_list,
        help_hints=build_help_hints("dc info", {"guild": guild}),
        command_name="dc info",
    ):
        return

    table = Table(title="Guild Info", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    for k, v in info.items():
        table.add_row(k, str(v) if v is not None else "—")

    console.print(table)