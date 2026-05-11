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

def test_fake_driver_mutates_pinned_on_pin_dispatch():
    d = FakeDriver(pinned=set())
    d.dispatch("pinwindow", "address:0x1")
    assert d.pinned_addresses() == {"0x1"}

def test_fake_driver_mutates_pinned_on_unpin_dispatch():
    d = FakeDriver(pinned={"0x1"})
    d.dispatch("unpinwindow", "address:0x1")
    assert d.pinned_addresses() == set()
