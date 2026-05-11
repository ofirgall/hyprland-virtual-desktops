# Monitor Profile Collapser — Design

**Status:** Draft
**Date:** 2026-05-12
**Scope:** A standalone tool, sibling to the `virtual-desktops` plugin, that automatically transforms the window layout when the connected monitor count changes, and restores the previous layout when returning to a count it has seen before. Drives the plugin only through existing `hyprctl` dispatchers.

## Goals

- When the user goes from N monitors to M monitors, snapshot the layout for profile N, then apply profile M's transformation rules, then replay the last known snapshot for profile M.
- Symmetric: returning N→M→N restores the layout that was live the moment the user left N.
- Concrete worked example: on a 3-monitor → 1-monitor change, unpin any plugin-pinned windows (e.g. Slack), move Slack to vdesk 9. On 1→3, re-pin Slack and put every other known window back where it was.
- Implementation lives entirely outside the plugin. The plugin remains untouched.

## Non-goals

- Auto-spawning new windows on transition (e.g. opening a tmux terminal on an empty vdesk).
- Distinguishing different physical setups that happen to have the same monitor count (e.g. "home dock 2-monitor" vs "office dock 2-monitor"). Profile key = monitor count only, for now.
- Reacting to individual window open/close events. Rules apply only at profile-transition time.
- Touching Hyprland's native pinned/sticky concept. "Sticky" in this design = plugin-pinned via `pinwindow`.

## Architecture

A standalone Python daemon `vdesk-collapser`, started via `exec-once` in Hyprland's config. Single-threaded asyncio loop. Stdlib-only (no runtime dependencies).

**Components**
- **Event reader** — reads `$XDG_RUNTIME_DIR/hypr/$HIS/.socket2.sock`; filters for `monitoradded>>` and `monitorremoved>>` lines.
- **Debouncer** — coalesces bursts; fires the transition only after the monitor count has been stable for `debounce_ms` (default 1500ms).
- **Transition driver** — runs the N→M procedure (snapshot → rules → replay) under a file lock.
- **Snapshot store** — `~/.local/state/vdesk-collapser/snapshots/<N>.json`, one per monitor-count, atomic writes (temp + rename).
- **Config loader** — `~/.config/vdesk-collapser/config.toml`. Loaded once at startup; restart on edit.
- **Hyprctl wrapper** — thin shim around `hyprctl` subprocess calls; the only component that performs side effects. Mockable for tests.

**Lifecycle**
1. Start → load config → query `hyprctl monitors -j` → `current_profile = N` → idle. No snapshot taken at startup.
2. Loop: read socket lines, drive debouncer; when debounce fires and the count has changed, run the transition.
3. SIGTERM → release lock, exit.

## The transition procedure (N → M)

```
on_debounced_monitor_change(N_old, M_new):
    acquire flock(state.json)
    state.transitioning = true; persist
    try:
        snapshot_profile(N_old)        # step 1
        apply_rules(M_new)             # step 2
        replay_snapshot(M_new)         # step 3
        state.current_profile = M_new
    finally:
        state.transitioning = false; persist
        release flock
```

### Step 1 — snapshot

1. `hyprctl clients -j` → live windows.
2. `hyprctl printpinnedwindows` → set of plugin-pinned addresses.
3. `hyprctl printstate` → workspace-id → vdesk-number mapping.
4. Build one snapshot row per window with `key=(class, initial_title, pid)`, `vdesk`, `monitor`, `workspace_id`, `pinned`, `floating`, `at`, `size`.
5. Atomic write to `snapshots/<N_old>.json`. Overwrites unconditionally.

### Step 2 — apply rules

For each rule in `profile.<M_new>.rules`, in declaration order:
1. Find matching live windows from `hyprctl clients -j`.
2. For each match, apply in this exact order:
   - If `pin = false` and currently pinned → `hyprctl dispatch unpinwindow address:0x…`
   - If `target_vdesk` set → `hyprctl dispatch movetodesksilent <vdesk>,address:0x…`
   - If `pin = true` and not currently pinned → `hyprctl dispatch pinwindow address:0x…`

Ordering rationale: pinned windows ignore vdesk moves, so unpin must happen before move; pin must happen after move so it locks onto the right vdesk.

All rule operations are idempotent.

### Step 3 — replay snapshot

Only runs if `snapshots/<M_new>.json` exists.

For each row in the snapshot:
1. Resolve to a live window: try `address` first (fast path within a Hyprland session); fall back to scanning `clients -j` for a row matching `key`.
2. If not found → skip silently.
3. **If a rule in step 2 already touched this window → skip** (rule wins).
4. Otherwise:
   - If currently pinned and snapshot says unpinned → unpin.
   - If current `vdesk` differs from snapshot → `movetodesksilent`.
   - If snapshot says pinned and not currently pinned → pin (after move).
   - If floating and position/size differ → `hyprctl dispatch movewindowpixel exact …` and resize equivalent.

## Window identity

Within a single Hyprland session, `address` is stable and used as a fast-path lookup.

Across operations (and across daemon restarts within a session), the matching key is `(class, initial_title, pid)`. Across Hyprland or OS restarts, pids change and snapshots become best-effort: unmatched rows are silently skipped, and the next snapshot of that profile rebuilds the picture.

## Config schema — `~/.config/vdesk-collapser/config.toml`

