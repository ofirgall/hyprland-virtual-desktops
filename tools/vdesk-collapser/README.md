# vdesk-collapser

Companion tool for [hyprland-virtual-desktops](../../). Snapshots the window
layout per monitor-count profile, applies per-profile rules on transition,
and restores known profiles when revisited. Drives the plugin only via
existing `hyprctl` dispatchers — the plugin itself is untouched.

## Install

```bash
cd tools/vdesk-collapser
python -m pip install --user .
```

Then in `~/.config/hypr/hyprland.conf`:

```
exec-once = vdesk-collapser
```

## Configure

Create `~/.config/vdesk-collapser/config.toml`:

```toml
[general]
debounce_ms = 1500

# 1-monitor profile: unpin Slack and route it to vdesk 9.
[[profile.1.rules]]
match.class = "Slack"
target_vdesk = 9
pin = false

# 3-monitor profile: keep Slack pinned across vdesks.
[[profile.3.rules]]
match.class = "Slack"
pin = true
```

Match fields (all optional, AND-ed):
- `match.class` — exact match against `class`
- `match.initial_class` — exact match against `initialClass`
- `match.title_regex` — regex search against `title`

Action fields (omit a field to leave that aspect untouched):
- `target_vdesk` — move window to this vdesk
- `pin` — `true` to plugin-pin, `false` to unpin

## Usage

| Command | What it does |
|---|---|
| `vdesk-collapser` | run daemon (intended for `exec-once`) |
| `vdesk-collapser --once --simulate 1` | force a transition to the 1-monitor profile |
| `vdesk-collapser --once --simulate 3` | force a transition to the 3-monitor profile |
| `vdesk-collapser --dry-run --once --simulate 1` | log intended dispatches, do nothing |

Bind a key for manual override:

```
bind = SUPER SHIFT, M, exec, vdesk-collapser --once --simulate 1
```

## State

- Config: `~/.config/vdesk-collapser/config.toml`
- Snapshots: `~/.local/state/vdesk-collapser/snapshots/<N>.json` (one per monitor count)
- Current profile + lock: `~/.local/state/vdesk-collapser/state.json`

## Design

See [`docs/superpowers/specs/2026-05-12-monitor-profile-collapser-design.md`](../../docs/superpowers/specs/2026-05-12-monitor-profile-collapser-design.md)
and [`docs/superpowers/plans/2026-05-12-monitor-profile-collapser.md`](../../docs/superpowers/plans/2026-05-12-monitor-profile-collapser.md).
