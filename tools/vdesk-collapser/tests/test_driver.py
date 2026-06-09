from vdesk_collapser.driver import FakeDriver, parse_pinned_windows, parse_printstate

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


def test_parse_pinned_windows_extracts_addresses():
    out = "Window 5f9499eec170 (Slack): * dev (Channel) - Drift - Slack\n\n"
    assert parse_pinned_windows(out) == {"0x5f9499eec170"}


def test_parse_pinned_windows_multiple():
    out = (
        "Window 5f9499eec170 (Slack): * dev (Channel) - Drift - Slack\n"
        "Window abc123 (Firefox): Mozilla Firefox\n"
    )
    assert parse_pinned_windows(out) == {"0x5f9499eec170", "0xabc123"}


def test_parse_pinned_windows_empty():
    assert parse_pinned_windows("") == set()
    assert parse_pinned_windows("\n") == set()


def test_parse_printstate_real_output():
    out = (
        "Virtual desks\n"
        "- 8: 8\n"
        "  Focused: false\n"
        "  Populated: false\n"
        "  Workspaces: 24, 23, 22\n"
        "  Windows: 0\n"
        "  Status: \n"
        "\n"
        "- 4: 4\n"
        "  Focused: false\n"
        "  Populated: false\n"
        "  Workspaces: 12, 11, 10\n"
        "  Windows: 0\n"
        "  Status: \n"
        "\n"
        "- 9  hypr: 9\n"
        "  Focused: true\n"
        "  Populated: true\n"
        "  Workspaces: 27, 26, 25\n"
        "  Windows: 2\n"
        "  Status: DONE\n"
    )
    mapping = parse_printstate(out)
    assert mapping == {
        24: 8, 23: 8, 22: 8,
        12: 4, 11: 4, 10: 4,
        27: 9, 26: 9, 25: 9,
    }


def test_parse_printstate_empty():
    assert parse_printstate("") == {}
    assert parse_printstate("Virtual desks\n") == {}
