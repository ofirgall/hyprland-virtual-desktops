# Monitor Profile Collapser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python daemon `vdesk-collapser` that snapshots window layout per monitor-count profile, applies per-profile rules on transition, and restores known profiles when revisited — driving the `virtual-desktops` plugin only via `hyprctl`.

**Architecture:** Single-process asyncio daemon listening to Hyprland's `.socket2.sock`. On debounced `monitoradded`/`monitorremoved`, runs a serialized N→M transition: snapshot N → apply rules for M → replay snapshot M. All side effects go through one mockable `Driver` shim, enabling pure-unit tests.

**Tech Stack:** Python 3.11+ (stdlib only — `asyncio`, `tomllib`, `json`, `subprocess`, `fcntl`, `re`, `dataclasses`, `pathlib`); `pytest` for tests; `ruff` for lint.

**Reference spec:** `docs/superpowers/specs/2026-05-12-monitor-profile-collapser-design.md`

---

## File Structure

```
tools/vdesk-collapser/
├── README.md                          # install/run docs
├── pyproject.toml                     # ruff + pytest config; no runtime deps
├── vdesk_collapser/
│   ├── __init__.py                    # empty
│   ├── __main__.py                    # `python -m vdesk_collapser` entry
│   ├── models.py                      # dataclasses: WindowKey, WindowState, Snapshot, Matcher, Rule, Config
│   ├── config.py                      # load + validate TOML config
│   ├── driver.py                      # Driver protocol + HyprctlDriver + FakeDriver
│   ├── snapshot.py                    # build snapshot, atomic read/write
│   ├── rules.py                       # match windows, apply rule actions in order
│   ├── transition.py                  # the N→M procedure under flock
│   ├── debounce.py                    # asyncio debouncer (fake-clock-friendly)
│   ├── daemon.py                      # socket2 reader + main loop
│   └── cli.py                         # argparse, --dry-run/--simulate/--once
└── tests/
    ├── __init__.py
    ├── conftest.py                    # FakeDriver fixture, tmp state dir
    ├── test_config.py
    ├── test_snapshot.py
    ├── test_rules.py
    ├── test_transition.py
    └── test_debounce.py
```

**Responsibility split rationale:** `driver.py` is the only side-effecting module; everything else is pure transformation over data. `models.py` keeps types in one place so tests and modules import from a single source. `transition.py` orchestrates `snapshot.py` + `rules.py` and owns the flock.

---

## Task 1: Project skeleton

**Files:**
- Create: `tools/vdesk-collapser/pyproject.toml`
- Create: `tools/vdesk-collapser/vdesk_collapser/__init__.py`
- Create: `tools/vdesk-collapser/tests/__init__.py`
- Create: `tools/vdesk-collapser/tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "vdesk-collapser"
version = "0.1.0"
description = "Per-monitor-count window layout daemon for hyprland-virtual-desktops"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
vdesk-collapser = "vdesk_collapser.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["vdesk_collapser*"]

[tool.ruff]
line-length = 110
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 2: Create empty package files**

```bash
: > tools/vdesk-collapser/vdesk_collapser/__init__.py
: > tools/vdesk-collapser/tests/__init__.py
```

- [ ] **Step 3: Write minimal `conftest.py`**

```python
import pytest
from pathlib import Path

@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    (d / "snapshots").mkdir()
    return d
```

- [ ] **Step 4: Verify pytest discovers zero tests cleanly**

Run: `cd tools/vdesk-collapser && python -m pytest -q`
Expected: `no tests ran in ...` (exit code 5, that's fine; or 0 if pytest reports "collected 0 items").

- [ ] **Step 5: Commit**

```bash
git add tools/vdesk-collapser/
git commit -m "feat(collapser): project skeleton"
```

---

## Task 2: Data models

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/models.py`
- Create: `tools/vdesk-collapser/tests/test_models.py`

- [ ] **Step 1: Write failing test**

`tests/test_models.py`:

```python
from vdesk_collapser.models import WindowKey, WindowState, Snapshot, Matcher, Rule

def test_window_key_is_hashable_and_frozen():
    k = WindowKey(klass="Slack", initial_title="Slack", pid=4711)
    {k}  # must be hashable
    # frozen
    import dataclasses
    assert dataclasses.fields(WindowKey)
    try:
        k.klass = "Other"
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("WindowKey must be frozen")

def test_rule_defaults_are_leave_as_is():
    r = Rule(match=Matcher(klass="Slack"))
    assert r.target_vdesk is None
    assert r.pin is None

def test_snapshot_round_trips_via_to_dict_from_dict():
    snap = Snapshot(
        monitor_count=3,
        taken_at="2026-05-12T14:32:10Z",
        windows=[
            WindowState(
                key=WindowKey("Slack", "Slack", 4711),
                address="0x55aabb",
                vdesk=1,
                monitor="DP-1",
                workspace_id=3,
                pinned=True,
                floating=False,
                at=(120, 80),
                size=(1800, 1000),
            )
        ],
    )
    assert Snapshot.from_dict(snap.to_dict()) == snap
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_models.py -v`
Expected: ImportError / ModuleNotFoundError on `vdesk_collapser.models`.

