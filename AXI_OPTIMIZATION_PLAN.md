# AXI Optimization Plan for discord-cli

## Current State Analysis

The discord-cli currently outputs JSON/YAML with an envelope schema (`ok`, `schema_version`, `data`/`error`). While this is structured, it doesn't follow AXI principles:

| AXI Principle | Current Status | Gap |
|--------------|----------------|-----|
| **TOON format** | JSON/YAML only | No TOON support |
| **Minimal default schemas** | Full objects returned | 10+ fields per item |
| **Content truncation** | Full content always | No `--full` flag |
| **Pre-computed aggregates** | Missing | No counts in lists |
| **Definitive empty states** | Partial | Some show "No X found" |
| **Structured errors on stdout** | Partial | Some errors to stderr |
| **Content-first default** | Help text | No live state on no-args |
| **Contextual disclosure** | None | No next-step hints |
| **Help in output** | Separate `--help` | Not embedded |
| **Session integration** | None | No hook |

---

## Phase 1: Core Output Format (TOON + Minimal Schemas)

### 1.1 Add TOON Serialization
- Add `toon` as output format option alongside `json`/`yaml`
- Implement TOON serializer in `_output.py`
- Default to YAML for non-TTY, TOON for agents (detect via env)

### 1.2 Minimal Default Schemas (3-4 fields)
| Command | Current Fields | Minimal Schema |
|---------|---------------|----------------|
| `dc guilds` | id, name, icon, owner | `id, name, owner` |
| `dc channels` | id, name, type, position, parent_id, topic | `id, name, topic` |
| `dc members` | id, username, global_name, nick, bot | `id, username, display, nick, bot` |
| `dc history` | msg_id, channel_id, sender_id, sender_name, content, timestamp | `msg_id, sender_name, content, timestamp` |
| `dc search` | same as history | `msg_id, sender_name, content, timestamp` |
| `dc recent` | same as history | `msg_id, sender_name, content, timestamp` |
| `search` (local) | same as history | `msg_id, sender_name, content, timestamp` |
| `recent` (local) | same as history | `msg_id, sender_name, content, timestamp` |
| `stats` | channel_id, channel_name, guild_name, msg_count, first_msg, last_msg | `channel_name, guild_name, msg_count, last_msg` |
| `top` | sender_name, msg_count, first_msg, last_msg | `sender_name, msg_count, last_msg` |
| `today` | grouped messages | `channel, msg_count, messages[msg_id, sender_name, content, timestamp]` |

Add `--fields` flag to request additional fields.

---

## Phase 2: Content Truncation & Detail Views

### 2.1 Message Content Truncation
- Default: truncate `content` to 200 chars in list views
- Add `--full` flag to show complete content
- Show truncation indicator: `... (truncated, 1234 chars total)`
- Help hint: `Run 'discord dc history <id> --full' to see complete message`

### 2.2 Detail Views
- Single-item commands (`whoami`, `dc info`, `dc guilds <id>`) show full content
- Add `--full` to list commands to expand all items

---

## Phase 3: Pre-computed Aggregates

### 3.1 List Commands - Add Total Count
```
guilds[3]{id,name,owner}:
  "123",My Server,true
  "456",Another,false
  "789",Third,false
count: 3 of 3 total
help[1]: Run 'discord dc channels <guild_id>' to list channels
```

### 3.2 Derived Status Fields
- `dc sync`: add `last_synced` timestamp
- `dc tail`: add `watching` status
- `search`: add `total_matches` (may exceed `limit`)

---

## Phase 4: Definitive Empty States

Every list command must explicitly state:
```
channels: 0 text channels found in guild "My Server"
help[1]: Run 'discord dc guilds' to list available servers
```

---

## Phase 5: Structured Errors on Stdout

All errors must go to stdout in envelope format:
```yaml
ok: false
schema_version: "1"
error:
  code: guild_not_found
  message: Guild 'My Server' not found
  details:
    searched: "My Server"
help: Run 'discord dc guilds --yaml' to list available guilds
```

---

## Phase 6: Content-First Default

Running `discord` with no args should show ambient context:
```
bin: ~/.local/bin/discord
description: Discord CLI for local-first sync, search, export
status:
  authenticated: true
  user: "user#1234"
  guilds: 5
  channels_tracked: 12
  messages_stored: 45230
recent[3]{channel,sender,content,timestamp}:
  "#general",alice,"Hello team!",2024-01-15T10:30:00Z
  "#random",bob,"Anyone seen the docs?",2024-01-15T10:25:00Z
  "#dev",charlie,"PR #42 ready",2024-01-15T10:20:00Z
help[3]:
  Run 'discord dc guilds --yaml' to list servers
  Run 'discord today --yaml' to see today's messages
  Run 'discord dc sync-all' to sync all channels
```

---

## Phase 7: Contextual Disclosure (Next-Step Hints)

Add `help` array to every list/detail response with 2-3 relevant next commands:
- After `dc guilds`: suggest `dc channels <guild>`
- After `dc channels`: suggest `dc history <channel>`
- After `dc history`: suggest `dc sync <channel>` or `search "term" -c <channel>`
- After `search`: suggest `recent -c <channel>` or `export <channel> -f json`
- After `today`: suggest `timeline --by hour` or `top --hours 24`

---

## Phase 8: Help Integration

Every structured output includes:
```
help[1]: Run 'discord <command> --help' for full options
```

---

## Phase 9: Session Integration (Hook)

Create `discord hook install` command that:
1. Adds a `SessionStart` hook to Claude Code / Codex / OpenCode
2. Hook runs `discord --ambient` (new flag) and injects output as context
3. Output is compact ambient dashboard (like Phase 6 but minimal)

---

## Implementation Order

1. **TOON serializer + `--toon` flag** (_output.py)
2. **Minimal schemas + `--fields` flag** (each command file)
3. **Content truncation + `--full`** (_output.py + commands)
4. **Aggregates + empty states** (each command)
5. **Structured errors everywhere** (_output.py + commands)
6. **Content-first default** (main.py)
7. **Contextual disclosure** (each command)
8. **Help integration** (_output.py)
9. **Session hook** (new command + hook templates)

---

## Breaking Changes

- Default output format for lists changes from full objects → minimal schemas
- Error output moves from stderr → stdout (structured)
- Non-TTY default changes from YAML → TOON (for agents)

Mitigation:
- Add `--legacy` flag to restore old behavior
- Document migration in CHANGELOG
- Version bump to 1.0.0

---

## Testing Checklist

For each command:
- [ ] `--yaml` produces envelope with minimal schema
- [ ] `--json` produces envelope with minimal schema
- [ ] `--toon` produces TOON with minimal schema
- [ ] `--fields id,name,extra` adds requested fields
- [ ] `--full` shows complete content (no truncation)
- [ ] Empty state shows "0 X found" with context + help hint
- [ ] List output includes `count: N of M total`
- [ ] Errors emit to stdout with `ok: false` envelope
- [ ] Help hints present in output
- [ ] No-args `discord` shows ambient dashboard