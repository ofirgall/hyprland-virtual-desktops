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
    p.write_text("garbage")
    driver = FakeDriver(clients=[], monitors=[], pinned=set(), workspace_to_vdesk={})
    write_snapshot(build_snapshot(driver, monitor_count=3, now_iso="t"), p)
    assert json.loads(p.read_text())["monitor_count"] == 3

def test_read_snapshot_missing_returns_none(tmp_state_dir: Path):
    assert read_snapshot(snapshot_path(tmp_state_dir, 7)) is None

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
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=5)],
        pinned=set(),
        workspace_to_vdesk={5: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert driver.calls == [("movetodesksilent", "2,address:0x1")]

def test_replay_finds_window_by_key_when_address_differs():
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
    snap = Snapshot(monitor_count=3, taken_at="t", windows=[_ws(vdesk=1, pinned=True)])
    driver = FakeDriver(
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=1)],
        pinned=set(),
        workspace_to_vdesk={1: 1},
    )
    replay_snapshot(driver, snap, skip_addresses=set())
    assert ("pinwindow", "address:0x1") in driver.calls
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