- [ ] **Step 3: Implement `models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True)
class WindowKey:
    klass: str
    initial_title: str
    pid: int

@dataclass
class WindowState:
    key: WindowKey
    address: str
    vdesk: int
    monitor: str
    workspace_id: int
    pinned: bool
    floating: bool
    at: tuple[int, int]
    size: tuple[int, int]

@dataclass
class Snapshot:
    monitor_count: int
    taken_at: str
    windows: list[WindowState]
    schema: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "monitor_count": self.monitor_count,
            "taken_at": self.taken_at,
            "windows": [
                {
                    "key": {"class": w.key.klass, "initial_title": w.key.initial_title, "pid": w.key.pid},
                    "address": w.address,
                    "vdesk": w.vdesk,
                    "monitor": w.monitor,
                    "workspace_id": w.workspace_id,
                    "pinned": w.pinned,
                    "floating": w.floating,
                    "at": list(w.at),
                    "size": list(w.size),
                }
                for w in self.windows
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Snapshot":
        return cls(
            schema=d.get("schema", 1),
            monitor_count=d["monitor_count"],
            taken_at=d["taken_at"],
            windows=[
                WindowState(
                    key=WindowKey(w["key"]["class"], w["key"]["initial_title"], w["key"]["pid"]),
                    address=w["address"],
                    vdesk=w["vdesk"],
                    monitor=w["monitor"],
                    workspace_id=w["workspace_id"],
                    pinned=w["pinned"],
                    floating=w["floating"],
                    at=tuple(w["at"]),
                    size=tuple(w["size"]),
                )
                for w in d["windows"]
            ],
        )

@dataclass
class Matcher:
    klass: str | None = None
    title_regex: str | None = None
    initial_class: str | None = None

@dataclass
class Rule:
    match: Matcher
    target_vdesk: int | None = None
    pin: bool | None = None

@dataclass
class Config:
    debounce_ms: int = 1500
    state_dir: str = "~/.local/state/vdesk-collapser"
    profiles: dict[int, list[Rule]] = field(default_factory=dict)
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/models.py tests/test_models.py
git commit -m "feat(collapser): data models"
```

---

## Task 3: Config loader

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/config.py`
- Create: `tools/vdesk-collapser/tests/test_config.py`

- [ ] **Step 1: Write failing test**

`tests/test_config.py`:

```python
from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.models import Matcher, Rule

SAMPLE = """
[general]
debounce_ms = 800
state_dir = "/tmp/vc"

[[profile.1.rules]]
match.class = "Slack"
target_vdesk = 9
pin = false

[[profile.1.rules]]
match.title_regex = ".* - TMUX$"

[[profile.3.rules]]
match.class = "Slack"
pin = true
"""

def test_load_config_parses_general_and_profiles(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(SAMPLE)
    cfg = load_config(p)
    assert cfg.debounce_ms == 800
    assert cfg.state_dir == "/tmp/vc"
    assert list(cfg.profiles.keys()) == [1, 3]
    r1 = cfg.profiles[1]
    assert r1[0] == Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)
    assert r1[1] == Rule(match=Matcher(title_regex=".* - TMUX$"))
    assert cfg.profiles[3][0] == Rule(match=Matcher(klass="Slack"), pin=True)

def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.debounce_ms == 1500
    assert cfg.profiles == {}

def test_load_config_rejects_unknown_match_field(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[[profile.1.rules]]\nmatch.bogus = "x"\n')
    import pytest
    with pytest.raises(ValueError, match="unknown match field"):
        load_config(p)
```

- [ ] **Step 2: Run test, expect failure (ModuleNotFoundError)**

Run: `python -m pytest tests/test_config.py -v`

- [ ] **Step 3: Implement `config.py`**

```python
from __future__ import annotations
import tomllib
from pathlib import Path
from vdesk_collapser.models import Config, Matcher, Rule

_ALLOWED_MATCH = {"class", "title_regex", "initial_class"}
_ALLOWED_RULE_TOP = {"match", "target_vdesk", "pin"}

def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)

    general = data.get("general", {})
    cfg = Config(
        debounce_ms=int(general.get("debounce_ms", 1500)),
        state_dir=general.get("state_dir", "~/.local/state/vdesk-collapser"),
    )
    profiles_raw = data.get("profile", {})
    for key, body in profiles_raw.items():
        n = int(key)
        rules = []
        for raw in body.get("rules", []):
            extra = set(raw) - _ALLOWED_RULE_TOP
            if extra:
                raise ValueError(f"unknown rule field(s) in profile {n}: {extra}")
            match_raw = raw.get("match", {})
            bad = set(match_raw) - _ALLOWED_MATCH
            if bad:
                raise ValueError(f"unknown match field(s) in profile {n}: {bad}")
            rules.append(
                Rule(
                    match=Matcher(
                        klass=match_raw.get("class"),
                        title_regex=match_raw.get("title_regex"),
                        initial_class=match_raw.get("initial_class"),
                    ),
                    target_vdesk=raw.get("target_vdesk"),
                    pin=raw.get("pin"),
                )
            )
        cfg.profiles[n] = rules
    return cfg
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/config.py tests/test_config.py
git commit -m "feat(collapser): TOML config loader"
```

---

## Task 4: Driver protocol and FakeDriver

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/driver.py`
- Modify: `tools/vdesk-collapser/tests/conftest.py`
- Create: `tools/vdesk-collapser/tests/test_driver.py`

- [ ] **Step 1: Write failing test**

`tests/test_driver.py`:

```python
from vdesk_collapser.driver import FakeDriver

def test_fake_driver_records_dispatches():
    d = FakeDriver()
    d.dispatch("movetodesksilent", "9,address:0x1")
    d.dispatch("unpinwindow", "address:0x1")
    assert d.calls == [
        ("movetodesksilent", "9,address:0x1"),
        ("unpinwindow", "address:0x1"),
    ]

def test_fake_driver_returns_canned_clients():
    d = FakeDriver(clients=[{"address": "0x1", "class": "Slack"}])
    assert d.clients() == [{"address": "0x1", "class": "Slack"}]

def test_fake_driver_pinned_addresses_set():
    d = FakeDriver(pinned={"0x1", "0x2"})
    assert d.pinned_addresses() == {"0x1", "0x2"}

def test_fake_driver_workspace_to_vdesk_map():
    d = FakeDriver(workspace_to_vdesk={1: 1, 2: 1, 3: 2})
    assert d.workspace_to_vdesk() == {1: 1, 2: 1, 3: 2}

def test_fake_driver_monitors_count():
    d = FakeDriver(monitors=[{"name": "DP-1"}, {"name": "DP-2"}])
    assert len(d.monitors()) == 2
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_driver.py -v`

