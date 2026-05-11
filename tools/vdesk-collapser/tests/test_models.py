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
