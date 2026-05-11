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
        clients=[_client("0x1", "Slack", "Slack", 4711, ws_id=9)],
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
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_transition(driver, cfg, n_old=3, m_new=1, state_dir=tmp_state_dir, now_iso="t")
    move_calls = [c for c in driver.calls if c[0] == "movetodesksilent"]
    assert move_calls == [("movetodesksilent", "9,address:0x1")]