- [ ] **Step 3: Implement `driver.py`**

```python
from __future__ import annotations
import json
import subprocess
from typing import Protocol

class Driver(Protocol):
    def clients(self) -> list[dict]: ...
    def monitors(self) -> list[dict]: ...
    def pinned_addresses(self) -> set[str]: ...
    def workspace_to_vdesk(self) -> dict[int, int]: ...
    def dispatch(self, command: str, args: str) -> None: ...

class HyprctlDriver:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def _json(self, *args: str) -> list[dict] | dict:
        out = subprocess.check_output(["hyprctl", "-j", *args], text=True)
        return json.loads(out)

    def clients(self) -> list[dict]:
        return self._json("clients")  # type: ignore[return-value]

    def monitors(self) -> list[dict]:
        return self._json("monitors")  # type: ignore[return-value]

    def pinned_addresses(self) -> set[str]:
        # plugin command "printpinnedwindows" returns plain text, one address per line
        out = subprocess.check_output(["hyprctl", "printpinnedwindows"], text=True)
        addrs: set[str] = set()
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("0x"):
                addrs.add(line.split()[0])
        return addrs

    def workspace_to_vdesk(self) -> dict[int, int]:
        # plugin "printstate" returns lines like "vdesk 1: workspace 1 (monitor DP-1), ..."
        out = subprocess.check_output(["hyprctl", "printstate"], text=True)
        mapping: dict[int, int] = {}
        import re
        for line in out.splitlines():
            m = re.match(r"\s*vdesk\s+(\d+)\s*:", line)
            if not m:
                continue
            vdesk = int(m.group(1))
            for ws in re.findall(r"workspace\s+(\d+)", line):
                mapping[int(ws)] = vdesk
        return mapping

    def dispatch(self, command: str, args: str) -> None:
        if self.dry_run:
            print(f"[dry-run] hyprctl dispatch {command} {args}")
            return
        subprocess.check_call(["hyprctl", "dispatch", command, args])


class FakeDriver:
    def __init__(
        self,
        clients: list[dict] | None = None,
        monitors: list[dict] | None = None,
        pinned: set[str] | None = None,
        workspace_to_vdesk: dict[int, int] | None = None,
    ) -> None:
        self._clients = clients or []
        self._monitors = monitors or []
        self._pinned = set(pinned or set())
        self._w2v = dict(workspace_to_vdesk or {})
        self.calls: list[tuple[str, str]] = []

    def clients(self) -> list[dict]:
        return self._clients

    def monitors(self) -> list[dict]:
        return self._monitors

    def pinned_addresses(self) -> set[str]:
        return self._pinned

    def workspace_to_vdesk(self) -> dict[int, int]:
        return self._w2v

    def dispatch(self, command: str, args: str) -> None:
        self.calls.append((command, args))
        # mirror simple state mutations so subsequent reads in the same test see effects
        if command == "pinwindow":
            addr = args.split("address:", 1)[1] if "address:" in args else None
            if addr:
                self._pinned.add(addr)
        elif command == "unpinwindow":
            addr = args.split("address:", 1)[1] if "address:" in args else None
            if addr:
                self._pinned.discard(addr)
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_driver.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/driver.py tests/test_driver.py tests/conftest.py
git commit -m "feat(collapser): Driver protocol with hyprctl + fake impls"
```

---

## Task 5: Snapshot build and persistence

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/snapshot.py`
- Create: `tools/vdesk-collapser/tests/test_snapshot.py`

- [ ] **Step 1: Write failing test**

`tests/test_snapshot.py`:

```python
import json
from pathlib import Path
from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.snapshot import build_snapshot, write_snapshot, read_snapshot, snapshot_path

CLIENT = {
    "address": "0x1",
    "class": "Slack",
    "initialTitle": "Slack",
    "pid": 4711,
    "workspace": {"id": 3},
    "monitor": 0,
    "floating": False,
    "at": [120, 80],
    "size": [1800, 1000],
}

def test_build_snapshot_from_driver_state():
    driver = FakeDriver(
        clients=[CLIENT],
        monitors=[{"id": 0, "name": "DP-1"}],
        pinned={"0x1"},
        workspace_to_vdesk={3: 2},
    )
    snap = build_snapshot(driver, monitor_count=3, now_iso="2026-05-12T14:32:10Z")
    assert snap.monitor_count == 3
    assert len(snap.windows) == 1
    w = snap.windows[0]
    assert w.address == "0x1"
    assert w.key.klass == "Slack"
    assert w.key.initial_title == "Slack"
    assert w.key.pid == 4711
    assert w.vdesk == 2
    assert w.monitor == "DP-1"
    assert w.workspace_id == 3
    assert w.pinned is True
    assert w.at == (120, 80)

def test_build_snapshot_skips_clients_on_unknown_workspace():
    driver = FakeDriver(
        clients=[{**CLIENT, "workspace": {"id": 999}}],
        monitors=[{"id": 0, "name": "DP-1"}],
        pinned=set(),
        workspace_to_vdesk={3: 2},
    )
    snap = build_snapshot(driver, monitor_count=3, now_iso="t")
    assert snap.windows == []

def test_write_and_read_snapshot_round_trip(tmp_state_dir: Path):
    driver = FakeDriver(
        clients=[CLIENT],
        monitors=[{"id": 0, "name": "DP-1"}],
        pinned=set(),
        workspace_to_vdesk={3: 2},
    )
    snap = build_snapshot(driver, monitor_count=3, now_iso="t")
    write_snapshot(snap, snapshot_path(tmp_state_dir, 3))
    again = read_snapshot(snapshot_path(tmp_state_dir, 3))
    assert again == snap

