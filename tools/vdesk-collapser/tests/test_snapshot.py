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
