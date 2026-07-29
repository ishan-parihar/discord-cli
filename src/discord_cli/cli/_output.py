"""Shared structured output helpers for discord-cli — AXI-compliant."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

import click
import yaml

_OUTPUT_ENV = "OUTPUT"
_SCHEMA_VERSION = "1"
_DEFAULT_TRUNCATE_LEN = 200
_DEFAULT_LIST_FIELDS = {
    "guilds": ["id", "name", "owner"],
    "channels": ["id", "name", "topic"],
    "members": ["id", "username", "display_name", "nick", "bot"],
    "messages": ["msg_id", "sender_name", "content", "timestamp"],
    "search_results": ["msg_id", "sender_name", "content", "timestamp"],
    "stats": ["channel_name", "guild_name", "msg_count", "last_msg"],
    "top_senders": ["sender_name", "msg_count", "last_msg"],
    "today": ["channel", "msg_count", "messages"],
}

_TOON_FIELD_SEP = ","


def default_structured_format(*, as_json: bool, as_yaml: bool, as_toon: bool) -> str | None:
    """Resolve explicit flags first, then env override, then TTY default."""
    if sum([as_json, as_yaml, as_toon]) > 1:
        raise click.UsageError("Use only one of --json, --yaml, or --toon.")
    if as_yaml:
        return "yaml"
    if as_json:
        return "json"
    if as_toon:
        return "toon"

    output_mode = os.getenv(_OUTPUT_ENV, "auto").strip().lower()
    if output_mode == "yaml":
        return "yaml"
    if output_mode == "json":
        return "json"
    if output_mode == "toon":
        return "toon"
    if output_mode == "rich":
        return None

    if not sys.stdout.isatty():
        return "yaml"
    return None


def structured_output_options(command: Callable) -> Callable:
    """Add --json/--yaml/--toon options to a Click command."""
    command = click.option("--toon", "as_toon", is_flag=True, help="Output as TOON (Token-Oriented Object Notation)")(command)
    command = click.option("--yaml", "as_yaml", is_flag=True, help="Output as YAML")(command)
    command = click.option("--json", "as_json", is_flag=True, help="Output as JSON")(command)
    return command


def fields_option(command: Callable) -> Callable:
    """Add --fields option to select output fields."""
    return click.option(
        "--fields",
        "fields",
        default=None,
        help="Comma-separated list of fields to include (e.g., 'id,name,topic')",
    )(command)


def full_option(command: Callable) -> Callable:
    """Add --full option to show complete content without truncation."""
    return click.option("--full", "full", is_flag=True, help="Show full content without truncation")(command)


def dump_structured(data: Any, *, fmt: str) -> str:
    """Serialize data to JSON, YAML, or TOON text."""
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if fmt == "yaml":
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    if fmt == "toon":
        return dump_toon(data)
    raise ValueError(f"Unsupported structured format: {fmt}")


def dump_toon(data: Any, *, indent: int = 0) -> str:
    """Serialize data to TOON format."""
    lines: list[str] = []
    _toon_encode(data, lines, indent)
    return "\n".join(lines)


def _toon_encode(value: Any, lines: list[str], indent: int) -> None:
    """Recursively encode value to TOON lines."""
    prefix = "  " * indent
    if value is None:
        lines.append(f"{prefix}null")
    elif isinstance(value, bool):
        lines.append(f"{prefix}{str(value).lower()}")
    elif isinstance(value, (int, float)):
        lines.append(f"{prefix}{value}")
    elif isinstance(value, str):
        # Escape quotes and backslashes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{prefix}"{escaped}"')
    elif isinstance(value, list):
        if not value:
            lines.append(f"{prefix}[]")
        else:
            for i, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}[{i}]")
                    _toon_encode(item, lines, indent + 1)
                else:
                    escaped = str(item).replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{prefix}[{i}] "{escaped}"')
    elif isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}{{}}")
        else:
            for key, val in value.items():
                if isinstance(val, (dict, list)):
                    lines.append(f"{prefix}{key}{{")
                    _toon_encode(val, lines, indent + 1)
                    lines.append(f"{prefix}}}")
                else:
                    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{prefix}{key}: "{escaped}"')
    else:
        lines.append(f"{prefix}{value}")


def emit_structured(
    data: Any,
    *,
    as_json: bool,
    as_yaml: bool,
    as_toon: bool,
    fields: list[str] | None = None,
    full: bool = False,
    total: int | None = None,
    help_hints: list[str] | None = None,
    command_name: str | None = None,
) -> bool:
    """Emit structured output and return True when a structured format was used."""
    fmt = default_structured_format(as_json=as_json, as_yaml=as_yaml, as_toon=as_toon)
    if not fmt:
        return False

    # Don't double-wrap error payloads (they already have ok: false)
    if isinstance(data, dict) and data.get("ok") is False and "error" in data:
        # Error payload - emit directly
        if fields:
            # Can't easily filter error fields, just emit as-is
            pass
        click.echo(dump_structured(data, fmt=fmt))
        return True

    # Apply field selection if requested
    if fields:
        data = _filter_fields(data, fields)

    # Build envelope with metadata
    envelope = _build_envelope(data, total=total, help_hints=help_hints, command_name=command_name)

    click.echo(dump_structured(envelope, fmt=fmt))
    return True


def _filter_fields(data: Any, fields: list[str]) -> Any:
    """Filter data to only include specified fields."""
    if isinstance(data, list):
        return [_filter_fields(item, fields) for item in data]
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    return data


def _build_envelope(
    data: Any,
    *,
    total: int | None = None,
    help_hints: list[str] | None = None,
    command_name: str | None = None,
) -> dict[str, Any]:
    """Build the standard output envelope with metadata."""
    envelope: dict[str, Any] = {"ok": True, "schema_version": _SCHEMA_VERSION}

    # Add data - if it's already a dict with data key, unwrap
    if isinstance(data, dict) and "data" in data and "ok" in data:
        envelope["data"] = data["data"]
    else:
        envelope["data"] = data

    # Add count info
    if total is not None:
        envelope["count"] = _count_items(data)
        envelope["total"] = total

    # Add help hints
    if help_hints:
        envelope["help"] = help_hints

    # Add command reference
    if command_name:
        envelope["command"] = command_name

    return envelope


def _count_items(data: Any) -> int:
    """Count items in data."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # If it's a dict with a 'messages' list (like today command), count those
        if "messages" in data and isinstance(data["messages"], list):
            return len(data["messages"])
        return 1
    return 0