def test_write_snapshot_is_atomic(tmp_state_dir: Path):
    p = snapshot_path(tmp_state_dir, 3)
    # Pre-existing junk file should still be replaced cleanly
    p.write_text("garbage")
    driver = FakeDriver(clients=[], monitors=[], pinned=set(), workspace_to_vdesk={})
    write_snapshot(build_snapshot(driver, monitor_count=3, now_iso="t"), p)
    assert json.loads(p.read_text())["monitor_count"] == 3

def test_read_snapshot_missing_returns_none(tmp_state_dir: Path):
    assert read_snapshot(snapshot_path(tmp_state_dir, 7)) is None
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_snapshot.py -v`

- [ ] **Step 3: Implement `snapshot.py`**

```python
from __future__ import annotations
import json
import os
from pathlib import Path
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Snapshot, WindowKey, WindowState

def snapshot_path(state_dir: Path, monitor_count: int) -> Path:
    return state_dir / "snapshots" / f"{monitor_count}.json"

def build_snapshot(driver: Driver, monitor_count: int, now_iso: str) -> Snapshot:
    monitors = {m["id"]: m["name"] for m in driver.monitors()}
    w2v = driver.workspace_to_vdesk()
    pinned = driver.pinned_addresses()
    windows: list[WindowState] = []
    for c in driver.clients():
        ws_id = c["workspace"]["id"]
        if ws_id not in w2v:
            continue
        at = c.get("at", [0, 0])
        size = c.get("size", [0, 0])
        windows.append(
            WindowState(
                key=WindowKey(
                    klass=c.get("class", ""),
                    initial_title=c.get("initialTitle", c.get("title", "")),
                    pid=int(c.get("pid", 0)),
                ),
                address=c["address"],
                vdesk=w2v[ws_id],
                monitor=monitors.get(c.get("monitor"), ""),
                workspace_id=ws_id,
                pinned=c["address"] in pinned,
                floating=bool(c.get("floating", False)),
                at=(int(at[0]), int(at[1])),
                size=(int(size[0]), int(size[1])),
            )
        )
    return Snapshot(monitor_count=monitor_count, taken_at=now_iso, windows=windows)

def write_snapshot(snap: Snapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snap.to_dict(), indent=2))
    os.replace(tmp, path)

def read_snapshot(path: Path) -> Snapshot | None:
    if not path.exists():
        return None
    return Snapshot.from_dict(json.loads(path.read_text()))
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/snapshot.py tests/test_snapshot.py
git commit -m "feat(collapser): snapshot build + atomic persistence"
```

---

## Task 6: Rule matching and application

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/rules.py`
- Create: `tools/vdesk-collapser/tests/test_rules.py`

- [ ] **Step 1: Write failing test**

`tests/test_rules.py`:

```python
from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Matcher, Rule
from vdesk_collapser.rules import match_window, apply_rules

SLACK = {"address": "0x1", "class": "Slack", "title": "Slack | foo", "initialClass": "Slack"}
KITTY = {"address": "0x2", "class": "kitty", "title": "host - TMUX", "initialClass": "kitty"}
FIREFOX = {"address": "0x3", "class": "firefox", "title": "github - Firefox", "initialClass": "firefox"}

def test_match_window_by_class():
    assert match_window(SLACK, Matcher(klass="Slack"))
    assert not match_window(KITTY, Matcher(klass="Slack"))

def test_match_window_by_title_regex():
    assert match_window(KITTY, Matcher(title_regex=r".* - TMUX$"))
    assert not match_window(FIREFOX, Matcher(title_regex=r".* - TMUX$"))

def test_match_window_combined_is_AND():
    m = Matcher(klass="kitty", title_regex=r".* - TMUX$")
    assert match_window(KITTY, m)
    assert not match_window(SLACK, m)

def test_apply_rules_unpin_before_move_before_pin():
    driver = FakeDriver(clients=[SLACK], pinned={"0x1"})
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
    assert driver.calls == [
        ("unpinwindow", "address:0x1"),
        ("movetodesksilent", "9,address:0x1"),
    ]

def test_apply_rules_pin_after_move():
    driver = FakeDriver(clients=[SLACK], pinned=set())
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=2, pin=True)]
    apply_rules(driver, rules)
    assert driver.calls == [
        ("movetodesksilent", "2,address:0x1"),
        ("pinwindow", "address:0x1"),
    ]

def test_apply_rules_idempotent_when_state_matches():
    driver = FakeDriver(clients=[SLACK], pinned={"0x1"})
    rules = [Rule(match=Matcher(klass="Slack"), pin=True)]  # already pinned, no target
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
    assert driver.calls == []

def test_apply_rules_returns_addresses_touched():
    driver = FakeDriver(clients=[SLACK, KITTY], pinned=set())
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=9)]
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_rules.py -v`

- [ ] **Step 3: Implement `rules.py`**

```python
from __future__ import annotations
import re
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Matcher, Rule

def match_window(client: dict, m: Matcher) -> bool:
    if m.klass is not None and client.get("class") != m.klass:
        return False
    if m.initial_class is not None and client.get("initialClass") != m.initial_class:
        return False
    if m.title_regex is not None:
        if not re.search(m.title_regex, client.get("title", "")):
            return False
    return True

def apply_rules(driver: Driver, rules: list[Rule]) -> set[str]:
    """Apply rules in declaration order. Returns the set of window addresses touched
    (matched by any rule), so the caller can skip them in the snapshot-replay phase."""
    touched: set[str] = set()
    clients = driver.clients()
    pinned = set(driver.pinned_addresses())

    for rule in rules:
        for c in clients:
            if not match_window(c, rule.match):
                continue
            addr = c["address"]
            touched.add(addr)

            # Step A: unpin first (if rule says pin=False and currently pinned).
            if rule.pin is False and addr in pinned:
                driver.dispatch("unpinwindow", f"address:{addr}")
                pinned.discard(addr)

            # Step B: move (only meaningful when not pinned).
            if rule.target_vdesk is not None and addr not in pinned:
                driver.dispatch("movetodesksilent", f"{rule.target_vdesk},address:{addr}")

            # Step C: pin last (if rule says pin=True and not currently pinned).
            if rule.pin is True and addr not in pinned:
                driver.dispatch("pinwindow", f"address:{addr}")
                pinned.add(addr)

    return touched
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_rules.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/rules.py tests/test_rules.py
git commit -m "feat(collapser): rule matching and ordered application"
```

