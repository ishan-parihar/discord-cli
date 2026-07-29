"""Data commands — export, purge."""

import json

import click
from rich.console import Console
import yaml

from ._channels import resolve_channel_id_or_raise
from ._output import (
    build_help_hints,
    dump_structured,
    emit_error,
    emit_structured,
    fields_option,
    full_option,
    structured_output_options,
)
from ..db import MessageDB

console = Console(stderr=True)


@click.group("data", invoke_without_command=True)
def data_group():
    """Data management commands (registered at top-level)."""
    pass


@data_group.command("export")
@click.argument("channel")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "json", "yaml", "toon"]), default="text")
@click.option("-o", "--output", "output_file", help="Output file path")
@click.option("--hours", type=int, help="Only export last N hours")
@structured_output_options
@fields_option
@full_option
def export(
    channel: str,
    fmt: str,
    output_file: str | None,
    hours: int | None,
    as_json: bool,
    as_yaml: bool,
    as_toon: bool,
    fields: str | None,
    full: bool,
):
    """Export messages from CHANNEL to text or JSON."""
    field_list = fields.split(",") if fields else None

    with MessageDB() as db:
        channel_id = resolve_channel_id_or_raise(db, channel)
        msgs = db.get_recent(channel_id=channel_id, hours=hours, limit=100000)

    if not msgs:
        if emit_error(
            "no_messages",
            f"No messages found for '{channel}'.",
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            help_hints=["Run 'discord dc channels <guild_id>' to list available channels"],
        ):
            raise SystemExit(1) from None
        console.print(f"[yellow]No messages found for '{channel}'.[/yellow]")
        return

    # Apply field filter
    if field_list:
        msgs = [{k: v for k, v in msg.items() if k in field_list} for msg in msgs]

    # Apply truncation for non-full output
    if not full:
        msgs = [
            {**msg, "content": msg.get("content", "")[:300] + ("..." if len(msg.get("content", "")) > 300 else "")}
            for msg in msgs
        ]

    # For structured output, use emit_structured
    if as_json or as_yaml or as_toon:
        if emit_structured(
            msgs,
            as_json=as_json,
            as_yaml=as_yaml,
            as_toon=as_toon,
            fields=field_list,
            total=len(msgs),
            help_hints=build_help_hints("export", {"channel": channel}),
            command_name="export",
        ):
            return

    # File output for structured formats
    if output_file:
        if fmt in ("json", "yaml", "toon"):
            content = dump_structured(msgs, fmt=fmt)
        else:
            lines = []
            for msg in msgs:
                ts = (msg.get("timestamp") or "")[:19]
                sender = msg.get("sender_name") or "Unknown"
                text = msg.get("content") or ""
                lines.append(f"[{ts}] {sender}: {text}")
            content = "\n".join(lines)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]✓[/green] Exported {len(msgs)} messages to {output_file}")
        return

    # Text output to console
    if fmt == "json":
        content = json.dumps(msgs, ensure_ascii=False, indent=2, default=str)
    elif fmt == "yaml":
        content = yaml.safe_dump(msgs, allow_unicode=True, sort_keys=False, default_flow_style=False)
    elif fmt == "toon":
        content = dump_structured(msgs, fmt="toon")
    else:
        lines = []
        for msg in msgs:
            ts = (msg.get("timestamp") or "")[:19]
            sender = msg.get("sender_name") or "Unknown"
            text = msg.get("content") or ""
            lines.append(f"[{ts}] {sender}: {text}")
        content = "\n".join(lines)

    console.print(content)


@data_group.command("purge")
@click.argument("channel")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def purge(channel: str, yes: bool):
    """Delete all stored messages for CHANNEL."""
    with MessageDB() as db:
        channel_id = resolve_channel_id_or_raise(db, channel)
        if not yes:
            count = db.count(channel_id)
            if not click.confirm(f"Delete {count} messages from channel {channel_id}?"):
                return

        deleted = db.delete_channel(channel_id)

    console.print(f"[green]✓[/green] Deleted {deleted} messages")