def success_payload(data: Any) -> dict[str, Any]:
    """Wrap structured success data in the shared agent schema."""
    return {"ok": True, "schema_version": _SCHEMA_VERSION, "data": data}


def error_payload(code: str, message: str, *, details: Any | None = None) -> dict[str, Any]:
    """Wrap structured error data in the shared agent schema."""
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"ok": False, "schema_version": _SCHEMA_VERSION, "error": error}


def _normalize_success_payload(data: Any) -> Any:
    """Wrap plain structured data in the shared agent success schema."""
    if isinstance(data, dict) and data.get("schema_version") == _SCHEMA_VERSION and "ok" in data:
        return data
    return success_payload(data)


def emit_error(
    code: str,
    message: str,
    *,
    as_json: bool | None = None,
    as_yaml: bool | None = None,
    as_toon: bool | None = None,
    details: Any | None = None,
    help_hints: list[str] | None = None,
) -> bool:
    """Emit a structured error when the active output mode is machine-readable."""
    if as_json is None or as_yaml is None or as_toon is None:
        ctx = click.get_current_context(silent=True)
        params = ctx.params if ctx is not None else {}
        as_json = bool(params.get("as_json", False)) if as_json is None else as_json
        as_yaml = bool(params.get("as_yaml", False)) if as_yaml is None else as_yaml
        as_toon = bool(params.get("as_toon", False)) if as_toon is None else as_toon

    fmt = default_structured_format(as_json=bool(as_json), as_yaml=bool(as_yaml), as_toon=bool(as_toon))
    if fmt is None:
        return False

    error = error_payload(code, message, details=details)
    if help_hints:
        error["help"] = help_hints
    click.echo(dump_structured(error, fmt=fmt))
    return True