---

## Task 7: Snapshot replay

**Files:**
- Modify: `tools/vdesk-collapser/vdesk_collapser/snapshot.py` (add `replay_snapshot`)
- Modify: `tools/vdesk-collapser/tests/test_snapshot.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_snapshot.py`:

```python
from vdesk_collapser.snapshot import replay_snapshot
from vdesk_collapser.models import Snapshot, WindowState, WindowKey

def _client(addr, klass, title, pid, ws_id, monitor=0):
    return {
        "address": addr, "class": klass, "initialTitle": title, "title": title,
        "pid": pid, "workspace": {"id": ws_id}, "monitor": monitor,
        "floating": False, "at": [0, 0], "size": [800, 600],
    }

def _ws(key_class="Slack", key_title="Slack", key_pid=4711, addr="0x1",
        vdesk=1, monitor="DP-1", workspace_id=1, pinned=False,
        floating=False, at=(0, 0), size=(800, 600)):
    return WindowState(
        key=WindowKey(key_class, key_title, key_pid),
        address=addr, vdesk=vdesk, monitor=monitor, workspace_id=workspace_id,
        pinned=pinned, floating=floating, at=at, size=size,
    )

def test_replay_moves_window_back_to_snapshot_vdesk():
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(vdesk=2)])
    # Live client currently on workspace 5 (vdesk 1)
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=5)],
        pinned=set(),
        workspace_to_vdesk={5: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert driver.calls == [("movetodesksilent", "2,address:0x1")]

def test_replay_finds_window_by_key_when_address_differs():
    # Snapshot recorded old address 0x99, live address is 0x1 — match by key.
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(addr="0x99", vdesk=2)])
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=5)],
        pinned=set(),
        workspace_to_vdesk={5: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert ("movetodesksilent", "2,address:0x1") in driver.calls

def test_replay_skips_addresses_already_touched_by_rules():
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(vdesk=2)])
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=5)],
        pinned=set(),
        workspace_to_vdesk={5: 1},
    )
    replay_snapshot(driver, snap, skip_addresses={"0x1"})
    assert driver.calls == []

def test_replay_skips_missing_windows_silently():
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(addr="0xZ", vdesk=2)])
    driver = FakeDriver(clients=[], pinned=set(), workspace_to_vdesk={})
    replay_snapshot(driver, snap, skip_addresses=set())
    assert driver.calls == []

def test_replay_unpins_then_pins_to_match_snapshot():
    # Snapshot: pinned=True, currently unpinned.
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(vdesk=1, pinned=True)])
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        pinned=set(),
        workspace_to_vdesk={1: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert ("pinwindow", "address:0x1") in driver.calls
    # No move because vdesk matches.
    assert not any(c[0] == "movetodesksilent" for c in driver.calls)

def test_replay_unpins_when_snapshot_says_unpinned_but_currently_pinned():
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(vdesk=1, pinned=False)])
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert driver.calls == [("unpinwindow", "address:0x1")]
```

- [ ] **Step 2: Run tests, expect failure**

Run: `python -m pytest tests/test_snapshot.py -v`

- [ ] **Step 3: Implement `replay_snapshot`**

Append to `vdesk_collapser/snapshot.py`:

```python
from vdesk_collapser.models import WindowKey

def _client_key(c: dict) -> WindowKey:
    return WindowKey(
        klass=c.get("class", ""),
        initial_title=c.get("initialTitle", c.get("title", "")),
        pid=int(c.get("pid", 0)),
    )

def replay_snapshot(driver: Driver, snap: Snapshot, skip_addresses: set[str]) -> None:
    clients = driver.clients()
    by_addr = {c["address"]: c for c in clients}
    by_key: dict[WindowKey, dict] = {_client_key(c): c for c in clients}
    pinned = set(driver.pinned_addresses())
    w2v = driver.workspace_to_vdesk()

    for row in snap.windows:
        # Try fast path (same address still alive); fall back to key match.
        live = by_addr.get(row.address) or by_key.get(row.key)
        if live is None:
            continue
        addr = live["address"]
        if addr in skip_addresses:
            continue

        # Unpin first if needed (so move can take effect).
        if addr in pinned and not row.pinned:
            driver.dispatch("unpinwindow", f"address:{addr}")
            pinned.discard(addr)

        # Move if current vdesk differs from snapshot, and not currently pinned.
        current_vdesk = w2v.get(live["workspace"]["id"])
        if current_vdesk != row.vdesk and addr not in pinned:
            driver.dispatch("movetodesksilent", f"{row.vdesk},address:{addr}")

        # Pin last if snapshot says pinned but we aren't.
        if row.pinned and addr not in pinned:
            driver.dispatch("pinwindow", f"address:{addr}")
            pinned.add(addr)
```

- [ ] **Step 4: Run tests, expect pass**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: all snapshot tests pass.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/snapshot.py tests/test_snapshot.py
git commit -m "feat(collapser): snapshot replay with key fallback"
```

---

## Task 8: Transition orchestrator

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/transition.py`
- Create: `tools/vdesk-collapser/tests/test_transition.py`

- [ ] **Step 1: Write failing test**

`tests/test_transition.py`:

