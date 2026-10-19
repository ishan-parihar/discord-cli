# discord-cli Project Story

## Audience
Developers, AI agent builders, researchers who need local-first Discord data access for search, analytics, and agent integration.

## One-sentence value
Local-first Discord CLI that syncs messages to SQLite for fast search, analytics, and AI agent integration — with structured TOON/YAML/JSON output.

## Primary proof
Terminal output showing structured YAML from `discord search "term" --yaml` with agent-friendly schema (ok: true, schema_version: "1", data: [...])

## First successful action
```
discord auth --save && discord dc sync-all && discord today --yaml
```

## Visual theme
Terminal-native, CLI-focused, structured data visualization, agent-ready

## Native visual material
- Terminal output (real command runs)
- TOON format examples
- Structured YAML/JSON schemas
- Command workflow diagrams
- Agent integration patterns

## Content architecture (Value → Proof → Mechanism → First use → Detail)
1. **Hero**: Project name + plain value + real terminal output
2. **Proof**: Real structured output examples (YAML, TOON, JSON)
3. **Mechanism**: How it works (sync → store → query → agent)
4. **First use**: Install + auth + sync + query in 4 commands
5. **Detail**: Commands, schema, agent tips, limits

## Visual system
- **Palette**: Terminal dark (`#1e1e1e`), terminal green (`#4ec9b0`), accent amber (`#dcdcaa`), muted (`#858585`), foreground (`#d4d4d4`)
- **Typography**: System UI stack, monospace for code/terminal (`JetBrains Mono`, `Fira Code`, `monospace`)
- **Shape**: 4px radius, 1px stroke, 8px grid
- **Motif**: Terminal prompt `discord $` + cursor block, structured data brackets `{}[]`
- **Composition**: Technical/editorial — clean, high contrast, terminal-native