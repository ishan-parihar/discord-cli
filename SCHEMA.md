# Structured Output Schema

`discord-cli` uses a shared agent-friendly envelope for machine-readable output.

## Success Envelope

```yaml
ok: true
schema_version: "1"
data: ...
count: 3          # number of items in current response
total: 42         # total available (may exceed count due to limits)
help:             # contextual next-step hints
  - "Run 'discord dc channels <guild_id>' to list channels"
  - "Run 'discord dc history <channel_id>' to fetch messages"
command: "dc guilds"  # command that produced this output
```

## Error Envelope

```yaml
ok: false
schema_version: "1"
error:
  code: guild_not_found
  message: Guild 'My Server' not found
  details:
    searched: "My Server"
help:
  - "Run 'discord dc guilds --yaml' to list available servers"
```

## Output Formats

| Flag | Format | Use Case |
|------|--------|----------|
| `--yaml` | YAML | Human-readable, structured |
| `--json` | JSON | Machine parsing, strict typing |
| `--toon` | TOON | Token-efficient (40% smaller than JSON) |
| `--fields id,name` | Any | Select specific fields only |
| `--full` | Any | Show complete content (no truncation) |

## Default Behavior

- **TTY (interactive)**: Rich tables, no envelope
- **Non-TTY (piped)**: TOON envelope by default
- **Env override**: `OUTPUT=yaml|json|toon|rich|auto`

## Minimal Default Schemas (3-4 fields)

| Command | Default Fields |
|---------|---------------|
| `dc guilds` | `id`, `name`, `owner` |
| `dc channels` | `id`, `name`, `topic` |
| `dc members` | `id`, `username`, `display_name`, `nick`, `bot` |
| `dc history` / `dc sync` / `search` / `recent` | `msg_id`, `sender_name`, `content`, `timestamp` |
| `stats` | `channel_name`, `guild_name`, `msg_count`, `last_msg` |
| `top` | `sender_name`, `msg_count`, `last_msg` |
| `today` | `channel`, `msg_count`, `messages[]` |
| `timeline` | `period`, `msg_count` |

Use `--fields` to request additional fields (e.g., `--fields id,name,icon,owner`).

## Content Truncation

List views truncate `content` to 200-300 chars by default:
```yaml
content: "Hello world... (truncated, 1234 chars total)"
help:
  - "Run 'discord dc history <id> --full' to see complete message"
```

Use `--full` to disable truncation.

## Empty States

All list commands return definitive empty states:
```yaml
ok: true
schema_version: "1"
data: []
count: 0
total: 0
help:
  - "Run 'discord dc guilds --yaml' to list available servers"
```

Console output: `channels: 0 text channels found in guild 'My Server'`

## Content-First Default

Running `discord` with no arguments shows ambient context dashboard:
```yaml
ok: true
schema_version: "1"
data:
  bin: "~/.local/bin/discord"
  description: "Discord CLI for local-first sync, search, export"
  status:
    authenticated: true
    user: "user#1234"
    guilds: 5
    channels_tracked: 12
    messages_stored: 45230
  recent:
    - channel: "#general"
      sender: "alice"
      content: "Hello team!"
      timestamp: "2024-01-15T10:30:00Z"
help:
  - "Run 'discord dc guilds --yaml' to list servers"
  - "Run 'discord today --yaml' to see today's messages"
  - "Run 'discord dc sync-all' to sync all channels"
```

## Session Integration

Install session hook for ambient context at startup:
```bash
discord hook install --shell zsh  # or bash, fish
```

This adds a `SessionStart` hook to Claude Code / Codex / OpenCode that injects the ambient dashboard as initial context.