```python
import json
from pathlib import Path
from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Config, Matcher, Rule
from vdesk_collapser.transition import run_transition
from vdesk_collapser.snapshot import snapshot_path, read_snapshot

def _client(addr, klass, title, pid, ws_id):
    return {
        "address": addr, "class": klass, "initialTitle": title, "title": title,
        "pid": pid, "workspace": {"id": ws_id}, "monitor": 0,
        "floating": False, "at": [0, 0], "size": [800, 600],
    }

def test_transition_writes_snapshot_for_old_profile(tmp_state_dir: Path):
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        monitors=[{"id": 0, "name": "DP-1"}],
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_transition(driver, cfg, n_old=3, m_new=1, state_dir=tmp_state_dir, now_iso="t")
    p = snapshot_path(tmp_state_dir, 3)
    assert p.exists()
    snap = read_snapshot(p)
    assert snap is not None and snap.monitor_count == 3
    assert snap.windows[0].pinned is True

def test_transition_applies_new_profile_rules(tmp_state_dir: Path):
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        monitors=[{"id": 0, "name": "DP-1"}],
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_transition(driver, cfg, n_old=3, m_new=1, state_dir=tmp_state_dir, now_iso="t")
    assert ("unpinwindow", "address:0x1") in driver.calls
    assert ("movetodesksilent", "9,address:0x1") in driver.calls

def test_transition_replays_snapshot_for_new_profile(tmp_state_dir: Path):
    # Pre-seed snapshot for profile 3: Slack pinned on vdesk 1
    from vdesk_collapser.models import Snapshot, WindowState, WindowKey
    from vdesk_collapser.snapshot import write_snapshot
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[
        WindowState(
            key=WindowKey("Slack", "Slack", 4711),
            address="0x1", vdesk=1, monitor="DP-1", workspace_id=1,
            pinned=True, floating=False, at=(0, 0), size=(800, 600),
        )
    ])
    write_snapshot(snap, snapshot_path(tmp_state_dir, 3))

    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=9)],  # currently on vdesk 9
        monitors=[{"id": 0, "name": "DP-1"}, {"id": 1, "name": "DP-2"}, {"id": 2, "name": "DP-3"}],
        pinned=set(),
        workspace_to_vdesk={9: 9, 1: 1},
    )
    cfg = Config(profiles={3: []})
    run_transition(driver, cfg, n_old=1, m_new=3, state_dir=tmp_state_dir, now_iso="t")
    assert ("movetodesksilent", "1,address:0x1") in driver.calls
    assert ("pinwindow", "address:0x1") in driver.calls

def test_transition_rules_win_over_snapshot_for_same_window(tmp_state_dir: Path):
    from vdesk_collapser.models import Snapshot, WindowState, WindowKey
    from vdesk_collapser.snapshot import write_snapshot
    # Snapshot for profile 1 says Slack on vdesk 5 unpinned
    snap = Snapshot(monitor_count=1, taken_at="t", windows=[
        WindowState(
            key=WindowKey("Slack", "Slack", 4711),
            address="0x1", vdesk=5, monitor="eDP-1", workspace_id=5,
            pinned=False, floating=False, at=(0, 0), size=(800, 600),
        )
    ])
    write_snapshot(snap, snapshot_path(tmp_state_dir, 1))

    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        monitors=[{"id": 0, "name": "eDP-1"}],
        pinned={"0x1"},  # was pinned, need to unpin per rule
        workspace_to_vdesk={1: 1},
    )
    # Rule for profile 1 puts Slack on vdesk 9 (not 5)
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_transition(driver, cfg, n_old=3, m_new=1, state_dir=tmp_state_dir, now_iso="t")
    # Move came from the rule (9), not the snapshot (5)
    move_calls = [c for c in driver.calls if c[0] == "movetodesksilent"]
    assert move_calls == [("movetodesksilent", "9,address:0x1")]
```

- [ ] **Step 2: Run tests, expect failure**

Run: `python -m pytest tests/test_transition.py -v`

- [ ] **Step 3: Implement `transition.py`**

```python
from __future__ import annotations
import fcntl
import json
from pathlib import Path
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Config
from vdesk_collapser.rules import apply_rules
from vdesk_collapser.snapshot import (
    build_snapshot, write_snapshot, read_snapshot, snapshot_path, replay_snapshot,
)

def _state_file(state_dir: Path) -> Path:
    return state_dir / "state.json"

def run_transition(
    driver: Driver,
    cfg: Config,
    n_old: int,
    m_new: int,
    state_dir: Path,
    now_iso: str,
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    sfile = _state_file(state_dir)
    sfile.touch(exist_ok=True)
    with open(sfile, "r+") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            sfile.write_text(json.dumps({"current_profile": n_old, "transitioning": True}))

            # Step 1: snapshot old profile
            snap_old = build_snapshot(driver, monitor_count=n_old, now_iso=now_iso)
            write_snapshot(snap_old, snapshot_path(state_dir, n_old))

            # Step 2: apply rules for new profile
            rules = cfg.profiles.get(m_new, [])
            touched = apply_rules(driver, rules)

            # Step 3: replay snapshot for new profile (if any), skipping rule-touched
            snap_new = read_snapshot(snapshot_path(state_dir, m_new))
            if snap_new is not None:
                replay_snapshot(driver, snap_new, skip_addresses=touched)

            sfile.write_text(json.dumps({"current_profile": m_new, "transitioning": False}))
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
```

- [ ] **Step 4: Run tests, expect pass**

Run: `python -m pytest tests/test_transition.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/transition.py tests/test_transition.py
git commit -m "feat(collapser): N->M transition under flock"
```

---

## Task 9: Asyncio debouncer

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/debounce.py`
- Create: `tools/vdesk-collapser/tests/test_debounce.py`

- [ ] **Step 1: Write failing test**

`tests/test_debounce.py`:

```python
import asyncio
import pytest
from vdesk_collapser.debounce import Debouncer

@pytest.mark.asyncio
async def test_debouncer_fires_after_quiet_period():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.05, callback=cb)
    d.bump(1)
    await asyncio.sleep(0.02)
    d.bump(2)
    await asyncio.sleep(0.02)
    d.bump(3)
    assert fired == []
    await asyncio.sleep(0.1)
    assert fired == [3]