def truncate_content(text: str, max_len: int = _DEFAULT_TRUNCATE_LEN) -> str:
    """Truncate text to max_len chars with indicator."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f" ... (truncated, {len(text)} chars total)"


def get_default_fields(command_type: str) -> list[str]:
    """Get default field list for a command type."""
    return _DEFAULT_LIST_FIELDS.get(command_type, [])


def build_help_hints(command: str, context: dict[str, Any] | None = None) -> list[str]:
    """Build contextual help hints based on command and context."""
    hints: list[str] = []

    if command == "dc guilds":
        hints.append("Run 'discord dc channels <guild_id>' to list channels in a server")
    elif command == "dc channels":
        guild = context.get("guild") if context else None
        if guild:
            hints.append("Run 'discord dc history <channel_id>' to fetch messages from a channel")
    elif command in ("dc history", "dc sync"):
        hints.append("Run 'discord dc sync <channel_id>' for incremental sync")
        hints.append("Run 'discord search \"term\" -c <channel>' to search messages")
    elif command in ("dc search", "search"):
        hints.append("Run 'discord recent -c <channel>' to see recent messages")
        hints.append("Run 'discord export <channel> -f json -o out.json' to export")
    elif command in ("dc recent", "recent"):
        hints.append("Run 'discord search \"term\" -c <channel>' to search in a channel")
    elif command == "today":
        hints.append("Run 'discord timeline --by hour' for hourly activity")
        hints.append("Run 'discord top --hours 24' for most active senders today")
    elif command == "stats":
        hints.append("Run 'discord dc channels <guild_id>' to see channels")
    elif command == "top":
        hints.append("Run 'discord recent -c <channel>' to see messages from top senders")
    elif command == "timeline":
        hints.append("Run 'discord today' to see today's messages")

    # Always add generic help hint
    hints.append(f"Run 'discord {command} --help' for all options")

    return hints


def emit_ambient_context(
    *,
    authenticated: bool,
    user: dict[str, Any] | None = None,
    guilds_count: int = 0,
    channels_tracked: int = 0,
    messages_stored: int = 0,
    recent_messages: list[dict[str, Any]] | None = None,
    as_json: bool = False,
    as_yaml: bool = False,
    as_toon: bool = False,
) -> bool:
    """Emit ambient context for session start (no-args command)."""
    fmt = default_structured_format(as_json=as_json, as_yaml=as_yaml, as_toon=as_toon)
    if not fmt:
        return False

    bin_path = os.path.expanduser("~/.local/bin/discord")
    if not os.path.exists(bin_path):
        bin_path = "discord"

    data = {
        "bin": bin_path.replace(os.path.expanduser("~"), "~"),
        "description": "Discord CLI for local-first sync, search, export, and agent-friendly retrieval",
        "status": {
            "authenticated": authenticated,
            "user": f"{user.get('global_name') or user.get('username', '?')}@{user.get('username', '?')}" if user else "unknown",
            "guilds": guilds_count,
            "channels_tracked": channels_tracked,
            "messages_stored": messages_stored,
        },
    }

    if recent_messages:
        data["recent"] = recent_messages[:3]
        data["help"] = [
            "Run 'discord dc guilds --yaml' to list servers",
            "Run 'discord today --yaml' to see today's messages",
            "Run 'discord dc sync-all' to sync all channels",
        ]

    envelope = _build_envelope(data, command_name="discord")
    click.echo(dump_structured(envelope, fmt=fmt))
    return True