```toml
[general]
debounce_ms = 1500
state_dir = "~/.local/state/vdesk-collapser"  # optional

# Per-profile rules. Profile key = monitor count.
# Each rule = window matcher + action.
# Matcher fields (all optional, AND-ed): class, title_regex, initial_class
# Action fields: target_vdesk (int), pin (bool). Omitted fields = leave-as-is.

[[profile.1.rules]]
match.class = "Slack"
target_vdesk = 9
pin = false

[[profile.1.rules]]
match.title_regex = ".* - TMUX$"
# placeholder for future tmux-specific actions; currently a no-op

[[profile.3.rules]]
match.class = "Slack"
pin = true
```

Profiles with no section get no rule transformation — pure snapshot replay.

## Snapshot schema — `snapshots/<N>.json`

```json
{
  "schema": 1,
  "monitor_count": 3,
  "taken_at": "2026-05-12T14:32:10Z",
  "windows": [
    {
      "key": {"class": "Slack", "initial_title": "Slack", "pid": 4711},
      "address": "0x55aabb...",
      "vdesk": 1,
      "monitor": "DP-1",
      "workspace_id": 3,
      "pinned": true,
      "floating": false,
      "at": [120, 80],
      "size": [1800, 1000]
    }
  ]
}
```

## State file — `state.json`

```json
{ "current_profile": 1, "transitioning": false }
```

Guarded by `flock(2)` during transitions.

## Concurrency and re-entry

- The transition procedure runs under `flock` on `state.json`.
- If a monitor event arrives mid-transition, the event reader updates the latest observed count; the debouncer re-arms; the in-flight transition completes; the next debounce window evaluates against the latest count.
- If the new count equals the just-completed count → no-op.
- No nested transitions, ever.

## Edge cases

| Case | Behavior |
|---|---|
| Cable flicker / dock re-enumeration | Debounce coalesces bursts into a single transition. |
| Rapid N→M→N | Snapshot of N is overwritten right before leaving N, so returning replays the freshest state. |
| Window closed between snapshot and restore | Silently skipped during replay. |
| New window opened in profile M with matching rule | Rules re-fire on every entry to M, so it gets handled on the next transition into M. (Not at window-open time — out of scope.) |
| New window opened in profile M with no rule | Untouched; captured in next snapshot of M. |
| Rule and snapshot disagree about the same window | Rule wins; step 3 skips windows step 2 touched. |
| Hyprland restart | Addresses change; `(class, initial_title, pid)` survives within an OS session. |
| OS reboot | pids change; snapshots degrade to best-effort skip-unknowns. |
| Daemon started mid-session, no snapshot for current profile | Current live state becomes the baseline; first snapshot of this profile is taken on the next transition *out*. |
| Daemon was down during a profile change | Same as above. |
| Transition fires while another is in flight | Serialized by `flock`; debouncer re-evaluates after release. |
| User manually re-pinned or moved a window during profile M | That manual state is what gets snapshotted on the way out. Restoring to M honors user intent. |
| Plugin reports pinned address that has since been closed | Filtered against `clients -j` before issuing dispatches. |
| `target_vdesk` references a vdesk that doesn't exist yet | `movetodesksilent` creates it (plugin behavior). Acceptable. |
| Slack not running at collapse | Rule has no matches → no-op. Will not auto-pin on later launch in profile 3. |
| Simultaneous multi-monitor change (3→1 in one event) | Single debounced event; transition jumps 3→1 directly. Snapshot for profile 2 is not touched (never observed as a stable state). |
| First-ever encounter of a profile (no snapshot, no rules) | Leave windows where the plugin's existing layout cache put them. |

## Testing

**Unit tests (`pytest`, no Hyprland required)**

The hyprctl wrapper is the only side-effecting component, and is injected. Tests assert which dispatcher calls are issued for canned `hyprctl` JSON outputs.

Coverage:
- Rule matching (class, title_regex, initial_class, combined).
- Operation ordering (unpin → move → pin).
- Snapshot/rule conflict resolution (rule wins).
- Missing-window skip during replay.
- Empty-snapshot baseline (first encounter of a profile).
- Debouncer coalescing (fake clock).
- Atomic snapshot writes (no half-written JSON on crash).

**Integration / manual smoke**

CLI flags:
- `--dry-run` — log intended dispatches, execute nothing.
- `--simulate N` — pretend N monitors are connected; run a single transition. Useful for keybinds and for testing without unplugging cables.
- `--once` — run one transition based on current real state and exit.

## Project layout

```
tools/vdesk-collapser/
├── README.md
├── pyproject.toml          # ruff config; no runtime deps
├── vdesk_collapser/
│   ├── __init__.py
│   ├── __main__.py         # CLI entrypoint
│   ├── config.py           # TOML load + validation
│   ├── driver.py           # hyprctl wrapper (mockable)
│   ├── snapshot.py         # snapshot read/write/diff
│   ├── rules.py            # rule matching + apply
│   ├── transition.py       # N→M procedure
│   ├── debounce.py         # asyncio debouncer
│   └── daemon.py           # event reader + main loop
└── tests/
    ├── test_rules.py
    ├── test_snapshot.py
    ├── test_transition.py
    └── test_debounce.py
```

## Future work (not in this spec)

- React to window-open events so newly-launched apps get rule treatment without waiting for a transition.
- Per-physical-setup profiles (key on sorted monitor names rather than count).
- Spawn-missing-tmux on empty vdesks.
- Rules that act on workspace position within a monitor (e.g. force Slack to right monitor on 3-monitor profile).