@pytest.mark.asyncio
async def test_debouncer_coalesces_rapid_bursts():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.03, callback=cb)
    for v in range(10):
        d.bump(v)
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.1)
    assert fired == [9]

@pytest.mark.asyncio
async def test_debouncer_can_fire_multiple_times_with_gaps():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.03, callback=cb)
    d.bump(1); await asyncio.sleep(0.1)
    d.bump(2); await asyncio.sleep(0.1)
    assert fired == [1, 2]
```

Also add to `pyproject.toml` `[tool.pytest.ini_options]` section:

```toml
asyncio_mode = "auto"
```

And install `pytest-asyncio` as a dev dep. Update the test command. Actually, to stay stdlib-only at runtime we don't add it to `[project.dependencies]` — only as a test-time dep. Add a `[project.optional-dependencies]` `dev` group:

```toml
[project.optional-dependencies]
dev = ["pytest>=7", "pytest-asyncio>=0.23", "ruff"]
```

- [ ] **Step 2: Install dev deps and run test, expect failure**

```bash
cd tools/vdesk-collapser
python -m pip install -e ".[dev]"
python -m pytest tests/test_debounce.py -v
```

Expected: ModuleNotFoundError on `vdesk_collapser.debounce`.

- [ ] **Step 3: Implement `debounce.py`**

```python
from __future__ import annotations
import asyncio
from typing import Any, Awaitable, Callable

class Debouncer:
    """Calls `callback(latest_value)` once after `delay_s` of quiet."""

    def __init__(self, delay_s: float, callback: Callable[[Any], Awaitable[None]]) -> None:
        self._delay = delay_s
        self._callback = callback
        self._latest: Any = None
        self._task: asyncio.Task | None = None

    def bump(self, value: Any) -> None:
        self._latest = value
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        await self._callback(self._latest)
```

- [ ] **Step 4: Run test, expect pass**

Run: `python -m pytest tests/test_debounce.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add vdesk_collapser/debounce.py tests/test_debounce.py pyproject.toml
git commit -m "feat(collapser): asyncio debouncer"
```

---

## Task 10: Daemon (socket2 reader + main loop)

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/daemon.py`

This task has no isolated unit test (socket connection is the integration boundary). Tested manually via the CLI's `--once` and `--simulate` flags in Task 11.

- [ ] **Step 1: Implement `daemon.py`**

```python
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import os
from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.debounce import Debouncer
from vdesk_collapser.driver import Driver, HyprctlDriver
from vdesk_collapser.transition import run_transition

log = logging.getLogger("vdesk-collapser")

def _socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    his = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    return Path(runtime) / "hypr" / his / ".socket2.sock"

async def _read_events(path: Path, on_monitor_event: callable) -> None:
    reader, _ = await asyncio.open_unix_connection(str(path))
    while not reader.at_eof():
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if text.startswith("monitoradded>>") or text.startswith("monitorremoved>>"):
            on_monitor_event()

def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

async def run_daemon(config_path: Path, driver: Driver | None = None) -> None:
    cfg = load_config(config_path)
    state_dir = Path(os.path.expanduser(cfg.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(exist_ok=True)

    drv: Driver = driver or HyprctlDriver()
    current_profile = len(drv.monitors())
    log.info("starting; current_profile=%d", current_profile)

    async def on_debounce_fire(target_count: int) -> None:
        nonlocal current_profile
        if target_count == current_profile:
            return
        log.info("transition %d -> %d", current_profile, target_count)
        await asyncio.to_thread(
            run_transition,
            drv, cfg, current_profile, target_count, state_dir, _now_iso(),
        )
        current_profile = target_count

    debouncer = Debouncer(delay_s=cfg.debounce_ms / 1000.0, callback=on_debounce_fire)

    def on_monitor_event() -> None:
        debouncer.bump(len(drv.monitors()))

    await _read_events(_socket_path(), on_monitor_event)
```

- [ ] **Step 2: Smoke-import the module**

Run: `python -c "from vdesk_collapser.daemon import run_daemon; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add vdesk_collapser/daemon.py
git commit -m "feat(collapser): daemon main loop + socket2 reader"
```

---

## Task 11: CLI entrypoint

**Files:**
- Create: `tools/vdesk-collapser/vdesk_collapser/cli.py`
- Create: `tools/vdesk-collapser/vdesk_collapser/__main__.py`
- Create: `tools/vdesk-collapser/tests/test_cli.py`

- [ ] **Step 1: Write failing test**

`tests/test_cli.py`:

```python
import sys
from pathlib import Path
from vdesk_collapser.cli import _build_parser, run_once_with_simulated_count
from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Config, Matcher, Rule

def test_parser_accepts_simulate_once_and_dry_run():
    p = _build_parser()
    ns = p.parse_args(["--simulate", "1", "--once", "--dry-run", "--config", "/tmp/c.toml"])
    assert ns.simulate == 1
    assert ns.once is True
    assert ns.dry_run is True
    assert ns.config == "/tmp/c.toml"

def test_run_once_with_simulated_count_drives_transition(tmp_state_dir: Path):
    driver = FakeDriver(
        clients=[{
            "address": "0x1", "class": "Slack", "initialTitle": "Slack", "title": "Slack",
            "pid": 4711, "workspace": {"id": 1}, "monitor": 0,
            "floating": False, "at": [0, 0], "size": [800, 600],
        }],
        monitors=[{"id": 0, "name": "DP-1"}, {"id": 1, "name": "DP-2"}, {"id": 2, "name": "DP-3"}],
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_once_with_simulated_count(driver, cfg, simulated=1, state_dir=tmp_state_dir)
    assert ("unpinwindow", "address:0x1") in driver.calls
    assert ("movetodesksilent", "9,address:0x1") in driver.calls
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_cli.py -v`

- [ ] **Step 3: Implement `cli.py`**

```python
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.daemon import run_daemon
from vdesk_collapser.driver import Driver, HyprctlDriver
from vdesk_collapser.models import Config
from vdesk_collapser.transition import run_transition

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vdesk-collapser")
    p.add_argument("--config", default=os.path.expanduser("~/.config/vdesk-collapser/config.toml"))
    p.add_argument("--dry-run", action="store_true", help="log dispatches without executing")
    p.add_argument("--once", action="store_true", help="run a single transition and exit")
    p.add_argument("--simulate", type=int, default=None,
                   help="pretend N monitors are connected (use with --once)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p

def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

def run_once_with_simulated_count(
    driver: Driver, cfg: Config, simulated: int, state_dir: Path,
) -> None:
    # Read "current" count from the persisted state file if present, else fall back
    # to whatever the driver reports.
    state_file = state_dir / "state.json"
    current = None
    if state_file.exists():
        import json
        try:
            current = int(json.loads(state_file.read_text()).get("current_profile"))
        except Exception:
            current = None
    if current is None:
        current = len(driver.monitors())
    if current == simulated:
        return
    run_transition(driver, cfg, n_old=current, m_new=simulated,
                   state_dir=state_dir, now_iso=_now_iso())

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = load_config(Path(args.config))
    state_dir = Path(os.path.expanduser(cfg.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(exist_ok=True)
    driver: Driver = HyprctlDriver(dry_run=args.dry_run)

    if args.once:
        if args.simulate is not None:
            run_once_with_simulated_count(driver, cfg, args.simulate, state_dir)
        else:
            current = len(driver.monitors())
            run_once_with_simulated_count(driver, cfg, current, state_dir)
        return 0

    asyncio.run(run_daemon(Path(args.config), driver=driver))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `__main__.py`**

```python
from vdesk_collapser.cli import main
import sys
sys.exit(main())
```

- [ ] **Step 5: Run tests, expect pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add vdesk_collapser/cli.py vdesk_collapser/__main__.py tests/test_cli.py
git commit -m "feat(collapser): CLI with --once/--simulate/--dry-run"
```

---

## Task 12: README and Hyprland integration docs

**Files:**
- Create: `tools/vdesk-collapser/README.md`

- [ ] **Step 1: Write README**

```markdown
# vdesk-collapser

Companion tool for [hyprland-virtual-desktops](../../). Snapshots the window
layout per monitor-count profile, applies per-profile rules on transition,
and restores known profiles when revisited. Drives the plugin only via
existing `hyprctl` dispatchers.

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

See [`docs/superpowers/specs/2026-05-12-monitor-profile-collapser-design.md`](../../docs/superpowers/specs/2026-05-12-monitor-profile-collapser-design.md).
```

- [ ] **Step 2: Commit**

```bash
git add tools/vdesk-collapser/README.md
git commit -m "docs(collapser): README and Hyprland integration"
```

---

## Task 13: End-to-end smoke test against a live Hyprland session

This task is manual. It verifies the daemon behaves correctly against the real plugin.

- [ ] **Step 1: Install**

```bash
cd tools/vdesk-collapser
python -m pip install --user .
```

- [ ] **Step 2: Write a minimal config** at `~/.config/vdesk-collapser/config.toml`:

```toml
[[profile.1.rules]]
match.class = "Slack"
target_vdesk = 9
pin = false

[[profile.3.rules]]
match.class = "Slack"
pin = true
```

- [ ] **Step 3: Dry-run from 3-monitor state**

With 3 monitors connected and Slack pinned on vdesk 1:

```bash
vdesk-collapser --dry-run --once --simulate 1 --verbose
```

Expected log output should include:
- `hyprctl dispatch unpinwindow address:0x…` for the Slack window
- `hyprctl dispatch movetodesksilent 9,address:0x…`
- A snapshot file written at `~/.local/state/vdesk-collapser/snapshots/3.json`

Verify `~/.local/state/vdesk-collapser/snapshots/3.json` contains Slack with `"pinned": true` and the correct `vdesk`.

- [ ] **Step 4: Live run, collapse to 1 monitor**

```bash
vdesk-collapser --once --simulate 1
```

Verify: Slack is now on vdesk 9 and unpinned (`hyprctl printpinnedwindows` should not list it).

- [ ] **Step 5: Live run, expand back to 3 monitors**

```bash
vdesk-collapser --once --simulate 3
```

Verify: Slack is back on the vdesk it was on before collapse, pinned.

- [ ] **Step 6: Daemon mode end-to-end**

```bash
vdesk-collapser --verbose &
```

Disconnect two monitors physically (or via `wlr-randr`). After ~1.5s of stable monitor count, the daemon should log the transition and apply the same effects as Step 4. Reconnect → same as Step 5.

- [ ] **Step 7: Commit any tweaks discovered during smoke**

```bash
git commit -am "fix(collapser): smoke-test adjustments"
```

(Skip if nothing changed.)

---

## Self-review notes

Spec coverage check (each spec section → task that covers it):

- **Architecture / lifecycle** → Tasks 10, 11
- **Transition procedure (snapshot/rules/replay)** → Tasks 5, 6, 7, 8
- **Window identity (address + key fallback)** → Task 7
- **Config schema** → Task 3
- **Snapshot schema + atomic writes** → Tasks 2, 5
- **State file + flock** → Task 8
- **Concurrency / re-entry (debouncer + flock)** → Tasks 8, 9
- **Edge cases** → Covered by tests in 6, 7, 8 (rule-wins-over-snapshot, missing windows, idempotence, pin/unpin ordering)
- **CLI flags (--dry-run/--simulate/--once)** → Task 11
- **Project layout** → Task 1
- **Manual integration testing** → Task 13

Naming consistency check passed: `build_snapshot`, `write_snapshot`, `read_snapshot`, `replay_snapshot`, `snapshot_path`, `apply_rules`, `match_window`, `run_transition`, `run_daemon` used identically across tasks.

No placeholders. All code blocks complete.
